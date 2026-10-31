"""
ml/random_forest_demanda.py
Objetivo: Modelo Random Forest de demanda diaria de comensales (social / afiliado /
normal) para el panel de gráficos de Machine Learning (COM-5 v4 / COM-8 v7).
Entrena con el historial del padrón/ventas y devuelve los datos del gráfico
de dispersión REAL vs PREDICHO con split temporal configurable, métricas
R²/MAE/MAPE por tipo de comensal y la relevancia de cada variable (feature
importances), de modo que el gráfico pueda exhibir sus indicadores/variables.
Variables (features) usadas:
- dia_semana (0=Lunes .. 6=Domingo)
- mes (1-12)
- dia_del_mes (1-31)
- es_fin_de_semana (0/1)
Targets:  raciones diarias por tipo: social, afiliado, normal.
Uso: Importado por routers/modelos_ml.py (Parte 3). Todas las funciones reciben un
cursor psycopg2 (RealDictCursor); el entrenamiento es bajo demanda (no se persiste).
Nota: Detección defensiva del esquema (padron_diario / ventas / comensales), coherente
con el resto de motores del proyecto.
Historial:
COM-5 v4 / COM-8 v7: versión original con R² y MAE. Split temporal 80/20.
COM-91: se agrega MAPE (Mean Absolute Percentage Error) por tipo de comensal.
El MAPE es más intuitivo que el MAE porque se expresa en porcentaje,
permitiendo comparar la precisión del modelo entre tipos de comensal con escalas
diferentes (ej. social ~20 vs normal ~80). Se calcula solo sobre muestras donde
real > 0 para evitar división por cero; si no hay tales muestras, retorna None.
COM-91 v2 (este archivo): SPLIT TEMPORAL CONFIGURABLE con dos modos:
- modo='evaluacion' (default): split por fecha fija (FECHA_CORTE_DEFAULT = 2026-10-01).
  Todo lo anterior es train, desde aquí es test. Simula el escenario real: el modelo
  aprende del pasado y predice el futuro. La fecha de corte se puede sobrescribir
  pasando el parámetro `fecha_corte` a entrenar_y_evaluar_rf().
- modo='produccion': expanding window con los últimos `dias_test` días como prueba
  y todo el resto como entrenamiento. El modelo se reentrena con todos los datos
  disponibles, simulando el comportamiento en producción.
La respuesta incluye `info_split` con el tipo de split, rangos y cantidades de días
para auditoría en el panel ML.
Referencia: ticket COM-5 v4 / HU-04 / COM-91 / COM-91 v2 (solo trazabilidad).
"""
from datetime import date, datetime
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
TIPOS = ('social', 'afiliado', 'normal')
VARIABLES = ('dia_semana', 'mes', 'dia_del_mes', 'es_fin_de_semana')
RANDOM_STATE = 42

# COM-91 v2: configuración de splits
MIN_DIAS_TRAIN = 60          # mínimo de días de entrenamiento para tener sentido estadístico
MIN_DIAS_TEST = 5            # mínimo de días de prueba para evaluar
SPLIT_ENTRENAMIENTO = 0.80   # fallback: ratio 80/20 si no hay suficiente histórico
FECHA_CORTE_DEFAULT = date(2026, 10, 1)  # COM-91 v2: split por defecto (todo antes = train)
DIAS_TEST_DEFAULT = 30       # COM-91 v2: días de prueba en modo 'produccion'


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
    Retorna {fecha: {'social': n, 'afiliado': n, 'normal': n}} agregado por día.
    Detecta si el tipo de comensal vive en la tabla de ventas o se obtiene por join
    con la tabla de comensales.
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
        raise ValueError(f"La tabla '{tabla}' no tiene columnas de fecha/cantidad reconocibles: {cols}")
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
        dia = historia.setdefault(f, {'social': 0.0, 'afiliado': 0.0, 'normal': 0.0})
        dia[t] += float(r['n'] or 0)
    return historia


def _features_de(f: date):
    """Vector de variables calendarías de un día."""
    return [f.weekday(), f.month, f.day, 1 if f.weekday() >= 5 else 0]


# ==========================================
# COM-91: CÁLCULO DE MAPE
# ==========================================
def _calcular_mape(real, predicho):
    """
    COM-91: calcula el Mean Absolute Percentage Error (MAPE) entre arrays de valores
    reales y predichos. Solo considera muestras donde real > 0 para evitar división
    por cero. Si no hay tales muestras, retorna None.
    Fórmula: MAPE = (1/n) * Σ|(real - predicho) / real| * 100
    """
    real = np.array(real)
    predicho = np.array(predicho)
    # Filtrar solo donde real > 0
    mascara = real > 0
    if not mascara.any():
        return None
    real_filtrado = real[mascara]
    pred_filtrado = predicho[mascara]
    errores_pct = np.abs((real_filtrado - pred_filtrado) / real_filtrado)
    return float(np.mean(errores_pct) * 100)


# ==========================================
# COM-91 v2: FUNCIONES DE SPLIT
# ==========================================
def _split_por_fecha(fechas, fecha_corte):
    """
    COM-91 v2: divide las fechas en entrenamiento (antes de fecha_corte) y
    prueba (desde fecha_corte en adelante). Retorna (fechas_train, fechas_test).
    """
    fechas_train = [f for f in fechas if f < fecha_corte]
    fechas_test = [f for f in fechas if f >= fecha_corte]
    return fechas_train, fechas_test


def _split_expanding_window(fechas, dias_test):
    """
    COM-91 v2: split tipo 'produccion': los últimos `dias_test` días son prueba,
    el resto es entrenamiento. Retorna (fechas_train, fechas_test).
    """
    fechas_test = fechas[-dias_test:]
    fechas_train = fechas[:-dias_test]
    return fechas_train, fechas_test


def _split_ratio(fechas, ratio):
    """
    Fallback legacy: split por ratio (80/20). Solo se usa si los otros modos
    no son viables (ej. no hay suficientes días).
    """
    corte = int(len(fechas) * ratio)
    return fechas[:corte], fechas[corte:]


# ==========================================
# ENTRENAMIENTO Y EVALUACIÓN (split configurable)
# ==========================================
def entrenar_y_evaluar_rf(cur, modo='evaluacion', fecha_corte=None, dias_test=None):
    """
    Entrena un RandomForestRegressor por tipo de comensal con split temporal
    configurable y retorna el payload completo para el gráfico de dispersión
    del panel ML:
    - puntos: [{fecha, tipo, real, predicho}] del conjunto de prueba
    - metricas: R², MAE y MAPE por tipo (COM-91: se agrega MAPE)
    - importancias: relevancia de cada variable por tipo (indicadores del gráfico)
    - info_split: información del split (tipo, fechas, cantidad de días)

    COM-91 v2: tres modos de split:
    - modo='evaluacion' (default): split por fecha fija. Todo lo anterior a
      fecha_corte (default: 2026-10-01) es train, desde aquí es test. Simula
      el escenario real: el modelo aprende del pasado y predice el futuro.
    - modo='produccion': expanding window. Los últimos `dias_test` días (default: 30)
      son prueba, el resto es entrenamiento. El modelo se reentrena con todos los
      datos disponibles, simulando el comportamiento en producción.
    - fallback: si ningún modo es viable (pocos días), usa ratio 80/20.

    El MAPE se expresa en porcentaje y es más intuitivo que el MAE para comparar
    precisión entre tipos de comensal con escalas diferentes.
    """
    historia = _cargar_historia_demanda(cur)
    fechas = sorted(historia.keys())

    # COM-91 v2: aplicar parámetros por defecto si no se proporcionan
    if fecha_corte is None:
        fecha_corte = FECHA_CORTE_DEFAULT
    if dias_test is None:
        dias_test = DIAS_TEST_DEFAULT

    # COM-91 v2: seleccionar el tipo de split
    info_split = {}
    if modo == 'evaluacion':
        # Split por fecha fija
        fechas_train, fechas_test = _split_por_fecha(fechas, fecha_corte)
        info_split = {
            'tipo': 'evaluacion_fija',
            'fecha_corte': fecha_corte.isoformat(),
        }
    elif modo == 'produccion':
        # Expanding window
        if len(fechas) > dias_test:
            fechas_train, fechas_test = _split_expanding_window(fechas, dias_test)
        else:
            # Fallback: si no hay suficientes días, usar ratio 80/20
            fechas_train, fechas_test = _split_ratio(fechas, SPLIT_ENTRENAMIENTO)
        info_split = {
            'tipo': 'expanding_window',
            'dias_test': dias_test,
        }
    else:
        # Fallback: ratio 80/20
        fechas_train, fechas_test = _split_ratio(fechas, SPLIT_ENTRENAMIENTO)
        info_split = {
            'tipo': 'ratio_80_20',
            'ratio': SPLIT_ENTRENAMIENTO,
        }

    # Validaciones
    if len(fechas_train) < MIN_DIAS_TRAIN:
        raise ValueError(
            f"Insuficientes días de entrenamiento: {len(fechas_train)} días "
            f"(mínimo {MIN_DIAS_TRAIN}). Registre más ventas del padrón.")
    if len(fechas_test) < MIN_DIAS_TEST:
        raise ValueError(
            f"Insuficientes días de prueba: {len(fechas_test)} días "
            f"(mínimo {MIN_DIAS_TEST}).")

    # Preparar matrices de entrenamiento y prueba
    X_train = np.array([_features_de(f) for f in fechas_train])
    Y_train = np.array([[historia[f][t] for t in TIPOS] for f in fechas_train])
    X_test = np.array([_features_de(f) for f in fechas_test])
    Y_test = np.array([[historia[f][t] for t in TIPOS] for f in fechas_test])

    puntos = []
    metricas = {}
    importancias = {}

    for i, t in enumerate(TIPOS):
        rf = RandomForestRegressor(
            n_estimators=100, random_state=RANDOM_STATE, min_samples_leaf=2)
        rf.fit(X_train, Y_train[:, i])
        pred = rf.predict(X_test)
        real = Y_test[:, i]
        r2 = float(r2_score(real, pred)) if len(set(real.tolist())) > 1 else None
        mae = float(mean_absolute_error(real, pred))
        # COM-91: calcular MAPE (solo si hay muestras con real > 0)
        mape = _calcular_mape(real, pred)
        metricas[t] = {
            'r2': round(r2, 4) if r2 is not None else None,
            'mae': round(mae, 2),
            # COM-91: MAPE en porcentaje (None si no hay muestras válidas)
            'mape': round(mape, 2) if mape is not None else None,
        }
        importancias[t] = [
            {'variable': VARIABLES[j], 'importancia': round(float(rf.feature_importances_[j]), 4)}
            for j in range(len(VARIABLES))
        ]
        for f, re_, pr_ in zip(fechas_test, real, pred):
            puntos.append({
                'fecha': f.isoformat(),
                'tipo': t,
                'real': round(float(re_), 1),
                'predicho': round(float(pr_), 1),
            })

    # COM-91 v2: información completa del split para auditoría
    info_split.update({
        'n_dias_train': len(fechas_train),
        'n_dias_test': len(fechas_test),
        'rango_train': [fechas_train[0].isoformat(), fechas_train[-1].isoformat()],
        'rango_test': [fechas_test[0].isoformat(), fechas_test[-1].isoformat()],
    })

    return {
        'modelo': 'RandomForestRegressor(n_estimators=100)',
        'variables': list(VARIABLES),
        'tipos': list(TIPOS),
        'n_dias_historial': len(fechas),
        'n_dias_entrenamiento': len(fechas_train),
        'n_dias_test': len(fechas_test),
        'rango_fechas': [fechas[0].isoformat(), fechas[-1].isoformat()],
        'metricas': metricas,
        'importancias': importancias,
        'puntos': puntos,
        'info_split': info_split,  # COM-91 v2: información del split
    }