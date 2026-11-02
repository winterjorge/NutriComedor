"""
ml/random_forest_precios.py
Objetivo: Modelo Random Forest de PRECIOS DE INSUMOS. 
(Historial y responsabilidades se mantienen idénticos al original)
COM-105 v4 (Optimización de rendimiento): 
    * Reducción de universo a 12 insumos top y 3 cortes para garantizar carga < 30s.
    * Eliminación de n_jobs=-1 en RF (el overhead de multiprocesamiento en datasets 
      de <100 filas en entornos web ralentiza la ejecución hasta 10x).
    * Top de métricas en UI reducido a 5 para agilizar renderizado.
"""
import time
import statistics
from datetime import timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

from precios_insumos import gramos_por_unidad_compra

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
VENTANA_DIAS = 90          
MIN_REGISTROS = 5          
PISO_PRECIO = 0.01         
RANDOM_STATE = 42

# COM-105 v4: Optimizado para web. n_jobs=1 (default) es más rápido que -1 en datasets pequeños.
RF_PRECIOS_PARAMS = {
    'n_estimators': 60,    
    'max_depth': 4,        
    'min_samples_split': 3,
    'min_samples_leaf': 2,
    'random_state': RANDOM_STATE,
    # 'n_jobs': -1  <-- ELIMINADO: Causaba overhead severo en servidor web
}

PRECIO_RF_CACHE_TTL_SEG = 900
_PRECIO_RF_CACHE = {}

EVAL_CACHE_TTL_SEG = 600
_EVAL_CACHE = {'clave': None, 'ts': 0.0, 'payload': None}

# COM-105 v4: UNIVERSO ACOTADO AGRESIVO PARA < 30s DE CARGA
N_CORTES_DEFAULT = 3             # Reducido de 4 a 3
PASO_DIAS_DEFAULT = 7
TOP_INSUMOS_RECETARIO = 12       # Reducido de 20 a 12 (suficiente para tesis/UI)
DIAS_SERIE = 60                
TOP_INSUMOS_SERIES = TOP_INSUMOS_RECETARIO  # Ahora será 12
TOP_INSUMOS_METRICAS = 5         # Reducido de 8 a 5 (Solicitud explícita del usuario)


# ==========================================
# HUELLAS DE CACHÉ
# ==========================================
def _huella_historial_global(cur):
    cur.execute("""
        SELECT COUNT(*) AS n, MAX(fecha) AS f
        FROM historial_precios
        WHERE precio_prom IS NOT NULL AND precio_prom > 0;
    """)
    r = cur.fetchone()
    return (int(r['n'] or 0), str(r['f']))


# ==========================================
# UNIVERSO ACOTADO
# ==========================================
def _insumos_top_del_recetario(cur, limite=TOP_INSUMOS_RECETARIO):
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS nombre, COUNT(ri.id) AS n_lineas
        FROM recetas_clusters rc
        JOIN receta_ingrediente ri ON ri.receta_id = rc.receta_id
        JOIN insumos ins ON ins.ingrediente_id = ri.ingrediente_id
        WHERE rc.modelo_id = (
            SELECT id FROM kmeans_modelos WHERE activo = TRUE
            ORDER BY id DESC LIMIT 1)
        GROUP BY ins.id, ins.nombre
        ORDER BY n_lineas DESC
        LIMIT %s;
    """, (limite,))
    filas = cur.fetchall()
    if filas:
        return [dict(f) for f in filas]
    
    # Degradación controlada
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS nombre, COUNT(ri.id) AS n_lineas
        FROM receta_ingrediente ri
        JOIN insumos ins ON ins.ingrediente_id = ri.ingrediente_id
        GROUP BY ins.id, ins.nombre
        ORDER BY n_lineas DESC
        LIMIT %s;
    """, (limite,))
    return [dict(f) for f in cur.fetchall()]


# ==========================================
# PREDICCIÓN PUNTUAL
# ==========================================
def predecir_precio_con_confianza(insumo_id, fecha_objetivo, conn, cur):
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

    huella = (len(registros), str(registros[-1]['fecha']))
    clave_cache = (insumo_id, str(fecha_objetivo), huella)
    ahora = time.time()
    entrada = _PRECIO_RF_CACHE.get(clave_cache)
    if entrada and (ahora - entrada['ts']) < PRECIO_RF_CACHE_TTL_SEG:
        return entrada['valor']

    try:
        X = np.array([[i] for i in range(len(registros))])
        y = np.array([float(r['precio_prom']) for r in registros])
        
        # Aquí se beneficia de la eliminación de n_jobs=-1
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
        precio_promedio = sum(float(r['precio_prom']) for r in registros) / len(registros)
        resultado = (round(precio_promedio, 2), 50.0, True)

    _PRECIO_RF_CACHE[clave_cache] = {'ts': ahora, 'valor': resultado}
    if len(_PRECIO_RF_CACHE) > 4000:
        expiradas = [k for k, v in _PRECIO_RF_CACHE.items() if ahora - v['ts'] > PRECIO_RF_CACHE_TTL_SEG]
        for k in expiradas:
            _PRECIO_RF_CACHE.pop(k, None)
    return resultado


# ==========================================
# EVALUACIÓN OUT-OF-SAMPLE
# ==========================================
def evaluar_prediccion_precios(cur, n_cortes=N_CORTES_DEFAULT, paso_dias=PASO_DIAS_DEFAULT, insumo_ids=None):
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
                                   "ing.peso_estimado_g;", (corte, list(insumo_ids)))
        else:
            cur.execute(sql_base + " GROUP BY ins.id, ins.nombre, um.abreviatura, "
                                   "um.tipo_magnitud, um.factor_a_base, ing.peso_estimado_g;", (corte,))
        for r in cur.fetchall():
            pred, conf, ok = predecir_precio_con_confianza(r['insumo_id'], corte, None, cur)
            if not (ok and pred):
                continue
            
            g = gramos_por_unidad_compra(r['u_abrev'], r['u_tipo'], float(r['u_factor']), float(r['peso_estimado_g']))
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
# SERIES HISTÓRICAS
# ==========================================
def _series_de_insumos(cur, insumo_ids, dias=DIAS_SERIE):
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
        g = gramos_por_unidad_compra(r['u_abrev'], r['u_tipo'], float(r['u_factor']), float(r['peso_estimado_g']))
        if not g or g <= 0:
            continue
        cur.execute("""
            SELECT fecha, MIN(precio_prom) AS precio
            FROM historial_precios
            WHERE insumo_id = %s AND precio_prom IS NOT NULL AND precio_prom > 0
              AND fecha >= CURRENT_DATE - %s
            GROUP BY fecha ORDER BY fecha;
        """, (iid, dias))
        historia = [{'fecha': str(h['fecha']), 'precio_kg': round(float(h['precio']) / g * 1000.0, 3)} for h in cur.fetchall()]
        out[iid] = {'nombre': r['nombre'], 'unidad': r['u_abrev'], 'historia': historia, 'predicciones': []}
    return out


# ==========================================
# PAYLOAD DEL PANEL
# ==========================================
def payload_panel(cur, n_cortes=N_CORTES_DEFAULT, paso_dias=PASO_DIAS_DEFAULT, insumo_ids=None):
    universo_info = None
    if insumo_ids is None:
        top = _insumos_top_del_recetario(cur, TOP_INSUMOS_RECETARIO)
        insumo_ids = [t['insumo_id'] for t in top]
        universo_info = {
            'criterio': f"top {TOP_INSUMOS_RECETARIO} insumos por frecuencia de uso en recetas activas",
            'n_insumos_evaluados': len(insumo_ids),
            'n_cortes': n_cortes,
            'paso_dias': paso_dias,
            'top': top,
        }
        
    clave = (_huella_historial_global(cur), n_cortes, paso_dias, tuple(sorted(insumo_ids)) if insumo_ids else None)
    ahora = time.time()
    if (_EVAL_CACHE['clave'] == clave and _EVAL_CACHE['payload'] is not None and (ahora - _EVAL_CACHE['ts']) < EVAL_CACHE_TTL_SEG):
        return _EVAL_CACHE['payload']

    res = evaluar_prediccion_precios(cur, n_cortes=n_cortes, paso_dias=paso_dias, insumo_ids=insumo_ids)
    puntos = res['puntos']
    por_insumo = res['por_insumo']
    
    por_puntos = sorted(por_insumo, key=lambda x: (-x['n'], x['mape_pct']))
    ids_series = [x['insumo_id'] for x in por_puntos[:TOP_INSUMOS_SERIES]]
    series = _series_de_insumos(cur, ids_series)
    
    for p in puntos:
        s = series.get(p['insumo_id'])
        if s is not None:
            s['predicciones'].append({'fecha': p['fecha'], 'precio_kg': p['predicho_kg']})
    for s in series.values():
        s['predicciones'].sort(key=lambda d: d['fecha'])

    payload = {
        'modelo': 'RandomForestRegressor(' + ', '.join(f'{k}={v}' for k, v in RF_PRECIOS_PARAMS.items() if k != 'random_state') + ')',
        'modelo_key': 'rf_precios',
        'unidad_scatter': 'S/ por kg',
        'variables': ['indice_temporal'],
        'metricas': res['resumen'],
        'metricas_por_insumo': por_insumo[:TOP_INSUMOS_METRICAS], # AHORA SOLO 5
        'puntos': puntos,
        'series': [{'insumo_id': iid, **series[iid]} for iid in ids_series if iid in series],
        'universo_evaluado': universo_info,
        'nota': 'Métricas out-of-sample sobre cortes temporales. Universo acotado para rendimiento óptimo.',
    }
    _EVAL_CACHE.update({'clave': clave, 'ts': ahora, 'payload': payload})
    return payload