"""
ml/greedy_search.py
Objetivo: Motor de búsqueda heurística (Greedy Search) del ticket COM-8. Genera 3
propuestas de menú semanal (NutriMax, EconoMax, BalanceMax) combinando valor
nutricional y precio, respetando la rotación de clusters K-means (COM-5),
la variedad de platos y el presupuesto del comedor.
Historial:
COM-8 v1/v2/v3: días seleccionables, top-3 por categorías, FIX de formatos legacy.
COM-37 v2: regla de PRECIOS COMPLETOS para el flujo del comedor.
COM-37 v4/v5: validación de reglas de proteína VIGENTES (R1/R2 de K-means); costeo
    sobre precios_insumos.py con equivalencias uso->gramos.
COM-37 v7: la predicción RF cuenta como fuente de precio válida para completitud;
    fallback_ultima_fecha para días sin corrida del scraper.
COM-47 v3: la nutrición de recetas_almuerzo YA ESTÁ POR RACIÓN; se usa SIN dividir.
    La división entre raciones aplica SOLO a cantidades de ingredientes y al costo.
COM-50 v3: costeo sin fallback legacy (fuentes modernas) y aislamiento por receta.
COM-59A: modelo de negocio autogestionado: recolección vía precio_venta_vigente;
    costo_racion = costo REAL post-subsidio (costo_con_subsidio); auditoría semanal
    del subsidio (subsidio_agotado_semana) y del MARGEN SEMANAL OBJETIVO
    (margen_semanal_pct / cumple_margen_semanal / alerta_margen en el resumen).
COM-60: PRIORIDAD ANEMIA CERO + DESEMPATE Fe/S/: cuota semanal mínima de días del
    cluster Anti-Anemia (KMEANS_CUOTA_CLUSTER_FEO, regla de deadline) y desempate por
    hierro por sol (KMEANS_FE_SO_DESEMPATE). Auditoría dias_anti_anemia /
    cumple_cuota_anemia por variante y es_anti_anemia / fe_por_sol por día.
COM-71: ECONOMÍA SEMANAL CON HOLGURA Y SUBSIDIO REAL:
    * D2 ELEGIBILIDAD: recetas con costeable=False no seleccionables; auditadas en
      recetas_no_costeables (y clave legacy recetas_excluidas_precio_incompleto).
    * D3 COSTEO POR DÍA: _mapa_costos_dia() con la fecha real de cada día.
    * D5 STOCK REMANENTE: descuento contra stock_remanente_mes() de subsidio_motor.
    * D4 HOLGURA DIARIA (FLEX): tope por día = PLANIFICACION_FLEX_DIA ×
      ((límite − acumulado) / días restantes); excedente marcado flex_excedido.
    * _costear_recetas queda como wrapper de trazabilidad (stock completo, 1 fecha).
COM-72: HOTFIX KeyError 'propuestas' (primer_mapa ANTES de validar R1/R2) y guarda
    anti-repetición intra-semana en día forzado anti-anemia (cluster singleton).
COM-61 / HU-11: VARIEDAD ENTRE SEMANAS:
    * _recetas_semana_anterior(): receta_ids del menú VIGENTE más reciente del comedor
      con fecha_referencia < lunes de la semana a generar (criterio D1).
    * generar_tres_propuestas(..., permitir_repetidos=False): con False, los platos de
      la semana pasada se EXCLUYEN del pool diario y solo entran si el pool del cluster
      objetivo se queda sin alternativas frescas (repetición INEVITABLE, auditada por
      día y en el resumen). Con True, no se excluye nada pero toda coincidencia con la
      semana pasada se audita (criterio D5: la única vía voluntaria es el checkbox UI).
    * Comparación por receta_id completo (criterio D2).
    * Auditoría aditiva POR DÍA: repite_semana_anterior / repeticion_inevitable.
      POR VARIANTE (resumen): semana_anterior_fecha, n_recetas_semana_anterior,
      repeticiones_semana_anterior, variedad_pct (% de días con plato nuevo) y
      permitir_repetidos. Todo viaja en el JSONB resumen/menu (criterio D7: sin DDL).
    * La guarda anti-repetición COM-72 del día forzado ahora prefiere frescas.
COM-74 (este archivo): COMENSALES PROYECTADOS POR DÍA:
    * _comensales_por_dia(): para cada día de cocina consulta la PREDICCIÓN IA
      (ai_engine.predecir_demanda_raciones con la fecha real del día) + cocineras
      (PLANIFICACION_COCINERAS, default 20). Si sin_datos=True -> fallback a
      parámetros estáticos y fuente_comensales='parametro' (auditable).
    * El COSTO del día usa total_con_cocineras (raciones físicamente cocinadas) y
      la RECOLECCIÓN solo los tipos pagantes (Social/Afiliado/Normal) × precios
      vigentes. Antes se usaban 120 fijos sin cocineras para todo.
    * Cada día del menú persiste comensales_social/afiliado/normal/cocinera/total y
      fuente_comensales para auditoría y para que la selección los grabe en
      planificacion_dia.
    * Resumen agrega dias_con_prediccion_ia y total_comensales_dia pasa a ser el
      promedio real de los días generados (clave conservada por compatibilidad).
    Ningún helper, clave de payload ni bloque de trazabilidad anterior se elimina.
Uso: Importado por routers/propuestas_menu.py (generar_tres_propuestas,
     obtener_candidatas_sesion, obtener_candidata). Todas las funciones reciben un
     cursor psycopg2 (RealDictCursor); el caller gestiona la transacción.
Referencia: tickets COM-8 / COM-37 / COM-47 / COM-50 / COM-59 / COM-60 / COM-71 /
COM-72 / COM-61 / COM-74 (solo trazabilidad).
"""
import json
import hashlib
from datetime import date, timedelta
from collections import Counter

# COM-37 v5: resolución unificada de precios y conversión estándar de unidades
from precios_insumos import (
    precios_por_gramo_por_insumo,
    mejor_opcion_ingrediente,
    gramos_por_unidad_estandar,
    gramos_por_unidad_compra,
)
# COM-37 v7: predicción RF compartida con el optimizador (misma fuente de verdad)
from optimizador import predecir_precio_con_confianza
# COM-59A + COM-71: precios vigentes, subsidio, margen objetivo y STOCK REMANENTE
from subsidio_motor import (
    costo_con_subsidio,
    precio_venta_vigente,
    margen_semanal_objetivo,
    subsidio_gramos_del_mes,
    stock_remanente_mes,          # COM-71 (D5)
)
# COM-74: predicción de demanda (misma fuente que el POS) para comensales por día
from ai_engine import predecir_demanda_raciones
# COM-37 v4/v5: reglas de proteína VIGENTES y normalizador, compartidos con K-means
try:
    from ml.kmeans_recetas import cargar_reglas_proteinas, _normalizar
except Exception:  # degradación controlada si el paquete se importa como módulo suelto
    from kmeans_recetas import cargar_reglas_proteinas, _normalizar

# ==========================================
# METADATOS DE LAS 3 VARIANTES DE PONDERACIÓN
# ==========================================
VARIANTES = {
    'NUTRI': {
        'codigo': 'NUTRI',
        'etiqueta': '🩸 NutriMax',
        'descripcion': 'Prioriza combatir la anemia: máximo hierro y proteína.',
        'parametro': 'PLANIFICACION_VARIANTE_NUTRI_W',
    },
    'ECONO': {
        'codigo': 'ECONO',
        'etiqueta': '💰 EconoMax',
        'descripcion': 'Prioriza el presupuesto: menor costo por ración.',
        'parametro': 'PLANIFICACION_VARIANTE_ECONO_W',
    },
    'BALANCE': {
        'codigo': 'BALANCE',
        'etiqueta': '⚖️ BalanceMax',
        'descripcion': 'Balance óptimo entre nutrición y costo.',
        'parametro': 'PLANIFICACION_VARIANTE_BALANCE_W',
    },
}

DIAS_NOMBRE = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
CLAVES_PESOS = ['hierro', 'proteina', 'energia', 'precio', 'variedad']
TOLERANCIA_PRESUPUESTO = 1.05   # margen del 5% sobre el presupuesto semanal
# COM-8 v2: el top de ingredientes solo considera estas categorías (nunca especias,
# cereales, grasas ni lácteos), según requerimiento de la administradora.
CATEGORIAS_TOP_INGREDIENTE = ('Vegetales y Hortalizas', 'Frutas', 'Proteinas')
# COM-8 v2: días de cocina por defecto (Lun-Vie); el comedor puede ampliar/reducir.
DIAS_DEFAULT = [1, 2, 3, 4, 5]
# COM-60: prefijo de etiqueta del cluster prioritario (re-etiquetado COM-60 D4)
PREFIJO_CLUSTER_ANEMIA = 'Anti-Anemia'
# COM-71: piso sensato del factor de holgura diaria (1.0 = gasto perfectamente uniforme)
FLEX_DIA_MIN = 1.0
FLEX_DIA_DEFAULT = 2.0
# COM-74: default de cocineras si el parámetro no existe (coherente con POS)
COCINERAS_DEFAULT = 20


# ==========================================
# UTILIDADES
# ==========================================
def _lunes_de(fecha_referencia: date) -> date:
    """Retorna el lunes de la semana de la fecha dada."""
    return fecha_referencia - timedelta(days=fecha_referencia.weekday())


def _z(valor, minimo, maximo):
    """Normalización min-max 0..1; 0.5 si no hay rango."""
    if maximo == minimo:
        return 0.5
    return (float(valor) - minimo) / (maximo - minimo)


def _jitter_weights(base: dict, seed: int, idx_variante: int) -> dict:
    """
    Desplaza ligeramente cada peso de forma determinista según (seed, variante).
    Es el mecanismo del botón "Regenerar": seed distinto => ponderaciones distintas
    => menús distintos, sin alterar la lógica del motor.
    """
    if not isinstance(base, dict):
        base = {}
    out = {}
    for i, clave in enumerate(CLAVES_PESOS):
        delta = (((seed or 0) * 7 + idx_variante * 13 + i * 5) % 11) - 5  # -5..+5
        out[clave] = max(0.0, float(base.get(clave, 0.0)) + delta * 0.01)
    total = sum(out.values()) or 1.0
    return {k: round(v / total, 4) for k, v in out.items()}


# ==========================================
# CARGA DE PARÁMETROS Y CONTEXTO
# ==========================================
def cargar_parametros(cur) -> dict:
    """
    Lee los parámetros COM-8 y los comensales por tipo.
    COM-59A: los PRECIOS DE VENTA ya no se leen de los parámetros fijos PRECIO_*:
    se resuelven con precio_venta_vigente() (tabla precios_venta, precio único
    vigente con historial; los parámetros quedan como fallback interno del helper).
    COM-60: lee además KMEANS_CUOTA_CLUSTER_FEO (días mínimos/semana del cluster
    anti-anemia) y KMEANS_FE_SO_DESEMPATE (desempate por hierro por sol).
    COM-71: lee PLANIFICACION_FLEX_DIA (holgura diaria; default 2.0, piso 1.0).
    COM-74: lee PLANIFICACION_COCINERAS (default 20): comensales que comen pero no
    pagan; se suman al total de raciones a cocinar (no a la recolección).
    """
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave LIKE 'PLANIFICACION_%'
           OR clave IN ('KMEANS_CUOTA_CLUSTER_FEO', 'KMEANS_FE_SO_DESEMPATE');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    ponderaciones = {}
    for codigo, meta in VARIANTES.items():
        base = {}
        crudo = p.get(meta['parametro'], '{}')
        try:
            parsed = json.loads(crudo)
            if isinstance(parsed, dict):
                base = parsed
        except Exception:
            base = {}
        ponderaciones[codigo] = base
    rotacion = [1, 2, 4, 1, 3, 2, 4]
    try:
        parsed_rot = json.loads(p.get('PLANIFICACION_ROTACION_CLUSTERS', '[1,2,4,1,3,2,4]'))
        if isinstance(parsed_rot, list) and parsed_rot:
            rotacion = [int(x) for x in parsed_rot]
    except Exception:
        pass
    # COM-60: cuota anti-anemia y flag de desempate (con defaults del criterio D3)
    try:
        cuota_feo = int(float(p.get('KMEANS_CUOTA_CLUSTER_FEO', 2)))
    except Exception:
        cuota_feo = 2
    desempate_fe_so = str(p.get('KMEANS_FE_SO_DESEMPATE', 'true')).strip().lower() in ('true', '1', 'si', 'sí')
    # COM-71 (D4): factor de holgura diaria con piso sensato
    try:
        flex_dia = float(p.get('PLANIFICACION_FLEX_DIA', FLEX_DIA_DEFAULT))
    except Exception:
        flex_dia = FLEX_DIA_DEFAULT
    if flex_dia < FLEX_DIA_MIN:
        flex_dia = FLEX_DIA_MIN
    # COM-74: cocineras por día (parámetro nuevo; default 20)
    try:
        cocineras = int(float(p.get('PLANIFICACION_COCINERAS', COCINERAS_DEFAULT)))
    except Exception:
        cocineras = COCINERAS_DEFAULT
    return {
        'dias': int(float(p.get('PLANIFICACION_DIAS_SEMANA', 7))),
        'rotacion': rotacion,
        'ponderaciones': ponderaciones,
        'com_social': int(float(p.get('PLANIFICACION_COMENSALES_SOCIAL', 22))),
        'com_afiliado': int(float(p.get('PLANIFICACION_COMENSALES_AFILIADO', 48))),
        'com_normal': int(float(p.get('PLANIFICACION_COMENSALES_NORMAL', 50))),
        # COM-59A (trazabilidad): lectura anterior de parámetros fijos, comentada:
        # 'precio_social': float(p.get('PRECIO_SOCIAL', 0)),
        # 'precio_afiliado': float(p.get('PRECIO_AFILIADO', 3)),
        # 'precio_normal': float(p.get('PRECIO_NORMAL', 5)),
        'precio_social': precio_venta_vigente(cur, 'Social'),
        'precio_afiliado': precio_venta_vigente(cur, 'Afiliado'),
        'precio_normal': precio_venta_vigente(cur, 'Normal'),
        # COM-60: prioridad Anemia Cero y desempate Fe/S/
        'cuota_feo': cuota_feo,
        'desempate_fe_so': desempate_fe_so,
        # COM-71: holgura diaria
        'flex_dia': flex_dia,
        # COM-74: cocineras (comen, no pagan)
        'cocineras': cocineras,
    }


# ==========================================
# COM-74: COMENSALES PROYECTADOS POR DÍA (IA + cocineras)
# ==========================================
def _limites_ia(cur):
    """Lee los pisos de predicción IA (IA_MIN_* / IA_FINDE_*) desde parametros_sistema."""
    cur.execute("SELECT clave, valor FROM parametros_sistema WHERE clave LIKE 'IA_%';")
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    limites_minimos = {
        'SOCIAL': int(float(p.get('IA_MIN_SOCIAL', 15))),
        'AFILIADO': int(float(p.get('IA_MIN_AFILIADO', 35))),
        'NORMAL': int(float(p.get('IA_MIN_NORMAL', 80))),
    }
    limites_finde = {
        'SOCIAL': int(float(p.get('IA_FINDE_SOCIAL', 10))),
        'AFILIADO': int(float(p.get('IA_FINDE_AFILIADO', 20))),
        'NORMAL': int(float(p.get('IA_FINDE_NORMAL', 30))),
    }
    return limites_minimos, limites_finde


def _comensales_por_dia(cur, params, fecha_inicio, dias) -> dict:
    """
    COM-74 (D1): para cada día de cocina consulta la PREDICCIÓN DE DEMANDA con la
    fecha real del día (misma fuente que el POS: ai_engine con historial real).
    Suma las cocineras (PLANIFICACION_COCINERAS). Si la predicción devuelve None
    (sin históricos suficientes del día), cae a los parámetros estáticos y marca
    fuente_comensales='parametro' para auditoría.
    Retorna {dia: {social, afiliado, normal, cocineras, total, pagantes, fuente}}.
    """
    limites_minimos, limites_finde = _limites_ia(cur)
    out = {}
    for d in dias:
        fd = fecha_inicio + timedelta(days=d - 1)
        pred = None
        try:
            pred = predecir_demanda_raciones(
                fd.weekday(), fd.day, limites_minimos, limites_finde, cur=cur)
        except Exception as e:
            print(f"[COM-74] Predicción de comensales falló para {fd}: {e}")
            pred = None
        if pred:
            # COM-74: pred es un dict {'prediccion': [social, afiliado, normal], ...}
            prediccion = pred['prediccion']
            soc, afi, nor = int(prediccion[0]), int(prediccion[1]), int(prediccion[2])
            fuente = 'prediccion_ia'
        else:
            soc, afi, nor = params['com_social'], params['com_afiliado'], params['com_normal']
            fuente = 'parametro'
        coc = params['cocineras']
        out[d] = {
            'social': soc,
            'afiliado': afi,
            'normal': nor,
            'cocineras': coc,
            'total': soc + afi + nor + coc,          # raciones a cocinar (COM-74 D2)
            'pagantes': soc + afi + nor,             # base de la recolección
            'fuente': fuente,
            'fecha': fd.isoformat(),
        }
    return out


# =========================================================================
# COM-37 v5 (trazabilidad): _precios_por_gramo COMENTADO. Reemplazado por
# precios_insumos + mejor_opcion_ingrediente + equivalencias de unidad de USO.
# =========================================================================
# def _precios_por_gramo(cur) -> dict:
#     cur.execute(""" ... historial_precios último día por ingrediente ... """)
#     precios = {r['ing_id']: float(r['precio_por_gramo']) for r in cur.fetchall()}
#     manuales = obtener_precios_manuales_por_kg(cur, date.today())
#     for ing_id, precio_kg in manuales.items():
#         precios.setdefault(ing_id, precio_kg / 1000.0)
#     return precios


def _cargar_equivalencias(cur):
    """COM-37 v5: mapa {(ingrediente_id, insumo_id, unidad_uso_id): gramos} activas."""
    cur.execute("""
        SELECT ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso
        FROM ingredientes_equivalencias
        WHERE estado_activo = TRUE;
    """)
    return {(r['ingrediente_id'], r['insumo_id'], r['unidad_uso_id']):
            float(r['gramos_por_unidad_uso']) for r in cur.fetchall()}


def _opcion_con_prediccion(cur, ing_id, fecha, precios_insumo, peso_estimado_g):
    """
    COM-37 v7: mejor opción de precio del ingrediente con la MISMA jerarquía que
    Evaluar: scraper (día o última corrida) > manual insumo > legacy ingrediente >
    predicción RF (menor costo entre los insumos del ingrediente).
    """
    opc = mejor_opcion_ingrediente(cur, ing_id, fecha, precios_insumo)
    if opc:
        return opc
    cur.execute("""
        SELECT ins.id, ins.nombre, ins.origen,
               um.abreviatura, um.tipo_magnitud, um.factor_a_base
        FROM insumos ins
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        WHERE ins.ingrediente_id = %s;
    """, (ing_id,))
    mejor = None
    for ins in cur.fetchall():
        pred, conf, ok = predecir_precio_con_confianza(ins['id'], fecha, None, cur)
        if not (ok and pred):
            continue
        g_compra = gramos_por_unidad_compra(
            ins['abreviatura'], ins['tipo_magnitud'], ins['factor_a_base'], peso_estimado_g)
        if g_compra <= 0:
            continue
        ppg = float(pred) / g_compra
        if mejor is None or ppg < mejor['ppg']:
            mejor = {
                'insumo_id': ins['id'],
                'insumo_nombre': ins['nombre'],
                'origen': ins['origen'],
                'ppg': ppg,
                'fuente': 'PREDICHO',
                'detalle': f"S/ {pred} por {ins['abreviatura']} (PREDICHO {conf}%)",
            }
    return mejor


def _cargar_recetas_cluster(cur):
    """
    Recetas del modelo K-means activo con nutrición POR RACIÓN (COM-47 v3: sin dividir).
    COM-71: también carga el flag `costeable` del snapshot (R4 como flag); las no
    costeables se filtran antes de seleccionar pero se auditan en el resumen.
    Retorna (recetas, modelo_id).
    """
    cur.execute("SELECT id FROM kmeans_modelos WHERE activo = TRUE ORDER BY id DESC LIMIT 1;")
    fila = cur.fetchone()
    if not fila:
        return [], None
    modelo_id = fila['id']
    cur.execute("""
        SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
               COALESCE(rc.costeable, TRUE) AS costeable,
               r.nombre,
               COALESCE(NULLIF(r.raciones, 0), 4) AS raciones,
               r.hierro_mg, r.proteina_g, r.energia_kcal
        FROM recetas_clusters rc
        JOIN recetas_almuerzo r ON r.id = rc.receta_id
        WHERE rc.modelo_id = %s;
    """, (modelo_id,))
    recetas = []
    for r in cur.fetchall():
        if r['energia_kcal'] is None:
            continue  # receta sin nutrición cargada: se omite del motor
        recetas.append({
            'receta_id': r['receta_id'],
            'nombre': r['nombre'],
            'cluster_codigo': r['cluster_codigo'],
            'cluster_etiqueta': r['cluster_etiqueta'],
            # COM-71 (D2): flag de elegibilidad económica venido del modelo
            'costeable': bool(r['costeable']),
            'raciones': float(r['raciones']),
            'hierro_mg': float(r['hierro_mg'] or 0),
            'proteina_g': float(r['proteina_g'] or 0),
            'energia_kcal': float(r['energia_kcal'] or 0),
            'costo_racion': 0.0,            # se completa en el mapeo de costos del día
            'costo_racion_bruto': 0.0,      # COM-59A: costo sin subsidio (auditoría)
            'ahorro_subsidio_racion': 0.0,  # COM-59A: ahorro por ración por subsidio
            'fe_por_sol': 0.0,              # COM-60: hierro por sol (desempate)
            'precio_completo': False,       # COM-37 v2: se completa en el mapeo
            'ingredientes_sin_precio': [],  # COM-37 v2: auditoría de faltantes
            'ingredientes': [],             # lista de dicts {nombre, categoria}
            # COM-61: se marca en generar_tres_propuestas contra el menú anterior
            'repetida_semana_previa': False,
        })
    return recetas, modelo_id


# ==========================================
# COM-61 (HU-11): MENÚ DE LA SEMANA ANTERIOR
# ==========================================
def _recetas_semana_anterior(cur, comedor_id: int, fecha_inicio: date):
    """
    COM-61 (criterio D1): receta_ids del "menú de la semana pasada": la planificación
    VIGENTE más reciente del comedor con fecha_referencia ESTRICTAMENTE ANTERIOR al
    lunes de la semana que se va a generar. Compara por receta_id completo (D2).
    Retorna (set_de_receta_ids, fecha_referencia_o_None). Si el comedor no tiene
    historial VIGENTE previo (primera semana), devuelve (set(), None) y la variedad
    se reporta al 100% sin restricción.
    """
    cur.execute("""
        SELECT ps.id, ps.fecha_referencia
        FROM presupuesto_semanal ps
        WHERE ps.comedor_id = %s
          AND ps.estado = 'VIGENTE'
          AND ps.fecha_referencia < %s
        ORDER BY ps.fecha_referencia DESC, ps.id DESC
        LIMIT 1;
    """, (comedor_id, fecha_inicio))
    fila = cur.fetchone()
    if not fila:
        return set(), None
    cur.execute("""
        SELECT DISTINCT pd.receta_id
        FROM planificacion_dia pd
        WHERE pd.presupuesto_semanal_id = %s AND pd.receta_id IS NOT NULL;
    """, (fila['id'],))
    return {r['receta_id'] for r in cur.fetchall()}, fila['fecha_referencia']


# ==========================================
# COM-71 (D3/D5): MAPEO DE COSTOS POR DÍA CON STOCK REMANENTE
# ==========================================
def _mapa_costos_dia(cur, recetas, fecha: date, comedor_id=None, stock_override=None):
    """
    COM-71: cuerpo generalizado del costeo COM-59A/COM-60. Calcula, PARA UNA FECHA
    DADA, el costo por ración de cada receta y devuelve un mapa
    {receta_id: {costo_racion, costo_racion_bruto, ahorro_subsidio_racion,
    lineas_subvencionadas, fe_por_sol, detalle_gramos_racion, ingredientes,
    precio_completo, ingredientes_sin_precio}} SIN mutar `recetas`.
    * D3: `fecha` es el día real de cocina (precios scraper/predicción de ese día).
    * D5: si `stock_override` se provee (gramos remanentes del mes), el descuento de
      subsidio se hace contra ese stock vía costo_con_subsidio(stock_inicial=...);
      si es None, se usa el stock completo del mes (comportamiento COM-59A).
    * Si comedor_id es None, no se aplica subsidio (costo = bruto), como antes.
    """
    ids = [r['receta_id'] for r in recetas]
    if not ids:
        return {}
    precios_insumo = precios_por_gramo_por_insumo(cur, fecha, fallback_ultima_fecha=True)
    eq_map = _cargar_equivalencias(cur)
    opciones_cache = {}

    def _opcion(ing_id, peso_estimado_g):
        if ing_id not in opciones_cache:
            opciones_cache[ing_id] = _opcion_con_prediccion(
                cur, ing_id, fecha, precios_insumo, peso_estimado_g)
        return opciones_cache[ing_id]

    cur.execute("""
        SELECT ri.receta_id, ri.ingrediente_id, ri.cantidad_requerida,
               ri.unidad_medida_id AS unidad_uso_id,
               um.abreviatura AS unidad_abrev, um.tipo_magnitud, um.factor_a_base,
               ing.peso_estimado_g, ing.nombre AS ing_nombre,
               ca.nombre AS categoria
        FROM receta_ingrediente ri
        JOIN unidades_medida um ON um.id = ri.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ri.ingrediente_id
        LEFT JOIN categorias_alimentos ca ON ca.id = ing.categoria_id
        WHERE ri.receta_id = ANY(%s);
    """, (ids,))
    costo_acum = {}
    nombres_acum = {}
    lineas_tot = {}
    lineas_con_precio = {}
    sin_precio_nom = {}
    lineas_detalle = {}
    for fila in cur.fetchall():
        rid = fila['receta_id']
        lineas_tot[rid] = lineas_tot.get(rid, 0) + 1
        opc = _opcion(fila['ingrediente_id'], fila['peso_estimado_g'])
        if opc is None:
            sin_precio_nom.setdefault(rid, []).append(fila['ing_nombre'])
        else:
            g = eq_map.get((fila['ingrediente_id'], opc['insumo_id'], fila['unidad_uso_id']))
            if g is None:
                g = gramos_por_unidad_estandar(
                    fila['unidad_abrev'], fila['tipo_magnitud'],
                    fila['factor_a_base'], fila['peso_estimado_g'])
            gramos = g * float(fila['cantidad_requerida'])
            costo_linea = gramos * opc['ppg']
            costo_acum[rid] = costo_acum.get(rid, 0.0) + costo_linea
            lineas_con_precio[rid] = lineas_con_precio.get(rid, 0) + 1
            lineas_detalle.setdefault(rid, []).append({
                'ingrediente_id': fila['ingrediente_id'],
                'gramos_totales': gramos,
                'costo_parcial': costo_linea,
            })
        nombres_acum.setdefault(rid, []).append({
            'nombre': fila['ing_nombre'],
            'categoria': fila['categoria'] or '',
        })
    mapa = {}
    for r in recetas:
        rid = r['receta_id']
        raciones = r['raciones'] or 4.0
        lineas = lineas_detalle.get(rid, [])
        total_bruto = costo_acum.get(rid, 0.0)
        bruto_racion = total_bruto / raciones
        ahorro_racion = 0.0
        real_racion = bruto_racion
        n_subv = 0
        if comedor_id is not None and lineas:
            # COM-59A + COM-71(D5): descuento contra stock completo o REMANENTE
            res_sub = costo_con_subsidio(cur, comedor_id, fecha, lineas,
                                         stock_inicial=stock_override)
            real_racion = res_sub['costo_total'] / raciones
            ahorro_racion = bruto_racion - real_racion
            n_subv = sum(1 for l in res_sub['detalle'] if l.get('subvencionado'))
        tot = lineas_tot.get(rid, 0)
        conp = lineas_con_precio.get(rid, 0)
        mapa[rid] = {
            'costo_racion_bruto': round(bruto_racion, 2),
            'costo_racion': round(real_racion, 2),   # REAL post-subsidio del día
            'ahorro_subsidio_racion': round(ahorro_racion, 2),
            'lineas_subvencionadas': n_subv,
            # COM-60: hierro por sol sobre el costo REAL del día (desempate)
            'fe_por_sol': round(r['hierro_mg'] / real_racion, 4) if real_racion and real_racion > 0 else 0.0,
            # COM-59A: gramos por ración por ingrediente (auditoría de stock)
            'detalle_gramos_racion': {l['ingrediente_id']: (l['gramos_totales'] / raciones) for l in lineas},
            'ingredientes': nombres_acum.get(rid, []),
            'precio_completo': (tot > 0 and conp == tot),
            'ingredientes_sin_precio': sorted(set(sin_precio_nom.get(rid, []))),
        }
    return mapa


def _costear_recetas(cur, recetas, fecha: date, comedor_id=None):
    """
    COM-59A/COM-60 (wrapper de trazabilidad COM-71): aplica el mapa de costos de UNA
    fecha sobre `recetas` mutándolas in-place, con stock COMPLETO del mes
    (stock_override=None). Conserva la firma histórica para callers externos;
    el motor semanal usa _mapa_costos_dia por día (D3/D5).
    """
    mapa = _mapa_costos_dia(cur, recetas, fecha, comedor_id, stock_override=None)
    for r in recetas:
        r.update(mapa.get(r['receta_id'], {}))


# ==========================================
# COM-37 v4/v5: VALIDACIÓN DE REGLAS DE PROTEÍNA VIGENTES (R1/R2)
# ==========================================
def _validar_reglas_proteinas_vigentes(cur, recetas):
    """
    COM-37 v4/v5: aplica las listas CONFIGURABLES de proteínas permitidas (R1) e
    ingredientes vetados (R2) vigentes en parametros_sistema (las mismas que usa
    K-means) sobre las recetas candidatas del modelo activo. Retorna (validas, excluidas).
    COM-72 (nota): requiere que `recetas[].ingredientes` YA esté poblado (lo hace el
    primer_mapa en generar_tres_propuestas ANTES de llamar a esta función).
    """
    re_permitida, re_vetada, _, _ = cargar_reglas_proteinas(cur)
    validas = []
    excluidas = []
    for r in recetas:
        tiene_permitida = False
        tiene_vetada = False
        for ing in r['ingredients'] if 'ingredients' in r else r['ingredientes']:
            nombre = ing.get('nombre') if isinstance(ing, dict) else ing
            nn = _normalizar(nombre)
            if not nn:
                continue
            if re_permitida.search(nn):
                tiene_permitida = True
            elif re_vetada.search(nn):
                tiene_vetada = True
        if tiene_permitida and not tiene_vetada:
            validas.append(r)
        else:
            detalles = []
            if not tiene_permitida:
                detalles.append('sin_proteina_permitida')
            if tiene_vetada:
                detalles.append('contiene_ingrediente_vetado')
            excluidas.append({
                'receta_id': r['receta_id'],
                'nombre': r['nombre'],
                'motivo': 'no_cumple_reglas_proteina_vigentes',
                'detalle': detalles,
            })
    return validas, excluidas


def _minmax(recetas) -> dict:
    """Rangos min-max por feature para la normalización del scoring."""
    if not recetas:
        return {k: (0, 1) for k in ('hierro', 'proteina', 'energia', 'precio')}
    return {
        'hierro': (min(r['hierro_mg'] for r in recetas), max(r['hierro_mg'] for r in recetas)),
        'proteina': (min(r['proteina_g'] for r in recetas), max(r['proteina_g'] for r in recetas)),
        'energia': (min(r['energia_kcal'] for r in recetas), max(r['energia_kcal'] for r in recetas)),
        'precio': (min(r['costo_racion'] for r in recetas), max(r['costo_racion'] for r in recetas)),
    }


# ==========================================
# COM-60: HELPERS DE PRIORIDAD ANEMIA CERO
# ==========================================
def _codigos_anti_anemia(recetas_por_cluster) -> set:
    """Códigos de cluster cuya etiqueta empieza por 'Anti-Anemia' (re-etiquetado COM-60)."""
    return {codigo for codigo, filas in recetas_por_cluster.items()
            if filas and str(filas[0].get('cluster_etiqueta') or '').startswith(PREFIJO_CLUSTER_ANEMIA)}


# ==========================================
# SCORING GREEDY
# ==========================================
def _score(rec, pesos, mm, usada: bool) -> float:
    """
    Score lineal ponderado POR RACIÓN: hierro/proteína/energía suman, precio resta.
    El peso 'variedad' bonifica recetas aún no usadas en la semana.
    COM-59A: el precio que usa es el costo REAL post-subsidio (campo costo_racion).
    COM-60: el score NO incluye Fe/S/; ese indicador solo desempata.
    COM-71: con costeo por día, costo_racion es el del día evaluado (D3).
    """
    s = (pesos.get('hierro', 0) * _z(rec['hierro_mg'], *mm['hierro']) +
         pesos.get('proteina', 0) * _z(rec['proteina_g'], *mm['proteina']) +
         pesos.get('energia', 0) * _z(rec['energia_kcal'], *mm['energia']) -
         pesos.get('precio', 0) * _z(rec['costo_racion'], *mm['precio']))
    if not usada:
        s += pesos.get('variedad', 0)
    return s


def _generar_menu_variante(recetas_por_cluster, todas, pesos, params,
                           presupuesto_semanal, fecha_inicio, dias,
                           costos_por_dia, comensales_por_dia, permitir_repetidos=False):
    """
    COM-8 v2 + COM-60 + COM-71 + COM-72 + COM-61 + COM-74: Greedy por DÍA SELECCIONADO.
    * COM-60: cuota anti-anemia por deadline y desempate Fe/S/.
    * COM-71 (D2): solo candidatas costeables y con precio completo ese día.
    * COM-71 (D3): scoring y presupuesto con el costo del día (costos_por_dia[d]).
    * COM-71 (D4): tope diario = flex × ((límite − acumulado) / días restantes); si no
      cabe en el tope pero sí en el límite semanal, se permite con flex_excedido=True.
    * COM-71 (D5): el costo del día ya viene descontado contra stock REMANENTE.
    * COM-72: guarda anti-repetición en día forzado (cluster singleton agotado).
    * COM-61 (HU-11): con permitir_repetidos=False, el pool diario prefiere recetas
      FRESCAS (no cocinadas la semana VIGENTE anterior); las repetidas solo entran si
      el pool del cluster objetivo se queda sin frescas (repetición INEVITABLE,
      marcada por día). Con permitir_repetidos=True no se filtra, pero se audita.
    * COM-74: el costo del día se multiplica por el TOTAL PROYECTADO del día
      (predicción IA + cocineras) y la recolección proyectada usa solo pagantes
      (Social/Afiliado/Normal) × precios vigentes. Cada día del menú persiste sus
      comensales por tipo, total, pagantes y fuente_comensales para auditoría y
      para que la selección los grabe en planificacion_dia.
    Retorna (menu, sobrepaso, conteo_anemia).
    Trazabilidad: firma anterior sin costos_por_dia/comensales_por_dia comentada abajo.
    """
    comensales_por_dia = comensales_por_dia or {}
    usadas = set()
    menu = []
    acumulado = 0.0
    sobrepaso = False
    conteo_anemia = 0                      # COM-60
    anemia_codes = _codigos_anti_anemia(recetas_por_cluster)   # COM-60
    cuota = int(params.get('cuota_feo', 2))                    # COM-60
    desempate = bool(params.get('desempate_fe_so', True))      # COM-60
    flex = float(params.get('flex_dia', FLEX_DIA_DEFAULT))     # COM-71 (D4)
    # COM-74 (trazabilidad): antes total_comensales y recolección eran FIJOS:
    # total_comensales = params['com_social'] + params['com_afiliado'] + params['com_normal']
    # recoleccion_dia = (com_social*precio_social + com_afiliado*precio_afiliado + com_normal*precio_normal)
    limite = presupuesto_semanal * TOLERANCIA_PRESUPUESTO

    for i, d in enumerate(dias):
        info_dia = costos_por_dia.get(d, {})
        costo_map = info_dia.get('mapa', {}) if isinstance(info_dia, dict) else {}
        stock_rem_aplicado = bool(info_dia.get('stock_remanente_aplicado', False)) if isinstance(info_dia, dict) else False
        # COM-74: comensales proyectados del día (IA + cocineras) con fallback estático
        cd = comensales_por_dia.get(d) or {
            'social': params['com_social'], 'afiliado': params['com_afiliado'],
            'normal': params['com_normal'], 'cocineras': params.get('cocineras', COCINERAS_DEFAULT),
            'total': params['com_social'] + params['com_afiliado'] + params['com_normal'] + params.get('cocineras', COCINERAS_DEFAULT),
            'pagantes': params['com_social'] + params['com_afiliado'] + params['com_normal'],
            'fuente': 'parametro',
        }
        total_dia = cd['total']
        recoleccion_dia = (cd['social'] * params['precio_social'] +
                           cd['afiliado'] * params['precio_afiliado'] +
                           cd['normal'] * params['precio_normal'])

        # COM-71 (D2/D3): fusiona la receta base con sus costos DEL día y filtra elegibles
        def _merge(r):
            m = dict(r)
            m.update(costo_map.get(r['receta_id'], {}))
            return m
        elegibles = [
            _merge(r) for r in todas
            if r.get('costeable', True)
            and costo_map.get(r['receta_id'], {}).get('precio_completo', False)
            and costo_map.get(r['receta_id'], {}).get('costo_racion', 0) > 0
        ]
        mm = _minmax(elegibles) if elegibles else _minmax(todas)
        por_cluster_dia = {}
        for m in elegibles:
            por_cluster_dia.setdefault(m['cluster_codigo'], []).append(m)

        # COM-60: regla de deadline para garantizar la cuota anti-anemia
        restantes = len(dias) - i
        faltante = cuota - conteo_anemia
        forzar_anemia = (faltante > 0 and restantes == faltante and bool(anemia_codes))
        cluster_obj = params['rotacion'][(d - 1) % len(params['rotacion'])]
        if forzar_anemia:
            cluster_forzado = next((c for c in params['rotacion'] if c in anemia_codes), None)
            if cluster_forzado is not None and por_cluster_dia.get(cluster_forzado):
                cluster_obj = cluster_forzado
        candidatas = list(por_cluster_dia.get(cluster_obj, [])) or list(elegibles)
        if not candidatas:
            continue  # sin elegibles ese día (ej. todo sin precio): se omite el día

        # COM-61 (HU-11, D5): pool de frescas primero; repetidas solo si no hay
        # alternativas frescas en este pool (repetición inevitable, auditada).
        # Trazabilidad: antes de COM-61 el pool era directamente `candidatas`.
        if not permitir_repetidos:
            frescas = [c for c in candidatas if not c.get('repetida_semana_previa')]
            candidatas = frescas if frescas else candidatas

        # COM-72 + COM-61: guarda anti-repetición intra-semana en día forzado;
        # al relajar la cuota se prefieren frescas sin usar antes que repetidas.
        if forzar_anemia and all(c['receta_id'] in usadas for c in candidatas):
            sin_usar = [e for e in elegibles
                        if e['receta_id'] not in usadas
                        and (permitir_repetidos or not e.get('repetida_semana_previa'))]
            if not sin_usar:
                sin_usar = [e for e in elegibles if e['receta_id'] not in usadas]
            if sin_usar:
                candidatas = sin_usar

        # COM-60: orden por (score, Fe/S/ si desempate, sin_usar).
        candidatas.sort(key=lambda r: (
            _score(r, pesos, mm, r['receta_id'] in usadas),
            (r.get('fe_por_sol') or 0.0) if desempate else 0.0,
            r['receta_id'] not in usadas), reverse=True)

        # COM-71 (D4): tope diario con holgura sobre el presupuesto restante
        share = (limite - acumulado) / restantes if restantes > 0 else limite
        cap_dia = share * flex

        def _guardia_repeticion(r):
            return not (r['receta_id'] in usadas and any(c['receta_id'] not in usadas for c in candidatas))

        elegida = None
        flex_excedido_dia = False
        # Pase 1: dentro del tope diario FLEX y del límite semanal
        for r in candidatas:
            if not _guardia_repeticion(r):
                continue
            costo_dia = r['costo_racion'] * total_dia          # COM-74: total con cocineras
            if acumulado + costo_dia <= limite and costo_dia <= cap_dia:
                elegida = r
                break
        # Pase 2: holgura: no cabe en el tope diario pero sí en el semanal
        if elegida is None:
            for r in candidatas:
                if not _guardia_repeticion(r):
                    continue
                costo_dia = r['costo_racion'] * total_dia
                if acumulado + costo_dia <= limite:
                    elegida = r
                    flex_excedido_dia = True
                    break
        # Pase 3: fallback histórico (la más barata; puede marcar sobrepaso)
        if elegida is None:
            elegida = min(candidatas, key=lambda r: r['costo_racion'])
            if acumulado + elegida['costo_racion'] * total_dia > limite:
                sobrepaso = True

        costo_dia = round(elegida['costo_racion'] * total_dia, 2)
        acumulado += costo_dia
        usadas.add(elegida['receta_id'])
        es_anemia = elegida['cluster_codigo'] in anemia_codes   # COM-60
        if es_anemia:
            conteo_anemia += 1
        menu.append({
            'dia_semana': d,
            'dia_nombre': DIAS_NOMBRE[(d - 1) % 7],
            'fecha': (fecha_inicio + timedelta(days=d - 1)).isoformat(),
            'receta_id': elegida['receta_id'],
            'receta_nombre': elegida['nombre'],
            'cluster_codigo': elegida['cluster_codigo'],
            'cluster_etiqueta': elegida['cluster_etiqueta'],
            'costo_racion': elegida['costo_racion'],
            # COM-59A: auditoría del subsidio por día
            'costo_racion_bruto': elegida.get('costo_racion_bruto', elegida['costo_racion']),
            'ahorro_subsidio': elegida.get('ahorro_subsidio_racion', 0.0),
            # COM-60: auditoría de prioridad anti-anemia y eficiencia Fe/S/ por día
            'es_anti_anemia': es_anemia,
            'fe_por_sol': elegida.get('fe_por_sol', 0.0),
            # COM-71: auditoría de holgura diaria y stock remanente por día
            'flex_cap_dia': round(cap_dia, 2),
            'flex_excedido': flex_excedido_dia,
            'stock_remanente_aplicado': stock_rem_aplicado,
            'costeable': True,
            # COM-61 (HU-11): auditoría de variedad entre semanas por día
            'repite_semana_anterior': bool(elegida.get('repetida_semana_previa', False)),
            'repeticion_inevitable': bool(elegida.get('repetida_semana_previa', False)) and not permitir_repetidos,
            # COM-74: comensales proyectados del día (persistibles en planificacion_dia)
            'comensales_social': cd['social'],
            'comensales_afiliado': cd['afiliado'],
            'comensales_normal': cd['normal'],
            'comensales_cocinera': cd['cocineras'],
            'comensales_total': cd['total'],
            'comensales_pagantes': cd['pagantes'],
            'fuente_comensales': cd['fuente'],
            'costo_total_dia': costo_dia,
            'energia_kcal': round(elegida['energia_kcal'], 2),
            'proteina_g': round(elegida['proteina_g'], 2),
            'hierro_mg': round(elegida['hierro_mg'], 2),
            'recoleccion_proyectada': round(recoleccion_dia, 2),
        })
    return menu, sobrepaso, conteo_anemia

# COM-71 (trazabilidad): firma anterior de _generar_menu_variante (sin costos_por_dia),
# comentada: el costo venía mutado en `recetas` por _costear_recetas de una sola fecha.
# COM-74 (trazabilidad): firma intermedia sin comensales_por_dia:
# def _generar_menu_variante(recetas_por_cluster, todas, pesos, params,
#                            presupuesto_semanal, fecha_inicio, dias,
#                            costos_por_dia): ...


def _top_ingredientes(menu, ingredientes_por_id, n=3):
    """COM-8 v3: Top N ingredientes más usados en la semana (categorías permitidas)."""
    contador = Counter()
    nombres_vistos = {}
    for dia in menu:
        for ing in ingredientes_por_id.get(dia['receta_id'], []):
            if not isinstance(ing, dict):
                continue  # legacy (texto plano): se omite, no se puede validar categoría
            categoria = (ing.get('categoria') or '').strip()
            if categoria not in CATEGORIAS_TOP_INGREDIENTE:
                continue
            nombre = (ing.get('nombre') or '').strip()
            if not nombre:
                continue
            clave = nombre.lower()
            contador[clave] += 1
            nombres_vistos[clave] = nombre
    return [nombres_vistos[k] for k, _ in contador.most_common(n)]


# ==========================================
# API PÚBLICA DEL MOTOR
# ==========================================
def generar_tres_propuestas(cur, comedor_id: int, presupuesto_semanal: float,
                            creado_por_id: int, fecha_referencia: date = None,
                            seed: int = 0, dias_semana: list = None,
                            permitir_repetidos: bool = False):
    """
    COM-8 v2/v3 + COM-37 + COM-47 v3 + COM-50 v3 + COM-59A + COM-60 + COM-71 +
    COM-72 + COM-61 + COM-74: Genera y persiste las 3 propuestas de menú semanal para
    los DÍAS DE COCINA indicados.
    COM-74: los comensales de cada día vienen de la PREDICCIÓN IA (con cocineras y
    fallback a parámetros marcado como fuente='parametro'); el costo del día usa el
    total con cocineras y la recolección solo pagantes.
    COM-71: (D2) filtra no costeables y las audita; (D3) costeo por día con fecha
    real; (D5) subsidio contra stock REMANENTE; (D4) tope diario FLEX.
    COM-72 (HOTFIX): el mapa de costos del primer día (que rellena `ingredientes` y
    `precio_completo`) se aplica ANTES de la validación R1/R2.
    COM-61 (HU-11): `permitir_repetidos` (default False, lo pone el checkbox de la UI
    tras confirmación) controla la exclusión de los platos del menú VIGENTE de la
    semana anterior (_recetas_semana_anterior, criterio D1/D2). Cada variante audita
    en su resumen: semana_anterior_fecha, repeticiones_semana_anterior, variedad_pct
    y permitir_repetidos (criterio D7: todo en JSONB, sin cambios de esquema).
    COM-60: auditoría de cuota anti-anemia por variante.
    COM-59A: recolección con precios vigentes y validación del margen semanal objetivo.
    """
    if presupuesto_semanal is None or float(presupuesto_semanal) <= 0:
        raise ValueError("El presupuesto semanal debe ser mayor a cero.")
    presupuesto_semanal = float(presupuesto_semanal)
    fecha_referencia = fecha_referencia or date.today()
    dias = sorted(set(int(d) for d in (dias_semana or DIAS_DEFAULT)))
    if not dias or any(d < 1 or d > 7 for d in dias):
        raise ValueError("Los días de cocina deben estar entre 1 (Lunes) y 7 (Domingo).")
    params = cargar_parametros(cur)
    recetas, modelo_id = _cargar_recetas_cluster(cur)
    if not recetas:
        raise ValueError(
            "No hay un modelo K-means activo con recetas aptas. Entrene el modelo en "
            "la pestaña 'Clusters K-Means' antes de generar propuestas de menú.")
    # COM-71 (D2): separa no costeables (auditoría) de seleccionables
    no_costeables = [r for r in recetas if not r.get('costeable', True)]
    seleccionables = [r for r in recetas if r.get('costeable', True)]

    fecha_inicio = _lunes_de(fecha_referencia)
    # COM-74 (D1): comensales proyectados por día (IA + cocineras) ANTES del costeo
    comensales_por_dia = _comensales_por_dia(cur, params, fecha_inicio, dias)
    # COM-71 (D3/D5): stock remanente por mes involucrado y mapa de costos por día
    meses = sorted({((fecha_inicio + timedelta(days=d - 1)).year,
                     (fecha_inicio + timedelta(days=d - 1)).month) for d in dias})
    stock_rem_por_mes = {}
    stock_full_por_mes = {}
    for (yy, mm_) in meses:
        stock_rem_por_mes[(yy, mm_)] = stock_remanente_mes(cur, comedor_id, yy, mm_,
                                                           antes_de=fecha_inicio)
        stock_full_por_mes[(yy, mm_)] = subsidio_gramos_del_mes(cur, comedor_id, yy, mm_)
    costos_por_dia = {}
    for d in dias:
        fd = fecha_inicio + timedelta(days=d - 1)
        clave_mes = (fd.year, fd.month)
        rem = stock_rem_por_mes.get(clave_mes, {})
        costos_por_dia[d] = {
            'mapa': _mapa_costos_dia(cur, seleccionables, fd, comedor_id, stock_override=rem),
            'stock_remanente_aplicado': bool(rem),
        }
    # COM-72 (HOTFIX): rellena ingredientes/completitud ANTES de validar R1/R2.
    # COM-71 (trazabilidad): este bloque estaba DESPUÉS de la validación:
    #   seleccionables, excluidas_reglas = _validar_reglas_proteinas_vigentes(...)
    #   ... raise si len(seleccionables) < len(dias) ...
    #   primer_mapa = costos_por_dia[dias[0]]['mapa']; for r in seleccionables: r.update(...)
    primer_mapa = costos_por_dia[dias[0]]['mapa'] if dias else {}
    for r in seleccionables:
        r.update(primer_mapa.get(r['receta_id'], {}))

    # COM-37 v4/v5: reglas de proteína vigentes sobre recetas YA pobladas
    seleccionables, excluidas_reglas = _validar_reglas_proteinas_vigentes(cur, seleccionables)
    if len(seleccionables) < len(dias):
        detalle_reglas = "; ".join(
            f"{e['nombre']} ({'/'.join(e['detalle'])})" for e in excluidas_reglas[:5]
        )
        detalle_nc = "; ".join(
            f"{r['nombre']} (sin precio: {', '.join(r.get('ingredientes_sin_precio') or ['?'])[:60]})"
            for r in no_costeables[:5]
        )
        raise ValueError(
            f"Solo hay {len(seleccionables)} recetas costeables y con reglas de proteína "
            f"vigentes; se requieren al menos {len(dias)} para cubrir los días seleccionados. "
            f"No costeables (R4 como flag, COM-71): {detalle_nc or 'ninguna'}. "
            f"Excluidas por reglas de proteína: {detalle_reglas or 'ninguna'}. "
            f"Cargue precios manuales en Gestión de Ingredientes (COM-37) o espere la "
            f"corrida del scraper; al completarse el precio la receta vuelve a ser "
            f"seleccionable SIN re-entrenar el modelo.")

    # COM-61 (HU-11, D1/D2): marca las recetas que ya se cocinaron la semana VIGENTE
    # anterior para que el greedy las evite (salvo permitir_repetidos o inevitabilidad).
    recetas_previas, fecha_previa = _recetas_semana_anterior(cur, comedor_id, fecha_inicio)
    for r in seleccionables:
        r['repetida_semana_previa'] = r['receta_id'] in recetas_previas

    recetas_por_cluster = {}
    for r in seleccionables:
        recetas_por_cluster.setdefault(r['cluster_codigo'], []).append(r)
    recetas_por_id = {r['receta_id']: r for r in seleccionables}
    marca = f"{comedor_id}|{fecha_inicio.isoformat()}|{creado_por_id}|{seed}|{'-'.join(map(str, dias))}"
    sesion_id = hashlib.sha256(marca.encode()).hexdigest()[:32]
    margen_objetivo = margen_semanal_objetivo(cur)
    propuestas = []
    for idx, (codigo, meta) in enumerate(VARIANTES.items()):
        pesos = _jitter_weights(params['ponderaciones'].get(codigo, {}), seed, idx)
        menu, sobrepaso, conteo_anemia = _generar_menu_variante(
            recetas_por_cluster, seleccionables, pesos, params,
            presupuesto_semanal, fecha_inicio, dias, costos_por_dia,
            comensales_por_dia=comensales_por_dia,
            permitir_repetidos=permitir_repetidos)
        costo_total = round(sum(d['costo_total_dia'] for d in menu), 2)
        recoleccion_total = round(sum(d['recoleccion_proyectada'] for d in menu), 2)
        # ---- COM-59A + COM-71(D5): auditoría semanal contra STOCK REMANENTE por mes ----
        consumo_por_mes = {}
        for d in menu:
            fd = date.fromisoformat(d['fecha'])
            clave_mes = (fd.year, fd.month)
            rec = recetas_por_id.get(d['receta_id'])
            if not rec:
                continue
            total_dia = d.get('comensales_total', params['com_social'] + params['com_afiliado'] + params['com_normal'])
            for ing_id, g_racion in (rec.get('detalle_gramos_racion') or {}).items():
                if ing_id in stock_rem_por_mes.get(clave_mes, {}):
                    consumo_por_mes.setdefault(clave_mes, {}).setdefault(ing_id, 0.0)
                    consumo_por_mes[clave_mes][ing_id] += g_racion * total_dia
        agotados_ids = set()
        for clave_mes, cons in consumo_por_mes.items():
            rem = stock_rem_por_mes.get(clave_mes, {})
            for ing_id, g in cons.items():
                if g > rem.get(ing_id, 0.0):
                    agotados_ids.add(ing_id)
        agotados_nombres = []
        if agotados_ids:
            cur.execute("SELECT nombre FROM ingredientes WHERE id = ANY(%s);", (sorted(agotados_ids),))
            agotados_nombres = [f['nombre'] for f in cur.fetchall()]
        ahorro_subsidio_semana = round(
            sum(d.get('ahorro_subsidio', 0.0) * d.get('comensales_total', 1) for d in menu), 2)
        margen_semana_pct = round(((recoleccion_total - costo_total) / costo_total) * 100, 2) \
            if costo_total else None
        cumple_margen = bool(margen_semana_pct is not None and
                             margen_semana_pct >= margen_objetivo * 100)
        # COM-71 (D4): auditoría de holgura diaria
        dias_flex_excedido = sum(1 for d in menu if d.get('flex_excedido'))
        stock_rem_usado = any(bool(costos_por_dia[d].get('stock_remanente_aplicado')) for d in dias)
        # COM-61 (HU-11): auditoría de variedad entre semanas de la variante
        repeticiones = [
            {
                'dia_nombre': d['dia_nombre'],
                'receta_id': d['receta_id'],
                'receta_nombre': d['receta_nombre'],
                'inevitable': bool(d.get('repeticion_inevitable', False)),
            }
            for d in menu if d.get('repite_semana_anterior')
        ]
        variedad_pct = round(100.0 * (len(menu) - len(repeticiones)) / len(menu), 1) if menu else 100.0
        # COM-74: auditoría de fuente de comensales
        dias_con_ia = sum(1 for d in menu if d.get('fuente_comensales') == 'prediccion_ia')
        total_comensales_prom = round(sum(d.get('comensales_total', 0) for d in menu) / max(len(menu), 1), 1)
        resumen = {
            'costo_total_semana': costo_total,
            'costo_racion_promedio': round(costo_total / max(sum(d.get('comensales_total', 0) for d in menu), 1), 2),
            'calorias_promedio_dia': round(sum(d['energia_kcal'] for d in menu) / max(len(menu), 1), 2),
            'hierro_promedio_dia': round(sum(d['hierro_mg'] for d in menu) / max(len(menu), 1), 2),
            'proteina_promedio_dia': round(sum(d['proteina_g'] for d in menu) / max(len(menu), 1), 2),
            'top_ingredientes': _top_ingredientes(menu, recetas_por_id, n=3),
            'presupuesto_semanal': presupuesto_semanal,
            'dias_seleccionados': dias,
            # COM-74: clave conservada; ahora es el promedio real proyectado (con cocineras)
            'total_comensales_dia': total_comensales_prom,
            'dias_con_prediccion_ia': dias_con_ia,
            'recoleccion_total_semana': recoleccion_total,
            'margen_proyectado': round(recoleccion_total - costo_total, 2),
            'dentro_de_presupuesto': not sobrepaso and costo_total <= presupuesto_semanal,
            'n_dias': len(menu),
            # COM-59A: bloque de autogestión (subsidio + margen semanal)
            'costo_semana_sin_subsidio': round(costo_total + ahorro_subsidio_semana, 2),
            'ahorro_subsidio_semana': ahorro_subsidio_semana,
            'subsidio_agotado_semana': agotados_nombres,
            'margen_semanal_pct': margen_semana_pct,
            'margen_semanal_objetivo_pct': round(margen_objetivo * 100, 2),
            'cumple_margen_semanal': cumple_margen,
            'alerta_margen': None if cumple_margen else (
                f"El margen semanal proyectado ({margen_semana_pct}%) está por debajo del "
                f"objetivo ({margen_objetivo * 100:.0f}%). Revise precios de venta, el subsidio "
                f"del mes o aplique las sugerencias de ahorro del reporte."),
            # COM-60: auditoría de prioridad Anemia Cero
            'dias_anti_anemia': conteo_anemia,
            'cuota_anti_anemia': params['cuota_feo'],
            'cumple_cuota_anemia': bool(conteo_anemia >= params['cuota_feo']),
            # COM-71: auditoría de holgura diaria y stock remanente
            'flex_dia': params['flex_dia'],
            'dias_con_flex_excedido': dias_flex_excedido,
            'stock_remanente_usado': stock_rem_usado,
            'recetas_no_costeables_omitidas': len(no_costeables),
            # COM-61 (HU-11): indicador de variedad entre semanas (criterio D7: JSONB)
            'semana_anterior_fecha': fecha_previa.isoformat() if fecha_previa else None,
            'n_recetas_semana_anterior': len(recetas_previas),
            'repeticiones_semana_anterior': repeticiones,
            'variedad_pct': variedad_pct,
            'permitir_repetidos': bool(permitir_repetidos),
        }
        cur.execute("""
            INSERT INTO planificaciones_candidatas
                (comedor_id, sesion_id, variante, etiqueta, descripcion,
                 ponderacion, resumen, menu, creado_por_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (comedor_id, sesion_id, codigo, meta['etiqueta'], meta['descripcion'],
              json.dumps(pesos), json.dumps(resumen), json.dumps(menu), creado_por_id))
        candidata_id = cur.fetchone()['id']
        propuestas.append({
            'candidata_id': candidata_id,
            'variante': codigo,
            'etiqueta': meta['etiqueta'],
            'descripcion': meta['descripcion'],
            'ponderacion': pesos,
            'resumen': resumen,
            'menu': menu,
        })
    detalle_no_costeables = [
        {
            'receta_id': r['receta_id'],
            'nombre': r['nombre'],
            'ingredientes_sin_precio': r.get('ingredientes_sin_precio', []),
        }
        for r in no_costeables
    ]
    return {
        'sesion_id': sesion_id,
        'comedor_id': comedor_id,
        'semana_inicio': fecha_inicio.isoformat(),
        'dias_seleccionados': dias,
        'modelo_kmeans_id': modelo_id,
        'seed': seed,
        'propuestas': propuestas,
        'recetas_con_precio_completo': len(seleccionables) + len(excluidas_reglas),
        # COM-71: clave nueva + clave legacy conservada con el mismo contenido
        'recetas_no_costeables': detalle_no_costeables,
        'recetas_excluidas_precio_incompleto': detalle_no_costeables,
        'recetas_excluidas_reglas_proteina': excluidas_reglas,
        # COM-61 (HU-11): contexto de variedad para la UI (checkbox y badges)
        'semana_anterior': {
            'fecha_referencia': fecha_previa.isoformat() if fecha_previa else None,
            'receta_ids': sorted(recetas_previas),
        },
        'permitir_repetidos': bool(permitir_repetidos),
        # COM-74: proyección de comensales usada (transparencia para la UI)
        'comensales_por_dia': comensales_por_dia,
    }


# ==========================================
# CONSULTAS DE APOYO PARA EL ROUTER
# ==========================================
def obtener_candidatas_sesion(cur, sesion_id: str):
    """Recupera las 3 propuestas persistidas de una sesión de generación."""
    cur.execute("""
        SELECT id, variante, etiqueta, descripcion, ponderacion, resumen, menu,
               estado, fecha
        FROM planificaciones_candidatas
        WHERE sesion_id = %s
        ORDER BY id;
    """, (sesion_id,))
    return cur.fetchall()


def obtener_candidata(cur, candidata_id: int):
    """Recupera una propuesta individual por id (para el paso de selección)."""
    cur.execute("""
        SELECT id, comedor_id, sesion_id, variante, etiqueta, descripcion,
               ponderacion, resumen, menu, estado, creado_por_id, fecha
        FROM planificaciones_candidatas
        WHERE id = %s;
    """, (candidata_id,))
    return cur.fetchone()