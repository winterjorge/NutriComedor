"""
routers/kmeans.py
Objetivo: Endpoints del módulo de clustering nutricional del recetario (COM-5):
entrenamiento del modelo K-means (k=4), resumen del modelo activo, recetas
por cluster, auditoría de reglas R1-R3, diagnóstico del esquema y, desde
COM-5 v4, la CONFIGURACIÓN de proteínas permitidas / ingredientes vetados.
Historial:
COM-5 v1: endpoints con permiso de entrenamiento para Admin de Sistemas o Directivo.
COM-5 v4: la vista de Clusters K-Means pasa a ser EXCLUSIVA del Administrador de
    Sistemas (módulo 'clusters'), por lo que TODOS los endpoints exigen
    es_admin_sistema. Se agregan GET/PUT /kmeans/proteinas. El permiso anterior
    (Directivo podía entrenar) queda COMENTADO abajo por trazabilidad.
COM-60 (este archivo): K-means v2:
    * GET /kmeans/resumen expone (aditivo) medianas por cluster, métricas post-hoc
      (precio mediano, Fe/S/, Prot/S/), scaler, k_evaluados y k_recomendado desde
      parametros del modelo; ninguna clave existente se elimina.
    * GET /kmeans/diagnostico-k nuevo: curva silhouette/inercia k=2..8 y
      k_recomendado sin persistir nada (criterio D5).
    * GET /kmeans/clusters devuelve también las 6 variables del snapshot.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-5 / COM-5 v4 / COM-60 (solo trazabilidad).
"""
import json
import unicodedata
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
from database import get_db
from permisos import es_admin_sistema
from ml.kmeans_recetas import (
    entrenar_y_persistir,
    obtener_modelo_activo,
    obtener_recetas_por_cluster,
    listar_candidatas,
    diagnosticar_esquema,
    diagnosticar_k,
    PROTEINAS_PERMITIDAS_DEFAULT,
    INGREDIENTES_VETADOS_DEFAULT,
)

router = APIRouter(prefix="/kmeans", tags=["K-Means Recetas"])

CLAVE_PROTEINAS = 'KMEANS_PROTEINAS_PERMITIDAS'
CLAVE_VETADOS = 'KMEANS_INGREDIENTES_VETADOS'


# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class ProteinasConfigInput(BaseModel):
    """Configuración de reglas de proteínas del clustering (solo Admin de Sistemas)."""
    permitidas: List[str]
    vetadas: List[str]
    usuario_solicitante_id: int


# ==========================================
# HELPERS DE PERMISO Y NORMALIZACIÓN
# ==========================================
def _validar_admin(cur, usuario_id: int) -> None:
    """
    COM-5 v4: el módulo de Clusters K-Means (vista, entrenamiento y configuración)
    es exclusivo del Administrador de Sistemas.
    """
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: el módulo de Clusters K-Means es exclusivo del "
                   "Administrador de Sistemas.")


# COM-5 v4 (trazabilidad): permiso ANTERIOR de entrenamiento (Admin o Directivo),
# comentado porque la vista de clusters pasó a ser admin-only. NO eliminar:
# def _puede_entrenar(cur, usuario_id: int) -> bool:
#     perfil = obtener_perfil_usuario(cur, usuario_id)
#     return perfil in (PERFIL_ADMIN_SISTEMA, PERFIL_DIRECTIVO)

def _token(t: str) -> str:
    """Normaliza un token de ingrediente: minúsculas, sin tildes ni espacios extra."""
    if not t:
        return ''
    txt = unicodedata.normalize('NFD', str(t).lower())
    return ''.join(c for c in txt if unicodedata.category(c) != 'Mn').strip()


def _leer_listas_config(cur):
    """Lee las listas configurables con fallback a los defaults históricos."""
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN (%s, %s);
    """, (CLAVE_PROTEINAS, CLAVE_VETADOS))
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    try:
        permitidas = json.loads(p.get(CLAVE_PROTEINAS) or 'null') or PROTEINAS_PERMITIDAS_DEFAULT
    except Exception:
        permitidas = PROTEINAS_PERMITIDAS_DEFAULT
    try:
        vetadas = json.loads(p.get(CLAVE_VETADOS) or 'null')
        if vetadas is None:
            vetadas = INGREDIENTES_VETADOS_DEFAULT
    except Exception:
        vetadas = INGREDIENTES_VETADOS_DEFAULT
    return permitidas, vetadas


def _guardar_lista(cur, clave: str, descripcion: str, valores: List[str]) -> None:
    """UPSERT de una lista de configuración en parametros_sistema (JSON)."""
    cur.execute("""
        INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato)
        VALUES (%s, %s, %s, 'IA', 'JSON')
        ON CONFLICT (clave) DO UPDATE
        SET valor = EXCLUDED.valor,
            fecha_actualizacion = CURRENT_TIMESTAMP - INTERVAL '5 hours';
    """, (clave, json.dumps(valores), descripcion))


# ==========================================
# CONFIGURACIÓN DE PROTEÍNAS (COM-5 v4)
# ==========================================
@router.get("/proteinas")
def obtener_proteinas(usuario_solicitante_id: int, db=Depends(get_db)):
    """Listas vigentes de proteínas permitidas e ingredientes vetados del clustering."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        permitidas, vetadas = _leer_listas_config(cur)
        return {
            'permitidas': permitidas,
            'vetadas': vetadas,
            'defaults': {
                'permitidas': PROTEINAS_PERMITIDAS_DEFAULT,
                'vetadas': INGREDIENTES_VETADOS_DEFAULT,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer la configuración: {e}")
    finally:
        cur.close()


@router.put("/proteinas")
def actualizar_proteinas(data: ProteinasConfigInput, db=Depends(get_db)):
    """
    Actualiza las listas configurables. Valida tokens no vacíos y al menos una
    proteína permitida. El cambio impacta en el PRÓXIMO entrenamiento del modelo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        permitidas = sorted({t for t in (_token(x) for x in data.permitidas) if t})
        vetadas = sorted({t for t in (_token(x) for x in data.vetadas) if t})
        if not permitidas:
            raise HTTPException(status_code=400,
                            detail="Debe existir al menos una proteína permitida.")
        for t in permitidas + vetadas:
            if len(t) < 2 or len(t) > 40:
                raise HTTPException(status_code=400,
                                detail=f"Token inválido: '{t}' (use entre 2 y 40 caracteres).")
        _guardar_lista(cur, CLAVE_PROTEINAS,
                       'COM-5 v4: listado configurable de proteínas permitidas para el clustering K-means',
                       permitidas)
        _guardar_lista(cur, CLAVE_VETADOS,
                       'COM-5 v4: listado configurable de ingredientes vetados por presupuesto (res/cerdo y derivados)',
                       vetadas)
        db.commit()
        return {
            'message': 'Configuración de proteínas actualizada. Re-entrene el modelo para aplicarla.',
            'permitidas': permitidas,
            'vetadas': vetadas,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar la configuración: {e}")
    finally:
        cur.close()


# ==========================================
# DIAGNÓSTICO DEL ESQUEMA (auditoría del motor)
# ==========================================
@router.get("/diagnostico")
def diagnostico(usuario_solicitante_id: int, db=Depends(get_db)):
    """Reporte de tablas/columnas detectadas por el motor (verificación de configuración)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        return diagnosticar_esquema(cur)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de diagnóstico: {e}")
    finally:
        cur.close()


# ==========================================
# COM-60: DIAGNÓSTICO DE K ÓPTIMO (curva silhouette/inercia)
# ==========================================
@router.get("/diagnostico-k")
def diagnostico_k(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-60 (criterio D5): curva de silhouette e inercia para k=2..8 sobre el dataset
    apto (RobustScaler, 6 features nutricionales) y k_recomendado por mejor
    silhouette. Es INFORMATIVO: no persiste modelos ni cambia el k operativo
    (KMEANS_K). Útil para el panel ML y para la sección de validación de la tesis.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        return diagnosticar_k(cur)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al diagnosticar k: {e}")
    finally:
        cur.close()


# ==========================================
# ENTRENAMIENTO DEL MODELO
# ==========================================
@router.post("/entrenar")
def entrenar_modelo(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-60: entrena el modelo K-means (k=KMEANS_K, default 4) con las 6 variables
    nutricionales por ración escaladas con RobustScaler, tras aplicar las reglas
    R1-R4; re-etiqueta centroides por medianas reales (prioridad Anemia Cero en el
    código 1), calcula métricas post-hoc por cluster (Fe/S/, Prot/S/) y el
    diagnóstico de k óptimo, y persiste el modelo activo. Exclusivo Admin.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        resumen = entrenar_y_persistir(cur)
        db.commit()
        return resumen
    except HTTPException:
        raise
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al entrenar el modelo: {e}")
    finally:
        cur.close()


# ==========================================
# RESUMEN DEL MODELO ACTIVO
# ==========================================
@router.get("/resumen")
def resumen_modelo(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Metadatos del modelo activo (métricas, centroides) + agregado por cluster.
    COM-60 (aditivo): expone scaler, features, k_evaluados, k_recomendado,
    n_imputadas, medianas y post-hoc por cluster desde parametros/centroides del
    modelo; las claves históricas (clusters, centroides, etiquetas) se conservan.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        modelo = obtener_modelo_activo(cur)
        if not modelo:
            raise HTTPException(
                status_code=404,
                detail="Aún no hay un modelo K-means entrenado. Ejecute POST /kmeans/entrenar.")
        cur.execute("""
            SELECT cluster_codigo,
                   cluster_etiqueta,
                   COUNT(*)                    AS n_recetas,
                   ROUND(AVG(energia_kcal), 2) AS energia_prom,
                   ROUND(AVG(hierro_mg), 2)    AS hierro_prom,
                   ROUND(AVG(proteina_g), 2)   AS proteina_prom,
                   ROUND(AVG(fibra_g), 2)      AS fibra_prom,
                   ROUND(AVG(precio_soles), 2) AS precio_prom,
                   MIN(precio_soles)           AS precio_min,
                   MAX(precio_soles)           AS precio_max
            FROM recetas_clusters
            WHERE modelo_id = %s
            GROUP BY cluster_codigo, cluster_etiqueta
            ORDER BY cluster_codigo;
        """, (modelo['id'],))
        clusters = cur.fetchall()
        # COM-60: enriquecimiento aditivo desde parametros del modelo
        params = modelo['parametros'] or {}
        medianas = params.get('medianas_por_cluster', {}) or {}
        post_hoc = params.get('post_hoc_por_cluster', {}) or {}
        for c in clusters:
            codigo_str = str(c['cluster_codigo'])
            c['medianas'] = medianas.get(codigo_str)
            c['post_hoc'] = post_hoc.get(codigo_str)
        return {
            'modelo_id': modelo['id'],
            'fecha_entrenamiento': modelo['fecha_entrenamiento'],
            'k': modelo['k'],
            'n_recetas': modelo['n_recetas'],
            'n_excluidas': modelo['n_excluidas'],
            'inercia': modelo['inercia'],
            'silhouette': modelo['silhouette'],
            'centroides': modelo['centroides'],
            'etiquetas': modelo['etiquetas'],
            'parametros': modelo['parametros'],
            'clusters': clusters,
            # COM-60: campos nuevos de auditoría v2 (aditivos)
            'scaler': params.get('scaler', 'StandardScaler'),
            'features': params.get('features'),
            'k_evaluados': params.get('k_evaluados', []),
            'k_recomendado': params.get('k_recomendado'),
            'n_imputadas': params.get('n_imputadas', 0),
            'post_hoc_por_cluster': post_hoc,
            'medianas_por_cluster': medianas,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener el resumen: {e}")
    finally:
        cur.close()


# ==========================================
# RECETAS POR CLUSTER
# ==========================================
@router.get("/clusters")
def recetas_por_cluster(
    usuario_solicitante_id: int,
    cluster_codigo: int = Query(None, ge=1, le=4,
                                description="Código de cluster (1-4). Si se omite, devuelve todos."),
    db=Depends(get_db),
):
    """Recetas asignadas al modelo activo con su snapshot de features por ración (6 variables COM-60)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        modelo = obtener_modelo_activo(cur)
        if not modelo:
            raise HTTPException(
                status_code=404,
                detail="Aún no hay un modelo K-means entrenado. Ejecute POST /kmeans/entrenar.")
        return obtener_recetas_por_cluster(cur, modelo['id'], cluster_codigo)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener recetas del cluster: {e}")
    finally:
        cur.close()


# ==========================================
# TRANSPARENCIA: RECETAS APTAS Y EXCLUIDAS
# ==========================================
@router.get("/candidatas")
def recetas_candidatas(usuario_solicitante_id: int, db=Depends(get_db)):
    """Recalcula el dataset con los parámetros vigentes sin persistir (auditoría R1-R4)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        return listar_candidatas(cur)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener recetas candidatas: {e}")
    finally:
        cur.close()