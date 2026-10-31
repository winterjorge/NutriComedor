"""
ml/random_forest_demanda.py
Objetivo: Modelos de demanda diaria de comensales (social / afiliado / normal /
cocinera) para el panel de gráficos de Machine Learning (COM-5 v4 / COM-8 v7).
Entrena con el historial del padrón/ventas y devuelve los datos del gráfico de
dispersión REAL vs PREDICHO con split temporal configurable, métricas
R²/MAE/MAPE por tipo (crudas y limpias), baseline naive de referencia, auditoría
de atípicos y la relevancia de cada variable (feature importances).
Historial:
COM-5 v4 / COM-8 v7: versión original con RF y split 80/20 (4 features calendario).
COM-91: se agrega MAPE por tipo de comensal.
COM-91 v2: split temporal configurable (evaluacion por fecha fija / produccion
expanding window / fallback ratio).
COM-92: selector de modelo (RF vs GBM) vía parámetro modelo_key + ensemble.
COM-93: features POR DÍA OPERATIVO y POR TIPO (lags 1/2/5, medias móviles, lags del
total, calendario, tendencia) con warm-start de media expansiva; baseline naive en
`metricas_baseline`; estrategia 'constante' para series con std < 0.5 (Cocinera).
COM-94: features robustas anti-spike (roll_median5_op, ewma_op) + ventana de pago
(ventana_pago, dist_dia_pago); hiperparámetros RF/GBM recalibrados.
COM-95 (este archivo): TRATAMIENTO DE ATÍPICOS EN 4 CAPAS (registro manual/CSV
sujeto a error o manipulación; NUNCA se borra el dato):
* Capa 1 DETECCIÓN: z-score modificado (MAD, Iglewicz & Hoaglin) > 3.5 por tipo;
  fallback IQR si MAD=0 (series casi constantes) y fallback de desviación
  absoluta si IQR=0; MÁS reglas de negocio por tipo (rangos operativos del
  comedor: social 5-35, afiliado 20-100, normal 3-80, cocinera=20 exacto).
* Capa 2 WINSORIZACIÓN: el valor atípico se ACOTA al límite robusto (intersección
  del límite estadístico con el de negocio) para los targets de entrenamiento Y
  para las features/lags (el spike del 02/10 ya no envenena lag1_op del 05/10).
  El día NO se elimina: se conserva la secuencia operativa y el dato crudo en BD.
* Capa 3 MÉTRICAS DOBLES: `metricas` sobre test CRUDO (lo que ve operación) y
  `metricas_limpias` sobre test excluyendo días flag (calidad real del modelo,
  argumento de tesis: varianza explicada descontando errores de registro).
* Capa 4 AUDITORÍA: `atipicos_detectados` en el payload (fecha, tipo, valor real,
  valor acotado, límites, motivo) para que el panel ML liste los registros a
  verificar en el libro de ventas; decisión humana, no del algoritmo.
* Trazabilidad: estrategias, baseline naive, splits y payload COM-94 intactos;
  se agregan claves nuevas sin romper consumidores existentes.
Uso: Importado por routers/modelos_ml.py. Entrenamiento bajo demanda (no persiste).
Referencia: tickets COM-5 v4 / HU-04 / COM-91 / COM-92 / COM-93 / COM-94 / COM-95.
"""
from datetime import date, datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal', 'cocinera')

# COM-94: 19 features por tipo sobre días operativos (orden = columnas de la matriz).
# Trazabilidad COM-91 v2/COM-92 (4 features calendario): dia_semana, mes,
# dia_del_mes, es_fin_de_semana. COM-93 agregó lags/medias por día operativo.
# COM-94 agregó roll_median5_op, ewma_op, ventana_pago y dist_dia_pago.
VARIABLES = (
    'lag1_op', 'lag2_op', 'lag5_op',
    'roll_mean5_op', 'roll_mean10_op', 'roll_std5_op',
    'roll_median5_op', 'ewma_op',
    'total_lag1_op', 'total_roll5_op',
    'dia_semana', 'dia_del_mes', 'mes',
    'es_fin_semana', 'es_inicio_mes', 'es_fin_mes',
    'ventana_pago', 'dist_dia_pago',
    'tendencia_op',
)
RANDOM_STATE = 42

# COM-93/94/95: configuración de splits
MIN_DIAS_TRAIN = 60
MIN_DIAS_TEST = 5
FECHA_CORTE_DEFAULT = date(2026, 10, 1)
DIAS_TEST_DEFAULT = 30
SPLIT_ENTRENAMIENTO_LEGACY = 0.80

# COM-93: una serie es "constante" solo si su desviación es casi nula (Cocinera std=0)
UMBRAL_STD_CONSTANTE = 0.5

# COM-94: alpha del EWMA (0.3 = memoria corta, decae spikes en 2-3 días operativos)
EWMA_ALPHA = 0.3

# ==========================================
# COM-95: UMBRALES Y REGLAS DE ATÍPICOS
# ==========================================
# Z-score modificado (0.6745*(x-med)/MAD): umbral clásico de Iglewicz & Hoaglin.
UMBRAL_MAD_MOD = 3.5
# Sigmas del límite de winsorización sobre la sigma robusta (1.4826*MAD).
SIGMAS_WINSOR = 3.0
# Reglas de negocio por tipo (rangos operativos del comedor piloto; si un valor
# cae fuera es candidato a error de registro manual o manipulación).
REGLAS_NEGOCIO = {
    'social': (5.0, 35.0),
    'afiliado': (20.0, 100.0),
    'normal': (3.0, 80.0),
    'cocinera': (20.0, 20.0),  # constante por definición: cualquier otro valor es error
}

# COM-92 / COM-94: hiperparámetros por modelo (rf/gbm) y ensemble.
MODELOS_DISPONIBLES = {
    'rf': {
        'nombre': 'Random Forest',
        'clase': RandomForestRegressor,
        'params': {
            'n_estimators': 400,
            'max_depth': 9,
            'min_samples_leaf': 2,
            'max_features': 0.6,
            'random_state': RANDOM_STATE,
            'n_jobs': -1,
        },
    },
    'gbm': {
        'nombre': 'Gradient Boosting',
        'clase': GradientBoostingRegressor,
        'params': {
            'n_estimators': 180,
            'learning_rate': 0.05,
            'max_depth': 2,
            'subsample': 0.8,
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
    agregado por día. Detecta si el tipo vive en la tabla de ventas o se obtiene
    por join con la tabla de comensales.
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
# COM-95: DETECCIÓN ROBUSTA DE ATÍPICOS + WINSORIZACIÓN
# ==========================================
def _detectar_atipicos_serie(vals: list, tipo: str) -> dict:
    """
    COM-95 (Capas 1 y 1b): detecta atípicos en UNA serie por tipo con:
    * Z-score modificado (MAD): |0.6745*(x-med)/MAD| > UMBRAL_MAD_MOD.
    * Fallback IQR (Q1-1.5*IQR, Q3+1.5*IQR) si MAD=0 (serie casi constante).
    * Fallback de desviación absoluta |x-med| > max(2, 0.15*med) si IQR=0.
    * Regla de negocio: valor fuera de REGLAS_NEGOCIO[tipo].
    Retorna {'flags': [bool], 'lo': float, 'hi': float, 'med': float,
             'motivos': [str|None]} donde lo/hi son los límites de winsorización
    (intersección del límite estadístico con el de negocio) y motivos indica por
    qué se flaggeó cada posición ('mad', 'iqr', 'desv_abs', 'regla_negocio' o
    combinaciones, None si no es atípico).
    """
    arr = np.array(vals, dtype=float)
    n = len(arr)
    flags = [False] * n
    motivos = [None] * n
    if n == 0:
        return {'flags': flags, 'lo': 0.0, 'hi': 0.0, 'med': 0.0, 'motivos': motivos}
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    # ---- Límite estadístico y flag por dispersión robusta ----
    if mad > 0:
        sigma = 1.4826 * mad
        z = np.abs(arr - med) / sigma
        mask_stat = z > UMBRAL_MAD_MOD
        lo_stat = med - SIGMAS_WINSOR * sigma
        hi_stat = med + SIGMAS_WINSOR * sigma
        motivo_stat = 'mad'
    else:
        q1, q3 = np.percentile(arr, [25, 75])
        iqr = q3 - q1
        if iqr > 0:
            mask_stat = (arr < q1 - 1.5 * iqr) | (arr > q3 + 1.5 * iqr)
            lo_stat = q1 - 1.5 * iqr
            hi_stat = q3 + 1.5 * iqr
            motivo_stat = 'iqr'
        else:
            tol = max(2.0, 0.15 * med)
            mask_stat = np.abs(arr - med) > tol
            lo_stat = med - tol
            hi_stat = med + tol
            motivo_stat = 'desv_abs'
    # ---- Regla de negocio por tipo ----
    lo_biz, hi_biz = REGLAS_NEGOCIO.get(tipo, (-np.inf, np.inf))
    mask_biz = (arr < lo_biz) | (arr > hi_biz)
    # ---- Límites finales de winsorización: intersección estadístico ∩ negocio ----
    lo = max(lo_stat, lo_biz) if np.isfinite(lo_biz) else lo_stat
    hi = min(hi_stat, hi_biz) if np.isfinite(hi_biz) else hi_stat
    if lo > hi:  # guarda: si la intersección degenera, se usa el límite estadístico
        lo, hi = lo_stat, hi_stat
    for i in range(n):
        m_stat = bool(mask_stat[i])
        m_biz = bool(mask_biz[i])
        if m_stat or m_biz:
            flags[i] = True
            motivos[i] = '+'.join(
                [m for m, ok in ((motivo_stat, m_stat), ('regla_negocio', m_biz)) if ok])
    return {'flags': flags, 'lo': float(lo), 'hi': float(hi), 'med': med, 'motivos': motivos}


def _winsorizar_serie(vals: list, lo: float, hi: float) -> list:
    """
    COM-95 (Capa 2): acota cada valor al intervalo [lo, hi]. El día NO se elimina:
    se conserva la secuencia operativa (los lags no se rompen) y el dato crudo
    permanece en BD y en `metricas` para auditoría.
    """
    return [min(max(float(v), lo), hi) for v in vals]


# ==========================================
# COM-93/94: FEATURES POR DÍA OPERATIVO, POR TIPO Y ROBUSTAS
# ==========================================
def _matriz_features_por_tipo(historia: dict, fechas: list, tipo: str) -> np.ndarray:
    """
    COM-93 + COM-94: matriz (len(fechas) x len(VARIABLES)) para UN tipo.
    Lags/medias sobre la SECUENCIA DE DÍAS OPERATIVOS (nunca ceros de domingos).
    COM-95: el caller pasa `historia` ya WINSORIZADO, de modo que los spikes
    acotados no envenenen lag1_op/roll_mean5_op/etc. del entrenamiento.
    Warm-start con media expansiva cuando aún no hay pasado suficiente.
    """
    vals = [float(historia[f].get(tipo, 0.0)) for f in fechas]
    totals = [sum(float(v) for v in historia[f].values()) for f in fechas]
    media_global = float(np.mean(vals)) if vals else 0.0
    media_global_total = float(np.mean(totals)) if totals else 0.0

    # COM-94: EWMA hacia adelante sobre la serie operativa (solo pasado conocido)
    ewma_serie = []
    acc = None
    for v in vals:
        acc = v if acc is None else (EWMA_ALPHA * v + (1.0 - EWMA_ALPHA) * acc)
        ewma_serie.append(acc)

    X = []
    for i, f in enumerate(fechas):
        pref = vals[:i]
        media_exp = float(np.mean(pref)) if pref else media_global
        # Lags propios por día operativo
        lag1 = vals[i - 1] if i - 1 >= 0 else media_exp
        lag2 = vals[i - 2] if i - 2 >= 0 else media_exp
        lag5 = vals[i - 5] if i - 5 >= 0 else media_exp
        # Ventanas móviles (solo pasado)
        w5 = vals[max(0, i - 5):i] or [media_exp]
        w10 = vals[max(0, i - 10):i] or [media_exp]
        roll5 = float(np.mean(w5))
        roll10 = float(np.mean(w10))
        roll_std5 = float(np.std(w5)) if len(w5) > 1 else 0.0
        roll_med5 = float(np.median(w5))                       # COM-94: robusto
        ewma = ewma_serie[i - 1] if i - 1 >= 0 else media_exp  # COM-94: EWMA del pasado
        # Lags del TOTAL por día operativo
        pref_t = totals[:i]
        media_exp_t = float(np.mean(pref_t)) if pref_t else media_global_total
        tlag1 = totals[i - 1] if i - 1 >= 0 else media_exp_t
        tw5 = totals[max(0, i - 5):i] or [media_exp_t]
        troll5 = float(np.mean(tw5))
        # Calendario + ventana de pago (COM-94) + tendencia operativa
        dia = f.day
        ventana_pago = 1.0 if (dia <= 5 or dia >= 28) else 0.0
        dist_pago = float(min(abs(dia - 1), abs(dia - 30)))
        X.append([
            lag1, lag2, lag5,
            roll5, roll10, roll_std5,
            roll_med5, ewma,
            tlag1, troll5,
            float(f.weekday()), float(dia), float(f.month),
            1.0 if f.weekday() >= 5 else 0.0,
            1.0 if dia <= 5 else 0.0,
            1.0 if dia >= 26 else 0.0,
            ventana_pago, dist_pago,
            float(i),
        ])
    return np.array(X, dtype=float)


# COM-93 (trazabilidad): matriz de 15 features sin estadísticos robustos ni
# ventana de pago; reemplazada por la versión COM-94/95 anterior.


def _prediccion_naive(historia: dict, fechas: list, tipo: str) -> list:
    """
    COM-93: baseline naive = valor del MISMO día operativo de la semana anterior
    (lag 5 operativo); si no existe, media expansiva. Piso de comparación en
    `metricas_baseline` y componente del ensemble. COM-95: opera sobre la serie
    winsorizada que recibe el caller.
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
# COM-91: MAPE Y MÉTRICAS
# ==========================================
def _calcular_mape(real, predicho):
    """MAPE = (1/n) * Σ|(real - predicho)/real| * 100 sobre reales > 0; None si no hay."""
    real = np.array(real, dtype=float)
    predicho = np.array(predicho, dtype=float)
    mascara = real > 0
    if not mascara.any():
        return None
    rf_ = real[mascara]
    pf_ = predicho[mascara]
    return float(np.mean(np.abs((rf_ - pf_) / rf_)) * 100)


def _metricas_de(real, pred) -> dict:
    """R²/MAE/MAPE redondeados de un par real/predicho."""
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
# COM-92/94: HELPERS DE MODELOS INDIVIDUALES
# ==========================================
def _entrenar_modelo_individual(X_train, X_test, y_train, modelo_key: str) -> list:
    """Entrena RF o GBM sobre la matriz del tipo y devuelve predicciones >= 0."""
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, y_train)
    pred = modelo.predict(X_test)
    return [max(0.0, round(float(p), 1)) for p in pred]


def _importancias_de(X_train, y_train, modelo_key: str) -> list:
    """Importancias en formato dict (fix COM-93: `feature_importances_`)."""
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, y_train)
    return [
        {'variable': VARIABLES[j], 'importancia': round(float(v), 4)}
        for j, v in enumerate(modelo.feature_importances_)
    ]


def _prediccion_ensemble(X_train, X_test, y_train, naive_test) -> list:
    """COM-92/93: ensemble 40% RF + 40% GBM + 20% naive semanal."""
    pred_rf = _entrenar_modelo_individual(X_train, X_test, y_train, 'rf')
    pred_gbm = _entrenar_modelo_individual(X_train, X_test, y_train, 'gbm')
    return [
        max(0.0, round(0.4 * rf + 0.4 * gbm + 0.2 * nv, 1))
        for rf, gbm, nv in zip(pred_rf, pred_gbm, naive_test)
    ]


# ==========================================
# ENTRENAMIENTO Y EVALUACIÓN (COM-95)
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None,
                          modelo_key='rf'):
    """
    COM-95: entrena el modelo elegido (rf / gbm / ensemble) con features POR TIPO
    sobre días OPERATIVOS, serie WINSORIZADA para entrenamiento/features y doble
    lectura de métricas (cruda y limpia) + auditoría de atípicos.
    Payload del panel ML:
    - puntos, metricas (R²/MAE/MAPE sobre test CRUDO), metricas_limpias (test sin
      días flag), metricas_baseline (naive), importancias, info_split con
      estrategias y conteo de atípicos por tipo, y atipicos_detectados (Capa 4).
    Estrategias por tipo (COM-93, vigente): 'constante' si std < 0.5 (Cocinera,
    usando la MEDIANA winsorizada); resto modelo ML / ensemble.
    Nota de interpretación (COM-93, vigente): en series casi constantes (Social)
    el R² es inherentemente ≈0 aunque el MAPE sea ~1-2%; el indicador útil ahí es
    el MAPE y la comparación contra el baseline naive.
    """
    if modelo_key not in MODELOS_DISPONIBLES:
        raise ValueError(f"Modelo '{modelo_key}' no válido. Use 'rf', 'gbm' o 'ensemble'.")

    historia_cruda = _cargar_historia_demanda(cur)
    fechas = sorted(historia_cruda.keys())

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

    idx_train = [fechas.index(f) for f in fechas_train]
    idx_test = [fechas.index(f) for f in fechas_test]

    # ==========================================
    # COM-95 (Capas 1 y 2): detección por tipo + serie winsorizada de trabajo
    # ==========================================
    historia_win = {f: {t: 0.0 for t in TIPOS} for f in fechas}
    atipicos_detectados = []
    flags_por_tipo = {}
    n_atipicos_por_tipo = {}
    for tipo in TIPOS:
        vals_crudos = [float(historia_cruda[f].get(tipo, 0.0)) for f in fechas]
        det = _detectar_atipicos_serie(vals_crudos, tipo)
        vals_win = _winsorizar_serie(vals_crudos, det['lo'], det['hi'])
        flags_por_tipo[tipo] = det['flags']
        n_atipicos_por_tipo[tipo] = int(sum(1 for fl in det['flags'] if fl))
        for i, f in enumerate(fechas):
            historia_win[f][tipo] = vals_win[i]
            if det['flags'][i]:
                atipicos_detectados.append({
                    'fecha': f.isoformat(),
                    'tipo': tipo,
                    'valor_real': vals_crudos[i],
                    'valor_acotado': vals_win[i],
                    'limite_inf': round(det['lo'], 2),
                    'limite_sup': round(det['hi'], 2),
                    'motivo': det['motivos'][i],
                })
        # Los demás tipos se copian crudos=winsorizados si no tuvieron flags
        for i, f in enumerate(fechas):
            for otro in TIPOS:
                if otro != tipo:
                    historia_win[f][otro] = float(historia_cruda[f].get(otro, 0.0))
    atipicos_detectados.sort(key=lambda a: (a['fecha'], a['tipo']))

    puntos = []
    metricas = {}
    metricas_limpias = {}
    metricas_baseline = {}
    importancias = {}
    estrategias_usadas = {}

    for tipo in TIPOS:
        vals_crudos = np.array([float(historia_cruda[f].get(tipo, 0.0)) for f in fechas])
        vals_win = np.array([historia_win[f][tipo] for f in fechas])
        std_serie = float(np.std(vals_win)) if len(vals_win) else 0.0

        y_test_crudo = vals_crudos[idx_test]
        naive_full = _prediccion_naive(historia_win, fechas, tipo)
        naive_test = [naive_full[i] for i in idx_test]

        # ---- COM-93: estrategia por tipo (constante solo si std < 0.5) ----
        if std_serie < UMBRAL_STD_CONSTANTE:
            # Cocinera: la MEDIANA winsorizada del train es la predicción óptima
            med_train = float(np.median(vals_win[idx_train]))
            pred = [round(med_train) for _ in idx_test]
            estrategias_usadas[tipo] = 'constante'
            importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES]
        else:
            # COM-95: features y targets sobre la serie WINSORIZADA
            X_full = _matriz_features_por_tipo(historia_win, fechas, tipo)
            X_train = X_full[idx_train]
            X_test = X_full[idx_test]
            y_train = vals_win[idx_train]
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

        # ---- COM-95 (Capa 3): métricas CRUDAS y LIMPIAS ----
        metricas[tipo] = _metricas_de(y_test_crudo, pred)
        metricas_baseline[tipo] = _metricas_de(y_test_crudo, naive_test)
        flags_test = [flags_por_tipo[tipo][i] for i in idx_test]
        mask_limpios = [j for j, fl in enumerate(flags_test) if not fl]
        if len(mask_limpios) >= 3:
            metricas_limpias[tipo] = _metricas_de(
                [y_test_crudo[j] for j in mask_limpios],
                [pred[j] for j in mask_limpios])
        else:
            metricas_limpias[tipo] = None

        for f, re_, pr_ in zip(fechas_test, y_test_crudo, pred):
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
        # COM-95: conteo de atípicos detectados por tipo (auditoría del split)
        'n_atipicos_por_tipo': n_atipicos_por_tipo,
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
        'metricas_limpias': metricas_limpias,      # COM-95 (Capa 3)
        'metricas_baseline': metricas_baseline,    # COM-93
        'atipicos_detectados': atipicos_detectados,  # COM-95 (Capa 4)
        'importancias': importancias,
        'puntos': puntos,
        'info_split': info_split,
    }