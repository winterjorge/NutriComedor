"""
ai_engine.py
Objetivo: Motor de Machine Learning para predicción de demanda de comensales.
Historial:
Sprint 1/2: versión original con datos simulados hardcodeados y pisos mínimos.
COM-64: entrena Random Forest con datos REALES de padron_diario (≥30 días).
COM-64 v3: devuelve None cuando faltan datos del día de semana consultado
(≥4 históricos) para que la UI muestre "datos insuficientes".
COM-64 v4: se RETIRAN los pisos mínimos (max(limites, predicción)) que
disfrazaban la salida del modelo con los parámetros IA_MIN_/IA_FINDE_.
Ahora se devuelve la predicción PURA más indicadores de calidad:
confianza_pct: según cuántas muestras históricas existen del día de semana.
n_muestras: días históricos del día de semana usados.
r2: R² por tipo (Social/Afiliado/Normal) vía cross_val_predict.
Política v4: "si no se puede predecir con datos reales, NO se predice".
Trazabilidad: el modelo simulado y los pisos v3 quedan COMENTADOS al final.
COM-103 (este archivo): CACHÉ DE MODELO + PREDICCIÓN POR LOTE.
* _obtener_modelo_cacheado(): el RF de demanda se entrena UNA vez por proceso
  y se reutiliza mientras no cambie el historial (huella = n filas + fecha max
  de padron_diario) ni expire el TTL (10 min). Antes, CADA llamada a
  predecir_demanda_raciones entrenaba 1 RF + 5 fits de cross_val: el greedy
  (5 días de cocina) hacía ~30 entrenamientos por generación de propuestas.
* predecir_demanda_lote(fechas): predice N fechas con UN solo predict()
  vectorizado; retorna {fecha_iso: payload} con el mismo shape que la
  predicción unitaria. Las fechas sin ≥4 históricos de su día de semana
  quedan ausentes y el caller aplica su fallback de parámetros.
* predecir_demanda_raciones conserva su firma y comportamiento (usa la caché).
Uso: Importado por routers/padron.py y ml/greedy_search.py.
Referencia: ticket COM-64 / COM-103 (solo trazabilidad).
"""
import time
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import r2_score
from collections import defaultdict

# ==========================================
# COM-103: CACHÉ DE MODELO EN PROCESO
# ==========================================
# El historial de demanda solo cambia cuando el POS/carga masiva escribe en
# padron_diario; la huella (n filas, fecha max) invalida la caché automáticamente
# en ese caso. El TTL cubre el escenario de escrituras que no cambian la huella.
CACHE_MODELO_TTL_SEG = 600
_CACHE_MODELO = {'clave': None, 'modelo': None, 'metadata': None, 'ts': 0.0}


def _clave_cache(cur):
    """Huella barata del historial de demanda (sin cargar todas las filas)."""
    cur.execute("""
        SELECT COUNT(*) AS n, MAX(fecha) AS f
        FROM padron_diario
        WHERE tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal');
    """)
    r = cur.fetchone()
    return (int(r['n'] or 0), str(r['f']))


def _obtener_modelo_cacheado(cur):
    """
    COM-103: devuelve (modelo, metadata) reutilizando el entrenamiento mientras la
    huella del historial y el TTL lo permitan; si no, entrena y cachea.
    """
    clave = _clave_cache(cur)
    ahora = time.time()
    if (_CACHE_MODELO['clave'] == clave and _CACHE_MODELO['modelo'] is not None
            and (ahora - _CACHE_MODELO['ts']) < CACHE_MODELO_TTL_SEG):
        return _CACHE_MODELO['modelo'], _CACHE_MODELO['metadata']
    modelo, metadata = _entrenar_con_datos_reales(cur)
    if modelo is not None:
        _CACHE_MODELO.update({'clave': clave, 'modelo': modelo,
                              'metadata': metadata, 'ts': ahora})
    return modelo, metadata


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
    COM-103: este function queda como ÚNICO punto de entrenamiento; los callers
    (unitario y lote) pasan por _obtener_modelo_cacheado para no re-entrenar.
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
    COM-64 v4 + COM-103: predice la demanda PURA del modelo para una fecha específica.
    Retorna un dict:
    {'prediccion': [social, afiliado, normal],
     'confianza_pct': int 0-100,
     'n_muestras': int,
     'r2': {'Social':..,'Afiliado':..,'Normal':..} o None}
    o None si no hay datos reales suficientes (la UI muestra "datos insuficientes").
    Los parámetros limites_minimos/limites_finde se mantienen en la firma por
    compatibilidad con callers antiguos, pero YA NO se aplican como piso
    (trazabilidad: lógica v3 comentada al final del archivo).
    COM-103: el entrenamiento pasa por _obtener_modelo_cacheado (1 fit por proceso
    y huella de historial, en lugar de 1 fit + 5 CV por llamada).
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
        # COM-103: modelo cacheado (antes: _entrenar_con_datos_reales(cur) directo)
        modelo, metadata = _obtener_modelo_cacheado(cur)
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
# COM-103: PREDICCIÓN POR LOTE (1 entrenamiento + 1 predict vectorizado)
# ==========================================
def predecir_demanda_lote(fechas, limites_minimos: dict = None,
                          limites_finde: dict = None, cur=None):
    """
    COM-103: predice VARIAS fechas de una sola vez para el greedy (COM-74):
    un único modelo cacheado y un único predict() vectorizado, en lugar de una
    llamada unitaria por día de cocina.
    Retorna {fecha_iso: payload} con el MISMO shape que predecir_demanda_raciones.
    Las fechas sin ≥4 históricos de su día de semana (o sin modelo) quedan
    AUSENTES del dict: el caller aplica su fallback de parámetros estáticos.
    Los parámetros limites_* se conservan en la firma por simetría con la
    predicción unitaria (ya no se aplican como piso, política COM-64 v4).
    """
    if cur is None or not fechas:
        return {}
    try:
        # Conteos por día de semana en UNA sola consulta (antes: 1 consulta por día)
        cur.execute("""
            SELECT EXTRACT(ISODOW FROM fecha)::int AS dow, COUNT(DISTINCT fecha) AS total_dias
            FROM padron_diario
            WHERE tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal')
            GROUP BY 1;
        """)
        counts = {r['dow']: r['total_dias'] for r in cur.fetchall()}
        validas = [f for f in fechas if counts.get(f.weekday() + 1, 0) >= 4]
        if not validas:
            return {}
        modelo, metadata = _obtener_modelo_cacheado(cur)
        if modelo is None:
            return {}
        X = np.array([[f.weekday(), f.day] for f in validas])
        preds = modelo.predict(X)
        out = {}
        for f, p in zip(validas, preds):
            n_muestras = metadata.get('muestras_por_dia', {}).get(
                f.weekday(), counts.get(f.weekday() + 1, 0))
            out[f.isoformat()] = {
                'prediccion': [int(round(p[0])), int(round(p[1])), int(round(p[2]))],
                'confianza_pct': _calcular_confianza(n_muestras),
                'n_muestras': n_muestras,
                'r2': metadata.get('r2'),
            }
        return out
    except Exception as e:
        print(f"[AI_ENGINE] Error en predicción por lote: {e}")
        return {}


# ==========================================
# COM-64 v4 (TRAZABILIDAD): código v3 COMENTADO (pisos mínimos y modelo simulado)
# ==========================================
# --- Pisos mínimos v3 (distorsionaban la predicción real; RETIRADOS en v4): ---
# if dia_semana >= 5:
#     social = max(limites_finde['SOCIAL'], int(round(prediccion[0])))
#     afiliado = max(limites_finde['AFILIADO'], int(round(prediccion[1])))
#     normal = max(limites_finde['NORMAL'], int(round(prediccion[2])))
# else:
#     social = max(limites_minimos['SOCIAL'], int(round(prediccion[0])))
#     afiliado = max(limites_minimos['AFILIADO'], int(round(prediccion[1])))
#     normal = max(limites_minimos['NORMAL'], int(round(prediccion[2])))
# return [social, afiliado, normal]
#
# --- Modelo simulado v2/v3 (fallback que ya NO se usa; política v4: sin datos no
# hay predicción). Se conserva la referencia histórica: ---
# def _generar_datos_entrenamiento():
#     X, y = [], []
#     for semana in range(104):
#         for dia_semana in range(7):
#             ... bases simuladas por día (22/43/110 ... 8/15/25) ...
#     return np.array(X), np.array(y)
# rf_regressor_simulado = RandomForestRegressor(...).fit(X_train_sim, y_train_sim)