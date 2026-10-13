"""
subsidio_motor.py
Objetivo: COM-59A: helpers de negocio del modelo autogestionado:
          * subsidio_gramos_del_mes(): víveres subvencionados del comedor en un mes
            calendario, convertidos a gramos (unidad de compra del subsidio -> gramos).
          * costo_con_subsidio(): descuenta del costo de una receta los gramos cubiertos
            por el subsidio del mes (política: el víver ya lo pagó el municipio). Con
            tope acumulado: si las líneas del detalle superan el stock subvencionado del
            mes, el excedente se paga a precio de mercado y se marca 'subsidio_agotado'.
          * precio_venta_vigente(): precio único vigente por tipo de comensal
            (estabilidad de precio; el historial queda en precios_venta).
          * margen_semanal_objetivo(): parámetro MARGEN_SEMANAL_OBJETIVO (default 0.15).
Historial:
COM-59A v1: versión original. Supuestos documentados: sin ledger de consumo (el stock
    del mes se considera completo para cualquier semana) y descuento por ingrediente.
COM-71 (este archivo):
    * costo_con_subsidio() acepta `stock_inicial: dict = None`: si se provee, usa ese
      stock (gramos por ingrediente) en lugar de leer el mes completo. Cambio ADITIVO:
      sin el argumento el comportamiento es idéntico a COM-59A (COM-69 intacto).
    * Nuevos helpers de stock remanente (criterio COM-71 D5):
        - consumo_planes_vigentes_mes(): gramos comprometidos por planificaciones
          VIGENTES del mismo mes/comedor (enlace defensivo presupuesto->comedor y
          filtro de estado si existe), opcionalmente solo semanas ANTES de una fecha.
        - stock_remanente_mes(): max(0, stock_mes - consumo_vigente), el stock que el
          greedy debe asumir disponible al costear una semana nueva.
      La matemática de gramos por línea replica la del reporte COM-69 (equivalencias
      uso->gramos con fallback estándar) para que costo y reporte coincidan.
Uso: Importado por routers/subsidio.py, ml/greedy_search.py y reportes.
Referencia: tickets COM-59 / COM-71 (solo trazabilidad).
"""
from datetime import date

from precios_insumos import gramos_por_unidad_estandar


# ==========================================
# SUBSIDIO DEL MES EN GRAMOS
# ==========================================
def subsidio_gramos_del_mes(cur, comedor_id: int, anio: int, mes: int) -> dict:
    """
    COM-59A: {ingrediente_id: gramos_subvencionados} del comedor en el mes calendario.
    Convierte cantidad_recibida (unidad de compra declarada en el subsidio) a gramos
    con la regla estándar de unidades (kg/l -> 1000, und -> peso_estimado, etc.).
    """
    cur.execute("""
        SELECT sm.ingrediente_id, sm.cantidad_recibida,
               um.abreviatura, um.tipo_magnitud, um.factor_a_base,
               COALESCE(i.peso_estimado_g, 100.0) AS peso_estimado_g
        FROM subsidio_mensual sm
        JOIN unidades_medida um ON um.id = sm.unidad_medida_id
        JOIN ingredientes i ON i.id = sm.ingrediente_id
        WHERE sm.comedor_id = %s AND sm.anio = %s AND sm.mes = %s;
    """, (comedor_id, anio, mes))
    out = {}
    for r in cur.fetchall():
        gramos = float(r['cantidad_recibida']) * gramos_por_unidad_estandar(
            r['abreviatura'], r['tipo_magnitud'],
            float(r['factor_a_base'] or 1.0), float(r['peso_estimado_g']))
        out[r['ingrediente_id']] = out.get(r['ingrediente_id'], 0.0) + gramos
    return out


# ==========================================
# COM-71: CONSUMO COMPROMETIDO Y STOCK REMANENTE
# ==========================================
def _columnas(cur, tabla: str) -> set:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s;
    """, (tabla,))
    return {r['column_name'] for r in cur.fetchall()}


def _link_comedor_de_plan(cur):
    """
    COM-71: resuelve defensivamente cómo se vincula un presupuesto_semanal (alias ps)
    con su comedor y, si existe, dónde vive el estado de la planificación.
    Retorna (expr_comedor, join_sql, expr_estado_o_None) o (None, '', None) si el
    esquema no ofrece enlace (el caller operará sin filtro de comedor/estado).
    """
    cols_ps = _columnas(cur, 'presupuesto_semanal')
    if 'comedor_id' in cols_ps:
        # Enlace directo; el estado (si existe) también estaría en presupuesto_semanal
        expr_estado = 'ps.estado' if 'estado' in cols_ps else None
        return 'ps.comedor_id', '', expr_estado
    if 'candidata_id' in cols_ps:
        cols_pc = _columnas(cur, 'planificaciones_candidatas')
        if 'comedor_id' in cols_pc:
            join_sql = ' JOIN planificaciones_candidatas pc ON pc.id = ps.candidata_id'
            expr_estado = 'pc.estado' if 'estado' in cols_pc else None
            return 'pc.comedor_id', join_sql, expr_estado
    return None, '', None


def _gramos_linea_simple(cur, eq_map, ing_id, insumo_id, unidad_uso_id,
                         unidad_abrev, tipo_magnitud, factor_a_base,
                         peso_estimado_g, cantidad):
    """COM-71: gramos de una línea con equivalencia activa o conversión estándar."""
    g = eq_map.get((ing_id, insumo_id, unidad_uso_id))
    if g is None:
        g = gramos_por_unidad_estandar(unidad_abrev, tipo_magnitud,
                                       float(factor_a_base or 1.0), float(peso_estimado_g or 100.0))
    return g * float(cantidad)


def consumo_planes_vigentes_mes(cur, comedor_id: int, anio: int, mes: int,
                                antes_de=None) -> dict:
    """
    COM-71 (criterio D5): gramos por ingrediente ya comprometidos por planificaciones
    VIGENTES del mismo mes/comedor. Si `antes_de` (date) se provee, solo cuenta semanas
    con fecha_referencia < antes_de (para costear una semana nueva sin contarse a sí
    misma). Replica la matemática de gramos del reporte COM-69 para coincidir.
    Sin enlace comedor->plan en el esquema, retorna {} (el caller usará stock completo).
    """
    expr_comedor, join_sql, expr_estado = _link_comedor_de_plan(cur)
    if expr_comedor is None:
        return {}
    where = ["EXTRACT(YEAR FROM ps.fecha_referencia) = %s",
             "EXTRACT(MONTH FROM ps.fecha_referencia) = %s",
             f"{expr_comedor} = %s"]
    params = [anio, mes, comedor_id]
    if expr_estado:
        where.append(f"{expr_estado} = 'VIGENTE'")
    if antes_de is not None:
        where.append("ps.fecha_referencia < %s")
        params.append(antes_de)
    cur.execute(f"""
        SELECT ps.id
        FROM presupuesto_semanal ps{join_sql}
        WHERE {' AND '.join(where)}
        ORDER BY ps.id;
    """, params)
    plan_ids = [r['id'] for r in cur.fetchall()]
    if not plan_ids:
        return {}

    # Equivalencias activas uso->gramos (misma fuente que greedy y reporte)
    cur.execute("""
        SELECT ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso
        FROM ingredientes_equivalencias
        WHERE estado_activo = TRUE;
    """)
    eq_map = {(r['ingrediente_id'], r['insumo_id'], r['unidad_uso_id']):
              float(r['gramos_por_unidad_uso']) for r in cur.fetchall()}

    cur.execute("""
        SELECT pd.presupuesto_semanal_id, pd.receta_id, pd.total_comensales,
               COALESCE(NULLIF(ra.raciones, 0), 4) AS raciones,
               ri.ingrediente_id, ri.cantidad_requerida,
               ri.unidad_medida_id AS unidad_uso_id,
               um.abreviatura, um.tipo_magnitud, um.factor_a_base,
               ing.peso_estimado_g
        FROM planificacion_dia pd
        JOIN recetas_almuerzo ra ON ra.id = pd.receta_id
        JOIN receta_ingrediente ri ON ri.receta_id = pd.receta_id
        JOIN unidades_medida um ON um.id = ri.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ri.ingrediente_id
        WHERE pd.presupuesto_semanal_id = ANY(%s);
    """, (plan_ids,))
    consumo = {}
    for r in cur.fetchall():
        # El insumo elegido para la equivalencia no se persiste en planificacion_dia;
        # se usa cualquier equivalencia activa del ingrediente con esa unidad de uso
        # (regla del reporte COM-69) o la conversión estándar.
        g = None
        for (ing_id, ins_id, uu_id), gramos_eq in eq_map.items():
            if ing_id == r['ingrediente_id'] and uu_id == r['unidad_uso_id']:
                g = gramos_eq
                break
        if g is None:
            g = gramos_por_unidad_estandar(
                r['abreviatura'], r['tipo_magnitud'],
                float(r['factor_a_base'] or 1.0), float(r['peso_estimado_g'] or 100.0))
        gramos_linea = g * float(r['cantidad_requerida'])
        gramos_racion_total = gramos_linea * (float(r['total_comensales']) / float(r['raciones']))
        consumo[r['ingrediente_id']] = consumo.get(r['ingrediente_id'], 0.0) + gramos_racion_total
    return consumo


def stock_remanente_mes(cur, comedor_id: int, anio: int, mes: int,
                        antes_de=None) -> dict:
    """
    COM-71 (criterio D5): stock subvencionado REALMENTE disponible para una semana
    nueva: max(0, stock_mes - consumo de planificaciones VIGENTES anteriores del mes).
    Si no hay enlace comedor->plan en el esquema, devuelve el stock completo
    (comportamiento COM-59A, documentado como supuesto).
    """
    stock = subsidio_gramos_del_mes(cur, comedor_id, anio, mes)
    if not stock:
        return {}
    consumo = consumo_planes_vigentes_mes(cur, comedor_id, anio, mes, antes_de=antes_de)
    return {k: max(0.0, v - consumo.get(k, 0.0)) for k, v in stock.items()}


# ==========================================
# COSTEO CON DESCUENTO DE SUBSIDIO
# ==========================================
def costo_con_subsidio(cur, comedor_id: int, fecha, detalle_insumos: list,
                       stock_inicial: dict = None) -> dict:
    """
    COM-59A: recibe el detalle de líneas de costeo (formato del optimizador: dicts con
    'ingrediente_id', 'gramos_totales' o 'peso_usado_g', y 'costo_parcial') y devuelve:
      {
        'costo_total':            suma de costos ajustados por subsidio,
        'costo_sin_subsidio':     suma de costos originales (auditoría),
        'ahorro_subsidio':        diferencia,
        'detalle':                líneas con 'subvencionado' (bool), 'costo_ajustado'
                                  y 'subsidio_agotado' (bool) cuando el stock mensual
                                  no cubrió todos los gramos de la línea,
      }
    Regla: los gramos de un ingrediente subvencionado se cubren con el stock del mes en
    orden de aparición; el excedente (si el stock se agota) se paga a precio de mercado.
    COM-71 (ADITIVO): si `stock_inicial` se provee (dict {ingrediente_id: gramos}),
    se usa ese stock en lugar del mes completo; es el mecanismo con el que el greedy
    costea contra el STOCK REMANENTE (stock_remanente_mes). Sin el argumento, el
    comportamiento es idéntico a COM-59A.
    """
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    stock = dict(stock_inicial) if stock_inicial is not None \
        else subsidio_gramos_del_mes(cur, comedor_id, fecha.year, fecha.month)
    restante = dict(stock)

    detalle_out = []
    total_ajustado = 0.0
    total_original = 0.0
    for linea in detalle_insumos:
        ing_id = linea.get('ingrediente_id')
        gramos = float(linea.get('gramos_totales') or linea.get('peso_usado_g') or 0.0)
        costo_original = float(linea.get('costo_parcial') or 0.0)
        total_original += costo_original

        nueva = dict(linea)
        disponible = restante.get(ing_id, 0.0) if ing_id in stock else 0.0
        if ing_id in stock and gramos > 0 and disponible > 0:
            cubierto = min(gramos, disponible)
            restante[ing_id] = disponible - cubierto
            proporcion = cubierto / gramos if gramos else 0.0
            costo_ajustado = round(costo_original * (1.0 - proporcion), 2)
            nueva['subvencionado'] = True
            nueva['subsidio_agotado'] = cubierto < gramos
            nueva['gramos_cubiertos_subsidio'] = round(cubierto, 2)
        else:
            costo_ajustado = costo_original
            nueva['subvencionado'] = False
            nueva['subsidio_agotado'] = False
            nueva['gramos_cubiertos_subsidio'] = 0.0
        nueva['costo_ajustado'] = costo_ajustado
        total_ajustado += costo_ajustado
        detalle_out.append(nueva)

    return {
        'costo_total': round(total_ajustado, 2),
        'costo_sin_subsidio': round(total_original, 2),
        'ahorro_subsidio': round(total_original - total_ajustado, 2),
        'detalle': detalle_out,
    }


# ==========================================
# PRECIO DE VENTA VIGENTE (estabilidad de precio)
# ==========================================
def precio_venta_vigente(cur, tipo_comensal: str, fecha=None) -> float:
    """
    COM-59A: precio único vigente para el tipo de comensal: la fila con mayor
    vigente_desde que no sea futura. Si no existe, fallback a los parámetros legacy
    PRECIO_SOCIAL/PRECIO_AFILIADO/PRECIO_NORMAL (trazabilidad de la migración).
    """
    momento = fecha or date.today()
    cur.execute("""
        SELECT precio FROM precios_venta
        WHERE tipo_comensal = %s AND vigente_desde <= %s
        ORDER BY vigente_desde DESC
        LIMIT 1;
    """, (tipo_comensal, momento))
    fila = cur.fetchone()
    if fila:
        return float(fila['precio'])
    clave = {'Social': 'PRECIO_SOCIAL', 'Afiliado': 'PRECIO_AFILIADO', 'Normal': 'PRECIO_NORMAL'}.get(tipo_comensal)
    if clave:
        cur.execute("SELECT valor FROM parametros_sistema WHERE clave = %s;", (clave,))
        legacy = cur.fetchone()
        if legacy:
            return float(legacy['valor'])
    return 0.0


# ==========================================
# MARGEN SEMANAL OBJETIVO
# ==========================================
def margen_semanal_objetivo(cur) -> float:
    """COM-59A: margen objetivo semanal (default 0.15) desde parametros_sistema."""
    cur.execute("SELECT valor FROM parametros_sistema WHERE clave = 'MARGEN_SEMANAL_OBJETIVO';")
    fila = cur.fetchone()
    try:
        return float(fila['valor']) if fila else 0.15
    except (TypeError, ValueError):
        return 0.15