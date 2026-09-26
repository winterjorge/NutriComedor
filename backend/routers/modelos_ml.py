"""
routers/modelos_ml.py
Objetivo: Endpoints del PANEL DE GRÁFICOS DE MACHINE LEARNING (COM-5 v4 / COM-8 v7),
          exclusivo del Administrador de Sistemas (módulo 'modelos_ml'):
          - GET /modelos-ml/estado: disponibilidad de cada modelo sin entrenar nada.
          - GET /modelos-ml/random-forest: dispersión REAL vs PREDICHO de la demanda
            diaria por tipo de comensal (Random Forest), con métricas R²/MAE y la
            relevancia (feature importances) de cada variable del modelo.
          - GET /modelos-ml/kmeans-scatter: dispersión PCA-2D de las recetas del modelo
            K-means activo, coloreada por cluster, con centroides proyectados, varianza
            explicada por componente y las cargas de cada variable en PC1/PC2.
          - GET /modelos-ml/greedy: serie diaria y totales por variante de la última
            sesión del motor Greedy Search (costo, recolección, margen, kcal, hierro).
          Todos los payloads incluyen explícitamente las VARIABLES/INDICADORES que el
          frontend debe rotular en ejes y leyendas (requerimiento del ticket).
Uso: Registrado en main.py con prefijo /api/v1.
Permisos: TODOS los endpoints exigen es_admin_sistema (módulo 'modelos_ml' sembrado
          en esquema_modelos_ml.py únicamente para el rol Administrador de Sistemas).
Referencia: tickets COM-5 v4 / COM-8 v7 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from database import get_db
from permisos import es_admin_sistema
from ml.kmeans_recetas import obtener_modelo_activo, FEATURES
from ml.random_forest_demanda import entrenar_y_evaluar_rf, _cargar_historia_demanda

router = APIRouter(prefix="/modelos-ml", tags=["Modelos ML"])


# ==========================================
# HELPERS DE PERMISO
# ==========================================
def _validar_admin(cur, usuario_id: int) -> None:
    """COM-5 v4: el panel de Modelos ML es exclusivo del Administrador de Sistemas."""
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: el panel de Modelos ML es exclusivo del Administrador de Sistemas.")


# ==========================================
# ESTADO / DISPONIBILIDAD DE MODELOS
# ==========================================
@router.get("/estado")
def estado_modelos(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Disponibilidad de cada modelo para el encabezado del panel (sin entrenar):
    K-means activo, última sesión greedy y días de historial para Random Forest.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)

        # --- K-means ---
        modelo = obtener_modelo_activo(cur)
        kmeans = None
        if modelo:
            kmeans = {
                'modelo_id': modelo['id'],
                'k': modelo['k'],
                'n_recetas': modelo['n_recetas'],
                'silhouette': modelo['silhouette'],
                'inercia': modelo['inercia'],
                'fecha_entrenamiento': modelo['fecha_entrenamiento'],
            }

        # --- Greedy Search: última sesión generada ---
        cur.execute("""
            SELECT sesion_id, MAX(fecha) AS fecha, COUNT(*) AS n_propuestas
            FROM planificaciones_candidatas
            GROUP BY sesion_id
            ORDER BY MAX(fecha) DESC
            LIMIT 1;
        """)
        g = cur.fetchone()
        greedy = {
            'sesion_id': g['sesion_id'],
            'fecha': g['fecha'],
            'n_propuestas': g['n_propuestas'],
        } if g else None

        # --- Random Forest: días de historial disponibles (sin entrenar) ---
        try:
            historia = _cargar_historia_demanda(cur)
            rf = {'dias_historial': len(historia), 'suficiente': len(historia) >= 30}
        except ValueError as ve:
            rf = {'dias_historial': 0, 'suficiente': False, 'detalle': str(ve)}

        return {'kmeans': kmeans, 'greedy': greedy, 'random_forest': rf}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar el estado de modelos: {e}")
    finally:
        cur.close()


# ==========================================
# GRÁFICO 1: DISPERSIÓN RANDOM FOREST (REAL vs PREDICHO)
# ==========================================
@router.get("/random-forest")
def grafico_random_forest(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Entrena Random Forest bajo demanda con split temporal 80/20 y devuelve los puntos
    de dispersión (real vs predicho) por tipo de comensal, más métricas R²/MAE y la
    importancia de cada variable (dia_semana, mes, dia_del_mes, es_fin_de_semana).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        return entrenar_y_evaluar_rf(cur)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al entrenar Random Forest: {e}")
    finally:
        cur.close()


# ==========================================
# GRÁFICO 2: DISPERSIÓN PCA-2D DEL K-MEANS
# ==========================================
@router.get("/kmeans-scatter")
def grafico_kmeans(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Proyecta las 4 variables del modelo K-means activo (energia_kcal, hierro_mg,
    proteina_g, precio_soles) a 2 componentes principales y devuelve:
      - puntos por receta con su cluster (para colorear la dispersión),
      - centroides de cada cluster proyectados en el mismo espacio,
      - varianza explicada por PC1/PC2 y cargas de cada variable en ambos ejes
        (indicadores que el gráfico debe mostrar en ejes/leyenda).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        modelo = obtener_modelo_activo(cur)
        if not modelo:
            raise HTTPException(status_code=404,
                            detail="No hay modelo K-means activo. Entrene desde la vista de Clusters.")

        cur.execute("""
            SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
                   rc.energia_kcal, rc.hierro_mg, rc.proteina_g, rc.precio_soles,
                   r.nombre
            FROM recetas_clusters rc
            JOIN recetas_almuerzo r ON r.id = rc.receta_id
            WHERE rc.modelo_id = %s
            ORDER BY rc.cluster_codigo, rc.precio_soles;
        """, (modelo['id'],))
        filas = cur.fetchall()
        if len(filas) < 3:
            raise HTTPException(status_code=400,
                            detail="Muy pocas recetas en el modelo activo para proyectar (mínimo 3).")

        X = np.array([[float(f['energia_kcal']), float(f['hierro_mg']),
                       float(f['proteina_g']), float(f['precio_soles'])] for f in filas])
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)
        pca = PCA(n_components=2, random_state=42)
        P = pca.fit_transform(Xs)

        puntos = []
        for f, xy in zip(filas, P):
            puntos.append({
                'receta_id': f['receta_id'],
                'nombre': f['nombre'],
                'cluster_codigo': f['cluster_codigo'],
                'cluster_etiqueta': f['cluster_etiqueta'],
                'x': round(float(xy[0]), 4),
                'y': round(float(xy[1]), 4),
                'energia_kcal': float(f['energia_kcal']),
                'hierro_mg': float(f['hierro_mg']),
                'proteina_g': float(f['proteina_g']),
                'precio_soles': float(f['precio_soles']),
            })

        # Centroides crudos guardados en el modelo -> mismo espacio PCA
        centroides = []
        for codigo, c in (modelo['centroides'] or {}).items():
            v = [[float(c['energia_kcal']), float(c['hierro_mg']),
                  float(c['proteina_g']), float(c['precio_soles'])]]
            xy = pca.transform(scaler.transform(v))[0]
            centroides.append({
                'cluster_codigo': int(codigo),
                'cluster_etiqueta': (modelo['etiquetas'] or {}).get(str(codigo)),
                'x': round(float(xy[0]), 4),
                'y': round(float(xy[1]), 4),
            })

        cargas = [
            {'variable': FEATURES[j],
             'pc1': round(float(pca.components_[0][j]), 4),
             'pc2': round(float(pca.components_[1][j]), 4)}
            for j in range(len(FEATURES))
        ]

        return {
            'modelo_id': modelo['id'],
            'fecha_entrenamiento': modelo['fecha_entrenamiento'],
            'silhouette': modelo['silhouette'],
            'inercia': modelo['inercia'],
            'variables': FEATURES,
            'varianza_explicada': {
                'pc1': round(float(pca.explained_variance_ratio_[0]), 4),
                'pc2': round(float(pca.explained_variance_ratio_[1]), 4),
            },
            'cargas': cargas,
            'puntos': puntos,
            'centroides': centroides,
            'etiquetas_clusters': modelo['etiquetas'],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al proyectar el K-means: {e}")
    finally:
        cur.close()


# ==========================================
# GRÁFICO 3: GREEDY SEARCH (serie diaria + totales por variante)
# ==========================================
@router.get("/greedy")
def grafico_greedy(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    Última sesión del motor Greedy Search: por cada variante (NutriMax/EconoMax/
    BalanceMax) devuelve los totales (costo, recolección, margen, kcal/día, hierro/día)
    para el gráfico de barras y la serie diaria (costo del día, recolección del día,
    kcal, hierro, proteína) para el gráfico de líneas. Incluye los nombres de las
    variables/indicadores que el frontend debe rotular.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT sesion_id FROM planificaciones_candidatas
            ORDER BY fecha DESC LIMIT 1;
        """)
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404,
                            detail="Aún no hay sesiones del motor greedy. Genere propuestas desde la vista correspondiente.")

        cur.execute("""
            SELECT variante, etiqueta, descripcion, resumen, menu, estado, fecha
            FROM planificaciones_candidatas
            WHERE sesion_id = %s
            ORDER BY id;
        """, (row['sesion_id'],))
        filas = cur.fetchall()

        variantes = []
        for f in filas:
            menu = f['menu'] if isinstance(f['menu'], list) else (f['menu'] or [])
            resumen = f['resumen'] if isinstance(f['resumen'], dict) else (f['resumen'] or {})
            variantes.append({
                'variante': f['variante'],
                'etiqueta': f['etiqueta'],
                'descripcion': f['descripcion'],
                'estado': f['estado'],
                'totales': {
                    'costo_total_semana': resumen.get('costo_total_semana'),
                    'recoleccion_total_semana': resumen.get('recoleccion_total_semana'),
                    'margen_proyectado': resumen.get('margen_proyectado'),
                    'calorias_promedio_dia': resumen.get('calorias_promedio_dia'),
                    'hierro_promedio_dia': resumen.get('hierro_promedio_dia'),
                    'proteina_promedio_dia': resumen.get('proteina_promedio_dia'),
                },
                'serie_diaria': [
                    {
                        'dia_nombre': d.get('dia_nombre'),
                        'fecha': d.get('fecha'),
                        'costo_total_dia': d.get('costo_total_dia'),
                        'recoleccion_proyectada': d.get('recoleccion_proyectada'),
                        'energia_kcal': d.get('energia_kcal'),
                        'hierro_mg': d.get('hierro_mg'),
                        'proteina_g': d.get('proteina_g'),
                    } for d in menu
                ],
            })

        return {
            'sesion_id': row['sesion_id'],
            'fecha_generacion': filas[0]['fecha'] if filas else None,
            'variables_totales': ['costo_total_semana', 'recoleccion_total_semana',
                                  'margen_proyectado', 'calorias_promedio_dia',
                                  'hierro_promedio_dia', 'proteina_promedio_dia'],
            'variables_serie': ['costo_total_dia', 'recoleccion_proyectada',
                                'energia_kcal', 'hierro_mg', 'proteina_g'],
            'variantes': variantes,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener los datos del greedy: {e}")
    finally:
        cur.close()