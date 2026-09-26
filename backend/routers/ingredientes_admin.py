"""
routers/ingredientes_admin.py
Objetivo: COM-37: módulo "Gestión de Ingredientes" exclusivo del Administrador de
          Sistemas:
          - Listado de ingredientes con estado de emparejamiento (insumos ligados,
            insumos con precio, períodos manuales activos).
          - CRUD de ingredientes SIN BORRADO físico: crear y editar/renombrar (toda
            edición es responsabilidad del admin: el frontend muestra advertencia de
            inconsistencias históricas antes de confirmar).
          - Períodos de precio promedio manual por ingrediente, en la UNIDAD ESTÁNDAR
            del ingrediente, con rango de vigencia OPCIONAL (si usar_rango=False el
            precio rige siempre). Validación de solapes entre períodos activos.
          - Desactivación lógica de períodos (estado_activo=FALSE); nunca se eliminan.
          - Re-emparejado de insumos huérfanos (ingrediente_id NULL) usando el
            algoritmo de reconocimiento existente (scraper/classifiers/heuristics.py)
            más matching por nombre normalizado, para alimentar el reconocimiento
            tras crear/renombrar ingredientes.
Precedencia de precios (decisión COM-37): precio real del día > predicción Random
          Forest > precio manual vigente. Este router solo administra el manual; el
          fallback lo aplican optimizador.py / kmeans / greedy vía precios_manuales.py.
Permisos: todos los endpoints exigen es_admin_sistema (403 en caso contrario).
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: ticket COM-37 (solo trazabilidad).
"""
import unicodedata
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema

# COM-37: algoritmo de reconocimiento existente del scraper para re-emparejar insumos.
# Si el paquete no fuera importable en este contexto, el re-emparejado degrada a
# matching por nombre normalizado (no se rompe el endpoint).
try:
    from scraper.classifiers.heuristics import clasificar_heuristica_mejorada
    HEURISTICA_DISPONIBLE = True
except Exception:  # pragma: no cover - degradación controlada
    clasificar_heuristica_mejorada = None
    HEURISTICA_DISPONIBLE = False

router = APIRouter(prefix="/ingredientes-admin", tags=["Gestión de Ingredientes (COM-37)"])


# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class CrearIngredienteInput(BaseModel):
    usuario_solicitante_id: int
    nombre: str
    categoria_id: Optional[int] = None
    unidad_medida_id: int
    peso_estimado_g: float = 100.0


class EditarIngredienteInput(BaseModel):
    """COM-37: edición sin borrado. El frontend advierte que puede generar
    inconsistencias históricas (emparejamientos y costos pasados)."""
    usuario_solicitante_id: int
    nombre: Optional[str] = None
    categoria_id: Optional[int] = None
    unidad_medida_id: Optional[int] = None
    peso_estimado_g: Optional[float] = None


class CrearPrecioManualInput(BaseModel):
    usuario_solicitante_id: int
    precio_por_unidad: float
    usar_rango: bool = False            # False => vigencia permanente (fechas NULL)
    fecha_inicio: Optional[str] = None  # YYYY-MM-DD
    fecha_fin: Optional[str] = None     # YYYY-MM-DD o NULL (abierto)
    observacion: Optional[str] = None


class EditarPrecioManualInput(BaseModel):
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
    """Solape de intervalos con extremos abiertos (None = infinito)."""
    a_start = a_ini or date.min
    a_end = a_fin or date.max
    b_start = b_ini or date.min
    b_end = b_fin or date.max
    return a_start <= b_end and b_start <= a_end


def _periodos_activos(cur, ingrediente_id, excluir_id=None):
    cur.execute("""
        SELECT id, fecha_inicio, fecha_fin
        FROM ingredientes_precios_manuales
        WHERE ingrediente_id = %s AND estado_activo = TRUE
          AND (%s IS NULL OR id <> %s);
    """, (ingrediente_id, excluir_id, excluir_id))
    return cur.fetchall()


def _validar_sin_solapes(cur, ingrediente_id, ini, fin, excluir_id=None):
    for p in _periodos_activos(cur, ingrediente_id, excluir_id):
        if _solapan(ini, fin, p['fecha_inicio'], p['fecha_fin']):
            raise HTTPException(
                status_code=400,
                detail=f"El rango se solapa con un período activo existente "
                       f"(id {p['id']}: {p['fecha_inicio'] or 'siempre'} → {p['fecha_fin'] or 'abierto'}). "
                       f"Desactívelo antes de registrar este precio.")


def _mapa_categorias(cur):
    cur.execute("SELECT id, nombre FROM categorias_alimentos;")
    return {r['nombre']: r['id'] for r in cur.fetchall()}


# ==========================================
# LISTADO DE INGREDIENTES CON ESTADO DE EMPAREJAMIENTO
# ==========================================
@router.get("")
def listar_ingredientes(usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37: ingredientes + indicadores para decidir carga de precio manual."""
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
                     JOIN historial_precios hp ON hp.insumo_id = ins.id
                     WHERE ins.ingrediente_id = i.id) AS n_insumos_con_precio,
                   (SELECT COUNT(*) FROM ingredientes_precios_manuales pm
                     WHERE pm.ingrediente_id = i.id AND pm.estado_activo = TRUE) AS n_precios_manuales
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


# ==========================================
# CREACIÓN Y EDICIÓN DE INGREDIENTES (SIN BORRADO)
# ==========================================
@router.post("", status_code=201)
def crear_ingrediente(data: CrearIngredienteInput, db=Depends(get_db)):
    """COM-37: crea un ingrediente. Crear/renombrar alimenta al algoritmo de
    reconocimiento (heuristics + matching por nombre) en el siguiente re-emparejado."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        nombre = (data.nombre or '').strip()
        if len(nombre) < 2:
            raise HTTPException(status_code=400, detail="El nombre del ingrediente es obligatorio.")
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
                'message': 'Ingrediente creado. Use "Re-emparejar insumos" para vincular insumos huérfanos.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el ingrediente: {e}")
    finally:
        cur.close()


@router.put("/{ingrediente_id}")
def editar_ingrediente(ingrediente_id: int, data: EditarIngredienteInput, db=Depends(get_db)):
    """COM-37: edición/renombrado sin borrado físico. La advertencia de inconsistencias
    la muestra el frontend antes de confirmar (decisión de ticket)."""
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
            cur.execute("UPDATE ingredientes SET unidad_medida_id = %s WHERE id = %s;",
                        (data.unidad_medida_id, ingrediente_id))
        if data.peso_estimado_g is not None:
            if data.peso_estimado_g <= 0:
                raise HTTPException(status_code=400, detail="peso_estimado_g debe ser mayor a cero.")
            cur.execute("UPDATE ingredientes SET peso_estimado_g = %s WHERE id = %s;",
                        (data.peso_estimado_g, ingrediente_id))
        db.commit()
        return {'message': 'Ingrediente actualizado. Verifique emparejamientos y precios manuales vigentes.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al editar el ingrediente: {e}")
    finally:
        cur.close()


# ==========================================
# PERÍODOS DE PRECIO MANUAL CON VIGENCIA
# ==========================================
@router.get("/{ingrediente_id}/precios-manuales")
def listar_precios_manuales(ingrediente_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37: períodos del ingrediente (activos e inactivos), más recientes primero."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT pm.id, pm.ingrediente_id, pm.precio_por_unidad, pm.fecha_inicio,
                   pm.fecha_fin, pm.observacion, pm.estado_activo, pm.fecha_registro,
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
        raise HTTPException(status_code=500, detail=f"Error al listar precios manuales: {e}")
    finally:
        cur.close()


@router.post("/{ingrediente_id}/precios-manuales", status_code=201)
def crear_precio_manual(ingrediente_id: int, data: CrearPrecioManualInput, db=Depends(get_db)):
    """COM-37: registra un precio promedio manual en la unidad estándar del ingrediente."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("SELECT id FROM ingredientes WHERE id = %s;", (ingrediente_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ingrediente no encontrado.")
        if data.precio_por_unidad is None or data.precio_por_unidad <= 0:
            raise HTTPException(status_code=400, detail="El precio por unidad debe ser mayor a cero.")
        ini = fin = None
        if data.usar_rango:
            ini = _parse_fecha(data.fecha_inicio)
            fin = _parse_fecha(data.fecha_fin)
            if ini is None:
                raise HTTPException(status_code=400,
                                detail="Con el rango activado, fecha_inicio es obligatoria.")
            if fin is not None and fin < ini:
                raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")
        _validar_sin_solapes(cur, ingrediente_id, ini, fin)
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
                'message': 'Precio manual registrado. Se usará solo cuando el scraper/RF no puedan predecir.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear el precio manual: {e}")
    finally:
        cur.close()


@router.put("/precios-manuales/{periodo_id}")
def editar_precio_manual(periodo_id: int, data: EditarPrecioManualInput, db=Depends(get_db)):
    """COM-37: edita un período (precio, rango, observación) con re-validación de solapes."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("""
            SELECT id, ingrediente_id, precio_por_unidad, fecha_inicio, fecha_fin, observacion
            FROM ingredientes_precios_manuales WHERE id = %s;
        """, (periodo_id,))
        periodo = cur.fetchone()
        if not periodo:
            raise HTTPException(status_code=404, detail="Período de precio manual no encontrado.")

        precio = data.precio_por_unidad if data.precio_por_unidad is not None else float(periodo['precio_por_unidad'])
        if precio <= 0:
            raise HTTPException(status_code=400, detail="El precio por unidad debe ser mayor a cero.")

        usar_rango = data.usar_rango if data.usar_rango is not None else (periodo['fecha_inicio'] is not None)
        if usar_rango:
            ini = _parse_fecha(data.fecha_inicio) if data.fecha_inicio is not None else periodo['fecha_inicio']
            fin = _parse_fecha(data.fecha_fin) if data.fecha_fin is not None else periodo['fecha_fin']
            if ini is None:
                raise HTTPException(status_code=400,
                                detail="Con el rango activado, fecha_inicio es obligatoria.")
            if fin is not None and fin < ini:
                raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")
        else:
            ini = fin = None
        _validar_sin_solapes(cur, periodo['ingrediente_id'], ini, fin, excluir_id=periodo_id)

        observacion = data.observacion if data.observacion is not None else periodo['observacion']
        cur.execute("""
            UPDATE ingredientes_precios_manuales
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
def desactivar_precio_manual(periodo_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-37: baja lógica del período (no se elimina: preserva trazabilidad)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            UPDATE ingredientes_precios_manuales
            SET estado_activo = FALSE
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
# RE-EMPAREJADO DE INSUMOS HUÉRFANOS
# ==========================================
@router.post("/reemparejar-insumos")
def reemparejar_insumos(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-37: vincula insumos con ingrediente_id NULL usando el algoritmo de reconocimiento
    existente (heuristics.clasificar_heuristica_mejorada) y matching por nombre
    normalizado contra el catálogo vigente de ingredientes. Permite que crear/renombrar
    ingredientes desde esta pestaña alimente al algoritmo sin reiniciar el scraper.
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
                    generico, _cat_id, _cat_nom = clasificar_heuristica_mejorada(ins['nombre'], mapa_cat)
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
                actualizados.append({
                    'insumo_id': ins['id'],
                    'insumo': ins['nombre'],
                    'ingrediente_id': candidato,
                })

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