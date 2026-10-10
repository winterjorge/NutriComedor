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
Supuestos documentados (COM-59A v1):
          - No se lleva aún un ledger de consumo del subsidio: el stock del mes se
            considera disponible completo para planificar cualquier semana del mes.
            El reporte mostrará 'subvencionado vs comprado' para auditoría mensual.
          - El descuento aplica por ingrediente (no por insumo): todos los insumos de un
            ingrediente subvencionado se consideran cubiertos.
Uso: Importado por routers/subsidio.py y (Parte 3) por ml/greedy_search.py y reportes.
Referencia: tickets COM-59 (solo trazabilidad).
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
# COSTEO CON DESCUENTO DE SUBSIDIO
# ==========================================
def costo_con_subsidio(cur, comedor_id: int, fecha, detalle_insumos: list) -> dict:
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
    """
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    stock = subsidio_gramos_del_mes(cur, comedor_id, fecha.year, fecha.month)
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