"""
ml/random_forest_demanda.py
Objetivo: Modelos de demanda diaria de comensales (social / afiliado / normal)
para el panel de gráficos de Machine Learning (COM-5 v4 / COM-8 v7).
COM-92: Implementa DOS modelos seleccionables:
- Random Forest (RF): ensemble de árboles, robusto a outliers.
- Gradient Boosting (GBM): boosting secuencial, mejor para patrones temporales.
Ambos comparten las mismas features enriquecidas (13 variables) y el mismo
split temporal configurable. El caller elige el modelo vía parámetro.
Variables (features) usadas:
BÁSICAS: dia_semana, mes, dia_del_mes, es_fin_de_semana
ENRIQUECIDAS (COM-91 v3): tendencia, lag_1, lag_7, media_movil_7, media_movil_14,
dia_semana_sin/cos, mes_sin/cos (codificación cíclica).
Targets: raciones diarias por tipo: social, afiliado, normal.
Uso: Importado por routers/modelos_ml.py. Entrenamiento bajo demanda.
Historial:
COM-5 v4 / COM-8 v7: versión original con R² y MAE. Split 80/20.
COM-91: se agrega MAPE.
COM-91 v2: split temporal configurable (evaluacion/produccion).
COM-91 v3: features enriquecidas (13 variables) + Gradient Boosting.
COM-92 (este archivo): selector de modelo (RF vs GBM) vía parámetro.
Referencia: ticket COM-5 v4 / HU-04 / COM-91 / COM-92.
"""
from datetime import date, datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal')
VARIABLES_BASICAS = ('dia_semana', 'mes', 'dia_del_mes', 'es_fin_de_semana')
VARIABLES_ENRIQUECIDAS = (
    'dia_semana', 'mes', 'dia_del_mes', 'es_fin_de_semana',
    'tendencia', 'lag_1', 'lag_7', 'media_movil_7', 'media_movil_14',
    'dia_semana_sin', 'dia_semana_cos', 'mes_sin', 'mes_cos'
)
RANDOM_STATE = 42
MIN_DIAS_TRAIN = 60
MIN_DIAS_TEST = 5
SPLIT_ENTRENAMIENTO = 0.80
FECHA_CORTE_DEFAULT = date(2026, 10, 1)
DIAS_TEST_DEFAULT = 30

# COM-92: configuración de modelos
MODELOS_DISPONIBLES = {
    'rf': {
        'nombre': 'Random Forest',
        'clase': RandomForestRegressor,
        'params': {'n_estimators': 100, 'random_state': RANDOM_STATE, 'min_samples_leaf': 2},
    },
    'gbm': {
        'nombre': 'Gradient Boosting',
        'clase': GradientBoostingRegressor,
        'params': {'n_estimators': 200, 'learning_rate': 0.1, 'max_depth': 5, 'random_state': RANDOM_STATE},
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
        dia = historia.setdefault(f, {'social': 0.0, 'afiliado': 0.0, 'normal': 0.0})
        dia[t] += float(r['n'] or 0)
    return historia


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
# COM-92: ENTRENAMIENTO CON SELECTOR DE MODELO
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None, modelo_key='rf'):
    """
    COM-92: entrena el modelo seleccionado (RF o GBM) con features enriquecidas.
    
    Args:
        cur: cursor de base de datos
        modo: 'evaluacion' (split por fecha) o 'produccion' (expanding window)
        fecha_corte: fecha de corte para modo evaluacion (default: 2026-10-01)
        dias_test: días de prueba para modo produccion (default: 30)
        modelo_key: 'rf' para Random Forest, 'gbm' para Gradient Boosting
    
    Returns:
        Dict con métricas, puntos, importancias e info del modelo usado.
    """
    if modelo_key not in MODELOS_DISPONIBLES:
        raise ValueError(f"Modelo '{modelo_key}' no válido. Use 'rf' o 'gbm'.")
    
    modelo_config = MODELOS_DISPONIBLES[modelo_key]
    historia = _cargar_historia_demanda(cur)
    fechas = sorted(historia.keys())
    
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
            fechas_train, fechas_test = _split_ratio(fechas, SPLIT_ENTRENAMIENTO)
        info_split = {'tipo': 'expanding_window', 'dias_test': dias_test}
    else:
        fechas_train, fechas_test = _split_ratio(fechas, SPLIT_ENTRENAMIENTO)
        info_split = {'tipo': 'ratio_80_20', 'ratio': SPLIT_ENTRENAMIENTO}
    
    if len(fechas_train) < MIN_DIAS_TRAIN:
        raise ValueError(f"Insuficientes días de entrenamiento: {len(fechas_train)} (mín {MIN_DIAS_TRAIN})")
    if len(fechas_test) < MIN_DIAS_TEST:
        raise ValueError(f"Insuficientes días de prueba: {len(fechas_test)} (mín {MIN_DIAS_TEST})")
    
    fecha_inicio = fechas[0]
    X_train = np.array([_features_enriquecidas(f, historia, fecha_inicio) for f in fechas_train])
    Y_train = np.array([[historia[f][t] for t in TIPOS] for f in fechas_train])
    X_test = np.array([_features_enriquecidas(f, historia, fecha_inicio) for f in fechas_test])
    Y_test = np.array([[historia[f][t] for t in TIPOS] for f in fechas_test])
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    puntos = []
    metricas = {}
    importancias = {}
    
    for i, t in enumerate(TIPOS):
        modelo = modelo_config['clase'](**modelo_config['params'])
        modelo.fit(X_train_scaled, Y_train[:, i])
        pred = modelo.predict(X_test_scaled)
        real = Y_test[:, i]
        
        r2 = float(r2_score(real, pred)) if len(set(real.tolist())) > 1 else None
        mae = float(mean_absolute_error(real, pred))
        mape = _calcular_mape(real, pred)
        
        metricas[t] = {
            'r2': round(r2, 4) if r2 is not None else None,
            'mae': round(mae, 2),
            'mape': round(mape, 2) if mape is not None else None,
        }
        
        importancias[t] = [
            {'variable': VARIABLES_ENRIQUECIDAS[j], 'importancia': round(float(modelo.feature_importances_[j]), 4)}
            for j in range(len(VARIABLES_ENRIQUECIDAS))
        ]
        
        for f, re_, pr_ in zip(fechas_test, real, pred):
            puntos.append({
                'fecha': f.isoformat(),
                'tipo': t,
                'real': round(float(re_), 1),
                'predicho': round(float(pr_), 1),
            })
    
    info_split.update({
        'n_dias_train': len(fechas_train),
        'n_dias_test': len(fechas_test),
        'rango_train': [fechas_train[0].isoformat(), fechas_train[-1].isoformat()],
        'rango_test': [fechas_test[0].isoformat(), fechas_test[-1].isoformat()],
    })
    
    return {
        'modelo': f"{modelo_config['nombre']}({', '.join(f'{k}={v}' for k, v in modelo_config['params'].items())})",
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