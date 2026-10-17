"""
ml/reportes_comedor.py
Objetivo: COM-77: motor de los 5 REPORTES OPERATIVOS del comedor (Directiva/Tesorero):
  A) estado_resultados(): ingresos reales POS (raciones por tipo x precio vigente y
     caja recaudada) vs ingresos proyectados (recoleccion_proyectada), costo ejecutado
     (costo_total post-subsidio) + valorización del subsidio consumido, margen
     ejecutado vs proyectado y comparación contra MARGEN_SEMANAL_OBJETIVO.
  B) consumo_subsidio(): stock mensual en gramos vs consumo real a la fecha
     (consumo_subsidio_a_la_fecha COM-74) + comprometido futuro
     (consumo_planes_vigentes_mes), semáforo OK/POR_AGOTAR/AGOTADO (umbrales COM-69)
     y FECHA ESTIMADA DE QUIEBRE por insumo (hoy + restante / consumo diario planificado).
  C) inteligencia_compras(): por planificación, fecha_compra (COM-75 v2), fuente de
     precio usada, ahorro IA = (precio promedio 30d previo - precio usado) x gramos
     para ítems PREDICHO/SCRAPER_DIA, y comparativo costo usado vs costo a precio
     promedio del mes.
  D) merma_demanda(): por día, proyectado IA/parámetro (comensales_total) vs atendido
     real (padron_diario), merma = cocinado - atendido, precisión y sesgo acumulado.
  E) semaforo_nutricional(): promedios mensuales por ración de Fe/Prot/Kcal vs metas
     parametrizables (META_* sembradas por esquema_reportes_avanzados) y % de días con
     receta del cluster Anti-Anemia vs cuota mensual (KMEANS_CUOTA_CLUSTER_FEO x semanas).
Fuentes: presupuesto_semanal, planificacion_dia, padron_diario, precios_venta,
historial_precios, subsidio_motor, recetas_clusters (modelo activo).
Supuesto documentado: padron_diario no tiene comedor_id (piloto monocomedor); las
ventas reales se atribuyen al comedor consultado y se informa en cada payload.
Uso: Importado por routers/reportes_avanzados.py (COM-77) y, en COM-78, por el
drill-down municipal (mismas funciones con comedor_id focalizado).
Referencia: ticket COM-77 (solo trazabilidad).
"""
from datetime import date, timedelta

from precios_insumos import (
    precios_por_gramo_por_insumo,
    precios_por_gramo_por_ingrediente,
    gramos_por_unidad_estandar,
)
from subsidio_motor import (
    subsidio_gramos_del_mes,
    consumo_subsidio_a_la_fecha,
    consumo_planes_vigentes_mes,
    precio_venta_vigente,
    margen_semanal_objetivo,
)

# COM-77: umbrales de semáforo de subsidio (coherentes con COM-69)
UMBRAL_POR_AGOTAR = 90.0
# COM-77: fuentes de precio que cuentan como "inteligencia" (dato real del día o IA)
FUENTES_INTELIGENCIA = ('PREDICHO', 'SCRAPER_DIA')


# ==========================================
# UTILIDADES
# ==========================================
def _r2(v):
    return round(float(v), 2) if v is not None else None


def _iso(v):
    return v.isoformat() if isinstance(v, (date,)) else v


def _meta_params(cur):
    """COM-77: metas nutricionales por ración y cuota anti-anemia (parametrizables)."""
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('META_HIERRO_RACION_MG', 'META_PROTEINA_RACION_G',
                        'META_KCAL_RACION', 'KMEANS_CUOTA_CLUSTER_FEO');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    return {
        'hierro': float(p.get('META_HIERRO_RACION_MG', 4.5)),
        'proteina': float(p.get('META_PROTEINA_RACION_G', 22.0)),
        'kcal': float(p.get('META_KCAL_RACION', 750.0)),
        'cuota_anemia_semanal': int(float(p.get('KMEANS_CUOTA_CLUSTER_FEO', 2))),
    }


def _equivalencias(cur):
    cur.execute("""
        SELECT ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso
        FROM ingredientes_equivalencias
        WHERE estado_activo = TRUE;
    """)
    return {(r['ingrediente_id'], r['insumo_id'], r['unidad_uso_id']):
            float(r['gramos_por_unidad_uso']) for r in cur.fetchall()}


def _dias_efectivos(cur, comedor_id, f_ini, f_fin):
    """
    COM-77: días de cocina efectivos del comedor en el rango, deduplicados por fecha
    (si una semana fue reemplazada a mitad de semana, prioriza el plan VIGENTE, mismo
    criterio que consumo_subsidio_a_la_fecha COM-74).
    """
    cur.execute("""
        SELECT ps.id AS plan_id, ps.estado, ps.fecha_referencia,
               pd.dia, pd.dia_nombre, pd.receta_id, pd.nombre_receta,
               pd.comensales_social, pd.comensales_afiliado, pd.comensales_normal,
               COALESCE(pd.comensales_cocinera, 0) AS comensales_cocinera,
               pd.total_comensales, pd.fuente_comensales,
               pd.costo_racion, pd.costo_total, pd.recoleccion_proyectada,
               pd.energia_kcal_racion, pd.hierro_mg_racion, pd.proteina_g_racion,
               (ps.fecha_referencia + (pd.dia - 1)) AS fecha_dia
        FROM presupuesto_semanal ps
        JOIN planificacion_dia pd ON pd.presupuesto_semanal_id = ps.id
        WHERE ps.comedor_id = %s
          AND ps.estado IN ('VIGENTE', 'REEMPLAZADA')
          AND (ps.fecha_referencia + (pd.dia - 1)) BETWEEN %s AND %s
        ORDER BY fecha_dia, (ps.estado = 'VIGENTE') DESC, ps.id DESC;
    """, (comedor_id, f_ini, f_fin))
    vistos = set()
    out = []
    for r in cur.fetchall():
        if r['fecha_dia'] in vistos:
            continue
        vistos.add(r['fecha_dia'])
        out.append(r)
    return sorted(out, key=lambda x: x['fecha_dia'])


def _ventas_por_dia(cur, f_ini, f_fin):
    """COM-77: atención real del POS por día y tipo (padron_diario, sin comedor_id)."""
    cur.execute("""
        SELECT fecha, tipo_comensal_venta AS tipo,
               SUM(raciones)::int AS raciones,
               SUM(monto_pagado) AS monto
        FROM padron_diario
        WHERE fecha BETWEEN %s AND %s
        GROUP BY fecha, tipo_comensal_venta
        ORDER BY fecha;
    """, (f_ini, f_fin))
    out = {}
    for r in cur.fetchall():
        d = out.setdefault(r['fecha'], {'tipos': {}, 'monto': 0.0, 'raciones': 0})
        d['tipos'][r['tipo']] = int(r['raciones'])
        d['monto'] += float(r['monto'] or 0)
        d['raciones'] += int(r['raciones'])
    return out


def _insumo_de_linea(cur, eq_map, ing_id, unidad_uso_id):
    """Insumo vinculado por equivalencia activa (misma regla que lista de compras)."""
    cands = [(ins_id, g) for (i_id, ins_id, uu_id), g in eq_map.items()
             if i_id == ing_id and uu_id == unidad_uso_id]
    if cands:
        return cands[0][0]
    cur.execute("""
        SELECT ins.id FROM insumos ins
        LEFT JOIN historial_precios hp ON hp.insumo_id = ins.id
        WHERE ins.ingrediente_id = %s
        GROUP BY ins.id ORDER BY MAX(hp.fecha) DESC NULLS LAST, ins.id LIMIT 1;
    """, (ing_id,))
    fila = cur.fetchone()
    return fila['id'] if fila else None


def _gramos_semana_plan(cur, plan_id, eq_map):
    """
    COM-77: gramos requeridos por ingrediente en la SEMANA completa del plan
    (réplica de la agregación de lista de compras, sin split de subsidio).
    Retorna lista de {ingrediente_id, insumo_id, gramos}.
    """
    cur.execute("""
        SELECT pd.receta_id, pd.total_comensales,
               COALESCE(NULLIF(ra.raciones, 0), 4) AS raciones
        FROM planificacion_dia pd
        JOIN recetas_almuerzo ra ON ra.id = pd.receta_id
        WHERE pd.presupuesto_semanal_id = %s;
    """, (plan_id,))
    dias = cur.fetchall()
    acum = {}
    for d in dias:
        cur.execute("""
            SELECT ri.ingrediente_id, ri.cantidad_requerida,
                   ri.unidad_medida_id AS unidad_uso_id,
                   um.abreviatura, um.tipo_magnitud, um.factor_a_base,
                   ing.peso_estimado_g
            FROM receta_ingrediente ri
            JOIN unidades_medida um ON um.id = ri.unidad_medida_id
            JOIN ingredientes ing ON ing.id = ri.ingrediente_id
            WHERE ri.receta_id = %s;
        """, (d['receta_id'],))
        for lin in cur.fetchall():
            g = eq_map.get((lin['ingrediente_id'],
                            _insumo_de_linea(cur, eq_map, lin['ingrediente_id'], lin['unidad_uso_id']),
                            lin['unidad_uso_id']))
            if g is None:
                g = gramos_por_unidad_estandar(
                    lin['abreviatura'], lin['tipo_magnitud'],
                    float(lin['factor_a_base'] or 1.0), float(lin['peso_estimado_g'] or 100.0))
            gramos = g * float(lin['cantidad_requerida']) * \
                (float(d['total_comensales']) / float(d['raciones']))
            insumo_id = _insumo_de_linea(cur, eq_map, lin['ingrediente_id'], lin['unidad_uso_id'])
            clave = (lin['ingrediente_id'], insumo_id)
            acum[clave] = acum.get(clave, 0.0) + gramos
    return [{'ingrediente_id': k[0], 'insumo_id': k[1], 'gramos': v} for k, v in acum.items()]


def _unidades_de_insumos(cur, insumo_ids):
    if not insumo_ids:
        return {}
    cur.execute("""
        SELECT ins.id, ins.nombre, um.abreviatura, um.tipo_magnitud,
               um.factor_a_base, ing.peso_estimado_g
        FROM insumos ins
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE ins.id = ANY(%s);
    """, (list(insumo_ids),))
    return {r['id']: r for r in cur.fetchall()}


def _g_compra_de(unidad):
    return gramos_por_unidad_estandar(
        unidad['abreviatura'], unidad['tipo_magnitud'],
        float(unidad['factor_a_base'] or 1.0), float(unidad['peso_estimado_g'] or 100.0))


# ==========================================
# A) ESTADO DE RESULTADOS Y MARGEN REAL
# ==========================================
def estado_resultados(cur, comedor_id, anio, mes):
    f_ini = date(anio, mes, 1)
    f_fin = (f_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias = _dias_efectivos(cur, comedor_id, f_ini, f_fin)
    ventas = _ventas_por_dia(cur, f_ini, f_fin)
    precios_tipo = {t: precio_venta_vigente(cur, t) for t in ('Social', 'Afiliado', 'Normal', 'Cocinera')}

    ingreso_proyectado = sum(float(d['recoleccion_proyectada'] or 0) for d in dias)
    costo_proyectado = sum(float(d['costo_total'] or 0) for d in dias)
    costo_ejecutado = costo_proyectado  # el costo del plan es el costo cocinado (post-subsidio)

    # Ingresos reales: raciones POS por tipo x precio vigente + caja recaudada
    raciones_tipo = {t: 0 for t in precios_tipo}
    caja = 0.0
    for fecha, v in ventas.items():
        caja += v['monto']
        for t, n in v['tipos'].items():
            raciones_tipo[t] = raciones_tipo.get(t, 0) + n
    ingreso_real_tarifa = sum(raciones_tipo.get(t, 0) * p for t, p in precios_tipo.items())

    # Valorización del subsidio consumido en el mes (gramos x ppg de hoy)
    cons_fin = consumo_subsidio_a_la_fecha(cur, comedor_id, f_fin + timedelta(days=1))
    cons_ini = consumo_subsidio_a_la_fecha(cur, comedor_id, f_ini)
    ppg_ing = precios_por_gramo_por_ingrediente(cur, date.today(), fallback_ultima_fecha=True) or {}
    valor_subsidio = 0.0
    detalle_subsidio = []
    for ing_id, g in cons_fin.items():
        g_mes = float(g) - float(cons_ini.get(ing_id, 0.0) or 0.0)
        if g_mes <= 0:
            continue
        ppg = ppg_ing.get(ing_id)
        val = (g_mes * ppg) if ppg else 0.0
        valor_subsidio += val
        detalle_subsidio.append({'ingrediente_id': ing_id, 'gramos': _r2(g_mes), 'valorizado': _r2(val)})

    costo_sin_subsidio = costo_ejecutado + valor_subsidio
    margen_ejecutado = ingreso_real_tarifa - costo_ejecutado
    margen_proyectado = ingreso_proyectado - costo_proyectado
    margen_pct = (margen_ejecutado / costo_ejecutado * 100.0) if costo_ejecutado > 0 else None
    objetivo_pct = margen_semanal_objetivo(cur) * 100.0

    # Desglose semanal (por plan)
    semanas = {}
    for d in dias:
        s = semanas.setdefault(d['plan_id'], {
            'plan_id': d['plan_id'], 'semana': _iso(d['fecha_referencia']), 'estado': d['estado'],
            'ingreso_proyectado': 0.0, 'costo_proyectado': 0.0,
            'ingreso_real_tarifa': 0.0, 'caja_real': 0.0, 'costo_ejecutado': 0.0,
        })
        s['ingreso_proyectado'] += float(d['recoleccion_proyectada'] or 0)
        s['costo_proyectado'] += float(d['costo_total'] or 0)
        s['costo_ejecutado'] += float(d['costo_total'] or 0)
        v = ventas.get(d['fecha_dia'])
        if v:
            s['caja_real'] += v['monto']
            s['ingreso_real_tarifa'] += sum(v['tipos'].get(t, 0) * p for t, p in precios_tipo.items())
    semanas_list = []
    for s in sorted(semanas.values(), key=lambda x: x['semana']):
        s['margen_proyectado'] = _r2(s['ingreso_proyectado'] - s['costo_proyectado'])
        s['margen_ejecutado'] = _r2(s['ingreso_real_tarifa'] - s['costo_ejecutado'])
        s['margen_pct_ejecutado'] = _r2(s['margen_ejecutado'] / s['costo_ejecutado'] * 100) if s['costo_ejecutado'] > 0 else None
        s['cumple_objetivo'] = bool(s['margen_pct_ejecutado'] is not None and s['margen_pct_ejecutado'] >= objetivo_pct)
        for k in ('ingreso_proyectado', 'costo_proyectado', 'ingreso_real_tarifa', 'caja_real', 'costo_ejecutado'):
            s[k] = _r2(s[k])
        semanas_list.append(s)

    return {
        'reporte': 'estado_resultados',
        'comedor_id': comedor_id,
        'anio': anio, 'mes': mes,
        'generado_el': date.today().isoformat(),
        'nota_padron': 'Las ventas reales provienen del POS (padron_diario), que en el piloto no discrimina comedor.',
        'totales': {
            'dias_cocinados': len(dias),
            'raciones_reales_por_tipo': raciones_tipo,
            'ingreso_real_tarifa': _r2(ingreso_real_tarifa),
            'ingreso_real_caja': _r2(caja),
            'ingreso_proyectado': _r2(ingreso_proyectado),
            'costo_ejecutado': _r2(costo_ejecutado),
            'costo_proyectado': _r2(costo_proyectado),
            'valor_subsidio_consumido': _r2(valor_subsidio),
            'costo_sin_subsidio': _r2(costo_sin_subsidio),
            'margen_ejecutado': _r2(margen_ejecutado),
            'margen_proyectado': _r2(margen_proyectado),
            'margen_pct_ejecutado': _r2(margen_pct),
            'margen_objetivo_pct': _r2(objetivo_pct),
            'cumple_objetivo': bool(margen_pct is not None and margen_pct >= objetivo_pct),
        },
        'detalle_subsidio_valorizado': detalle_subsidio,
        'semanas': semanas_list,
    }


# ==========================================
# B) TABLERO DE CONSUMO DE SUBSIDIO (QUIEBRE DE STOCK)
# ==========================================
def consumo_subsidio(cur, comedor_id, anio, mes):
    hoy = date.today()
    stock = subsidio_gramos_del_mes(cur, comedor_id, anio, mes) or {}
    consumo_real = consumo_subsidio_a_la_fecha(cur, comedor_id, hoy)
    consumo_futuro = consumo_planes_vigentes_mes(cur, comedor_id, anio, mes, antes_de=hoy)
    cur.execute("""
        SELECT sm.ingrediente_id, i.nombre AS ingrediente,
               sm.cantidad_recibida, um.abreviatura AS unidad_abrev
        FROM subsidio_mensual sm
        JOIN ingredientes i ON i.id = sm.ingrediente_id
        JOIN unidades_medida um ON um.id = sm.unidad_medida_id
        WHERE sm.comedor_id = %s AND sm.anio = %s AND sm.mes = %s
        ORDER BY i.nombre;
    """, (comedor_id, anio, mes))
    lineas_db = cur.fetchall()

    # Consumo diario promedio planificado restante (menús VIGENTE futuros del mes)
    f_ini = date(anio, mes, 1)
    f_fin = (f_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias_futuros = [d for d in _dias_efectivos(cur, comedor_id, max(hoy, f_ini), f_fin)
                    if d['estado'] == 'VIGENTE']
    n_dias_futuros = max(len(dias_futuros), 0)

    lineas = []
    for l in lineas_db:
        ing_id = l['ingrediente_id']
        g_stock = float(stock.get(ing_id, 0.0) or 0.0)
        g_real = float(consumo_real.get(ing_id, 0.0) or 0.0)
        g_fut = float(consumo_futuro.get(ing_id, 0.0) or 0.0)
        g_total = g_real + g_fut
        restante = g_stock - g_total
        pct = round((g_total / g_stock) * 100, 1) if g_stock > 0 else None
        if g_total <= 0:
            estado = 'SIN_CONSUMO'
        elif g_total > g_stock:
            estado = 'AGOTADO'
        elif pct is not None and pct >= UMBRAL_POR_AGOTAR:
            estado = 'POR_AGOTAR'
        else:
            estado = 'OK'
        # Fecha estimada de quiebre: restante / consumo diario planificado
        consumo_diario = (g_fut / n_dias_futuros) if n_dias_futuros > 0 else 0.0
        fecha_quiebre = None
        if estado in ('OK', 'POR_AGOTAR') and consumo_diario > 0 and restante > 0:
            fecha_quiebre = (hoy + timedelta(days=int(restante // consumo_diario))).isoformat()
        lineas.append({
            'ingrediente_id': ing_id,
            'ingrediente': l['ingrediente'],
            'cantidad_recibida': float(l['cantidad_recibida']),
            'unidad_abrev': l['unidad_abrev'],
            'gramos_stock': _r2(g_stock),
            'gramos_consumo_real': _r2(g_real),
            'gramos_comprometido_futuro': _r2(g_fut),
            'gramos_restante': _r2(restante),
            'pct_uso': pct,
            'estado': estado,
            'consumo_diario_planificado': _r2(consumo_diario),
            'fecha_estimada_quiebre': fecha_quiebre,
        })
    return {
        'reporte': 'consumo_subsidio',
        'comedor_id': comedor_id, 'anio': anio, 'mes': mes,
        'generado_el': hoy.isoformat(),
        'dias_cocina_futuros_del_mes': n_dias_futuros,
        'totales': {
            'ingredientes_con_subsidio': len(lineas),
            'ok': sum(1 for x in lineas if x['estado'] == 'OK'),
            'por_agotar': sum(1 for x in lineas if x['estado'] == 'POR_AGOTAR'),
            'agotados': sum(1 for x in lineas if x['estado'] == 'AGOTADO'),
            'sin_consumo': sum(1 for x in lineas if x['estado'] == 'SIN_CONSUMO'),
        },
        'lineas': lineas,
    }


# ==========================================
# C) INTELIGENCIA DE COMPRAS (AHORRO POR IA)
# ==========================================
def inteligencia_compras(cur, comedor_id, anio, mes):
    f_ini = date(anio, mes, 1)
    f_fin = (f_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias = _dias_efectivos(cur, comedor_id, f_ini, f_fin)
    plan_ids = sorted({d['plan_id'] for d in dias})
    eq_map = _equivalencias(cur)

    planes = []
    tot_ahorro_ia = 0.0
    tot_costo_usado = 0.0
    tot_costo_prom_mes = 0.0
    fuentes_global = {}
    for pid in plan_ids:
        cur.execute("SELECT fecha_referencia FROM presupuesto_semanal WHERE id = %s;", (pid,))
        fref = cur.fetchone()['fecha_referencia']
        cur.execute("SELECT MIN(dia) AS d FROM planificacion_dia WHERE presupuesto_semanal_id = %s;", (pid,))
        dia_min = cur.fetchone()['d'] or 1
        fecha_compra = fref + timedelta(days=dia_min - 1)
        lineas = _gramos_semana_plan(cur, pid, eq_map)
        insumo_ids = {l['insumo_id'] for l in lineas if l['insumo_id']}
        unidades = _unidades_de_insumos(cur, insumo_ids)
        mapa = precios_por_gramo_por_insumo(cur, fecha_compra, fallback_ultima_fecha=True,
                                            insumo_ids=insumo_ids or None) or {}
        # Promedios históricos: 30d previos a la compra y promedio del mes
        cur.execute("""
            SELECT insumo_id, AVG(precio_prom) AS prom30
            FROM historial_precios
            WHERE fecha BETWEEN %s AND %s AND precio_prom IS NOT NULL AND precio_prom > 0
            GROUP BY insumo_id;
        """, (fecha_compra - timedelta(days=30), fecha_compra - timedelta(days=1)))
        prom30 = {r['insumo_id']: float(r['prom30']) for r in cur.fetchall()}
        cur.execute("""
            SELECT insumo_id, AVG(precio_prom) AS prommes
            FROM historial_precios
            WHERE fecha BETWEEN %s AND %s AND precio_prom IS NOT NULL AND precio_prom > 0
            GROUP BY insumo_id;
        """, (f_ini, f_fin))
        prommes = {r['insumo_id']: float(r['prommes']) for r in cur.fetchall()}

        costo_usado = 0.0
        costo_prom_mes = 0.0
        ahorro_plan = 0.0
        fuentes_plan = {}
        top_ahorros = []
        for l in lineas:
            ins_id = l['insumo_id']
            if not ins_id or ins_id not in unidades:
                continue
            g_compra = _g_compra_de(unidades[ins_id])
            if g_compra <= 0:
                continue
            opc = mapa.get(ins_id)
            if not opc:
                continue
            ppg_usado = opc['ppg']
            fuentes_plan[opc['fuente']] = fuentes_plan.get(opc['fuente'], 0) + 1
            fuentes_global[opc['fuente']] = fuentes_global.get(opc['fuente'], 0) + 1
            costo_usado += ppg_usado * l['gramos']
            if ins_id in prommes:
                costo_prom_mes += (prommes[ins_id] / g_compra) * l['gramos']
            if opc['fuente'] in FUENTES_INTELIGENCIA and ins_id in prom30:
                ahorro = ((prom30[ins_id] / g_compra) - ppg_usado) * l['gramos']
                ahorro_plan += ahorro
                top_ahorros.append({
                    'insumo': unidades[ins_id]['nombre'],
                    'fuente': opc['fuente'],
                    'ahorro': _r2(ahorro),
                })
        top_ahorros.sort(key=lambda x: x['ahorro'] or 0, reverse=True)
        planes.append({
            'plan_id': pid,
            'semana': _iso(fref),
            'fecha_compra': _iso(fecha_compra),
            'costo_usado': _r2(costo_usado),
            'costo_promedio_mes': _r2(costo_prom_mes),
            'ahorro_ia': _r2(ahorro_plan),
            'items_por_fuente': fuentes_plan,
            'top_ahorros': top_ahorros[:3],
        })
        tot_ahorro_ia += ahorro_plan
        tot_costo_usado += costo_usado
        tot_costo_prom_mes += costo_prom_mes

    return {
        'reporte': 'inteligencia_compras',
        'comedor_id': comedor_id, 'anio': anio, 'mes': mes,
        'generado_el': date.today().isoformat(),
        'criterio': ('Ahorro IA = (precio promedio 30d previo a la fecha de compra - precio usado) '
                     'x gramos, solo para ítems con fuente PREDICHO o SCRAPER_DIA (COM-75 v2).'),
        'totales': {
            'planes_evaluados': len(planes),
            'ahorro_ia': _r2(tot_ahorro_ia),
            'costo_usado': _r2(tot_costo_usado),
            'costo_a_promedio_mes': _r2(tot_costo_prom_mes),
            'diferencia_usado_vs_prommes': _r2(tot_costo_usado - tot_costo_prom_mes),
            'items_por_fuente': fuentes_global,
        },
        'planes': planes,
    }


# ==========================================
# D) MERMAS Y PRECISIÓN DE DEMANDA
# ==========================================
def merma_demanda(cur, comedor_id, anio, mes):
    f_ini = date(anio, mes, 1)
    f_fin = (f_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias = _dias_efectivos(cur, comedor_id, f_ini, f_fin)
    ventas = _ventas_por_dia(cur, f_ini, f_fin)

    filas = []
    sum_proj = sum_real = sum_merma = 0
    precisions = []
    sesgo = 0.0
    dias_con_ia = 0
    sin_registro = 0
    for d in dias:
        v = ventas.get(d['fecha_dia'])
        proyectado = int(d['total_comensales'] or 0)
        if d.get('fuente_comensales') == 'prediccion_ia':
            dias_con_ia += 1
        if not v:
            sin_registro += 1
            filas.append({
                'fecha': _iso(d['fecha_dia']), 'dia_nombre': d['dia_nombre'],
                'proyectado': proyectado, 'atendido_real': None,
                'merma': None, 'precision': None, 'fuente': d.get('fuente_comensales'),
                'estado': 'SIN_REGISTRO_POS',
            })
            continue
        real = v['raciones']
        merma = proyectado - real
        precision = (1.0 - abs(proyectado - real) / real) if real > 0 else None
        sum_proj += proyectado
        sum_real += real
        sum_merma += merma
        sesgo += merma
        if precision is not None:
            precisions.append(precision)
        filas.append({
            'fecha': _iso(d['fecha_dia']), 'dia_nombre': d['dia_nombre'],
            'proyectado': proyectado, 'atendido_real': real,
            'merma': merma,
            'precision': round(precision * 100, 1) if precision is not None else None,
            'fuente': d.get('fuente_comensales'),
            'estado': 'OK',
        })
    precision_prom = (sum(precisions) / len(precisions) * 100) if precisions else None
    return {
        'reporte': 'merma_demanda',
        'comedor_id': comedor_id, 'anio': anio, 'mes': mes,
        'generado_el': date.today().isoformat(),
        'nota_padron': 'Atención real tomada del POS (padron_diario); días sin registro se marcan SIN_REGISTRO_POS.',
        'totales': {
            'dias_planificados': len(dias),
            'dias_con_registro_pos': len(dias) - sin_registro,
            'dias_sin_registro_pos': sin_registro,
            'raciones_proyectadas': sum_proj,
            'raciones_reales': sum_real,
            'merma_total': sum_merma,
            'precision_promedio_pct': _r2(precision_prom),
            'sesgo_acumulado': sesgo,
            'interpretacion_sesgo': ('La IA sobrestima la demanda (sobre-producción)' if sesgo > 0
                                     else 'La IA subestima la demanda (falta de raciones)' if sesgo < 0
                                     else 'Sin sesgo'),
            'dias_con_prediccion_ia': dias_con_ia,
        },
        'dias': filas,
    }


# ==========================================
# E) SEMÁFORO NUTRICIONAL Y ANEMIA CERO
# ==========================================
def _semaforo(valor, meta):
    if valor is None or meta is None or meta <= 0:
        return 'SIN_DATOS'
    if valor >= meta:
        return 'OK'
    if valor >= 0.9 * meta:
        return 'EN_RIESGO'
    return 'CRITICO'


def semaforo_nutricional(cur, comedor_id, anio, mes):
    f_ini = date(anio, mes, 1)
    f_fin = (f_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    dias = _dias_efectivos(cur, comedor_id, f_ini, f_fin)
    metas = _meta_params(cur)

    # Mapping receta -> cluster del modelo activo (prefijo Anti-Anemia, COM-60)
    cur.execute("SELECT id FROM kmeans_modelos WHERE activo = TRUE ORDER BY id DESC LIMIT 1;")
    mrow = cur.fetchone()
    mapa_anemia = {}
    if mrow:
        cur.execute("""
            SELECT receta_id, cluster_etiqueta FROM recetas_clusters WHERE modelo_id = %s;
        """, (mrow['id'],))
        mapa_anemia = {r['receta_id']: str(r['cluster_etiqueta']) for r in cur.fetchall()}

    n = len(dias)
    prom_fe = sum(float(d['hierro_mg_racion'] or 0) for d in dias) / n if n else None
    prom_pr = sum(float(d['proteina_g_racion'] or 0) for d in dias) / n if n else None
    prom_kc = sum(float(d['energia_kcal_racion'] or 0) for d in dias) / n if n else None
    dias_anemia = sum(1 for d in dias if mapa_anemia.get(d['receta_id'], '').startswith('Anti-Anemia'))
    semanas = max(len({d['plan_id'] for d in dias}), 1)
    cuota_mes = metas['cuota_anemia_semanal'] * semanas

    nutrientes = [
        {'nutriente': 'Hierro (mg/ración)', 'valor': _r2(prom_fe), 'meta': metas['hierro'],
         'semaforo': _semaforo(prom_fe, metas['hierro'])},
        {'nutriente': 'Proteína (g/ración)', 'valor': _r2(prom_pr), 'meta': metas['proteina'],
         'semaforo': _semaforo(prom_pr, metas['proteina'])},
        {'nutriente': 'Energía (kcal/ración)', 'valor': _r2(prom_kc), 'meta': metas['kcal'],
         'semaforo': _semaforo(prom_kc, metas['kcal'])},
    ]
    pct_anemia = round(dias_anemia / n * 100, 1) if n else None
    return {
        'reporte': 'semaforo_nutricional',
        'comedor_id': comedor_id, 'anio': anio, 'mes': mes,
        'generado_el': date.today().isoformat(),
        'dias_evaluados': n,
        'nutrientes': nutrientes,
        'anemia_cero': {
            'dias_con_receta_anti_anemia': dias_anemia,
            'pct_dias_anti_anemia': pct_anemia,
            'cuota_mensual_esperada': cuota_mes,
            'cumple_cuota': bool(dias_anemia >= cuota_mes),
            'semaforo': 'OK' if dias_anemia >= cuota_mes else ('EN_RIESGO' if dias_anemia >= cuota_mes * 0.75 else 'CRITICO'),
        },
        'dias': [
            {
                'fecha': _iso(d['fecha_dia']), 'dia_nombre': d['dia_nombre'],
                'receta': d['nombre_receta'],
                'hierro_mg_racion': _r2(d['hierro_mg_racion']),
                'proteina_g_racion': _r2(d['proteina_g_racion']),
                'energia_kcal_racion': _r2(d['energia_kcal_racion']),
                'es_anti_anemia': bool(mapa_anemia.get(d['receta_id'], '').startswith('Anti-Anemia')),
            } for d in dias
        ],
    }