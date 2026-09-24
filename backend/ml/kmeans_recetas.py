"""
ml/kmeans_recetas.py
Objetivo: Motor del modelo K-means del recetario (COM-5). Construye el dataset por
          ración con las 4 variables (energía kcal, hierro mg, proteína g, precio S/),
          aplica las reglas de negocio del comedor (R1 proteínas permitidas, R2 veto a
          res/cerdo, R3 sin recetas de precio alto), entrena K-means con k=4, etiqueta
          los centroides semánticamente (biyección determinista) y persiste el modelo
          activo junto con la asignación receta->cluster.
Uso: Importado por routers/kmeans.py. Todas las funciones reciben un cursor psycopg2
     (RealDictCursor) activo; el caller gestiona la transacción.
Reglas de negocio (COM-5):
  R1: La receta debe contener al menos una fuente de proteína permitida
      (pollo, gallina, huevo, hígado de res, pescado/atún/bonito/jurel, sangrecita).
  R2: Se excluyen recetas con ingredientes de res/cerdo/derivados. El "hígado de res"
      se exceptúa del veto porque es fuente permitida (se evalúa R1 antes que R2).
  R3: El costo por ración se clasifica en bajo/medio/alto según parámetros del sistema;
      las recetas de nivel ALTO se excluyen del modelo.
Etiquetado de centroides (biyección determinista):
  1) Anti-Anemia Premium        = centroide con mayor hierro.
  3) Ligero y Saludable         = menor energía entre los restantes.
  2) Fortalecimiento Balanceado = mayor (proteína + energía) entre los restantes.
  4) All-Rounder Económico      = el centroide restante.
Referencia: ticket COM-5 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
import re
import json
import unicodedata

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
FEATURES = ['energia_kcal', 'hierro_mg', 'proteina_g', 'precio_soles']

CODIGO_ETIQUETA = {
    1: 'Anti-Anemia Premium',
    2: 'Fortalecimiento Balanceado',
    3: 'Ligero y Saludable',
    4: 'All-Rounder Económico',
}

# R1: fuentes de proteína permitidas por el presupuesto del comedor
RE_PROTEINA_PERMITIDA = re.compile(
    r'\b(pollo|gallina|huevo|higado|pescado|atun|bonito|jurel|caballa|trucha|sangrecita)\b')
# R2: ingredientes vetados (res, cerdo y derivados)
RE_PROHIBIDO = re.compile(
    r'\b(res|vaca|vacuno|cerdo|chancho|porcino|chorizo|salchicha|bistec|bisteck|lomo|panceta|tocino|chicharron)\b')

RANDOM_STATE = 42
N_INIT = 10


# ==========================================
# UTILIDADES
# ==========================================
def _normalizar(texto):
    """Minúsculas y sin tildes, para emparejar nombres de ingredientes."""
    if not texto:
        return ''
    txt = unicodedata.normalize('NFD', str(texto).lower())
    return ''.join(c for c in txt if unicodedata.category(c) != 'Mn').strip()


def _tabla_existe(cur, nombre):
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s;", (nombre,))
    return cur.fetchone() is not None


def _columnas(cur, tabla):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s;", (tabla,))
    return [f['column_name'] for f in cur.fetchall()]


def _a_gramos(cantidad, sim_unidad, gramos_por_unidad=100.0):
    """Convierte una cantidad de receta a gramos según el símbolo de la unidad."""
    s = (sim_unidad or '').strip()
    if s in ('gr', 'g', 'gramo', 'gramos'):
        return float(cantidad)
    if s in ('kg', 'kilo', 'kilos', 'kilogramo'):
        return float(cantidad) * 1000.0
    if s in ('ml', 'mililitro'):
        return float(cantidad)          # densidad ~1
    if s in ('lt', 'l', 'litro'):
        return float(cantidad) * 1000.0
    if s in ('und', 'unidad', 'u', 'un'):
        return float(cantidad) * float(gramos_por_unidad)
    if s == 'taza':
        return float(cantidad) * 240.0
    if s in ('cda', 'cucharada'):
        return float(cantidad) * 15.0
    if s in ('cdta', 'cucharadita'):
        return float(cantidad) * 5.0
    return float(cantidad)              # unidad desconocida: se asume gramos


# ==========================================
# DESCUBRIMIENTO DEFENSIVO DEL ESQUEMA
# ==========================================
def _detectar_tabla_precios(cur):
    """Detecta la tabla de precios del scraper y sus columnas clave."""
    for nombre in ('precios_ingredientes', 'precios_historicos', 'historial_precios',
                   'ingrediente_precios', 'precios'):
        if not _tabla_existe(cur, nombre):
            continue
        cols = _columnas(cur, nombre)
        col_ing = next((c for c in cols if c in ('ingrediente_id', 'catalogo_id', 'ingrediente')), None)
        col_fecha = next((c for c in cols if c in ('fecha', 'fecha_registro', 'fecha_precio')), None)
        col_precio = next((c for c in cols if c in ('precio', 'precio_soles', 'precio_kg')), None)
        if col_ing and col_precio:
            return nombre, col_ing, col_fecha, col_precio
    return None, None, None, None


def _detectar_tabla_receta_ingredientes(cur):
    """Detecta la tabla puente receta-ingrediente y sus columnas."""
    for nombre in ('receta_ingredientes', 'recetas_ingredientes', 'receta_almuerzo_ingredientes'):
        if not _tabla_existe(cur, nombre):
            continue
        cols = _columnas(cur, nombre)
        col_ing = next((c for c in cols if c in ('ingrediente_id', 'catalogo_id', 'ingrediente')), None)
        col_cant = next((c for c in cols if c in ('cantidad', 'cant', 'monto')), None)
        if col_ing and col_cant:
            col_unid = next((c for c in cols if c in ('unidad_medida_id', 'unidad_id', 'unidad')), None)
            return nombre, col_ing, col_cant, col_unid
    return None, None, None, None


def _detectar_tabla_catalogo(cur):
    """Detecta la tabla catálogo de ingredientes y su columna de nombre."""
    for nombre in ('ingredientes', 'catalogo_ingredientes', 'catalogo_insumos', 'insumos'):
        if not _tabla_existe(cur, nombre):
            continue
        cols = _columnas(cur, nombre)
        if 'nombre' in cols:
            return nombre
    return None


# ==========================================
# CARGA DE DATOS BASE
# ==========================================
def _parametros_kmeans(cur):
    """Lee k y los umbrales de precio por ración desde parametros_sistema."""
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('KMEANS_K', 'KMEANS_PRECIO_BAJO_MAX', 'KMEANS_PRECIO_MEDIO_MAX');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    k = int(float(p.get('KMEANS_K', 4)))
    bajo = float(p.get('KMEANS_PRECIO_BAJO_MAX', 2.20))
    medio = float(p.get('KMEANS_PRECIO_MEDIO_MAX', 3.50))
    return k, bajo, medio


def _precios_actuales(cur):
    """Retorna {ingrediente_id: precio_por_kg} con el último precio conocido."""
    tabla, col_ing, col_fecha, col_precio = _detectar_tabla_precios(cur)
    if not tabla:
        return {}
    if col_fecha:
        cur.execute(f"""
            SELECT DISTINCT ON ({col_ing}) {col_ing} AS ingrediente_id, {col_precio} AS precio
            FROM {tabla}
            WHERE {col_precio} IS NOT NULL
            ORDER BY {col_ing}, {col_fecha} DESC;
        """)
    else:
        cur.execute(f"SELECT {col_ing} AS ingrediente_id, {col_precio} AS precio FROM {tabla};")
    return {r['ingrediente_id']: float(r['precio']) for r in cur.fetchall()}


def _cargar_unidades(cur):
    """Retorna {unidad_id: simbolo_normalizado} de unidades_medida."""
    if not _tabla_existe(cur, 'unidades_medida'):
        return {}
    cols = _columnas(cur, 'unidades_medida')
    col_sim = next((c for c in ('simbolo', 'abreviatura', 'codigo', 'nombre') if c in cols), None)
    if not col_sim:
        return {}
    cur.execute(f"SELECT id, {col_sim} AS sim FROM unidades_medida;")
    return {r['id']: _normalizar(r['sim']) for r in cur.fetchall()}


def _cargar_nutricion(cur):
    """Retorna la tabla de composición nutricional por ingrediente (por 100 g)."""
    cur.execute("""
        SELECT nombre_normalizado, energia_kcal_100g, proteina_g_100g,
               hierro_mg_100g, fibra_g_100g, gramos_por_unidad
        FROM ingredientes_nutricion;
    """)
    return cur.fetchall()


def _match_nutricion(nombre_norm, nutricion):
    """Empareja un ingrediente de receta con su fila nutricional (exacto o contenimiento)."""
    for n in nutricion:
        if n['nombre_normalizado'] == nombre_norm:
            return n
    mejor = None
    for n in nutricion:
        nn = n['nombre_normalizado']
        if nn in nombre_norm or nombre_norm in nn:
            if mejor is None or len(nn) > len(mejor['nombre_normalizado']):
                mejor = n
    return mejor


# ==========================================
# CONSTRUCCIÓN DEL DATASET (por ración) + REGLAS R1-R3
# ==========================================
def construir_dataset(cur, precio_bajo_max, precio_medio_max):
    """
    Construye el dataset por ración de todas las recetas y aplica las reglas R1-R3.
    Retorna (filas, excluidas):
      filas: lista de dicts con receta_id, nombre, energia_kcal, hierro_mg, proteina_g,
             fibra_g, precio_soles y nivel_precio (aptas para el modelo).
      excluidas: lista de dicts con receta_id, nombre y motivo de exclusión.
    """
    nutricion = _cargar_nutricion(cur)
    precios = _precios_actuales(cur)
    unidades = _cargar_unidades(cur)

    tabla_ri, col_ing, col_cant, col_unid = _detectar_tabla_receta_ingredientes(cur)
    catalogo = _detectar_tabla_catalogo(cur)
    if not tabla_ri or not catalogo:
        raise ValueError("No se detectaron las tablas de receta-ingredientes o catálogo.")

    # Recetas vigentes
    cols_rec = _columnas(cur, 'recetas_almuerzo')
    filtro_estado = ""
    if 'estado_activo' in cols_rec:
        filtro_estado = " WHERE estado_activo = TRUE"
    cur.execute(f"SELECT id, nombre, COALESCE(raciones, 4) AS raciones FROM recetas_almuerzo{filtro_estado};")
    recetas = cur.fetchall()

    # Ingredientes de todas las recetas en una sola consulta
    sel_unid = f"ri.{col_unid} AS unidad_id," if col_unid else "NULL AS unidad_id,"
    cur.execute(f"""
        SELECT ri.receta_id, ri.{col_cant} AS cantidad, {sel_unid}
               ci.id AS ing_id, ci.nombre AS ing_nombre
        FROM {tabla_ri} ri
        JOIN {catalogo} ci ON ci.id = ri.{col_ing};
    """)
    ingredientes_por_receta = {}
    for r in cur.fetchall():
        ingredientes_por_receta.setdefault(r['receta_id'], []).append(r)

    filas = []
    excluidas = []
    for rec in recetas:
        items = ingredientes_por_receta.get(rec['id'], [])
        if not items:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_ingredientes'})
            continue

        suma = {'energia': 0.0, 'proteina': 0.0, 'hierro': 0.0, 'fibra': 0.0}
        costo_total = 0.0
        tiene_proteina_permitida = False
        motivo_exclusion = None

        for it in items:
            nombre_norm = _normalizar(it['ing_nombre'])

            # R1/R2: primero se evalúa proteína permitida (exceptúa hígado de res del veto)
            es_permitida = bool(RE_PROTEINA_PERMITIDA.search(nombre_norm))
            if es_permitida:
                tiene_proteina_permitida = True
            elif RE_PROHIBIDO.search(nombre_norm):
                motivo_exclusion = motivo_exclusion or 'contiene_res_o_cerdo'

            # Nutrición del ingrediente
            nut = _match_nutricion(nombre_norm, nutricion)
            gramos = _a_gramos(it['cantidad'],
                               unidades.get(it['unidad_id']),
                               nut['gramos_por_unidad'] if nut else 100.0)
            if nut:
                factor = gramos / 100.0
                suma['energia'] += float(nut['energia_kcal_100g']) * factor
                suma['proteina'] += float(nut['proteina_g_100g']) * factor
                suma['hierro'] += float(nut['hierro_mg_100g']) * factor
                suma['fibra'] += float(nut['fibra_g_100g']) * factor

            # Costo: precio del scraper es por kg
            precio_kg = precios.get(it['ing_id'])
            if precio_kg is not None:
                costo_total += (gramos / 1000.0) * precio_kg

        # Aplicación de reglas en orden
        if motivo_exclusion:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': motivo_exclusion})
            continue
        if not tiene_proteina_permitida:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_proteina_permitida'})
            continue
        if suma['energia'] <= 0:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_datos_nutricion'})
            continue
        if costo_total <= 0:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_precio'})
            continue

        raciones = float(rec['raciones']) or 4.0
        precio_racion = costo_total / raciones

        # R3: nivel de precio y exclusión de nivel alto
        if precio_racion <= precio_bajo_max:
            nivel = 'bajo'
        elif precio_racion <= precio_medio_max:
            nivel = 'medio'
        else:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'precio_alto'})
            continue

        filas.append({
            'receta_id': rec['id'],
            'nombre': rec['nombre'],
            'energia_kcal': round(suma['energia'] / raciones, 2),
            'hierro_mg': round(suma['hierro'] / raciones, 2),
            'proteina_g': round(suma['proteina'] / raciones, 2),
            'fibra_g': round(suma['fibra'] / raciones, 2),
            'precio_soles': round(precio_racion, 2),
            'nivel_precio': nivel,
        })

    return filas, excluidas


# ==========================================
# ETIQUETADO SEMÁNTICO DE CENTROIDES
# ==========================================
def _etiquetar_centroides(centros_estandarizados):
    """
    Biyección determinista centroide->código de cluster:
      1) mayor hierro -> Anti-Anemia Premium
      3) menor energía (restantes) -> Ligero y Saludable
      2) mayor proteína+energía (restantes) -> Fortalecimiento Balanceado
      4) restante -> All-Rounder Económico
    Retorna {indice_cluster: codigo}.
    """
    idx = list(range(len(centros_estandarizados)))
    asignacion = {}

    i_anemia = max(idx, key=lambda i: centros_estandarizados[i][1])   # hierro z
    asignacion[i_anemia] = 1
    idx.remove(i_anemia)

    i_ligero = min(idx, key=lambda i: centros_estandarizados[i][0])   # energía z
    asignacion[i_ligero] = 3
    idx.remove(i_ligero)

    i_fuerza = max(idx, key=lambda i: centros_estandarizados[i][2] + centros_estandarizados[i][0])
    asignacion[i_fuerza] = 2
    idx.remove(i_fuerza)

    asignacion[idx[0]] = 4                                            # All-Rounder restante
    return asignacion


# ==========================================
# ENTRENAMIENTO Y PERSISTENCIA
# ==========================================
def entrenar_y_persistir(cur):
    """
    Ejecuta el pipeline completo: dataset -> reglas -> K-means(k) -> etiquetado ->
    persistencia del modelo activo y su asignación receta->cluster.
    Retorna el resumen del entrenamiento (dict). El caller gestiona el commit.
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)

    if len(filas) < k:
        raise ValueError(
            f"Solo {len(filas)} recetas aptas para k={k}. "
            "Revise las reglas de negocio o amplíe el recetario.")

    X = np.array([[f['energia_kcal'], f['hierro_mg'], f['proteina_g'], f['precio_soles']] for f in filas])
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
    labels = km.fit_predict(Xs)

    inercia = float(km.inertia_)
    silhouette = float(silhouette_score(Xs, labels)) if len(set(labels)) > 1 else 0.0

    # Etiquetado semántico sobre centroides estandarizados
    asignacion = _etiquetar_centroides(km.cluster_centers_)

    # Centroides crudos por código de cluster (interpretables para la UI)
    centroides = {}
    for i, codigo in asignacion.items():
        centroides[str(codigo)] = {
            'energia_kcal': round(float(km.cluster_centers_[i][0]), 2),
            'hierro_mg': round(float(km.cluster_centers_[i][1]), 2),
            'proteina_g': round(float(km.cluster_centers_[i][2]), 2),
            'precio_soles': round(float(km.cluster_centers_[i][3]), 2),
        }
    etiquetas = {str(c): CODIGO_ETIQUETA[c] for c in asignacion.values()}

    # Desactiva el modelo anterior y persiste el nuevo
    cur.execute("UPDATE kmeans_modelos SET activo = FALSE WHERE activo = TRUE;")
    parametros = {
        'features': FEATURES,
        'random_state': RANDOM_STATE,
        'n_init': N_INIT,
        'precio_bajo_max': bajo_max,
        'precio_medio_max': medio_max,
        'reglas': ['R1_proteina_permitida', 'R2_veto_res_cerdo', 'R3_sin_precio_alto'],
    }
    cur.execute("""
        INSERT INTO kmeans_modelos
            (k, n_recetas, n_excluidas, inercia, silhouette, centroides, etiquetas, parametros, activo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id;
    """, (k, len(filas), len(excluidas), inercia, silhouette,
          json.dumps(centroides), json.dumps(etiquetas), json.dumps(parametros)))
    modelo_id = cur.fetchone()['id']

    # Asignación receta->cluster con snapshot de features
    for f, lab in zip(filas, labels):
        codigo = asignacion[lab]
        cur.execute("""
            INSERT INTO recetas_clusters
                (modelo_id, receta_id, cluster_codigo, cluster_etiqueta,
                 energia_kcal, proteina_g, hierro_mg, fibra_g, precio_soles, nivel_precio)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (modelo_id, receta_id) DO UPDATE
                SET cluster_codigo = EXCLUDED.cluster_codigo,
                    cluster_etiqueta = EXCLUDED.cluster_etiqueta;
        """, (modelo_id, f['receta_id'], codigo, CODIGO_ETIQUETA[codigo],
              f['energia_kcal'], f['proteina_g'], f['hierro_mg'], f['fibra_g'],
              f['precio_soles'], f['nivel_precio']))

    # Resumen para la respuesta del endpoint
    resumen_clusters = []
    for codigo in sorted(CODIGO_ETIQUETA.keys()):
        miembros = [f for f, lab in zip(filas, labels) if asignacion[lab] == codigo]
        resumen_clusters.append({
            'codigo': codigo,
            'etiqueta': CODIGO_ETIQUETA[codigo],
            'n_recetas': len(miembros),
            'centroide': centroides[str(codigo)],
            'ejemplos': [m['nombre'] for m in miembros[:3]],
        })

    return {
        'modelo_id': modelo_id,
        'k': k,
        'n_recetas': len(filas),
        'n_excluidas': len(excluidas),
        'inercia': round(inercia, 4),
        'silhouette': round(silhouette, 4),
        'clusters': resumen_clusters,
        'excluidas': excluidas,
    }


# ==========================================
# CONSULTAS PARA EL ROUTER
# ==========================================
def obtener_modelo_activo(cur):
    """Retorna el modelo activo con sus metadatos, o None si aún no se entrena."""
    cur.execute("""
        SELECT id, fecha_entrenamiento, k, n_recetas, n_excluidas, inercia, silhouette,
               centroides, etiquetas, parametros
        FROM kmeans_modelos
        WHERE activo = TRUE
        ORDER BY id DESC
        LIMIT 1;
    """)
    return cur.fetchone()


def obtener_recetas_por_cluster(cur, modelo_id, cluster_codigo=None):
    """Retorna las recetas asignadas al modelo (opcionalmente filtradas por cluster)."""
    query = """
        SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
               rc.energia_kcal, rc.proteina_g, rc.hierro_mg, rc.fibra_g,
               rc.precio_soles, rc.nivel_precio, r.nombre
        FROM recetas_clusters rc
        JOIN recetas_almuerzo r ON r.id = rc.receta_id
        WHERE rc.modelo_id = %s
    """
    params = [modelo_id]
    if cluster_codigo is not None:
        query += " AND rc.cluster_codigo = %s"
        params.append(cluster_codigo)
    query += " ORDER BY rc.cluster_codigo, rc.precio_soles;"
    cur.execute(query, params)
    return cur.fetchall()


def listar_candidatas(cur):
    """
    Transparencia del modelo: retorna las recetas aptas y las excluidas con su motivo,
    recalculadas con los parámetros vigentes (sin persistir nada).
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)
    return {'k': k, 'aptas': filas, 'excluidas': excluidas}