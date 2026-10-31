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
COM-93: reingeniería de features por DÍA OPERATIVO y POR TIPO (lags 1/2/5,
medias móviles 5/10, desviación móvil, lags del total, calendario, flags
inicio/fin de mes y tendencia operativa), warm-start con media expansiva,
baseline naive en `metricas_baseline` y fix de `feature_importances_`.
Resultado medido COM-93 (test octubre): RF Social R² -0.02/MAPE 1.85%,
Afiliado R² -0.63/MAPE 11.58%, Normal R² -0.44/MAPE 20.36% (RF > GBM en todo).
COM-94 (este archivo): FEATURES ROBUSTAS ANTI-SPIKE + VENTANA DE PAGO:
* `roll_median5_op`: nivel reciente robusto (la mediana no se arrastra con los
  spikes de quincena, a diferencia de roll_mean5 que contaminaba 5 días).
* `ewma_op` (alpha=0.3): rastreador exponencial de nivel que decae un spike en
  2-3 días operativos, evitando que `lag1_op` lo propague intacto al día siguiente
  (caso medido: tras Afiliado=77 del vie 02/10, el mar 06/10 heredaba lag1=77
  contra un real de 56 -> error ~20 raciones que dominaba el SS_res).
* `ventana_pago`: flag único (dia<=5 OR dia>=28) que cubre la ventana completa de
  quincena/pago visible en los datos (Afiliado 77/76 el 02 y 05/10; Normal 8/14
  esos mismos días; semana del 28/09 con Afiliado 70.2 y Normal 11.4).
* `dist_dia_pago`: distancia numérica al día de pago más cercano (1 o 30); una
  sola variable continua permite al árbol cortar ej. `<=2` sin combinar 2 flags.
* Hiperparámetros: RF max_depth 12->9 y max_features 0.7->0.6 (menos overfitting
  al ruido de lags con ~160 días de train); GBM depth 3->2 y 250->180 iteraciones
  (su boosting secuencial perseguía residuales de spikes: R² -2.57 en Afiliado).
* Se conservan estrategias COM-93: 'constante' solo si std < 0.5 (Cocinera),
  baseline naive en `metricas_baseline`, splits y payload sin rupturas.
Uso: Importado por routers/modelos_ml.py. Entrenamiento bajo demanda (no persiste).
Referencia: tickets COM-5 v4 / HU-04 / COM-91 / COM-92 / COM-93 / COM-94 (trazabilidad).
"""
from datetime import date, datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal', 'cocinera')

# COM-94: nombres de las 18 features por tipo (orden = columnas de la matriz).
# Trazabilidad COM-93 (15 features): se agregan roll_median5_op, ewma_op,
# ventana_pago y dist_dia_pago al final-compatible (los índices anteriores
# no se reusan en payloads persistidos; las importancias se rotulan por nombre).
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

# COM-93/94: configuración de splits
MIN_DIAS_TRAIN = 30
MIN_DIAS_TEST = 5
FECHA_CORTE_DEFAULT = date(2026, 10, 1)
DIAS_TEST_DEFAULT = 30
SPLIT_ENTRENAMIENTO_LEGACY = 0.80

# COM-93: una serie es "constante" solo si su desviación es casi nula (Cocinera std=0)
UMBRAL_STD_CONSTANTE = 0.5

# COM-94: alpha del EWMA (0.3 = memoria corta, decae spikes en 2-3 días operativos)
EWMA_ALPHA = 0.3

# COM-94: hiperparámetros recalibrados (trazabilidad COM-93 en comentarios internos)
MODELOS_DISPONIBLES = {
    'rf': {
        'nombre': 'Random Forest',
        'clase': RandomForestRegressor,
        'params': {
            'n_estimators': 400,          # COM-93: 300
            'max_depth': 9,               # COM-93: 12 (overfitting al ruido de lags)
            'min_samples_leaf': 2,
            'max_features': 0.6,          # COM-93: 0.7
            'random_state': RANDOM_STATE,
            'n_jobs': -1,
        },
    },
    'gbm': {
        'nombre': 'Gradient Boosting',
        'clase': GradientBoostingRegressor,
        'params': {
            'n_estimators': 180,          # COM-93: 250 (boosting perseguía spikes)
            'learning_rate': 0.05,        # COM-93: 0.06
            'max_depth': 2,               # COM-93: 3
            'subsample': 0.8,             # COM-93: 0.9
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
# COM-94: FEATURES POR DÍA OPERATIVO, POR TIPO Y ROBUSTAS ANTI-SPIKE
# ==========================================
def _matriz_features_por_tipo(historia: dict, fechas: list, tipo: str) -> np.ndarray:
    """
    COM-93 + COM-94: matriz (len(fechas) x len(VARIABLES)) para UN tipo.
    Lags/medias sobre la SECUENCIA DE DÍAS OPERATIVOS (Lun-Vie): el "lag1" de un
    lunes es el viernes anterior, nunca un cero artificial. Warm-start con media
    expansiva cuando aún no hay pasado suficiente.
    COM-94 agrega estadísticos robustos y de ventana de pago:
    - roll_median5_op: mediana de los últimos 5 días operativos (no se arrastra
      con spikes, a diferencia de la media que contaminaba 5 días).
    - ewma_op: media exponencial (alpha=0.3) que decae un spike en 2-3 días.
    - ventana_pago: 1 si dia<=5 o dia>=28 (quincena completa observada en datos).
    - dist_dia_pago: min(|dia-1|, |dia-30|); variable continua para cortes finos.
    En producción es legítimo: al predecir un día, los reales anteriores ya están
    registrados en el padrón.
    """
    vals = [float(historia[f].get(tipo, 0.0)) for f in fechas]
    totals = [sum(float(v) for v in historia[f].values()) for f in fechas]
    media_global = float(np.mean(vals)) if vals else 0.0
    media_global_total = float(np.mean(totals)) if totals else 0.0

    # COM-94: EWMA hacia adelante sobre la serie operativa (solo pasado conocido)
    ewma_serie = []
    acc = None
    for i, v in enumerate(vals):
        if acc is None:
            acc = v
        else:
            acc = EWMA_ALPHA * v + (1.0 - EWMA_ALPHA) * acc
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
        roll_med5 = float(np.median(w5))                      # COM-94: robusto
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
# ventana de pago; quedó reemplazada por la versión COM-94 anterior.


def _prediccion_naive(historia: dict, fechas: list, tipo: str) -> list:
    """
    COM-93: baseline naive = valor del MISMO día operativo de la semana anterior
    (lag 5 operativo); si no existe, media expansiva. Piso de comparación en
    `metricas_baseline` y componente del ensemble.
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
# COM-93/94: HELPERS DE MODELOS INDIVIDUALES
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
    """COM-92 v2/93: ensemble 40% RF + 40% GBM + 20% naive semanal."""
    pred_rf = _entrenar_modelo_individual(X_train, X_test, y_train, 'rf')
    pred_gbm = _entrenar_modelo_individual(X_train, X_test, y_train, 'gbm')
    return [
        max(0.0, round(0.4 * rf + 0.4 * gbm + 0.2 * nv, 1))
        for rf, gbm, nv in zip(pred_rf, pred_gbm, naive_test)
    ]


# ==========================================
# ENTRENAMIENTO Y EVALUACIÓN (COM-94)
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None,
                          modelo_key='rf'):
    """
    COM-94: entrena el modelo elegido (rf / gbm / ensemble) con features POR TIPO,
    por DÍA OPERATIVO y robustas anti-spike. Payload del panel ML:
    - puntos, metricas (R²/MAE/MAPE), metricas_baseline (naive), importancias,
      info_split con estrategias usadas por tipo.
    Estrategias: 'constante' si std < 0.5 (Cocinera); resto modelo ML.
    Nota de interpretación (COM-93, vigente): en series casi constantes (Social,
    std≈1.8 sobre media≈19.3) el R² es inherentemente ≈0 aunque el MAPE sea ~1-2%:
    la varianza del test es mínima y cualquier error pequeño la consume. En esas
    series el indicador útil es el MAPE y la comparación contra el baseline naive.
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

        if std_serie < UMBRAL_STD_CONSTANTE:
            # Serie constante (Cocinera): la media redondeada es la predicción óptima
            media_train = float(np.mean(vals[idx_train]))
            pred = [round(media_train) for _ in idx_test]
            estrategias_usadas[tipo] = 'constante'
            importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES]
        else:
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
        'metricas_baseline': metricas_baseline,
        'importancias': importancias,
        'puntos': puntos,
        'info_split': info_split,
    }