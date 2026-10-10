"""
routers/precios_venta.py
Objetivo: COM-59A: precios de venta por tipo de comensal con HISTORIAL y política de
          precio único vigente hasta nuevo cambio (estabilidad para el comensal).
          GET  /precios-venta/vigentes            -> precio vigente por tipo (público
                                                     interno: POS, motores y UI).
          GET  /precios-venta/historial           -> historial completo (o por tipo).
          POST /precios-venta                     -> nuevo precio (cierra el anterior por
                                                     fecha: rige el más reciente no futuro).
Historial:
 - COM-59A v1: versión original.
 - COM-59A v2: FIX DE SEGURIDAD del historial: exige usuario_solicitante_id y valida
   es_admin_sistema (la v1 ejecutaba un SELECT que no usaba al solicitante).
 - COM-59A v3 (este archivo): ESPEJO DE PRECIOS para consumidores legacy: al registrar
   un precio nuevo se sincroniza el parámetro PRECIO_SOCIAL/PRECIO_AFILIADO/PRECIO_NORMAL
   de parametros_sistema, de modo que POS y cualquier vista que lea parámetros reflejen
   el precio vigente SIN modificar POSView.jsx. precios_venta sigue siendo la fuente de
   verdad (los motores leen precio_venta_vigente()).
Permisos: POST y GET /historial exclusivos del Administrador de Sistemas.
          GET /vigentes sin gate (dato de política comercial de uso interno).
Nota: no hay PUT/DELETE: un precio no se edita ni se borra; se registra uno nuevo y el
      historial queda para auditoría/rendición de cuentas.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-59 (solo trazabilidad).
"""
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema
from subsidio_motor import precio_venta_vigente

router = APIRouter(prefix="/precios-venta", tags=["Precios de Venta (COM-59A)"])

TIPOS_COMENSAL = ('Social', 'Afiliado', 'Normal')

# COM-59A v3: mapa tipo de comensal -> parámetro legacy espejado en parametros_sistema
PARAM_LEGACY_POR_TIPO = {
    'Social': 'PRECIO_SOCIAL',
    'Afiliado': 'PRECIO_AFILIADO',
    'Normal': 'PRECIO_NORMAL',
}


class NuevoPrecioVentaInput(BaseModel):
    usuario_solicitante_id: int
    tipo_comensal: str
    precio: float
    observacion: Optional[str] = None


def _validar_admin(cur, usuario_id: int) -> None:
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(status_code=403,
                            detail="Sin permiso: los precios de venta los define solo el "
                                   "Administrador de Sistemas (política global).")


@router.get("/vigentes")
def precios_vigentes(db=Depends(get_db)):
    """
    COM-59A: precio vigente de cada tipo de comensal (el más reciente no futuro).
    Sin gate: es dato de política comercial usado por POS, motores Greedy/Reporte y UI.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        out = {t: precio_venta_vigente(cur, t) for t in TIPOS_COMENSAL}
        return out
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al leer precios vigentes ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/historial")
def historial_precios(
    usuario_solicitante_id: int = Query(..., description="COM-59A v2: obligatorio para auditar al lector"),
    tipo_comensal: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """
    COM-59A v2: historial de cambios de precio (auditoría). EXCLUSIVO del Admin de
    Sistemas: se valida al solicitante con es_admin_sistema.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # COM-59A v2 (fix): validación real del solicitante.
        # COM-59A v1 (trazabilidad): check anterior COMENTADO (no usaba al solicitante):
        # cur.execute("SELECT 1 FROM usuarios WHERE rol = 'Administrador Sistema' LIMIT 1;")
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT pv.id, pv.tipo_comensal, pv.precio, pv.vigente_desde, pv.observacion,
                   u.nombres || ' ' || u.apellido_paterno AS creado_por_nombre
            FROM precios_venta pv
            LEFT JOIN usuarios u ON u.id = pv.creado_por
            WHERE (%s IS NULL OR pv.tipo_comensal = %s)
            ORDER BY pv.vigente_desde DESC;
        """, (tipo_comensal, tipo_comensal))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al leer el historial ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.post("", status_code=201)
def registrar_precio(data: NuevoPrecioVentaInput, db=Depends(get_db)):
    """
    COM-59A v3: registra un nuevo precio vigente (el anterior queda en historial) y
    ESPEJA el valor en el parámetro legacy PRECIO_* para que POS y consumidores de
    parametros_sistema reflejen el precio vigente de inmediato. Solo Admin de Sistemas.
    """
    if data.tipo_comensal not in TIPOS_COMENSAL:
        raise HTTPException(status_code=400,
                            detail=f"Tipo de comensal inválido: use uno de {TIPOS_COMENSAL}.")
    if data.precio < 0:
        raise HTTPException(status_code=400, detail="El precio no puede ser negativo.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        cur.execute("""
            INSERT INTO precios_venta (tipo_comensal, precio, observacion, creado_por)
            VALUES (%s, %s, %s, %s)
            RETURNING id, vigente_desde;
        """, (data.tipo_comensal, data.precio,
              (data.observacion or '').strip() or None, data.usuario_solicitante_id))
        nuevo = cur.fetchone()
        # COM-59A v3: espejo legacy en parametros_sistema (POS y vistas antiguas)
        clave_param = PARAM_LEGACY_POR_TIPO[data.tipo_comensal]
        cur.execute("""
            UPDATE parametros_sistema
            SET valor = %s,
                fecha_actualizacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
            WHERE clave = %s;
        """, (f"{data.precio:.2f}", clave_param))
        espejado = cur.rowcount or 0
        db.commit()
        return {'id': nuevo['id'], 'vigente_desde': str(nuevo['vigente_desde']),
                'parametro_reflejado': clave_param if espejado else None,
                'message': f"Precio {data.tipo_comensal} = S/ {data.precio:.2f} vigente desde ahora."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al registrar el precio ({type(e).__name__}): {e}")
    finally:
        cur.close()