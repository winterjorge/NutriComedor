"""
ml/greedy_search.py
Objetivo: Motor de búsqueda heurística (Greedy Search) del ticket COM-8. Genera 3
          propuestas de menú semanal (NutriMax, EconoMax, BalanceMax) combinando valor
          nutricional y precio, respetando la rotación de clusters K-means (COM-5),
          la variedad de platos y el presupuesto del comedor.
Historial:
 - COM-8 v1/v2/v3: días seleccionables, top-3 por categorías, FIX de formatos legacy.
 - COM-37 v2: regla de PRECIOS COMPLETOS: solo recetas con todos sus ingredientes
   priceados alimentan propuestas/planificación; excluidas reportadas en el payload.
 - COM-37 v4 (concepto conservado): validación de reglas de proteína VIGENTES (R1/R2
   configuradas en K-means) sobre las recetas recomendadas, aunque el modelo no se haya
   re-entrenado tras editarlas; excluidas reportadas como
   `recetas_excluidas_reglas_proteina`.
 - COM-37 v5 (este archivo): costeo reescrito sobre precios_insumos.py con el modelo de
   DOS CONCEPTOS: gramos de la unidad de USO vía ingredientes_equivalencias (o
   conversión estándar) × precio por gramo del MEJOR insumo (scraper día > manual
   insumo > legacy ingrediente). El bloque _precios_por_gramo anterior queda COMENTADO.
Entradas:
  - Nutrición por receta: columnas hierro_mg / proteina_g / energia_kcal de
    recetas_almuerzo (valores de la receta completa), divididas entre raciones.
  - Costo por gramo: precios_insumos (mejor opción por ingrediente a la fecha de hoy).
  - Clusters: recetas_clusters del modelo K-means activo (COM-5).
  - Parámetros: PLANIFICACION_* (ponderaciones, rotación, comensales) y
    PRECIO_SOCIAL/AFILIADO/NORMAL para la recolección proyectada.
Uso: Importado por routers/propuestas_menu.py. Todas las funciones reciben un cursor
     psycopg2 (RealDictCursor); el caller gestiona la transacción.
Referencia: tickets COM-8 / COM-37 (solo trazabilidad).
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
)

# COM-37 v4/v5: reglas de proteína VIGENTES y normalizador, compartidos con K-means
# para garantizar que Greedy y el clustering evalúen las mismas restricciones.
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
        'descripcion': 'Balance óptimo entre nutrición y costo.',
        'etiqueta': '⚖️ BalanceMax',
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
    """Lee los parámetros COM-8 y los precios por tipo de comensal."""
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave LIKE 'PLANIFICACION_%' OR clave IN
              ('PRECIO_SOCIAL', 'PRECIO_AFILIADO', 'PRECIO_NORMAL');
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
        'precio_social': float(p.get('PRECIO_SOCIAL', 0)),
        'precio_afiliado': float(p.get('PRECIO_AFILIADO', 3)),
        'precio_normal': float(p.get('PRECIO_NORMAL', 5)),
    }


# =========================================================================
# COM-37 v5 (trazabilidad): _precios_por_gramo COMENTADO. Mapeaba el último día de
# historial_precios por ingrediente y completaba con manuales legacy. Reemplazado por
# precios_insumos.mejor_opcion_ingrediente + equivalencias de unidad de USO.
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


def _cargar_recetas_cluster(cur):
    """
    Recetas del modelo K-means activo con nutrición POR RACIÓN (columnas de
    recetas_almuerzo divididas entre raciones). Retorna (recetas, modelo_id).
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
        rac = float(r['raciones'])
        recetas.append({
            'receta_id': r['receta_id'],
            'nombre': r['nombre'],
            'cluster_codigo': r['cluster_codigo'],
            'cluster_etiqueta': r['cluster_etiqueta'],
            'raciones': rac,
            'hierro_mg': float(r['hierro_mg'] or 0) / rac,
            'proteina_g': float(r['proteina_g'] or 0) / rac,
            'energia_kcal': float(r['energia_kcal'] or 0) / rac,
            'costo_racion': 0.0,            # se completa en _costear_recetas
            'precio_completo': False,       # COM-37 v2: se completa en _costear_recetas
            'ingredientes_sin_precio': [],  # COM-37 v2: auditoría de faltantes
            'ingredientes': [],             # lista de dicts {nombre, categoria}
        })
    return recetas, modelo_id


def _costear_recetas(cur, recetas, fecha: date):
    """
    COM-37 v5: calcula el costo por ración de cada receta con el modelo de DOS
    CONCEPTOS: por línea, gramos de la unidad de USO (equivalencia del insumo elegido
    o conversión estándar) × precio por gramo del MEJOR insumo del ingrediente
    (scraper día > manual insumo > legacy ingrediente). Deja los ingredientes
    NORMALIZADOS como dicts {nombre, categoria} y marca precio_completo /
    ingredientes_sin_precio para la regla del flujo del comedor.
    """
    ids = [r['receta_id'] for r in recetas]
    if not ids:
        return
    precios_insumo = precios_por_gramo_por_insumo(cur, fecha)
    eq_map = _cargar_equivalencias(cur)
    opciones_cache = {}

    def _opcion(ing_id):
        if ing_id not in opciones_cache:
            opciones_cache[ing_id] = mejor_opcion_ingrediente(cur, ing_id, fecha, precios_insumo)
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
    for fila in cur.fetchall():
        rid = fila['receta_id']
        lineas_tot[rid] = lineas_tot.get(rid, 0) + 1
        opc = _opcion(fila['ingrediente_id'])
        if opc is None:
            sin_precio_nom.setdefault(rid, []).append(fila['ing_nombre'])
        else:
            g = eq_map.get((fila['ingrediente_id'], opc['insumo_id'], fila['unidad_uso_id']))
            if g is None:
                g = gramos_por_unidad_estandar(
                    fila['unidad_abrev'], fila['tipo_magnitud'],
                    fila['factor_a_base'], fila['peso_estimado_g'])
            gramos = g * float(fila['cantidad_requerida'])
            costo_acum[rid] = costo_acum.get(rid, 0.0) + gramos * opc['ppg']
            lineas_con_precio[rid] = lineas_con_precio.get(rid, 0) + 1
        nombres_acum.setdefault(rid, []).append({
            'nombre': fila['ing_nombre'],
            'categoria': fila['categoria'] or '',
        })

    for r in recetas:
        total = costo_acum.get(r['receta_id'], 0.0)
        r['costo_racion'] = round(total / r['raciones'], 2)
        r['ingredientes'] = nombres_acum.get(r['receta_id'], [])
        tot = lineas_tot.get(r['receta_id'], 0)
        conp = lineas_con_precio.get(r['receta_id'], 0)
        r['precio_completo'] = (tot > 0 and conp == tot)
        r['ingredientes_sin_precio'] = sorted(set(sin_precio_nom.get(r['receta_id'], [])))


# ==========================================
# COM-37 v4/v5: VALIDACIÓN DE REGLAS DE PROTEÍNA VIGENTES (R1/R2)
# ==========================================
def _validar_reglas_proteinas_vigentes(cur, recetas):
    """
    COM-37 v4/v5: aplica las listas CONFIGURABLES de proteínas permitidas (R1) e
    ingredientes vetados (R2) vigentes en parametros_sistema (las mismas que usa
    K-means) sobre las recetas candidatas del modelo activo. Replica la lógica de
    ml/kmeans_recetas.construir_dataset: por ingrediente, permitida primero; veto solo
    si no es permitida (así 'hígado de res' pasa: 'higado' es permitida y se evalúa
    antes que el veto 'res'). Retorna (validas, excluidas).
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
    Score lineal ponderado: hierro/proteína/energía suman, precio resta.
    El peso 'variedad' bonifica recetas aún no usadas en la semana.
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
            'costo_total_dia': costo_dia,
            'energia_kcal': round(elegida['energia_kcal'], 2),
            'proteina_g': round(elegida['proteina_g'], 2),
            'hierro_mg': round(elegida['hierro_mg'], 2),
            'recoleccion_proyectada': round(recoleccion_dia, 2),
        })
    return menu, sobrepaso


def _top_ingredientes(menu, ingredientes_por_id, n=3):
    """
    COM-8 v3: Top N ingredientes más usados en la semana, SOLO de las categorías
    Vegetales y Hortalizas / Frutas / Proteínas. Tolerante a formatos legacy: si un
    elemento no es un dict {nombre, categoria}, se omite en lugar de fallar.
    """
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
    COM-8 v2/v3 + COM-37 v2/v4/v5: Genera y persiste las 3 propuestas de menú semanal
    (NUTRI, ECONO, BALANCE) para los DÍAS DE COCINA indicados, usando SOLO recetas que
    cumplan, en este orden:
      1) nutrición cargada (energía no nula),
      2) precios COMPLETOS de todos sus ingredientes (scraper/manual insumo/legacy),
      3) reglas de proteína VIGENTES R1/R2 configuradas en K-means (COM-37 v4/v5).
    Retorna el payload completo, incluyendo las recetas excluidas por precio incompleto
    y por reglas de proteína vigentes (transparencia para UI y sustentación).
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

    # COM-37 v5: costeo con equivalencias uso->gramos y mejor insumo por ingrediente
    _costear_recetas(cur, recetas, fecha_referencia)

    # COM-37 v2 (trazabilidad): filtro anterior COMENTADO (solo costo>0, permitía
    # recetas con costo parcial y precios subestimados):
    # recetas = [r for r in recetas if r['costo_racion'] > 0]
    # COM-37 v2: SOLO recetas con precios COMPLETOS alimentan el flujo del comedor
    excluidas_incompletas = [r for r in recetas if not r.get('precio_completo', False)]
    recetas = [r for r in recetas if r.get('precio_completo', False) and r['costo_racion'] > 0]

    # COM-37 v4/v5: validación de reglas de proteína VIGENTES (R1/R2 de K-means)
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
            f"Cargue precios/insumos manuales en Gestión de Ingredientes (COM-37), revise "
            f"las listas R1/R2 en Clusters K-Means o espere la corrida del scraper.")

    recetas_por_cluster = {}
    for r in recetas:
        recetas_por_cluster.setdefault(r['cluster_codigo'], []).append(r)
    recetas_por_id = {r['receta_id']: r for r in recetas}

    fecha_inicio = _lunes_de(fecha_referencia)
    marca = f"{comedor_id}|{fecha_inicio.isoformat()}|{creado_por_id}|{seed}|{'-'.join(map(str, dias))}"
    sesion_id = hashlib.sha256(marca.encode()).hexdigest()[:32]

    total_comensales = params['com_social'] + params['com_afiliado'] + params['com_normal']
    propuestas = []
    for idx, (codigo, meta) in enumerate(VARIANTES.items()):
        pesos = _jitter_weights(params['ponderaciones'].get(codigo, {}), seed, idx)
        menu, sobrepaso = _generar_menu_variante(
            recetas_por_cluster, recetas, pesos, params,
            presupuesto_semanal, fecha_inicio, dias)

        costo_total = round(sum(d['costo_total_dia'] for d in menu), 2)
        recoleccion_total = round(sum(d['recoleccion_proyectada'] for d in menu), 2)
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
        # COM-37 v2: transparencia de la regla de precios completos
        'recetas_con_precio_completo': len(recetas) + len(excluidas_reglas),
        'recetas_excluidas_precio_incompleto': [
            {
                'receta_id': r['receta_id'],
                'nombre': r['nombre'],
                'ingredientes_sin_precio': r.get('ingredientes_sin_precio', []),
            }
            for r in excluidas_incompletas
        ],
        # COM-37 v4/v5: transparencia de la validación de reglas de proteína vigentes
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