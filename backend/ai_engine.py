"""
ai_engine.py
Objetivo: Motor de Machine Learning para predicción de demanda de comensales.
          COM-64: entrena Random Forest con datos REALES de padron_diario cuando
          existen ≥30 días de historial; fallback a datos simulados si no hay
          suficientes datos reales.
Uso: Importar desde routers de FastAPI para predecir comensales por tipo.
Historial:
 - Sprint 1/2: versión original con datos simulados hardcodeados.
 - COM-64 (este archivo): entrenamiento con datos reales de padron_diario.
"""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta
from collections import defaultdict

# ==========================================
# DATOS DE ENTRENAMIENTO SIMULADOS (fallback)
# ==========================================
def _generar_datos_entrenamiento():
    """Genera datos de entrenamiento simulados basados en patrones reales"""
    X = []
    y = []
    for semana in range(104):
        for dia_semana in range(5):  # Solo lunes a viernes
            dia_mes = ((semana * 7) + dia_semana) % 31 + 1
            if dia_semana == 0: base_social, base_afiliado, base_normal = 22, 43, 110
            elif dia_semana == 1: base_social, base_afiliado, base_normal = 21, 44, 115
            elif dia_semana == 2: base_social, base_afiliado, base_normal = 20, 45, 120
            elif dia_semana == 3: base_social, base_afiliado, base_normal = 21, 44, 118
            else: base_social, base_afiliado, base_normal = 23, 42, 105
            if dia_mes <= 5: factor = 0.95
            elif 10 <= dia_mes <= 20: factor = 1.05
            elif dia_mes >= 25: factor = 1.15
            else: factor = 1.0
            np.random.seed(semana * 5 + dia_semana)
            variacion = np.random.uniform(0.9, 1.1)
            social = int(base_social * factor * variacion)
            afiliado = int(base_afiliado * factor * variacion)
            normal = int(base_normal * factor * variacion)
            X.append([dia_semana, dia_mes])
            y.append([social, afiliado, normal])
    return np.array(X), np.array(y)

X_train_sim, y_train_sim = _generar_datos_entrenamiento()
rf_regressor_simulado = RandomForestRegressor(
    n_estimators=100, max_depth=5, min_samples_split=10,
    min_samples_leaf=5, random_state=42, n_jobs=-1
)
rf_regressor_simulado.fit(X_train_sim, y_train_sim)


# ==========================================
# COM-64: CARGA DE DATOS REALES DESDE padron_diario
# ==========================================
def _cargar_datos_reales(cur):
    """
    COM-64: extrae datos reales de padron_diario agrupados por fecha y tipo.
    Retorna (X, y, n_dias_unicos) o (None, None, 0) si no hay suficientes datos.
    Excluye el tipo 'Cocinera' (es fijo: 20 diarios, no se predice).
    """
    cur.execute("""
        SELECT fecha, tipo_comensal_venta, SUM(raciones) as total
        FROM padron_diario
        WHERE tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal')
        GROUP BY fecha, tipo_comensal_venta
        ORDER BY fecha;
    """)
    rows = cur.fetchall()
    if not rows:
        return None, None, 0
    
    # Pivotar: una fila por fecha con columnas social, afiliado, normal
    datos_por_fecha = defaultdict(lambda: {'Social': 0, 'Afiliado': 0, 'Normal': 0})
    for r in rows:
        datos_por_fecha[r['fecha']][r['tipo_comensal_venta']] = int(r['total'])
    
    X = []
    y = []
    for fecha, tipos in datos_por_fecha.items():
        dia_semana = fecha.weekday()  # 0=Lunes, 6=Domingo
        dia_mes = fecha.day
        X.append([dia_semana, dia_mes])
        y.append([tipos['Social'], tipos['Afiliado'], tipos['Normal']])
    
    return np.array(X), np.array(y), len(datos_por_fecha)


def _entrenar_con_datos_reales(cur):
    """
    COM-64: entrena un RF con datos reales si hay ≥30 días de historial.
    Retorna el modelo entrenado o None si no hay suficientes datos.
    """
    try:
        X_real, y_real, n_dias = _cargar_datos_reales(cur)
        if X_real is None or n_dias < 30:
            return None
        modelo = RandomForestRegressor(
            n_estimators=100, max_depth=5, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        modelo.fit(X_real, y_real)
        return modelo
    except Exception as e:
        print(f"[AI_ENGINE] Error al entrenar con datos reales: {e}")
        return None


# ==========================================
# PREDICCIÓN (Modular y Parametrizable)
# ==========================================
def predecir_demanda_raciones(dia_semana: int, dia_mes: int, 
                               limites_minimos: dict = None, 
                               limites_finde: dict = None,
                               cur=None):
    """
    COM-64: predice la cantidad de comensales por tipo para una fecha específica.
    - Si cur es proporcionado y hay ≥30 días de datos reales, usa RF entrenado con datos reales.
    - Si no, usa el modelo simulado (fallback).
    - Fines de semana usan los límites configurables directamente.
    """
    # Fallback por si se llama sin parámetros (ej. en tests unitarios)
    limites_minimos = limites_minimos or {'SOCIAL': 15, 'AFILIADO': 35, 'NORMAL': 80}
    limites_finde = limites_finde or {'SOCIAL': 10, 'AFILIADO': 20, 'NORMAL': 30}
    
    try:
        if not (0 <= dia_semana <= 6):
            raise ValueError(f"dia_semana debe estar entre 0 y 6, recibido: {dia_semana}")
        if not (1 <= dia_mes <= 31):
            raise ValueError(f"dia_mes debe estar entre 1 y 31, recibido: {dia_mes}")
        
        # Si es fin de semana, retornar valores base configurables
        if dia_semana >= 5:
            return [
                limites_finde['SOCIAL'], 
                limites_finde['AFILIADO'], 
                limites_finde['NORMAL']
            ]
        
        # COM-64: seleccionar modelo (real si hay datos, simulado si no)
        modelo = rf_regressor_simulado  # default
        if cur is not None:
            modelo_real = _entrenar_con_datos_reales(cur)
            if modelo_real is not None:
                modelo = modelo_real
        
        prediccion = modelo.predict([[dia_semana, dia_mes]])[0]
        
        # Aplicar mínimos configurables desde la BD
        social = max(limites_minimos['SOCIAL'], int(round(prediccion[0])))
        afiliado = max(limites_minimos['AFILIADO'], int(round(prediccion[1])))
        normal = max(limites_minimos['NORMAL'], int(round(prediccion[2])))
        
        return [social, afiliado, normal]
    except Exception as e:
        print(f"Error en predicción de demanda: {e}")
        # Fallback de emergencia usando los mínimos configurados
        return [
            limites_minimos['SOCIAL'], 
            limites_minimos['AFILIADO'], 
            limites_minimos['NORMAL']
        ]