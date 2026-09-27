"""
precios_insumos.py
Objetivo: COM-37 v5: resolución unificada de (a) equivalencias unidad de USO -> gramos
          y (b) precios por gramo de cada insumo/ingrediente en una fecha, combinando
          las cuatro fuentes con precedencia:
            1) precio scraper del día (historial_precios de insumos SCRAPER),
            2) predicción Random Forest (la aplica el optimizador; este módulo expone
               los gramos de compra para convertirla),
            3) período manual vigente del insumo (insumos_precios_manuales, incluye
               insumos MANUAL creados por el Admin),
            4) precio manual legacy por ingrediente (ingredientes_precios_manuales v1).
          Entre insumos de un mismo ingrediente gana el MENOR costo por gramo
          (criterio de compra económica del comedor).
Modelo de unidades:
          - USO (ingrediente/receta): pizca, cucharadita, taza, rodaja, und...
            gramos = equivalencia (ingrediente,insumo,unidad_uso) si existe; si no,
            conversión estándar (factor_a_base masa/volumen; peso_estimado_g discretas;
            atado=100 g; rodaja=20 g).
          - COMPRA (insumo): Kg, L, atado, und... gramos por unidad de compra con la
            misma regla estándar sobre la unidad del insumo.
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
def precios_por_gramo_por_insumo(cur, fecha):
    """
    COM-37 v5: {insumo_id: {'ppg', 'fuente', 'detalle', 'insumo_nombre', 'origen'}}
    con la mejor fuente disponible por insumo para la fecha:
      'SCRAPER_DIA'      -> mínimo precio_prom del día en historial_precios,
      'MANUAL_PERIODO'   -> período vigente más reciente de insumos_precios_manuales
                            (solo si el insumo no tuvo precio scraper ese día).
    La conversión a gramos usa la unidad de COMPRA del insumo.
    """
    out = {}

    # 1) Precios scraper del día (mínimo por insumo entre mercados)
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
        }

    # 2) Períodos manuales vigentes (solo insumos sin precio scraper del día)
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
    `precios_insumo` puede pasarse precalculado (mapa de precios_por_gramo_por_insumo)
    para evitar reconsultas en bucles de costeo.
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


def precios_por_gramo_por_ingrediente(cur, fecha):
    """
    COM-37 v5: {ingrediente_id: ppg} con la mejor opción de cada ingrediente
    (scraper día > manual insumo > legacy ingrediente). Lo usan K-means y Greedy para
    costear con precios completos sin recorrer insumo por insumo en cada línea.
    """
    precios_insumo = precios_por_gramo_por_insumo(cur, fecha)
    cur.execute("""
        SELECT DISTINCT ingrediente_id FROM insumos WHERE ingrediente_id IS NOT NULL;
    """)
    out = {}
    for fila in cur.fetchall():
        opc = mejor_opcion_ingrediente(cur, fila['ingrediente_id'], fecha, precios_insumo)
        if opc:
            out[fila['ingrediente_id']] = opc['ppg']
    return out