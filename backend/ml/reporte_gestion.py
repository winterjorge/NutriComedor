"""
ml/reporte_gestion.py
Objetivo: COM-50 (HU-10): motor del reporte "Resumen ejecutivo y recomendaciones".
          Toma el plan semanal vigente del comedor y produce:
            1) Resumen ejecutivo: costo total, costo por ración promedio, recolección
               proyectada, margen, viabilidad y fuente del plan.
            2) Uso de presupuesto por día (para gráfico de barras en la UI).
            3) Sugerencias automáticas:
               - AHORRO: por día, la alternativa más barata del MISMO cluster K-means
                 (mismo perfil nutricional) que cumpla las reglas R1/R2 vigentes y tenga
                 precio completo; se sugiere solo si el ahorro >= UMBRAL_SUGERENCIA_PCT
                 ("Para ahorrar X%, reemplace 'A' por 'B'").
               - ALERTA: margen negativo (recolección no cubre costos) y semana que
                 supera el presupuesto declarado.
               - VARIEDAD: platos repetidos dentro de la misma semana.
Fuente del plan (precedencia): última propuesta SELECCIONADA del comedor -> última
          propuesta del comedor -> última planificación guardada
          (presupuesto_semanal + planificacion_dia). También admite ids explícitos.
Uso: Importado por routers/reportes_gestion.py. Recibe cursor psycopg2 (RealDictCursor).
Referencia: tickets COM-50 / HU-10 (solo trazabilidad).
"""
import json
from datetime import date

from precios_insumos import (
    precios_por_gramo_por_insumo,
    gramos_por_unidad_estandar,
)
# COM-50: reglas vigentes y clusters del modelo activo (misma fuente que K-means/Greedy)
from ml.kmeans_recetas import cargar_reglas_proteinas, _normalizar, obtener_modelo_activo
# COM-50: reutiliza el costeo por equivalencias + jerarquía de fuentes del Greedy
from ml.greedy_search import _opcion_con_prediccion, _cargar_equivalencias

# Ahorro mínimo (%) para que un reemplazo se reporte como sugerencia (HU-10: ej. 5%)
UMBRAL_SUGERENCIA_PCT = 5.0


# ==========================================
# CONTEXTO DE COSTEO (cache por ejecución del reporte)
# ==========================================
def _nuevo_contexto(cur, fecha):
    """Precios por insumo (con fallback a última corrida), equivalencias y cache."""
    return {
        'fecha': fecha,
        'precios_insumo': precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=True),
        'eq_map': _cargar_equivalencias(cur),
        'cache_costo': {},
    }


def _costo_receta_por_racion(cur, receta_id, ctx):
    """
    COM-50: costo por ración de una receta con la misma jerarquía de fuentes que
    Evaluar/Greedy (scraper día/última corrida > manual insumo > legacy > predicción RF)
    y gramos de la unidad de USO vía equivalencias o conversión estándar.
    Retorna (costo_por_racion, precio_completo); None si la receta no existe.
    """
    if receta_id in ctx['cache_costo']:
        return ctx['cache_costo'][receta_id]
    cur.execute("""
        SELECT r.raciones
        FROM recetas_almuerzo r
        WHERE r.id = %s;
    """, (receta_id,))
    fila_rec = cur.fetchone()
    if not fila_rec:
        return None
    raciones = float(fila_rec['raciones']) if fila_rec['raciones'] else 4.0
    cur.execute("""
        SELECT ri.ingrediente_id, ri.cantidad_requerida, ri.unidad_medida_id,
               um.abreviatura AS unidad_abrev, um.tipo_magnitud, um.factor_a_base,
               ing.peso_estimado_g
        FROM receta_ingrediente ri
        JOIN unidades_medida um ON um.id = ri.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ri.ingrediente_id
        WHERE ri.receta_id = %s;
    """, (receta_id,))
    total = 0.0
    completo = True
    for fila in cur.fetchall():
        opc = _opcion_con_prediccion(
            cur, fila['ingrediente_id'], ctx['fecha'],
            ctx['precios_insumo'], fila['peso_estimado_g'])
        if opc is None:
            completo = False
            continue
        g = ctx['eq_map'].get((fila['ingrediente_id'], opc['insumo_id'], fila['unidad_medida_id']))
        if g is None:
            g = gramos_por_unidad_estandar(
                fila['unidad_abrev'], fila['tipo_magnitud'],
                fila['factor_a_base'], fila['peso_estimado_g'])
        total += (g * float(fila['cantidad_requerida'])) * opc['ppg']
    resultado = (round(total / raciones, 2) if raciones else round(total, 2), completo)
    ctx['cache_costo'][receta_id] = resultado
    return resultado


def _cumple_reglas_vigentes(nombres_ingredientes, re_permitida, re_vetada):
    """Réplica compacta de R1/R2 (permitida primero; veto solo si no es permitida)."""
    tiene_permitida = False
    tiene_vetada = False
    for nombre in nombres_ingredientes:
        nn = _normalizar(nombre)
        if not nn:
            continue
        if re_permitida.search(nn):
            tiene_permitida = True
        elif re_vetada.search(nn):
            tiene_vetada = True
    return tiene_permitida and not tiene_vetada


# ==========================================
# RESOLUCIÓN DEL PLAN VIGENTE
# ==========================================
def _resolver_plan(cur, comedor_id, candidata_id=None, presupuesto_id=None):
    """
    Devuelve (fuente, dias, resumen_base, presupuesto_total) del plan a reportar.
    Precedencia: candidata_id explícita -> última seleccionada del comedor ->
    última candidata del comedor -> presupuesto_id explícito -> último presupuesto.
    """
    # 1) Propuesta candidata (seleccionada o última)
    if candidata_id:
        cur.execute("""
            SELECT * FROM planificaciones_candidatas WHERE id = %s AND comedor_id = %s;
        """, (candidata_id, comedor_id))
        cand = cur.fetchone()
        fuente = 'propuesta_indicada'
    else:
        cur.execute("""
            SELECT * FROM planificaciones_candidatas
            WHERE comedor_id = %s AND estado ILIKE 'seleccion%'
            ORDER BY id DESC LIMIT 1;
        """, (comedor_id,))
        cand = cur.fetchone()
        fuente = 'propuesta_seleccionada'
        if not cand:
            cur.execute("""
                SELECT * FROM planificaciones_candidatas
                WHERE comedor_id = %s ORDER BY id DESC LIMIT 1;
            """, (comedor_id,))
            cand = cur.fetchone()
            fuente = 'propuesta_ultima'
    if cand:
        menu = cand['menu'] if isinstance(cand['menu'], list) else json.loads(cand['menu'] or '[]')
        resumen_base = cand['resumen'] if isinstance(cand['resumen'], dict) else json.loads(cand['resumen'] or '{}')
        dias = [{
            'dia_semana': d.get('dia_semana'),
            'dia_nombre': d.get('dia_nombre'),
            'fecha': d.get('fecha'),
            'receta_id': d.get('receta_id'),
            'receta_nombre': d.get('receta_nombre'),
            'costo_racion': float(d.get('costo_racion') or 0),
            'costo_total_dia': float(d.get('costo_total_dia') or 0),
            'recoleccion_proyectada': float(d.get('recoleccion_proyectada') or 0),
            'total_comensales': None,
            'cluster_codigo': d.get('cluster_codigo'),
            'cluster_etiqueta': d.get('cluster_etiqueta'),
        } for d in menu]
        return fuente, dias, resumen_base, resumen_base.get('presupuesto_semanal'), cand['id']

    # 2) Planificación guardada (presupuesto_semanal + planificacion_dia)
    if presupuesto_id:
        cur.execute("SELECT * FROM presupuesto_semanal WHERE id = %s;", (presupuesto_id,))
        pres = cur.fetchone()
        fuente = 'planificacion_indicada'
    else:
        cur.execute("SELECT * FROM presupuesto_semanal ORDER BY id DESC LIMIT 1;")
        pres = cur.fetchone()
        fuente = 'planificacion_ultima'
    if not pres:
        return None, [], {}, None, None
    cur.execute("""
        SELECT pd.dia, pd.dia_nombre, pd.receta_id, pd.nombre_receta,
               pd.costo_racion, pd.costo_total, pd.recoleccion_proyectada, pd.total_comensales
        FROM planificacion_dia pd
        WHERE pd.presupuesto_semanal_id = %s
        ORDER BY pd.dia;
    """, (pres['id'],))
    dias = [{
        'dia_semana': r['dia'],
        'dia_nombre': r['dia_nombre'],
        'fecha': None,
        'receta_id': r['receta_id'],
        'receta_nombre': r['nombre_receta'],
        'costo_racion': float(r['costo_racion'] or 0),
        'costo_total_dia': float(r['costo_total'] or 0),
        'recoleccion_proyectada': float(r['recoleccion_proyectada'] or 0),
        'total_comensales': r['total_comensales'],
        'cluster_codigo': None,
        'cluster_etiqueta': None,
    } for r in cur.fetchall()]
    resumen_base = {
        'costo_total_semana': float(pres['costo_total_semana'] or 0),
        'recoleccion_total_semana': float(pres['recoleccion_total_proyectada'] or 0),
        'margen_proyectado': float(pres['margen'] or 0),
        'dentro_de_presupuesto': bool(pres['viable']),
    }
    return fuente, dias, resumen_base, float(pres['fondo_total'] or 0), pres['id']


# ==========================================
# GENERACIÓN DEL REPORTE
# ==========================================
def generar_reporte_gestion(cur, comedor_id, candidata_id=None, presupuesto_id=None):
    """
    COM-50: construye el resumen ejecutivo + uso de presupuesto por día + sugerencias
    automáticas del plan semanal vigente del comedor.
    """
    fuente, dias, resumen_base, presupuesto_total, plan_id = _resolver_plan(
        cur, comedor_id, candidata_id, presupuesto_id)
    if not dias:
        return {'error': 'sin_plan',
                'detalle': 'El comedor aún no tiene propuestas seleccionadas ni planificaciones guardadas.'}

    fecha_hoy = date.today()
    ctx = _nuevo_contexto(cur, fecha_hoy)

    # Clusters del modelo activo (para completar cluster de días venidos de planificación)
    modelo = obtener_modelo_activo(cur)
    cluster_por_receta = {}
    if modelo:
        cur.execute("""
            SELECT receta_id, cluster_codigo, cluster_etiqueta
            FROM recetas_clusters WHERE modelo_id = %s;
        """, (modelo['id'],))
        for r in cur.fetchall():
            cluster_por_receta[r['receta_id']] = (r['cluster_codigo'], r['cluster_etiqueta'])
    for d in dias:
        if d['cluster_codigo'] is None and d['receta_id'] in cluster_por_receta:
            d['cluster_codigo'], d['cluster_etiqueta'] = cluster_por_receta[d['receta_id']]

    # ---- Resumen ejecutivo ----
    costo_total = resumen_base.get('costo_total_semana') or round(sum(d['costo_total_dia'] for d in dias), 2)
    recoleccion = resumen_base.get('recoleccion_total_semana') or round(sum(d['recoleccion_proyectada'] for d in dias), 2)
    margen = resumen_base.get('margen_proyectado')
    if margen is None:
        margen = round(recoleccion - costo_total, 2)
    comensales_dia = resumen_base.get('total_comensales_dia') or next(
        (d['total_comensales'] for d in dias if d['total_comensales']), None)
    costo_racion_prom = resumen_base.get('costo_racion_promedio') or (
        round(sum(d['costo_racion'] for d in dias) / len(dias), 2) if dias else 0)

    # ---- Uso de presupuesto por día (gráfico de barras) ----
    uso_por_dia = []
    for d in dias:
        pct = round((d['costo_total_dia'] / presupuesto_total) * 100, 2) if presupuesto_total else None
        uso_por_dia.append({
            'dia_nombre': d['dia_nombre'],
            'fecha': d['fecha'],
            'costo_total_dia': d['costo_total_dia'],
            'recoleccion_proyectada': d['recoleccion_proyectada'],
            'costo_racion': d['costo_racion'],
            'pct_del_presupuesto': pct,
        })

    # ---- Sugerencias automáticas ----
    sugerencias = []
    re_permitida, re_vetada, _, _ = cargar_reglas_proteinas(cur)
    recetas_usadas = {d['receta_id'] for d in dias if d['receta_id']}

    # Nombres de ingredientes por receta candidata (validación R1/R2)
    def _nombres_ingredientes(rec_id):
        cur.execute("""
            SELECT i.nombre
            FROM receta_ingrediente ri JOIN ingredientes i ON i.id = ri.ingrediente_id
            WHERE ri.receta_id = %s;
        """, (rec_id,))
        return [r['nombre'] for r in cur.fetchall()]

    for d in dias:
        if not d['receta_id'] or d['cluster_codigo'] is None:
            continue
        costo_actual = _costo_receta_por_racion(cur, d['receta_id'], ctx)
        if not costo_actual or not costo_actual[1]:
            continue  # sin precio completo: no se sugiere sobre base incierta
        cur.execute("""
            SELECT rc.receta_id, r.nombre
            FROM recetas_clusters rc
            JOIN recetas_almuerzo r ON r.id = rc.receta_id
            WHERE rc.modelo_id = %s AND rc.cluster_codigo = %s
              AND rc.receta_id <> %s;
        """, (modelo['id'] if modelo else 0, d['cluster_codigo'], d['receta_id']))
        mejor_alt = None
        for cand in cur.fetchall():
            if cand['receta_id'] in recetas_usadas:
                continue  # variedad: no sugerir algo ya usado en la semana
            if not _cumple_reglas_vigentes(_nombres_ingredientes(cand['receta_id']), re_permitida, re_vetada):
                continue
            costo_alt = _costo_receta_por_racion(cur, cand['receta_id'], ctx)
            if not costo_alt or not costo_alt[1]:
                continue
            if costo_alt[0] < costo_actual[0] and (mejor_alt is None or costo_alt[0] < mejor_alt[0]):
                mejor_alt = (cand['nombre'], costo_alt[0])
        if mejor_alt:
            ahorro_soles = round(costo_actual[0] - mejor_alt[1], 2)
            ahorro_pct = round((ahorro_soles / costo_actual[0]) * 100, 1) if costo_actual[0] else 0
            if ahorro_pct >= UMBRAL_SUGERENCIA_PCT:
                sugerencias.append({
                    'tipo': 'ahorro',
                    'dia_nombre': d['dia_nombre'],
                    'receta_actual': d['receta_nombre'],
                    'receta_sugerida': mejor_alt[0],
                    'ahorro_pct': ahorro_pct,
                    'ahorro_soles_por_racion': ahorro_soles,
                    'texto': (f"Para ahorrar {ahorro_pct}% el {d['dia_nombre']}: reemplace "
                              f"'{d['receta_nombre']}' (S/ {costo_actual[0]:.2f}/ración) por "
                              f"'{mejor_alt[0]}' (S/ {mejor_alt[1]:.2f}/ración) del mismo cluster "
                              f"'{d['cluster_etiqueta'] or 'similar'}'."),
                })

    # Alertas globales
    if margen is not None and margen < 0:
        sugerencias.append({
            'tipo': 'alerta',
            'texto': (f"La recolección proyectada (S/ {recoleccion:.2f}) NO cubre el costo semanal "
                      f"(S/ {costo_total:.2f}): margen negativo de S/ {abs(margen):.2f}. Revise precios "
                      f"de venta o aplique las sugerencias de ahorro."),
        })
    if presupuesto_total and costo_total > presupuesto_total:
        sugerencias.append({
            'tipo': 'alerta',
            'texto': (f"El costo semanal (S/ {costo_total:.2f}) supera el presupuesto declarado "
                      f"(S/ {presupuesto_total:.2f}) en S/ {round(costo_total - presupuesto_total, 2):.2f}."),
        })
    # Variedad: platos repetidos en la semana
    conteo = {}
    for d in dias:
        if d['receta_nombre']:
            conteo[d['receta_nombre']] = conteo.get(d['receta_nombre'], 0) + 1
    for nombre, n in conteo.items():
        if n > 1:
            sugerencias.append({
                'tipo': 'variedad',
                'texto': f"El plato '{nombre}' se repite {n} veces en la semana; considere alternarlo para mejorar la variedad.",
            })

    return {
        'comedor_id': comedor_id,
        'fuente_plan': fuente,
        'plan_id': plan_id,
        'generado_el': fecha_hoy.isoformat(),
        'resumen': {
            'costo_total_semana': round(costo_total, 2),
            'costo_racion_promedio': costo_racion_prom,
            'recoleccion_total_semana': round(recoleccion, 2),
            'margen_proyectado': round(margen, 2),
            'presupuesto_semanal': presupuesto_total,
            'dentro_de_presupuesto': bool(presupuesto_total and costo_total <= presupuesto_total),
            'n_dias': len(dias),
            'total_comensales_dia': comensales_dia,
        },
        'uso_presupuesto_por_dia': uso_por_dia,
        'menu': dias,
        'sugerencias': sugerencias,
        'umbral_sugerencia_pct': UMBRAL_SUGERENCIA_PCT,
    }


def listar_planes_disponibles(cur, comedor_id):
    """COM-50: selector de planes para la UI (propuestas del comedor + planificaciones)."""
    cur.execute("""
        SELECT id, variante, etiqueta, estado, fecha,
               (resumen::jsonb->>'costo_total_semana') AS costo_total_semana
        FROM planificaciones_candidatas
        WHERE comedor_id = %s
        ORDER BY id DESC
        LIMIT 10;
    """, (comedor_id,))
    candidatas = cur.fetchall()
    cur.execute("""
        SELECT id, fecha_referencia, fondo_total, costo_total_semana, viable
        FROM presupuesto_semanal
        ORDER BY id DESC
        LIMIT 10;
    """)
    planificaciones = cur.fetchall()
    return {'propuestas': candidatas, 'planificaciones': planificaciones}