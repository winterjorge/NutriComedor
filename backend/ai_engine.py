"""
ai_engine.py
Objetivo: Motor de Machine Learning para predicción de demanda de comensales.
          COM-64: entrena Random Forest con datos REALES de padron_diario cuando
          existen ≥30 días de historial; fallback a datos simulados si no hay
          suficientes datos reales.
Uso: Importar desde routers de FastAPI para predecir comensales por tipo.
Historial:
 - Sprint 1/2: versión original con datos simulados hardcodeados.
 - COM-64 v1: entrenamiento con datos reales de padron_diario.
 - COM-64 v2 (este archivo): FIX del fallback de fin de semana que ignoraba el
   modelo ML. Ahora el modelo se entrena con TODOS los datos (incluyendo fines
   de semana si existen) y se usa para predecir cualquier día. El fallback de
   fin de semana solo aplica si NO hay modelo entrenado.
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
        for dia_semana in range(7):  # COM-64 v2: todos los días (0=Lunes a 6=Domingo)
            dia_mes = ((semana * 7) + dia_semana) % 31 + 1
            # Patrones base por día de semana
            if dia_semana == 0: base_social, base_afiliado, base_normal = 22, 43, 110
            elif dia_semana == 1: base_social, base_afiliado, base_normal = 21, 44, 115
            elif dia_semana == 2: base_social, base_afiliado, base_normal = 20, 45, 120
            elif dia_semana == 3: base_social, base_afiliado, base_normal = 21, 44, 118
            elif dia_semana == 4: base_social, base_afiliado, base_normal = 23, 42, 105
            else: base_social, base_afiliado, base_normal = 8, 15, 25  # Fin de semana
            # Factor por día del mes
            if dia_mes <= 5: factor = 0.95
            elif 10 <= dia_mes <= 20: factor = 1.05
            elif dia_mes >= 25: factor = 1.15
            else: factor = 1.0
            np.random.seed(semana * 7 + dia_semana)
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
# COM-64 v2: CARGA DE DATOS REALES DESDE padron_diario
# ==========================================
def _cargar_datos_reales(cur):
    """
    COM-64 v2: extrae datos reales de padron_diario agrupados por fecha y tipo.
    Retorna (X, y, n_dias_unicos) o (None, None, 0) si no hay suficientes datos.
    Excluye el tipo 'Cocinera' (es fijo: 20 diarios, no se predice).
    Incluye TODOS los días (lunes a domingo) para que el modelo pueda predecir
    cualquier día de la semana.
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
    COM-64 v2: entrena un RF con datos reales si hay ≥30 días de historial.
    Retorna el modelo entrenado o None si no hay suficientes datos.
    """
    try:
        X_real, y_real, n_dias = _cargar_datos_reales(cur)
        if X_real is None or n_dias < 30:
            print(f"[AI_ENGINE] No hay suficientes datos reales ({n_dias} días). Usando modelo simulado.")
            return None
        print(f"[AI_ENGINE] Entrenando modelo con {n_dias} días de datos reales...")
        modelo = RandomForestRegressor(
            n_estimators=100, max_depth=5, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        modelo.fit(X_real, y_real)
        # Calcular score R² para auditoría
        score = modelo.score(X_real, y_real)
        print(f"[AI_ENGINE] Modelo entrenado exitosamente. R² = {score:.3f}")
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
    COM-64 v2: predice la cantidad de comensales por tipo para una fecha específica.
    - Si cur es proporcionado y hay ≥30 días de datos reales, usa RF entrenado con
      datos reales (para CUALQUIER día de la semana, incluyendo fines de semana).
    - Si no hay modelo real, usa el modelo simulado (fallback).
    - Los mínimos configurables se aplican como piso, no como reemplazo.
    """
    # Fallback por si se llama sin parámetros (ej. en tests unitarios)
    limites_minimos = limites_minimos or {'SOCIAL': 15, 'AFILIADO': 35, 'NORMAL': 80}
    limites_finde = limites_finde or {'SOCIAL': 10, 'AFILIADO': 20, 'NORMAL': 30}

    try:
        if not (0 <= dia_semana <= 6):
            raise ValueError(f"dia_semana debe estar entre 0 y 6, recibido: {dia_semana}")
        if not (1 <= dia_mes <= 31):
            raise ValueError(f"dia_mes debe estar entre 1 y 31, recibido: {dia_mes}")

        # COM-64 v2: seleccionar modelo (real si hay datos, simulado si no)
        modelo = rf_regressor_simulado  # default
        modelo_es_real = False
        if cur is not None:
            modelo_real = _entrenar_con_datos_reales(cur)
            if modelo_real is not None:
                modelo = modelo_real
                modelo_es_real = True

        prediccion = modelo.predict([[dia_semana, dia_mes]])[0]

        # Aplicar mínimos configurables desde la BD como PISO (no reemplazo)
        # Para días laborales: usar limites_minimos
        # Para fines de semana: usar limites_finde como piso
        if dia_semana >= 5:  # Fin de semana
            social = max(limites_finde['SOCIAL'], int(round(prediccion[0])))
            afiliado = max(limites_finde['AFILIADO'], int(round(prediccion[1])))
            normal = max(limites_finde['NORMAL'], int(round(prediccion[2])))
        else:  # Día laboral
            social = max(limites_minimos['SOCIAL'], int(round(prediccion[0])))
            afiliado = max(limites_minimos['AFILIADO'], int(round(prediccion[1])))
            normal = max(limites_minimos['NORMAL'], int(round(prediccion[2])))

        return [social, afiliado, normal]
    except Exception as e:
        print(f"Error en predicción de demanda: {e}")
        # Fallback de emergencia usando los mínimos configurados
        if dia_semana >= 5:
            return [limites_finde['SOCIAL'], limites_finde['AFILIADO'], limites_finde['NORMAL']]
        return [limites_minimos['SOCIAL'], limites_minimos['AFILIADO'], limites_minimos['NORMAL']]