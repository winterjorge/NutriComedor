"""
precios_insumos.py
Objetivo: COM-37 v5: resolución unificada de (a) equivalencias unidad de USO -> gramos
y (b) precios por gramo de cada insumo/ingrediente en una fecha, combinando
las fuentes con precedencia.
Historial:
COM-37 v5: versión original (scraper día + manual insumo + legacy).
COM-37 v5-fix: parámetro fallback_ultima_fecha para motores de planificación.
COM-49: cada entrada del mapa expone también `unidad_compra_abrev` y
`precio_por_unidad` (el precio EN LA UNIDAD DE COMPRA tal como se registró),
para que el optimizador pueda auditar el costeo de cada línea sin ambigüedad.
COM-75: JERARQUÍA DE PRECIOS REDEFINIDA y centralizada (aplica a todo el sistema
porque greedy/optimizador/planificacion/kmeans consumen este mapa):
    1) SCRAPER_DIA      -> precio real de la fecha EXACTA pedida (prioridad máxima).
    2) MANUAL_PERIODO   -> precio manual vigente (la decisión del usuario pesa más
                           que la IA); solo insumos sin scraper del día.
    3) PREDICHO (RF)    -> predicción Random Forest para la fecha; solo insumos sin
                           scraper del día ni manual (caso típico: planificar futuro).
    4) SCRAPER_ULTIMO   -> última corrida del scraper, SOLO con fallback_ultima_fecha
                           =True y únicamente si RF falló (no deja sin precio a
                           insumos con histórico corto).
    5) LEGACY ingrediente-> se mantiene al final en mejor_opcion_ingrediente.
COM-75 v2 (este archivo): REGLA DEL DÍA DE COMPRA:
    * precios_por_gramo_por_insumo() acepta `insumo_ids` (set opcional) para limitar
      el paso 3 (RF, el costoso) y el paso 4 a los insumos relevantes del caller:
      evita entrenar RF para insumos que ninguna receta usa (causa del 504).
    * ingredientes_requieren_precio_manual() acepta `precios_mapa` para REUTILIZAR un
      mapa ya calculado en la misma petición (la predicción corre UNA sola vez por
      planificación) y `insumo_ids` para acotar el diagnóstico. Ya no hace una segunda
      pasada de RF: con fallback_ultima_fecha=True, un insumo ausente del mapa ya
      implica que RF falló y no hay scraper ni manual.
    * _query_insumos_unidad() expone también ingrediente_nombre para el diagnóstico.
Modelo de unidades:
- USO (ingrediente/receta): pizca, cucharadita, taza, und...
- COMPRA (insumo): Kg, L, atado, und...
Uso: Importado por optimizador.py, ml/kmeans_recetas.py, ml/greedy_search.py,
routers/planificacion.py y routers/ingredientes_admin.py.
Referencia: tickets COM-37 / COM-49 / COM-75 / COM-75 v2 (solo trazabilidad).
"""
from precios_manuales import obtener_precio_manual_por_gramo  # fallback legacy v1


# ==========================================
# CONVERSIONES ESTÁNDAR DE UNIDADES -> GRAMOS
# ==========================================
def gramos_por_unidad_estandar(abrev, tipo_magnitud, factor_a_base, peso_estimado_g):
    """
    Reglas estándar compartidas (réplica del optimizador Sprint 2):
    kg/l -> 1000 g | g/ml -> 1 g | tz -> factor (250) | cda -> factor (15) |
    cdta -> factor (5) | pz -> factor (1) | und/dte/rma -> peso_estimado_g del
    ingrediente | atd -> 100 g | rdj -> 20 g.
    Fallback: masa/volumen -> factor_a_base; discreto/otro -> peso_estimado_g.
    """
    s = (abrev or '').lower().strip()
    if s in ('kg', 'kilogramo'):
        return 1000.0
    if s in ('g', 'gramo'):
        return 1.0
    if s in ('l', 'litro'):
        return 1000.0
    if s in ('ml', 'mililitro'):
        return 1.0
    if s in ('tz', 'taza'):
        return float(factor_a_base or 250.0)
    if s in ('cda', 'cucharada'):
        return float(factor_a_base or 15.0)
    if s in ('cdta', 'cucharadita'):
        return float(factor_a_base or 5.0)
    if s in ('pz', 'pizca'):
        return float(factor_a_base or 1.0)
    if s in ('und', 'unidad', 'u'):
        return float(peso_estimado_g or 100.0)
    if s in ('dte', 'diente'):
        return float(peso_estimado_g or 10.0)
    if s in ('rma', 'rama'):
        return float(peso_estimado_g or 20.0)
    if s in ('atd', 'atado'):
        return 100.0
    if s in ('rdj', 'rodaja'):
        return 20.0
    if tipo_magnitud in ('masa', 'volumen'):
        return float(factor_a_base or 1.0)
    return float(peso_estimado_g or 100.0)


# ==========================================
# EQUIVALENCIAS DE UNIDAD DE USO (COM-37 v5)
# ==========================================
def obtener_equivalencia(cur, ingrediente_id, insumo_id, unidad_uso_id):
    """Fila activa de ingredientes_equivalencias para el trío, o None."""
    cur.execute("""
        SELECT id, gramos_por_unidad_uso, observacion
        FROM ingredientes_equivalencias
        WHERE ingrediente_id = %s AND insumo_id = %s AND unidad_uso_id = %s
          AND estado_activo = TRUE
        ORDER BY id DESC
        LIMIT 1;
    """, (ingrediente_id, insumo_id, unidad_uso_id))
    return cur.fetchone()


def gramos_por_unidad_uso(cur, ingrediente_id, insumo_id, unidad_uso_id,
                          unidad_abrev, tipo_magnitud, factor_a_base, peso_estimado_g):
    """
    COM-37 v5: gramos reales de 1 unidad de USO del ingrediente consumida desde el
    insumo indicado. Prioridad: equivalencia registrada por el Admin; si no existe,
    conversión estándar de la unidad de uso.
    COM-49: se devuelve SOLO el factor por unidad; el caller multiplica por la
    cantidad de la línea (auditable en el detalle del optimizador).
    """
    eq = obtener_equivalencia(cur, ingrediente_id, insumo_id, unidad_uso_id)
    if eq:
        return float(eq['gramos_por_unidad_uso'])
    return gramos_por_unidad_estandar(unidad_abrev, tipo_magnitud, factor_a_base, peso_estimado_g)


def gramos_por_unidad_compra(insumo_abrev, tipo_magnitud, factor_a_base, peso_estimado_g):
    """Gramos de 1 unidad de COMPRA del insumo (regla estándar sobre su unidad)."""
    return gramos_por_unidad_estandar(insumo_abrev, tipo_magnitud, factor_a_base, peso_estimado_g)


# ==========================================
# PRECIOS POR GRAMO POR INSUMO EN UNA FECHA
# ==========================================
def _fecha_scraper_efectiva(cur, fecha):
    """
    COM-37 v5-fix: si la fecha pedida no tiene corrida del scraper, devuelve la última
    fecha con precios disponibles (MAX(fecha)); si no hay historial alguno, devuelve
    la fecha pedida (el mapa quedará vacío y regirán manuales/predicción).
    COM-75: se usa SOLO para el paso 4 (SCRAPER_ULTIMO) del orden jerárquico.
    """
    cur.execute("""
        SELECT COUNT(*) AS n FROM historial_precios
        WHERE fecha = %s AND precio_prom IS NOT NULL AND precio_prom > 0;
    """, (fecha,))
    fila = cur.fetchone()
    if fila and fila['n']:
        return fecha
    cur.execute("""
        SELECT MAX(fecha) AS f FROM historial_precios
        WHERE precio_prom IS NOT NULL AND precio_prom > 0;
    """)
    row = cur.fetchone()
    return row['f'] if row and row['f'] else fecha


def _query_insumos_unidad(cur):
    """
    COM-75 / COM-75 v2: helper: insumos con su unidad de compra, peso estimado y
    nombre del ingrediente (este último agregado en v2 para el diagnóstico de
    ingredientes que requieren precio manual).
    """
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
               ins.ingrediente_id, ing.nombre AS ingrediente_nombre,
               um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo,
               um.factor_a_base AS u_factor, ing.peso_estimado_g
        FROM insumos ins
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id;
    """)
    return cur.fetchall()


def precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=False, insumo_ids=None):
    """
    COM-75 + COM-75 v2: {insumo_id: {'ppg','fuente','detalle','insumo_nombre','origen',
    'unidad_compra_abrev','precio_por_unidad'}} con la JERARQUÍA central:
      1) SCRAPER_DIA     -> precio real de la fecha EXACTA (MIN precio_prom del día).
      2) MANUAL_PERIODO  -> período manual vigente para la fecha (insumos sin scraper día).
      3) PREDICHO        -> Random Forest para la fecha (insumos sin scraper día ni manual).
      4) SCRAPER_ULTIMO  -> última corrida, SOLO si fallback_ultima_fecha=True y RF falló.
    COM-75 v2: `insumo_ids` (set/list opcional) limita los pasos 3 y 4 (los costosos)
    a los insumos relevantes del caller; los pasos 1 y 2 son SQL barato y se mantienen
    globales. Si insumo_ids es None, comportamiento COM-75 completo.
    COM-49: se exponen unidad_compra_abrev y precio_por_unidad para auditoría del
    costeo (precio_por_unidad / gramos_de_compra = ppg).
    Trazabilidad COM-37 (orden anterior): scraper(día o última corrida) > manual;
    RF NO estaba en el mapa (solo greedy lo usaba como último recurso), lo que
    congelaba precios viejos en planificaciones futuras. COM-75 lo corrige.
    """
    conjunto = set(insumo_ids) if insumo_ids is not None else None
    out = {}

    # ---- Paso 1: SCRAPER DEL DÍA EXACTO (prioridad máxima, dato real) ----
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
               MIN(hp.precio_prom) AS precio_prom,
               um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo,
               um.factor_a_base AS u_factor, ing.peso_estimado_g
        FROM historial_precios hp
        JOIN insumos ins ON ins.id = hp.insumo_id
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE hp.fecha = %s AND hp.precio_prom IS NOT NULL AND hp.precio_prom > 0
        GROUP BY ins.id, ins.nombre, ins.origen,
                 um.abreviatura, um.tipo_magnitud, um.factor_a_base, ing.peso_estimado_g;
    """, (fecha,))
    for r in cur.fetchall():
        g_compra = gramos_por_unidad_compra(
            r['u_abrev'], r['u_tipo'], r['u_factor'], r['peso_estimado_g'])
        if g_compra <= 0:
            continue
        out[r['insumo_id']] = {
            'ppg': float(r['precio_prom']) / g_compra,
            'fuente': 'SCRAPER_DIA',
            'detalle': f"S/ {r['precio_prom']} por {r['u_abrev']} (scraper {fecha})",
            'insumo_nombre': r['insumo_nombre'],
            'origen': r['origen'],
            'unidad_compra_abrev': r['u_abrev'],
            'precio_por_unidad': float(r['precio_prom']),
        }

    # ---- Paso 2: MANUAL VIGENTE (decisión del usuario > IA) ----
    cur.execute("""
        SELECT ipm.insumo_id, ipm.precio_por_unidad, ipm.id AS periodo_id, ipm.observacion,
               ins.nombre AS insumo_nombre, ins.origen,
               um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo,
               um.factor_a_base AS u_factor, ing.peso_estimado_g
        FROM insumos_precios_manuales ipm
        JOIN insumos ins ON ins.id = ipm.insumo_id
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE ipm.estado_activo = TRUE
          AND (ipm.fecha_inicio IS NULL OR ipm.fecha_inicio <= %s)
          AND (ipm.fecha_fin IS NULL OR ipm.fecha_fin >= %s)
        ORDER BY ipm.fecha_registro DESC;
    """, (fecha, fecha))
    for r in cur.fetchall():
        if r['insumo_id'] in out:
            continue  # el scraper del día tiene precedencia
        g_compra = gramos_por_unidad_compra(
            r['u_abrev'], r['u_tipo'], r['u_factor'], r['peso_estimado_g'])
        if g_compra <= 0:
            continue
        out[r['insumo_id']] = {
            'ppg': float(r['precio_por_unidad']) / g_compra,
            'fuente': 'MANUAL_PERIODO',
            'detalle': f"S/ {r['precio_por_unidad']} por {r['u_abrev']} (precio manual)",
            'insumo_nombre': r['insumo_nombre'],
            'origen': r['origen'],
            'unidad_compra_abrev': r['u_abrev'],
            'precio_por_unidad': float(r['precio_por_unidad']),
        }

    # ---- Paso 3: PREDICCIÓN RF (solo insumos sin scraper del día ni manual) ----
    # COM-75 v2: acotado a `insumo_ids` si el caller lo provee (rendimiento).
    try:  # import diferido: optimizador importa este módulo (evita ciclo)
        from optimizador import predecir_precio_con_confianza
    except Exception:  # degradación controlada si optimizador no está disponible
        predecir_precio_con_confianza = None
    if predecir_precio_con_confianza is not None:
        for ins in _query_insumos_unidad(cur):
            if ins['insumo_id'] in out:
                continue
            if conjunto is not None and ins['insumo_id'] not in conjunto:
                continue
            try:
                pred, conf, ok = predecir_precio_con_confianza(ins['insumo_id'], fecha, None, cur)
            except Exception:
                pred, conf, ok = None, None, False
            if not (ok and pred):
                continue
            g_compra = gramos_por_unidad_compra(
                ins['u_abrev'], ins['u_tipo'], ins['u_factor'], ins['peso_estimado_g'])
            if g_compra <= 0:
                continue
            out[ins['insumo_id']] = {
                'ppg': float(pred) / g_compra,
                'fuente': 'PREDICHO',
                'detalle': f"S/ {pred} por {ins['u_abrev']} (PREDICHO {conf}%)",
                'insumo_nombre': ins['insumo_nombre'],
                'origen': ins['origen'],
                'unidad_compra_abrev': ins['u_abrev'],
                'precio_por_unidad': float(pred),
            }

    # ---- Paso 4: SCRAPER ÚLTIMA CORRIDA (solo fallback y solo si RF falló) ----
    if fallback_ultima_fecha:
        fecha_ult = _fecha_scraper_efectiva(cur, fecha)
        if fecha_ult != fecha:
            cur.execute("""
                SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
                       MIN(hp.precio_prom) AS precio_prom,
                       um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo,
                       um.factor_a_base AS u_factor, ing.peso_estimado_g
                FROM historial_precios hp
                JOIN insumos ins ON ins.id = hp.insumo_id
                JOIN unidades_medida um ON um.id = ins.unidad_medida_id
                JOIN ingredientes ing ON ing.id = ins.ingrediente_id
                WHERE hp.fecha = %s AND hp.precio_prom IS NOT NULL AND hp.precio_prom > 0
                GROUP BY ins.id, ins.nombre, ins.origen,
                         um.abreviatura, um.tipo_magnitud, um.factor_a_base, ing.peso_estimado_g;
            """, (fecha_ult,))
            for r in cur.fetchall():
                if r['insumo_id'] in out:
                    continue
                if conjunto is not None and r['insumo_id'] not in conjunto:
                    continue
                g_compra = gramos_por_unidad_compra(
                    r['u_abrev'], r['u_tipo'], r['u_factor'], r['peso_estimado_g'])
                if g_compra <= 0:
                    continue
                out[r['insumo_id']] = {
                    'ppg': float(r['precio_prom']) / g_compra,
                    'fuente': 'SCRAPER_ULTIMO',
                    'detalle': f"S/ {r['precio_prom']} por {r['u_abrev']} (scraper {fecha_ult})",
                    'insumo_nombre': r['insumo_nombre'],
                    'origen': r['origen'],
                    'unidad_compra_abrev': r['u_abrev'],
                    'precio_por_unidad': float(r['precio_prom']),
                }
    return out


# ==========================================
# COM-75: DIAGNÓSTICO DE FUENTE DE PRECIO (para prompt de precio manual)
# ==========================================
def diagnosticar_fuente_precio(cur, insumo_id, fecha):
    """
    COM-75 + COM-75 v2: devuelve {'fuente', 'disponible', 'detalle'} con la fuente que
    se usaría para el insumo en la fecha, siguiendo la jerarquía central. COM-75 v2:
    acota el mapa al insumo consultado (insumo_ids={insumo_id}) para no entrenar RF
    del catálogo completo en una consulta puntual. Si ninguna fuente real o predecible
    existe, disponible=False y fuente='NINGUNA' (insumo nuevo sin histórico): el caller
    debe promptear al usuario para asignar precio manual temporal.
    """
    mapa = precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=True,
                                        insumo_ids={insumo_id})
    opc = mapa.get(insumo_id)
    if opc:
        return {'fuente': opc['fuente'], 'disponible': True, 'detalle': opc['detalle']}
    return {'fuente': 'NINGUNA', 'disponible': False,
            'detalle': 'Sin scraper del día, sin precio manual y sin predicción RF disponible.'}


def ingredientes_requieren_precio_manual(cur, fecha, insumo_ids=None, precios_mapa=None) -> list:
    """
    COM-75 + COM-75 v2: lista de {ingrediente_id, ingrediente, insumos, motivo} para los
    ingredientes cuyos insumos NO tienen NINGUNA fuente de precio (ni scraper del día,
    ni manual, ni RF, ni scraper último). La UI usa esta lista para PROMPTEAR al
    usuario a asignar un precio manual temporal hasta juntar datos para predecir.
    COM-75 v2:
    * `precios_mapa`: si el caller ya calculó el mapa en esta misma petición (regla del
      día de compra: la predicción corre UNA sola vez por planificación), se reutiliza
      y NO se hace una segunda pasada de RF.
    * `insumo_ids`: acota el diagnóstico a los insumos relevantes del caller.
    * Se elimina la doble confirmación RF de COM-75: un mapa construido con
      fallback_ultima_fecha=True ya intentó RF en el paso 3; un insumo ausente del mapa
      implica necesariamente que RF falló y no hay scraper ni manual.
    Un ingrediente se reporta solo si TODOS sus insumos considerados carecen de fuente
    (si un insumo hermano tiene precio, el ingrediente se costea con él).
    """
    mapa = precios_mapa if precios_mapa is not None else precios_por_gramo_por_insumo(
        cur, fecha, fallback_ultima_fecha=True, insumo_ids=insumo_ids)
    conjunto = set(insumo_ids) if insumo_ids is not None else None

    con_fuente = set()
    sin_fuente_por_ing = {}
    for f in _query_insumos_unidad(cur):
        if conjunto is not None and f['insumo_id'] not in conjunto:
            continue
        if f['insumo_id'] in mapa:
            con_fuente.add(f['ingrediente_id'])
            continue
        reg = sin_fuente_por_ing.setdefault(f['ingrediente_id'], {
            'ingrediente': f['ingrediente_nombre'], 'insumos': []})
        reg['insumos'].append(f['insumo_nombre'])

    out = []
    for ing_id, reg in sin_fuente_por_ing.items():
        if ing_id in con_fuente:
            continue  # algún insumo hermano sí tiene fuente: no requiere manual
        out.append({
            'ingrediente_id': ing_id,
            'ingrediente': reg['ingrediente'],
            'insumos': sorted(set(reg['insumos'])),
            'motivo': 'sin_historico_para_predecir',
        })
    return sorted(out, key=lambda x: x['ingrediente'])


# ==========================================
# MEJOR OPCIÓN POR INGREDIENTE (para motores y optimizador)
# ==========================================
def mejor_opcion_ingrediente(cur, ingrediente_id, fecha, precios_insumo=None):
    """
    COM-37 v5 + COM-75: mejor (menor costo por gramo) opción de precio para un
    ingrediente en una fecha, recorriendo sus insumos sobre el mapa jerarquizado
    (scraper día > manual > RF > scraper último). Si ningún insumo tiene precio, cae
    al manual legacy por ingrediente (COM-37 v1). Retorna dict con:
    {insumo_id, insumo_nombre, origen, ppg, fuente, detalle,
    unidad_compra_abrev, precio_por_unidad} o None.
    """
    if precios_insumo is None:
        precios_insumo = precios_por_gramo_por_insumo(cur, fecha)
    cur.execute("""
        SELECT id, nombre, origen FROM insumos WHERE ingrediente_id = %s;
    """, (ingrediente_id,))
    mejor = None
    for ins in cur.fetchall():
        opc = precios_insumo.get(ins['id'])
        if not opc:
            continue
        if mejor is None or opc['ppg'] < mejor['ppg']:
            mejor = {
                'insumo_id': ins['id'],
                'insumo_nombre': ins['nombre'],
                'origen': ins['origen'],
                'ppg': opc['ppg'],
                'fuente': opc['fuente'],
                'detalle': opc['detalle'],
                'unidad_compra_abrev': opc.get('unidad_compra_abrev'),
                'precio_por_unidad': opc.get('precio_por_unidad'),
            }
    if mejor:
        return mejor
    # 5) Fallback legacy: precio manual por ingrediente (COM-37 v1)
    legacy = obtener_precio_manual_por_gramo(cur, ingrediente_id, fecha)
    if legacy:
        return {
            'insumo_id': None,
            'insumo_nombre': 'Obtenido de la Base de Datos',
            'origen': 'LEGACY',
            'ppg': legacy['precio_por_gramo'],
            'fuente': 'LEGACY_INGREDIENTE',
            'detalle': legacy['detalle'],
            'unidad_compra_abrev': None,
            'precio_por_unidad': None,
        }
    return None


def precios_por_gramo_por_ingrediente(cur, fecha, fallback_ultima_fecha=False):
    """
    COM-37 v5 + COM-75: {ingrediente_id: ppg} con la mejor opción de cada ingrediente
    bajo la jerarquía central (scraper día > manual > RF > scraper último > legacy).
    """
    precios_insumo = precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha)
    cur.execute("""
        SELECT DISTINCT ingrediente_id FROM insumos WHERE ingrediente_id IS NOT NULL;
    """)
    out = {}
    for fila in cur.fetchall():
        opc = mejor_opcion_ingrediente(cur, fila['ingrediente_id'], fecha, precios_insumo)
        if opc:
            out[fila['ingrediente_id']] = opc['ppg']
    return out