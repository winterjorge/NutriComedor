"""
routers/propuestas_menu.py
Objetivo: Endpoints del flujo COM-8 "Mostrar 3 propuestas de menú semanal":
          - POST /propuestas/generar: ejecuta el motor greedy con los DÍAS DE COCINA
            seleccionados (COM-8 v2) y persiste las 3 candidatas.
          - GET  /propuestas/sesion/{sesion_id}: recupera las 3 tarjetas de una sesión.
          - POST /propuestas/{candidata_id}/seleccionar: fija el menú definitivo en
            presupuesto_semanal + planificacion_dia (solo Directivo).
          - GET  /propuestas/historial y /historial/{id}/dias: historial y detalle.
Historial:
 - COM-8 v1: generación de semana completa (7 días).
 - COM-8 v2: parámetro dias_semana en /generar (por defecto Lun-Vie) para excluir
   feriados o incluir sábados según la operativa real del comedor.
Permisos (regla del ticket):
          - Generar/ver: Directivo u Operativo del comedor (admin de sistemas por soporte).
          - Seleccionar o cambiar el menú: SOLO Directivo del comedor.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: ticket COM-8 / HU-08 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import (
    es_admin_sistema,
    es_directivo_de_comedor,
    es_operativo_de_comedor,
)
from ml.greedy_search import (
    generar_tres_propuestas,
    obtener_candidatas_sesion,
    obtener_candidata,
)

router = APIRouter(prefix="/propuestas", tags=["Propuestas de Menú"])

# Límite superior del presupuesto semanal (coherente con HU-02: S/ 10,000)
PRESUPUESTO_MAXIMO = 10000.0


# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class GenerarPropuestasInput(BaseModel):
    """Parámetros de generación de las 3 propuestas semanales."""
    comedor_id: int
    presupuesto_semanal: float
    fecha_referencia: Optional[str] = None   # YYYY-MM-DD; por defecto hoy
    seed: int = 0                            # jitter del botón "Regenerar"
    # COM-8 v2: días de cocina (1=Lunes .. 7=Domingo). Por defecto Lun-Vie.
    dias_semana: Optional[List[int]] = None
    usuario_solicitante_id: int


class SeleccionarPropuestaInput(BaseModel):
    """Usuario que fija el menú definitivo (debe ser Directivo del comedor)."""
    usuario_solicitante_id: int


# ==========================================
# HELPERS DE PERMISO Y CONTEXTO
# ==========================================
def _validar_puede_generar(cur, usuario_id: int, comedor_id: int) -> None:
    """Directivo u Operativo del comedor (vista COM-8); admin de sistemas por soporte."""
    if es_admin_sistema(cur, usuario_id):
        return
    if es_directivo_de_comedor(cur, usuario_id, comedor_id):
        return
    if es_operativo_de_comedor(cur, usuario_id, comedor_id):
        return
    raise HTTPException(
        status_code=403,
        detail="Sin permiso: la generación de propuestas es para el personal "
               "directivo y operativo del comedor.")


def _validar_puede_seleccionar(cur, usuario_id: int, comedor_id: int) -> None:
    """Regla del ticket: solo el personal Directivo fija o cambia el menú semanal."""
    if es_directivo_de_comedor(cur, usuario_id, comedor_id):
        return
    raise HTTPException(
        status_code=403,
        detail="Sin permiso: solo el personal directivo del comedor puede "
               "seleccionar o cambiar el menú semanal.")


def _comensales_por_tipo(cur):
    """Comensales proyectados por tipo desde parametros_sistema (seed COM-8)."""
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('PLANIFICACION_COMENSALES_SOCIAL',
                        'PLANIFICACION_COMENSALES_AFILIADO',
                        'PLANIFICACION_COMENSALES_NORMAL');
    """)
    p = {r['clave']: int(float(r['valor'])) for r in cur.fetchall()}
    social = p.get('PLANIFICACION_COMENSALES_SOCIAL', 22)
    afiliado = p.get('PLANIFICACION_COMENSALES_AFILIADO', 48)
    normal = p.get('PLANIFICACION_COMENSALES_NORMAL', 50)
    return social, afiliado, normal


def _lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


# ==========================================
# GENERACIÓN DE LAS 3 PROPUESTAS
# ==========================================
@router.post("/generar", status_code=201)
def generar_propuestas(data: GenerarPropuestasInput, db=Depends(get_db)):
    """
    Ejecuta el motor greedy para los días de cocina indicados y persiste las 3
    propuestas candidatas agrupadas por sesion_id. El botón "Regenerar" del frontend
    re-llama este endpoint con otro `seed`.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_puede_generar(cur, data.usuario_solicitante_id, data.comedor_id)

        if data.presupuesto_semanal is None or data.presupuesto_semanal <= 0:
            raise HTTPException(status_code=400, detail="El presupuesto no puede ser negativo.")
        if data.presupuesto_semanal > PRESUPUESTO_MAXIMO:
            raise HTTPException(status_code=400,
                            detail="El presupuesto no puede superar los 10,000 soles.")

        # COM-8 v2: validación de días de cocina
        dias = sorted(set(data.dias_semana or [1, 2, 3, 4, 5]))
        if not dias or any(d < 1 or d > 7 for d in dias):
            raise HTTPException(status_code=400,
                            detail="Los días de cocina deben estar entre 1 (Lunes) y 7 (Domingo).")

        fecha = date.fromisoformat(data.fecha_referencia) if data.fecha_referencia else date.today()

        # Limpieza de candidatas PENDIENTE antiguas (>7 días) para no acumular sesiones
        cur.execute("""
            DELETE FROM planificaciones_candidatas
            WHERE estado = 'PENDIENTE'
              AND fecha < CURRENT_TIMESTAMP - INTERVAL '7 days';
        """)

        resultado = generar_tres_propuestas(
            cur,
            comedor_id=data.comedor_id,
            presupuesto_semanal=data.presupuesto_semanal,
            creado_por_id=data.usuario_solicitante_id,
            fecha_referencia=fecha,
            seed=data.seed,
            dias_semana=dias,
        )
        # Flag para que la UI muestre/oculte el botón "Seleccionar esta opción"
        resultado['puede_seleccionar'] = es_directivo_de_comedor(
            cur, data.usuario_solicitante_id, data.comedor_id)

        db.commit()
        return resultado
    except HTTPException:
        raise
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al generar propuestas: {e}")
    finally:
        cur.close()


# ==========================================
# RECUPERACIÓN DE UNA SESIÓN (las 3 tarjetas)
# ==========================================
@router.get("/sesion/{sesion_id}")
def obtener_sesion(sesion_id: str, usuario_solicitante_id: int, db=Depends(get_db)):
    """Devuelve las 3 propuestas persistidas de una sesión de generación."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        filas = obtener_candidatas_sesion(cur, sesion_id)
        if not filas:
            raise HTTPException(status_code=404, detail="Sesión de propuestas no encontrada.")
        _validar_puede_generar(cur, usuario_solicitante_id, filas[0]['comedor_id'])
        return {
            'sesion_id': sesion_id,
            'comedor_id': filas[0]['comedor_id'],
            'puede_seleccionar': es_directivo_de_comedor(
                cur, usuario_solicitante_id, filas[0]['comedor_id']),
            'propuestas': [
                {
                    'candidata_id': f['id'],
                    'variante': f['variante'],
                    'etiqueta': f['etiqueta'],
                    'descripcion': f['descripcion'],
                    'ponderacion': f['ponderacion'],
                    'resumen': f['resumen'],
                    'menu': f['menu'],
                    'estado': f['estado'],
                } for f in filas
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la sesión: {e}")
    finally:
        cur.close()


# ==========================================
# SELECCIÓN DEL MENÚ DEFINITIVO (solo Directivo)
# ==========================================
@router.post("/{candidata_id}/seleccionar")
def seleccionar_propuesta(candidata_id: int, data: SeleccionarPropuestaInput,
                          db=Depends(get_db)):
    """
    Fija la propuesta como menú definitivo: escribe el maestro presupuesto_semanal
    y una fila en planificacion_dia POR CADA DÍA DE COCINA (COM-8 v2: solo los días
    seleccionados). Marca la candidata como SELECCIONADA y sus hermanas DESCARTADAS.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cand = obtener_candidata(cur, candidata_id)
        if not cand:
            raise HTTPException(status_code=404, detail="La propuesta seleccionada no existe.")
        if cand['estado'] == 'SELECCIONADA':
            raise HTTPException(status_code=400, detail="Esta propuesta ya fue seleccionada.")

        comedor_id = cand['comedor_id']
        _validar_puede_seleccionar(cur, data.usuario_solicitante_id, comedor_id)

        menu = cand['menu'] if isinstance(cand['menu'], list) else cand['menu']
        resumen = cand['resumen'] if isinstance(cand['resumen'], dict) else cand['resumen']
        if not menu:
            raise HTTPException(status_code=400, detail="La propuesta no tiene menú cargado.")

        fecha_inicio = _lunes_de(date.fromisoformat(menu[0]['fecha']))
        social, afiliado, normal = _comensales_por_tipo(cur)
        total_comensales = social + afiliado + normal

        # Planificación VIGENTE previa de la misma semana pasa a REEMPLAZADA
        cur.execute("""
            UPDATE presupuesto_semanal
            SET estado = 'REEMPLAZADA'
            WHERE comedor_id = %s AND fecha_referencia = %s AND estado = 'VIGENTE'
            RETURNING candidata_id;
        """, (comedor_id, fecha_inicio))
        for fila in cur.fetchall():
            if fila['candidata_id']:
                cur.execute("""
                    UPDATE planificaciones_candidatas
                    SET estado = 'REEMPLAZADA'
                    WHERE id = %s AND estado = 'SELECCIONADA';
                """, (fila['candidata_id'],))

        # Maestro de planificación semanal
        cur.execute("""
            INSERT INTO presupuesto_semanal
                (fondo_total, dias_operativos, fecha_referencia,
                 costo_total_semana, recoleccion_total_proyectada, margen, viable,
                 comedor_id, candidata_id, seleccionado_por_id, fecha_seleccion, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    CURRENT_TIMESTAMP - INTERVAL '5 hours', 'VIGENTE')
            RETURNING id;
        """, (
            resumen.get('presupuesto_semanal', 0),
            resumen.get('n_dias', len(menu)),
            fecha_inicio,
            resumen.get('costo_total_semana'),
            resumen.get('recoleccion_total_semana'),
            resumen.get('margen_proyectado'),
            bool(resumen.get('dentro_de_presupuesto', True)),
            comedor_id,
            candidata_id,
            data.usuario_solicitante_id,
        ))
        presupuesto_id = cur.fetchone()['id']

        # Detalle diario (solo los días de cocina seleccionados)
        for dia in menu:
            cur.execute("""
                INSERT INTO planificacion_dia
                    (presupuesto_semanal_id, dia, dia_nombre,
                     comensales_social, comensales_afiliado, comensales_normal,
                     total_comensales, receta_id, nombre_receta,
                     costo_racion, costo_total, recoleccion_proyectada)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                presupuesto_id,
                dia['dia_semana'],
                dia['dia_nombre'],
                social, afiliado, normal, total_comensales,
                dia['receta_id'],
                dia['receta_nombre'],
                dia['costo_racion'],
                dia['costo_total_dia'],
                dia['recoleccion_proyectada'],
            ))

        # Estados de las candidatas de la sesión
        cur.execute("""
            UPDATE planificaciones_candidatas SET estado = 'SELECCIONADA'
            WHERE id = %s;
        """, (candidata_id,))
        cur.execute("""
            UPDATE planificaciones_candidatas SET estado = 'DESCARTADA'
            WHERE sesion_id = %s AND id <> %s AND estado = 'PENDIENTE';
        """, (cand['sesion_id'], candidata_id))

        db.commit()
        return {
            'presupuesto_semanal_id': presupuesto_id,
            'comedor_id': comedor_id,
            'semana_inicio': fecha_inicio.isoformat(),
            'dias_cocina': sorted({d['dia_semana'] for d in menu}),
            'variante': cand['variante'],
            'etiqueta': cand['etiqueta'],
            'costo_total_semana': resumen.get('costo_total_semana'),
            'recoleccion_total_semana': resumen.get('recoleccion_total_semana'),
            'margen_proyectado': resumen.get('margen_proyectado'),
            'viable': bool(resumen.get('dentro_de_presupuesto', True)),
            'estado': 'SELECCIONADA',
            'message': 'Menú semanal fijado exitosamente. Ya está disponible en Planificaciones.',
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al seleccionar la propuesta: {e}")
    finally:
        cur.close()


# ==========================================
# HISTORIAL DE MENÚS SELECCIONADOS
# ==========================================
@router.get("/historial")
def historial_propuestas(comedor_id: int, usuario_solicitante_id: int,
                         db=Depends(get_db)):
    """Menús semanales definitivos del comedor (maestro + variante que los originó)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_puede_generar(cur, usuario_solicitante_id, comedor_id)
        cur.execute("""
            SELECT ps.id, ps.fecha_referencia, ps.fondo_total, ps.dias_operativos,
                   ps.costo_total_semana, ps.recoleccion_total_proyectada,
                   ps.margen, ps.viable, ps.estado, ps.fecha_seleccion,
                   pc.variante, pc.etiqueta, pc.sesion_id,
                   us.nombres || ' ' || us.apellido_paterno AS seleccionado_por
            FROM presupuesto_semanal ps
            LEFT JOIN planificaciones_candidatas pc ON pc.id = ps.candidata_id
            LEFT JOIN usuarios us ON us.id = ps.seleccionado_por_id
            WHERE ps.comedor_id = %s
            ORDER BY ps.fecha_referencia DESC, ps.id DESC;
        """, (comedor_id,))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el historial: {e}")
    finally:
        cur.close()


@router.get("/historial/{presupuesto_id}/dias")
def historial_dias(presupuesto_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """Detalle diario (planificacion_dia) de un menú seleccionado, con recolección y comensales."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT comedor_id FROM presupuesto_semanal WHERE id = %s;",
                    (presupuesto_id,))
        maestro = cur.fetchone()
        if not maestro:
            raise HTTPException(status_code=404, detail="Planificación no encontrada.")
        _validar_puede_generar(cur, usuario_solicitante_id, maestro['comedor_id'])
        cur.execute("""
            SELECT id, dia, dia_nombre, comensales_social, comensales_afiliado,
                   comensales_normal, total_comensales, receta_id, nombre_receta,
                   costo_racion, costo_total, recoleccion_proyectada
            FROM planificacion_dia
            WHERE presupuesto_semanal_id = %s
            ORDER BY dia;
        """, (presupuesto_id,))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el detalle: {e}")
    finally:
        cur.close()