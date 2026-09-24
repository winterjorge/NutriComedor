"""
routers/kmeans.py
Objetivo: Endpoints del módulo de clustering nutricional del recetario (COM-5):
          entrenamiento del modelo K-means (k=4) sobre las 4 variables por ración
          (energía, hierro, proteína y precio), consulta del modelo activo con sus
          clusters agregados, listado de recetas por cluster y transparencia de
          recetas aptas/excluidas por las reglas de negocio R1-R3.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos: El entrenamiento (POST /entrenar) queda restringido al Administrador de
          Sistemas y al perfil Directivo (Presidente/Tesorero), que son quienes
          gestionan el recetario según la matriz de módulos (COM-25).
Referencia: ticket COM-5 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from database import get_db
from permisos import (
    obtener_perfil_usuario,
    PERFIL_ADMIN_SISTEMA,
    PERFIL_DIRECTIVO,
)
from ml.kmeans_recetas import (
    entrenar_y_persistir,
    obtener_modelo_activo,
    obtener_recetas_por_cluster,
    listar_candidatas,
)

router = APIRouter(prefix="/kmeans", tags=["K-Means Recetas"])


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _puede_entrenar(cur, usuario_id: int) -> bool:
    """
    COM-5: El re-entrenamiento del modelo es una acción de gestión del recetario:
    se permite al Administrador de Sistemas y al perfil Directivo.
    """
    if not usuario_id:
        return False
    perfil = obtener_perfil_usuario(cur, usuario_id)
    return perfil in (PERFIL_ADMIN_SISTEMA, PERFIL_DIRECTIVO)


# ==========================================
# ENTRENAMIENTO DEL MODELO
# ==========================================
@router.post("/entrenar")
def entrenar_modelo(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Entrena el modelo K-means (k=4) con las recetas aptas tras aplicar las reglas
    R1 (proteína permitida), R2 (veto a res/cerdo) y R3 (sin precio alto), etiqueta
    los centroides semánticamente y persiste el nuevo modelo como activo.
    Retorna el resumen: métricas (inercia, silhouette), clusters con centroide y
    ejemplos, y el detalle de recetas excluidas con su motivo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _puede_entrenar(cur, usuario_solicitante_id):
            raise HTTPException(
                status_code=403,
                detail="Sin permiso: el entrenamiento del modelo está reservado al "
                       "Administrador de Sistemas y al perfil Directivo.")
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
def resumen_modelo(db=Depends(get_db)):
    """
    Metadatos del modelo activo (k, métricas, centroides, parámetros) junto con el
    agregado por cluster: número de recetas y promedios de las 4 variables.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
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
        }
    finally:
        cur.close()


# ==========================================
# RECETAS POR CLUSTER
# ==========================================
@router.get("/clusters")
def recetas_por_cluster(
    cluster_codigo: int = Query(None, ge=1, le=4,
                                description="Código de cluster (1-4). Si se omite, devuelve todos."),
    db=Depends(get_db),
):
    """
    Recetas asignadas al modelo activo con su snapshot de features por ración
    (energía, proteína, hierro, fibra, precio y nivel de precio).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        modelo = obtener_modelo_activo(cur)
        if not modelo:
            raise HTTPException(
                status_code=404,
                detail="Aún no hay un modelo K-means entrenado. Ejecute POST /kmeans/entrenar.")
        return obtener_recetas_por_cluster(cur, modelo['id'], cluster_codigo)
    finally:
        cur.close()


# ==========================================
# TRANSPARENCIA: RECETAS APTAS Y EXCLUIDAS
# ==========================================
@router.get("/candidatas")
def recetas_candidatas(db=Depends(get_db)):
    """
    Recalcula el dataset con los parámetros vigentes sin persistir nada: recetas
    aptas (con sus 4 variables por ración) y recetas excluidas con su motivo
    (contiene_res_o_cerdo, sin_proteina_permitida, sin_datos_nutricion, sin_precio,
    precio_alto, sin_ingredientes). Útil para auditar las reglas R1-R3.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        return listar_candidatas(cur)
    finally:
        cur.close()