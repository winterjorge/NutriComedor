"""
precios_manuales.py
Objetivo: COM-37: resolución de precios promedio manuales ("en duro") con vigencia,
          para ingredientes sin insumos emparejados o sin predicción posible (Random
          Forest). Es la única fuente del fallback: el optimizador (Evaluar), K-means
          (agrupar) y Greedy (propuestas) consultan este módulo, garantizando precios
          completos en toda la planificación.
Reglas de vigencia (decisión COM-37):
          - Si el período tiene fecha_inicio NULL => rige siempre (sin rango activado).
          - Si tiene rango => rige solo entre fecha_inicio y COALESCE(fecha_fin, abierto).
          - Solo períodos con estado_activo = TRUE.
Unidad: el precio se guarda POR UNIDAD ESTÁNDAR del ingrediente
          (ingredientes.unidad_medida_id). La conversión a gramos replica la regla del
          motor: factor_a_base para masa/volumen, peso_estimado_g para discretas.
Precedencia (decisión COM-37): precio real/predicho del scraper SIEMPRE gana; el manual
          solo se usa cuando la predicción falla o no hay insumos con precio.
Uso: Importado por optimizador.py, ml/kmeans_recetas.py y ml/greedy_search.py.
Referencia: ticket COM-37 (solo trazabilidad).
"""


def _fila_precio_manual(cur, ingrediente_id, fecha):
    """
    COM-37: período manual vigente más reciente para (ingrediente, fecha).
    `fecha` puede ser datetime.date o string ISO; se pasa como parámetro DATE.
    """
    cur.execute("""
        SELECT pm.id, pm.precio_por_unidad, pm.fecha_inicio, pm.fecha_fin, pm.observacion,
               um.nombre AS unidad_nombre, um.abreviatura AS unidad_abrev,
               um.tipo_magnitud, um.factor_a_base, i.peso_estimado_g
        FROM ingredientes_precios_manuales pm
        JOIN ingredientes i ON i.id = pm.ingrediente_id
        JOIN unidades_medida um ON um.id = i.unidad_medida_id
        WHERE pm.ingrediente_id = %s
          AND pm.estado_activo = TRUE
          AND (pm.fecha_inicio IS NULL OR pm.fecha_inicio <= %s)
          AND (pm.fecha_inicio IS NULL OR pm.fecha_fin IS NULL OR pm.fecha_fin >= %s)
        ORDER BY pm.fecha_registro DESC
        LIMIT 1;
    """, (ingrediente_id, fecha, fecha))
    return cur.fetchone()


def obtener_precio_manual_por_gramo(cur, ingrediente_id, fecha):
    """
    COM-37: retorna {'precio_por_gramo', 'precio_por_kg', 'detalle', 'periodo_id'}
    o None si no hay período manual vigente para la fecha evaluada.
    """
    fila = _fila_precio_manual(cur, ingrediente_id, fecha)
    if not fila:
        return None
    if fila['tipo_magnitud'] in ('masa', 'volumen'):
        gramos_por_unidad = float(fila['factor_a_base'] or 1)
    else:
        gramos_por_unidad = float(fila['peso_estimado_g'] or 1)
    if gramos_por_unidad <= 0:
        return None
    ppg = float(fila['precio_por_unidad']) / gramos_por_unidad
    vigencia = ''
    if fila['fecha_inicio']:
        vigencia = f" (vigencia {fila['fecha_inicio']} → {fila['fecha_fin'] or 'abierto'})"
    else:
        vigencia = " (sin rango de vigencia)"
    return {
        'precio_por_gramo': ppg,
        'precio_por_kg': ppg * 1000.0,
        'detalle': f"S/ {fila['precio_por_unidad']} por {fila['unidad_nombre']}{vigencia}",
        'periodo_id': fila['id'],
    }


def obtener_precios_manuales_por_kg(cur, fecha):
    """
    COM-37: {ingrediente_id: precio_por_kg} de TODOS los períodos manuales vigentes en
    `fecha`. Lo usan K-means y Greedy para completar ingredientes sin precio de scraper.
    En caso de solape (no permitido por validación, pero por seguridad) gana el más
    reciente por fecha_registro.
    """
    cur.execute("""
        SELECT pm.ingrediente_id, pm.precio_por_unidad, pm.fecha_registro,
               um.tipo_magnitud, um.factor_a_base, i.peso_estimado_g
        FROM ingredientes_precios_manuales pm
        JOIN ingredientes i ON i.id = pm.ingrediente_id
        JOIN unidades_medida um ON um.id = i.unidad_medida_id
        WHERE pm.estado_activo = TRUE
          AND (pm.fecha_inicio IS NULL OR pm.fecha_inicio <= %s)
          AND (pm.fecha_inicio IS NULL OR pm.fecha_fin IS NULL OR pm.fecha_fin >= %s)
        ORDER BY pm.fecha_registro DESC;
    """, (fecha, fecha))
    out = {}
    for f in cur.fetchall():
        if f['ingrediente_id'] in out:
            continue  # ya se tomó el período más reciente de este ingrediente
        gramos = float(f['factor_a_base'] or 1) if f['tipo_magnitud'] in ('masa', 'volumen') \
            else float(f['peso_estimado_g'] or 1)
        if gramos <= 0:
            continue
        out[f['ingrediente_id']] = float(f['precio_por_unidad']) / gramos * 1000.0
    return out