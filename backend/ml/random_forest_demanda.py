"""
ml/random_forest_demanda.py
Objetivo: Modelo Random Forest de demanda diaria de comensales (social / afiliado /
          normal) para el panel de gráficos de Machine Learning (COM-5 v4 / COM-8 v7).
          Entrena con el historial del padrón/ventas y devuelve los datos del gráfico
          de dispersión REAL vs PREDICHO con split temporal 80/20, métricas R²/MAE por
          tipo de comensal y la relevancia de cada variable (feature importances), de
          modo que el gráfico pueda exhibir sus indicadores/variables.
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
Referencia: ticket COM-5 v4 / HU-04 (solo trazabilidad; los nombres obedecen a la funcionalidad).
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
MIN_DIAS = 30          # historial mínimo para entrenar con sentido estadístico
SPLIT_ENTRENAMIENTO = 0.80


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
            "No se detectó la tabla de padrón/ventas (padron_diario, ventas, ...). "
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
# ENTRENAMIENTO Y EVALUACIÓN (split temporal)
# ==========================================
def entrenar_y_evaluar_rf(cur):
    """
    Entrena un RandomForestRegressor por tipo de comensal con split temporal 80/20 y
    retorna el payload completo para el gráfico de dispersión del panel ML:
      - puntos: [{fecha, tipo, real, predicho}] del conjunto de prueba
      - metricas: R² y MAE por tipo
      - importancias: relevancia de cada variable por tipo (indicadores del gráfico)
    """
    historia = _cargar_historia_demanda(cur)
    fechas = sorted(historia.keys())
    if len(fechas) < MIN_DIAS:
        raise ValueError(
            f"Historial insuficiente para Random Forest: {len(fechas)} día(s) "
            f"(mínimo {MIN_DIAS}). Registre ventas del padrón antes de ver el gráfico.")

    X = np.array([_features_de(f) for f in fechas])
    Y = np.array([[historia[f][t] for t in TIPOS] for f in fechas])
    corte = int(len(fechas) * SPLIT_ENTRENAMIENTO)
    if corte < 10 or (len(fechas) - corte) < 5:
        raise ValueError("Historial demasiado corto para dividir en entrenamiento/prueba.")

    Xtr, Xte = X[:corte], X[corte:]
    Ytr, Yte = Y[:corte], Y[corte:]

    puntos = []
    metricas = {}
    importancias = {}
    for i, t in enumerate(TIPOS):
        rf = RandomForestRegressor(
            n_estimators=100, random_state=RANDOM_STATE, min_samples_leaf=2)
        rf.fit(Xtr, Ytr[:, i])
        pred = rf.predict(Xte)
        real = Yte[:, i]

        r2 = float(r2_score(real, pred)) if len(set(real.tolist())) > 1 else None
        metricas[t] = {
            'r2': round(r2, 4) if r2 is not None else None,
            'mae': round(float(mean_absolute_error(real, pred)), 2),
        }
        importancias[t] = [
            {'variable': VARIABLES[j], 'importancia': round(float(rf.feature_importances_[j]), 4)}
            for j in range(len(VARIABLES))
        ]
        for f, re_, pr_ in zip(fechas[corte:], real, pred):
            puntos.append({
                'fecha': f.isoformat(),
                'tipo': t,
                'real': round(float(re_), 1),
                'predicho': round(float(pr_), 1),
            })

    return {
        'modelo': 'RandomForestRegressor(n_estimators=100)',
        'variables': list(VARIABLES),
        'tipos': list(TIPOS),
        'n_dias_historial': len(fechas),
        'n_dias_entrenamiento': corte,
        'n_dias_test': len(fechas) - corte,
        'rango_fechas': [fechas[0].isoformat(), fechas[-1].isoformat()],
        'metricas': metricas,
        'importancias': importancias,
        'puntos': puntos,
    }