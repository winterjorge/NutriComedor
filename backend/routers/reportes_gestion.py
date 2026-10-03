"""
routers/reportes_gestion.py
Objetivo: COM-50 (HU-10): endpoints del reporte "Resumen ejecutivo y recomendaciones":
          GET /reportes-gestion/resumen     -> reporte completo del plan vigente (o del
                                               plan indicado por candidata_id/presupuesto_id).
          GET /reportes-gestion/planes      -> selector de planes disponibles del comedor.
Historial:
 - COM-50 v1: versión original.
 - COM-50 v2 (este archivo): el except del endpoint /resumen imprime el traceback
   completo en los logs de la API (docker compose logs api) para diagnóstico inmediato
   de errores 500, y el detalle del error incluye el tipo de excepción.
Permisos: módulo 'reportes' de la matriz COM-25 (sembrado para Directivo
          Presidente/Tesorero/Secretario y Admin), o Admin de Sistemas, o Admin del
          comedor. La voluntaria administradora puede así rendir cuentas a su organización.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-50 / HU-10 (solo trazabilidad).
"""
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema, es_admin_comedor
from ml.reporte_gestion import generar_reporte_gestion, listar_planes_disponibles

router = APIRouter(prefix="/reportes-gestion", tags=["Reporte de Gestión (COM-50)"])


def _puede_ver_reportes(cur, usuario_id: int, comedor_id: int) -> bool:
    """Admin de sistema, admin del comedor, o cualquier rol con el módulo 'reportes'."""
    if es_admin_sistema(cur, usuario_id):
        return True
    try:
        if es_admin_comedor(cur, usuario_id, comedor_id):
            return True
    except Exception:
        pass
    cur.execute("""
        SELECT 1
        FROM usuario_grupo ug
        JOIN roles_modulos rm ON rm.rol_id = ug.rol_id
        JOIN modulos_sistema m ON m.id = rm.modulo_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND m.clave = 'reportes'
        LIMIT 1;
    """, (usuario_id,))
    return cur.fetchone() is not None


@router.get("/resumen")
def resumen_ejecutivo(
    usuario_solicitante_id: int,
    comedor_id: int = Query(..., description="Comedor a reportar"),
    candidata_id: int = Query(None, description="Propuesta específica a reportar (opcional)"),
    presupuesto_id: int = Query(None, description="Planificación guardada específica (opcional)"),
    db=Depends(get_db),
):
    """COM-50: resumen ejecutivo + uso de presupuesto por día + sugerencias de ahorro."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _puede_ver_reportes(cur, usuario_solicitante_id, comedor_id):
            raise HTTPException(status_code=403,
                                detail="Sin permiso para ver reportes de este comedor.")
        reporte = generar_reporte_gestion(cur, comedor_id, candidata_id, presupuesto_id)
        if reporte.get('error') == 'sin_plan':
            raise HTTPException(status_code=404, detail=reporte.get('detalle'))
        return reporte
    except HTTPException:
        raise
    except Exception as e:
        # COM-50 v2: traza completa en logs para diagnóstico de errores 500
        traceback.print_exc()
        raise HTTPException(status_code=500,
                            detail=f"Error al generar el reporte ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/planes")
def planes_disponibles(
    usuario_solicitante_id: int,
    comedor_id: int = Query(...),
    db=Depends(get_db),
):
    """COM-50: propuestas y planificaciones disponibles para el selector del reporte."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _puede_ver_reportes(cur, usuario_solicitante_id, comedor_id):
            raise HTTPException(status_code=403,
                                detail="Sin permiso para ver reportes de este comedor.")
        return listar_planes_disponibles(cur, comedor_id)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al listar planes ({type(e).__name__}): {e}")
    finally:
        cur.close()