"""
routers/subsidio.py
Objetivo: COM-59A: CRUD del subsidio mensual de víveres por comedor (mes calendario).
          GET  /subsidio?comedor_id&anio&mes  -> líneas del mes con equivalencia en gramos.
          POST /subsidio                      -> alta/actualización (upsert por período).
          PUT  /subsidio/{id}                 -> edición de cantidad/unidad/observación.
          DELETE /subsidio/{id}               -> baja de una línea del período.
Permisos (COM-59A, SQL directo sin helpers externos):
          Gestión (POST/PUT/DELETE): Admin de Sistemas (cualquier comedor) o Directivo
          activo (Presidente/Tesorero/Secretario) DEL comedor objetivo.
          Lectura (GET): los anteriores + perfiles con módulo 'subsidio' cuyo alcance
          municipal (distrito de su municipalidad, COM-27) cubra el comedor.
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
from subsidio_motor import subsidio_gramos_del_mes

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
        JOIN comedores c ON c.{col_dist if col_dist in ('distrito_id',) else 'distrito_id'} = m.{col_dist}
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
# ENDPOINTS
# ==========================================
@router.get("")
def listar_subsidio(
    usuario_solicitante_id: int,
    comedor_id: int = Query(...),
    anio: int = Query(...),
    mes: int = Query(..., ge=1, le=12),
    db=Depends(get_db),
):
    """COM-59A: líneas del subsidio del mes con su equivalencia en gramos."""
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
        gramos = subsidio_gramos_del_mes(cur, comedor_id, anio, mes)
        for l in lineas:
            l['gramos_equivalentes'] = round(gramos.get(l['ingrediente_id'], 0.0), 2)
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