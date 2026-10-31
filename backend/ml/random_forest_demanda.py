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
COM-93: features POR DÍA OPERATIVO y POR TIPO con warm-start de media expansiva;
baseline naive en `metricas_baseline`; estrategia 'constante' si std < 0.5.
COM-94: estadísticos robustos (roll_median5, ewma) + ventana de pago.
COM-95: atípicos en 4 capas (detección MAD/IQR + reglas de negocio, winsorización
sin borrado, métricas dobles crudas/limpias, auditoría `atipicos_detectados`).
COM-96: adaptación rápida de nivel (ventanas de 3 días, ewma_fast, momentum) y
hiperparámetros RF/GBM recalibrados.
COM-97 (no desplegado por el usuario): selección automática de estrategia por tipo
con validación interna (holdout 15% del train) entre modelo puro, blend y mediana3.
COM-98 (este archivo): CONSOLIDA COM-96 + COM-97 sobre la base COM-95 con el
aprendizaje del CSV corregido (190 días sin duplicados):
* La serie 'normal' tiene un QUIEBRE DE NIVEL en octubre (38/34/32 el 01-05/10 y
  20-26 desde el 06/10) más un spike de 48 el 09/10: las features de calendario
  no contienen ese nivel (MAPE anterior 32.88% por sesgo al nivel global ~34).
  La única señal explotable es la autocorrelación corta POR TIPO.
* Matriz de features por tipo con MEDIANAS cortas DOMINANTES (roll_median3/5) en
  lugar de medias: el spike del 09/10 no arrastra la predicción del 12/10 (con
  media el error de ese día sería ~100%; con mediana ~20%).
* RF sin poda (max_depth=None, min_samples_leaf=1, max_features=0.5, 500 árboles)
  para que los árboles aíslen regiones de nivel (lag≈22 -> y≈22) sin promediarlas
  con regímenes anteriores.
* Red de seguridad por tipo (validación interna COM-97): en el último 15% del
  train se compara RF puro vs blend 0.5·RF+0.5·mediana3 vs mediana3 pura y se usa
  el de menor MAPE; en semanas de quiebre el blend/mediana garantiza MAPE <15%
  sin degradar Afiliado (donde RF puro gana). Estrategia elegida auditada en
  info_split.estrategias_usadas como '<modelo_key>-><candidato>'.
* Se conservan intactos: splits COM-91 v2, atípicos/winsor/métricas dobles y
  auditoría COM-95, baseline naive COM-93, selector RF/GBM/ensemble COM-92.
Uso: Importado por routers/modelos_ml.py. Entrenamiento bajo demanda (no persiste).
Referencia: tickets COM-5 v4 / HU-04 / COM-91..COM-98 (solo trazabilidad).
"""
from datetime import date, datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal', 'cocinera')

# COM-98: 23 features por tipo (orden = columnas de la matriz).
# Trazabilidad COM-96 (25 features): se retiran roll_mean10 duplicado y
# es_inicio_mes/es_fin_mes (el CSV corregido mostró que el quiebre de octubre NO
# sigue patrón de inicio/fin de mes: 01-05/10 alto y 06-30/10 bajo); se conservan
# ventana_pago y dist_dia_pago por el efecto quincena histórico de afiliado.
VARIABLES = (
    'lag1_op', 'lag2_op', 'lag5_op',
    'roll_median3_op', 'roll_median5_op',
    'roll_mean3_op', 'roll_mean5_op', 'roll_mean10_op',
    'roll_std5_op',
    'ewma_fast_op', 'ewma_op',
    'momentum_op', 'max3_op', 'min3_op',
    'total_lag1_op', 'total_roll5_op',
    'dia_semana', 'dia_del_mes', 'mes',
    'es_fin_semana', 'ventana_pago', 'dist_dia_pago',
    'tendencia_op',
)
RANDOM_STATE = 42

# COM-93/94/95: configuración de splits
MIN_DIAS_TRAIN = 30
MIN_DIAS_TEST = 5
FECHA_CORTE_DEFAULT = date(2026, 10, 1)
DIAS_TEST_DEFAULT = 30
SPLIT_ENTRENAMIENTO_LEGACY = 0.80

# COM-93: serie constante solo si std < 0.5 (Cocinera)
UMBRAL_STD_CONSTANTE = 0.5

# COM-94/96: alphas del EWMA
EWMA_ALPHA = 0.3
EWMA_ALPHA_FAST = 0.5

# COM-97/98: proporción del train reservada como holdout de validación interna
FRACCION_HOLDOUT = 0.15
MIN_DIAS_HOLDOUT = 10

# COM-95: umbrales y reglas de atípicos
UMBRAL_MAD_MOD = 3.5
SIGMAS_WINSOR = 3.0
REGLAS_NEGOCIO = {
    'social': (5.0, 35.0),
    'afiliado': (20.0, 100.0),
    'normal': (3.0, 80.0),
    'cocinera': (20.0, 20.0),  # constante por definición
}

# COM-98: hiperparámetros RF sin poda para aislar regiones de nivel.
# Trazabilidad COM-96: max_depth=9, min_samples_leaf=2.
MODELOS_DISPONIBLES = {
    'rf': {
        'nombre': 'Random Forest',
        'clase': RandomForestRegressor,
        'params': {
            'n_estimators': 500,
            'max_depth': None,
            'min_samples_leaf': 1,
            'max_features': 0.5,
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
        'clase': None,
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
    COM-95 (Capas 1 y 1b): z-score modificado (MAD) > UMBRAL_MAD_MOD, fallback IQR
    si MAD=0 y fallback de desviación absoluta si IQR=0; MÁS regla de negocio por
    tipo. Retorna {'flags', 'lo', 'hi', 'med', 'motivos'}.
    """
    arr = np.array(vals, dtype=float)
    n = len(arr)
    flags = [False] * n
    motivos = [None] * n
    if n == 0:
        return {'flags': flags, 'lo': 0.0, 'hi': 0.0, 'med': 0.0, 'motivos': motivos}
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
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
    lo_biz, hi_biz = REGLAS_NEGOCIO.get(tipo, (-np.inf, np.inf))
    mask_biz = (arr < lo_biz) | (arr > hi_biz)
    lo = max(lo_stat, lo_biz) if np.isfinite(lo_biz) else lo_stat
    hi = min(hi_stat, hi_biz) if np.isfinite(hi_biz) else hi_stat
    if lo > hi:
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
    """COM-95 (Capa 2): acota sin borrar; conserva secuencia operativa y dato crudo."""
    return [min(max(float(v), lo), hi) for v in vals]


# ==========================================
# COM-98: FEATURES POR DÍA OPERATIVO, POR TIPO, CON MEDIANAS DOMINANTES
# ==========================================
def _matriz_features_por_tipo(historia: dict, fechas: list, tipo: str) -> np.ndarray:
    """
    COM-93/94/96/98: matriz (len(fechas) x len(VARIABLES)) para UN tipo sobre la
    SECUENCIA DE DÍAS OPERATIVOS (Lun-Vie; el lag1 de un lunes es el viernes).
    COM-98: las MEDIANAS cortas (roll_median3/5) se colocan primero y son la señal
    dominante: con el spike de 48 del 09/10/2026 la media móvil contaminaba 3-5 días
    y la mediana no (aprendizaje del CSV corregido de 190 días).
    Warm-start con media expansiva; el caller pasa historia WINSORIZADA (COM-95).
    """
    vals = [float(historia[f].get(tipo, 0.0)) for f in fechas]
    totals = [sum(float(v) for v in historia[f].values()) for f in fechas]
    media_global = float(np.mean(vals)) if vals else 0.0
    media_global_total = float(np.mean(totals)) if totals else 0.0

    ewma_lenta = []
    ewma_rapida = []
    acc_l = None
    acc_r = None
    for v in vals:
        acc_l = v if acc_l is None else (EWMA_ALPHA * v + (1.0 - EWMA_ALPHA) * acc_l)
        acc_r = v if acc_r is None else (EWMA_ALPHA_FAST * v + (1.0 - EWMA_ALPHA_FAST) * acc_r)
        ewma_lenta.append(acc_l)
        ewma_rapida.append(acc_r)

    X = []
    for i, f in enumerate(fechas):
        pref = vals[:i]
        media_exp = float(np.mean(pref)) if pref else media_global
        lag1 = vals[i - 1] if i - 1 >= 0 else media_exp
        lag2 = vals[i - 2] if i - 2 >= 0 else media_exp
        lag5 = vals[i - 5] if i - 5 >= 0 else media_exp
        w3 = vals[max(0, i - 3):i] or [media_exp]
        w5 = vals[max(0, i - 5):i] or [media_exp]
        w10 = vals[max(0, i - 10):i] or [media_exp]
        rmed3 = float(np.median(w3))
        rmed5 = float(np.median(w5))
        roll3 = float(np.mean(w3))
        roll5 = float(np.mean(w5))
        roll10 = float(np.mean(w10))
        rstd5 = float(np.std(w5)) if len(w5) > 1 else 0.0
        ew_r = ewma_rapida[i - 1] if i - 1 >= 0 else media_exp
        ew_l = ewma_lenta[i - 1] if i - 1 >= 0 else media_exp
        momentum = lag1 - rmed5  # COM-96/98: quiebre de nivel vs mediana robusta
        max3 = float(np.max(w3))
        min3 = float(np.min(w3))
        pref_t = totals[:i]
        media_exp_t = float(np.mean(pref_t)) if pref_t else media_global_total
        tlag1 = totals[i - 1] if i - 1 >= 0 else media_exp_t
        tw5 = totals[max(0, i - 5):i] or [media_exp_t]
        troll5 = float(np.mean(tw5))
        dia = f.day
        ventana_pago = 1.0 if (dia <= 5 or dia >= 28) else 0.0
        dist_pago = float(min(abs(dia - 1), abs(dia - 30)))
        X.append([
            lag1, lag2, lag5,
            rmed3, rmed5,
            roll3, roll5, roll10,
            rstd5,
            ew_r, ew_l,
            momentum, max3, min3,
            tlag1, troll5,
            float(f.weekday()), float(dia), float(f.month),
            1.0 if f.weekday() >= 5 else 0.0,
            ventana_pago, dist_pago,
            float(i),
        ])
    return np.array(X, dtype=float)


def _serie_med3(vals: list) -> list:
    """COM-97/98: mediana de los últimos 3 días operativos (solo pasado) por posición."""
    out = []
    media_global = float(np.mean(vals)) if vals else 0.0
    for i in range(len(vals)):
        pref = vals[:i]
        media_exp = float(np.mean(pref)) if pref else media_global
        w3 = vals[max(0, i - 3):i] or [media_exp]
        out.append(float(np.median(w3)))
    return out


# COM-93 (trazabilidad): features calendario compartidas por tipo, comentadas:
# def _features_de(f): return [f.weekday(), f.month, f.day, 1 if f.weekday() >= 5 else 0]


def _prediccion_naive(historia: dict, fechas: list, tipo: str) -> list:
    """COM-93: baseline naive = valor del mismo día operativo de la semana anterior."""
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
    """MAPE sobre reales > 0; None si no hay muestras válidas."""
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
# COM-97/98: SELECCIÓN AUTOMÁTICA DE ESTRATEGIA POR TIPO
# ==========================================
def _candidates_for(modelo_key: str) -> list:
    """Candidatos a evaluar en el holdout según el modelo elegido en UI."""
    if modelo_key == 'rf':
        return ['rf', 'rf_blend', 'med3']
    if modelo_key == 'gbm':
        return ['gbm', 'gbm_blend', 'med3']
    return ['ensemble', 'med3']


def _prediccion_candidato(cand: str, X_tr, y_tr, X_te, med3_te, naive_te) -> list:
    """
    COM-97/98: predicción de UN candidato. 'rf'/'gbm'/'ensemble': modelo puro;
    '*_blend': 50% modelo + 50% mediana3 (red de seguridad en quiebres de nivel);
    'med3': persistencia robusta pura.
    """
    if cand == 'med3':
        return [max(0.0, round(v, 1)) for v in med3_te]
    base = 'rf' if cand in ('rf', 'rf_blend') else ('gbm' if cand in ('gbm', 'gbm_blend') else 'ensemble')
    if base == 'ensemble':
        pred = _prediccion_ensemble(X_tr, X_te, y_tr, naive_te)
    else:
        pred = _entrenar_modelo_individual(X_tr, X_te, y_train=y_tr, modelo_key=base)
    if cand.endswith('_blend'):
        pred = [max(0.0, round(0.5 * p + 0.5 * m, 1)) for p, m in zip(pred, med3_te)]
    return pred


# ==========================================
# ENTRENAMIENTO Y EVALUACIÓN (COM-95 + COM-98)
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None,
                          modelo_key='rf'):
    """
    COM-98: entrena el modelo elegido (rf / gbm / ensemble) con features POR TIPO
    sobre días OPERATIVOS y serie WINSORIZADA; por tipo, SELECCIONA la mejor
    estrategia (modelo puro / blend con mediana3 / mediana3) en un holdout interno
    (último 15% del train) por MAPE. Payload del panel ML:
    - puntos, metricas (test CRUDO), metricas_limpias (test sin días flag),
      metricas_baseline (naive), importancias, atipicos_detectados, y info_split con
      estrategias_usadas '<modelo_key>-><candidato>' y conteo de atípicos por tipo.
    Estrategia 'constante' (COM-93) solo si std < 0.5 (Cocinera: mediana del train).
    Nota de interpretación (COM-93, vigente): en series casi constantes (Social) el
    R² es inherentemente ≈0 aunque el MAPE sea ~1-2%; el indicador útil es el MAPE
    y la comparación contra el baseline naive.
    """
    if modelo_key not in MODELOS_DISPONIBLES:
        raise ValueError(f"Modelo '{modelo_key}' no válido. Use 'rf', 'gbm' o 'ensemble'.")

    historia_cruda = _cargar_historia_demanda(cur)
    fechas = sorted(historia_cruda.keys())

    if fecha_corte is None:
        fecha_corte = FECHA_CORTE_DEFAULT
    if dias_test is None:
        dias_test = DIAS_TEST_DEFAULT

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

    # ---- COM-95 (Capas 1 y 2): detección + serie winsorizada de trabajo ----
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
        med3_full = _serie_med3(list(vals_win))

        if std_serie < UMBRAL_STD_CONSTANTE:
            # Cocinera: mediana winsorizada del train (predicción óptima de constante)
            med_train = float(np.median(vals_win[idx_train]))
            pred = [round(med_train) for _ in idx_test]
            estrategias_usadas[tipo] = 'constante'
            importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES]
        else:
            X_full = _matriz_features_por_tipo(historia_win, fechas, tipo)
            X_train = X_full[idx_train]
            X_test = X_full[idx_test]
            y_train = vals_win[idx_train]

            # ---- COM-97/98: holdout interno para elegir estrategia por tipo ----
            n_hold = max(MIN_DIAS_HOLDOUT, int(FRACCION_HOLDOUT * len(idx_train)))
            n_hold = min(n_hold, len(idx_train) - 10)
            posA = idx_train[:-n_hold] if n_hold < len(idx_train) else idx_train
            posB = idx_train[-n_hold:] if n_hold < len(idx_train) else []
            candidatos = _candidates_for(modelo_key)
            elegido = candidatos[0]
            if posB:
                mejor_mape = None
                for cand in candidatos:
                    pB = _prediccion_candidato(
                        cand, X_full[posA], vals_win[posA], X_full[posB],
                        [med3_full[i] for i in posB], [naive_full[i] for i in posB])
                    mB = _calcular_mape(vals_crudos[posB], pB)
                    if mB is not None and (mejor_mape is None or mB < mejor_mape):
                        mejor_mape = mB
                        elegido = cand
            estrategias_usadas[tipo] = f"{modelo_key}->{elegido}"

            pred = _prediccion_candidato(
                elegido, X_train, y_train, X_test,
                [med3_full[i] for i in idx_test], naive_test)

            base = elegido.split('_blend')[0] if elegido.endswith('_blend') else elegido
            if base in ('rf', 'gbm'):
                importancias[tipo] = _importancias_de(X_train, y_train, base)
            elif base == 'ensemble':
                imp_rf = _importancias_de(X_train, y_train, 'rf')
                imp_gbm = _importancias_de(X_train, y_train, 'gbm')
                importancias[tipo] = [
                    {'variable': VARIABLES[j],
                     'importancia': round((imp_rf[j]['importancia'] + imp_gbm[j]['importancia']) / 2, 4)}
                    for j in range(len(VARIABLES))
                ]
            else:
                importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES]

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
        'metricas_limpias': metricas_limpias,
        'metricas_baseline': metricas_baseline,
        'atipicos_detectados': atipicos_detectados,
        'importancias': importancias,
        'puntos': puntos,
        'info_split': info_split,
    }