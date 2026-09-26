"""
ml/kmeans_recetas.py
Objetivo: Motor del modelo K-means del recetario (COM-5). Construye el dataset por
          ración con las 4 variables (energía kcal, hierro mg, proteína g, precio S/),
          aplica las reglas de negocio del comedor (R1 proteínas permitidas, R2 veto a
          res/cerdo, R3 sin recetas de precio alto), entrena K-means con k=4, etiqueta
          los centroides semánticamente (biyección determinista) y persiste el modelo
          activo junto con la asignación receta->cluster.
Historial:
 - COM-5 v1/v2/v3: reglas R1-R3 hardcodeadas; detección defensiva de esquema; FIX de
   precios por gramo vía insumos->historial_precios; top-3 tolerante a formatos legacy.
 - COM-5 v4: las listas de proteínas permitidas e ingredientes vetados dejan de estar
   hardcodeadas: se leen de parametros_sistema (KMEANS_PROTEINAS_PERMITIDAS /
   KMEANS_INGREDIENTES_VETADOS) y son editables desde la vista de Clusters (exclusiva
   del Admin de Sistemas). Las expresiones regulares fijas anteriores se conservan
   COMENTADAS como valores por defecto (fallback).
 - COM-5 v5: FIX del KeyError 'energia_kcal': el SELECT de recetas de construir_dataset
   no incluía las columnas nutricionales de recetas_almuerzo (hierro_mg, proteina_g,
   energia_kcal); se agregan con detección defensiva y se omiten recetas sin nutrición.
 - COM-5 v6 (este archivo): FIX de unidades de centroides. K-means entrena sobre
   features estandarizadas, por lo que km.cluster_centers_ vive en espacio z y la UI
   mostraba valores negativos rotulados como kcal/mg/g/S/. Ahora los centroides se
   persisten en UNIDADES REALES por ración vía scaler.inverse_transform(), y los
   centroides estandarizados se conservan en parametros.centroides_z para auditoría.
   El bloque de persistencia anterior queda COMENTADO por trazabilidad.
Uso: Importado por routers/kmeans.py. Todas las funciones reciben un cursor psycopg2
     (RealDictCursor); el caller gestiona la transacción.
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

RANDOM_STATE = 42
N_INIT = 10

# COM-5 v4: listas POR DEFECTO (fallback si el parámetro no existe o es inválido).
PROTEINAS_PERMITIDAS_DEFAULT = [
    'pollo', 'gallina', 'huevo', 'higado', 'pescado',
    'atun', 'bonito', 'jurel', 'caballa', 'trucha', 'sangrecita',
]
INGREDIENTES_VETADOS_DEFAULT = [
    'res', 'vaca', 'vacuno', 'cerdo', 'chancho', 'porcino', 'chorizo',
    'salchicha', 'bistec', 'bisteck', 'lomo', 'panceta', 'tocino', 'chicharron',
]

# COM-5 v4 (trazabilidad): expresiones regulares FIJAS de COM-5 v1-v3, comentadas.
# La configuración operativa ahora vive en parametros_sistema y se compila en
# cargar_reglas_proteinas(); estos patrones quedan solo como documentación del default.
# RE_PROTEINA_PERMITIDA = re.compile(
#     r'\b(pollo|gallina|huevo|higado|pescado|atun|bonito|jurel|caballa|trucha|sangrecita)\b')
# RE_PROHIBIDO = re.compile(
#     r'\b(res|vaca|vacuno|cerdo|chancho|porcino|chorizo|salchicha|bistec|bisteck|lomo|panceta|tocino|chicharron)\b')

# COM-5 v2: el top de ingredientes solo considera estas categorías (nunca especias,
# cereales, grasas ni lácteos), según requerimiento de la administradora.
CATEGORIAS_TOP_INGREDIENTE = ('Vegetales y Hortalizas', 'Frutas', 'Proteinas')


# ==========================================
# COM-5 v4: REGLAS CONFIGURABLES DE PROTEÍNAS
# ==========================================
def _regex_de_lista(tokens, por_defecto):
    """Compila una lista de tokens a un regex de palabra completa; usa el default si vacía."""
    lista = [str(t).strip() for t in (tokens or por_defecto) if str(t).strip()]
    if not lista:
        lista = por_defecto
    return re.compile(r'\b(' + '|'.join(lista) + r')\b')


def cargar_reglas_proteinas(cur):
    """
    COM-5 v4: Lee las listas configurables desde parametros_sistema y retorna
    (regex_permitidas, regex_vetadas, lista_permitidas, lista_vetadas).
    Si el parámetro no existe o el JSON es inválido, cae al default histórico.
    """
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('KMEANS_PROTEINAS_PERMITIDAS', 'KMEANS_INGREDIENTES_VETADOS');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    permitidas = PROTEINAS_PERMITIDAS_DEFAULT
    try:
        parsed = json.loads(p.get('KMEANS_PROTEINAS_PERMITIDAS') or 'null')
        if isinstance(parsed, list) and parsed:
            permitidas = [str(x).lower() for x in parsed]
    except Exception:
        permitidas = PROTEINAS_PERMITIDAS_DEFAULT
    vetadas = INGREDIENTES_VETADOS_DEFAULT
    try:
        parsed = json.loads(p.get('KMEANS_INGREDIENTES_VETADOS') or 'null')
        if isinstance(parsed, list) and parsed:
            vetadas = [str(x).lower() for x in parsed]
    except Exception:
        vetadas = INGREDIENTES_VETADOS_DEFAULT
    return (_regex_de_lista(permitidas, PROTEINAS_PERMITIDAS_DEFAULT),
            _regex_de_lista(vetadas, INGREDIENTES_VETADOS_DEFAULT),
            permitidas, vetadas)


# ==========================================
# UTILIDADES
# ==========================================
def _normalizar(texto):
    """Minúsculas y sin tildes, para emparejar nombres de ingredientes."""
    if not texto:
        return ''
    txt = unicodedata.normalize('NFD', str(texto).lower())
    return ''.join(c for c in txt if unicodedata.category(c) != 'Mn').strip()


def _tablas_public(cur):
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
    return [r['table_name'] for r in cur.fetchall()]


def _columnas(cur, tabla):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s;", (tabla,))
    return [r['column_name'] for r in cur.fetchall()]


def _col(cols, candidatos, contiene=None):
    """Primera columna que coincide por nombre exacto o, en su defecto, por subcadena."""
    for c in candidatos:
        if c in cols:
            return c
    if contiene:
        for c in cols:
            if contiene in c:
                return c
    return None


# ==========================================
# DETECCIÓN DEFENSIVA DEL ESQUEMA
# ==========================================
def _detectar_puente(cur, tablas):
    for n in ('receta_ingredientes', 'recetas_ingredientes', 'recetas_almuerzo_ingredientes',
              'receta_almuerzo_ingredientes', 'detalle_recetas', 'receta_detalle',
              'ingredientes_receta', 'ingredientes_recetas'):
        if n in tablas:
            return n
    for n in tablas:
        if 'recet' in n and any(k in n for k in ('ingred', 'insumo', 'alimento', 'food', 'detalle')):
            return n
    return None


def _detectar_catalogo(cur, tablas, puente):
    for n in ('catalogo_ingredientes', 'ingredientes', 'catalogo_insumos', 'insumos',
              'catalogo_alimentos', 'alimentos', 'food_items', 'fooditem'):
        if n in tablas and n != puente:
            return n
    for n in tablas:
        if n == puente:
            continue
        if any(k in n for k in ('ingred', 'alimento', 'insumo', 'food')) and \
           not any(k in n for k in ('precio', 'nutric', 'recet', 'histor', 'unidad')):
            return n
    return None


def _detectar_recetas(cur, tablas, puente):
    for n in ('recetas_almuerzo', 'recetas', 'receta_almuerzo', 'recetas_base', 'recipes'):
        if n in tablas and n != puente:
            return n
    for n in tablas:
        if n == puente:
            continue
        if 'recet' in n and not any(k in n for k in ('ingred', 'insumo', 'alimento', 'detalle', 'cluster')):
            return n
    return None


def _detectar_precios(cur, tablas):
    for n in ('precios_ingredientes', 'precios_historicos', 'historial_precios',
              'ingrediente_precios', 'precios', 'precios_alimentos', 'historico_precios'):
        if n in tablas:
            return n
    for n in tablas:
        if 'precio' in n or 'sisap' in n or ('histor' in n and any(k in n for k in ('ingred', 'alim', 'insumo'))):
            return n
    return None


def _detectar_unidades(cur, tablas):
    for n in ('unidades_medida', 'unidad_medida', 'unidades', 'unidad', 'umed'):
        if n in tablas:
            return n
    for n in tablas:
        if 'unid' in n:
            return n
    return None


def diagnosticar_esquema(cur):
    """
    COM-5: reporte de auditoría del esquema detectado (tablas, columnas y rol asignado).
    Se expone vía GET /kmeans/diagnostico para verificar la configuración del motor.
    """
    tablas = _tablas_public(cur)
    puente = _detectar_puente(cur, tablas)
    catalogo = _detectar_catalogo(cur, tablas, puente)
    recetas = _detectar_recetas(cur, tablas, puente)
    precios = _detectar_precios(cur, tablas)
    unidades = _detectar_unidades(cur, tablas)
    return {
        'tablas_publicas': sorted(tablas),
        'puente_receta_ingrediente': puente,
        'columnas_puente': _columnas(cur, puente) if puente else None,
        'catalogo_ingredientes': catalogo,
        'columnas_catalogo': _columnas(cur, catalogo) if catalogo else None,
        'tabla_recetas': recetas,
        'columnas_recetas': _columnas(cur, recetas) if recetas else None,
        'tabla_precios': precios,
        'columnas_precios': _columnas(cur, precios) if precios else None,
        'tabla_unidades': unidades,
        'tabla_nutricion': 'ingredientes_nutricion' if 'ingredientes_nutricion' in tablas else None,
    }


# ==========================================
# CARGA DE PARÁMETROS Y CONTEXTO
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
    """
    COM-8 FIX (conservado): {ingrediente_id: precio_por_kg} con el último día de
    historial_precios, unido por insumos->ingredientes y convirtiendo la unidad del
    insumo a gramos (factor_a_base para masa/volumen; peso_estimado_g para discretas).
    Se toma el MÍNIMO entre insumos del mismo ingrediente (criterio de compra económica).
    COM-5 v4 (trazabilidad): la versión anterior mapeaba insumo_id como si fuera
    ingrediente_id (precios cruzados); quedó reemplazada por este join correcto.
    """
    cur.execute("""
        SELECT ins.ingrediente_id AS ing_id,
               MIN(
                 CASE WHEN um.tipo_magnitud = 'discreto'
                      THEN hp.precio_prom / GREATEST(ing.peso_estimado_g, 1)
                      ELSE hp.precio_prom / GREATEST(um.factor_a_base, 0.0001)
                 END
               ) * 1000 AS precio_por_kg
        FROM historial_precios hp
        JOIN insumos ins ON ins.id = hp.insumo_id
        JOIN unidades_medida um ON um.id = ins.unidad_medida_id
        JOIN ingredientes ing ON ing.id = ins.ingrediente_id
        WHERE hp.fecha = (SELECT MAX(fecha) FROM historial_precios)
          AND hp.precio_prom IS NOT NULL AND hp.precio_prom > 0
        GROUP BY ins.ingrediente_id;
    """)
    return {r['ing_id']: float(r['precio_por_kg']) for r in cur.fetchall()}


def _cargar_unidades(cur):
    """Retorna {unidad_id: simbolo_normalizado} de la tabla de unidades de medida."""
    tabla = _detectar_unidades(cur, _tablas_public(cur))
    if not tabla:
        return {}
    cols = _columnas(cur, tabla)
    col_sim = _col(cols, ['simbolo', 'abreviatura', 'codigo', 'nombre', 'unidad'], contiene='simb') or \
              _col(cols, ['nombre', 'unidad'], contiene='nombr') or \
              _col(cols, ['unidad'], contiene='unid')
    if not col_sim:
        return {}
    cur.execute(f"SELECT id, {col_sim} AS sim FROM {tabla};")
    return {r['id']: _normalizar(r['sim']) for r in cur.fetchall()}


def _cargar_nutricion(cur):
    """Composición nutricional por ingrediente (por 100 g), sembrada por COM-5."""
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


def _a_gramos(cantidad, sim_unidad, gramos_por_unidad=100.0):
    """Convierte una cantidad de receta a gramos según el símbolo de la unidad."""
    s = (sim_unidad or '').strip()
    if s in ('gr', 'g', 'gramo', 'gramos'):
        return float(cantidad)
    if s in ('kg', 'kilo', 'kilos', 'kilogramo'):
        return float(cantidad) * 1000.0
    if s in ('ml', 'mililitro'):
        return float(cantidad)
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
    return float(cantidad)


# ==========================================
# CONSTRUCCIÓN DEL DATASET (por ración) + REGLAS R1-R3
# ==========================================
def construir_dataset(cur, precio_bajo_max, precio_medio_max):
    """
    Construye el dataset por ración de todas las recetas y aplica las reglas R1-R3.
    COM-5 v4: R1 y R2 usan las listas CONFIGURABLES de proteínas permitidas e
    ingredientes vetados (parametros_sistema), no regex hardcodeadas.
    COM-5 v5: el SELECT de recetas incluye las columnas nutricionales
    (hierro_mg, proteina_g, energia_kcal) que antes faltaban y causaban KeyError.
    Retorna (filas, excluidas).
    """
    # COM-5 v4: reglas de proteínas configurables por el Admin de Sistemas
    re_permitida, re_vetada, _, _ = cargar_reglas_proteinas(cur)
    nutricion = _cargar_nutricion(cur)
    precios = _precios_actuales(cur)
    unidades = _cargar_unidades(cur)

    tablas = _tablas_public(cur)
    puente = _detectar_puente(cur, tablas)
    catalogo = _detectar_catalogo(cur, tablas, puente)
    recetas_tabla = _detectar_recetas(cur, tablas, puente)

    if not puente or not catalogo or not recetas_tabla:
        faltantes = []
        if not puente:
            faltantes.append('puente receta-ingrediente')
        if not catalogo:
            faltantes.append('catálogo de ingredientes')
        if not recetas_tabla:
            faltantes.append('tabla de recetas')
        raise ValueError(
            "No se detectaron: " + ", ".join(faltantes) +
            ". Tablas públicas visibles: " + ", ".join(sorted(tablas)) +
            ". Use GET /kmeans/diagnostico para ver el detalle.")

    # Columnas del puente
    cols_p = _columnas(cur, puente)
    col_rec = _col(cols_p, ['receta_id', 'receta', 'id_receta'], contiene='recet')
    col_ing = _col(cols_p, ['ingrediente_id', 'ingrediente', 'catalogo_id', 'alimento_id', 'insumo_id', 'food_id'],
                   contiene='ingred') or _col(cols_p, [], contiene='alimento') or _col(cols_p, [], contiene='insumo')
    col_cant = _col(cols_p, ['cantidad', 'cant', 'cantidad_por_racion'], contiene='cant')
    col_unid = _col(cols_p, ['unidad_medida_id', 'unidad_id', 'unidad', 'umed_id', 'id_unidad'], contiene='unid')
    if not col_rec or not col_ing or not col_cant:
        raise ValueError(f"La tabla puente '{puente}' no tiene columnas reconocibles de receta/ingrediente/cantidad: {cols_p}")

    # Columnas del catálogo
    cols_c = _columnas(cur, catalogo)
    col_cat_nom = _col(cols_c, ['nombre', 'nombre_normalizado', 'name'], contiene='nombr') or \
                  _col(cols_c, ['descripcion'], contiene='desc')
    if not col_cat_nom:
        raise ValueError(f"El catálogo '{catalogo}' no tiene columna de nombre reconocible: {cols_c}")

    # Columnas de recetas
    cols_r = _columnas(cur, recetas_tabla)
    col_r_nom = _col(cols_r, ['nombre', 'nombre_receta', 'plato', 'titulo'], contiene='nombr')
    col_r_rac = _col(cols_r, ['raciones', 'porciones', 'nro_raciones', 'rendimiento'], contiene='racion') or \
                _col(cols_r, [], contiene='porcion')
    col_r_est = _col(cols_r, ['estado_activo', 'activo', 'estado'])
    filtro_estado = ''
    if col_r_est in ('estado_activo', 'activo'):
        filtro_estado = f" WHERE {col_r_est} = TRUE"
    elif col_r_est == 'estado':
        filtro_estado = f" WHERE LOWER({col_r_est}::text) IN ('activo', 'true', 'vigente')"

    # COM-5 v5 (FIX): detección de las columnas nutricionales de la tabla de recetas.
    # Sin ellas en el SELECT, el RealDictRow no trae las claves y entrenar abortaba
    # con KeyError 'energia_kcal'.
    col_r_hie = _col(cols_r, ['hierro_mg', 'hierro'], contiene='hierro')
    col_r_pro = _col(cols_r, ['proteina_g', 'proteina'], contiene='proteina')
    col_r_ene = _col(cols_r, ['energia_kcal', 'energia'], contiene='energia')
    if not (col_r_hie and col_r_pro and col_r_ene):
        raise ValueError(
            f"La tabla de recetas '{recetas_tabla}' no tiene columnas nutricionales "
            f"(hierro_mg / proteina_g / energia_kcal). Columnas detectadas: {cols_r}")
    sel_nut = f", {col_r_hie} AS hierro_mg, {col_r_pro} AS proteina_g, {col_r_ene} AS energia_kcal"

    sel_rac = f"{col_r_rac} AS raciones" if col_r_rac else "NULL AS raciones"

    # COM-5 v5 (trazabilidad): SELECT anterior COMENTADO: no incluía las columnas
    # nutricionales y provocaba KeyError 'energia_kcal' en el armado de `filas`.
    # cur.execute(f"SELECT id, {col_r_nom} AS nombre, {sel_rac} FROM {recetas_tabla}{filtro_estado};")
    cur.execute(f"SELECT id, {col_r_nom} AS nombre, {sel_rac}{sel_nut} FROM {recetas_tabla}{filtro_estado};")
    recetas = cur.fetchall()

    sel_unid = f"ri.{col_unid} AS unidad_id," if col_unid else "NULL AS unidad_id,"
    if col_unid:
        cur.execute(f"""
            SELECT ri.{col_rec} AS receta_id, ri.{col_cant} AS cantidad, {sel_unid}
                   ci.id AS ing_id, ci.{col_cat_nom} AS ing_nombre,
                   um2.tipo_magnitud, um2.factor_a_base, ci.peso_estimado_g,
                   ca.nombre AS categoria
            FROM {puente} ri
            JOIN {catalogo} ci ON ci.id = ri.{col_ing}
            LEFT JOIN unidades_medida um2 ON um2.id = ri.{col_unid}
            LEFT JOIN categorias_alimentos ca ON ca.id = ci.categoria_id
        """)
    else:
        cur.execute(f"""
            SELECT ri.{col_rec} AS receta_id, ri.{col_cant} AS cantidad, NULL AS unidad_id,
                   ci.id AS ing_id, ci.{col_cat_nom} AS ing_nombre,
                   um2.tipo_magnitud, um2.factor_a_base, ci.peso_estimado_g,
                   ca.nombre AS categoria
            FROM {puente} ri
            JOIN {catalogo} ci ON ci.id = ri.{col_ing}
            LEFT JOIN unidades_medida um2 ON um2.id = ci.unidad_medida_id
            LEFT JOIN categorias_alimentos ca ON ca.id = ci.categoria_id
        """)

    costo_acum = {}
    nombres_acum = {}
    for fila in cur.fetchall():
        if fila['tipo_magnitud'] in ('masa', 'volumen'):
            gramos = float(fila['cantidad']) * float(fila['factor_a_base'] or 1)
        elif fila['tipo_magnitud'] == 'discreto':
            gramos = float(fila['cantidad']) * float(fila['peso_estimado_g'] or 1)
        else:
            gramos = float(fila['cantidad'])
        pkg = precios.get(fila['ing_id'])
        if pkg is not None:
            costo_acum[fila['receta_id']] = costo_acum.get(fila['receta_id'], 0.0) + (gramos / 1000.0) * pkg
        nombres_acum.setdefault(fila['receta_id'], []).append({
            'nombre': fila['ing_nombre'],
            'categoria': fila['categoria'] or '',
        })

    filas = []
    excluidas = []
    for rec in recetas:
        # COM-5 v5: recetas sin nutrición cargada se omiten del modelo (antes el
        # KeyError ocultaba este caso; ahora se filtra explícitamente).
        if rec.get('energia_kcal') is None:
            continue

        items = nombres_acum.get(rec['id'], [])
        if not items:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_ingredientes'})
            continue

        # R1/R2 con reglas CONFIGURABLES (COM-5 v4): primero permitida (exceptúa hígado de res del veto)
        tiene_proteina_permitida = False
        motivo_exclusion = None
        for ing in items:
            nombre_norm = _normalizar(ing['nombre'])
            if re_permitida.search(nombre_norm):
                tiene_proteina_permitida = True
            elif re_vetada.search(nombre_norm):
                motivo_exclusion = motivo_exclusion or 'contiene_res_o_cerdo'

        # COM-5 v5 (trazabilidad): bloque muerto COMENTADO. El match nutricional por
        # nombre (ingredientes_nutricion) ya no se usa para las features: la nutrición
        # por ración se lee directamente de las columnas de recetas_almuerzo.
        # suma = {'energia': 0.0, 'proteina': 0.0, 'hierro': 0.0, 'fibra': 0.0}
        # nut_match = 0
        # for ing in items:
        #     nut = _match_nutricion(_normalizar(ing['nombre']), nutricion)
        #     if nut:
        #         nut_match += 1

        rac = float(rec['raciones']) if rec['raciones'] else 4.0
        costo_total = costo_acum.get(rec['id'], 0.0)

        if motivo_exclusion:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': motivo_exclusion})
            continue
        if not tiene_proteina_permitida:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_proteina_permitida'})
            continue
        if costo_total <= 0:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_precio'})
            continue

        precio_racion = costo_total / rac

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
            # COM-5 v5: nutrición POR RACIÓN desde las columnas ya presentes en el SELECT
            'energia_kcal': round(float(rec['energia_kcal'] or 0) / rac, 2),
            'hierro_mg': round(float(rec['hierro_mg'] or 0) / rac, 2),
            'proteina_g': round(float(rec['proteina_g'] or 0) / rac, 2),
            'fibra_g': 0.0,
            'precio_soles': round(precio_racion, 2),
            'nivel_precio': nivel,
            'ingredientes': items,
        })

    return filas, excluidas


def _minmax(recetas) -> dict:
    if not recetas:
        return {k: (0, 1) for k in ('hierro', 'proteina', 'energia', 'precio')}
    return {
        'hierro': (min(r['hierro_mg'] for r in recetas), max(r['hierro_mg'] for r in recetas)),
        'proteina': (min(r['proteina_g'] for r in recetas), max(r['proteina_g'] for r in recetas)),
        'energia': (min(r['energia_kcal'] for r in recetas), max(r['energia_kcal'] for r in recetas)),
        'precio': (min(r['precio_soles'] for r in recetas), max(r['precio_soles'] for r in recetas)),
    }


# ==========================================
# ETIQUETADO SEMÁNTICO DE CENTROIDES
# ==========================================
def _etiquetar_centroides(centros_estandarizados):
    """
    Biyección determinista centroide->código de cluster (sobre espacio estandarizado):
      1) mayor hierro -> Anti-Anemia Premium
      3) menor energía (restantes) -> Ligero y Saludable
      2) mayor proteína+energía (restantes) -> Fortalecimiento Balanceado
      4) restante -> All-Rounder Económico
    """
    idx = list(range(len(centros_estandarizados)))
    asignacion = {}

    i_anemia = max(idx, key=lambda i: centros_estandarizados[i][1])
    asignacion[i_anemia] = 1
    idx.remove(i_anemia)

    i_ligero = min(idx, key=lambda i: centros_estandarizados[i][0])
    asignacion[i_ligero] = 3
    idx.remove(i_ligero)

    i_fuerza = max(idx, key=lambda i: centros_estandarizados[i][2] + centros_estandarizados[i][0])
    asignacion[i_fuerza] = 2
    idx.remove(i_fuerza)

    asignacion[idx[0]] = 4
    return asignacion


# ==========================================
# ENTRENAMIENTO Y PERSISTENCIA
# ==========================================
def entrenar_y_persistir(cur):
    """
    Ejecuta el pipeline completo: dataset -> reglas -> K-means(k) -> etiquetado ->
    persistencia del modelo activo y su asignación receta->cluster.
    COM-5 v6: los centroides persistidos en `centroides` van en UNIDADES REALES por
    ración (inverse_transform); los estandarizados quedan en parametros.centroides_z.
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

    asignacion = _etiquetar_centroides(km.cluster_centers_)

    # COM-5 v6 (FIX UX): centroides en UNIDADES REALES por ración para la UI.
    # km.cluster_centers_ vive en espacio estandarizado (z-score); mostrarlo tal cual
    # producía valores negativos rotulados como kcal/mg/g/S/ en las tarjetas.
    centros_crudos = scaler.inverse_transform(km.cluster_centers_)
    centroides = {}
    centroides_z = {}
    for i, codigo in asignacion.items():
        # COM-5 v6 (trazabilidad): bloque anterior COMENTADO (guardaba espacio z como
        # si fueran unidades reales):
        # centroides[str(codigo)] = {
        #     'energia_kcal': round(float(km.cluster_centers_[i][0]), 2),
        #     'hierro_mg': round(float(km.cluster_centers_[i][1]), 2),
        #     'proteina_g': round(float(km.cluster_centers_[i][2]), 2),
        #     'precio_soles': round(float(km.cluster_centers_[i][3]), 2),
        # }
        centroides[str(codigo)] = {
            'energia_kcal': round(float(centros_crudos[i][0]), 2),
            'hierro_mg': round(float(centros_crudos[i][1]), 2),
            'proteina_g': round(float(centros_crudos[i][2]), 2),
            'precio_soles': round(float(centros_crudos[i][3]), 2),
        }
        # Auditoría técnica: centroides estandarizados (z-score) conservados aparte
        centroides_z[str(codigo)] = {
            'energia_kcal': round(float(km.cluster_centers_[i][0]), 4),
            'hierro_mg': round(float(km.cluster_centers_[i][1]), 4),
            'proteina_g': round(float(km.cluster_centers_[i][2]), 4),
            'precio_soles': round(float(km.cluster_centers_[i][3]), 4),
        }
    etiquetas = {str(c): CODIGO_ETIQUETA[c] for c in asignacion.values()}

    cur.execute("UPDATE kmeans_modelos SET activo = FALSE WHERE activo = TRUE;")
    parametros = {
        'features': FEATURES,
        'random_state': RANDOM_STATE,
        'n_init': N_INIT,
        'precio_bajo_max': bajo_max,
        'precio_medio_max': medio_max,
        'reglas': ['R1_proteina_permitida', 'R2_veto_res_cerdo', 'R3_sin_precio_alto'],
        # COM-5 v6: espacio z conservado para auditoría (el gráfico PCA de Modelos ML
        # recalcula su propia proyección; esto es solo referencia técnica).
        'centroides_z': centroides_z,
    }
    cur.execute("""
        INSERT INTO kmeans_modelos
            (k, n_recetas, n_excluidas, inercia, silhouette, centroides, etiquetas, parametros, activo)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING id;
    """, (k, len(filas), len(excluidas), inercia, silhouette,
          json.dumps(centroides), json.dumps(etiquetas), json.dumps(parametros)))
    modelo_id = cur.fetchone()['id']

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
    """Recetas asignadas al modelo (opcionalmente filtradas por cluster)."""
    tablas = _tablas_public(cur)
    puente = _detectar_puente(cur, tablas)
    recetas_tabla = _detectar_recetas(cur, tablas, puente)
    cols_r = _columnas(cur, recetas_tabla)
    col_r_nom = _col(cols_r, ['nombre', 'nombre_receta', 'plato', 'titulo'], contiene='nombr')

    query = f"""
        SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
               rc.energia_kcal, rc.proteina_g, rc.hierro_mg, rc.fibra_g,
               rc.precio_soles, rc.nivel_precio, r.{col_r_nom} AS nombre
        FROM recetas_clusters rc
        JOIN {recetas_tabla} r ON r.id = rc.receta_id
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
    Transparencia del modelo: recetas aptas y excluidas con su motivo,
    recalculadas con los parámetros vigentes (sin persistir nada).
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)
    return {'k': k, 'aptas': filas, 'excluidas': excluidas}