"""
routers/kmeans.py
Objetivo: Endpoints del módulo de clustering nutricional del recetario (COM-5):
          entrenamiento del modelo K-means (k=4), resumen del modelo activo,
          recetas por cluster, auditoría de reglas R1-R3 y diagnóstico del esquema
          detectado por el motor.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos: El entrenamiento queda restringido al Administrador de Sistemas y al perfil
          Directivo (Presidente/Tesorero), que gestionan el recetario.
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
    diagnosticar_esquema,
)

router = APIRouter(prefix="/kmeans", tags=["K-Means Recetas"])


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _puede_entrenar(cur, usuario_id: int) -> bool:
    """El re-entrenamiento es una acción de gestión del recetario."""
    if not usuario_id:
        return False
    perfil = obtener_perfil_usuario(cur, usuario_id)
    return perfil in (PERFIL_ADMIN_SISTEMA, PERFIL_DIRECTIVO)


# ==========================================
# DIAGNÓSTICO DEL ESQUEMA (auditoría del motor)
# ==========================================
@router.get("/diagnostico")
def diagnostico(db=Depends(get_db)):
    """
    Reporte de las tablas y columnas que el motor detectó en la base (puente
    receta-ingrediente, catálogo, recetas, precios, unidades y nutrición).
    Útil para verificar la configuración sin entrenar el modelo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        return diagnosticar_esquema(cur)
    finally:
        cur.close()


# ==========================================
# ENTRENAMIENTO DEL MODELO
# ==========================================
@router.post("/entrenar")
def entrenar_modelo(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Entrena el modelo K-means (k=4) con las recetas aptas tras aplicar las reglas
    R1 (proteína permitida), R2 (veto a res/cerdo) y R3 (sin precio alto), etiqueta
    los centroides semánticamente y persiste el nuevo modelo como activo.
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
    agregado por cluster. Responde 404 mientras no exista modelo entrenado (estado
    esperado antes del primer entrenamiento).
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
    """Recetas asignadas al modelo activo con su snapshot de features por ración."""
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
    aptas (con sus 4 variables por ración) y excluidas con su motivo (R1-R3).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        return listar_candidatas(cur)
    finally:
        cur.close()