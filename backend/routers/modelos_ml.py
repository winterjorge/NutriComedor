"""
routers/modelos_ml.py
Objetivo: Endpoints del PANEL DE GRÁFICOS DE MACHINE LEARNING (COM-5 v4 / COM-8 v7),
exclusivo del Administrador de Sistemas (módulo 'modelos_ml').
COM-92: el endpoint /random-forest ahora acepta parámetro `modelo` para elegir
entre Random Forest ('rf') y Gradient Boosting ('gbm').
Historial:
COM-5 v4 / COM-8 v7: versión original.
COM-60: scatter K-means con 6 variables nutricionales.
COM-92 (este archivo): selector de modelo RF vs GBM en endpoint random-forest.
"""
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler
from database import get_db
from permisos import es_admin_sistema
from ml.kmeans_recetas import obtener_modelo_activo, FEATURES
from ml.random_forest_demanda import entrenar_y_evaluar_rf, _cargar_historia_demanda

router = APIRouter(prefix="/modelos-ml", tags=["Modelos ML"])


def _validar_admin(cur, usuario_id: int) -> None:
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: el panel de Modelos ML es exclusivo del Administrador de Sistemas.")


@router.get("/estado")
def estado_modelos(usuario_solicitante_id: int, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
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
        try:
            historia = _cargar_historia_demanda(cur)
            rf = {'dias_historial': len(historia), 'suficiente': len(historia) >= 30}
        except ValueError as ve:
            rf = {'dias_historial': 0, 'suficiente': False, 'detalle': str(ve)}
        return {'kmeans': kmeans, 'greedy': greedy, 'random_forest': rf}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar estado de modelos: {e}")
    finally:
        cur.close()


# COM-92: endpoint con selector de modelo
@router.get("/random-forest")
def grafico_random_forest(
    usuario_solicitante_id: int,
    modelo: str = Query('rf', description="Modelo a usar: 'rf' (Random Forest) o 'gbm' (Gradient Boosting)"),
    db=Depends(get_db)
):
    """
    COM-92: entrena el modelo seleccionado (RF o GBM) y devuelve métricas,
    puntos de dispersión e importancias de variables.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        return entrenar_y_evaluar_rf(cur, modelo_key=modelo)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al entrenar modelo: {e}")
    finally:
        cur.close()


@router.get("/kmeans-scatter")
def grafico_kmeans(usuario_solicitante_id: int, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        modelo = obtener_modelo_activo(cur)
        if not modelo:
            raise HTTPException(status_code=404, detail="No hay modelo K-means activo.")
        cur.execute("""
            SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
                   rc.energia_kcal, rc.hierro_mg, rc.proteina_g,
                   rc.vitamina_a_ug, rc.zinc_mg, rc.carbohidratos_g,
                   rc.precio_soles,
                   r.nombre
            FROM recetas_clusters rc
            JOIN recetas_almuerzo r ON r.id = rc.receta_id
            WHERE rc.modelo_id = %s
            ORDER BY rc.cluster_codigo, rc.precio_soles;
        """, (modelo['id'],))
        filas = cur.fetchall()
        if len(filas) < 3:
            raise HTTPException(status_code=400, detail="Muy pocas recetas en el modelo activo para proyectar (mínimo 3).")
        X = np.array([[float(f[c] or 0.0) for c in FEATURES] for f in filas])
        scaler = RobustScaler()
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
                'vitamina_a_ug': float(f['vitamina_a_ug']),
                'zinc_mg': float(f['zinc_mg']),
                'carbohidratos_g': float(f['carbohidratos_g']),
                'precio_soles': float(f['precio_soles']),
            })
        centroides = []
        for codigo, c in (modelo['centroides'] or {}).items():
            v = [[float(c.get(feat, 0.0) or 0.0) for feat in FEATURES]]
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


@router.get("/greedy")
def grafico_greedy(usuario_solicitante_id: int, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("""
            SELECT sesion_id FROM planificaciones_candidatas
            ORDER BY fecha DESC LIMIT 1;
        """)
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Aún no hay sesiones del motor greedy. Genere propuestas desde la vista correspondiente.")
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
                    'dias_anti_anemia': resumen.get('dias_anti_anemia'),
                    'cuota_anti_anemia': resumen.get('cuota_anti_anemia'),
                    'cumple_cuota_anemia': resumen.get('cumple_cuota_anemia'),
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
                        'es_anti_anemia': d.get('es_anti_anemia', False),
                        'fe_por_sol': d.get('fe_por_sol'),
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
            'variables_cuota': ['dias_anti_anemia', 'cuota_anti_anemia', 'cumple_cuota_anemia'],
            'variantes': variantes,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener los datos del greedy: {e}")
    finally:
        cur.close()