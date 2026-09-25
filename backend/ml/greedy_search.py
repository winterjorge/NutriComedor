"""
ml/greedy_search.py
Objetivo: Motor de búsqueda heurística (Greedy Search) del ticket COM-8. Genera 3
          propuestas de menú semanal (NutriMax, EconoMax, BalanceMax) combinando valor
          nutricional y precio, respetando la rotación de clusters K-means (COM-5),
          la variedad de platos y el presupuesto semanal del comedor.
Entradas:
  - Nutrición por receta: columnas hierro_mg / proteina_g / energia_kcal de
    recetas_almuerzo (valores de la receta completa), divididas entre raciones.
  - Costo real por gramo: insumos -> historial_precios (última fecha disponible,
    mínimo entre insumos del mismo ingrediente), convertido a gramos con
    unidades_medida.factor_a_base (masa/volumen) o ingredientes.peso_estimado_g
    (unidades discretas).
  - Clusters: recetas_clusters del modelo K-means activo (COM-5).
  - Parámetros: PLANIFICACION_* de parametros_sistema (ponderaciones, rotación,
    comensales por tipo) y PRECIO_SOCIAL/AFILIADO/NORMAL para la recolección.
Salida: 3 menús de 7 días persistidos en planificaciones_candidatas (misma sesion_id),
        con resumen de costo total, calorías promedio/día y top 3 de ingredientes.
Jitter: el parámetro `seed` desplaza ligeramente las ponderaciones para que el botón
        "Regenerar" produzca propuestas distintas sin cambiar la lógica del motor.
Uso: Importado por routers/propuestas_menu.py (Parte 3). Todas las funciones reciben
     un cursor psycopg2 (RealDictCursor); el caller gestiona la transacción.
Referencia: ticket COM-8 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
import json
import hashlib
from datetime import date, timedelta
from collections import Counter

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
    for i, (codigo, meta) in enumerate(VARIANTES.items()):
        try:
            base = json.loads(p.get(meta['parametro'], '{}'))
        except Exception:
            base = {}
        ponderaciones[codigo] = base
    return {
        'dias': int(float(p.get('PLANIFICACION_DIAS_SEMANA', 7))),
        'rotacion': json.loads(p.get('PLANIFICACION_ROTACION_CLUSTERS', '[1,2,4,1,3,2,4]')),
        'ponderaciones': ponderaciones,
        'com_social': int(float(p.get('PLANIFICACION_COMENSALES_SOCIAL', 22))),
        'com_afiliado': int(float(p.get('PLANIFICACION_COMENSALES_AFILIADO', 48))),
        'com_normal': int(float(p.get('PLANIFICACION_COMENSALES_NORMAL', 50))),
        'precio_social': float(p.get('PRECIO_SOCIAL', 0)),
        'precio_afiliado': float(p.get('PRECIO_AFILIADO', 3)),
        'precio_normal': float(p.get('PRECIO_NORMAL', 5)),
    }


def _precios_por_gramo(cur) -> dict:
    """
    {ingrediente_id: precio_por_gramo} con el último día de historial_precios.
    Convierte la unidad del insumo a gramos (factor_a_base para masa/volumen;
    peso_estimado_g del ingrediente para unidades discretas) y toma el MÍNIMO
    entre insumos del mismo ingrediente (criterio de compra económica).
    """
    cur.execute("""
        SELECT ins.ingrediente_id AS ing_id,
               MIN(
                 CASE WHEN um.tipo_magnitud = 'discreto'
                      THEN hp.precio_prom / GREATEST(ing.peso_estimado_g, 1)
                      ELSE hp.precio_prom / GREATEST(um.factor_a_base, 0.0001)
                 END
               ) AS precio_por_gramo
        FROM historial_precios hp
        JOIN insumos ins ON ins.id = hp.insumo_id
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE hp.fecha = (SELECT MAX(fecha) FROM historial_precios)
          AND hp.precio_prom IS NOT NULL AND hp.precio_prom > 0
        GROUP BY ins.ingrediente_id;
    """)
    return {r['ing_id']: float(r['precio_por_gramo']) for r in cur.fetchall()}


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
            'costo_racion': 0.0,   # se completa en _costear_recetas
            'ingredientes': [],    # nombres, para el top-3 semanal
        })
    return recetas, modelo_id


def _costear_recetas(cur, recetas, precios_gramo: dict):
    """
    Calcula el costo por ración de cada receta sumando sus ingredientes a precios
    reales por gramo, y recoge los nombres de ingredientes para el top-3.
    """
    ids = [r['receta_id'] for r in recetas]
    if not ids:
        return
    cur.execute("""
        SELECT ri.receta_id, ri.ingrediente_id, ri.cantidad_requerida,
               um.tipo_magnitud, um.factor_a_base,
               ing.peso_estimado_g, ing.nombre AS ing_nombre
        FROM receta_ingrediente ri
        JOIN unidades_medida um ON um.id = ri.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ri.ingrediente_id
        WHERE ri.receta_id = ANY(%s);
    """, (ids,))
    costo_acum = {}
    nombres_acum = {}
    for fila in cur.fetchall():
        if fila['tipo_magnitud'] in ('masa', 'volumen'):
            gramos = float(fila['cantidad_requerida']) * float(fila['factor_a_base'] or 1)
        else:
            gramos = float(fila['cantidad_requerida']) * float(fila['peso_estimado_g'] or 1)
        ppg = precios_gramo.get(fila['ingrediente_id'])
        if ppg is not None:
            costo_acum[fila['receta_id']] = costo_acum.get(fila['receta_id'], 0.0) + gramos * ppg
        nombres_acum.setdefault(fila['receta_id'], []).append(fila['ing_nombre'])
    for r in recetas:
        total = costo_acum.get(r['receta_id'], 0.0)
        r['costo_racion'] = round(total / r['raciones'], 2)
        r['ingredientes'] = nombres_acum.get(r['receta_id'], [])


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
                           presupuesto_semanal, fecha_inicio):
    """
    Greedy por día: elige la receta de mayor score del cluster objetivo de la
    rotación (fallback: todas), sin repetir platos mientras haya alternativas y
    respetando el presupuesto semanal acumulado (con tolerancia del 5%).
    Retorna (menu, sobrepaso_presupuesto).
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

    for d in range(params['dias']):
        cluster_obj = params['rotacion'][d % len(params['rotacion'])]
        candidatas = [r for r in recetas_por_cluster.get(cluster_obj, [])] or list(todas)

        # Ordena por score descendente; las no usadas primero (variedad)
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
            # Ninguna cabe en el presupuesto restante: la más barata disponible
            elegida = min(candidatas, key=lambda r: r['costo_racion'])
            acumulado_check = acumulado + elegida['costo_racion'] * total_comensales
            if acumulado_check > limite:
                sobrepaso = True

        costo_dia = round(elegida['costo_racion'] * total_comensales, 2)
        acumulado += costo_dia
        usadas.add(elegida['receta_id'])
        menu.append({
            'dia_semana': d + 1,
            'dia_nombre': DIAS_NOMBRE[d % 7],
            'fecha': (fecha_inicio + timedelta(days=d)).isoformat(),
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


def _top_ingredientes(menu, recetas_por_id, n=3):
    """Top N ingredientes más usados en la semana (por frecuencia en los 7 platos)."""
    contador = Counter()
    for dia in menu:
        for nombre in recetas_por_id[dia['receta_id']]['ingredientes']:
            contador[nombre.lower()] += 1
    top = []
    for nombre_min, _ in contador.most_common(n):
        original = next((nm for nm in recetas_por_id[menu[0]['receta_id']]['ingredientes']
                         if nm.lower() == nombre_min), nombre_min)
        # recupera el nombre original desde cualquier receta que lo contenga
        for rec in recetas_por_id.values():
            hit = next((nm for nm in rec['ingredientes'] if nm.lower() == nombre_min), None)
            if hit:
                original = hit
                break
        top.append(original)
    return top


# ==========================================
# API PÚBLICA DEL MOTOR
# ==========================================
def generar_tres_propuestas(cur, comedor_id: int, presupuesto_semanal: float,
                            creado_por_id: int, fecha_referencia: date = None,
                            seed: int = 0):
    """
    Genera y persiste las 3 propuestas de menú semanal (NUTRI, ECONO, BALANCE)
    agrupadas por un sesion_id. Retorna el payload completo para el frontend.
    """
    if presupuesto_semanal is None or float(presupuesto_semanal) <= 0:
        raise ValueError("El presupuesto semanal debe ser mayor a cero.")
    presupuesto_semanal = float(presupuesto_semanal)
    fecha_referencia = fecha_referencia or date.today()

    params = _cargar_parametros(cur)
    recetas, modelo_id = _cargar_recetas_cluster(cur)
    if not recetas:
        raise ValueError(
            "No hay un modelo K-means activo con recetas aptas. Entrene el modelo en "
            "la pestaña 'Clusters K-Means' antes de generar propuestas de menú.")

    precios_gramo = _precios_por_gramo(cur)
    _costear_recetas(cur, recetas, precios_gramo)
    recetas = [r for r in recetas if r['costo_racion'] > 0]
    if len(recetas) < params['dias']:
        raise ValueError(
            f"Solo hay {len(recetas)} recetas con costo y nutrición completos; se "
            f"requieren al menos {params['dias']} para cubrir la semana.")

    recetas_por_cluster = {}
    for r in recetas:
        recetas_por_cluster.setdefault(r['cluster_codigo'], []).append(r)
    recetas_por_id = {r['receta_id']: r for r in recetas}

    fecha_inicio = _lunes_de(fecha_referencia)
    marca = f"{comedor_id}|{fecha_inicio.isoformat()}|{creado_por_id}|{seed}"
    sesion_id = hashlib.sha256(marca.encode()).hexdigest()[:32]

    total_comensales = params['com_social'] + params['com_afiliado'] + params['com_normal']
    propuestas = []
    for idx, (codigo, meta) in enumerate(VARIANTES.items()):
        pesos = _jitter_weights(params['ponderaciones'].get(codigo, {}), seed, idx)
        menu, sobrepaso = _generar_menu_variante(
            recetas_por_cluster, recetas, pesos, params, presupuesto_semanal, fecha_inicio)

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
        'modelo_kmeans_id': modelo_id,
        'seed': seed,
        'propuestas': propuestas,
    }


# ==========================================
# CONSULTAS DE APOYO PARA EL ROUTER (PARTE 3)
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