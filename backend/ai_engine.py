"""
ai_engine.py
Objetivo: Motor de Machine Learning para predicción de demanda de comensales.
Historial:
 - Sprint 1/2: versión original con datos simulados hardcodeados y pisos mínimos.
 - COM-64: entrena Random Forest con datos REALES de padron_diario (≥30 días).
 - COM-64 v3: devuelve None cuando faltan datos del día de semana consultado
   (≥4 históricos) para que la UI muestre "datos insuficientes".
 - COM-64 v4 (este archivo): se RETIRAN los pisos mínimos (max(limites, predicción))
   que disfrazaban la salida del modelo con los parámetros IA_MIN_*/IA_FINDE_*.
   Ahora se devuelve la predicción PURA más indicadores de calidad:
     * confianza_pct: según cuántas muestras históricas existen del día de semana.
     * n_muestras: días históricos del día de semana usados.
     * r2: R² por tipo (Social/Afiliado/Normal) vía cross_val_predict.
   Política v4: "si no se puede predecir con datos reales, NO se predice".
   Trazabilidad: el modelo simulado y los pisos v3 quedan COMENTADOS al final.
Uso: Importado por routers/padron.py (predecir_demanda_raciones).
Referencia: ticket COM-64 (solo trazabilidad).
"""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import r2_score
from collections import defaultdict


# ==========================================
# COM-64: CARGA DE DATOS REALES DESDE padron_diario
# ==========================================
def _cargar_datos_reales(cur):
    """
    Extrae datos reales agrupados por fecha y tipo (Social/Afiliado/Normal).
    COM-64 v4: además del matriz X/y, devuelve el conteo de muestras por día de
    la semana (muestras_por_dia_semana) para calcular la confianza de la predicción.
    Retorna (X, y, n_dias_unicos, muestras_por_dia_semana) o (None, None, 0, {}).
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
        return None, None, 0, {}

    datos_por_fecha = defaultdict(lambda: {'Social': 0, 'Afiliado': 0, 'Normal': 0})
    for r in rows:
        datos_por_fecha[r['fecha']][r['tipo_comensal_venta']] = int(r['total'])

    X, y = [], []
    muestras_por_dia_semana = defaultdict(int)
    for fecha, tipos in datos_por_fecha.items():
        X.append([fecha.weekday(), fecha.day])
        y.append([tipos['Social'], tipos['Afiliado'], tipos['Normal']])
        muestras_por_dia_semana[fecha.weekday()] += 1

    return np.array(X), np.array(y), len(datos_por_fecha), dict(muestras_por_dia_semana)


# ==========================================
# COM-64 v4: CONFIANZA SEGÚN MUESTRAS DEL DÍA DE SEMANA
# ==========================================
def _calcular_confianza(n_muestras_dia: int) -> int:
    """
    Nivel de confianza (0-100) de la predicción según cuántos días históricos del
    mismo día de semana alimentan el modelo:
      >= 12 muestras (3+ meses): 90-100% (alta)
      8-11 muestras (2-3 meses): 70-89%  (media)
      4-7  muestras (1-2 meses): 50-69%  (baja)
      < 4: no se predice (el caller devuelve None antes de llegar aquí).
    """
    if n_muestras_dia >= 12:
        return min(100, 90 + (n_muestras_dia - 12) * 2)
    if n_muestras_dia >= 8:
        return 70 + (n_muestras_dia - 8) * 5
    if n_muestras_dia >= 4:
        return 50 + (n_muestras_dia - 4) * 5
    return 0


# ==========================================
# COM-64 v4: ENTRENAMIENTO CON DATOS REALES + MÉTRICAS
# ==========================================
def _entrenar_con_datos_reales(cur):
    """
    Entrena un RandomForest con datos reales si hay ≥30 días de historial.
    COM-64 v4: además del modelo, calcula R² por tipo de comensal mediante
    cross_val_predict (validación cruzada) para que la UI pueda mostrar la calidad
    del ajuste. Retorna (modelo, metadata) o (None, {}) si no hay datos suficientes.
    """
    try:
        X_real, y_real, n_dias, muestras_por_dia = _cargar_datos_reales(cur)
        if X_real is None or n_dias < 30:
            return None, {}

        modelo = RandomForestRegressor(
            n_estimators=100, max_depth=5, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1
        )
        modelo.fit(X_real, y_real)

        # COM-64 v4: R² por tipo con validación cruzada (nunca falla el endpoint)
        r2 = None
        try:
            cv = 5 if n_dias >= 25 else (3 if n_dias >= 12 else 2)
            pred_cv = cross_val_predict(modelo, X_real, y_real, cv=cv)
            r2_arr = r2_score(y_real, pred_cv, multioutput='raw_values')
            r2 = {
                'Social': round(float(r2_arr[0]), 3),
                'Afiliado': round(float(r2_arr[1]), 3),
                'Normal': round(float(r2_arr[2]), 3),
            }
        except Exception as e:
            print(f"[AI_ENGINE] No se pudo calcular R² cruzado: {e}")
            r2 = None

        return modelo, {
            'muestras_por_dia': muestras_por_dia,
            'r2': r2,
            'n_dias': n_dias,
        }
    except Exception as e:
        print(f"[AI_ENGINE] Error al entrenar con datos reales: {e}")
        return None, {}


# ==========================================
# PREDICCIÓN (COM-64 v4: pura + confianza, sin pisos)
# ==========================================
def predecir_demanda_raciones(dia_semana: int, dia_mes: int,
                              limites_minimos: dict = None,
                              limites_finde: dict = None,
                              cur=None):
    """
    COM-64 v4: predice la demanda PURA del modelo para una fecha específica.
    Retorna un dict:
      {'prediccion': [social, afiliado, normal],
       'confianza_pct': int 0-100,
       'n_muestras': int,
       'r2': {'Social':..,'Afiliado':..,'Normal':..} o None}
    o None si no hay datos reales suficientes (la UI muestra "datos insuficientes").

    Los parámetros limites_minimos/limites_finde se mantienen en la firma por
    compatibilidad con callers antiguos, pero YA NO se aplican como piso
    (trazabilidad: lógica v3 comentada al final del archivo).
    """
    try:
        if not (0 <= dia_semana <= 6) or not (1 <= dia_mes <= 31):
            return None
        if cur is None:
            return None

        # Muestras históricas del día de semana consultado (ISODOW: 1=Lun .. 7=Dom)
        cur.execute("""
            SELECT COUNT(DISTINCT fecha) as total_dias
            FROM padron_diario
            WHERE tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal')
              AND EXTRACT(ISODOW FROM fecha) = %s
        """, (dia_semana + 1,))
        count_dia = cur.fetchone()['total_dias']
        if count_dia < 4:
            return None

        modelo, metadata = _entrenar_con_datos_reales(cur)
        if modelo is None:
            return None

        # COM-64 v4: predicción PURA del modelo, sin pisos artificiales
        prediccion = modelo.predict([[dia_semana, dia_mes]])[0]
        social = int(round(prediccion[0]))
        afiliado = int(round(prediccion[1]))
        normal = int(round(prediccion[2]))

        n_muestras = metadata.get('muestras_por_dia', {}).get(dia_semana, count_dia)
        return {
            'prediccion': [social, afiliado, normal],
            'confianza_pct': _calcular_confianza(n_muestras),
            'n_muestras': n_muestras,
            'r2': metadata.get('r2'),
        }
    except Exception as e:
        print(f"Error en predicción de demanda: {e}")
        return None


# ==========================================
# COM-64 v4 (TRAZABILIDAD): código v3 COMENTADO (pisos mínimos y modelo simulado)
# ==========================================
# --- Pisos mínimos v3 (distorsionaban la predicción real; RETIRADOS en v4): ---
#     if dia_semana >= 5:
#         social = max(limites_finde['SOCIAL'], int(round(prediccion[0])))
#         afiliado = max(limites_finde['AFILIADO'], int(round(prediccion[1])))
#         normal = max(limites_finde['NORMAL'], int(round(prediccion[2])))
#     else:
#         social = max(limites_minimos['SOCIAL'], int(round(prediccion[0])))
#         afiliado = max(limites_minimos['AFILIADO'], int(round(prediccion[1])))
#         normal = max(limites_minimos['NORMAL'], int(round(prediccion[2])))
#     return [social, afiliado, normal]
#
# --- Modelo simulado v2/v3 (fallback que ya NO se usa; política v4: sin datos no
#     hay predicción). Se conserva la referencia histórica: ---
# def _generar_datos_entrenamiento():
#     X, y = [], []
#     for semana in range(104):
#         for dia_semana in range(7):
#             ... bases simuladas por día (22/43/110 ... 8/15/25) ...
#     return np.array(X), np.array(y)
# rf_regressor_simulado = RandomForestRegressor(...).fit(X_train_sim, y_train_sim)