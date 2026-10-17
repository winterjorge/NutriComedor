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
COM-75: JERARQUÍA DE PRECIOS REDEFINIDA y centralizada (aplica a todo
el sistema porque greedy/optimizador/planificacion/kmeans consumen este mapa):
    1) SCRAPER_DIA      -> precio real de la fecha EXACTA pedida (prioridad máxima).
    2) MANUAL_PERIODO   -> precio manual vigente (la decisión del usuario pesa más
                           que la IA); solo insumos sin scraper del día.
    3) PREDICHO (RF)    -> predicción Random Forest para la fecha; solo insumos sin
                           scraper del día ni manual (caso típico: planificar futuro).
    4) SCRAPER_ULTIMO   -> última corrida del scraper, SOLO con fallback_ultima_fecha
                           =True y únicamente si RF falló (no deja sin precio a
                           insumos con histórico corto).
    5) LEGACY ingrediente-> se mantiene al final en mejor_opcion_ingrediente.
Antes (COM-37) el scraper "última corrida" ganaba sobre RF para fechas sin corrida,
lo que congelaba precios viejos en planificaciones futuras; COM-75 invierte eso:
para fechas sin scraper del día, RF proyecta la tendencia.
Nuevos helpers de diagnóstico COM-75:
* diagnosticar_fuente_precio(): fuente que se usaría para un insumo en una fecha.
* ingredientes_requieren_precio_manual(): ingredientes SIN ninguna fuente real o
  predecible (insumo nuevo sin histórico) para que la UI promptee asignar un
  precio manual temporal hasta juntar datos suficientes para predecir.
COM-80 (este archivo): mejor_opcion_ingrediente PREFIERE al insumo marcado
es_principal=True cuando éste tiene precio en la fecha (decisión explícita del
Admin pesa más que el precio mínimo); si el principal no tiene precio, se conserva
el comportamiento legacy de menor costo por gramo entre los demás insumos. Cada
opción del mapa expone también 'es_principal' para auditoría. Sin principal
marcado, el comportamiento es idéntico a COM-75 (no hay cambio de resultados).
Modelo de unidades:
  USO (ingrediente/receta): pizca, cucharadita, taza, und...
  COMPRA (insumo): Kg, L, atado, und...
Uso: Importado por optimizador.py, ml/kmeans_recetas.py, ml/greedy_search.py,
routers/planificacion.py y routers/ingredientes_admin.py.
Referencia: tickets COM-37 / COM-49 / COM-75 / COM-80 (solo trazabilidad).
"""
from precios_manuales import obtener_precio_manual_por_gramo  # fallback legacy v1

==========================================
CONVERSIONES ESTÁNDAR DE UNIDADES -> GRAMOS
==========================================
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

==========================================
EQUIVALENCIAS DE UNIDAD DE USO (COM-37 v5)
==========================================
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

==========================================
PRECIOS POR GRAMO POR INSUMO EN UNA FECHA
==========================================
def _fecha_scraper_efectiva(cur, fecha):
    """
    COM-37 v5-fix: si la fecha pedida no tiene corrida del scraper, devuelve la última
    fecha con precios disponibles (MAX(fecha)); si no hay historial alguno, devuelve
    la fecha pedida (el mapa quedará vacío y regirán manuales/predicción).
    COM-75: se usa SOLO para el paso 4 (SCRAPER_ULTIMO) del nuevo orden jerárquico.
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
    """COM-75: helper: insumos con su unidad de compra y peso estimado del ingrediente."""
    cur.execute("""
        SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
               ins.ingrediente_id,
               um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo,
               um.factor_a_base AS u_factor, ing.peso_estimado_g
        FROM insumos ins
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id;
    """)
    return cur.fetchall()


def precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=False):
    """
    COM-75: {insumo_id: {'ppg','fuente','detalle','insumo_nombre','origen',
    'unidad_compra_abrev','precio_por_unidad'}} con la JERARQUÍA central:
      1) SCRAPER_DIA     -> precio real de la fecha EXACTA (MIN precio_prom del día).
      2) MANUAL_PERIODO  -> período manual vigente para la fecha (insumos sin scraper día).
      3) PREDICHO        -> Random Forest para la fecha (insumos sin scraper día ni manual).
      4) SCRAPER_ULTIMO  -> última corrida, SOLO si fallback_ultima_fecha=True y RF falló.
    COM-49: se exponen unidad_compra_abrev y precio_por_unidad para auditoría del
    costeo (precio_por_unidad / gramos_de_compra = ppg).
    Trazabilidad COM-37 (orden anterior): scraper(día o última corrida) > manual;
    RF NO estaba en el mapa (solo greedy lo usaba como último recurso), lo que
    congelaba precios viejos en planificaciones futuras. COM-75 lo corrige.
    """
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
    try:
        from optimizador import predecir_precio_con_confianza
    except Exception:  # degradación controlada si optimizador no está disponible
        predecir_precio_con_confianza = None
    if predecir_precio_con_confianza is not None:
        faltantes = [r for r in _query_insumos_unidad(cur) if r['insumo_id'] not in out]
        for ins in faltantes:
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

==========================================
COM-75: DIAGNÓSTICO DE FUENTE DE PRECIO (para prompt de precio manual)
==========================================
def diagnosticar_fuente_precio(cur, insumo_id, fecha):
    """
    COM-75: devuelve {'fuente', 'disponible', 'detalle'} con la fuente que se usaría
    para el insumo en la fecha, siguiendo la jerarquía central. Si ninguna fuente real
    o predecible existe, disponible=False y fuente='NINGUNA' (insumo nuevo sin
    histórico): el caller debe promptear al usuario para asignar precio manual temporal.
    """
    mapa = precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=True)
    opc = mapa.get(insumo_id)
    if opc:
        return {'fuente': opc['fuente'], 'disponible': True, 'detalle': opc['detalle']}
    return {'fuente': 'NINGUNA', 'disponible': False,
            'detalle': 'Sin scraper del día, sin precio manual y sin predicción RF disponible.'}


def ingredientes_requieren_precio_manual(cur, fecha) -> list:
    """
    COM-75: lista de {ingrediente_id, ingrediente, insumo_id, insumo, motivo} para los
    insumos que NO tienen scraper del día, NI manual vigente, NI predicción RF posible
    (insumos nuevos sin histórico). La UI usa esta lista para PROMPTEAR al usuario a
    asignar un precio manual temporal hasta juntar datos suficientes para predecir.
    """
    try:
        from optimizador import predecir_precio_con_confianza
    except Exception:
        predecir_precio_con_confianza = None
    mapa = precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=False)
    # mapa sin fallback: contiene scraper_día, manual y RF. Los que faltan aquí no
    # tienen ninguna de esas tres fuentes reales/predecibles.
    faltantes = [r for r in _query_insumos_unidad(cur) if r['insumo_id'] not in mapa]
    out = []
    for ins in faltantes:
        # Doble confirmación de que RF realmente no puede predecir (por si el paso 3
        # falló por excepción transitoria y no por falta de histórico).
        rf_ok = False
        if predecir_precio_con_confianza is not None:
            try:
                _p, _c, rf_ok = predecir_precio_con_confianza(ins['insumo_id'], fecha, None, cur)
            except Exception:
                rf_ok = False
        if rf_ok:
            continue  # sí se puede predecir; no requiere manual
        out.append({
            'ingrediente_id': ins['ingrediente_id'],
            'ingrediente': None,  # se completa abajo si hace falta
            'insumo_id': ins['insumo_id'],
            'insumo': ins['insumo_nombre'],
            'motivo': 'sin_historico_para_predecir',
        })
    if out:
        ids = sorted({x['ingrediente_id'] for x in out if x['ingrediente_id']})
        if ids:
            cur.execute("SELECT id, nombre FROM ingredientes WHERE id = ANY(%s);", (ids,))
            nombres = {r['id']: r['nombre'] for r in cur.fetchall()}
            for x in out:
                x['ingrediente'] = nombres.get(x['ingrediente_id'])
    return out

==========================================
MEJOR OPCIÓN POR INGREDIENTE (para motores y optimizador)
==========================================
_COLUMNA_PRINCIPAL_CACHE = None


def _hay_columna_principal(cur) -> bool:
    """COM-80: detecta (una sola vez por proceso) si insumos.es_principal existe,
    para tolerar callers que corran antes de la migración del bootstrap."""
    global _COLUMNA_PRINCIPAL_CACHE
    if _COLUMNA_PRINCIPAL_CACHE is None:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'insumos' AND column_name = 'es_principal';
        """)
        _COLUMNA_PRINCIPAL_CACHE = cur.fetchone() is not None
    return _COLUMNA_PRINCIPAL_CACHE


def mejor_opcion_ingrediente(cur, ingrediente_id, fecha, precios_insumo=None):
    """
    COM-37 v5 + COM-75 + COM-80: mejor opción de precio para un ingrediente en una
    fecha, recorriendo sus insumos sobre el mapa jerarquizado (scraper día > manual >
    RF > scraper último). COM-80: si el ingrediente tiene un insumo marcado
    es_principal=True Y éste tiene precio en la fecha, ESA opción se retorna aunque
    no sea la más barata (decisión explícita del Admin > precio mínimo). Si el
    principal no tiene precio, se conserva el comportamiento legacy de menor costo
    por gramo entre los demás insumos. Si ningún insumo tiene precio, cae al manual
    legacy por ingrediente (COM-37 v1). Retorna dict con:
    {insumo_id, insumo_nombre, origen, ppg, fuente, detalle,
     unidad_compra_abrev, precio_por_unidad, es_principal} o None.
    """
    if precios_insumo is None:
        precios_insumo = precios_por_gramo_por_insumo(cur, fecha)
    # COM-80: se lee el flag de principalidad (defensivo si la columna aún no existe)
    if _hay_columna_principal(cur):
        cur.execute("""
            SELECT id, nombre, origen, es_principal
            FROM insumos WHERE ingrediente_id = %s;
        """, (ingrediente_id,))
    else:
        cur.execute("""
            SELECT id, nombre, origen, FALSE AS es_principal
            FROM insumos WHERE ingrediente_id = %s;
        """, (ingrediente_id,))
    mejor = None
    mejor_principal = None
    for ins in cur.fetchall():
        opc = precios_insumo.get(ins['id'])
        if not opc:
            continue
        cand = {
            'insumo_id': ins['id'],
            'insumo_nombre': ins['nombre'],
            'origen': ins['origen'],
            'ppg': opc['ppg'],
            'fuente': opc['fuente'],
            'detalle': opc['detalle'],
            'unidad_compra_abrev': opc.get('unidad_compra_abrev'),
            'precio_por_unidad': opc.get('precio_por_unidad'),
            # COM-80: auditoría de principalidad en cada opción evaluada
            'es_principal': bool(ins['es_principal']),
        }
        if cand['es_principal']:
            if mejor_principal is None or opc['ppg'] < mejor_principal['ppg']:
                mejor_principal = cand
        if mejor is None or opc['ppg'] < mejor['ppg']:
            mejor = cand
    # COM-80: el principal con precio gana; si no hay principal con precio, legacy
    if mejor_principal:
        return mejor_principal
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
            'es_principal': False,
        }
    return None


def precios_por_gramo_por_ingrediente(cur, fecha, fallback_ultima_fecha=False):
    """
    COM-37 v5 + COM-75 + COM-80: {ingrediente_id: ppg} con la mejor opción de cada
    ingrediente bajo la jerarquía central (scraper día > manual > RF > scraper último
    > legacy) y la preferencia de insumo principal de COM-80.
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