"""
ml/random_forest_demanda.py
Objetivo: Modelos de demanda diaria de comensales (social / afiliado / normal /
cocinera) para el panel de gráficos de Machine Learning (COM-5 v4 / COM-8 v7).
Entrena con el historial del padrón/ventas y devuelve los datos del gráfico de
dispersión REAL vs PREDICHO con split temporal configurable, métricas
R²/MAE/MAPE por tipo, baseline naive de referencia y la relevancia de cada
variable (feature importances).
Historial:
COM-5 v4 / COM-8 v7: versión original con RF y split 80/20.
COM-91: se agrega MAPE por tipo de comensal.
COM-91 v2: split temporal configurable (evaluacion por fecha fija / produccion
expanding window / fallback ratio).
COM-92: selector de modelo (RF vs GBM) vía parámetro modelo_key.
COM-92 v2: modelo híbrido adaptativo por estrategia (constante / media móvil /
modelo ML) según desviación de cada serie + ensemble RF+GBM+MM.
COM-93 (este archivo): REINGENIERÍA DE FEATURES POR DÍA OPERATIVO:
* Lags/medias móviles POR TIPO y sobre DÍAS OPERATIVOS (el comedor cocina
  Lun-Vie; los lags calendario de COM-91 v3 inyectaban CEROS los lunes porque
  "ayer" (domingo) no existe en el historial, ensuciando el entrenamiento).
* Matriz de features POR TIPO: lags propios (1/2/5 días operativos), medias
  móviles 5/10, desviación móvil 5, lags del total, calendario y flags de
  inicio/fin de mes (efecto quincena/pago visible en los datos: Afiliado 77/76
  y Normal 8/14 el 2 y 5 de octubre).
* Warm-start de lags con media expansiva: nunca ceros artificiales.
* Estrategias recalibradas con datos reales (191 días): 'constante' SOLO si
  std < 0.5 (Cocinera = 20 exacto); Social (std 1.80) pasa a modelo ML porque
  con lags predice ~20 y logra MAPE ~1-2% (la constante redondeada a 19 de
  COM-92 v2 daba MAPE ~6%).
* Baseline naive (valor del mismo día operativo de la semana anterior) expuesta
  en `metricas_baseline` para comparar RF/GBM contra el piso razonable.
* FIX COM-92 v2: `_calcular_importancias_dict` usaba `modelo.feature_importances`
  (sin guion final) -> AttributeError al pedir RF/GBM individual; corregido a
  `feature_importances_`.
* Sin escalado de features: RF/GBM son modelos de árbol, invariantes a escala
  (el RobustScaler de COM-92 v2 era un no-op costoso); se comenta por trazabilidad.
* El análisis de calendario mostró que dia_semana NO explica la varianza
  (Afiliado: 55.7/54.4/55.6/56.8/56.4 por día); la señal real es autocorrelación
  + nivel reciente + efecto inicio/fin de mes, por eso las features nuevas.
Uso: Importado por routers/modelos_ml.py. Entrenamiento bajo demanda (no persiste).
Referencia: tickets COM-5 v4 / HU-04 / COM-91 / COM-92 / COM-93 (solo trazabilidad).
"""
from datetime import date, datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal', 'cocinera')

# COM-93: nombres de las 15 features por tipo (orden = columnas de la matriz).
# Trazabilidad COM-91 v3 / COM-92 v2 (13 features calendario+lags CALENDARIO):
#   ('dia_semana','mes','dia_del_mes','es_fin_de_semana','tendencia',
#    'lag_1','lag_7','media_movil_7','media_movil_14',
#    'dia_semana_sin','dia_semana_cos','mes_sin','mes_cos')
# Ese set quedó obsoleto: lag_1/lag_7 calendario inyectaban ceros los lunes.
VARIABLES = (
    'lag1_op', 'lag2_op', 'lag5_op',
    'roll_mean5_op', 'roll_mean10_op', 'roll_std5_op',
    'total_lag1_op', 'total_roll5_op',
    'dia_semana', 'dia_del_mes', 'mes',
    'es_fin_semana', 'es_inicio_mes', 'es_fin_mes',
    'tendencia_op',
)
RANDOM_STATE = 42

# COM-93: configuración de splits (heredada de COM-91 v2)
MIN_DIAS_TRAIN = 30
MIN_DIAS_TEST = 5
FECHA_CORTE_DEFAULT = date(2026, 10, 1)
DIAS_TEST_DEFAULT = 30

# COM-93: una serie es "constante" solo si su desviación es casi nula
# (Cocinera: std=0.00). COM-92 v2 usaba 2.0, lo que degradaba a Social
# (std=1.80) a constante=19 cuando con lags el modelo clava ~20.
UMBRAL_STD_CONSTANTE = 0.5

# COM-92 / COM-93: hiperparámetros ajustados para ~160 días de train y 15 features.
# Trazabilidad COM-92 v2: RF n_estimators=200/max_depth=8; GBM lr=0.05/max_depth=4.
MODELOS_DISPONIBLES = {
    'rf': {
        'nombre': 'Random Forest',
        'clase': RandomForestRegressor,
        'params': {
            'n_estimators': 300,
            'max_depth': 12,
            'min_samples_leaf': 2,
            'max_features': 0.7,
            'random_state': RANDOM_STATE,
            'n_jobs': -1,
        },
    },
    'gbm': {
        'nombre': 'Gradient Boosting',
        'clase': GradientBoostingRegressor,
        'params': {
            'n_estimators': 250,
            'learning_rate': 0.06,
            'max_depth': 3,
            'subsample': 0.9,
            'min_samples_leaf': 5,
            'random_state': RANDOM_STATE,
        },
    },
    'ensemble': {
        'nombre': 'Ensemble (RF + GBM + Naive)',
        'clase': None,  # combinación especial, ver _prediccion_ensemble
        'params': {},
    },
}


# ==========================================
# UTILIDADES DE ESQUEMA (detección defensiva)
# ==========================================
def _tablas_public(cur):
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    return [r['table_name'] for r in cur.fetchall()]


def _columnas(cur, tabla):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s;", (tabla,))
    return [r['column_name'] for r in cur.fetchall()]


def _col(cols, candidatos, contiene=None):
    for c in candidatos:
        if c in cols:
            return c
    if contiene:
        for c in cols:
            if contiene in c:
                return c
    return None


def _detectar_tabla_ventas(cur, tablas):
    """Tabla de registro diario de ventas/padrón por tipo de comensal."""
    for n in ('padron_diario', 'ventas', 'venta_diaria', 'registro_ventas', 'padron'):
        if n in tablas:
            return n
    for n in tablas:
        if ('venta' in n or 'padron' in n) and 'detalle' not in n:
            return n
    return None


def _a_fecha(valor):
    """Convierte un valor de columna de fecha a datetime.date."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


# ==========================================
# CARGA DEL HISTORIAL DE DEMANDA
# ==========================================
def _cargar_historia_demanda(cur):
    """
    Retorna {fecha: {'social': n, 'afiliado': n, 'normal': n, 'cocinera': n}}
    agregado por día. Detecta si el tipo de comensal vive en la tabla de ventas
    o se obtiene por join con la tabla de comensales.
    """
    tablas = _tablas_public(cur)
    tabla = _detectar_tabla_ventas(cur, tablas)
    if not tabla:
        raise ValueError(
            f"No se detectó la tabla de padrón/ventas (padron_diario, ventas, ...). "
            f"Tablas públicas: {', '.join(sorted(tablas))}.")
    cols = _columnas(cur, tabla)
    col_fecha = _col(cols, ['fecha', 'fecha_venta', 'fecha_registro', 'dia'], contiene='fecha')
    col_cant = _col(cols, ['raciones', 'cantidad', 'menus', 'total'], contiene='racion') or \
               _col(cols, [], contiene='cant') or _col(cols, [], contiene='total')
    col_tipo = _col(cols, ['tipo_comensal', 'tipo_comensal_venta', 'tipo', 'categoria'], contiene='tipo')
    if not col_fecha or not col_cant:
        raise ValueError(f"La tabla '{tabla}' no tiene columnas fecha/cantidad reconocibles: {cols}")
    if col_tipo:
        cur.execute(f"""
            SELECT {col_fecha} AS f, LOWER({col_tipo}::text) AS t, SUM({col_cant}) AS n
            FROM {tabla}
            GROUP BY 1, 2;
        """)
    else:
        if 'comensales' not in tablas:
            raise ValueError("No se pudo determinar el tipo de comensal: falta columna 'tipo' o tabla 'comensales'.")
        ccols = _columnas(cur, 'comensales')
        col_ctipo = _col(ccols, ['tipo', 'categoria', 'tipo_comensal'], contiene='tipo')
        col_cid = _col(cols, ['comensal_id', 'id_comensal', 'comensal'], contiene='comensal')
        if not col_ctipo or not col_cid:
            raise ValueError("No se pudo unir padrón con comensales para obtener el tipo.")
        cur.execute(f"""
            SELECT v.{col_fecha} AS f, LOWER(c.{col_ctipo}::text) AS t, SUM(v.{col_cant}) AS n
            FROM {tabla} v
            JOIN comensales c ON c.id = v.{col_cid}
            GROUP BY 1, 2;
        """)
    historia = {}
    for r in cur.fetchall():
        f = _a_fecha(r['f'])
        t_raw = (r['t'] or '').strip()
        t = next((tt for tt in TIPOS if tt in t_raw), None)
        if not t:
            continue
        dia = historia.setdefault(f, {t_: 0.0 for t_ in TIPOS})
        dia[t] += float(r['n'] or 0)
    return historia


# ==========================================
# COM-93: FEATURES POR DÍA OPERATIVO Y POR TIPO
# ==========================================
def _matriz_features_por_tipo(historia: dict, fechas: list, tipo: str) -> np.ndarray:
    """
    COM-93: matriz (len(fechas) x len(VARIABLES)) para UN tipo de comensal.
    Los lags y medias móviles se calculan sobre la SECUENCIA DE DÍAS OPERATIVOS
    (las fechas presentes en el historial), no sobre días calendario: así el
    "lag1" de un lunes es el viernes anterior y nunca aparece un cero artificial.
    Warm-start: cuando aún no hay suficiente pasado (primeros días), el lag se
    reemplaza por la media expansiva conocida hasta ese punto.
    En producción esto es legítimo: al predecir un día, los reales anteriores
    ya están registrados en el padrón.
    """
    vals = [float(historia[f].get(tipo, 0.0)) for f in fechas]
    totals = [sum(float(v) for v in historia[f].values()) for f in fechas]
    media_global = float(np.mean(vals)) if vals else 0.0
    media_global_total = float(np.mean(totals)) if totals else 0.0
    X = []
    for i, f in enumerate(fechas):
        # Media expansiva del tipo (solo pasado conocido) para warm-start
        pref = vals[:i]
        media_exp = float(np.mean(pref)) if pref else media_global
        # Lags propios por día operativo
        lag1 = vals[i - 1] if i - 1 >= 0 else media_exp
        lag2 = vals[i - 2] if i - 2 >= 0 else media_exp
        lag5 = vals[i - 5] if i - 5 >= 0 else media_exp
        # Medias móviles y desviación móvil (ventana de hasta 10 días operativos)
        w5 = vals[max(0, i - 5):i] or [media_exp]
        w10 = vals[max(0, i - 10):i] or [media_exp]
        roll5 = float(np.mean(w5))
        roll10 = float(np.mean(w10))
        roll_std5 = float(np.std(w5)) if len(w5) > 1 else 0.0
        # Lags del TOTAL (todos los tipos) por día operativo
        pref_t = totals[:i]
        media_exp_t = float(np.mean(pref_t)) if pref_t else media_global_total
        tlag1 = totals[i - 1] if i - 1 >= 0 else media_exp_t
        tw5 = totals[max(0, i - 5):i] or [media_exp_t]
        troll5 = float(np.mean(tw5))
        # Calendario + efecto inicio/fin de mes (quincena/pago) + tendencia operativa
        X.append([
            lag1, lag2, lag5,
            roll5, roll10, roll_std5,
            tlag1, troll5,
            float(f.weekday()), float(f.day), float(f.month),
            1.0 if f.weekday() >= 5 else 0.0,
            1.0 if f.day <= 5 else 0.0,
            1.0 if f.day >= 26 else 0.0,
            float(i),
        ])
    return np.array(X, dtype=float)


# COM-93 (trazabilidad): features calendario de COM-91 v3 / COM-92 v2, comentadas.
# Eran compartidas por los 3 tipos y sus lags calendario valían 0 los lunes:
# def _features_enriquecidas(f, historia, fecha_inicio):
#     ... lag_1 = sum(historia[f - timedelta(days=1)].values()) si existe sino 0 ...


def _prediccion_naive(historia: dict, fechas: list, tipo: str) -> list:
    """
    COM-93: baseline naive = valor del MISMO día operativo de la semana anterior
    (lag 5 operativo); si no existe, media expansiva. Sirve como piso de
    comparación (metricas_baseline) y como componente del ensemble.
    """
    vals = [float(historia[f].get(tipo, 0.0)) for f in fechas]
    media_global = float(np.mean(vals)) if vals else 0.0
    out = []
    for i in range(len(fechas)):
        pref = vals[:i]
        media_exp = float(np.mean(pref)) if pref else media_global
        out.append(vals[i - 5] if i - 5 >= 0 else media_exp)
    return out


# ==========================================
# COM-91: CÁLCULO DE MAPE
# ==========================================
def _calcular_mape(real, predicho):
    """
    COM-91: MAPE = (1/n) * Σ|(real - predicho) / real| * 100, solo sobre muestras
    con real > 0 (evita división por cero). None si no hay muestras válidas.
    """
    real = np.array(real, dtype=float)
    predicho = np.array(predicho, dtype=float)
    mascara = real > 0
    if not mascara.any():
        return None
    rf_ = real[mascara]
    pf_ = predicho[mascara]
    errores_pct = np.abs((rf_ - pf_) / rf_)
    return float(np.mean(errores_pct) * 100)


def _metricas_de(real, pred) -> dict:
    """R²/MAE/MAPE redondeados de un par real/predicho (COM-91/COM-93)."""
    real = np.array(real, dtype=float)
    pred = np.array(pred, dtype=float)
    r2 = float(r2_score(real, pred)) if len(set(real.tolist())) > 1 else None
    mape = _calcular_mape(real, pred)
    return {
        'r2': round(r2, 4) if r2 is not None else None,
        'mae': round(float(mean_absolute_error(real, pred)), 2),
        'mape': round(mape, 2) if mape is not None else None,
    }


# ==========================================
# COM-91 v2: SPLITS (sin cambios)
# ==========================================
def _split_por_fecha(fechas, fecha_corte):
    fechas_train = [f for f in fechas if f < fecha_corte]
    fechas_test = [f for f in fechas if f >= fecha_corte]
    return fechas_train, fechas_test


def _split_expanding_window(fechas, dias_test):
    fechas_test = fechas[-dias_test:]
    fechas_train = fechas[:-dias_test]
    return fechas_train, fechas_test


def _split_ratio(fechas, ratio):
    corte = int(len(fechas) * ratio)
    return fechas[:corte], fechas[corte:]


# ==========================================
# COM-93: HELPERS DE MODELOS INDIVIDUALES
# ==========================================
def _entrenar_modelo_individual(X_train, X_test, y_train, modelo_key: str) -> list:
    """Entrena RF o GBM sobre la matriz del tipo y devuelve predicciones redondeadas."""
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, y_train)
    pred = modelo.predict(X_test)
    # COM-93: la demanda es discreta y no negativa -> redondeo y piso en 0
    return [max(0.0, round(float(p), 1)) for p in pred]


def _importancias_de(X_train, y_train, modelo_key: str) -> list:
    """
    COM-93: importancias en formato dict para el payload.
    FIX COM-92 v2: se usaba `modelo.feature_importances` (AttributeError);
    la propiedad correcta de scikit-learn es `feature_importances_`.
    """
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, y_train)
    return [
        {'variable': VARIABLES[j], 'importancia': round(float(v), 4)}
        for j, v in enumerate(modelo.feature_importances_)
    ]


def _prediccion_ensemble(X_train, X_test, y_train, naive_test) -> list:
    """
    COM-92 v2 / COM-93: ensemble 40% RF + 40% GBM + 20% naive semanal.
    El componente naive reemplaza a la "media móvil" de COM-92 v2 porque el
    naive de día operativo es un baseline más fuerte en estas series.
    """
    pred_rf = _entrenar_modelo_individual(X_train, X_test, y_train, 'rf')
    pred_gbm = _entrenar_modelo_individual(X_train, X_test, y_train, 'gbm')
    pred = [
        max(0.0, round(0.4 * rf + 0.4 * gbm + 0.2 * nv, 1))
        for rf, gbm, nv in zip(pred_rf, pred_gbm, naive_test)
    ]
    return pred


# ==========================================
# ENTRENAMIENTO Y EVALUACIÓN (COM-93)
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None,
                          modelo_key='rf'):
    """
    COM-93: entrena el modelo elegido (rf / gbm / ensemble) con features POR TIPO
    sobre días OPERATIVOS y devuelve el payload completo del panel ML:
    - puntos: [{fecha, tipo, real, predicho}] del conjunto de prueba
    - metricas: R², MAE y MAPE por tipo
    - metricas_baseline: R²/MAE/MAPE del naive semanal (piso de comparación)
    - importancias: relevancia de cada variable por tipo
    - info_split: tipo de split, rangos, días y estrategias usadas por tipo
    Estrategias por tipo (COM-93):
    - 'constante': std < 0.5 (Cocinera=20): se predice la media redondeada.
    - 'modelo_ml' / modelo_key: el resto (Social incluido: con lags predice ~20).
    Nota de interpretación: para series casi constantes (Social, std≈1.8 sobre
    media≈19.3) el R² es inherentemente cercano a 0 aunque el MAPE sea ~1-2%:
    la varianza del test es mínima y cualquier error pequeño la consume. En esas
    series el indicador útil es el MAPE, no el R².
    """
    if modelo_key not in MODELOS_DISPONIBLES:
        raise ValueError(f"Modelo '{modelo_key}' no válido. Use 'rf', 'gbm' o 'ensemble'.")

    historia = _cargar_historia_demanda(cur)
    fechas = sorted(historia.keys())

    if fecha_corte is None:
        fecha_corte = FECHA_CORTE_DEFAULT
    if dias_test is None:
        dias_test = DIAS_TEST_DEFAULT

    # ---- Split temporal (COM-91 v2, sin cambios) ----
    info_split = {}
    if modo == 'evaluacion':
        fechas_train, fechas_test = _split_por_fecha(fechas, fecha_corte)
        info_split = {'tipo': 'evaluacion_fija', 'fecha_corte': fecha_corte.isoformat()}
    elif modo == 'produccion':
        if len(fechas) > dias_test:
            fechas_train, fechas_test = _split_expanding_window(fechas, dias_test)
        else:
            fechas_train, fechas_test = _split_ratio(fechas, SPLIT_ENTRENAMIENTO_LEGACY)
        info_split = {'tipo': 'expanding_window', 'dias_test': dias_test}
    else:
        fechas_train, fechas_test = _split_ratio(fechas, SPLIT_ENTRENAMIENTO_LEGACY)
        info_split = {'tipo': 'ratio_80_20', 'ratio': SPLIT_ENTRENAMIENTO_LEGACY}

    if len(fechas_train) < MIN_DIAS_TRAIN:
        raise ValueError(
            f"Insuficientes días de entrenamiento: {len(fechas_train)} días "
            f"(mínimo {MIN_DIAS_TRAIN}). Registre más ventas del padrón.")
    if len(fechas_test) < MIN_DIAS_TEST:
        raise ValueError(
            f"Insuficientes días de prueba: {len(fechas_test)} días "
            f"(mínimo {MIN_DIAS_TEST}).")

    # Índices de train/test sobre la secuencia completa de días operativos
    idx_train = [fechas.index(f) for f in fechas_train]
    idx_test = [fechas.index(f) for f in fechas_test]

    puntos = []
    metricas = {}
    metricas_baseline = {}
    importancias = {}
    estrategias_usadas = {}

    for tipo in TIPOS:
        vals = np.array([float(historia[f].get(tipo, 0.0)) for f in fechas])
        std_serie = float(np.std(vals)) if len(vals) else 0.0

        y_test = vals[idx_test]
        naive_full = _prediccion_naive(historia, fechas, tipo)
        naive_test = [naive_full[i] for i in idx_test]

        # ---- COM-93: estrategia por tipo ----
        if std_serie < UMBRAL_STD_CONSTANTE:
            # Serie constante (Cocinera): la media redondeada es la predicción óptima
            media_train = float(np.mean(vals[idx_train]))
            pred = [round(media_train) for _ in idx_test]
            estrategias_usadas[tipo] = 'constante'
            importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES]
        else:
            # Serie con señal: matriz de features POR TIPO sobre días operativos
            X_full = _matriz_features_por_tipo(historia, fechas, tipo)
            X_train = X_full[idx_train]
            X_test = X_full[idx_test]
            y_train = vals[idx_train]
            estrategias_usadas[tipo] = modelo_key
            if modelo_key == 'ensemble':
                pred = _prediccion_ensemble(X_train, X_test, y_train, naive_test)
                imp_rf = _importancias_de(X_train, y_train, 'rf')
                imp_gbm = _importancias_de(X_train, y_train, 'gbm')
                importancias[tipo] = [
                    {'variable': VARIABLES[j],
                     'importancia': round((imp_rf[j]['importancia'] + imp_gbm[j]['importancia']) / 2, 4)}
                    for j in range(len(VARIABLES))
                ]
            else:
                pred = _entrenar_modelo_individual(X_train, X_test, y_train, modelo_key)
                importancias[tipo] = _importancias_de(X_train, y_train, modelo_key)

        metricas[tipo] = _metricas_de(y_test, pred)
        metricas_baseline[tipo] = _metricas_de(y_test, naive_test)

        for f, re_, pr_ in zip(fechas_test, y_test, pred):
            puntos.append({
                'fecha': f.isoformat(),
                'tipo': tipo,
                'real': round(float(re_), 1),
                'predicho': round(float(pr_), 1),
            })

    info_split.update({
        'n_dias_train': len(fechas_train),
        'n_dias_test': len(fechas_test),
        'rango_train': [fechas_train[0].isoformat(), fechas_train[-1].isoformat()],
        'rango_test': [fechas_test[0].isoformat(), fechas_test[-1].isoformat()],
        'estrategias_usadas': estrategias_usadas,
    })

    return {
        'modelo': MODELOS_DISPONIBLES[modelo_key]['nombre'],
        'modelo_key': modelo_key,
        'variables': list(VARIABLES),
        'tipos': list(TIPOS),
        'n_dias_historial': len(fechas),
        'n_dias_entrenamiento': len(fechas_train),
        'n_dias_test': len(fechas_test),
        'rango_fechas': [fechas[0].isoformat(), fechas[-1].isoformat()],
        'metricas': metricas,
        'metricas_baseline': metricas_baseline,   # COM-93: piso naive para comparar
        'importancias': importancias,
        'puntos': puntos,
        'info_split': info_split,
    }


# COM-93: alias legacy del ratio 80/20 usado por los splits fallback
SPLIT_ENTRENAMIENTO_LEGACY = 0.80