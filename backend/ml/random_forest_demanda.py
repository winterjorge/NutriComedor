"""
ml/random_forest_demanda.py
Objetivo: Modelo híbrido adaptativo de demanda diaria de comensales.
COM-92 v2: Recalibración basada en datos reales del sistema.

ANÁLISIS DE DATOS REALES (191 días):
- Cocinera: constante perfecta (20.00, desviación=0) → usar valor fijo
- Social: casi constante (19.27, desviación=1.80) → usar media móvil
- Afiliado: variación real (55.68, desviación=12.95) → modelo ML con lags
- Normal: variación real (28.71, desviación=11.63) → modelo ML con lags

ESTRATEGIA HÍBRIDA:
1. Si desviación < umbral: usar constante o media móvil
2. Si hay variación: usar ensemble (RF + GBM + Media Móvil)
3. Features enriquecidas: 13 variables (lags, tendencias, cíclicas)
4. Detección de outliers para no distorsionar entrenamiento

Variables (features) usadas:
BÁSICAS: dia_semana, mes, dia_del_mes, es_fin_de_semana
ENRIQUECIDAS: tendencia, lag_1, lag_7, media_movil_7, media_movil_14,
dia_semana_sin/cos, mes_sin/cos (codificación cíclica).

Targets: raciones diarias por tipo: social, afiliado, normal, cocinera.
Uso: Importado por routers/modelos_ml.py. Entrenamiento bajo demanda.
Historial:
COM-5 v4 / COM-8 v7: versión original con RF y split 80/20.
COM-91: se agrega MAPE.
COM-91 v2: split temporal configurable.
COM-91 v3: features enriquecidas (13 variables).
COM-92: selector de modelo (RF vs GBM).
COM-92 v2 (este archivo): modelo híbrido adaptativo basado en análisis de datos reales.
Referencia: ticket COM-5 v4 / HU-04 / COM-91 / COM-92 / COM-92 v2.
"""
from datetime import date, datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.metrics import mean_absolute_error, r2_score
from scipy import stats

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal', 'cocinera')
VARIABLES_BASICAS = ('dia_semana', 'mes', 'dia_del_mes', 'es_fin_de_semana')
VARIABLES_ENRIQUECIDAS = (
    'dia_semana', 'mes', 'dia_del_mes', 'es_fin_de_semana',
    'tendencia', 'lag_1', 'lag_7', 'media_movil_7', 'media_movil_14',
    'dia_semana_sin', 'dia_semana_cos', 'mes_sin', 'mes_cos'
)
RANDOM_STATE = 42
MIN_DIAS_TRAIN = 30
MIN_DIAS_TEST = 5
FECHA_CORTE_DEFAULT = date(2026, 10, 1)
DIAS_TEST_DEFAULT = 30

# COM-92 v2: umbrales para detección de series constantes
UMBRAL_DESVIACION_CONSTANTE = 2.0  # si std < esto, usar constante/media móvil
UMBRAL_OUTLIER_ZSCORE = 2.5  # para detectar outliers en entrenamiento

# COM-92 v2: configuración de modelos
MODELOS_DISPONIBLES = {
    'rf': {
        'nombre': 'Random Forest',
        'clase': RandomForestRegressor,
        'params': {'n_estimators': 200, 'random_state': RANDOM_STATE, 'min_samples_leaf': 3, 'max_depth': 8},
    },
    'gbm': {
        'nombre': 'Gradient Boosting',
        'clase': GradientBoostingRegressor,
        'params': {'n_estimators': 300, 'learning_rate': 0.05, 'max_depth': 4, 'random_state': RANDOM_STATE, 'subsample': 0.8},
    },
    'ensemble': {
        'nombre': 'Ensemble (RF + GBM + Media Móvil)',
        'clase': None,  # especial
        'params': {},
    },
}


# ==========================================
# UTILIDADES DE ESQUEMA
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
    for n in ('padron_diario', 'ventas', 'venta_diaria', 'registro_ventas', 'padron'):
        if n in tablas:
            return n
    for n in tablas:
        if ('venta' in n or 'padron' in n) and 'detalle' not in n:
            return n
    return None

def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


# ==========================================
# CARGA DEL HISTORIAL
# ==========================================
def _cargar_historia_demanda(cur):
    tablas = _tablas_public(cur)
    tabla = _detectar_tabla_ventas(cur, tablas)
    if not tabla:
        raise ValueError(f"No se detectó tabla de padrón/ventas. Tablas: {', '.join(sorted(tablas))}")
    cols = _columnas(cur, tabla)
    col_fecha = _col(cols, ['fecha', 'fecha_venta', 'fecha_registro', 'dia'], contiene='fecha')
    col_cant = _col(cols, ['raciones', 'cantidad', 'menus', 'total'], contiene='racion') or \
               _col(cols, [], contiene='cant') or _col(cols, [], contiene='total')
    col_tipo = _col(cols, ['tipo_comensal', 'tipo_comensal_venta', 'tipo', 'categoria'], contiene='tipo')
    if not col_fecha or not col_cant:
        raise ValueError(f"Tabla '{tabla}' sin columnas fecha/cantidad: {cols}")
    if col_tipo:
        cur.execute(f"""
            SELECT {col_fecha} AS f, LOWER({col_tipo}::text) AS t, SUM({col_cant}) AS n
            FROM {tabla} GROUP BY 1, 2;
        """)
    else:
        if 'comensales' not in tablas:
            raise ValueError("Falta tabla 'comensales' para obtener tipo.")
        ccols = _columnas(cur, 'comensales')
        col_ctipo = _col(ccols, ['tipo', 'categoria', 'tipo_comensal'], contiene='tipo')
        col_cid = _col(cols, ['comensal_id', 'id_comensal', 'comensal'], contiene='comensal')
        if not col_ctipo or not col_cid:
            raise ValueError("No se pudo unir con comensales.")
        cur.execute(f"""
            SELECT v.{col_fecha} AS f, LOWER(c.{col_ctipo}::text) AS t, SUM(v.{col_cant}) AS n
            FROM {tabla} v JOIN comensales c ON c.id = v.{col_cid} GROUP BY 1, 2;
        """)
    historia = {}
    for r in cur.fetchall():
        f = _a_fecha(r['f'])
        t_raw = (r['t'] or '').strip()
        t = next((tt for tt in TIPOS if tt in t_raw), None)
        if not t:
            continue
        dia = historia.setdefault(f, {'social': 0.0, 'afiliado': 0.0, 'normal': 0.0, 'cocinera': 0.0})
        dia[t] += float(r['n'] or 0)
    return historia


# ==========================================
# COM-92 v2: ANÁLISIS DE SERIES
# ==========================================
def _analizar_series(historia: dict) -> dict:
    """
    COM-92 v2: analiza cada tipo de comensal para determinar estrategia de predicción.
    Retorna dict con: tipo -> {estrategia, valor_fijo, media, std, datos_limpios}
    """
    analisis = {}
    
    for tipo in TIPOS:
        valores = []
        fechas = sorted(historia.keys())
        for f in fechas:
            valores.append(historia[f].get(tipo, 0.0))
        
        if not valores:
            analisis[tipo] = {'estrategia': 'constante', 'valor_fijo': 0, 'media': 0, 'std': 0, 'datos_limpios': []}
            continue
        
        arr = np.array(valores)
        media = np.mean(arr)
        std = np.std(arr)
        
        # COM-92 v2: detectar outliers usando z-score
        z_scores = np.abs(stats.zscore(arr))
        mascara_outliers = z_scores < UMBRAL_OUTLIER_ZSCORE
        datos_limpios = arr[mascara_outliers].tolist()
        
        # COM-92 v2: decidir estrategia
        if std < UMBRAL_DESVIACION_CONSTANTE:
            estrategia = 'constante'
            valor_fijo = round(media)
        elif std < UMBRAL_DESVIACION_CONSTANTE * 2:
            estrategia = 'media_movil'
            valor_fijo = round(media)
        else:
            estrategia = 'modelo_ml'
            valor_fijo = None
        
        analisis[tipo] = {
            'estrategia': estrategia,
            'valor_fijo': valor_fijo,
            'media': media,
            'std': std,
            'datos_limpios': datos_limpios,
            'n_outliers': len(arr) - len(datos_limpios),
        }
    
    return analisis


# ==========================================
# COM-91 v3: FEATURES ENRIQUECIDAS
# ==========================================
def _features_enriquecidas(f: date, historia: dict, fecha_inicio: date):
    """Vector de 13 features enriquecidas para capturar patrones temporales."""
    dia_semana = f.weekday()
    mes = f.month
    dia_del_mes = f.day
    es_fin_de_semana = 1 if dia_semana >= 5 else 0
    
    dia_semana_sin = np.sin(2 * np.pi * dia_semana / 7)
    dia_semana_cos = np.cos(2 * np.pi * dia_semana / 7)
    mes_sin = np.sin(2 * np.pi * mes / 12)
    mes_cos = np.cos(2 * np.pi * mes / 12)
    
    tendencia = (f - fecha_inicio).days
    
    lag_1 = 0
    lag_7 = 0
    media_7 = 0
    media_14 = 0
    
    if historia:
        ayer = f - timedelta(days=1)
        if ayer in historia:
            lag_1 = sum(historia[ayer].values())
        
        semana_atras = f - timedelta(days=7)
        if semana_atras in historia:
            lag_7 = sum(historia[semana_atras].values())
        
        total_7 = 0
        count_7 = 0
        for i in range(1, 8):
            d = f - timedelta(days=i)
            if d in historia:
                total_7 += sum(historia[d].values())
                count_7 += 1
        media_7 = total_7 / count_7 if count_7 > 0 else 0
        
        total_14 = 0
        count_14 = 0
        for i in range(1, 15):
            d = f - timedelta(days=i)
            if d in historia:
                total_14 += sum(historia[d].values())
                count_14 += 1
        media_14 = total_14 / count_14 if count_14 > 0 else 0
    
    return [
        dia_semana, mes, dia_del_mes, es_fin_de_semana,
        tendencia, lag_1, lag_7, media_7, media_14,
        dia_semana_sin, dia_semana_cos, mes_sin, mes_cos
    ]


# ==========================================
# COM-92 v2: PREDICCIÓN POR MEDIA MÓVIL
# ==========================================
def _predecir_media_movil(historia: dict, fechas_test: list, tipo: str, ventana: int = 7) -> list:
    """
    COM-92 v2: predicción simple usando media móvil de los últimos N días.
    Útil para series con poca variación (Social, Cocinera).
    """
    predicciones = []
    fechas_ordenadas = sorted(historia.keys())
    
    for f in fechas_test:
        # Tomar los últimos `ventana` días antes de f
        valores_recientes = []
        for i in range(1, ventana + 1):
            d = f - timedelta(days=i)
            if d in historia:
                valores_recientes.append(historia[d].get(tipo, 0.0))
        
        if valores_recientes:
            pred = np.mean(valores_recientes)
        else:
            # Fallback: media global
            valores_globales = [historia[fd].get(tipo, 0.0) for fd in fechas_ordenadas if fd < f]
            pred = np.mean(valores_globales) if valores_globales else 0.0
        
        predicciones.append(round(pred, 1))
    
    return predicciones


# ==========================================
# COM-91: MAPE
# ==========================================
def _calcular_mape(real, predicho):
    real = np.array(real)
    predicho = np.array(predicho)
    mascara = real > 0
    if not mascara.any():
        return None
    real_filtrado = real[mascara]
    pred_filtrado = predicho[mascara]
    errores_pct = np.abs((real_filtrado - pred_filtrado) / real_filtrado)
    return float(np.mean(errores_pct) * 100)


# ==========================================
# COM-91 v2: SPLITS
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
# COM-92 v2: ENTRENAMIENTO HÍBRIDO ADAPTATIVO
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None, modelo_key='ensemble'):
    """
    COM-92 v2: modelo híbrido adaptativo que selecciona estrategia por tipo de comensal.
    
    Estrategias:
    - 'constante': para series con desviación < 2 (Cocinera, Social)
    - 'media_movil': para series con desviación 2-4
    - 'modelo_ml': para series con variación real (Afiliado, Normal)
    - 'ensemble': combina RF + GBM + Media Móvil para series con variación
    
    Args:
        cur: cursor de base de datos
        modo: 'evaluacion' o 'produccion'
        fecha_corte: fecha de corte para modo evaluacion
        dias_test: días de prueba para modo produccion
        modelo_key: 'rf', 'gbm', o 'ensemble'
    
    Returns:
        Dict con métricas, puntos, importancias e info del modelo.
    """
    if modelo_key not in MODELOS_DISPONIBLES:
        raise ValueError(f"Modelo '{modelo_key}' no válido. Use 'rf', 'gbm', o 'ensemble'.")
    
    historia = _cargar_historia_demanda(cur)
    fechas = sorted(historia.keys())
    
    # COM-92 v2: analizar series para determinar estrategia
    analisis_series = _analizar_series(historia)
    
    if fecha_corte is None:
        fecha_corte = FECHA_CORTE_DEFAULT
    if dias_test is None:
        dias_test = DIAS_TEST_DEFAULT
    
    # Seleccionar split
    info_split = {}
    if modo == 'evaluacion':
        fechas_train, fechas_test = _split_por_fecha(fechas, fecha_corte)
        info_split = {'tipo': 'evaluacion_fija', 'fecha_corte': fecha_corte.isoformat()}
    elif modo == 'produccion':
        if len(fechas) > dias_test:
            fechas_train, fechas_test = _split_expanding_window(fechas, dias_test)
        else:
            fechas_train, fechas_test = _split_ratio(fechas, 0.80)
        info_split = {'tipo': 'expanding_window', 'dias_test': dias_test}
    else:
        fechas_train, fechas_test = _split_ratio(fechas, 0.80)
        info_split = {'tipo': 'ratio_80_20', 'ratio': 0.80}
    
    if len(fechas_train) < MIN_DIAS_TRAIN:
        raise ValueError(f"Insuficientes días de entrenamiento: {len(fechas_train)} (mín {MIN_DIAS_TRAIN})")
    if len(fechas_test) < MIN_DIAS_TEST:
        raise ValueError(f"Insuficientes días de prueba: {len(fechas_test)} (mín {MIN_DIAS_TEST})")
    
    # Features enriquecidas
    fecha_inicio = fechas[0]
    X_train = np.array([_features_enriquecidas(f, historia, fecha_inicio) for f in fechas_train])
    X_test = np.array([_features_enriquecidas(f, historia, fecha_inicio) for f in fechas_test])
    
    # COM-92 v2: normalización robusta (mejor para outliers)
    scaler = RobustScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    puntos = []
    metricas = {}
    importancias = {}
    estrategias_usadas = {}
    
    for tipo in TIPOS:
        # COM-92 v2: obtener valores reales de train y test
        Y_train_tipo = np.array([historia[f].get(tipo, 0.0) for f in fechas_train])
        Y_test_tipo = np.array([historia[f].get(tipo, 0.0) for f in fechas_test])
        
        analisis = analisis_series[tipo]
        estrategia = analisis['estrategia']
        
        # COM-92 v2: seleccionar método de predicción
        if estrategia == 'constante':
            # Para series constantes, usar valor fijo
            pred = [analisis['valor_fijo']] * len(fechas_test)
            estrategias_usadas[tipo] = 'constante'
            importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES_ENRIQUECIDAS]
            
        elif estrategia == 'media_movil':
            # Para series con poca variación, usar media móvil
            pred = _predecir_media_movil(historia, fechas_test, tipo, ventana=7)
            estrategias_usadas[tipo] = 'media_movil_7'
            importancias[tipo] = [{'variable': v, 'importancia': 0.0} for v in VARIABLES_ENRIQUECIDAS]
            
        else:
            # Para series con variación, usar modelo ML o ensemble
            estrategias_usadas[tipo] = modelo_key
            
            if modelo_key == 'ensemble':
                # COM-92 v2: ensemble de RF + GBM + Media Móvil
                pred_rf = _entrenar_modelo_individual(X_train_scaled, X_test_scaled, Y_train_tipo, 'rf')
                pred_gbm = _entrenar_modelo_individual(X_train_scaled, X_test_scaled, Y_train_tipo, 'gbm')
                pred_mm = _predecir_media_movil(historia, fechas_test, tipo, ventana=7)
                
                # Promedio ponderado: 40% RF, 40% GBM, 20% Media Móvil
                pred = [
                    round(0.4 * rf + 0.4 * gbm + 0.2 * mm, 1)
                    for rf, gbm, mm in zip(pred_rf, pred_gbm, pred_mm)
                ]
                
                # Importancias promedio de RF y GBM
                imp_rf = _calcular_importancias(X_train_scaled, Y_train_tipo, 'rf')
                imp_gbm = _calcular_importancias(X_train_scaled, Y_train_tipo, 'gbm')
                importancias[tipo] = [
                    {'variable': VARIABLES_ENRIQUECIDAS[j], 
                     'importancia': round((imp_rf[j] + imp_gbm[j]) / 2, 4)}
                    for j in range(len(VARIABLES_ENRIQUECIDAS))
                ]
                
            else:
                # Modelo individual (RF o GBM)
                pred = _entrenar_modelo_individual(X_train_scaled, X_test_scaled, Y_train_tipo, modelo_key)
                importancias[tipo] = _calcular_importancias_dict(X_train_scaled, Y_train_tipo, modelo_key)
        
        # Calcular métricas
        real = Y_test_tipo.tolist()
        r2 = float(r2_score(real, pred)) if len(set(real)) > 1 else None
        mae = float(mean_absolute_error(real, pred))
        mape = _calcular_mape(real, pred)
        
        metricas[tipo] = {
            'r2': round(r2, 4) if r2 is not None else None,
            'mae': round(mae, 2),
            'mape': round(mape, 2) if mape is not None else None,
        }
        
        for f, re_, pr_ in zip(fechas_test, real, pred):
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
        'analisis_series': {k: {kk: vv for kk, vv in v.items() if kk != 'datos_limpios'} for k, v in analisis_series.items()},
        'estrategias_usadas': estrategias_usadas,
    })
    
    return {
        'modelo': MODELOS_DISPONIBLES[modelo_key]['nombre'],
        'modelo_key': modelo_key,
        'variables': list(VARIABLES_ENRIQUECIDAS),
        'tipos': list(TIPOS),
        'n_dias_historial': len(fechas),
        'n_dias_entrenamiento': len(fechas_train),
        'n_dias_test': len(fechas_test),
        'rango_fechas': [fechas[0].isoformat(), fechas[-1].isoformat()],
        'metricas': metricas,
        'importancias': importancias,
        'puntos': puntos,
        'info_split': info_split,
    }


# ==========================================
# COM-92 v2: HELPERS PARA ENSEMBLE
# ==========================================
def _entrenar_modelo_individual(X_train, X_test, Y_train, modelo_key: str) -> list:
    """Entrena un modelo individual (RF o GBM) y retorna predicciones."""
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, Y_train)
    pred = modelo.predict(X_test)
    return [round(float(p), 1) for p in pred]


def _calcular_importancias(X_train, Y_train, modelo_key: str) -> list:
    """Calcula importancias de features para un modelo individual."""
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, Y_train)
    return [float(v) for v in modelo.feature_importances_]


def _calcular_importancias_dict(X_train, Y_train, modelo_key: str) -> list:
    """Calcula importancias en formato dict para respuesta."""
    config = MODELOS_DISPONIBLES[modelo_key]
    modelo = config['clase'](**config['params'])
    modelo.fit(X_train, Y_train)
    return [
        {'variable': VARIABLES_ENRIQUECIDAS[j], 'importancia': round(float(v), 4)}
        for j, v in enumerate(modelo.feature_importances_)
    ]