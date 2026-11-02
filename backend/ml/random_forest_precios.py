"""
ml/random_forest_precios.py
Objetivo: Modelo Random Forest de PRECIOS DE INSUMOS. El modelo nació en
optimizador.py (COM-37 v7), recibió caché y RF ligera en COM-103, y en COM-105 v2
se muda a su propio módulo para que el código sea mantenible y tenga gráfico
propio en el panel de Modelos ML, con la misma jerarquía de gobierno que los
otros tres motores (demanda, clustering y menús).
Responsabilidades:
* predecir_precio_con_confianza(): predicción puntual del precio de compra de un
  insumo para una fecha objetivo. Ventana de hasta 90 días de histórico, feature
  índice temporal, predicción en el índice siguiente al último registro, piso de
  un céntimo y redondeo a dos decimales. Caché en proceso invalidada por huella
  del histórico (n registros + última fecha de la ventana) con TTL de 15 min.
  La confianza expuesta es el R² DENTRO de la muestra por 100 (se declara así).
* evaluar_prediccion_precios(): protocolo OUT-OF-SAMPLE por cortes temporales,
  idéntico en espíritu al del modelo de demanda: para cada fecha de corte con
  corrida real del scraper, entrena con historial ESTRICTAMENTE anterior y
  compara contra el precio real del corte (MIN por insumo, coherente con el paso
  SCRAPER_DIA de precios_insumos). Como las unidades de compra son heterogéneas
  (kg, und, atado), el MAE se reporta en S/ POR KG tras convertir real y predicho
  con gramos_por_unidad_compra, y el MAPE se calcula sobre el precio en la unidad
  original (adimensional).
* payload_panel(): arma el payload del gráfico 4 del panel ML: dispersión real vs
  predicho en S/ por kg con línea y=x, métricas globales y por insumo, series
  históricas de los insumos con más puntos evaluados (línea real + marcadores
  predichos) y auditoría de cortes. Caché de evaluación con TTL de 10 min
  invalidada por huella global del historial de precios, para que abrir el panel
  no re-entrene cientos de RF en cada clic.
Historial:
COM-37 v7: la predicción RF de precios nace en optimizador.py y cuenta como fuente
    válida en la jerarquía scraper día > manual > RF > scraper último.
COM-103: caché en proceso por (insumo, fecha, huella) con TTL 15 min y poda simple;
    RF ligera (60 árboles, depth 4) con precisión equivalente en series cortas y
    ~40% más rápida; el greedy costea ~100 insumos por generación.
COM-105 v2 (este archivo): el modelo, su caché y su evaluación viven aquí.
    optimizador.py conserva un wrapper de re-exportación para no romper los
    consumidores históricos (precios_insumos, ml/greedy_search, ml/kmeans_recetas,
    ml/reporte_gestion). Se agrega payload_panel() y el endpoint del panel vive en
    routers/modelos_ml.py (GET /modelos-ml/random-forest-precios).
Uso: Importado por optimizador.py (wrapper), routers/modelos_ml.py (panel) y por
    cualquier módulo que necesite las métricas out-of-sample para la tesis.
Referencia: tickets COM-37 v7 / COM-103 / COM-105 v2 (solo trazabilidad).
"""
import time
import statistics
from datetime import timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

# COM-37 v5: conversión estándar de unidades de compra (kg comparables)
from precios_insumos import gramos_por_unidad_compra

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
VENTANA_DIAS = 90          # histórico máximo consultado por insumo
MIN_REGISTROS = 5          # piso para entrenar (coherente con producción)
PISO_PRECIO = 0.01         # piso económico del precio predicho
RANDOM_STATE = 42

# COM-103: hiperparámetros de la RF de precios (series cortas y tendenciales)
RF_PRECIOS_PARAMS = {
    'n_estimators': 60,    # COM-103: antes 100 (perf en costeo masivo)
    'max_depth': 4,        # COM-103: antes 5
    'min_samples_split': 3,
    'min_samples_leaf': 2,
    'random_state': RANDOM_STATE,
    'n_jobs': -1,
}

# COM-103: caché de predicciones puntuales (TTL 15 min + huella del histórico)
PRECIO_RF_CACHE_TTL_SEG = 900
_PRECIO_RF_CACHE = {}

# COM-105 v2: caché del payload del panel (evaluar es caro: 1 RF por insumo y corte)
EVAL_CACHE_TTL_SEG = 600
_EVAL_CACHE = {'clave': None, 'ts': 0.0, 'payload': None}

# COM-105 v2: parámetros por defecto de la evaluación y del panel
N_CORTES_DEFAULT = 6
PASO_DIAS_DEFAULT = 5
DIAS_SERIE = 60            # días de histórico real dibujados en las series del panel
TOP_INSUMOS_SERIES = 4     # insumos con serie histórica en el payload del panel
TOP_INSUMOS_METRICAS = 8   # insumos detallados en metricas_por_insumo


# ==========================================
# HUELLAS DE CACHÉ
# ==========================================
def _huella_historial_global(cur):
    """Huella barata de TODO el historial de precios (invalida la caché del panel)."""
    cur.execute("""
        SELECT COUNT(*) AS n, MAX(fecha) AS f
        FROM historial_precios
        WHERE precio_prom IS NOT NULL AND precio_prom > 0;
    """)
    r = cur.fetchone()
    return (int(r['n'] or 0), str(r['f']))


# ==========================================
# PREDICCIÓN PUNTUAL (producción + evaluación)
# ==========================================
def predecir_precio_con_confianza(insumo_id, fecha_objetivo, conn, cur):
    """
    Predice el precio de compra de un insumo para `fecha_objetivo` usando Random
    Forest sobre hasta 90 días de histórico (COM-37 v7 / COM-103).
    Contrato de retorno INVARIANTE desde su nacimiento en optimizador.py:
    (precio_redondeado, confianza_pct, ok). La confianza es R² DENTRO de la
    muestra por 100; las métricas honestas de error viven en
    evaluar_prediccion_precios() (COM-105 v2).
    COM-103: resultado cacheado por (insumo, fecha, huella de la ventana) con TTL
    de 15 min y poda simple cuando el dict crece; la huella se deriva de los
    propios registros ya leídos (n y última fecha), sin consulta extra: cuando el
    scraper agrega datos, la huella cambia y la caché se invalida sola.
    """
    cur.execute("""
        SELECT fecha, precio_prom
        FROM historial_precios
        WHERE insumo_id = %s
        AND fecha >= %s
        AND fecha < %s
        AND precio_prom IS NOT NULL
        ORDER BY fecha ASC
    """, (insumo_id, fecha_objetivo - timedelta(days=VENTANA_DIAS), fecha_objetivo))
    registros = cur.fetchall()
    if len(registros) < MIN_REGISTROS:
        return None, 0, False

    # COM-103: huella barata derivada de los registros ya leídos (sin query extra)
    huella = (len(registros), str(registros[-1]['fecha']))
    clave_cache = (insumo_id, str(fecha_objetivo), huella)
    ahora = time.time()
    entrada = _PRECIO_RF_CACHE.get(clave_cache)
    if entrada and (ahora - entrada['ts']) < PRECIO_RF_CACHE_TTL_SEG:
        return entrada['valor']

    try:
        X = np.array([[i] for i in range(len(registros))])
        y = np.array([float(r['precio_prom']) for r in registros])
        model = RandomForestRegressor(**RF_PRECIOS_PARAMS)
        model.fit(X, y)
        y_pred = model.predict(X)
        r2 = r2_score(y, y_pred)
        confianza = max(0, r2 * 100)
        dias_desde_ultimo = len(registros)
        precio_predicho = model.predict([[dias_desde_ultimo]])[0]
        precio_predicho = max(PISO_PRECIO, float(precio_predicho))
        resultado = (round(precio_predicho, 2), round(confianza, 1), True)
    except ImportError:
        # Degradación controlada sin sklearn: promedio simple con confianza media
        precio_promedio = sum(float(r['precio_prom']) for r in registros) / len(registros)
        resultado = (round(precio_promedio, 2), 50.0, True)

    # COM-103: guardar en caché y podar entradas expiradas si crece demasiado
    _PRECIO_RF_CACHE[clave_cache] = {'ts': ahora, 'valor': resultado}
    if len(_PRECIO_RF_CACHE) > 4000:
        expiradas = [k for k, v in _PRECIO_RF_CACHE.items()
                     if ahora - v['ts'] > PRECIO_RF_CACHE_TTL_SEG]
        for k in expiradas:
            _PRECIO_RF_CACHE.pop(k, None)
    return resultado


# ==========================================
# COM-105 v2: EVALUACIÓN OUT-OF-SAMPLE (protocolo de cortes temporales)
# ==========================================
def evaluar_prediccion_precios(cur, n_cortes=N_CORTES_DEFAULT, paso_dias=PASO_DIAS_DEFAULT,
                               insumo_ids=None):
    """
    COM-105 v2: validación out-of-sample de la RF de precios con la MISMA lógica de
    producción (ventana de 90 días, feature índice, predicción en índice n, piso
    0.01, redondeo a 2 decimales). Para cada fecha de corte con corrida real del
    scraper, entrena con historial ESTRICTAMENTE anterior y compara el predicho
    contra el precio real del día de corte (MIN por insumo, coherente con el paso
    SCRAPER_DIA de precios_insumos).
    Como las unidades de compra son heterogéneas (kg, und, atado), el MAE se reporta
    en S/ POR KG convirtiendo real y predicho con gramos_por_unidad_compra; el MAPE
    se calcula sobre el precio en la unidad original (adimensional).
    Retorna {'resumen': {...}, 'por_insumo': [...], 'puntos': [...]}:
    * resumen: n_cortes, cortes, n_puntos, n_insumos, mape_pct, mape_mediano_pct,
      mae_soles_por_kg, confianza_promedio_insample.
    * por_insumo: lista ordenada por MAPE descendente con n, mape y mae_kg.
    * puntos: auditoría cruda por insumo y fecha (real, predicho, unidad, ape,
      ae_kg, real_kg, predicho_kg, confianza) para el scatter y las tablas del paper.
    """
    cur.execute("""
        SELECT DISTINCT fecha FROM historial_precios
        WHERE precio_prom IS NOT NULL AND precio_prom > 0
        ORDER BY fecha DESC;
    """)
    fechas_disp = [r['fecha'] for r in cur.fetchall()]
    if not fechas_disp:
        return {'resumen': {'n_puntos': 0, 'n_cortes': 0}, 'por_insumo': [], 'puntos': []}
    cortes = fechas_disp[::paso_dias][:n_cortes]
    sql_base = """
        SELECT ins.id AS insumo_id, ins.nombre AS nombre,
               MIN(hp.precio_prom) AS real_prom,
               um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo,
               um.factor_a_base AS u_factor, ing.peso_estimado_g
        FROM historial_precios hp
        JOIN insumos ins ON ins.id = hp.insumo_id
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE hp.fecha = %s AND hp.precio_prom IS NOT NULL AND hp.precio_prom > 0
    """
    puntos = []
    for corte in cortes:
        if insumo_ids:
            cur.execute(sql_base + " AND ins.id = ANY(%s) GROUP BY ins.id, ins.nombre, "
                                   "um.abreviatura, um.tipo_magnitud, um.factor_a_base, "
                                   "ing.peso_estimado_g;",
                        (corte, list(insumo_ids)))
        else:
            cur.execute(sql_base + " GROUP BY ins.id, ins.nombre, um.abreviatura, "
                                   "um.tipo_magnitud, um.factor_a_base, ing.peso_estimado_g;",
                        (corte,))
        for r in cur.fetchall():
            pred, conf, ok = predecir_precio_con_confianza(r['insumo_id'], corte, None, cur)
            if not (ok and pred):
                continue  # sin histórico suficiente antes del corte: se omite de la evaluación
            g = gramos_por_unidad_compra(
                r['u_abrev'], r['u_tipo'], float(r['u_factor']), float(r['peso_estimado_g']))
            if not g or g <= 0:
                continue
            real = float(r['real_prom'])
            if real <= 0:
                continue
            real_kg = real / g * 1000.0
            pred_kg = float(pred) / g * 1000.0
            ape = abs(float(pred) - real) / real * 100.0
            puntos.append({
                'insumo_id': r['insumo_id'],
                'nombre': r['nombre'],
                'fecha': str(corte),
                'unidad': r['u_abrev'],
                'real': round(real, 2),
                'predicho': round(float(pred), 2),
                'real_kg': round(real_kg, 3),
                'predicho_kg': round(pred_kg, 3),
                'confianza_insample': conf,
                'ape_pct': round(ape, 2),
                'ae_soles_kg': round(abs(pred_kg - real_kg), 3),
            })
    if not puntos:
        return {'resumen': {'n_puntos': 0, 'n_cortes': len(cortes)}, 'por_insumo': [], 'puntos': []}
    apes = [p['ape_pct'] for p in puntos]
    aes_kg = [p['ae_soles_kg'] for p in puntos]
    confs = [p['confianza_insample'] for p in puntos]
    resumen = {
        'n_cortes': len(cortes),
        'cortes': [str(c) for c in cortes],
        'n_puntos': len(puntos),
        'n_insumos': len({p['insumo_id'] for p in puntos}),
        'mape_pct': round(sum(apes) / len(apes), 2),
        'mape_mediano_pct': round(statistics.median(apes), 2),
        'mae_soles_por_kg': round(sum(aes_kg) / len(aes_kg), 3),
        'confianza_promedio_insample': round(sum(confs) / len(confs), 1),
    }
    por_insumo = []
    for iid in sorted({p['insumo_id'] for p in puntos}):
        ps = [p for p in puntos if p['insumo_id'] == iid]
        por_insumo.append({
            'insumo_id': iid,
            'nombre': ps[0]['nombre'],
            'unidad': ps[0]['unidad'],
            'n': len(ps),
            'mape_pct': round(sum(p['ape_pct'] for p in ps) / len(ps), 2),
            'mae_soles_por_kg': round(sum(p['ae_soles_kg'] for p in ps) / len(ps), 3),
        })
    por_insumo.sort(key=lambda x: -x['mape_pct'])
    return {'resumen': resumen, 'por_insumo': por_insumo, 'puntos': puntos}


# ==========================================
# COM-105 v2: SERIES HISTÓRICAS PARA EL GRÁFICO DE LÍNEA DEL PANEL
# ==========================================
def _series_de_insumos(cur, insumo_ids, dias=DIAS_SERIE):
    """
    Histórico real reciente en S/ por kg de los insumos indicados (MIN por día,
    coherente con SCRAPER_DIA), más los puntos predichos en los cortes evaluados.
    Retorna {insumo_id: {nombre, unidad, historia: [{fecha, precio_kg}],
    predicciones: [{fecha, precio_kg}]}}.
    """
    out = {}
    if not insumo_ids:
        return out
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS nombre, um.abreviatura AS u_abrev,
               um.tipo_magnitud AS u_tipo, um.factor_a_base AS u_factor,
               ing.peso_estimado_g
        FROM insumos ins
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE ins.id = ANY(%s);
    """, (list(insumo_ids),))
    meta = {r['insumo_id']: r for r in cur.fetchall()}
    for iid, r in meta.items():
        g = gramos_por_unidad_compra(
            r['u_abrev'], r['u_tipo'], float(r['u_factor']), float(r['peso_estimado_g']))
        if not g or g <= 0:
            continue
        cur.execute("""
            SELECT fecha, MIN(precio_prom) AS precio
            FROM historial_precios
            WHERE insumo_id = %s AND precio_prom IS NOT NULL AND precio_prom > 0
              AND fecha >= CURRENT_DATE - %s
            GROUP BY fecha ORDER BY fecha;
        """, (iid, dias))
        historia = [{'fecha': str(h['fecha']),
                     'precio_kg': round(float(h['precio']) / g * 1000.0, 3)}
                    for h in cur.fetchall()]
        out[iid] = {'nombre': r['nombre'], 'unidad': r['u_abrev'],
                    'historia': historia, 'predicciones': []}
    return out


# ==========================================
# COM-105 v2: PAYLOAD DEL GRÁFICO 4 DEL PANEL ML (con caché)
# ==========================================
def payload_panel(cur, n_cortes=N_CORTES_DEFAULT, paso_dias=PASO_DIAS_DEFAULT,
                  insumo_ids=None):
    """
    COM-105 v2: payload completo del gráfico de precios del panel ML, con caché en
    proceso (TTL 10 min) invalidada por huella global del historial de precios:
    * puntos: dispersión real vs predicho EN S/ POR KG (unidades heterogéneas
      comparables) con fecha, insumo y ape para tooltip y línea y=x.
    * metricas: resumen global out-of-sample (MAPE, MAPE mediano, MAE S/ por kg,
      n puntos, n insumos, cortes) + nota declarando que la confianza de producción
      es R² dentro de la muestra.
    * metricas_por_insumo: top 8 insumos por MAPE descendente (pills del panel).
    * series: top 4 insumos por cantidad de puntos evaluados, con histórico real de
      60 días en S/ por kg y marcadores predichos en los cortes evaluados.
    * modelo y variables para rotular ejes y leyendas (requerimiento COM-5 v4).
    """
    clave = (_huella_historial_global(cur), n_cortes, paso_dias,
             tuple(sorted(insumo_ids)) if insumo_ids else None)
    ahora = time.time()
    if (_EVAL_CACHE['clave'] == clave and _EVAL_CACHE['payload'] is not None
            and (ahora - _EVAL_CACHE['ts']) < EVAL_CACHE_TTL_SEG):
        return _EVAL_CACHE['payload']

    res = evaluar_prediccion_precios(cur, n_cortes=n_cortes, paso_dias=paso_dias,
                                     insumo_ids=insumo_ids)
    puntos = res['puntos']
    por_insumo = res['por_insumo']
    # Series de los insumos con más puntos evaluados (empate: menor MAPE)
    por_puntos = sorted(por_insumo, key=lambda x: (-x['n'], x['mape_pct']))
    ids_series = [x['insumo_id'] for x in por_puntos[:TOP_INSUMOS_SERIES]]
    series = _series_de_insumos(cur, ids_series)
    # Marcadores predichos sobre cada serie (puntos evaluados de ese insumo)
    for p in puntos:
        s = series.get(p['insumo_id'])
        if s is not None:
            s['predicciones'].append({'fecha': p['fecha'], 'precio_kg': p['predicho_kg']})
    for s in series.values():
        s['predicciones'].sort(key=lambda d: d['fecha'])

    payload = {
        'modelo': 'RandomForestRegressor(' + ', '.join(
            f'{k}={v}' for k, v in RF_PRECIOS_PARAMS.items()) + ')',
        'modelo_key': 'rf_precios',
        'unidad_scatter': 'S/ por kg',
        'variables': ['indice_temporal'],
        'metricas': res['resumen'],
        'metricas_por_insumo': por_insumo[:TOP_INSUMOS_METRICAS],
        'puntos': puntos,
        'series': [
            {'insumo_id': iid, **series[iid]} for iid in ids_series if iid in series
        ],
        'nota': ('La confianza expuesta en producción es R² dentro de la muestra; '
                 'las métricas de error de este panel son out-of-sample sobre cortes '
                 'temporales (COM-105 v2).'),
    }
    _EVAL_CACHE.update({'clave': clave, 'ts': ahora, 'payload': payload})
    return payload