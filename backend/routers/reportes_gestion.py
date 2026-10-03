"""
routers/reportes_gestion.py
Objetivo: COM-50 (HU-10) v3: endpoints del reporte "Resumen ejecutivo y recomendaciones"
          con alcance por perfil:
            GET /reportes-gestion/alcance  -> qué puede reportar el usuario (perfil,
                                              comedor fijo, zonas y comedores disponibles).
            GET /reportes-gestion/resumen  -> reporte en nivel comedor/zona/macro.
            GET /reportes-gestion/planes   -> selector de planes de un comedor del alcance.
Matriz de permisos (COM-50 v3, resuelta con SQL directo, sin helpers externos):
            * Administrador de Sistemas  -> 403 (sin reportes relacionados a comedores).
            * Operativo (Cocinero)       -> 403 (sin reportería).
            * Directivo (Presidente/Tesorero/Secretario con comedor_id en usuario_grupo)
                                         -> solo SU comedor (nivel 'comedor' forzado).
            * Municipal (grupo Administrativo activo; vínculo usuario_municipalidad ->
              municipalidades.distrito_id -> comedores.distrito_id)
                                         -> macro (su distrito), zona o un comedor del distrito.
              Si el vínculo de municipalidad no existe, el alcance macro cae a todos los
              comedores (se informa en /alcance como 'macro_general').
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-50 / HU-10 (solo trazabilidad).
"""
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_db
from ml.reporte_gestion import generar_reporte_gestion, listar_planes_disponibles

router = APIRouter(prefix="/reportes-gestion", tags=["Reporte de Gestión (COM-50)"])

ROLES_DIRECTIVO = ('Presidente', 'Tesorero', 'Secretario')


# ==========================================
# RESOLUCIÓN DE ALCANCE (SQL directo, COM-50 v3)
# ==========================================
def _es_admin_sistema(cur, usuario_id):
    cur.execute("SELECT 1 FROM usuarios WHERE id = %s AND rol = 'Administrador Sistema';", (usuario_id,))
    return cur.fetchone() is not None


def _comedor_directivo(cur, usuario_id):
    """Comedor donde el usuario es Directivo activo (Presidente/Tesorero/Secretario)."""
    cur.execute("""
        SELECT ug.comedor_id
        FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        JOIN roles_grupo r ON r.id = ug.rol_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
          AND g.nombre = 'Directivo' AND r.nombre IN %s
          AND ug.comedor_id IS NOT NULL
        ORDER BY ug.id LIMIT 1;
    """, (usuario_id, ROLES_DIRECTIVO))
    fila = cur.fetchone()
    return fila['comedor_id'] if fila else None


def _es_operativo(cur, usuario_id):
    cur.execute("""
        SELECT 1
        FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND g.nombre = 'Operativo'
        LIMIT 1;
    """, (usuario_id,))
    return cur.fetchone() is not None


def _es_municipal(cur, usuario_id):
    cur.execute("""
        SELECT 1
        FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND g.nombre = 'Administrativo'
        LIMIT 1;
    """, (usuario_id,))
    return cur.fetchone() is not None


def _distrito_de_municipalidad_del_usuario(cur, usuario_id):
    """
    COM-50 v3 (defensivo): distrito de la municipalidad del usuario vía
    usuario_municipalidad -> municipalidades.distrito_id. Detecta columnas por esquema
    (estilo COM-5) para no depender de nombres exactos; None si no resoluble.
    """
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name IN ('usuario_municipalidad', 'municipalidades');
    """)
    tablas = {r['table_name'] for r in cur.fetchall()}
    if 'usuario_municipalidad' not in tablas or 'municipalidades' not in tablas:
        return None
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'usuario_municipalidad';
    """)
    cols_um = {r['column_name'] for r in cur.fetchall()}
    col_mun = next((c for c in ('municipalidad_id', 'id_municipalidad') if c in cols_um), None)
    if not col_mun:
        return None
    filtro_estado = " AND estado_activo = TRUE" if 'estado_activo' in cols_um else ""
    cur.execute(f"""
        SELECT {col_mun} AS mun_id FROM usuario_municipalidad
        WHERE usuario_id = %s{filtro_estado} LIMIT 1;
    """, (usuario_id,))
    fila = cur.fetchone()
    if not fila or fila['mun_id'] is None:
        return None
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'municipalidades';
    """)
    cols_m = {r['column_name'] for r in cur.fetchall()}
    col_dist = next((c for c in ('distrito_id', 'id_distrito') if c in cols_m), None)
    if not col_dist:
        return None
    cur.execute(f"SELECT {col_dist} AS distrito_id FROM municipalidades WHERE id = %s;", (fila['mun_id'],))
    fila2 = cur.fetchone()
    return fila2['distrito_id'] if fila2 else None


def _comedores_del_alcance(cur, usuario_id):
    """
    Retorna (tipo_alcance, lista_de_comedores) según la matriz COM-50 v3:
      ('ninguno', []) | ('sistema', []) | ('comedor', [uno]) |
      ('municipal', [distrito]) | ('macro_general', [todos])
    """
    if _es_admin_sistema(cur, usuario_id):
        return 'sistema', []
    comedor_id = _comedor_directivo(cur, usuario_id)
    if comedor_id:
        cur.execute("SELECT id, nombre, zona FROM comedores WHERE id = %s;", (comedor_id,))
        fila = cur.fetchone()
        return 'comedor', ([dict(fila)] if fila else [])
    if _es_operativo(cur, usuario_id):
        return 'ninguno', []
    if _es_municipal(cur, usuario_id):
        distrito_id = _distrito_de_municipalidad_del_usuario(cur, usuario_id)
        if distrito_id:
            cur.execute("""
                SELECT c.id, c.nombre, c.zona
                FROM comedores c
                WHERE c.distrito_id = %s
                ORDER BY c.zona, c.nombre;
            """, (distrito_id,))
            return 'municipal', [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT id, nombre, zona FROM comedores ORDER BY nombre;")
        return 'macro_general', [dict(r) for r in cur.fetchall()]
    return 'ninguno', []


# ==========================================
# ENDPOINTS
# ==========================================
@router.get("/alcance")
def alcance_reportes(usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-50 v3: qué puede reportar el usuario (para construir selectores en la UI)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        tipo, comedores = _comedores_del_alcance(cur, usuario_solicitante_id)
        if tipo in ('sistema', 'ninguno'):
            raise HTTPException(status_code=403,
                                detail=("El Administrador de Sistemas no tiene reportes relacionados a comedores."
                                        if tipo == 'sistema' else
                                        "Su perfil (operativo o sin membresías de gestión) no tiene acceso a reportería."))
        zonas = sorted({(c['zona'] or '').strip() for c in comedores if (c['zona'] or '').strip()})
        return {
            'tipo_alcance': tipo,
            'niveles_permitidos': (['comedor'] if tipo == 'comedor' else ['macro', 'zona', 'comedor']),
            'comedor_fijo': comedores[0]['id'] if tipo == 'comedor' else None,
            'comedor_nombre': comedores[0]['nombre'] if tipo == 'comedor' else None,
            'zonas': zonas,
            'comedores': comedores,
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al resolver alcance ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/resumen")
def resumen_ejecutivo(
    usuario_solicitante_id: int,
    nivel: str = Query('comedor', description="comedor | zona | macro"),
    comedor_id: int = Query(None),
    zona: str = Query(None),
    candidata_id: int = Query(None),
    presupuesto_id: int = Query(None),
    db=Depends(get_db),
):
    """COM-50 v3: resumen ejecutivo + uso de presupuesto por día + sugerencias."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        tipo, comedores = _comedores_del_alcance(cur, usuario_solicitante_id)
        if tipo == 'sistema':
            raise HTTPException(status_code=403,
                                detail="El Administrador de Sistemas no tiene reportes relacionados a comedores.")
        if tipo == 'ninguno':
            raise HTTPException(status_code=403,
                                detail="Su perfil no tiene acceso a reportería (solo Directivo y Municipal).")
        # Directivo: nivel forzado a su comedor, ignorando parámetros externos
        if tipo == 'comedor':
            nivel = 'comedor'
            comedor_id = comedores[0]['id']
        elif nivel == 'comedor' and comedor_id is not None:
            if not any(c['id'] == comedor_id for c in comedores):
                raise HTTPException(status_code=403,
                                    detail="El comedor solicitado no pertenece a su alcance de reportería.")
        reporte = generar_reporte_gestion(
            cur, comedores, nivel=nivel, zona=zona, comedor_id=comedor_id,
            candidata_id=candidata_id, presupuesto_id=presupuesto_id)
        if reporte.get('error') in ('sin_plan', 'sin_datos'):
            raise HTTPException(status_code=404, detail=reporte.get('detalle'))
        if reporte.get('error'):
            raise HTTPException(status_code=400, detail=reporte.get('detalle'))
        reporte['tipo_alcance'] = tipo
        return reporte
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al generar el reporte ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/planes")
def planes_disponibles(
    usuario_solicitante_id: int,
    comedor_id: int = Query(...),
    db=Depends(get_db),
):
    """COM-50: selector de planes de un comedor DENTRO del alcance del solicitante."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        tipo, comedores = _comedores_del_alcance(cur, usuario_solicitante_id)
        if tipo in ('sistema', 'ninguno'):
            raise HTTPException(status_code=403, detail="Sin acceso a reportería.")
        if not any(c['id'] == comedor_id for c in comedores):
            raise HTTPException(status_code=403, detail="Comedor fuera de su alcance de reportería.")
        return listar_planes_disponibles(cur, comedor_id)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al listar planes ({type(e).__name__}): {e}")
    finally:
        cur.close()