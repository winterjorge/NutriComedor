"""
routers/reportes_avanzados.py
Objetivo: COM-77: endpoints de los 5 REPORTES OPERATIVOS del comedor y del alcance
unificado que usará también COM-78 (drill-down municipal):
  GET /reportes-avanzados/alcance             -> qué puede ver el usuario (com77/com78).
  GET /reportes-avanzados/estado-resultados   -> A) margen real vs proyectado.
  GET /reportes-avanzados/consumo-subsidio    -> B) tablero de quiebre de stock.
  GET /reportes-avanzados/inteligencia-compras-> C) ahorro por IA/scraper.
  GET /reportes-avanzados/merma-demanda       -> D) proyectado IA vs atendido POS.
  GET /reportes-avanzados/semaforo-nutricional-> E) KPIs de salud y Anemia Cero.
Gates COM-77 (perfil -> comedores visibles):
  * Admin de Sistemas      -> todos (y COM-78 completo).
  * Directivo u Operativo  -> solo su(s) comedor(es).
  * Municipal (Administrativo con módulo 'reportes' o 'subsidio')
                           -> comedores de su distrito (COM-78 + drill-down COM-77).
  * Sin membresías/módulo  -> 403.
COM-78 (próximo drop) agregará dashboard-distrital / observatorio-precios /
cobertura-focalización reutilizando _alcance_avanzado y el drill-down de estos 5 endpoints.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-77 / COM-78 (solo trazabilidad).
"""
import traceback
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema
from ml import reportes_comedor as rc

router = APIRouter(prefix="/reportes-avanzados", tags=["Reportes Avanzados (COM-77/78)"])

ROLES_DIRECTIVO = ('Presidente', 'Tesorero', 'Secretario')


# ==========================================
# HELPERS DE ALCANCE (COM-77 + base COM-78)
# ==========================================
def _comedores_directivo(cur, usuario_id):
    cur.execute("""
        SELECT ug.comedor_id FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        JOIN roles_grupo r ON r.id = ug.rol_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
          AND g.nombre = 'Directivo' AND r.nombre IN %s AND ug.comedor_id IS NOT NULL;
    """, (usuario_id, ROLES_DIRECTIVO))
    return {f['comedor_id'] for f in cur.fetchall()}


def _comedores_operativo(cur, usuario_id):
    cur.execute("""
        SELECT ug.comedor_id FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
          AND g.nombre = 'Operativo' AND ug.comedor_id IS NOT NULL;
    """, (usuario_id,))
    return {f['comedor_id'] for f in cur.fetchall()}


def _tiene_modulo(cur, usuario_id, claves):
    cur.execute("""
        SELECT 1 FROM usuario_grupo ug
        JOIN roles_modulos rm ON rm.rol_id = ug.rol_id
        JOIN modulos_sistema m ON m.id = rm.modulo_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND m.clave = ANY(%s)
        LIMIT 1;
    """, (usuario_id, list(claves)))
    return cur.fetchone() is not None


def _comedores_municipales(cur, usuario_id):
    """Comedores del distrito de la municipalidad del usuario (defensivo, estilo COM-50)."""
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_name IN ('usuario_municipalidad','municipalidades');
    """)
    if {r['table_name'] for r in cur.fetchall()} != {'usuario_municipalidad', 'municipalidades'}:
        return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='usuario_municipalidad';")
    cols_um = {r['column_name'] for r in cur.fetchall()}
    col_mun = next((c for c in ('municipalidad_id', 'id_municipalidad') if c in cols_um), None)
    if not col_mun:
        return set()
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='municipalidades';")
    cols_m = {r['column_name'] for r in cur.fetchall()}
    col_dist = next((c for c in ('distrito_id', 'id_distrito') if c in cols_m), None)
    if not col_dist:
        return set()
    cur.execute(f"""
        SELECT c.id FROM usuario_municipalidad um
        JOIN municipalidades m ON m.id = um.{col_mun}
        JOIN comedores c ON c.{col_dist} = m.{col_dist}
        WHERE um.usuario_id = %s;
    """, (usuario_id,))
    return {r['id'] for r in cur.fetchall()}


def _alcance_avanzado(cur, usuario_id):
    """
    COM-77/78: alcance unificado. Retorna dict con tipo, comedores com77 (operativos +
    drill-down) y flag com78 (macro municipal / admin).
    """
    if es_admin_sistema(cur, usuario_id):
        cur.execute("SELECT id, nombre, zona FROM comedores ORDER BY zona, nombre;")
        todos = [dict(r) for r in cur.fetchall()]
        return {'tipo_alcance': 'sistema', 'comedores': todos,
                'comedor_fijo': None, 'puede_com77': True, 'puede_com78': True,
                'zonas': sorted({(c['zona'] or '').strip() for c in todos if (c['zona'] or '').strip()})}
    propios = _comedores_directivo(cur, usuario_id) | _comedores_operativo(cur, usuario_id)
    municipales = set()
    if _tiene_modulo(cur, usuario_id, ('reportes', 'subsidio')):
        municipales = _comedores_municipales(cur, usuario_id)
    if not propios and not municipales:
        return {'tipo_alcance': 'ninguno', 'comedores': [], 'comedor_fijo': None,
                'puede_com77': False, 'puede_com78': False, 'zonas': []}
    ids = sorted(propios | municipales)
    cur.execute("SELECT id, nombre, zona FROM comedores WHERE id = ANY(%s) ORDER BY zona, nombre;", (ids,))
    comedores = [dict(r) for r in cur.fetchall()]
    return {
        'tipo_alcance': 'comedor' if propios and not municipales else ('municipal' if municipales and not propios else 'mixto'),
        'comedores': comedores,
        'comedor_fijo': comedores[0]['id'] if len(comedores) == 1 else None,
        'puede_com77': True,
        'puede_com78': bool(municipales) or False,
        'zonas': sorted({(c['zona'] or '').strip() for c in comedores if (c['zona'] or '').strip()})}


def _validar_comedor(cur, usuario_id, comedor_id):
    alc = _alcance_avanzado(cur, usuario_id)
    if not alc['puede_com77']:
        raise HTTPException(status_code=403, detail="Sin acceso a reportes operativos de comedores.")
    if alc['tipo_alcance'] == 'sistema':
        return alc
    if not any(c['id'] == comedor_id for c in alc['comedores']):
        raise HTTPException(status_code=403, detail="El comedor solicitado no pertenece a su alcance.")
    return alc


def _periodo(anio, mes):
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
    return anio, mes


# ==========================================
# ENDPOINTS
# ==========================================
@router.get("/alcance")
def alcance(usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-77/78: comedores visibles y flags de acceso para construir la UI."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        return _alcance_avanzado(cur, usuario_solicitante_id)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error al resolver alcance ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/estado-resultados")
def estado_resultados(usuario_solicitante_id: int, comedor_id: int,
                      anio: int = Query(None), mes: int = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_comedor(cur, usuario_solicitante_id, comedor_id)
        hoy = date.today()
        anio, mes = _periodo(anio or hoy.year, mes or hoy.month)
        return rc.estado_resultados(cur, comedor_id, anio, mes)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en estado de resultados ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/consumo-subsidio")
def consumo_subsidio(usuario_solicitante_id: int, comedor_id: int,
                     anio: int = Query(None), mes: int = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_comedor(cur, usuario_solicitante_id, comedor_id)
        hoy = date.today()
        anio, mes = _periodo(anio or hoy.year, mes or hoy.month)
        return rc.consumo_subsidio(cur, comedor_id, anio, mes)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en consumo de subsidio ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/inteligencia-compras")
def inteligencia_compras(usuario_solicitante_id: int, comedor_id: int,
                         anio: int = Query(None), mes: int = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_comedor(cur, usuario_solicitante_id, comedor_id)
        hoy = date.today()
        anio, mes = _periodo(anio or hoy.year, mes or hoy.month)
        return rc.inteligencia_compras(cur, comedor_id, anio, mes)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en inteligencia de compras ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/merma-demanda")
def merma_demanda(usuario_solicitante_id: int, comedor_id: int,
                  anio: int = Query(None), mes: int = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_comedor(cur, usuario_solicitante_id, comedor_id)
        hoy = date.today()
        anio, mes = _periodo(anio or hoy.year, mes or hoy.month)
        return rc.merma_demanda(cur, comedor_id, anio, mes)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en merma/demanda ({type(e).__name__}): {e}")
    finally:
        cur.close()


@router.get("/semaforo-nutricional")
def semaforo_nutricional(usuario_solicitante_id: int, comedor_id: int,
                         anio: int = Query(None), mes: int = Query(None), db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_comedor(cur, usuario_solicitante_id, comedor_id)
        hoy = date.today()
        anio, mes = _periodo(anio or hoy.year, mes or hoy.month)
        return rc.semaforo_nutricional(cur, comedor_id, anio, mes)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error en semáforo nutricional ({type(e).__name__}): {e}")
    finally:
        cur.close()