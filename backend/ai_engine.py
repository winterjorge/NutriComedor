"""
ai_engine.py
Objetivo: Motor de Machine Learning para predicción de demanda de comensales.
          COM-64: entrena Random Forest con datos REALES de padron_diario.
          Si no hay suficientes datos reales (especialmente para el día de la semana
          específico), devuelve None para que la UI muestre un mensaje de advertencia.
"""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from collections import defaultdict

# ==========================================
# DATOS DE ENTRENAMIENTO SIMULADOS (fallback interno, no se usa si hay datos reales)
# ==========================================
def _generar_datos_entrenamiento():
    """Genera datos de entrenamiento simulados basados en patrones reales"""
    X = []
    y = []
    for semana in range(104):
        for dia_semana in range(7):
            dia_mes = ((semana * 7) + dia_semana) % 31 + 1
            if dia_semana == 0: base_social, base_afiliado, base_normal = 22, 43, 110
            elif dia_semana == 1: base_social, base_afiliado, base_normal = 21, 44, 115
            elif dia_semana == 2: base_social, base_afiliado, base_normal = 20, 45, 120
            elif dia_semana == 3: base_social, base_afiliado, base_normal = 21, 44, 118
            elif dia_semana == 4: base_social, base_afiliado, base_normal = 23, 42, 105
            else: base_social, base_afiliado, base_normal = 8, 15, 25
            
            if dia_mes <= 5: factor = 0.95
            elif 10 <= dia_mes <= 20: factor = 1.05
            elif dia_mes >= 25: factor = 1.15
            else: factor = 1.0
            
            np.random.seed(semana * 7 + dia_semana)
            variacion = np.random.uniform(0.9, 1.1)
            X.append([dia_semana, dia_mes])
            y.append([
                int(base_social * factor * variacion),
                int(base_afiliado * factor * variacion),
                int(base_normal * factor * variacion)
            ])
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
    """Extrae datos reales agrupados por fecha y tipo."""
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

    datos_por_fecha = defaultdict(lambda: {'Social': 0, 'Afiliado': 0, 'Normal': 0})
    for r in rows:
        datos_por_fecha[r['fecha']][r['tipo_comensal_venta']] = int(r['total'])

    X, y = [], []
    for fecha, tipos in datos_por_fecha.items():
        X.append([fecha.weekday(), fecha.day])
        y.append([tipos['Social'], tipos['Afiliado'], tipos['Normal']])

    return np.array(X), np.array(y), len(datos_por_fecha)


def _entrenar_con_datos_reales(cur):
    """Entrena un RF con datos reales si hay ≥30 días de historial."""
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
# PREDICCIÓN
# ==========================================
def predecir_demanda_raciones(dia_semana: int, dia_mes: int,
                               limites_minimos: dict = None,
                               limites_finde: dict = None,
                               cur=None):
    """
    COM-64 v3: Si no hay suficientes datos reales para el día de la semana específico,
    devuelve None para que la UI muestre un mensaje de "datos insuficientes".
    """
    limites_minimos = limites_minimos or {'SOCIAL': 15, 'AFILIADO': 35, 'NORMAL': 80}
    limites_finde = limites_finde or {'SOCIAL': 10, 'AFILIADO': 20, 'NORMAL': 30}

    try:
        if not (0 <= dia_semana <= 6) or not (1 <= dia_mes <= 31):
            return None

        modelo_es_real = False
        if cur is not None:
            # Verificar si hay al menos 4 registros históricos para ESTE día de la semana
            # EXTRACT(ISODOW FROM fecha): 1=Lunes ... 7=Domingo
            # dia_semana: 0=Lunes ... 6=Domingo -> sumamos 1
            cur.execute("""
                SELECT COUNT(DISTINCT fecha) as total_dias
                FROM padron_diario 
                WHERE tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal')
                AND EXTRACT(ISODOW FROM fecha) = %s
            """, (dia_semana + 1,))
            count_dia = cur.fetchone()['total_dias']
            
            if count_dia >= 4:
                modelo_real = _entrenar_con_datos_reales(cur)
                if modelo_real is not None:
                    modelo = modelo_real
                    modelo_es_real = True

        # Si no pudimos usar un modelo real, no predecimos (devolvemos None)
        if not modelo_es_real:
            return None

        prediccion = modelo.predict([[dia_semana, dia_mes]])[0]

        # Aplicar mínimos configurables como piso
        if dia_semana >= 5:
            social = max(limites_finde['SOCIAL'], int(round(prediccion[0])))
            afiliado = max(limites_finde['AFILIADO'], int(round(prediccion[1])))
            normal = max(limites_finde['NORMAL'], int(round(prediccion[2])))
        else:
            social = max(limites_minimos['SOCIAL'], int(round(prediccion[0])))
            afiliado = max(limites_minimos['AFILIADO'], int(round(prediccion[1])))
            normal = max(limites_minimos['NORMAL'], int(round(prediccion[2])))

        return [social, afiliado, normal]
    except Exception as e:
        print(f"Error en predicción de demanda: {e}")
        return None