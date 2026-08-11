"""
optimizador.py
Objetivo: Motor de cálculo de costos de recetas con predicción de precios basada en histórico.
Uso: Importar desde routers de FastAPI para calcular costos dinámicos de recetas en cualquier fecha.
Nota: Utiliza Random Forest para predicción de precios (consistente con ai_engine.py)
"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import math

DB_URL = os.getenv("DATABASE_URL", "postgresql://nutri_admin:Nutri2026Secure!@db:5432/nutricomedor")

def redondear_hacia_arriba_010(valor):
    """Redondea hacia arriba al múltiplo de 0.10 más cercano."""
    if valor <= 0:
        return 0.0
    return math.ceil(valor * 10) / 10

def evaluar_mejor_insumo(opciones_insumos, peso_estimado_g):
    """Selecciona el mejor insumo y calcula el costo redondeado."""
    mejor_opcion = None
    menor_costo_real = float('inf')
    
    for insumo in opciones_insumos:
        precio_kg = float(insumo['precio_prom'])
        precio_por_gramo = precio_kg / 1000.0
        costo_sin_redondear = precio_por_gramo * peso_estimado_g
        costo_redondeado = redondear_hacia_arriba_010(costo_sin_redondear)
        
        insumo['costo_calculado'] = costo_redondeado
        insumo['costo_sin_redondear'] = costo_sin_redondear
        
        if costo_redondeado < menor_costo_real:
            menor_costo_real = costo_redondeado
            mejor_opcion = insumo
    
    return mejor_opcion

def predecir_precio_con_confianza(insumo_id, fecha_objetivo, conn, cur):
    """
    Predice el precio usando Random Forest con R².
    Busca hasta 90 días de histórico para tener mejor base de predicción.
    """
    # Buscar hasta 90 días de histórico para mejor predicción
    cur.execute("""
        SELECT fecha, precio_prom
        FROM historial_precios
        WHERE insumo_id = %s
        AND fecha >= %s
        AND fecha < %s
        AND precio_prom IS NOT NULL
        ORDER BY fecha ASC
    """, (insumo_id, fecha_objetivo - timedelta(days=90), fecha_objetivo))
    registros = cur.fetchall()
    
    # Necesitamos al menos 5 registros para Random Forest
    if len(registros) < 5:
        return None, 0, False
    
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import r2_score
        
        X = np.array([[i] for i in range(len(registros))])
        y = np.array([float(r['precio_prom']) for r in registros])
        
        # Random Forest con parámetros ajustados para series de precios
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=5,
            min_samples_split=3,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X, y)
        
        y_pred = model.predict(X)
        r2 = r2_score(y, y_pred)
        confianza = max(0, r2 * 100)
        
        dias_desde_ultimo = len(registros)
        precio_predicho = model.predict([[dias_desde_ultimo]])[0]
        precio_predicho = max(0.01, precio_predicho)
        
        return round(precio_predicho, 2), round(confianza, 1), True
    except ImportError:
        # Fallback: usar promedio si no hay sklearn
        precio_promedio = sum(float(r['precio_prom']) for r in registros) / len(registros)
        return round(precio_promedio, 2), 50.0, True

def calcular_costo_receta(receta_id: int, fecha_evaluacion: str):
    """
    Calcula el costo real de una receta considerando:
    1. La unidad de medida de cada ingrediente
    2. El número de raciones que produce la receta
    Retorna el costo POR RACIÓN
    """
    conn = None
    cur = None
    
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Obtener número de raciones de la receta
        cur.execute("""
            SELECT raciones FROM recetas_almuerzo WHERE id = %s
        """, (receta_id,))
        receta_info = cur.fetchone()
        
        if not receta_info:
            return {"error": "La receta no existe"}
        
        raciones_receta = receta_info['raciones'] if receta_info['raciones'] and receta_info['raciones'] > 0 else 1
        
        # Extraer ingredientes con la UNIDAD DE MEDIDA DE LA RECETA
        cur.execute("""
            SELECT 
                ri.id as receta_ingrediente_id,
                ri.ingrediente_id,
                i.nombre as ingrediente_nombre,
                COALESCE(i.peso_estimado_g, 100.0) as peso_estimado_g,
                ri.cantidad_requerida,
                ri.unidad_medida_id as receta_unidad_medida_id,
                um_receta.nombre as receta_unidad_nombre,
                um_receta.abreviatura as receta_unidad_abrev,
                um_receta.factor_a_base as receta_factor_a_base,
                cat.nombre as categoria_nombre
            FROM receta_ingrediente ri
            JOIN ingredientes i ON ri.ingrediente_id = i.id
            JOIN unidades_medida um_receta ON ri.unidad_medida_id = um_receta.id
            LEFT JOIN categorias_alimentos cat ON i.categoria_id = cat.id
            WHERE ri.receta_id = %s
            ORDER BY ri.id;
        """, (receta_id,))
        
        ingredientes_receta = cur.fetchall()
        
        if not ingredientes_receta:
            return {"error": "La receta no tiene ingredientes asignados"}
        
        costo_total_receta = 0.0
        detalle_costos = []
        fecha_objetivo = datetime.strptime(fecha_evaluacion, "%Y-%m-%d").date()
        
        for req in ingredientes_receta:
            categoria = req['categoria_nombre'] or ''
            unidad_abrev = (req['receta_unidad_abrev'] or '').lower()
            unidad_nombre = req['receta_unidad_nombre'] or ''
            cantidad_requerida = float(req['cantidad_requerida'])
            factor_receta = float(req['receta_factor_a_base'])
            peso_estimado_base = float(req['peso_estimado_g'])
            
            # Determinar peso total en gramos según la unidad de la receta
            if unidad_abrev in ['und', 'unidad', 'u']:
                peso_total_g = cantidad_requerida * peso_estimado_base
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()} ({peso_total_g}g)"
            elif unidad_abrev in ['kg', 'kilogramo']:
                peso_total_g = cantidad_requerida * 1000
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['g', 'gramo']:
                peso_total_g = cantidad_requerida
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['l', 'litro']:
                peso_total_g = cantidad_requerida * 1000
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['ml', 'mililitro']:
                peso_total_g = cantidad_requerida
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['tz', 'taza']:
                peso_total_g = cantidad_requerida * factor_receta
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['cda', 'cucharada']:
                peso_total_g = cantidad_requerida * factor_receta
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['cdta', 'cucharadita']:
                peso_total_g = cantidad_requerida * factor_receta
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['pz', 'pizca']:
                peso_total_g = cantidad_requerida * factor_receta
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['dte', 'diente']:
                peso_total_g = cantidad_requerida * peso_estimado_base
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['rma', 'rama']:
                peso_total_g = cantidad_requerida * peso_estimado_base
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['atd', 'atado']:
                peso_total_g = cantidad_requerida * 100
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['rdj', 'rodaja']:
                peso_total_g = cantidad_requerida * 20
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            else:
                peso_total_g = cantidad_requerida * factor_receta
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            
            # Buscar insumos disponibles para esta fecha
            cur.execute("""
                SELECT 
                    ins.id as insumo_id,
                    ins.nombre as insumo_nombre,
                    ins.ingrediente_id,
                    hp.precio_prom,
                    hp.fecha,
                    um.factor_a_base as factor_insumo
                FROM insumos ins
                LEFT JOIN historial_precios hp ON hp.insumo_id = ins.id AND hp.fecha = %s
                JOIN unidades_medida um ON ins.unidad_medida_id = um.id
                WHERE ins.ingrediente_id = %s
            """, (fecha_evaluacion, req['ingrediente_id']))
            
            opciones = cur.fetchall()
            
            if not opciones:
                # No hay insumos registrados para este ingrediente
                cur.execute("""
                    SELECT ins.id, ins.nombre, ins.ingrediente_id, um.factor_a_base
                    FROM insumos ins
                    JOIN unidades_medida um ON ins.unidad_medida_id = um.id
                    WHERE ins.ingrediente_id = %s
                    LIMIT 1
                """, (req['ingrediente_id'],))
                insumo_base = cur.fetchone()
                
                if insumo_base:
                    # Intentar predecir SIEMPRE, no solo para fechas futuras
                    precio_predicho, confianza, es_prediccion = predecir_precio_con_confianza(
                        insumo_base['id'], fecha_objetivo, conn, cur
                    )
                    
                    if precio_predicho:
                        costo_sin_redondear = (precio_predicho / 1000.0) * peso_total_g
                        costo_ingrediente = redondear_hacia_arriba_010(costo_sin_redondear)
                        costo_total_receta += costo_ingrediente
                        
                        detalle_costos.append({
                            "ingrediente": req['ingrediente_nombre'],
                            "insumo_comprado": f"{insumo_base['nombre']} (PREDICHO {confianza}%)",
                            "cantidad_usada": unidad_display,
                            "costo_parcial": round(costo_ingrediente, 2),
                            "peso_usado_g": peso_total_g,
                            "es_prediccion": True,
                            "confianza_prediccion": f"{confianza}%"
                        })
                        continue
                
                # Si no se pudo predecir
                detalle_costos.append({
                    "ingrediente": req['ingrediente_nombre'],
                    "insumo_comprado": "Sin insumo disponible",
                    "cantidad_usada": unidad_display,
                    "costo_parcial": 0.0,
                    "peso_usado_g": peso_total_g,
                    "error": "Sin insumos disponibles",
                    "es_prediccion": False
                })
                continue
            
            # Hay insumos, verificar si tienen precio
            opciones_con_precio = [o for o in opciones if o['precio_prom'] is not None]
            
            if not opciones_con_precio:
                # No hay precios para esta fecha, intentar predecir
                primera_opcion = opciones[0]
                precio_predicho, confianza, es_prediccion = predecir_precio_con_confianza(
                    primera_opcion['insumo_id'], fecha_objetivo, conn, cur
                )
                
                if precio_predicho:
                    costo_sin_redondear = (precio_predicho / 1000.0) * peso_total_g
                    costo_ingrediente = redondear_hacia_arriba_010(costo_sin_redondear)
                    costo_total_receta += costo_ingrediente
                    
                    detalle_costos.append({
                        "ingrediente": req['ingrediente_nombre'],
                        "insumo_comprado": f"{primera_opcion['insumo_nombre']} (PREDICHO {confianza}%)",
                        "cantidad_usada": unidad_display,
                        "costo_parcial": round(costo_ingrediente, 2),
                        "peso_usado_g": peso_total_g,
                        "es_prediccion": True,
                        "confianza_prediccion": f"{confianza}%"
                    })
                    continue
                
                # Si no se pudo predecir
                detalle_costos.append({
                    "ingrediente": req['ingrediente_nombre'],
                    "insumo_comprado": "Sin precios disponibles",
                    "cantidad_usada": unidad_display,
                    "costo_parcial": 0.0,
                    "peso_usado_g": peso_total_g,
                    "error": "Sin precios para esta fecha",
                    "es_prediccion": False
                })
                continue
            
            # Hay precios disponibles, usar el mejor
            mejor_insumo = evaluar_mejor_insumo(opciones_con_precio, peso_total_g)
            costo_ingrediente = mejor_insumo.get('costo_calculado', 0.0)
            costo_total_receta += costo_ingrediente
            
            detalle_costos.append({
                "ingrediente": req['ingrediente_nombre'],
                "insumo_comprado": mejor_insumo['insumo_nombre'],
                "cantidad_usada": unidad_display,
                "costo_parcial": round(costo_ingrediente, 2),
                "peso_usado_g": peso_total_g,
                "es_prediccion": False
            })
        
        # CALCULAR COSTO POR RACIÓN (dividir costo total entre número de raciones)
        costo_por_racion = costo_total_receta / raciones_receta
        
        return {
            "receta_id": receta_id,
            "fecha_calculo": fecha_evaluacion,
            "raciones_receta": raciones_receta,
            "costo_total_receta": round(costo_total_receta, 2),
            "costo_total_racion": round(costo_por_racion, 2),
            "detalle_insumos": detalle_costos,
            "total_ingredientes": len(detalle_costos),
            "ingredientes_con_precio": sum(1 for d in detalle_costos if d['costo_parcial'] > 0),
            "ingredientes_sin_precio": sum(1 for d in detalle_costos if d['costo_parcial'] == 0),
            "ingredientes_predichos": sum(1 for d in detalle_costos if d.get('es_prediccion', False))
        }
        
    except Exception as e:
        print(f"Error en el motor de optimización: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        if cur: cur.close()
        if conn: conn.close()