"""
ml/reportes_municipio.py
Objetivo: COM-78: motor de los 3 REPORTES MACRO de la municipalidad (y Admin de
Sistemas), agregados por zona/comedor con drill-down a los 5 reportes COM-77:
  A) dashboard_distrital(): por comedor: ¿menú VIGENTE esta semana? (sí/no + días),
     margen semanal verde/rojo vs MARGEN_SEMANAL_OBJETIVO, estado de subsidio (peor
     insumo del mes), % cumplimiento nutricional (semáforos COM-77) y raciones de la
     semana; KPIs distritales y orden/filtro por comedores.zona.
  B) observatorio_precios(): canasta crítica (parametro CANASTA_CRITICA_OBSERVATORIO)
     sobre historial_precios: serie por insumo representativo, precio actual,
     variación 7d/30d, volatilidad (σ/μ 30d) y ALERTA temprana si |var7d| supera
     ALERTA_VOLATILIDAD_PCT. Mercado único SISAP (se reporta la última corrida).
  C) cobertura_focalizacion(): raciones reales POS por tipo (Social/Afiliado/Normal/
     Cocinera) vs proyectadas (planificacion_dia de los comedores del alcance) vs
     padrón declarado (comensales); % gratuito real/proyectado/declarado y BRECHA de
     focalización (Ley 31315); tendencia 6 meses y agregado por zona (proyectado).
Fuentes: presupuesto_semanal, planificacion_dia, padron_diario, comensales,
historial_precios, insumos/ingredientes, comedores, parametros_sistema y los
reportes COM-77 (rc.consumo_subsidio / rc.semaforo_nutricional) reutilizados.
Supuestos documentados (piloto):
  * padron_diario y comensales NO tienen comedor_id: los indicadores REALES de
    cobertura son a nivel despliegue y se marcan con nota_padron; el desglose por
    zona usa solo lo proyectado.
  * presupuesto_semanal puede tener filas con comedor_id NULL (ingesta legacy):
    se excluyen al iterar por comedor.
Uso: Importado por routers/reportes_municipio.py (COM-78). El drill-down a un
comedor reutiliza los endpoints COM-77 existentes (sin endpoint nuevo).
Referencia: ticket COM-78 (solo trazabilidad).
"""
import json
import statistics
from datetime import date, timedelta

from subsidio_motor import margen_semanal_objetivo
from ml import reportes_comedor as rc


# ==========================================
# UTILIDADES
# ==========================================
def _r2(v):
    return round(float(v), 2) if v is not None else None


def _pct(num, den):
    return round((float(num) / float(den)) * 100.0, 1) if den else None


def _leer_params(cur):
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('ALERTA_VOLATILIDAD_PCT', 'CANASTA_CRITICA_OBSERVATORIO');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    try:
        umbral = float(p.get('ALERTA_VOLATILIDAD_PCT', 8.0))
    except Exception:
        umbral = 8.0
    try:
        canasta = json.loads(p.get('CANASTA_CRITICA_OBSERVATORIO') or '[]')
        if not isinstance(canasta, list) or not canasta:
            canasta = ['pollo', 'huevo', 'arroz', 'frijol', 'aceite', 'papa', 'cebolla']
    except Exception:
        canasta = ['pollo', 'huevo', 'arroz', 'frijol', 'aceite', 'papa', 'cebolla']
    return umbral, [str(x).lower() for x in canasta]


def _comedores_base(cur, comedor_ids, zona):
    """Comedores del alcance con filtro opcional de zona, ordenados por zona+nombre."""
    q = "SELECT id, nombre, zona FROM comedores WHERE TRUE"
    params = []
    if comedor_ids:
        q += " AND id = ANY(%s)"
        params.append(list(comedor_ids))
    if zona:
        q += " AND LOWER(TRIM(COALESCE(zona,''))) = LOWER(TRIM(%s))"
        params.append(zona)
    q += " ORDER BY zona NULLS LAST, nombre;"
    cur.execute(q, tuple(params) if params else None)
    return [dict(r) for r in cur.fetchall()]


def _plan_vigente_semana(cur, comedor_id, hoy):
    """Plan VIGENTE cuyo rango [fecha_referencia, +dias_operativos-1] cubre `hoy`."""
    cur.execute("""
        SELECT ps.id, ps.fecha_referencia, ps.dias_operativos, ps.margen,
               ps.costo_total_semana, ps.recoleccion_total_proyectada
        FROM presupuesto_semanal ps
        WHERE ps.comedor_id = %s
          AND ps.estado = 'VIGENTE'
          AND ps.fecha_referencia <= %s
          AND (ps.fecha_referencia + GREATEST(COALESCE(ps.dias_operativos,1),1) - 1) >= %s
        ORDER BY ps.fecha_referencia DESC
        LIMIT 1;
    """, (comedor_id, hoy, hoy))
    return cur.fetchone()


# ==========================================
# A) DASHBOARD DISTRITAL DE SEGURIDAD ALIMENTARIA
# ==========================================
def dashboard_distrital(cur, comedor_ids, anio, mes, zona=None):
    hoy = date.today()
    objetivo_pct = margen_semanal_objetivo(cur) * 100.0
    comedores = _comedores_base(cur, comedor_ids, zona)
    filas = []
    kpis = {'n_comedores': len(comedores), 'n_con_menu_vigente': 0,
            'raciones_semana_total': 0, 'margenes_pct': [], 'n_en_riesgo': 0,
            'por_zona': {}}
    for c in comedores:
        cid = c['id']
        zkey = (c['zona'] or 'SIN ZONA').strip()
        kpis['por_zona'].setdefault(zkey, {'n_comedores': 0, 'n_con_menu': 0, 'n_en_riesgo': 0})
        kpis['por_zona'][zkey]['n_comedores'] += 1

        plan = _plan_vigente_semana(cur, cid, hoy)
        tiene_menu = plan is not None
        dias_plan = 0
        raciones_semana = 0
        margen = None
        margen_pct = None
        cumple_margen = None
        if plan:
            cur.execute("""
                SELECT COUNT(*) AS n, COALESCE(SUM(total_comensales),0) AS rac
                FROM planificacion_dia WHERE presupuesto_semanal_id = %s;
            """, (plan['id'],))
            agg = cur.fetchone()
            dias_plan = int(agg['n'] or 0)
            raciones_semana = int(agg['rac'] or 0)
            margen = float(plan['margen']) if plan['margen'] is not None else (
                float(plan['recoleccion_total_proyectada'] or 0) - float(plan['costo_total_semana'] or 0))
            costo = float(plan['costo_total_semana'] or 0)
            margen_pct = _pct(margen, costo) if costo > 0 else None
            cumple_margen = bool(margen_pct is not None and margen_pct >= objetivo_pct)
            kpis['n_con_menu_vigente'] += 1
            kpis['raciones_semana_total'] += raciones_semana
            if margen_pct is not None:
                kpis['margenes_pct'].append(margen_pct)
            kpis['por_zona'][zkey]['n_con_menu'] += 1

        # Subsidio del mes (peor estado entre ingredientes)
        sub = rc.consumo_subsidio(cur, cid, anio, mes)
        t = sub['totales']
        if t['ingredientes_con_subsidio'] == 0:
            estado_sub = 'SIN_SUBSIDIO'
            peor_ing = None
        elif t['agotados'] > 0:
            estado_sub = 'AGOTADO'
            peor_ing = next((l['ingrediente'] for l in sub['lineas'] if l['estado'] == 'AGOTADO'), None)
        elif t['por_agotar'] > 0:
            estado_sub = 'POR_AGOTAR'
            peor_ing = next((l['ingrediente'] for l in sub['lineas'] if l['estado'] == 'POR_AGOTAR'), None)
        else:
            estado_sub = 'OK'
            peor_ing = None

        # Semáforo nutricional del mes
        nut = rc.semaforo_nutricional(cur, cid, anio, mes)
        n_ok = sum(1 for n in nut['nutrientes'] if n['semaforo'] == 'OK')
        pct_nut = _pct(n_ok, len(nut['nutrientes']) or 3)
        sem_nut = 'CRITICO' if any(n['semaforo'] == 'CRITICO' for n in nut['nutrientes']) else (
            'EN_RIESGO' if any(n['semaforo'] == 'EN_RIESGO' for n in nut['nutrientes']) else 'OK')
        cumple_anemia = bool(nut['anemia_cero']['cumple_cuota'])

        en_riesgo = bool(
            (not tiene_menu) or
            (margen is not None and margen < 0) or
            estado_sub in ('AGOTADO', 'POR_AGOTAR') or
            sem_nut == 'CRITICO'
        )
        if en_riesgo:
            kpis['n_en_riesgo'] += 1
            kpis['por_zona'][zkey]['n_en_riesgo'] += 1

        filas.append({
            'comedor_id': cid,
            'comedor_nombre': c['nombre'],
            'zona': c['zona'],
            'menu_vigente_semana': tiene_menu,
            'plan_id': plan['id'] if plan else None,
            'semana_referencia': plan['fecha_referencia'].isoformat() if plan else None,
            'dias_planificados': dias_plan,
            'raciones_semana': raciones_semana,
            'margen_semanal': _r2(margen),
            'margen_pct': margen_pct,
            'cumple_margen_objetivo': cumple_margen,
            'estado_subsidio': estado_sub,
            'subsidio_peor_ingrediente': peor_ing,
            'pct_cumplimiento_nutricional': pct_nut,
            'semaforo_nutricional': sem_nut,
            'cumple_cuota_anemia': cumple_anemia,
            'en_riesgo': en_riesgo,
        })

    kpis['margen_promedio_pct'] = _r2(sum(kpis['margenes_pct']) / len(kpis['margenes_pct'])) \
        if kpis['margenes_pct'] else None
    kpis.pop('margenes_pct', None)
    kpis['por_zona'] = [
        {'zona': z, **v} for z, v in sorted(kpis['por_zona'].items())
    ]
    return {
        'reporte': 'dashboard_distrital',
        'generado_el': hoy.isoformat(),
        'anio': anio, 'mes': mes,
        'zona_filtro': zona,
        'margen_objetivo_pct': _r2(objetivo_pct),
        'kpis': kpis,
        'comedores': filas,
    }


# ==========================================
# B) OBSERVATORIO DE VOLATILIDAD DE PRECIOS
# ==========================================
def _serie_insumo(cur, insumo_id, desde):
    cur.execute("""
        SELECT fecha, MIN(precio_prom) AS precio
        FROM historial_precios
        WHERE insumo_id = %s AND fecha >= %s AND precio_prom IS NOT NULL AND precio_prom > 0
        GROUP BY fecha ORDER BY fecha;
    """, (insumo_id, desde))
    return [(r['fecha'], float(r['precio'])) for r in cur.fetchall()]


def _precio_en_o_antes(serie, fecha_objetivo):
    prev = [p for f, p in serie if f <= fecha_objetivo]
    return prev[-1] if prev else None


def observatorio_precios(cur, dias=90):
    hoy = date.today()
    umbral, canasta = _leer_params(cur)
    desde = hoy - timedelta(days=dias)
    cur.execute("""
        SELECT MAX(fecha) AS f, MIN(fecha) AS m, COUNT(DISTINCT mercado) AS n_mercados
        FROM historial_precios;
    """)
    glob = cur.fetchone()
    items = []
    alertas = []
    for token in canasta:
        cur.execute("""
            SELECT i.id AS ing_id, i.nombre AS ing_nombre
            FROM ingredientes i
            WHERE LOWER(i.nombre) LIKE %s
            ORDER BY i.nombre;
        """, (f'%{token}%',))
        ings = cur.fetchall()
        if not ings:
            items.append({'token': token, 'match': None, 'detalle': 'Sin ingrediente que calce'})
            continue
        ing_ids = [i['ing_id'] for i in ings]
        cur.execute("""
            SELECT ins.id, ins.nombre, COUNT(hp.id) AS n
            FROM insumos ins
            LEFT JOIN historial_precios hp ON hp.insumo_id = ins.id
            WHERE ins.ingrediente_id = ANY(%s)
            GROUP BY ins.id, ins.nombre
            ORDER BY n DESC, ins.id
            LIMIT 1;
        """, (ing_ids,))
        rep = cur.fetchone()
        if not rep or not rep['n']:
            items.append({'token': token, 'match': ings[0]['ing_nombre'],
                          'insumo_representativo': rep['nombre'] if rep else None,
                          'detalle': 'Sin histórico de precios'})
            continue
        serie = _serie_insumo(cur, rep['id'], desde)
        if len(serie) < 2:
            items.append({'token': token, 'match': ings[0]['ing_nombre'],
                          'insumo_representativo': rep['nombre'],
                          'detalle': 'Serie insuficiente'})
            continue
        f_ult, p_ult = serie[-1]
        p_7 = _precio_en_o_antes(serie, f_ult - timedelta(days=7))
        p_30 = _precio_en_o_antes(serie, f_ult - timedelta(days=30))
        var7 = _pct(p_ult - p_7, p_7) if p_7 else None
        var30 = _pct(p_ult - p_30, p_30) if p_30 else None
        ventana30 = [p for f, p in serie if f >= f_ult - timedelta(days=30)]
        vol = round((statistics.pstdev(ventana30) / statistics.mean(ventana30)) * 100, 1) \
            if len(ventana30) > 1 and statistics.mean(ventana30) > 0 else None
        alerta = bool(var7 is not None and abs(var7) > umbral)
        if alerta:
            alertas.append({'token': token, 'insumo': rep['nombre'], 'var_7d_pct': var7})
        items.append({
            'token': token,
            'match': ', '.join(i['ing_nombre'] for i in ings[:3]),
            'n_ingredientes': len(ings),
            'insumo_representativo': rep['nombre'],
            'precio_actual': _r2(p_ult),
            'fecha_actual': f_ult.isoformat(),
            'var_7d_pct': var7,
            'var_30d_pct': var30,
            'volatilidad_30d_pct': vol,
            'alerta': alerta,
            'serie': [{'fecha': f.isoformat(), 'precio': _r2(p)} for f, p in serie],
        })
    return {
        'reporte': 'observatorio_precios',
        'generado_el': hoy.isoformat(),
        'mercados': glob['n_mercados'],
        'primera_corrida': glob['m'].isoformat() if glob['m'] else None,
        'ultima_corrida': glob['f'].isoformat() if glob['f'] else None,
        'umbral_alerta_pct': umbral,
        'ventana_dias': dias,
        'alertas': alertas,
        'canasta': items,
    }


# ==========================================
# C) COBERTURA Y FOCALIZACIÓN SOCIAL (Ley 31315)
# ==========================================
def _rango_mes(anio, mes):
    f_ini = date(anio, mes, 1)
    f_fin = (f_ini + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return f_ini, f_fin


def cobertura_focalizacion(cur, comedor_ids, anio, mes, zona=None):
    f_ini, f_fin = _rango_mes(anio, mes)
    comedores = _comedores_base(cur, comedor_ids, zona)
    cids = [c['id'] for c in comedores]

    # Reales POS (nivel despliegue: padron_diario sin comedor_id)
    cur.execute("""
        SELECT tipo_comensal_venta AS tipo, COALESCE(SUM(raciones),0) AS rac
        FROM padron_diario WHERE fecha BETWEEN %s AND %s
        GROUP BY 1;
    """, (f_ini, f_fin))
    reales = {r['tipo']: int(r['rac']) for r in cur.fetchall()}

    # Proyectadas (planes efectivos de los comedores del alcance, dedup por fecha)
    proy = {'Social': 0, 'Afiliado': 0, 'Normal': 0, 'Cocinera': 0}
    por_zona = {}
    for c in comedores:
        dias = rc._dias_efectivos(cur, c['id'], f_ini, f_fin)
        zkey = (c['zona'] or 'SIN ZONA').strip()
        z = por_zona.setdefault(zkey, {'zona': zkey, 'n_comedores': 0,
                                       'Social': 0, 'Afiliado': 0, 'Normal': 0, 'Cocinera': 0})
        if not z['n_comedores']:
            z['n_comedores'] = 1
        for d in dias:
            vals = {
                'Social': int(d['comensales_social'] or 0),
                'Afiliado': int(d['comensales_afiliado'] or 0),
                'Normal': int(d['comensales_normal'] or 0),
                'Cocinera': int(d['comensales_cocinera'] or 0),
            }
            for k, v in vals.items():
                proy[k] += v
                z[k] += v
    por_zona_list = []
    for z in sorted(por_zona.values(), key=lambda x: x['zona']):
        z['total'] = z['Social'] + z['Afiliado'] + z['Normal'] + z['Cocinera']
        z['pct_gratuito_proyectado'] = _pct(z['Social'], z['total'])
        por_zona_list.append(z)

    # Padrón declarado (fichas comensales, nivel despliegue)
    cur.execute("""
        SELECT tipo_comensal AS tipo, COUNT(*) AS fichas
        FROM comensales GROUP BY 1;
    """)
    declaradas = {r['tipo']: int(r['fichas']) for r in cur.fetchall()}

    total_real = sum(reales.values())
    total_proy = sum(proy.values())
    total_dec = sum(declaradas.values())
    pcts = {
        'pct_gratuito_real': _pct(reales.get('Social', 0), total_real),
        'pct_gratuito_proyectado': _pct(proy['Social'], total_proy),
        'pct_gratuito_declarado': _pct(declaradas.get('Social', 0), total_dec),
        'pct_pagante_real': _pct(reales.get('Afiliado', 0) + reales.get('Normal', 0), total_real),
    }
    # COM-78 FIX: typo corregido (pct_gratuito_declarado, no pct_gratuido_declarado)
    brecha = None
    if pcts['pct_gratuito_real'] is not None and pcts['pct_gratuito_declarado'] is not None:
        brecha = round(pcts['pct_gratuito_real'] - pcts['pct_gratuito_declarado'], 1)

    # Tendencia 6 meses (reales POS)
    tendencia = []
    for i in range(5, -1, -1):
        f = date(anio, mes, 1)
        for _ in range(i):
            f = (f - timedelta(days=1)).replace(day=1)
        ti, tf = _rango_mes(f.year, f.month)
        cur.execute("""
            SELECT tipo_comensal_venta AS tipo, COALESCE(SUM(raciones),0) AS rac
            FROM padron_diario WHERE fecha BETWEEN %s AND %s GROUP BY 1;
        """, (ti, tf))
        mm = {r['tipo']: int(r['rac']) for r in cur.fetchall()}
        tot = sum(mm.values())
        tendencia.append({
            'anio': f.year, 'mes': f.month,
            'social': mm.get('Social', 0), 'afiliado': mm.get('Afiliado', 0),
            'normal': mm.get('Normal', 0), 'cocinera': mm.get('Cocinera', 0),
            'total': tot,
            'pct_gratuito': _pct(mm.get('Social', 0), tot),
        })

    return {
        'reporte': 'cobertura_focalizacion',
        'generado_el': date.today().isoformat(),
        'anio': anio, 'mes': mes,
        'zona_filtro': zona,
        'n_comedores': len(cids),
        'nota_padron': ('padron_diario y comensales no discriminan comedor en el piloto: '
                        'los indicadores reales y declarados son a nivel despliegue; '
                        'el desglose por zona usa solo raciones proyectadas.'),
        'reales_pos': reales,
        'proyectadas': proy,
        'declaradas_padron': declaradas,
        'totales': {'real': total_real, 'proyectado': total_proy, 'declarado': total_dec},
        'pcts': pcts,
        'brecha_focalizacion_pp': brecha,
        'tendencia_mensual': tendencia,
        'por_zona': por_zona_list,
    }