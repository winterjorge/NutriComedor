"""
precios_insumos.py
Objetivo: COM-37 v5: resolución unificada de (a) equivalencias unidad de USO -> gramos
          y (b) precios por gramo de cada insumo/ingrediente en una fecha, combinando
          las fuentes con precedencia:
            1) precio scraper del día (historial_precios),
            2) predicción Random Forest (la aplica el optimizador; este módulo expone
               los gramos de compra para convertirla),
            3) período manual vigente del insumo (insumos_precios_manuales),
            4) precio manual legacy por ingrediente (ingredientes_precios_manuales v1).
          Entre insumos de un mismo ingrediente gana el MENOR costo por gramo.
Historial:
 - COM-37 v5: versión original (scraper del día + manual por insumo + legacy).
 - COM-37 v5-fix (este archivo): nuevo parámetro `fallback_ultima_fecha` en
   precios_por_gramo_por_insumo. Cuando se activa (motores K-means y Greedy, que
   planifican con el último precio disponible), si la fecha pedida no tiene corrida
   del scraper se usa el MAX(fecha) de historial_precios y la fuente se marca
   'SCRAPER_ULTIMO'. El optimizador (Evaluar) NO lo activa: conserva la precedencia
   día -> predicción RF -> manual (filas "PREDICHO" intactas).
   Sin este fallback, un día sin corrida del scraper dejaba solo precios manuales
   y el entrenamiento K-means caía con 4 recetas aptas (error de silhouette).
Modelo de unidades:
          - USO (ingrediente/receta): pizca, cucharadita, taza, und...
          - COMPRA (insumo): Kg, L, atado, und...
Uso: Importado por optimizador.py, ml/kmeans_recetas.py, ml/greedy_search.py y
     routers/ingredientes_admin.py.
Referencia: ticket COM-37 v5 (solo trazabilidad).
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


def precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=False):
    """
    COM-37 v5/v5-fix: {insumo_id: {'ppg','fuente','detalle','insumo_nombre','origen'}}
    con la mejor fuente disponible por insumo para la fecha:
      'SCRAPER_DIA'     -> mínimo precio_prom del día en historial_precios,
      'SCRAPER_ULTIMO'  -> (solo con fallback_ultima_fecha=True) mínimo precio_prom de
                           la última corrida disponible cuando la fecha pedida no tiene,
      'MANUAL_PERIODO'  -> período vigente más reciente de insumos_precios_manuales
                           (solo si el insumo no tuvo precio scraper efectivo).
    La conversión a gramos usa la unidad de COMPRA del insumo.
    """
    out = {}
    fecha_scraper = _fecha_scraper_efectiva(cur, fecha) if fallback_ultima_fecha else fecha

    # 1) Precios scraper (del día pedido o de la última corrida, según fallback)
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
    """, (fecha_scraper,))
    for r in cur.fetchall():
        g_compra = gramos_por_unidad_compra(
            r['u_abrev'], r['u_tipo'], r['u_factor'], r['peso_estimado_g'])
        if g_compra <= 0:
            continue
        fuente = 'SCRAPER_DIA' if fecha_scraper == fecha else 'SCRAPER_ULTIMO'
        out[r['insumo_id']] = {
            'ppg': float(r['precio_prom']) / g_compra,
            'fuente': fuente,
            'detalle': f"S/ {r['precio_prom']} por {r['u_abrev']} (scraper {fecha_scraper})",
            'insumo_nombre': r['insumo_nombre'],
            'origen': r['origen'],
        }

    # 2) Períodos manuales vigentes (solo insumos sin precio scraper efectivo)
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
          AND (ipm.fecha_inicio IS NULL OR ipm.fecha_fin IS NULL OR ipm.fecha_fin >= %s)
        ORDER BY ipm.fecha_registro DESC;
    """, (fecha, fecha))
    for r in cur.fetchall():
        if r['insumo_id'] in out:
            continue  # el scraper (del día o última corrida) tiene precedencia
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
        }
    return out


# ==========================================
# MEJOR OPCIÓN POR INGREDIENTE (para motores y optimizador)
# ==========================================
def mejor_opcion_ingrediente(cur, ingrediente_id, fecha, precios_insumo=None):
    """
    COM-37 v5: mejor (menor costo por gramo) opción de precio para un ingrediente en
    una fecha, recorriendo sus insumos. Si ningún insumo tiene precio, cae al manual
    legacy por ingrediente (COM-37 v1). Retorna dict con:
      {insumo_id, insumo_nombre, origen, ppg, fuente, detalle} o None.
    `precios_insumo` puede pasarse precalculado para evitar reconsultas en bucles.
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
            }
    if mejor:
        return mejor
    # 4) Fallback legacy: precio manual por ingrediente (COM-37 v1)
    legacy = obtener_precio_manual_por_gramo(cur, ingrediente_id, fecha)
    if legacy:
        return {
            'insumo_id': None,
            'insumo_nombre': 'Obtenido de la Base de Datos',
            'origen': 'LEGACY',
            'ppg': legacy['precio_por_gramo'],
            'fuente': 'LEGACY_INGREDIENTE',
            'detalle': legacy['detalle'],
        }
    return None


def precios_por_gramo_por_ingrediente(cur, fecha, fallback_ultima_fecha=False):
    """
    COM-37 v5: {ingrediente_id: ppg} con la mejor opción de cada ingrediente
    (scraper día/último > manual insumo > legacy ingrediente).
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