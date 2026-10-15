"""
routers/reportes_municipio.py
Objetivo: COM-78: endpoints macro de la municipalidad / Admin de Sistemas:
  GET /reportes-municipio/dashboard   -> Dashboard Distrital de Seguridad Alimentaria.
  GET /reportes-municipio/observatorio-> Observatorio de Volatilidad de Precios.
  GET /reportes-municipio/cobertura   -> Cobertura y Focalización Social (Ley 31315).
Gate: reutiliza _alcance_avanzado de COM-77: requiere puede_com78 (perfil
ADMINISTRATIVO municipal con módulo 'reportes'/'subsidio', o Admin de Sistemas).
El alcance limita los comedores agregados (municipal: su distrito; sistema: todos).
El DRILL-DOWN a un comedor no necesita endpoint nuevo: la UI monta los 5 endpoints
COM-77 (/reportes-avanzados/*) con el comedor_id focalizado (su gate ya acepta
municipal/sistema).
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: ticket COM-78 (solo trazabilidad).
"""
import traceback
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_db
from routers.reportes_avanzados import _alcance_avanzado
from ml import reportes_municipio as rm

router = APIRouter(prefix="/reportes-municipio", tags=["Reportes Municipio (COM-78)"])


def _validar_com78(cur, usuario_id):
    """Devuelve el alcance COM-77/78 o 403. comedor_ids=None significa 'todos'."""
    alc = _alcance_avanzado(cur, usuario_id)
    if not alc.get('puede_com78'):
        raise HTTPException(
            status_code=403,
            detail="Sin acceso a reportes macro municipales (requiere perfil "
                   "Administrativo municipal o Admin de Sistemas).")
    comedor_ids = None if alc['tipo_alcance'] == 'sistema' else [c['id'] for c in alc['comedores']]
    return alc, comedor_ids


@router.get("/dashboard")
def dashboard(usuario_solicitante_id: int,
              anio: int = Query(None), mes: int = Query(None),
              zona: str = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_com78(cur, usuario_solicitante_id)
        hoy = date.today()
        anio = anio or hoy.year
        mes = mes or hoy.month
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
        _, comedor_ids = _validar_com78(cur, usuario_solicitante_id)
        return rm.dashboard_distrital(cur, comedor_ids, anio, mes, zona=zona)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en dashboard distrital ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/observatorio")
def observatorio(usuario_solicitante_id: int,
                 dias: int = Query(90, ge=30, le=365), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_com78(cur, usuario_solicitante_id)
        return rm.observatorio_precios(cur, dias=dias)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en observatorio de precios ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/cobertura")
def cobertura(usuario_solicitante_id: int,
              anio: int = Query(None), mes: int = Query(None),
              zona: str = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_com78(cur, usuario_solicitante_id)
        hoy = date.today()
        anio = anio or hoy.year
        mes = mes or hoy.month
        if not (1 <= mes <= 12):
            raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
        _, comedor_ids = _validar_com78(cur, usuario_solicitante_id)
        return rm.cobertura_focalizacion(cur, comedor_ids, anio, mes, zona=zona)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en cobertura/focalización ({type(e).__name__}): {e}")
    finally:
        cur.close()