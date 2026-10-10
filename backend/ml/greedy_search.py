"""
ml/greedy_search.py
Objetivo: Motor de búsqueda heurística (Greedy Search) del ticket COM-8. Genera 3
          propuestas de menú semanal (NutriMax, EconoMax, BalanceMax) combinando valor
          nutricional y precio, respetando la rotación de clusters K-means (COM-5),
          la variedad de platos y el presupuesto del comedor.
Historial:
 - COM-8 v1/v2/v3: días seleccionables, top-3 por categorías, FIX de formatos legacy.
 - COM-37 v2: regla de PRECIOS COMPLETOS para el flujo del comedor.
 - COM-37 v4/v5: validación de reglas de proteína VIGENTES (R1/R2 de K-means); costeo
   sobre precios_insumos.py con equivalencias uso->gramos.
 - COM-37 v7: la predicción RF cuenta como fuente de precio válida para completitud;
   fallback_ultima_fecha para días sin corrida del scraper.
 - COM-47 v3: la nutrición de recetas_almuerzo YA ESTÁ POR RACIÓN; se usa SIN dividir.
   La división entre raciones aplica SOLO a cantidades de ingredientes y al costo.
 - COM-50 v3: costeo sin fallback legacy (fuentes modernas) y aislamiento por receta.
 - COM-59A (este archivo): modelo de negocio autogestionado:
     * Precios de venta de la recolección proyectada vía subsidio_motor.precio_venta_vigente
       (precio único vigente con historial); los parámetros PRECIO_* quedan solo como
       fallback interno del helper.
     * _costear_recetas conserva el detalle de líneas y aplica costo_con_subsidio():
       costo_racion = costo REAL post-subsidio; costo_racion_bruto y
       ahorro_subsidio_racion quedan para auditoría y UI.
     * Por variante: auditoría SEMANAL del subsidio (consumo proyectado vs stock del
       mes -> subsidio_agotado_semana) y validación del MARGEN SEMANAL OBJETIVO
       (margen_semanal_pct / cumple_margen_semanal / alerta_margen en el resumen).
Uso: Importado por routers/propuestas_menu.py. Todas las funciones reciben un cursor
     psycopg2 (RealDictCursor); el caller gestiona la transacción.
Referencia: tickets COM-8 / COM-37 / COM-47 / COM-50 / COM-59 (solo trazabilidad).
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
# COM-59A: precios de venta vigentes, subsidio del mes y margen semanal objetivo
from subsidio_motor import (
    costo_con_subsidio,
    precio_venta_vigente,
    margen_semanal_objetivo,
    subsidio_gramos_del_mes,
)

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
def _cargar_parametros(cur) -> dict:
    """
    Lee los parámetros COM-8 y los comensales por tipo.
    COM-59A: los PRECIOS DE VENTA ya no se leen de los parámetros fijos PRECIO_*:
    se resuelven con precio_venta_vigente() (tabla precios_venta, precio único
    vigente con historial; los parámetros quedan como fallback interno del helper).
    """
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave LIKE 'PLANIFICACION_%';
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
    }


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
    Retorna (recetas, modelo_id).
    """
    cur.execute("SELECT id FROM kmeans_modelos WHERE activo = TRUE ORDER BY id DESC LIMIT 1;")
    fila = cur.fetchone()
    if not fila:
        return [], None
    modelo_id = fila['id']
    cur.execute("""
        SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
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
            'raciones': float(r['raciones']),
            'hierro_mg': float(r['hierro_mg'] or 0),
            'proteina_g': float(r['proteina_g'] or 0),
            'energia_kcal': float(r['energia_kcal'] or 0),
            'costo_racion': 0.0,            # se completa en _costear_recetas (REAL post-subsidio)
            'costo_racion_bruto': 0.0,      # COM-59A: costo sin subsidio (auditoría)
            'ahorro_subsidio_racion': 0.0,  # COM-59A: ahorro por ración por subsidio
            'precio_completo': False,       # COM-37 v2: se completa en _costear_recetas
            'ingredientes_sin_precio': [],  # COM-37 v2: auditoría de faltantes
            'ingredientes': [],             # lista de dicts {nombre, categoria}
        })
    return recetas, modelo_id


def _costear_recetas(cur, recetas, fecha: date, comedor_id=None):
    """
    COM-37 v5/v7 + COM-47 v3 + COM-59A: calcula el costo POR RACIÓN de cada receta:
    gramos de la unidad de USO de cada línea (equivalencia o conversión estándar) ×
    precio por gramo de la MEJOR opción del ingrediente, sumado para la preparación
    completa y dividido entre raciones (única división permitida).
    COM-59A: conserva el detalle de líneas (gramos y costo) y, si se indica
    comedor_id, aplica costo_con_subsidio(): `costo_racion` queda como el costo REAL
    post-subsidio (los víveres del mes ya los pagó el municipio), `costo_racion_bruto`
    es el costo de mercado y `ahorro_subsidio_racion` la diferencia. También expone
    `detalle_gramos_racion` (gramos por ración por ingrediente) para la auditoría
    semanal del stock subvencionado.
    """
    ids = [r['receta_id'] for r in recetas]
    if not ids:
        return
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
    lineas_detalle = {}   # COM-59A: detalle de líneas por receta
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
            # COM-59A: descuento de los víveres subvencionados del mes calendario
            res_sub = costo_con_subsidio(cur, comedor_id, fecha, lineas)
            real_racion = res_sub['costo_total'] / raciones
            ahorro_racion = bruto_racion - real_racion
            n_subv = sum(1 for l in res_sub['detalle'] if l.get('subvencionado'))
        r['costo_racion_bruto'] = round(bruto_racion, 2)
        r['costo_racion'] = round(real_racion, 2)   # REAL post-subsidio (uso downstream)
        r['ahorro_subsidio_racion'] = round(ahorro_racion, 2)
        r['lineas_subvencionadas'] = n_subv
        # COM-59A: gramos por ración por ingrediente (auditoría semanal del stock)
        r['detalle_gramos_racion'] = {
            l['ingrediente_id']: (l['gramos_totales'] / raciones) for l in lineas
        }
        r['ingredientes'] = nombres_acum.get(rid, [])
        tot = lineas_tot.get(rid, 0)
        conp = lineas_con_precio.get(rid, 0)
        r['precio_completo'] = (tot > 0 and conp == tot)
        r['ingredientes_sin_precio'] = sorted(set(sin_precio_nom.get(rid, [])))


# ==========================================
# COM-37 v4/v5: VALIDACIÓN DE REGLAS DE PROTEÍNA VIGENTES (R1/R2)
# ==========================================
def _validar_reglas_proteinas_vigentes(cur, recetas):
    """
    COM-37 v4/v5: aplica las listas CONFIGURABLES de proteínas permitidas (R1) e
    ingredientes vetados (R2) vigentes en parametros_sistema (las mismas que usa
    K-means) sobre las recetas candidatas del modelo activo. Retorna (validas, excluidas).
    """
    re_permitida, re_vetada, _, _ = cargar_reglas_proteinas(cur)
    validas = []
    excluidas = []
    for r in recetas:
        tiene_permitida = False
        tiene_vetada = False
        for ing in r['ingredientes']:
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
# SCORING GREEDY
# ==========================================
def _score(rec, pesos, mm, usada: bool) -> float:
    """
    Score lineal ponderado POR RACIÓN: hierro/proteína/energía suman, precio resta.
    El peso 'variedad' bonifica recetas aún no usadas en la semana.
    COM-59A: el precio que usa es el costo REAL post-subsidio (campo costo_racion).
    """
    s = (pesos.get('hierro', 0) * _z(rec['hierro_mg'], *mm['hierro']) +
         pesos.get('proteina', 0) * _z(rec['proteina_g'], *mm['proteina']) +
         pesos.get('energia', 0) * _z(rec['energia_kcal'], *mm['energia']) -
         pesos.get('precio', 0) * _z(rec['costo_racion'], *mm['precio']))
    if not usada:
        s += pesos.get('variedad', 0)
    return s


def _generar_menu_variante(recetas_por_cluster, todas, pesos, params,
                           presupuesto_semanal, fecha_inicio, dias):
    """
    COM-8 v2: Greedy por DÍA SELECCIONADO: elige la receta de mayor score del cluster
    objetivo de la rotación (fallback: todas), sin repetir platos mientras haya
    alternativas y respetando el presupuesto acumulado (con tolerancia del 5%).
    COM-59A: los costos diarios usan el costo REAL post-subsidio y la recolección
    proyectada usa los precios de venta vigentes (precio_venta_vigente).
    """
    mm = _minmax(todas)
    usadas = set()
    menu = []
    acumulado = 0.0
    sobrepaso = False
    total_comensales = params['com_social'] + params['com_afiliado'] + params['com_normal']
    recoleccion_dia = (params['com_social'] * params['precio_social'] +
                       params['com_afiliado'] * params['precio_afiliado'] +
                       params['com_normal'] * params['precio_normal'])
    limite = presupuesto_semanal * TOLERANCIA_PRESUPUESTO

    for d in dias:
        cluster_obj = params['rotacion'][(d - 1) % len(params['rotacion'])]
        candidatas = list(recetas_por_cluster.get(cluster_obj, [])) or list(todas)

        candidatas.sort(key=lambda r: (_score(r, pesos, mm, r['receta_id'] in usadas),
                                       r['receta_id'] not in usadas), reverse=True)

        elegida = None
        for r in candidatas:
            if r['receta_id'] in usadas and any(
                    c['receta_id'] not in usadas for c in candidatas):
                continue  # hay alternativas sin usar: evita repetir
            costo_dia = r['costo_racion'] * total_comensales
            if acumulado + costo_dia <= limite:
                elegida = r
                break
        if elegida is None:
            elegida = min(candidatas, key=lambda r: r['costo_racion'])
            if acumulado + elegida['costo_racion'] * total_comensales > limite:
                sobrepaso = True

        costo_dia = round(elegida['costo_racion'] * total_comensales, 2)
        acumulado += costo_dia
        usadas.add(elegida['receta_id'])
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
            'costo_total_dia': costo_dia,
            'energia_kcal': round(elegida['energia_kcal'], 2),
            'proteina_g': round(elegida['proteina_g'], 2),
            'hierro_mg': round(elegida['hierro_mg'], 2),
            'recoleccion_proyectada': round(recoleccion_dia, 2),
        })
    return menu, sobrepaso


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
                            seed: int = 0, dias_semana: list = None):
    """
    COM-8 v2/v3 + COM-37 + COM-47 v3 + COM-50 v3 + COM-59A: Genera y persiste las 3
    propuestas de menú semanal para los DÍAS DE COCINA indicados, usando SOLO recetas
    con precios completos y reglas de proteína vigentes.
    COM-59A: el costeo es con costo REAL post-subsidio del mes calendario del comedor;
    cada propuesta incluye en su resumen la auditoría semanal del subsidio (consumo
    proyectado vs stock del mes) y la validación del MARGEN SEMANAL OBJETIVO
    (recolección a precios vigentes vs costo real), con alerta si no se cumple.
    """
    if presupuesto_semanal is None or float(presupuesto_semanal) <= 0:
        raise ValueError("El presupuesto semanal debe ser mayor a cero.")
    presupuesto_semanal = float(presupuesto_semanal)
    fecha_referencia = fecha_referencia or date.today()

    dias = sorted(set(int(d) for d in (dias_semana or DIAS_DEFAULT)))
    if not dias or any(d < 1 or d > 7 for d in dias):
        raise ValueError("Los días de cocina deben estar entre 1 (Lunes) y 7 (Domingo).")

    params = _cargar_parametros(cur)
    recetas, modelo_id = _cargar_recetas_cluster(cur)
    if not recetas:
        raise ValueError(
            "No hay un modelo K-means activo con recetas aptas. Entrene el modelo en "
            "la pestaña 'Clusters K-Means' antes de generar propuestas de menú.")

    # COM-59A: costeo con costo real post-subsidio del comedor solicitante
    _costear_recetas(cur, recetas, fecha_referencia, comedor_id)

    excluidas_incompletas = [r for r in recetas if not r.get('precio_completo', False)]
    recetas = [r for r in recetas if r.get('precio_completo', False) and r['costo_racion'] > 0]

    recetas, excluidas_reglas = _validar_reglas_proteinas_vigentes(cur, recetas)

    if len(recetas) < len(dias):
        detalle_precios = "; ".join(
            f"{r['nombre']} (sin precio: {', '.join(r['ingredientes_sin_precio'][:4])})"
            for r in excluidas_incompletas[:5]
        )
        detalle_reglas = "; ".join(
            f"{e['nombre']} ({'/'.join(e['detalle'])})" for e in excluidas_reglas[:5]
        )
        raise ValueError(
            f"Solo hay {len(recetas)} recetas con precios completos y reglas de proteína "
            f"vigentes; se requieren al menos {len(dias)} para cubrir los días seleccionados. "
            f"Excluidas por precio incompleto: {detalle_precios or 'ninguna'}. "
            f"Excluidas por reglas de proteína vigentes: {detalle_reglas or 'ninguna'}. "
            f"Cargue precios manuales en Gestión de Ingredientes (COM-37), revise "
            f"las listas R1/R2 en Clusters K-Means o espere la corrida del scraper.")

    recetas_por_cluster = {}
    for r in recetas:
        recetas_por_cluster.setdefault(r['cluster_codigo'], []).append(r)
    recetas_por_id = {r['receta_id']: r for r in recetas}

    fecha_inicio = _lunes_de(fecha_referencia)
    marca = f"{comedor_id}|{fecha_inicio.isoformat()}|{creado_por_id}|{seed}|{'-'.join(map(str, dias))}"
    sesion_id = hashlib.sha256(marca.encode()).hexdigest()[:32]

    total_comensales = params['com_social'] + params['com_afiliado'] + params['com_normal']

    # COM-59A: stock subvencionado del mes y margen objetivo (una lectura por corrida)
    stock_mes = subsidio_gramos_del_mes(cur, comedor_id, fecha_referencia.year, fecha_referencia.month)
    margen_objetivo = margen_semanal_objetivo(cur)

    propuestas = []
    for idx, (codigo, meta) in enumerate(VARIANTES.items()):
        pesos = _jitter_weights(params['ponderaciones'].get(codigo, {}), seed, idx)
        menu, sobrepaso = _generar_menu_variante(
            recetas_por_cluster, recetas, pesos, params,
            presupuesto_semanal, fecha_inicio, dias)

        costo_total = round(sum(d['costo_total_dia'] for d in menu), 2)
        recoleccion_total = round(sum(d['recoleccion_proyectada'] for d in menu), 2)

        # ---- COM-59A: auditoría semanal del subsidio y del margen objetivo ----
        consumo_semana = {}
        for d in menu:
            rec = recetas_por_id.get(d['receta_id'])
            if not rec:
                continue
            for ing_id, g_racion in (rec.get('detalle_gramos_racion') or {}).items():
                if ing_id in stock_mes:
                    consumo_semana[ing_id] = consumo_semana.get(ing_id, 0.0) + g_racion * total_comensales
        agotados_ids = [i for i, g in consumo_semana.items() if g > stock_mes.get(i, 0.0)]
        agotados_nombres = []
        if agotados_ids:
            cur.execute("SELECT nombre FROM ingredientes WHERE id = ANY(%s);", (agotados_ids,))
            agotados_nombres = [f['nombre'] for f in cur.fetchall()]
        ahorro_subsidio_semana = round(
            sum(d.get('ahorro_subsidio', 0.0) * total_comensales for d in menu), 2)
        margen_semana_pct = round(((recoleccion_total - costo_total) / costo_total) * 100, 2) \
            if costo_total else None
        cumple_margen = bool(margen_semana_pct is not None and
                             margen_semana_pct >= margen_objetivo * 100)

        resumen = {
            'costo_total_semana': costo_total,
            'costo_racion_promedio': round(costo_total / max(total_comensales * len(menu), 1), 2),
            'calorias_promedio_dia': round(sum(d['energia_kcal'] for d in menu) / max(len(menu), 1), 2),
            'hierro_promedio_dia': round(sum(d['hierro_mg'] for d in menu) / max(len(menu), 1), 2),
            'proteina_promedio_dia': round(sum(d['proteina_g'] for d in menu) / max(len(menu), 1), 2),
            'top_ingredientes': _top_ingredientes(menu, recetas_por_id, n=3),
            'presupuesto_semanal': presupuesto_semanal,
            'dias_seleccionados': dias,
            'total_comensales_dia': total_comensales,
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

    return {
        'sesion_id': sesion_id,
        'comedor_id': comedor_id,
        'semana_inicio': fecha_inicio.isoformat(),
        'dias_seleccionados': dias,
        'modelo_kmeans_id': modelo_id,
        'seed': seed,
        'propuestas': propuestas,
        'recetas_con_precio_completo': len(recetas) + len(excluidas_reglas),
        'recetas_excluidas_precio_incompleto': [
            {
                'receta_id': r['receta_id'],
                'nombre': r['nombre'],
                'ingredientes_sin_precio': r.get('ingredientes_sin_precio', []),
            }
            for r in excluidas_incompletas
        ],
        'recetas_excluidas_reglas_proteina': excluidas_reglas,
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