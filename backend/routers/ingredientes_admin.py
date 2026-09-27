"""
routers/ingredientes_admin.py
Objetivo: COM-37 v5: módulo "Gestión de Ingredientes" exclusivo del Administrador de
          Sistemas, sobre el modelo de DOS CONCEPTOS:
            - INGREDIENTE: lo que se cocina; unidad de USO (pizca, cucharadita, taza,
              rodaja, unidad...) declarada en receta_ingrediente / ingredientes.
            - INSUMO: lo que se compra; unidad de COMPRA (Kg, L, atado, unidad...);
              origen 'SCRAPER' (SISAP) o 'MANUAL' (registrado por el Admin).
          Secciones del router:
            A) Ingredientes: listado con indicadores, crear y editar/renombrar SIN
               borrado físico (toda edición advierte inconsistencias en el frontend).
            B) Emparejamiento ingrediente<->insumo: insumos vinculados con precio de
               hoy y fuente, búsqueda de insumos del scraper, vinculación con
               equivalencias opcionales, creación de insumo MANUAL (unidad de compra +
               precio con vigencia + equivalencias en un solo paso), edición y
               desvinculación de insumos manuales.
            C) Equivalencias unidad de USO -> gramos (ingredientes_equivalencias):
               CRUD con desactivación lógica; si no existe equivalencia, el motor
               aplica la conversión estándar de la unidad de uso.
            D) Precios manuales por INSUMO (insumos_precios_manuales): períodos con
               vigencia opcional y validación de solapes por insumo.
            E) Re-emparejado de insumos huérfanos (ingrediente_id NULL) usando el
               algoritmo de reconocimiento existente (scraper/classifiers/heuristics.py)
               más matching por nombre normalizado.
            LEGACY (COM-37 v1): endpoints de precios manuales POR INGREDIENTE
               (ingredientes_precios_manuales) conservados como último fallback de
               resolución de precios; no se eliminan.
Precedencia de precio (precios_insumos.py): scraper del día > predicción RF (Evaluar)
          > período manual del insumo > manual legacy del ingrediente. Entre insumos de
          un mismo ingrediente gana el menor costo por gramo (criterio de compra).
Permisos: todos los endpoints exigen es_admin_sistema (403 en caso contrario).
Uso: Registrado en main.py con prefijo /api/v1 (include ya existente de COM-37).
Referencia: ticket COM-37 v5 (solo trazabilidad).
"""
import unicodedata
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema
# COM-37 v5: precio de hoy por insumo (para exhibir fuente y ppg en el listado)
from precios_insumos import precios_por_gramo_por_insumo

# COM-37: algoritmo de reconocimiento existente del scraper para re-emparejar insumos.
# Si el paquete no fuera importable en este contexto, el re-emparejado degrada a
# matching por nombre normalizado (no se rompe el endpoint).
try:
    from scraper.classifiers.heuristics import clasificar_heuristica_mejorada
    HEURISTICA_DISPONIBLE = True
except Exception:  # pragma: no cover - degradación controlada
    clasificar_heuristica_mejorada = None
    HEURISTICA_DISPONIBLE = False

router = APIRouter(prefix="/ingredientes-admin", tags=["Gestión de Ingredientes (COM-37 v5)"])


# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class CrearIngredienteInput(BaseModel):
    usuario_solicitante_id: int
    nombre: str
    categoria_id: Optional[int] = None
    unidad_medida_id: int          # unidad de USO por defecto del ingrediente
    peso_estimado_g: float = 100.0


class EditarIngredienteInput(BaseModel):
    """COM-37: edición sin borrado. El frontend advierte inconsistencias históricas."""
    usuario_solicitante_id: int
    nombre: Optional[str] = None
    categoria_id: Optional[int] = None
    unidad_medida_id: Optional[int] = None
    peso_estimado_g: Optional[float] = None


class EquivalenciaItem(BaseModel):
    """Equivalencia unidad de USO -> gramos para un insumo concreto."""
    unidad_uso_id: int
    gramos_por_unidad_uso: float
    observacion: Optional[str] = None


class VincularInsumoInput(BaseModel):
    """Vincula un insumo existente (scraper o manual) al ingrediente."""
    usuario_solicitante_id: int
    insumo_id: int
    reasignar: bool = False        # permite mover un insumo ya vinculado a otro ingrediente
    equivalencias: List[EquivalenciaItem] = []


class CrearInsumoManualInput(BaseModel):
    """Crea insumo MANUAL + su primer período de precio + equivalencias opcionales."""
    usuario_solicitante_id: int
    nombre: str
    unidad_medida_id: int          # unidad de COMPRA (Kg, L, atado, und...)
    precio_por_unidad: float
    usar_rango: bool = False
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    observacion: Optional[str] = None
    equivalencias: List[EquivalenciaItem] = []


class EditarInsumoManualInput(BaseModel):
    """Solo insumos de origen MANUAL (no se altera el catálogo del scraper)."""
    usuario_solicitante_id: int
    nombre: Optional[str] = None
    unidad_medida_id: Optional[int] = None


class CrearEquivalenciaInput(BaseModel):
    usuario_solicitante_id: int
    insumo_id: int
    unidad_uso_id: int
    gramos_por_unidad_uso: float
    observacion: Optional[str] = None


class EditarEquivalenciaInput(BaseModel):
    usuario_solicitante_id: int
    unidad_uso_id: Optional[int] = None
    gramos_por_unidad_uso: Optional[float] = None
    observacion: Optional[str] = None


class CrearPrecioInsumoInput(BaseModel):
    usuario_solicitante_id: int
    precio_por_unidad: float
    usar_rango: bool = False
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    observacion: Optional[str] = None


class EditarPrecioInsumoInput(BaseModel):
    usuario_solicitante_id: int
    precio_por_unidad: Optional[float] = None
    usar_rango: Optional[bool] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    observacion: Optional[str] = None


# LEGACY COM-37 v1 (precios manuales por INGREDIENTE, tabla ingredientes_precios_manuales)
class CrearPrecioManualLegacyInput(BaseModel):
    usuario_solicitante_id: int
    precio_por_unidad: float
    usar_rango: bool = False
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    observacion: Optional[str] = None


class EditarPrecioManualLegacyInput(BaseModel):
    usuario_solicitante_id: int
    precio_por_unidad: Optional[float] = None
    usar_rango: Optional[bool] = None
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    observacion: Optional[str] = None


# ==========================================
# HELPERS
# ==========================================
def _validar_admin(cur, usuario_id: int) -> None:
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: la Gestión de Ingredientes es exclusiva del Administrador de Sistemas.")


def _normalizar(texto):
    if not texto:
        return ''
    txt = unicodedata.normalize('NFD', str(texto).lower())
    return ''.join(c for c in txt if unicodedata.category(c) != 'Mn').strip()


def _parse_fecha(valor: Optional[str]) -> Optional[date]:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor)
    except Exception:
        raise HTTPException(status_code=400, detail=f"Fecha inválida: {valor} (use YYYY-MM-DD).")


def _solapan(a_ini, a_fin, b_ini, b_fin) -> bool:
    a_start = a_ini or date.min
    a_end = a_fin or date.max
    b_start = b_ini or date.min
    b_end = b_fin or date.max
    return a_start <= b_end and b_start <= a_end


def _validar_sin_solapes_insumo(cur, insumo_id, ini, fin, excluir_id=None):
    cur.execute("""
        SELECT id, fecha_inicio, fecha_fin
        FROM insumos_precios_manuales
        WHERE insumo_id = %s AND estado_activo = TRUE
          AND (%s IS NULL OR id <> %s);
    """, (insumo_id, excluir_id, excluir_id))
    for p in cur.fetchall():
        if _solapan(ini, fin, p['fecha_inicio'], p['fecha_fin']):
            raise HTTPException(
                status_code=400,
                detail=f"El rango se solapa con un período activo del insumo "
                       f"(id {p['id']}: {p['fecha_inicio'] or 'siempre'} → {p['fecha_fin'] or 'abierto'}). "
                       f"Desactívelo antes de registrar este precio.")


def _validar_unidad(cur, unidad_id: Optional[int]) -> None:
    if unidad_id is None:
        return
    cur.execute("SELECT id FROM unidades_medida WHERE id = %s;", (unidad_id,))
    if not cur.fetchone():
        raise HTTPException(status_code=400, detail=f"Unidad de medida inexistente: id {unidad_id}.")


def _upsert_equivalencias(cur, ingrediente_id, insumo_id, items: List[EquivalenciaItem], creador_id):
    """Crea/actualiza equivalencias unidad de USO -> gramos para el par (ing, insumo)."""
    n = 0
    for eq in items or []:
        if eq.gramos_por_unidad_uso is None or eq.gramos_por_unidad_uso <= 0:
            raise HTTPException(status_code=400, detail="gramos_por_unidad_uso debe ser mayor a cero.")
        cur.execute("""
            INSERT INTO ingredientes_equivalencias
                (ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso, observacion, creado_por)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ingrediente_id, insumo_id, unidad_uso_id)
            DO UPDATE SET gramos_por_unidad_uso = EXCLUDED.gramos_por_unidad_uso,
                          observacion = COALESCE(EXCLUDED.observacion, ingredientes_equivalencias.observacion),
                          estado_activo = TRUE;
        """, (ingrediente_id, insumo_id, eq.unidad_uso_id, eq.gramos_por_unidad_uso,
              (eq.observacion or '').strip() or None, creador_id))
        n += 1
    return n


def _mapa_categorias(cur):
    cur.execute("SELECT id, nombre FROM categorias_alimentos;")
    return {r['nombre']: r['id'] for r in cur.fetchall()}


# ==========================================
# SECCIÓN A: INGREDIENTES (CRUD sin borrado)
# ==========================================
@router.get("")
def listar_ingredientes(usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37 v5: ingredientes + indicadores de emparejamiento y precios."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT i.id, i.nombre, i.categoria_id, ca.nombre AS categoria_nombre,
                   i.unidad_medida_id, um.nombre AS unidad_nombre,
                   um.abreviatura AS unidad_abrev, i.peso_estimado_g,
                   (SELECT COUNT(*) FROM insumos ins
                     WHERE ins.ingrediente_id = i.id) AS n_insumos,
                   (SELECT COUNT(*) FROM insumos ins
                     WHERE ins.ingrediente_id = i.id AND ins.origen = 'MANUAL') AS n_insumos_manuales,
                   (SELECT COUNT(*) FROM insumos ins
                     JOIN historial_precios hp ON hp.insumo_id = ins.id
                     WHERE ins.ingrediente_id = i.id) AS n_insumos_con_precio_scraper,
                   (SELECT COUNT(*) FROM ingredientes_equivalencias eq
                     WHERE eq.ingrediente_id = i.id AND eq.estado_activo = TRUE) AS n_equivalencias,
                   (SELECT COUNT(*) FROM ingredientes_precios_manuales pm
                     WHERE pm.ingrediente_id = i.id AND pm.estado_activo = TRUE) AS n_precios_manuales_legacy
            FROM ingredientes i
            LEFT JOIN categorias_alimentos ca ON ca.id = i.categoria_id
            LEFT JOIN unidades_medida um ON um.id = i.unidad_medida_id
            ORDER BY i.nombre;
        """)
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar ingredientes: {e}")
    finally:
        cur.close()


@router.post("", status_code=201)
def crear_ingrediente(data: CrearIngredienteInput, db=Depends(get_db)):
    """COM-37: crea un ingrediente (unidad de USO por defecto)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        nombre = (data.nombre or '').strip()
        if len(nombre) < 2:
            raise HTTPException(status_code=400, detail="El nombre del ingrediente es obligatorio.")
        _validar_unidad(cur, data.unidad_medida_id)
        cur.execute("SELECT id FROM ingredientes WHERE LOWER(nombre) = LOWER(%s);", (nombre,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Ya existe un ingrediente llamado '{nombre}'.")
        cur.execute("""
            INSERT INTO ingredientes (nombre, categoria_id, unidad_medida_id, peso_estimado_g)
            VALUES (%s, %s, %s, %s)
            RETURNING id, nombre;
        """, (nombre, data.categoria_id, data.unidad_medida_id, data.peso_estimado_g))
        nuevo = cur.fetchone()
        db.commit()
        return {'id': nuevo['id'], 'nombre': nuevo['nombre'],
                'message': 'Ingrediente creado. Vincule insumos del scraper o registre un insumo manual.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el ingrediente: {e}")
    finally:
        cur.close()


@router.put("/{ingrediente_id}")
def editar_ingrediente(ingrediente_id: int, data: EditarIngredienteInput, db=Depends(get_db)):
    """COM-37: edición/renombrado SIN borrado físico (advertencia de inconsistencias en UI)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM ingredientes WHERE id = %s;", (ingrediente_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ingrediente no encontrado.")
        if data.nombre is not None:
            nombre = data.nombre.strip()
            if len(nombre) < 2:
                raise HTTPException(status_code=400, detail="El nombre del ingrediente es obligatorio.")
            cur.execute("SELECT id FROM ingredientes WHERE LOWER(nombre) = LOWER(%s) AND id <> %s;",
                        (nombre, ingrediente_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Ya existe otro ingrediente llamado '{nombre}'.")
            cur.execute("UPDATE ingredientes SET nombre = %s WHERE id = %s;", (nombre, ingrediente_id))
        if data.categoria_id is not None:
            cur.execute("UPDATE ingredientes SET categoria_id = %s WHERE id = %s;",
                        (data.categoria_id, ingrediente_id))
        if data.unidad_medida_id is not None:
            _validar_unidad(cur, data.unidad_medida_id)
            cur.execute("UPDATE ingredientes SET unidad_medida_id = %s WHERE id = %s;",
                        (data.unidad_medida_id, ingrediente_id))
        if data.peso_estimado_g is not None:
            if data.peso_estimado_g <= 0:
                raise HTTPException(status_code=400, detail="peso_estimado_g debe ser mayor a cero.")
            cur.execute("UPDATE ingredientes SET peso_estimado_g = %s WHERE id = %s;",
                        (data.peso_estimado_g, ingrediente_id))
        db.commit()
        return {'message': 'Ingrediente actualizado. Verifique emparejamientos, equivalencias y precios.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al editar el ingrediente: {e}")
    finally:
        cur.close()


# ==========================================
# SECCIÓN B: EMPAREJAMIENTO INGREDIENTE <-> INSUMO
# ==========================================
@router.get("/buscar-insumos")
def buscar_insumos(
    usuario_solicitante_id: int,
    q: str = Query('', description="Texto del nombre del insumo"),
    solo_sin_vincular: bool = Query(False, description="Solo insumos huérfanos (ingrediente_id NULL)"),
    db=Depends(get_db),
):
    """COM-37 v5: búsqueda de insumos (scraper y manuales) para vincular al ingrediente."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT ins.id, ins.nombre, ins.origen, ins.ingrediente_id,
                   i2.nombre AS ingrediente_actual,
                   um.nombre AS unidad_nombre, um.abreviatura AS unidad_abrev
            FROM insumos ins
            LEFT JOIN unidades_medida um ON um.id = ins.unidad_medida_id
            LEFT JOIN ingredientes i2 ON i2.id = ins.ingrediente_id
            WHERE (%s = '' OR ins.nombre ILIKE %s)
              AND (%s = FALSE OR ins.ingrediente_id IS NULL)
            ORDER BY ins.nombre
            LIMIT 30;
        """, (q, f"%{q}%", solo_sin_vincular))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al buscar insumos: {e}")
    finally:
        cur.close()


@router.get("/{ingrediente_id}/insumos")
def listar_insumos_del_ingrediente(
    ingrediente_id: int,
    usuario_solicitante_id: int,
    fecha: Optional[str] = Query(None, description="Fecha para precio de hoy (default: hoy)"),
    db=Depends(get_db),
):
    """COM-37 v5: insumos vinculados al ingrediente con unidad de compra, último precio
    scraper, períodos manuales activos, equivalencias y precio por gramo de hoy."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        fecha_obj = _parse_fecha(fecha) or date.today()
        cur.execute("""
            SELECT ins.id, ins.nombre, ins.origen, ins.unidad_medida_id,
                   um.nombre AS unidad_nombre, um.abreviatura AS unidad_abrev,
                   (SELECT hp.precio_prom FROM historial_precios hp
                     WHERE hp.insumo_id = ins.id ORDER BY hp.fecha DESC LIMIT 1) AS ultimo_precio_scraper,
                   (SELECT hp.fecha FROM historial_precios hp
                     WHERE hp.insumo_id = ins.id ORDER BY hp.fecha DESC LIMIT 1) AS fecha_ultimo_precio,
                   (SELECT COUNT(*) FROM insumos_precios_manuales ipm
                     WHERE ipm.insumo_id = ins.id AND ipm.estado_activo = TRUE) AS n_precios_manuales,
                   (SELECT COUNT(*) FROM ingredientes_equivalencias eq
                     WHERE eq.ingrediente_id = ins.ingrediente_id AND eq.insumo_id = ins.id
                       AND eq.estado_activo = TRUE) AS n_equivalencias
            FROM insumos ins
            LEFT JOIN unidades_medida um ON um.id = ins.unidad_medida_id
            WHERE ins.ingrediente_id = %s
            ORDER BY ins.origen, ins.nombre;
        """, (ingrediente_id,))
        filas = cur.fetchall()
        precios_hoy = precios_por_gramo_por_insumo(cur, fecha_obj)
        for f in filas:
            opc = precios_hoy.get(f['id'])
            f['precio_por_gramo_hoy'] = opc['ppg'] if opc else None
            f['fuente_precio_hoy'] = opc['fuente'] if opc else None
        return filas
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar insumos del ingrediente: {e}")
    finally:
        cur.close()


@router.post("/{ingrediente_id}/vincular-insumo")
def vincular_insumo(ingrediente_id: int, data: VincularInsumoInput, db=Depends(get_db)):
    """COM-37 v5: vincula un insumo existente al ingrediente y registra equivalencias."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM ingredientes WHERE id = %s;", (ingrediente_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ingrediente no encontrado.")
        cur.execute("SELECT id, nombre, ingrediente_id FROM insumos WHERE id = %s;", (data.insumo_id,))
        ins = cur.fetchone()
        if not ins:
            raise HTTPException(status_code=404, detail="Insumo no encontrado.")
        if ins['ingrediente_id'] is not None and ins['ingrediente_id'] != ingrediente_id and not data.reasignar:
            raise HTTPException(
                status_code=400,
                detail=f"El insumo '{ins['nombre']}' ya está vinculado a otro ingrediente. "
                       f"Use reasignar=true para moverlo.")
        cur.execute("UPDATE insumos SET ingrediente_id = %s WHERE id = %s;",
                    (ingrediente_id, data.insumo_id))
        n_eq = _upsert_equivalencias(cur, ingrediente_id, data.insumo_id,
                                     data.equivalencias, data.usuario_solicitante_id)
        db.commit()
        return {'message': f"Insumo '{ins['nombre']}' vinculado. Equivalencias registradas: {n_eq}."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al vincular el insumo: {e}")
    finally:
        cur.close()


@router.post("/{ingrediente_id}/insumos-manuales", status_code=201)
def crear_insumo_manual(ingrediente_id: int, data: CrearInsumoManualInput, db=Depends(get_db)):
    """
    COM-37 v5: crea un insumo MANUAL (origen='MANUAL') vinculado al ingrediente, con su
    primer período de precio (unidad de COMPRA, vigencia opcional) y equivalencias
    unidad de USO -> gramos. Todo en una transacción.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM ingredientes WHERE id = %s;", (ingrediente_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ingrediente no encontrado.")
        nombre = (data.nombre or '').strip()
        if len(nombre) < 2:
            raise HTTPException(status_code=400, detail="El nombre del insumo es obligatorio.")
        if data.precio_por_unidad is None or data.precio_por_unidad <= 0:
            raise HTTPException(status_code=400, detail="El precio por unidad debe ser mayor a cero.")
        _validar_unidad(cur, data.unidad_medida_id)
        cur.execute("SELECT id FROM insumos WHERE LOWER(nombre) = LOWER(%s);", (nombre,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"Ya existe un insumo llamado '{nombre}'.")
        ini = fin = None
        if data.usar_rango:
            ini = _parse_fecha(data.fecha_inicio)
            fin = _parse_fecha(data.fecha_fin)
            if ini is None:
                raise HTTPException(status_code=400, detail="Con el rango activado, fecha_inicio es obligatoria.")
            if fin is not None and fin < ini:
                raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")

        cur.execute("""
            INSERT INTO insumos (ingrediente_id, nombre, unidad_medida_id, origen)
            VALUES (%s, %s, %s, 'MANUAL')
            RETURNING id;
        """, (ingrediente_id, nombre, data.unidad_medida_id))
        insumo_id = cur.fetchone()['id']

        cur.execute("""
            INSERT INTO insumos_precios_manuales
                (insumo_id, precio_por_unidad, fecha_inicio, fecha_fin, observacion, creado_por)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (insumo_id, data.precio_por_unidad, ini, fin,
              (data.observacion or '').strip() or None, data.usuario_solicitante_id))

        n_eq = _upsert_equivalencias(cur, ingrediente_id, insumo_id,
                                     data.equivalencias, data.usuario_solicitante_id)
        db.commit()
        return {'insumo_id': insumo_id,
                'message': f"Insumo manual '{nombre}' creado con precio y {n_eq} equivalencia(s)."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el insumo manual: {e}")
    finally:
        cur.close()


@router.put("/insumos/{insumo_id}")
def editar_insumo_manual(insumo_id: int, data: EditarInsumoManualInput, db=Depends(get_db)):
    """COM-37 v5: edita nombre/unidad de compra SOLO de insumos MANUALES."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id, origen, nombre FROM insumos WHERE id = %s;", (insumo_id,))
        ins = cur.fetchone()
        if not ins:
            raise HTTPException(status_code=404, detail="Insumo no encontrado.")
        if ins['origen'] != 'MANUAL':
            raise HTTPException(status_code=400,
                            detail="Los insumos del scraper no se editan aquí; gestione equivalencias y precios.")
        if data.nombre is not None:
            nombre = data.nombre.strip()
            if len(nombre) < 2:
                raise HTTPException(status_code=400, detail="El nombre del insumo es obligatorio.")
            cur.execute("SELECT id FROM insumos WHERE LOWER(nombre) = LOWER(%s) AND id <> %s;",
                        (nombre, insumo_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail=f"Ya existe otro insumo llamado '{nombre}'.")
            cur.execute("UPDATE insumos SET nombre = %s WHERE id = %s;", (nombre, insumo_id))
        if data.unidad_medida_id is not None:
            _validar_unidad(cur, data.unidad_medida_id)
            cur.execute("UPDATE insumos SET unidad_medida_id = %s WHERE id = %s;",
                        (data.unidad_medida_id, insumo_id))
        db.commit()
        return {'message': f"Insumo manual '{ins['nombre']}' actualizado."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al editar el insumo manual: {e}")
    finally:
        cur.close()


@router.put("/insumos/{insumo_id}/desvincular")
def desvincular_insumo(insumo_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37 v5: deja el insumo huérfano (ingrediente_id NULL); conserva historial y precios."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("UPDATE insumos SET ingrediente_id = NULL WHERE id = %s;", (insumo_id,))
        if cur.rowcount != 1:
            raise HTTPException(status_code=404, detail="Insumo no encontrado.")
        db.commit()
        return {'message': 'Insumo desvinculado. Queda como huérfano para re-emparejado.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al desvincular el insumo: {e}")
    finally:
        cur.close()


# ==========================================
# SECCIÓN C: EQUIVALENCIAS (unidad de USO -> gramos)
# ==========================================
@router.get("/{ingrediente_id}/equivalencias")
def listar_equivalencias(
    ingrediente_id: int,
    usuario_solicitante_id: int,
    insumo_id: Optional[int] = Query(None),
    db=Depends(get_db),
):
    """COM-37 v5: equivalencias activas e inactivas del ingrediente (opcionalmente por insumo)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT eq.id, eq.ingrediente_id, eq.insumo_id, ins.nombre AS insumo_nombre,
                   eq.unidad_uso_id, um.nombre AS unidad_uso_nombre, um.abreviatura AS unidad_uso_abrev,
                   eq.gramos_por_unidad_uso, eq.observacion, eq.estado_activo, eq.fecha_registro
            FROM ingredientes_equivalencias eq
            JOIN insumos ins ON ins.id = eq.insumo_id
            JOIN unidades_medida um ON um.id = eq.unidad_uso_id
            WHERE eq.ingrediente_id = %s AND (%s IS NULL OR eq.insumo_id = %s)
            ORDER BY eq.estado_activo DESC, ins.nombre, um.nombre;
        """, (ingrediente_id, insumo_id, insumo_id))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar equivalencias: {e}")
    finally:
        cur.close()


@router.post("/{ingrediente_id}/equivalencias", status_code=201)
def crear_equivalencia(ingrediente_id: int, data: CrearEquivalenciaInput, db=Depends(get_db)):
    """COM-37 v5: registra/actualiza la equivalencia (ingrediente, insumo, unidad de uso)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        if data.gramos_por_unidad_uso <= 0:
            raise HTTPException(status_code=400, detail="gramos_por_unidad_uso debe ser mayor a cero.")
        cur.execute("SELECT id FROM insumos WHERE id = %s;", (data.insumo_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Insumo no encontrado.")
        _validar_unidad(cur, data.unidad_uso_id)
        cur.execute("""
            INSERT INTO ingredientes_equivalencias
                (ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso, observacion, creado_por)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (ingrediente_id, insumo_id, unidad_uso_id)
            DO UPDATE SET gramos_por_unidad_uso = EXCLUDED.gramos_por_unidad_uso,
                          observacion = COALESCE(EXCLUDED.observacion, ingredientes_equivalencias.observacion),
                          estado_activo = TRUE
            RETURNING id;
        """, (ingrediente_id, data.insumo_id, data.unidad_uso_id, data.gramos_por_unidad_uso,
              (data.observacion or '').strip() or None, data.usuario_solicitante_id))
        eq_id = cur.fetchone()['id']
        db.commit()
        return {'id': eq_id, 'message': 'Equivalencia registrada.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear la equivalencia: {e}")
    finally:
        cur.close()


@router.put("/equivalencias/{eq_id}")
def editar_equivalencia(eq_id: int, data: EditarEquivalenciaInput, db=Depends(get_db)):
    """COM-37 v5: edita gramos/unidad de uso/observación de una equivalencia."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM ingredientes_equivalencias WHERE id = %s;", (eq_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Equivalencia no encontrada.")
        if data.gramos_por_unidad_uso is not None:
            if data.gramos_por_unidad_uso <= 0:
                raise HTTPException(status_code=400, detail="gramos_por_unidad_uso debe ser mayor a cero.")
            cur.execute("UPDATE ingredientes_equivalencias SET gramos_por_unidad_uso = %s WHERE id = %s;",
                        (data.gramos_por_unidad_uso, eq_id))
        if data.unidad_uso_id is not None:
            _validar_unidad(cur, data.unidad_uso_id)
            cur.execute("UPDATE ingredientes_equivalencias SET unidad_uso_id = %s WHERE id = %s;",
                        (data.unidad_uso_id, eq_id))
        if data.observacion is not None:
            cur.execute("UPDATE ingredientes_equivalencias SET observacion = %s WHERE id = %s;",
                        ((data.observacion or '').strip() or None, eq_id))
        db.commit()
        return {'message': 'Equivalencia actualizada.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al editar la equivalencia: {e}")
    finally:
        cur.close()


@router.put("/equivalencias/{eq_id}/desactivar")
def desactivar_equivalencia(eq_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37 v5: baja lógica; el motor volverá a la conversión estándar de la unidad de uso."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            UPDATE ingredientes_equivalencias SET estado_activo = FALSE
            WHERE id = %s AND estado_activo = TRUE;
        """, (eq_id,))
        if cur.rowcount != 1:
            raise HTTPException(status_code=404, detail="Equivalencia no encontrada o ya inactiva.")
        db.commit()
        return {'message': 'Equivalencia desactivada: se usará la conversión estándar.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al desactivar la equivalencia: {e}")
    finally:
        cur.close()


# ==========================================
# SECCIÓN D: PRECIOS MANUALES POR INSUMO
# ==========================================
@router.get("/insumos/{insumo_id}/precios-manuales")
def listar_precios_insumo(insumo_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37 v5: períodos manuales del insumo (activos e inactivos), más recientes primero."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT ipm.id, ipm.insumo_id, ipm.precio_por_unidad, ipm.fecha_inicio, ipm.fecha_fin,
                   ipm.observacion, ipm.estado_activo, ipm.fecha_registro,
                   um.nombre AS unidad_nombre, um.abreviatura AS unidad_abrev,
                   u.nombres || ' ' || u.apellido_paterno AS creado_por_nombre
            FROM insumos_precios_manuales ipm
            JOIN insumos ins ON ins.id = ipm.insumo_id
            JOIN unidades_medida um ON um.id = ins.unidad_medida_id
            LEFT JOIN usuarios u ON u.id = ipm.creado_por
            WHERE ipm.insumo_id = %s
            ORDER BY ipm.fecha_registro DESC;
        """, (insumo_id,))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar precios del insumo: {e}")
    finally:
        cur.close()


@router.post("/insumos/{insumo_id}/precios-manuales", status_code=201)
def crear_precio_insumo(insumo_id: int, data: CrearPrecioInsumoInput, db=Depends(get_db)):
    """COM-37 v5: período manual en la unidad de COMPRA del insumo, vigencia opcional."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM insumos WHERE id = %s;", (insumo_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Insumo no encontrado.")
        if data.precio_por_unidad <= 0:
            raise HTTPException(status_code=400, detail="El precio por unidad debe ser mayor a cero.")
        ini = fin = None
        if data.usar_rango:
            ini = _parse_fecha(data.fecha_inicio)
            fin = _parse_fecha(data.fecha_fin)
            if ini is None:
                raise HTTPException(status_code=400, detail="Con el rango activado, fecha_inicio es obligatoria.")
            if fin is not None and fin < ini:
                raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")
        _validar_sin_solapes_insumo(cur, insumo_id, ini, fin)
        cur.execute("""
            INSERT INTO insumos_precios_manuales
                (insumo_id, precio_por_unidad, fecha_inicio, fecha_fin, observacion, creado_por)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (insumo_id, data.precio_por_unidad, ini, fin,
              (data.observacion or '').strip() or None, data.usuario_solicitante_id))
        nuevo = cur.fetchone()
        db.commit()
        return {'id': nuevo['id'],
                'message': 'Precio manual registrado para el insumo.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el precio manual: {e}")
    finally:
        cur.close()


@router.put("/precios-manuales/{periodo_id}")
def editar_precio_insumo(periodo_id: int, data: EditarPrecioInsumoInput, db=Depends(get_db)):
    """COM-37 v5: edita un período manual del insumo con re-validación de solapes."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("""
            SELECT id, insumo_id, precio_por_unidad, fecha_inicio, fecha_fin, observacion
            FROM insumos_precios_manuales WHERE id = %s;
        """, (periodo_id,))
        periodo = cur.fetchone()
        if not periodo:
            raise HTTPException(status_code=404, detail="Período de precio manual no encontrado.")
        enviados = data.dict(exclude_unset=True)
        precio = data.precio_por_unidad if data.precio_por_unidad is not None else float(periodo['precio_por_unidad'])
        if precio <= 0:
            raise HTTPException(status_code=400, detail="El precio por unidad debe ser mayor a cero.")
        usar_rango = data.usar_rango if data.usar_rango is not None else (periodo['fecha_inicio'] is not None)
        if usar_rango:
            ini = _parse_fecha(data.fecha_inicio) if data.fecha_inicio is not None else periodo['fecha_inicio']
            fin = _parse_fecha(data.fecha_fin) if data.fecha_fin is not None else periodo['fecha_fin']
            if ini is None:
                raise HTTPException(status_code=400, detail="Con el rango activado, fecha_inicio es obligatoria.")
            if fin is not None and fin < ini:
                raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")
        else:
            ini = fin = None
        _validar_sin_solapes_insumo(cur, periodo['insumo_id'], ini, fin, excluir_id=periodo_id)
        observacion = data.observacion if data.observacion is not None else periodo['observacion']
        cur.execute("""
            UPDATE insumos_precios_manuales
            SET precio_por_unidad = %s, fecha_inicio = %s, fecha_fin = %s, observacion = %s
            WHERE id = %s;
        """, (precio, ini, fin, (observacion or '').strip() or None, periodo_id))
        db.commit()
        return {'message': 'Período de precio manual actualizado.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al editar el precio manual: {e}")
    finally:
        cur.close()


@router.put("/precios-manuales/{periodo_id}/desactivar")
def desactivar_precio_insumo(periodo_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37 v5: baja lógica del período (trazabilidad conservada)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            UPDATE insumos_precios_manuales SET estado_activo = FALSE
            WHERE id = %s AND estado_activo = TRUE;
        """, (periodo_id,))
        if cur.rowcount != 1:
            raise HTTPException(status_code=404, detail="Período no encontrado o ya inactivo.")
        db.commit()
        return {'message': 'Período desactivado: el precio manual dejará de aplicarse.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al desactivar el período: {e}")
    finally:
        cur.close()


# ==========================================
# SECCIÓN E: RE-EMPAREJADO DE INSUMOS HUÉRFANOS
# ==========================================
@router.post("/reemparejar-insumos")
def reemparejar_insumos(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-37 v5: vincula insumos con ingrediente_id NULL usando el algoritmo de
    reconocimiento existente (heuristics.clasificar_heuristica_mejorada) y matching por
    nombre normalizado contra el catálogo vigente. Permite que crear/renombrar
    ingredientes alimente al algoritmo sin reiniciar el scraper.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("SELECT id, nombre FROM insumos WHERE ingrediente_id IS NULL;")
        huerfanos = cur.fetchall()
        if not huerfanos:
            return {'emparejados': 0, 'detalle': [], 'message': 'No hay insumos huérfanos por emparejar.'}

        mapa_cat = _mapa_categorias(cur)
        cur.execute("SELECT id, nombre FROM ingredientes;")
        norm_ing = [(r['id'], _normalizar(r['nombre'])) for r in cur.fetchall()]

        actualizados = []
        for ins in huerfanos:
            nombre_norm = _normalizar(ins['nombre'])
            candidato = None

            # 1) Algoritmo de reconocimiento existente (nombre genérico -> ingrediente)
            if HEURISTICA_DISPONIBLE:
                try:
                    generico, _cat_id = clasificar_heuristica_mejorada(ins['nombre'], mapa_cat)
                except Exception:
                    generico = None
                if generico:
                    gnorm = _normalizar(generico)
                    for iid, inorm in norm_ing:
                        if inorm == gnorm:
                            candidato = iid
                            break
                    if candidato is None:
                        for iid, inorm in norm_ing:
                            if gnorm and (gnorm in inorm or inorm in gnorm):
                                candidato = iid
                                break

            # 2) Matching directo por nombre normalizado del insumo
            if candidato is None:
                for iid, inorm in norm_ing:
                    if inorm and inorm == nombre_norm:
                        candidato = iid
                        break
            if candidato is None:
                for iid, inorm in norm_ing:
                    if inorm and len(inorm) >= 4 and (inorm in nombre_norm or nombre_norm in inorm):
                        candidato = iid
                        break

            if candidato is not None:
                cur.execute("UPDATE insumos SET ingrediente_id = %s WHERE id = %s;",
                            (candidato, ins['id']))
                actualizados.append({'insumo_id': ins['id'], 'insumo': ins['nombre'],
                                     'ingrediente_id': candidato})

        db.commit()
        cur.execute("SELECT COUNT(*) AS n FROM insumos WHERE ingrediente_id IS NULL;")
        restantes = cur.fetchone()['n']
        return {
            'emparejados': len(actualizados),
            'detalle': actualizados,
            'huerfanos_restantes': restantes,
            'heuristica_disponible': HEURISTICA_DISPONIBLE,
            'message': f"{len(actualizados)} insumo(s) emparejado(s); quedan {restantes} huérfano(s).",
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al re-emparejar insumos: {e}")
    finally:
        cur.close()


# ==========================================
# LEGACY COM-37 v1: PRECIOS MANUALES POR INGREDIENTE (fallback de resolución)
# Se conservan: precios_insumos.mejor_opcion_ingrediente los usa como última fuente.
# ==========================================
@router.get("/{ingrediente_id}/precios-manuales")
def listar_precios_manuales_legacy(ingrediente_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """LEGACY v1: períodos manuales por INGREDIENTE (tabla ingredientes_precios_manuales)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT pm.id, pm.ingrediente_id, pm.precio_por_unidad, pm.fecha_inicio, pm.fecha_fin,
                   pm.observacion, pm.estado_activo, pm.fecha_registro,
                   um.nombre AS unidad_nombre, um.abreviatura AS unidad_abrev,
                   u.nombres || ' ' || u.apellido_paterno AS creado_por_nombre
            FROM ingredientes_precios_manuales pm
            JOIN ingredientes i ON i.id = pm.ingrediente_id
            JOIN unidades_medida um ON um.id = i.unidad_medida_id
            LEFT JOIN usuarios u ON u.id = pm.creado_por
            WHERE pm.ingrediente_id = %s
            ORDER BY pm.fecha_registro DESC;
        """, (ingrediente_id,))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar precios manuales legacy: {e}")
    finally:
        cur.close()


@router.post("/{ingrediente_id}/precios-manuales", status_code=201)
def crear_precio_manual_legacy(ingrediente_id: int, data: CrearPrecioManualLegacyInput, db=Depends(get_db)):
    """LEGACY v1: precio manual en la unidad estándar del ingrediente (último fallback)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM ingredientes WHERE id = %s;", (ingrediente_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ingrediente no encontrado.")
        if data.precio_por_unidad <= 0:
            raise HTTPException(status_code=400, detail="El precio por unidad debe ser mayor a cero.")
        ini = fin = None
        if data.usar_rango:
            ini = _parse_fecha(data.fecha_inicio)
            fin = _parse_fecha(data.fecha_fin)
            if ini is None:
                raise HTTPException(status_code=400, detail="Con el rango activado, fecha_inicio es obligatoria.")
            if fin is not None and fin < ini:
                raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")
        cur.execute("""
            SELECT id, fecha_inicio, fecha_fin FROM ingredientes_precios_manuales
            WHERE ingrediente_id = %s AND estado_activo = TRUE;
        """, (ingrediente_id,))
        for p in cur.fetchall():
            if _solapan(ini, fin, p['fecha_inicio'], p['fecha_fin']):
                raise HTTPException(status_code=400,
                                detail=f"Solape con período activo id {p['id']}. Desactívelo primero.")
        cur.execute("""
            INSERT INTO ingredientes_precios_manuales
                (ingrediente_id, precio_por_unidad, fecha_inicio, fecha_fin, observacion, creado_por)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (ingrediente_id, data.precio_por_unidad, ini, fin,
              (data.observacion or '').strip() or None, data.usuario_solicitante_id))
        nuevo = cur.fetchone()
        db.commit()
        return {'id': nuevo['id'],
                'message': 'Precio manual legacy registrado (fallback de último recurso).'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el precio manual legacy: {e}")
    finally:
        cur.close()


@router.put("/precios-manuales-legacy/{periodo_id}/desactivar")
def desactivar_precio_manual_legacy(periodo_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """LEGACY v1: baja lógica de un período por ingrediente."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            UPDATE ingredientes_precios_manuales SET estado_activo = FALSE
            WHERE id = %s AND estado_activo = TRUE;
        """, (periodo_id,))
        if cur.rowcount != 1:
            raise HTTPException(status_code=404, detail="Período no encontrado o ya inactivo.")
        db.commit()
        return {'message': 'Período legacy desactivado.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al desactivar el período legacy: {e}")
    finally:
        cur.close()