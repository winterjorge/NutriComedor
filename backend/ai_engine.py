"""
ai_engine.py
Objetivo: Motor de Machine Learning para predicción de demanda de comensales.
Uso: Importar desde routers de FastAPI para predecir comensales por tipo.
"""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime, timedelta

# ==========================================
# DATOS DE ENTRENAMIENTO (Simulación de 2 años)
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

X_train, y_train = _generar_datos_entrenamiento()

rf_regressor = RandomForestRegressor(
    n_estimators=100, max_depth=5, min_samples_split=10, 
    min_samples_leaf=5, random_state=42, n_jobs=-1
)
rf_regressor.fit(X_train, y_train)

# ==========================================
# PREDICCIÓN (Modular y Parametrizable)
# ==========================================
def predecir_demanda_raciones(dia_semana: int, dia_mes: int, limites_minimos: dict = None, limites_finde: dict = None):
    """
    Predice la cantidad de comensales por tipo para una fecha específica.
    Ahora acepta diccionarios de configuración para umbrales mínimos y fines de semana.
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
        
        prediccion = rf_regressor.predict([[dia_semana, dia_mes]])[0]
        
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