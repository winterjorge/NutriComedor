"""
ml/reporte_gestion.py
Objetivo: COM-50 (HU-10): motor del reporte "Resumen ejecutivo y recomendaciones",
          con tres niveles de alcance (COM-50 v3):
            * 'comedor': indicadores de un solo comedor (menú, costos, sugerencias).
            * 'zona':    agregado de los comedores de una zona (ej. "Motupe").
            * 'macro':   agregado de todos los comedores del alcance del solicitante.
          Produce: resumen ejecutivo, uso de presupuesto por día (gráfico de barras),
          menú del plan y sugerencias automáticas (ahorro dentro del mismo cluster
          K-means, alertas de margen/presupuesto y variedad).
Historial:
 - COM-50 v1/v2: versión por comedor con blindaje parcial.
 - COM-50 v3 (este archivo): FIX definitivo del IndexError "tuple index out of range" y
   soporte multi-comedor:
     * Se ELIMINA la dependencia del fallback legacy de precios
       (mejor_opcion_ingrediente / obtener_precio_manual_por_gramo): el reporte costea
       solo con fuentes modernas (scraper día/última corrida, manual de insumo,
       predicción RF). Un ingrediente sin esas fuentes marca la receta como
       "precio incompleto" y se omite de sugerencias (no interrumpe el reporte).
     * CERO indexado posicional de tuplas/filas: todo acceso por nombre con guardas.
     * Cada comedor y cada día se procesan aislados (try/except + traceback en logs):
       un dato malo degrada ese elemento, no tumba el reporte completo.
     * Agregación macro/zona: totales, uso por día sumado y sugerencias con el nombre
       del comedor al que pertenecen.
Uso: Importado por routers/reportes_gestion.py. Recibe cursor psycopg2 (RealDictCursor).
Referencia: tickets COM-50 / HU-10 (solo trazabilidad).
"""
import json
import traceback
from datetime import date

from precios_insumos import (
    precios_por_gramo_por_insumo,
    gramos_por_unidad_estandar,
    gramos_por_unidad_compra,
)
from optimizador import predecir_precio_con_confianza
from ml.kmeans_recetas import cargar_reglas_proteinas, _normalizar, obtener_modelo_activo

# Ahorro mínimo (%) para que un reemplazo se reporte como sugerencia (HU-10: ej. 5%)
UMBRAL_SUGERENCIA_PCT = 5.0


# ==========================================
# UTILIDADES DEFENSIVAS (COM-50 v3)
# ==========================================
def _f(valor, por_defecto=0.0):
    """Convierte cualquier NUMERIC/str/None a float sin lanzar excepciones."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def _cargar_equivalencias_local(cur):
    """Mapa {(ingrediente_id, insumo_id, unidad_uso_id): gramos} activas (consulta propia)."""
    cur.execute("""
        SELECT ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso
        FROM ingredientes_equivalencias
        WHERE estado_activo = TRUE;
    """)
    out = {}
    for r in cur.fetchall():
        out[(r['ingrediente_id'], r['insumo_id'], r['unidad_uso_id'])] = _f(r['gramos_por_unidad_uso'])
    return out


def _nuevo_contexto(cur, fecha):
    return {
        'fecha': fecha,
        'precios_insumo': precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=True),
        'eq_map': _cargar_equivalencias_local(cur),
        'cache_costo': {},
    }


# ==========================================
# COSTEO SIN FALLBACK LEGACY (COM-50 v3)
# ==========================================
def _mejor_opcion_sin_legacy(cur, ing_id, fecha, precios_insumo, peso_estimado_g):
    """
    Mejor (menor costo por gramo) opción de precio para un ingrediente usando SOLO
    fuentes modernas: scraper (día o última corrida), manual de insumo o predicción RF.
    COM-50 v3: no se consulta el legacy por ingrediente (fuente del IndexError histórico).
    """
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
               um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo, um.factor_a_base AS u_factor
        FROM insumos ins
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        WHERE ins.ingrediente_id = %s;
    """, (ing_id,))
    mejor = None
    for ins in cur.fetchall():
        try:
            opc = precios_insumo.get(ins['insumo_id'])
            confianza = None
            if opc:
                ppg = _f(opc.get('ppg'))
                fuente = opc.get('fuente')
                precio_unidad = opc.get('precio_por_unidad')
                unidad_compra = opc.get('unidad_compra_abrev')
            else:
                pred, conf, ok = predecir_precio_con_confianza(ins['insumo_id'], fecha, cur.connection, cur)
                if not (ok and pred):
                    continue
                g_compra = gramos_por_unidad_compra(
                    ins['u_abrev'], ins['u_tipo'], _f(ins['u_factor'], 1.0), peso_estimado_g)
                if g_compra <= 0:
                    continue
                ppg = _f(pred) / g_compra
                fuente = 'PREDICHO'
                confianza = conf
                precio_unidad = pred
                unidad_compra = ins['u_abrev']
            if ppg <= 0:
                continue
            if mejor is None or ppg < mejor['ppg']:
                mejor = {
                    'insumo_id': ins['insumo_id'],
                    'insumo_nombre': ins['insumo_nombre'],
                    'ppg': ppg,
                    'fuente': fuente,
                    'confianza': confianza,
                    'precio_unidad_compra': precio_unidad,
                    'unidad_compra': unidad_compra,
                }
        except Exception:
            traceback.print_exc()
            continue
    return mejor


def _costo_receta_por_racion(cur, receta_id, ctx):
    """
    COM-50 v3: costo por ración con multiplicación explícita
    (gramos_por_unidad × cantidad) y sin fallback legacy.
    Retorna (costo_por_racion, precio_completo) o None si la receta no existe.
    """
    if receta_id in ctx['cache_costo']:
        return ctx['cache_costo'][receta_id]
    cur.execute("SELECT raciones FROM recetas_almuerzo WHERE id = %s;", (receta_id,))
    fila_rec = cur.fetchone()
    if not fila_rec:
        return None
    raciones = _f(fila_rec.get('raciones'), 0.0) or 4.0
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
        try:
            peso = _f(fila.get('peso_estimado_g'), 100.0)
            opc = _mejor_opcion_sin_legacy(cur, fila['ingrediente_id'], ctx['fecha'], ctx['precios_insumo'], peso)
            if opc is None:
                completo = False
                continue
            g = ctx['eq_map'].get((fila['ingrediente_id'], opc['insumo_id'], fila['unidad_medida_id']))
            if g is None:
                g = gramos_por_unidad_estandar(
                    fila.get('unidad_abrev'), fila.get('tipo_magnitud'),
                    _f(fila.get('factor_a_base'), 1.0), peso)
            total += (_f(g) * _f(fila.get('cantidad_requerida'))) * _f(opc['ppg'])
        except Exception:
            traceback.print_exc()
            completo = False
    resultado = (round(total / raciones, 2), completo)
    ctx['cache_costo'][receta_id] = resultado
    return resultado


def _cumple_reglas_vigentes(nombres, re_permitida, re_vetada):
    """R1/R2 compactas; si no hay reglas configuradas, se acepta la receta."""
    if re_permitida is None or re_vetada is None:
        return True
    tiene_permitida = False
    tiene_vetada = False
    for nombre in nombres:
        nn = _normalizar(nombre)
        if not nn:
            continue
        if re_permitida.search(nn):
            tiene_permitida = True
        elif re_vetada.search(nn):
            tiene_vetada = True
    return tiene_permitida and not tiene_vetada


# ==========================================
# RESOLUCIÓN DEL PLAN DE UN COMEDOR
# ==========================================
def _resolver_plan(cur, comedor_id, candidata_id=None, presupuesto_id=None):
    """(fuente, dias, resumen_base, presupuesto_total, plan_id) con precedencia:
    candidata indicada -> última seleccionada -> última candidata -> planificación."""
    cand = None
    fuente = None
    if candidata_id:
        cur.execute("SELECT * FROM planificaciones_candidatas WHERE id = %s AND comedor_id = %s;",
                    (candidata_id, comedor_id))
        cand = cur.fetchone()
        fuente = 'propuesta_indicada'
    if cand is None:
        cur.execute("""
            SELECT * FROM planificaciones_candidatas
            WHERE comedor_id = %s AND estado ILIKE 'seleccion%%'
            ORDER BY id DESC LIMIT 1;
        """, (comedor_id,))
        cand = cur.fetchone()
        fuente = 'propuesta_seleccionada'
    if cand is None:
        cur.execute("""
            SELECT * FROM planificaciones_candidatas
            WHERE comedor_id = %s ORDER BY id DESC LIMIT 1;
        """, (comedor_id,))
        cand = cur.fetchone()
        fuente = 'propuesta_ultima'
    if cand is not None:
        menu = cand['menu'] if isinstance(cand['menu'], list) else json.loads(cand['menu'] or '[]')
        resumen_base = cand['resumen'] if isinstance(cand['resumen'], dict) else json.loads(cand['resumen'] or '{}')
        dias = []
        for d in (menu if isinstance(menu, list) else []):
            if not isinstance(d, dict):
                continue
            dias.append({
                'dia_semana': d.get('dia_semana'),
                'dia_nombre': d.get('dia_nombre'),
                'fecha': d.get('fecha'),
                'receta_id': d.get('receta_id'),
                'receta_nombre': d.get('receta_nombre'),
                'costo_racion': _f(d.get('costo_racion')),
                'costo_total_dia': _f(d.get('costo_total_dia')),
                'recoleccion_proyectada': _f(d.get('recoleccion_proyectada')),
                'total_comensales': None,
                'cluster_codigo': d.get('cluster_codigo'),
                'cluster_etiqueta': d.get('cluster_etiqueta'),
            })
        return fuente, dias, resumen_base, resumen_base.get('presupuesto_semanal'), cand['id']

    pres = None
    if presupuesto_id:
        cur.execute("SELECT * FROM presupuesto_semanal WHERE id = %s;", (presupuesto_id,))
        pres = cur.fetchone()
        fuente = 'planificacion_indicada'
    else:
        cur.execute("SELECT * FROM presupuesto_semanal ORDER BY id DESC LIMIT 1;")
        pres = cur.fetchone()
        fuente = 'planificacion_ultima'
    if pres is None:
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
        'costo_racion': _f(r['costo_racion']),
        'costo_total_dia': _f(r['costo_total']),
        'recoleccion_proyectada': _f(r['recoleccion_proyectada']),
        'total_comensales': r['total_comensales'],
        'cluster_codigo': None,
        'cluster_etiqueta': None,
    } for r in cur.fetchall()]
    resumen_base = {
        'costo_total_semana': _f(pres['costo_total_semana']),
        'recoleccion_total_semana': _f(pres['recoleccion_total_proyectada']),
        'margen_proyectado': _f(pres['margen']),
        'dentro_de_presupuesto': bool(pres['viable']),
    }
    return fuente, dias, resumen_base, _f(pres['fondo_total']), pres['id']


# ==========================================
# REPORTE DE UN SOLO COMEDOR
# ==========================================
def _reporte_un_comedor(cur, comedor_id, candidata_id=None, presupuesto_id=None):
    """Reporte completo de un comedor; None si no tiene plan o falla (traza en logs)."""
    try:
        fuente, dias, resumen_base, presupuesto_total, plan_id = _resolver_plan(
            cur, comedor_id, candidata_id, presupuesto_id)
        if not dias:
            return None
        fecha_hoy = date.today()
        ctx = _nuevo_contexto(cur, fecha_hoy)

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
            par = cluster_por_receta.get(d['receta_id'])
            if d['cluster_codigo'] is None and par is not None and len(par) >= 2:
                d['cluster_codigo'] = par[0]
                d['cluster_etiqueta'] = par[1]

        costo_total = _f(resumen_base.get('costo_total_semana')) or round(sum(d['costo_total_dia'] for d in dias), 2)
        recoleccion = _f(resumen_base.get('recoleccion_total_semana')) or round(sum(d['recoleccion_proyectada'] for d in dias), 2)
        margen = resumen_base.get('margen_proyectado')
        margen = _f(margen) if margen is not None else round(recoleccion - costo_total, 2)
        comensales_dia = resumen_base.get('total_comensales_dia') or next(
            (d['total_comensales'] for d in dias if d['total_comensales']), None)
        costo_racion_prom = _f(resumen_base.get('costo_racion_promedio')) or (
            round(sum(d['costo_racion'] for d in dias) / len(dias), 2) if dias else 0)

        uso_por_dia = []
        for d in dias:
            pct = round((d['costo_total_dia'] / _f(presupuesto_total)) * 100, 2) if _f(presupuesto_total) else None
            uso_por_dia.append({
                'dia_nombre': d['dia_nombre'],
                'fecha': d['fecha'],
                'costo_total_dia': d['costo_total_dia'],
                'recoleccion_proyectada': d['recoleccion_proyectada'],
                'costo_racion': d['costo_racion'],
                'pct_del_presupuesto': pct,
            })

        # ---- Sugerencias (bloque aislado por día) ----
        sugerencias = []
        nota = None
        try:
            reglas = cargar_reglas_proteinas(cur)
            re_permitida = reglas[0] if len(reglas) > 0 else None
            re_vetada = reglas[1] if len(reglas) > 1 else None
            recetas_usadas = {d['receta_id'] for d in dias if d['receta_id']}

            def _nombres_ingredientes(rec_id):
                cur.execute("""
                    SELECT i.nombre
                    FROM receta_ingrediente ri JOIN ingredientes i ON i.id = ri.ingrediente_id
                    WHERE ri.receta_id = %s;
                """, (rec_id,))
                return [r['nombre'] for r in cur.fetchall()]

            for d in dias:
                try:
                    if not d['receta_id'] or d['cluster_codigo'] is None or modelo is None:
                        continue
                    costo_actual = _costo_receta_por_racion(cur, d['receta_id'], ctx)
                    if not costo_actual or not costo_actual[1]:
                        continue
                    cur.execute("""
                        SELECT rc.receta_id, r.nombre
                        FROM recetas_clusters rc
                        JOIN recetas_almuerzo r ON r.id = rc.receta_id
                        WHERE rc.modelo_id = %s AND rc.cluster_codigo = %s AND rc.receta_id <> %s;
                    """, (modelo['id'], d['cluster_codigo'], d['receta_id']))
                    mejor_alt = None
                    for cand in cur.fetchall():
                        if cand['receta_id'] in recetas_usadas:
                            continue
                        if not _cumple_reglas_vigentes(_nombres_ingredientes(cand['receta_id']), re_permitida, re_vetada):
                            continue
                        costo_alt = _costo_receta_por_racion(cur, cand['receta_id'], ctx)
                        if not costo_alt or not costo_alt[1]:
                            continue
                        if costo_alt[0] < costo_actual[0] and (mejor_alt is None or costo_alt[0] < mejor_alt[0]):
                            mejor_alt = {'nombre': cand['nombre'], 'costo': costo_alt[0]}
                    if mejor_alt:
                        ahorro_soles = round(costo_actual[0] - mejor_alt['costo'], 2)
                        ahorro_pct = round((ahorro_soles / costo_actual[0]) * 100, 1) if costo_actual[0] else 0
                        if ahorro_pct >= UMBRAL_SUGERENCIA_PCT:
                            sugerencias.append({
                                'tipo': 'ahorro',
                                'dia_nombre': d['dia_nombre'],
                                'receta_actual': d['receta_nombre'],
                                'receta_sugerida': mejor_alt['nombre'],
                                'ahorro_pct': ahorro_pct,
                                'ahorro_soles_por_racion': ahorro_soles,
                                'texto': (f"Para ahorrar {ahorro_pct}% el {d['dia_nombre']}: reemplace "
                                          f"'{d['receta_nombre']}' (S/ {costo_actual[0]:.2f}/ración) por "
                                          f"'{mejor_alt['nombre']}' (S/ {mejor_alt['costo']:.2f}/ración) del mismo cluster "
                                          f"'{d['cluster_etiqueta'] or 'similar'}'."),
                            })
                except Exception:
                    traceback.print_exc()
                    continue

            if margen < 0:
                sugerencias.append({
                    'tipo': 'alerta',
                    'texto': (f"La recolección proyectada (S/ {recoleccion:.2f}) NO cubre el costo semanal "
                              f"(S/ {costo_total:.2f}): margen negativo de S/ {abs(margen):.2f}."),
                })
            if _f(presupuesto_total) and costo_total > _f(presupuesto_total):
                sugerencias.append({
                    'tipo': 'alerta',
                    'texto': (f"El costo semanal (S/ {costo_total:.2f}) supera el presupuesto declarado "
                              f"(S/ {_f(presupuesto_total):.2f})."),
                })
            conteo = {}
            for d in dias:
                if d['receta_nombre']:
                    conteo[d['receta_nombre']] = conteo.get(d['receta_nombre'], 0) + 1
            for nombre, n in conteo.items():
                if n > 1:
                    sugerencias.append({
                        'tipo': 'variedad',
                        'texto': f"El plato '{nombre}' se repite {n} veces en la semana; considere alternarlo.",
                    })
        except Exception:
            traceback.print_exc()
            nota = 'No fue posible calcular las sugerencias de ahorro en esta ejecución; el resto del reporte es válido.'

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
                'dentro_de_presupuesto': bool(_f(presupuesto_total) and costo_total <= _f(presupuesto_total)),
                'n_dias': len(dias),
                'total_comensales_dia': comensales_dia,
            },
            'uso_presupuesto_por_dia': uso_por_dia,
            'menu': dias,
            'sugerencias': sugerencias,
            'nota_sugerencias': nota,
            'umbral_sugerencia_pct': UMBRAL_SUGERENCIA_PCT,
        }
    except Exception:
        traceback.print_exc()
        return None


# ==========================================
# API PÚBLICA: REPORTE CON NIVEL DE ALCANCE
# ==========================================
def generar_reporte_gestion(cur, comedores_alcance, nivel='comedor', zona=None,
                            comedor_id=None, candidata_id=None, presupuesto_id=None):
    """
    COM-50 v3: genera el reporte según el nivel:
      * 'comedor': un solo comedor (debe estar dentro del alcance del solicitante).
      * 'zona':    agregado de los comedores del alcance cuya zona coincide.
      * 'macro':   agregado de todos los comedores del alcance.
    `comedores_alcance`: lista de dicts {id, nombre, zona} ya filtrada por permisos
    en el router. Retorna dict de reporte o {'error': ...}.
    """
    if not comedores_alcance:
        return {'error': 'sin_alcance',
                'detalle': 'Su perfil no tiene comedores asignados para reportería.'}

    if nivel == 'comedor':
        objetivo = [c for c in comedores_alcance if c['id'] == comedor_id]
        if not objetivo:
            return {'error': 'fuera_de_alcance',
                    'detalle': 'El comedor solicitado no pertenece a su alcance de reportería.'}
        rep = _reporte_un_comedor(cur, objetivo[0]['id'], candidata_id, presupuesto_id)
        if rep is None:
            return {'error': 'sin_plan',
                    'detalle': 'El comedor aún no tiene propuestas seleccionadas ni planificaciones guardadas.'}
        rep['nivel'] = 'comedor'
        rep['comedor_nombre'] = objetivo[0]['nombre']
        rep['comedores_incluidos'] = objetivo
        return rep

    # ---- niveles zona / macro: agregado multi-comedor ----
    if nivel == 'zona':
        if not zona:
            return {'error': 'zona_requerida', 'detalle': 'Indique la zona a reportar.'}
        objetivos = [c for c in comedores_alcance if (c.get('zona') or '').strip().lower() == zona.strip().lower()]
        if not objetivos:
            # coincidencia parcial como fallback amigable
            objetivos = [c for c in comedores_alcance if zona.strip().lower() in (c.get('zona') or '').strip().lower()]
    else:
        objetivos = list(comedores_alcance)
    if not objetivos:
        return {'error': 'sin_datos', 'detalle': 'No hay comedores en el nivel seleccionado.'}

    fecha_hoy = date.today()
    por_comedor = []
    sugerencias = []
    uso_agregado = {}
    tot_costo = tot_rec = tot_pres = 0.0
    todos_dentro = True
    for c in objetivos:
        rep = _reporte_un_comedor(cur, c['id'])
        if rep is None:
            continue
        por_comedor.append({
            'comedor_id': c['id'],
            'comedor_nombre': c['nombre'],
            'zona': c.get('zona'),
            'fuente_plan': rep['fuente_plan'],
            'resumen': rep['resumen'],
            'menu': rep['menu'],
        })
        tot_costo += _f(rep['resumen']['costo_total_semana'])
        tot_rec += _f(rep['resumen']['recoleccion_total_semana'])
        tot_pres += _f(rep['resumen']['presupuesto_semanal'])
        todos_dentro = todos_dentro and bool(rep['resumen']['dentro_de_presupuesto'])
        for u in rep['uso_presupuesto_por_dia']:
            clave = u['dia_nombre']
            if clave not in uso_agregado:
                uso_agregado[clave] = {'dia_nombre': clave, 'costo_total_dia': 0.0, 'recoleccion_proyectada': 0.0}
            uso_agregado[clave]['costo_total_dia'] += _f(u['costo_total_dia'])
            uso_agregado[clave]['recoleccion_proyectada'] += _f(u['recoleccion_proyectada'])
        for s in rep['sugerencias']:
            s2 = dict(s)
            s2['comedor_nombre'] = c['nombre']
            s2['texto'] = f"[{c['nombre']}] {s['texto']}"
            sugerencias.append(s2)

    if not por_comedor:
        return {'error': 'sin_plan',
                'detalle': 'Ningún comedor del nivel seleccionado tiene planes guardados aún.'}

    orden_dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    uso_lista = sorted(uso_agregado.values(),
                       key=lambda u: orden_dias.index(u['dia_nombre']) if u['dia_nombre'] in orden_dias else 99)
    for u in uso_lista:
        u['costo_total_dia'] = round(u['costo_total_dia'], 2)
        u['recoleccion_proyectada'] = round(u['recoleccion_proyectada'], 2)
        u['pct_del_presupuesto'] = round((u['costo_total_dia'] / tot_pres) * 100, 2) if tot_pres else None

    margen = round(tot_rec - tot_costo, 2)
    return {
        'nivel': nivel,
        'zona': zona if nivel == 'zona' else None,
        'generado_el': fecha_hoy.isoformat(),
        'comedores_incluidos': objetivos,
        'resumen': {
            'costo_total_semana': round(tot_costo, 2),
            'recoleccion_total_semana': round(tot_rec, 2),
            'margen_proyectado': margen,
            'presupuesto_semanal': round(tot_pres, 2) if tot_pres else None,
            'dentro_de_presupuesto': todos_dentro,
            'n_comedores_con_plan': len(por_comedor),
            'costo_racion_promedio': round(
                sum(_f(p['resumen']['costo_racion_promedio']) for p in por_comedor) / len(por_comedor), 2),
        },
        'uso_presupuesto_por_dia': uso_lista,
        'por_comedor': por_comedor,
        'menu': [],
        'sugerencias': sugerencias[:20],
        'nota_sugerencias': None,
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