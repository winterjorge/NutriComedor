"""
routers/scraper_admin.py
Objetivo: COM-43: ejecución del scraper SISAP desde la web (solo Admin de Sistemas)
para UN DÍA o un RANGO de fechas, reutilizando SIN MODIFICACIONES el código existente
del scraper (scraper/main.py::ejecutar_scraper) mediante import in-process en un hilo
en segundo plano. Incluye:
* POST /scraper/ejecutar   -> lanza una corrida WEB (fecha_inicio/fecha_fin opcionales).
* GET  /scraper/estado     -> progreso en vivo del job + última fecha en BD + hueco.
* GET  /scraper/historial  -> últimas corridas auditadas (scraper_corridas).
* lanzar_catchup_arranque()-> al arrancar la API, si el servidor estuvo apagado y hay
  fechas faltantes entre la última corrida y ayer, lanza una corrida ORIGEN='ARRANQUE'
  (tope MAX_DIAS_CATCHUP) para que la automatización no dependa solo del cron.
* Las corridas dejan auditoría en scraper_corridas (esquema_scraper.py, COM-43).
El cron del host (corregido en COM-43) sigue siendo la vía diaria principal; este
router es la vía manual/backfill y la red de seguridad de arranque. Ninguna línea del
scraper existente se modifica: solo se importa y se orquesta.
Historial:
COM-43 (este archivo): versión original.
Permisos: TODOS los endpoints exigen es_admin_sistema (mismo gate que kmeans/modelos_ml).
Uso: Registrado en main.py con prefijo /api/v1. lanzar_catchup_arranque() se invoca
en el lifespan de main.py tras asegurar_esquema().
Referencia: ticket COM-43 (solo trazabilidad).
"""
import os
import sys
import json
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema

router = APIRouter(prefix="/scraper", tags=["Scraper SISAP"])

TZ = ZoneInfo("America/Lima")
# COM-43: pausa de cortesía entre fechas (no saturar al portal MIDAGRI)
PAUSA_ENTRE_FECHAS = 2.0
# COM-43: tope de días que el catch-up de arranque rellena en una sola pasada
MAX_DIAS_CATCHUP = 90
# COM-43: tope de rango aceptado en una corrida WEB (evita ranges abusivos)
MAX_DIAS_WEB = 400

# COM-43: el paquete `scraper` vive en backend/scraper/; el backend corre con cwd=backend,
# pero aseguramos el path para import in-process desde cualquier cwd (uvicorn/tests).
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ==========================================
# ESTADO DEL JOB EN MEMORIA (un solo job concurrente)
# ==========================================
_job_lock = threading.Lock()
_job = {
    'activo': False,
    'corrida_id': None,
    'origen': None,
    'fecha_inicio': None,
    'fecha_fin': None,
    'fecha_actual': None,
    'dias_totales': 0,
    'dias_procesados': 0,
    'dias_exitosos': 0,
    'dias_fallidos': 0,
    'inicio_iso': None,
    'ultimo_evento': None,
}


class EjecutarScraperInput(BaseModel):
    """COM-43: payload del lanzamiento web. Sin fechas => corrida de HOY."""
    usuario_solicitante_id: int
    fecha_inicio: Optional[str] = None   # YYYY-MM-DD
    fecha_fin: Optional[str] = None      # YYYY-MM-DD (default: fecha_inicio)


# ==========================================
# HELPERS DE BD Y AUDITORÍA
# ==========================================
def _conn_bd():
    """Conexión psycopg2 independiente para el hilo de trabajo (DATABASE_URL del compose)."""
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL no está definido en el entorno del contenedor api.")
    return psycopg2.connect(dsn)


def _validar_admin(cur, usuario_id: int) -> None:
    """COM-43: el módulo de scraper es exclusivo del Administrador de Sistemas."""
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: la operación del scraper es exclusiva del Administrador de Sistemas.")


def _parse_fecha(valor: str, campo: str) -> date:
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Formato inválido en {campo}: use YYYY-MM-DD.")


def _registros_de_fecha(fecha_iso: str) -> int:
    """COM-43: filas de historial_precios de una fecha (métrica de éxito por día)."""
    conn = _conn_bd()
    try:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM historial_precios WHERE fecha = %s;", (fecha_iso,))
            return int(c.fetchone()[0])
    finally:
        conn.close()


def _actualizar_corrida(corrida_id: int, **campos):
    if not campos:
        return
    sets = ", ".join(f"{k} = %s" for k in campos.keys())
    conn = _conn_bd()
    try:
        with conn.cursor() as c:
            c.execute(f"UPDATE scraper_corridas SET {sets} WHERE id = %s;",
                      tuple(campos.values()) + (corrida_id,))
        conn.commit()
    finally:
        conn.close()


def _crear_corrida(origen: str, f_inicio: date, f_fin: date, usuario_id: Optional[int]) -> int:
    conn = _conn_bd()
    try:
        with conn.cursor() as c:
            c.execute("""
                INSERT INTO scraper_corridas (origen, fecha_inicio, fecha_fin, usuario_solicitante_id)
                VALUES (%s, %s, %s, %s) RETURNING id;
            """, (origen, f_inicio, f_fin, usuario_id))
            corrida_id = c.fetchone()[0]
        conn.commit()
        return corrida_id
    finally:
        conn.close()


# ==========================================
# HILO DE TRABAJO (invoca el scraper EXISTENTE)
# ==========================================
def _trabajo_rango(corrida_id: int, origen: str, f_inicio: date, f_fin: date):
    """
    COM-43: recorre el rango y llama a scraper.main.ejecutar_scraper (código existente,
    sin modificaciones). Actualiza el job en memoria y la fila de auditoría por día.
    """
    # Import diferido dentro del hilo: un fallo de dependencias no tumba el import del router.
    from scraper.main import ejecutar_scraper

    fallos = []
    dia = f_inicio
    while dia <= f_fin:
        with _job_lock:
            if not _job['activo'] or _job['corrida_id'] != corrida_id:
                break
            _job['fecha_actual'] = dia.isoformat()
        ok = False
        regs = 0
        try:
            fecha_dt = datetime(dia.year, dia.month, dia.day, tzinfo=TZ)
            ok = bool(ejecutar_scraper(fecha_dt))
            regs = _registros_de_fecha(dia.isoformat())
            if ok and regs == 0:
                ok = False  # ejecutó pero no dejó precios: se cuenta como fallo auditable
        except Exception as e:
            ok = False
            fallos.append({'fecha': dia.isoformat(), 'error': str(e)[:300]})
        if not ok and not any(f['fecha'] == dia.isoformat() for f in fallos):
            fallos.append({'fecha': dia.isoformat(), 'error': 'sin registros insertados'})

        with _job_lock:
            _job['dias_procesados'] += 1
            if ok:
                _job['dias_exitosos'] += 1
                _job['ultimo_evento'] = f"OK {dia.isoformat()} ({regs} precios)"
            else:
                _job['dias_fallidos'] += 1
                _job['ultimo_evento'] = f"FALLO {dia.isoformat()}"
            snap = dict(_job)
        _actualizar_corrida(
            corrida_id,
            dias_procesados=snap['dias_procesados'],
            dias_exitosos=snap['dias_exitosos'],
            dias_fallidos=snap['dias_fallidos'],
        )
        dia += timedelta(days=1)
        if dia <= f_fin:
            time.sleep(PAUSA_ENTRE_FECHAS)

    with _job_lock:
        exitosos = _job['dias_exitosos']
        fallidos = _job['dias_fallidos']
        _job['activo'] = False
        _job['fecha_actual'] = None
    estado_final = 'COMPLETADA' if fallidos == 0 else ('FALLIDA' if exitosos == 0 else 'COMPLETADA_CON_ERRORES')
    _actualizar_corrida(
        corrida_id,
        estado=estado_final,
        detalle=json.dumps({'fallos': fallos[:100]}),
        terminado_en=datetime.now(TZ).replace(tzinfo=None),
    )


def _iniciar_job(origen: str, f_inicio: date, f_fin: date, usuario_id: Optional[int]) -> int:
    """Registra la corrida y lanza el hilo. Devuelve el corrida_id. 409 si hay job activo."""
    with _job_lock:
        if _job['activo']:
            raise HTTPException(status_code=409, detail="Ya hay una corrida de scraper en proceso.")
        corrida_id = _crear_corrida(origen, f_inicio, f_fin, usuario_id)
        _job.update({
            'activo': True,
            'corrida_id': corrida_id,
            'origen': origen,
            'fecha_inicio': f_inicio.isoformat(),
            'fecha_fin': f_fin.isoformat(),
            'fecha_actual': None,
            'dias_totales': (f_fin - f_inicio).days + 1,
            'dias_procesados': 0,
            'dias_exitosos': 0,
            'dias_fallidos': 0,
            'inicio_iso': datetime.now(TZ).isoformat(),
            'ultimo_evento': 'Iniciando...',
        })
    t = threading.Thread(target=_trabajo_rango, args=(corrida_id, origen, f_inicio, f_fin), daemon=True)
    t.start()
    return corrida_id


# ==========================================
# COM-43: CATCH-UP DE ARRANQUE (servidor no 24/7)
# ==========================================
def lanzar_catchup_arranque():
    """
    COM-43: al arrancar la API: (1) marca como FALLIDA cualquier corrida EN_PROCESO
    interrumpida por un reinicio; (2) si la última fecha de historial_precios es menor
    que ayer, lanza una corrida ORIGEN='ARRANQUE' para rellenar el hueco (tope
    MAX_DIAS_CATCHUP). Nunca bloquea ni tumba el arranque.
    """
    try:
        conn = _conn_bd()
        try:
            with conn.cursor() as c:
                c.execute("""
                    UPDATE scraper_corridas
                    SET estado = 'FALLIDA',
                        detalle = 'Interrumpida por reinicio del servicio',
                        terminado_en = CURRENT_TIMESTAMP
                    WHERE estado = 'EN_PROCESO';
                """)
                c.execute("SELECT MAX(fecha) FROM historial_precios;")
                fila = c.fetchone()
            conn.commit()
        finally:
            conn.close()
        max_fecha = fila[0] if fila else None
        ayer = datetime.now(TZ).date() - timedelta(days=1)
        if max_fecha is None or max_fecha >= ayer:
            return
        inicio = max(max_fecha + timedelta(days=1), ayer - timedelta(days=MAX_DIAS_CATCHUP))
        if inicio > ayer:
            return
        with _job_lock:
            if _job['activo']:
                return
        corrida_id = _iniciar_job('ARRANQUE', inicio, ayer, None)
        print(f"[BOOTSTRAP] COM-43: catch-up de scraper lanzado (corrida {corrida_id}): "
              f"{inicio.isoformat()} -> {ayer.isoformat()}.")
    except Exception as e:
        print(f"[BOOTSTRAP] COM-43: catch-up de scraper NO iniciado: {e}")


# ==========================================
# ENDPOINTS
# ==========================================
@router.post("/ejecutar")
def ejecutar_scraper_web(data: EjecutarScraperInput, db=Depends(get_db)):
    """
    COM-43: lanza una corrida WEB del scraper existente para un día o un rango.
    Sin fechas => corre HOY. Responde de inmediato con el corrida_id; el progreso
    se consulta en GET /scraper/estado. Exclusivo Admin de Sistemas.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        hoy = datetime.now(TZ).date()
        f_inicio = _parse_fecha(data.fecha_inicio, 'fecha_inicio') if data.fecha_inicio else hoy
        f_fin = _parse_fecha(data.fecha_fin, 'fecha_fin') if data.fecha_fin else f_inicio
        if f_fin < f_inicio:
            raise HTTPException(status_code=400, detail="fecha_fin no puede ser anterior a fecha_inicio.")
        if (f_fin - f_inicio).days + 1 > MAX_DIAS_WEB:
            raise HTTPException(status_code=400, detail=f"Rango máximo permitido: {MAX_DIAS_WEB} días.")
        if f_fin > hoy:
            raise HTTPException(status_code=400, detail="No se puede scrapear fechas futuras.")
        corrida_id = _iniciar_job('WEB', f_inicio, f_fin, data.usuario_solicitante_id)
        return {
            'corrida_id': corrida_id,
            'message': f"Corrida de scraper lanzada para {f_inicio.isoformat()} -> {f_fin.isoformat()}. "
                       f"Consulte el progreso en GET /scraper/estado.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al lanzar el scraper: {e}")
    finally:
        cur.close()


@router.get("/estado")
def estado_scraper(usuario_solicitante_id: int = Query(...), db=Depends(get_db)):
    """
    COM-43: progreso en vivo del job activo (o null), última fecha con datos en
    historial_precios, días faltantes hasta ayer y última corrida auditada.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        with _job_lock:
            job = dict(_job) if _job['activo'] else None
        cur.execute("SELECT MAX(fecha) AS ultima FROM historial_precios;")
        ultima = cur.fetchone()['ultima']
        ayer = datetime.now(TZ).date() - timedelta(days=1)
        faltantes = (ayer - ultima).days if ultima and ultima < ayer else (0 if ultima else None)
        cur.execute("""
            SELECT id, origen, fecha_inicio, fecha_fin, dias_procesados, dias_exitosos,
                   dias_fallidos, estado, iniciado_en, terminado_en, usuario_solicitante_id
            FROM scraper_corridas ORDER BY id DESC LIMIT 1;
        """)
        ultima_corrida = cur.fetchone()
        return {
            'job': job,
            'ultima_fecha_bd': ultima,
            'dias_faltantes_hasta_ayer': faltantes,
            'ultima_corrida': ultima_corrida,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar el estado: {e}")
    finally:
        cur.close()


@router.get("/historial")
def historial_scraper(usuario_solicitante_id: int = Query(...),
                      limite: int = Query(20, ge=1, le=100),
                      db=Depends(get_db)):
    """COM-43: últimas corridas auditadas (web, cron no audita aquí, arranque)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT id, origen, fecha_inicio, fecha_fin, dias_procesados, dias_exitosos,
                   dias_fallidos, estado, detalle, usuario_solicitante_id,
                   iniciado_en, terminado_en
            FROM scraper_corridas
            ORDER BY id DESC
            LIMIT %s;
        """, (limite,))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar el historial: {e}")
    finally:
        cur.close()