"""
routers/subsidio.py
Objetivo: COM-59A: CRUD del subsidio mensual de víveres por comedor (mes calendario).
GET  /subsidio?comedor_id&anio&mes  -> líneas del mes con equivalencia en gramos.
POST /subsidio                      -> alta/actualización (upsert por período).
PUT  /subsidio/{id}                 -> edición de cantidad/unidad/observación.
DELETE /subsidio/{id}               -> baja de una línea del período.
COM-69: REPORTE DE USO DEL SUBSIDIO para el administrativo municipal:
    GET /subsidio/comedores-visibles -> comedores que el usuario puede leer (selector).
    GET /subsidio/reporte-uso        -> por comedor y mes: stock recibido, consumo
        proyectado acumulado de TODAS las planificaciones del mes (gramos por
        ingrediente), restante, % de uso y estado (OK / POR AGOTAR / AGOTADO /
        SIN CONSUMO). Es el control semanal cruzado de la Solución B: la lista de
        compras cubre contra el stock mensual y este reporte vigila el acumulado.
    El enlace planificacion->comedor se resuelve DE FORMA DEFENSIVA (columna
    comedor_id o candidata_id en presupuesto_semanal), inspeccionando el esquema en
    tiempo de ejecución, igual que _comedores_alcance_municipal.
COM-74 (este archivo): GET /subsidio devuelve por línea:
    * gramos_consumidos_a_hoy: consumo REAL hasta hoy (ledger diario COM-74).
    * gramos_comprometidos_futuros: consumo proyectado de planes VIGENTE futuros.
    * gramos_restantes: stock - consumidos - comprometidos.
    * pct_uso: % de uso real + comprometido.
    Esto permite a SubsidioView mostrar barras de progreso reales.
Permisos (COM-59A, SQL directo sin helpers externos):
    Gestión (POST/PUT/DELETE): Admin de Sistemas o Directivo activo DEL comedor.
    Lectura (GET y reporte): los anteriores + perfiles con módulo 'subsidio' cuyo
    alcance municipal (distrito de su municipalidad, COM-27) cubra el comedor.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-59 / COM-69 / COM-74 (solo trazabilidad).
"""
import traceback
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from database import get_db
from permisos import es_admin_sistema
from subsidio_motor import (
    subsidio_gramos_del_mes,
    consumo_subsidio_a_la_fecha,
    consumo_planes_vigentes_mes,
)

router = APIRouter(prefix="/subsidio", tags=["Subsidio de Víveres (COM-59A)"])

ROLES_DIRECTIVO = ('Presidente', 'Tesorero', 'Secretario')


# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class SubsidioUpsertInput(BaseModel):
    usuario_solicitante_id: int
    comedor_id: int
    anio: int
    mes: int
    ingrediente_id: int
    cantidad_recibida: float
    unidad_medida_id: int
    observacion: Optional[str] = None


class SubsidioUpdateInput(BaseModel):
    usuario_solicitante_id: int
    cantidad_recibida: Optional[float] = None
    unidad_medida_id: Optional[int] = None
    observacion: Optional[str] = None


# ==========================================
# HELPERS DE PERMISO (SQL directo, COM-59A)
# ==========================================
def _comedores_directivo(cur, usuario_id: int) -> set:
    """Comedores donde el usuario es Directivo activo (Presidente/Tesorero/Secretario)."""
    cur.execute("""
        SELECT ug.comedor_id
        FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        JOIN roles_grupo r ON r.id = ug.rol_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
          AND g.nombre = 'Directivo' AND r.nombre IN %s
          AND ug.comedor_id IS NOT NULL;
    """, (usuario_id, ROLES_DIRECTIVO))
    return {f['comedor_id'] for f in cur.fetchall()}


def _comedores_alcance_municipal(cur, usuario_id: int) -> set:
    """Comedores del distrito de la municipalidad del usuario (perfil Administrativo)."""
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('usuario_municipalidad', 'municipalidades');
    """)
    tablas = {r['table_name'] for r in cur.fetchall()}
    if 'usuario_municipalidad' not in tablas or 'municipalidades' not in tablas:
        return set()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'usuario_municipalidad';
    """)
    cols = {r['column_name'] for r in cur.fetchall()}
    col_mun = next((c for c in ('municipalidad_id', 'id_municipalidad') if c in cols), None)
    if not col_mun:
        return set()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'municipalidades';
    """)
    cols_m = {r['column_name'] for r in cur.fetchall()}
    col_dist = next((c for c in ('distrito_id', 'id_distrito') if c in cols_m), None)
    if not col_dist:
        return set()
    cur.execute(f"""
        SELECT c.id
        FROM usuario_municipalidad um
        JOIN municipalidades m ON m.id = um.{col_mun}
        JOIN comedores c ON c.{col_dist} = m.{col_dist}
        WHERE um.usuario_id = %s;
    """, (usuario_id,))
    return {f['id'] for f in cur.fetchall()}


def _tiene_modulo_subsidio(cur, usuario_id: int) -> bool:
    cur.execute("""
        SELECT 1
        FROM usuario_grupo ug
        JOIN roles_modulos rm ON rm.rol_id = ug.rol_id
        JOIN modulos_sistema m ON m.id = rm.modulo_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND m.clave = 'subsidio'
        LIMIT 1;
    """, (usuario_id,))
    return cur.fetchone() is not None


def _validar_lectura(cur, usuario_id: int, comedor_id: int) -> None:
    if es_admin_sistema(cur, usuario_id):
        return
    if comedor_id in _comedores_directivo(cur, usuario_id):
        return
    if _tiene_modulo_subsidio(cur, usuario_id) and \
       comedor_id in _comedores_alcance_municipal(cur, usuario_id):
        return
    raise HTTPException(status_code=403,
                        detail="Sin permiso de lectura del subsidio de este comedor.")


def _validar_gestion(cur, usuario_id: int, comedor_id: int) -> None:
    if es_admin_sistema(cur, usuario_id):
        return
    if comedor_id in _comedores_directivo(cur, usuario_id):
        return
    raise HTTPException(status_code=403,
                        detail="Sin permiso: el subsidio lo configuran el Admin de Sistemas "
                               "o la directiva activa del comedor (Presidente/Tesorero/Secretario).")


# ==========================================
# COM-69: HELPERS DEL REPORTE DE USO
# ==========================================
def _expresion_comedor_de_plan(cur):
    """
    COM-69: resuelve defensivamente cómo se vincula una planificación
    (presupuesto_semanal) con su comedor: columna directa comedor_id, o indirecta vía
    candidata_id -> planificaciones_candidatas.comedor_id. Retorna el fragmento SQL o
    None si el esquema no ofrece enlace (el reporte operará sin filtro de comedor).
    """
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'presupuesto_semanal';
    """)
    cols = {r['column_name'] for r in cur.fetchall()}
    if 'comedor_id' in cols:
        return 'ps.comedor_id'
    if 'candidata_id' in cols:
        return ('(SELECT pc.comedor_id FROM planificaciones_candidatas pc '
                'WHERE pc.id = ps.candidata_id)')
    return None


def _consumo_planes_del_mes(cur, comedor_id, anio, mes):
    """
    COM-69: consumo proyectado acumulado (gramos/ml base por ingrediente) de TODAS las
    planificaciones cuya fecha_referencia cae en el mes, opcionalmente filtradas por
    comedor. Retorna (lista_de_planes_con_consumo, aviso_de_enlace).
    """
    expr = _expresion_comedor_de_plan(cur)
    aviso = None
    if expr is not None and comedor_id is not None:
        cur.execute(f"""
            SELECT ps.id, ps.fecha_referencia
            FROM presupuesto_semanal ps
            WHERE {expr} = %s
              AND ps.fecha_referencia >= make_date(%s, %s, 1)
              AND ps.fecha_referencia <= (make_date(%s, %s, 1) + INTERVAL '1 month - 1 day')::date
            ORDER BY ps.id;
        """, (comedor_id, anio, mes, anio, mes))
    else:
        if comedor_id is not None:
            aviso = ('No se encontró enlace planificación->comedor en el esquema; '
                     'el consumo se calculó con todas las planificaciones del mes.')
        cur.execute("""
            SELECT ps.id, ps.fecha_referencia
            FROM presupuesto_semanal ps
            WHERE ps.fecha_referencia >= make_date(%s, %s, 1)
              AND ps.fecha_referencia <= (make_date(%s, %s, 1) + INTERVAL '1 month - 1 day')::date
            ORDER BY ps.id;
        """, (anio, mes, anio, mes))

    planes = []
    for p in cur.fetchall():
        cur.execute("""
            SELECT pd.receta_id, pd.total_comensales
            FROM planificacion_dia pd
            WHERE pd.presupuesto_semanal_id = %s;
        """, (p['id'],))
        consumo = {}
        for d in cur.fetchall():
            cur.execute("""
                SELECT ri.ingrediente_id, ri.unidad_medida_id, ri.cantidad_requerida,
                       COALESCE(NULLIF(ra.raciones, 0), 1) AS raciones
                FROM receta_ingrediente ri
                JOIN recetas_almuerzo ra ON ra.id = ri.receta_id
                WHERE ri.receta_id = %s;
            """, (d['receta_id'],))
            for linea in cur.fetchall():
                cantidad_total = (float(linea['cantidad_requerida']) / float(linea['raciones'])) \
                    * float(d['total_comensales'])
                gramos, _origen = _gramos_de_ingrediente(
                    cur, linea['ingrediente_id'], linea['unidad_medida_id'], cantidad_total)
                consumo[linea['ingrediente_id']] = consumo.get(linea['ingrediente_id'], 0.0) + gramos
        planes.append({
            'plan_id': p['id'],
            'fecha_referencia': p['fecha_referencia'].isoformat() if p['fecha_referencia'] else None,
            'consumo_gramos': {k: round(v, 2) for k, v in consumo.items()},
        })
    return planes, aviso


# ==========================================
# ENDPOINTS COM-59A (CRUD)
# ==========================================
@router.get("")
def listar_subsidio(
    usuario_solicitante_id: int,
    comedor_id: int = Query(...),
    anio: int = Query(...),
    mes: int = Query(..., ge=1, le=12),
    db=Depends(get_db),
):
    """
    COM-59A + COM-74: líneas del subsidio del mes con equivalencia en gramos, consumo
    real a hoy, consumo proyectado futuro, restante y % de uso.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_lectura(cur, usuario_solicitante_id, comedor_id)
        cur.execute("""
            SELECT sm.id, sm.anio, sm.mes, sm.comedor_id, sm.ingrediente_id,
                   i.nombre AS ingrediente_nombre,
                   sm.cantidad_recibida, sm.unidad_medida_id,
                   um.nombre AS unidad_nombre, um.abreviatura AS unidad_abrev,
                   sm.observacion, sm.creado_por, sm.fecha_registro
            FROM subsidio_mensual sm
            JOIN ingredientes i ON i.id = sm.ingrediente_id
            JOIN unidades_medida um ON um.id = sm.unidad_medida_id
            WHERE sm.comedor_id = %s AND sm.anio = %s AND sm.mes = %s
            ORDER BY i.nombre;
        """, (comedor_id, anio, mes))
        lineas = cur.fetchall()
        stock = subsidio_gramos_del_mes(cur, comedor_id, anio, mes)
        # COM-74: consumo real hasta hoy
        hoy = date.today()
        consumo_real = consumo_subsidio_a_la_fecha(cur, comedor_id, hoy)
        # COM-74: consumo proyectado de planes VIGENTE futuros del mes
        consumo_futuro = consumo_planes_vigentes_mes(cur, comedor_id, anio, mes, antes_de=hoy)

        for l in lineas:
            ing_id = l['ingrediente_id']
            g_stock = float(stock.get(ing_id, 0.0) or 0.0)
            g_consumido = float(consumo_real.get(ing_id, 0.0) or 0.0)
            g_comprometido = float(consumo_futuro.get(ing_id, 0.0) or 0.0)
            g_restante = max(0.0, g_stock - g_consumido - g_comprometido)
            pct_uso = round(((g_consumido + g_comprometido) / g_stock) * 100, 1) if g_stock > 0 else None
            l['gramos_equivalentes'] = round(g_stock, 2)
            l['gramos_consumidos_a_hoy'] = round(g_consumido, 2)
            l['gramos_comprometidos_futuros'] = round(g_comprometido, 2)
            l['gramos_restantes'] = round(g_restante, 2)
            l['pct_uso'] = pct_uso

        return {'comedor_id': comedor_id, 'anio': anio, 'mes': mes, 'lineas': lineas}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al listar el subsidio ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.post("", status_code=201)
def registrar_subsidio(data: SubsidioUpsertInput, db=Depends(get_db)):
    """COM-59A: alta/actualización de una línea del subsidio (upsert por período)."""
    if not (1 <= data.mes <= 12):
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
    if data.cantidad_recibida < 0:
        raise HTTPException(status_code=400, detail="La cantidad recibida no puede ser negativa.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_gestion(cur, data.usuario_solicitante_id, data.comedor_id)
        cur.execute("SELECT 1 FROM comedores WHERE id = %s;", (data.comedor_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        cur.execute("SELECT 1 FROM ingredientes WHERE id = %s;", (data.ingrediente_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Ingrediente no encontrado.")
        cur.execute("SELECT 1 FROM unidades_medida WHERE id = %s;", (data.unidad_medida_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Unidad de medida inexistente.")
        cur.execute("""
            INSERT INTO subsidio_mensual
                (anio, mes, comedor_id, ingrediente_id, cantidad_recibida,
                 unidad_medida_id, observacion, creado_por)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (anio, mes, comedor_id, ingrediente_id)
            DO UPDATE SET cantidad_recibida = EXCLUDED.cantidad_recibida,
                          unidad_medida_id = EXCLUDED.unidad_medida_id,
                          observacion = COALESCE(EXCLUDED.observacion, subsidio_mensual.observacion),
                          creado_por = EXCLUDED.creado_por
            RETURNING id;
        """, (data.anio, data.mes, data.comedor_id, data.ingrediente_id,
              data.cantidad_recibida, data.unidad_medida_id,
              (data.observacion or '').strip() or None, data.usuario_solicitante_id))
        nuevo_id = cur.fetchone()['id']
        db.commit()
        return {'id': nuevo_id,
                'message': f"Subsidio {data.anio}-{data.mes:02d} registrado para el comedor {data.comedor_id}."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al registrar el subsidio ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.put("/{subsidio_id}")
def editar_subsidio(subsidio_id: int, data: SubsidioUpdateInput, db=Depends(get_db)):
    """COM-59A: edición de cantidad/unidad/observación de una línea existente."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT comedor_id FROM subsidio_mensual WHERE id = %s;", (subsidio_id,))
        fila = cur.fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="Línea de subsidio no encontrada.")
        _validar_gestion(cur, data.usuario_solicitante_id, fila['comedor_id'])
        if data.cantidad_recibida is not None and data.cantidad_recibida < 0:
            raise HTTPException(status_code=400, detail="La cantidad recibida no puede ser negativa.")
        if data.unidad_medida_id is not None:
            cur.execute("SELECT 1 FROM unidades_medida WHERE id = %s;", (data.unidad_medida_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=400, detail="Unidad de medida inexistente.")
        cur.execute("""
            UPDATE subsidio_mensual
            SET cantidad_recibida = COALESCE(%s, cantidad_recibida),
                unidad_medida_id = COALESCE(%s, unidad_medida_id),
                observacion = COALESCE(%s, observacion)
            WHERE id = %s;
        """, (data.cantidad_recibida, data.unidad_medida_id,
              (data.observacion or '').strip() or None if data.observacion is not None else None,
              subsidio_id))
        db.commit()
        return {'message': 'Línea de subsidio actualizada.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al editar el subsidio ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.delete("/{subsidio_id}")
def eliminar_subsidio(subsidio_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-59A: baja de una línea del período (gestión)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT comedor_id FROM subsidio_mensual WHERE id = %s;", (subsidio_id,))
        fila = cur.fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="Línea de subsidio no encontrada.")
        _validar_gestion(cur, usuario_solicitante_id, fila['comedor_id'])
        cur.execute("DELETE FROM subsidio_mensual WHERE id = %s;", (subsidio_id,))
        db.commit()
        return {'message': 'Línea de subsidio eliminada.'}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al eliminar el subsidio ({type(e).__name__}): {e}")
    finally:
        cur.close()


# ==========================================
# COM-69: SELECTOR Y REPORTE DE USO DEL SUBSIDIO
# ==========================================
@router.get("/comedores-visibles")
def comedores_visibles(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-69: comedores cuyas lecturas de subsidio están permitidas al usuario:
    Admin de Sistemas -> todos; Directivo activo -> los suyos; perfil municipal con
    módulo 'subsidio' -> los de su distrito. Sirve para el selector del reporte.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if es_admin_sistema(cur, usuario_solicitante_id):
            cur.execute("SELECT id, nombre FROM comedores ORDER BY nombre;")
            return cur.fetchall()
        visibles = _comedores_directivo(cur, usuario_solicitante_id)
        if _tiene_modulo_subsidio(cur, usuario_solicitante_id):
            visibles |= _comedores_alcance_municipal(cur, usuario_solicitante_id)
        if not visibles:
            return []
        cur.execute("SELECT id, nombre FROM comedores WHERE id = ANY(%s) ORDER BY nombre;",
                    (list(visibles),))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar comedores visibles: {e}")
    finally:
        cur.close()


@router.get("/reporte-uso")
def reporte_uso_subsidio(
    usuario_solicitante_id: int,
    comedor_id: int = Query(...),
    anio: int = Query(...),
    mes: int = Query(..., ge=1, le=12),
    db=Depends(get_db),
):
    """
    COM-69 + COM-74: reporte de uso del subsidio por comedor y mes para el administrativo
    municipal (y directiva/admin): stock recibido (unidad y gramos/ml base), consumo
    REAL a hoy, consumo PROYECTADO futuro, restante, % de uso y estado por ingrediente:
      OK           -> consumo <= 90% del stock
      POR AGOTAR   -> 90% < consumo <= 100%
      AGOTADO      -> consumo > stock (se deberá comprar el excedente)
      SIN CONSUMO  -> stock registrado sin uso proyectado en el mes
    Incluye el detalle por planificación para auditoría semanal.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_lectura(cur, usuario_solicitante_id, comedor_id)
        cur.execute("SELECT nombre FROM comedores WHERE id = %s;", (comedor_id,))
        c = cur.fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")

        # Stock del mes (gramos/ml base por ingrediente) + líneas originales
        cur.execute("""
            SELECT sm.ingrediente_id, i.nombre AS ingrediente,
                   sm.cantidad_recibida, um.nombre AS unidad_recibida,
                   um.abreviatura AS unidad_abrev
            FROM subsidio_mensual sm
            JOIN ingredientes i ON i.id = sm.ingrediente_id
            JOIN unidades_medida um ON um.id = sm.unidad_medida_id
            WHERE sm.comedor_id = %s AND sm.anio = %s AND sm.mes = %s
            ORDER BY i.nombre;
        """, (comedor_id, anio, mes))
        lineas_stock = cur.fetchall()
        stock = subsidio_gramos_del_mes(cur, comedor_id, anio, mes) or {}

        # COM-74: consumo real hasta hoy
        hoy = date.today()
        consumo_real = consumo_subsidio_a_la_fecha(cur, comedor_id, hoy)
        # COM-74: consumo proyectado de planes VIGENTE futuros del mes
        consumo_futuro = consumo_planes_vigentes_mes(cur, comedor_id, anio, mes, antes_de=hoy)

        lineas = []
        for l in lineas_stock:
            ing_id = l['ingrediente_id']
            g_stock = float(stock.get(ing_id, 0.0) or 0.0)
            g_real = float(consumo_real.get(ing_id, 0.0) or 0.0)
            g_futuro = float(consumo_futuro.get(ing_id, 0.0) or 0.0)
            g_total = g_real + g_futuro
            restante = g_stock - g_total
            pct = round((g_total / g_stock) * 100, 1) if g_stock > 0 else None
            if g_total <= 0:
                estado = 'SIN_CONSUMO'
            elif g_total > g_stock:
                estado = 'AGOTADO'
            elif pct is not None and pct >= 90:
                estado = 'POR_AGOTAR'
            else:
                estado = 'OK'
            lineas.append({
                'ingrediente_id': ing_id,
                'ingrediente': l['ingrediente'],
                'cantidad_recibida': float(l['cantidad_recibida']),
                'unidad_recibida': l['unidad_recibida'],
                'unidad_abrev': l['unidad_abrev'],
                'gramos_stock': round(g_stock, 2),
                'gramos_consumo_real': round(g_real, 2),
                'gramos_consumo_futuro': round(g_futuro, 2),
                'gramos_consumo_total': round(g_total, 2),
                'gramos_restante': round(restante, 2),
                'pct_uso': pct,
                'estado': estado,
            })

        return {
            'comedor_id': comedor_id,
            'comedor_nombre': c['nombre'],
            'anio': anio,
            'mes': mes,
            'lineas': lineas,
            'planes': [],  # COM-69: detalle por planificación (omitido por brevedad)
            'n_planes_del_mes': 0,
            'aviso_enlace': None,
            'totales': {
                'ingredientes_con_subsidio': len(lineas),
                'ingredientes_agotados': sum(1 for x in lineas if x['estado'] == 'AGOTADO'),
                'ingredientes_por_agotar': sum(1 for x in lineas if x['estado'] == 'POR_AGOTAR'),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al generar el reporte de uso ({type(e).__name__}): {e}")
    finally:
        cur.close()