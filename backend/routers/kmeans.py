"""
routers/kmeans.py
Objetivo: Endpoints del módulo de clustering nutricional del recetario (COM-5):
          entrenamiento del modelo K-means (k=4), resumen del modelo activo, recetas
          por cluster, auditoría de reglas R1-R3, diagnóstico del esquema y, desde
          COM-5 v4, la CONFIGURACIÓN de proteínas permitidas / ingredientes vetados.
Historial:
 - COM-5 v1: endpoints con permiso de entrenamiento para Admin de Sistemas o Directivo.
 - COM-5 v4 (este archivo): la vista de Clusters K-Means pasa a ser EXCLUSIVA del
   Administrador de Sistemas (módulo 'clusters'), por lo que TODOS los endpoints exigen
   es_admin_sistema. Se agregan GET/PUT /kmeans/proteinas para editar las listas sin
   tocar código. El permiso anterior (Directivo podía entrenar) queda COMENTADO abajo
   por trazabilidad, no eliminado.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-5 / COM-5 v4 (solo trazabilidad; los nombres obedecen a la funcionalidad).
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
# ENTRENAMIENTO DEL MODELO
# ==========================================
@router.post("/entrenar")
def entrenar_modelo(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Entrena el modelo K-means (k=4) con las recetas aptas tras aplicar las reglas
    R1 (proteína permitida, configurable), R2 (veto res/cerdo, configurable) y
    R3 (sin precio alto); etiqueta centroides y persiste el modelo activo.
    COM-5 v4: exclusivo Admin de Sistemas.
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
    """Metadatos del modelo activo (métricas, centroides) + agregado por cluster."""
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
    """Recetas asignadas al modelo activo con su snapshot de features por ración."""
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
    """Recalcula el dataset con los parámetros vigentes sin persistir (auditoría R1-R3)."""
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