"""
ml/kmeans_recetas.py
Objetivo: Motor del modelo K-means del recetario (COM-5). Construye el dataset por
ración, aplica las reglas de negocio del comedor (R0 seis nutrientes completos,
R1 proteínas permitidas, R2 veto configurable), entrena K-means, etiqueta los
centroides semánticamente (biyección determinista) y persiste el modelo activo con
su asignación receta->cluster.
Historial:
COM-5 v1/v2/v3: reglas hardcodeadas; detección defensiva de esquema; FIX de precios
    por gramo vía insumos->historial_precios.
COM-5 v4: reglas R1/R2 configurables desde parametros_sistema (Admin en Clusters).
COM-5 v5: FIX KeyError 'energia_kcal' (columnas nutricionales en el SELECT).
COM-5 v6: centroides persistidos en UNIDADES REALES (inverse_transform); z-score en
    parametros.centroides_z.
COM-37 v2: regla R4 de PRECIOS COMPLETOS (motivo 'precio_incompleto').
COM-37 v5: costeo sobre precios_insumos.py (equivalencias uso->gramos + mejor insumo).
COM-37 v5-fix: fallback_ultima_fecha para días sin corrida del scraper; blindaje de
    silhouette_score (n_samples > n_clusters) y mensaje de error guía.
COM-37 v7: la predicción Random Forest cuenta como fuente de precio válida para la
    completitud (misma jerarquía que Evaluar).
COM-47 v2: se dividió la nutrición de tabla entre raciones (interpretación errónea).
COM-47 v3: FIX definitivo: los valores nutricionales de recetas_almuerzo YA SON POR
    RACIÓN tal como se capturan; se usan SIN dividir (la división v2 queda COMENTADA).
COM-60: K-MEANS v2: FEATURES = 6 variables NUTRICIONALES (el precio sale de la
    distancia); RobustScaler; re-etiquetado por MEDIANAS (1=Anti-Anemia alto hierro,
    2=Energético denso, 3=Proteico balanceado, 4=Ligero complementario); diagnóstico
    de k óptimo (k=2..8, informativo); métricas post-hoc por cluster (Fe/S/, Prot/S/).
COM-60 v2.1: REGLA R0: el universo del modelo son SOLO recetas con los 6 nutrientes
    COMPLETOS; las incompletas se excluyen con motivo auditable 'nutricion_incompleta'
    (sin imputación; el bloque de imputación por mediana queda COMENTADO).
COM-71: MODELO LIMPIO: R3 (excluir por precio alto) SE ELIMINA del clustering
    (nivel_precio SOLO informativo); R4 pasa a FLAG `costeable` persistido en
    recetas_clusters; post-hoc y mediana de precio solo sobre costeables;
    /candidatas y resumen exponen n_costeables / n_no_costeables.
COM-72 (este archivo): AFINADO ante clusters singleton y silhouette baja:
    * Espacio de features log1p + RobustScaler (TRANSFORM): comprime colas de
      micronutrientes sesgados (vitamina A, zinc) que volvían recetas extremas en
      clusters de 1 miembro. Centroides reales vía expm1(inverse_transform(...)).
      Se aplica también en diagnosticar_k para coherencia de la curva de k.
    * Auditoría de tamaños: tamanos_clusters y aviso_clusters_pequenos (códigos con
      < KMEANS_MIN_CLUSTER_RECETAS miembros) en parametros y en el resumen, para que
      el comité detecte singletons sin que el motor los fusione a ciegas.
    * No se elimina ningún helper, regla ni bloque de trazabilidad de COM-71.
Uso: Importado por routers/kmeans.py y por ml/greedy_search.py (reglas R1/R2).
Referencia: tickets COM-5 / COM-37 / COM-47 / COM-60 / COM-71 / COM-72 (trazabilidad).
"""
import re
import json
import unicodedata
from datetime import date
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
# COM-60: RobustScaler reemplaza a StandardScaler (resistente a outliers de cocina).
from sklearn.preprocessing import RobustScaler
# COM-60 (trazabilidad): escalador anterior comentado:
# from sklearn.preprocessing import StandardScaler

# COM-37 v5: resolución unificada de precios y conversión estándar de unidades
from precios_insumos import (
    precios_por_gramo_por_insumo,
    mejor_opcion_ingrediente,
    gramos_por_unidad_estandar,
    gramos_por_unidad_compra,
)
# COM-37 v7: predicción RF compartida con el optimizador (misma fuente de verdad)
from optimizador import predecir_precio_con_confianza

# ==========================================
# CONSTANTES DEL MODELO
# ==========================================
# COM-60: las 6 variables nutricionales por ración. El precio YA NO es feature.
# COM-60 (trazabilidad): features anteriores comentadas:
# FEATURES = ['energia_kcal', 'hierro_mg', 'proteina_g', 'precio_soles']
FEATURES = ['energia_kcal', 'hierro_mg', 'proteina_g',
            'vitamina_a_ug', 'zinc_mg', 'carbohidratos_g']

# COM-60: etiquetas del re-etiquetado por medianas (criterio D4).
# COM-60 (trazabilidad): etiquetas anteriores comentadas:
# CODIGO_ETIQUETA = {1: 'Anti-Anemia Premium', 2: 'Fortalecimiento Balanceado',
#                    3: 'Ligero y Saludable', 4: 'All-Rounder Económico'}
CODIGO_ETIQUETA = {
    1: 'Anti-Anemia (alto hierro)',
    2: 'Energético denso',
    3: 'Proteico balanceado',
    4: 'Ligero complementario',
}

RANDOM_STATE = 42
N_INIT = 10
# COM-60: rango del diagnóstico de k óptimo (informativo, no cambia el k operativo)
K_DIAG_MIN = 2
K_DIAG_MAX = 8
# COM-72: tamaño mínimo deseado por cluster para auditar singletons
KMEANS_MIN_CLUSTER_RECETAS = 2
# COM-72: transformación del espacio de features (log1p antes de RobustScaler)
TRANSFORM = 'log1p+RobustScaler'

# COM-5 v4: listas POR DEFECTO (fallback si el parámetro no existe o es inválido).
# COM-72: se conservan EXACTAMENTE los defaults vigentes en disco (incluyen res/cerdo
# como permitidas y solo 'jamonada' vetada), decisión de negocio del comedor.
PROTEINAS_PERMITIDAS_DEFAULT = [
    'pollo', 'gallina', 'huevo', 'higado', 'pescado',
    'atun', 'bonito', 'jurel', 'caballa', 'trucha', 'sangrecita',
    'bofe', 'mondongo', 'lengua', 'res', 'chancho', 'cerdo', 'chicharron'
]
INGREDIENTES_VETADOS_DEFAULT = [
    'jamonada',
]

# COM-5 v4 (trazabilidad): expresiones regulares FIJAS de COM-5 v1-v3, comentadas.
# La configuración operativa ahora vive en parametros_sistema y se compila en
# cargar_reglas_proteinas(); estos patrones quedan solo como documentación del default.
# RE_PROTEINA_PERMITIDA = re.compile(
#     r'\b(pollo|gallina|huevo|higado|pescado|atun|bonito|jurel|caballa|trucha|sangrecita)\b')
# RE_PROHIBIDO = re.compile(
#     r'\b(res|vaca|vacuno|cerdo|chancho|porcino|chorizo|salchicha|bistec|bisteck|lomo|panceta|tocino|chicharron)\b')


# ==========================================
# COM-72: TRANSFORMACIÓN DEL ESPACIO DE FEATURES
# ==========================================
def _transformar_features(X: np.ndarray) -> np.ndarray:
    """
    COM-72: log1p con clip de negativos. Comprime las colas de micronutrientes muy
    sesgados (vitamina A en µg, zinc) para que una receta extrema no se convierta en
    un cluster de un solo miembro. Monotónica y reversible con _inv_transformar_features.
    """
    return np.log1p(np.clip(X, 0.0, None))


def _inv_transformar_features(Xl: np.ndarray) -> np.ndarray:
    """COM-72: inversa de log1p para regresar centroides a unidades reales."""
    return np.expm1(Xl)


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


def _mediana(valores):
    """Mediana defensiva (lista de floats no vacía)."""
    if not valores:
        return 0.0
    return float(np.median(np.array(valores, dtype=float)))


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
    """
    Lee k y los umbrales de precio por ración desde parametros_sistema.
    COM-71: los umbrales YA NO excluyen recetas; solo etiquetan nivel_precio
    (informativo) en el snapshot.
    """
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('KMEANS_K', 'KMEANS_PRECIO_BAJO_MAX', 'KMEANS_PRECIO_MEDIO_MAX');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    k = int(float(p.get('KMEANS_K', 4)))
    bajo = float(p.get('KMEANS_PRECIO_BAJO_MAX', 2.20))
    medio = float(p.get('KMEANS_PRECIO_MEDIO_MAX', 3.50))
    return k, bajo, medio


# =========================================================================
# COM-37 v5 (trazabilidad): _precios_actuales COMENTADO. Reemplazado por
# precios_insumos.mejor_opcion_ingrediente + equivalencias de unidad de USO.
# =========================================================================
# def _precios_actuales(cur):
#     cur.execute(""" ... historial_precios último día por ingrediente ... """)
#     precios = {r['ing_id']: float(r['precio_por_kg']) for r in cur.fetchall()}
#     manuales = obtener_precios_manuales_por_kg(cur, date.today())
#     for ing_id, precio_kg in manuales.items():
#         precios.setdefault(ing_id, precio_kg)
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


def _gramos_linea(eq_map, ing_id, insumo_id, unidad_uso_id,
                  unidad_abrev, tipo_magnitud, factor_a_base, peso_estimado_g, cantidad):
    """
    COM-37 v5: gramos reales de una línea de receta: equivalencia registrada para el
    par (ingrediente, insumo elegido, unidad de uso); si no existe, conversión estándar
    de la unidad de uso (factor para masa/volumen, peso_estimado/atado/rodaja p/discretas).
    """
    g = eq_map.get((ing_id, insumo_id, unidad_uso_id))
    if g is None:
        g = gramos_por_unidad_estandar(unidad_abrev, tipo_magnitud, factor_a_base, peso_estimado_g)
    return g * float(cantidad)


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


# ==========================================
# CONSTRUCCIÓN DEL DATASET (por ración) + REGLAS R0-R2 + FLAGS COM-71
# ==========================================
def construir_dataset(cur, precio_bajo_max, precio_medio_max):
    """
    Construye el dataset POR RACIÓN de todas las recetas y aplica:
    R0 (COM-60 v2.1): SOLO recetas con los 6 nutrientes COMPLETOS (NOT NULL); las
       incompletas se EXCLUYEN con motivo auditable 'nutricion_incompleta'.
    R1/R2 (COM-5 v4): proteínas permitidas / veto configurable; EXCLUYEN.
    COM-71 (R3 eliminada): el precio YA NO excluye. nivel_precio es informativo
       (bajo/medio/alto según umbrales; 'incompleto'/'sin_precio' si no costeable).
    COM-71 (R4 como flag): si faltan fuentes de precio o el costo es 0, la receta
       NO se excluye: entra al cluster con costeable=False y el greedy la audita.
    COM-47 v3: la NUTRICIÓN se toma DIRECTA de recetas_almuerzo (ya por ración).
    Retorna (filas, excluidas).
    """
    re_permitida, re_vetada, _, _ = cargar_reglas_proteinas(cur)
    unidades = _cargar_unidades(cur)
    fecha_hoy = date.today()
    precios_insumo = precios_por_gramo_por_insumo(cur, fecha_hoy, fallback_ultima_fecha=True)
    eq_map = _cargar_equivalencias(cur)
    opciones_cache = {}

    def _opcion(ing_id, peso_estimado_g):
        if ing_id not in opciones_cache:
            opciones_cache[ing_id] = _opcion_con_prediccion(
                cur, ing_id, fecha_hoy, precios_insumo, peso_estimado_g)
        return opciones_cache[ing_id]

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

    cols_p = _columnas(cur, puente)
    col_rec = _col(cols_p, ['receta_id', 'receta', 'id_receta'], contiene='recet')
    col_ing = _col(cols_p, ['ingrediente_id', 'ingrediente', 'catalogo_id', 'alimento_id', 'insumo_id', 'food_id'],
                   contiene='ingred') or _col(cols_p, [], contiene='alimento') or _col(cols_p, [], contiene='insumo')
    col_cant = _col(cols_p, ['cantidad', 'cant', 'cantidad_por_racion'], contiene='cant')
    col_unid = _col(cols_p, ['unidad_medida_id', 'unidad_id', 'unidad', 'umed_id', 'id_unidad'], contiene='unid')
    if not col_rec or not col_ing or not col_cant:
        raise ValueError(f"La tabla puente '{puente}' no tiene columnas reconocibles de receta/ingrediente/cantidad: {cols_p}")

    cols_c = _columnas(cur, catalogo)
    col_cat_nom = _col(cols_c, ['nombre', 'nombre_normalizado', 'name'], contiene='nombr') or \
        _col(cols_c, ['descripcion'], contiene='desc')
    if not col_cat_nom:
        raise ValueError(f"El catálogo '{catalogo}' no tiene columna de nombre reconocible: {cols_c}")

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

    # COM-5 v5 (FIX): detección de columnas nutricionales base.
    col_r_hie = _col(cols_r, ['hierro_mg', 'hierro'], contiene='hierro')
    col_r_pro = _col(cols_r, ['proteina_g', 'proteina'], contiene='proteina')
    col_r_ene = _col(cols_r, ['energia_kcal', 'energia'], contiene='energia')
    if not (col_r_hie and col_r_pro and col_r_ene):
        raise ValueError(
            f"La tabla de recetas '{recetas_tabla}' no tiene columnas nutricionales "
            f"(hierro_mg / proteina_g / energia_kcal). Columnas detectadas: {cols_r}")
    # COM-60: columnas de micronutrientes para las 6 features (R0 exige NOT NULL)
    col_r_vita = _col(cols_r, ['vitamina_a_ug', 'vitamina_a'], contiene='vitamina_a')
    col_r_zinc = _col(cols_r, ['zinc_mg', 'zinc'], contiene='zinc')
    col_r_carb = _col(cols_r, ['carbohidratos_g', 'carbohidratos'], contiene='carbohidr')
    sel_nut = (f", {col_r_hie} AS hierro_mg, {col_r_pro} AS proteina_g, {col_r_ene} AS energia_kcal"
               f", {col_r_vita if col_r_vita else 'NULL'} AS vitamina_a_ug"
               f", {col_r_zinc if col_r_zinc else 'NULL'} AS zinc_mg"
               f", {col_r_carb if col_r_carb else 'NULL'} AS carbohidratos_g")
    sel_rac = f"{col_r_rac} AS raciones" if col_r_rac else "NULL AS raciones"
    cur.execute(f"SELECT id, {col_r_nom} AS nombre, {sel_rac}{sel_nut} FROM {recetas_tabla}{filtro_estado};")
    recetas = cur.fetchall()

    sel_unid = f"ri.{col_unid} AS unidad_id," if col_unid else "NULL AS unidad_id,"
    if col_unid:
        cur.execute(f"""
            SELECT ri.{col_rec} AS receta_id, ri.{col_cant} AS cantidad, {sel_unid}
                   ci.id AS ing_id, ci.{col_cat_nom} AS ing_nombre,
                   um2.abreviatura AS unidad_abrev, um2.tipo_magnitud, um2.factor_a_base,
                   ci.peso_estimado_g,
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
                   um2.abreviatura AS unidad_abrev, um2.tipo_magnitud, um2.factor_a_base,
                   ci.peso_estimado_g,
                   ca.nombre AS categoria
            FROM {puente} ri
            JOIN {catalogo} ci ON ci.id = ri.{col_ing}
            LEFT JOIN unidades_medida um2 ON um2.id = ci.unidad_medida_id
            LEFT JOIN categorias_alimentos ca ON ca.id = ci.categoria_id
        """)

    costo_acum = {}
    nombres_acum = {}
    sin_precio_acum = {}
    for fila in cur.fetchall():
        opc = _opcion(fila['ing_id'], fila['peso_estimado_g'])
        if opc is None:
            sin_precio_acum.setdefault(fila['receta_id'], []).append(fila['ing_nombre'])
        else:
            gramos = _gramos_linea(
                eq_map, fila['ing_id'], opc['insumo_id'], fila['unidad_id'],
                fila['unidad_abrev'], fila['tipo_magnitud'], fila['factor_a_base'],
                fila['peso_estimado_g'], fila['cantidad']
            )
            costo_acum[fila['receta_id']] = costo_acum.get(fila['receta_id'], 0.0) + gramos * opc['ppg']
        nombres_acum.setdefault(fila['receta_id'], []).append({
            'nombre': fila['ing_nombre'],
            'categoria': fila['categoria'] or '',
        })

    filas = []
    excluidas = []
    for rec in recetas:
        # COM-60 v2.1 (R0): universo = recetas con los 6 nutrientes COMPLETOS.
        if any(rec.get(c) is None for c in
               ('energia_kcal', 'hierro_mg', 'proteina_g', 'vitamina_a_ug', 'zinc_mg', 'carbohidratos_g')):
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'],
                              'motivo': 'nutricion_incompleta'})
            continue
        items = nombres_acum.get(rec['id'], [])
        if not items:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_ingredientes'})
            continue
        tiene_proteina_permitida = False
        motivo_exclusion = None
        for ing in items:
            nombre_norm = _normalizar(ing['nombre'])
            if re_permitida.search(nombre_norm):
                tiene_proteina_permitida = True
            elif re_vetada.search(nombre_norm):
                motivo_exclusion = motivo_exclusion or 'contiene_ingrediente_vetado'
        rac = float(rec['raciones']) if rec['raciones'] else 4.0
        costo_total = costo_acum.get(rec['id'], 0.0)
        if motivo_exclusion:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': motivo_exclusion})
            continue
        if not tiene_proteina_permitida:
            excluidas.append({'receta_id': rec['id'], 'nombre': rec['nombre'], 'motivo': 'sin_proteina_permitida'})
            continue
        # ==================================================================
        # COM-71: R3/R4 ya NO excluyen. Se calcula el FLAG costeable y el
        # nivel_precio INFORMATIVO. Trazabilidad del bloque excluyente anterior:
        #   if costo_total <= 0:
        #       excluidas.append({... 'motivo': 'sin_precio'}); continue
        #   faltantes_precio = sin_precio_acum.get(rec['id'])
        #   if faltantes_precio:
        #       excluidas.append({... 'motivo': 'precio_incompleto', ...}); continue
        #   precio_racion = costo_total / rac
        #   if precio_racion > precio_medio_max:
        #       excluidas.append({... 'motivo': 'precio_alto'}); continue
        # ==================================================================
        faltantes_precio = sin_precio_acum.get(rec['id'])
        costeable = (not faltantes_precio) and costo_total > 0
        precio_racion = (costo_total / rac) if costo_total > 0 else 0.0
        if not costeable:
            nivel = 'incompleto' if faltantes_precio else 'sin_precio'
        elif precio_racion <= precio_bajo_max:
            nivel = 'bajo'
        elif precio_racion <= precio_medio_max:
            nivel = 'medio'
        else:
            nivel = 'alto'  # COM-71: 'alto' ya NO excluye; solo informa
        filas.append({
            'receta_id': rec['id'],
            'nombre': rec['nombre'],
            # COM-47 v3: nutrición POR RACIÓN tal como se capturó (sin dividir).
            # COM-47 v2 (trazabilidad): división entre raciones COMENTADA:
            # 'energia_kcal': round(float(rec['energia_kcal'] or 0) / rac, 2),
            # 'hierro_mg': round(float(rec['hierro_mg'] or 0) / rac, 2),
            # 'proteina_g': round(float(rec['proteina_g'] or 0) / rac, 2),
            'energia_kcal': round(float(rec['energia_kcal']), 2),
            'hierro_mg': round(float(rec['hierro_mg']), 2),
            'proteina_g': round(float(rec['proteina_g']), 2),
            'vitamina_a_ug': round(float(rec['vitamina_a_ug']), 2),
            'zinc_mg': round(float(rec['zinc_mg']), 2),
            'carbohidratos_g': round(float(rec['carbohidratos_g']), 2),
            'fibra_g': 0.0,
            'precio_soles': round(precio_racion, 2),
            'nivel_precio': nivel,
            # COM-71: flag de elegibilidad económica (R4 como flag)
            'costeable': bool(costeable),
            'ingredientes_sin_precio': sorted(set(faltantes_precio or [])),
            'ingredientes': items,
            'campos_imputados': [],
        })

    # COM-60 v2.1 (trazabilidad): imputación por MEDIANA de COM-60 v2 RETIRADA.
    # for campo in ('vitamina_a_ug', 'zinc_mg', 'carbohidratos_g'):
    #     presentes = [f[campo] for f in filas if f[campo] is not None]
    #     med = _mediana(presentes) if presentes else 0.0
    #     for f in filas:
    #         if f[campo] is None:
    #             f[campo] = round(med, 2); f['campos_imputados'].append(campo)
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
# COM-60: RE-ETIQUETADO DETERMINISTA POR MEDIANAS REALES
# ==========================================
def _medianas_por_indice(filas, labels):
    """
    {indice_cluster: {feature: mediana}} con las 6 variables + precio.
    COM-71: la mediana de precio se calcula SOLO sobre miembros costeables para no
    sesgar con ceros de recetas sin precio; si el cluster no tiene costeables, 0.0.
    """
    grupos = {}
    for f, lab in zip(filas, labels):
        grupos.setdefault(lab, []).append(f)
    out = {}
    for idx, miembros in grupos.items():
        costeables = [m for m in miembros if m.get('costeable', True)]
        out[idx] = {
            'energia_kcal': _mediana([m['energia_kcal'] for m in miembros]),
            'hierro_mg': _mediana([m['hierro_mg'] for m in miembros]),
            'proteina_g': _mediana([m['proteina_g'] for m in miembros]),
            'vitamina_a_ug': _mediana([m['vitamina_a_ug'] for m in miembros]),
            'zinc_mg': _mediana([m['zinc_mg'] for m in miembros]),
            'carbohidratos_g': _mediana([m['carbohidratos_g'] for m in miembros]),
            'precio_soles': _mediana([m['precio_soles'] for m in costeables]) if costeables else 0.0,
            'n_recetas': len(miembros),
            'n_costeables': len(costeables),
        }
    return out


def _etiquetar_por_medianas(medianas_por_indice):
    """
    COM-60 (criterio D4): biyección determinista indice->código sobre MEDIANAS reales:
    1) mayor mediana de hierro -> Anti-Anemia (alto hierro)
    2) mayor mediana de energía entre restantes -> Energético denso
    3) mayor mediana de proteína entre restantes -> Proteico balanceado
    4) restante -> Ligero complementario
    """
    idx = list(medianas_por_indice.keys())
    asignacion = {}
    i_anemia = max(idx, key=lambda i: medianas_por_indice[i]['hierro_mg'])
    asignacion[i_anemia] = 1
    idx.remove(i_anemia)
    i_energia = max(idx, key=lambda i: medianas_por_indice[i]['energia_kcal'])
    asignacion[i_energia] = 2
    idx.remove(i_energia)
    i_proteina = max(idx, key=lambda i: medianas_por_indice[i]['proteina_g'])
    asignacion[i_proteina] = 3
    idx.remove(i_proteina)
    asignacion[idx[0]] = 4
    return asignacion


# =========================================================================
# COM-60 (trazabilidad): etiquetado v1 SOBRE ESPACIO ESTANDARIZADO, COMENTADO.
# =========================================================================
# def _etiquetar_centroides(centros_estandarizados): ... (índices fijos de columnas z)


# ==========================================
# COM-60 + COM-71: MÉTRICAS POST-HOC POR CLUSTER (precio fuera del clustering)
# ==========================================
def _post_hoc_por_indice(filas, labels):
    """
    {indice: {precio_mediano, fe_por_sol, proteina_por_sol, n_costeables}}.
    COM-71: se calcula SOLO sobre miembros costeables (guard de división y de conjunto
    vacío -> None), para que el indicador Fe/S/ refleje precios reales del comedor.
    """
    grupos = {}
    for f, lab in zip(filas, labels):
        grupos.setdefault(lab, []).append(f)
    out = {}
    for idx, miembros in grupos.items():
        costeables = [m for m in miembros if m.get('costeable', True)]
        if not costeables:
            out[idx] = {'precio_mediano': None, 'fe_por_sol': None,
                        'proteina_por_sol': None, 'n_costeables': 0}
            continue
        precio_med = _mediana([m['precio_soles'] for m in costeables])
        fe_med = _mediana([m['hierro_mg'] for m in costeables])
        pro_med = _mediana([m['proteina_g'] for m in costeables])
        out[idx] = {
            'precio_mediano': round(precio_med, 2),
            'fe_por_sol': round(fe_med / precio_med, 3) if precio_med > 0 else None,
            'proteina_por_sol': round(pro_med / precio_med, 3) if precio_med > 0 else None,
            'n_costeables': len(costeables),
        }
    return out


# ==========================================
# COM-60 + COM-72: DIAGNÓSTICO DE K ÓPTIMO (informativo, espacio log1p)
# ==========================================
def diagnosticar_k(cur, k_max=K_DIAG_MAX):
    """
    COM-60 (criterio D5) + COM-72: curva silhouette/inercia k=2..k_max sobre el
    dataset apto en espacio log1p+RobustScaler. Devuelve k_recomendado (mejor
    silhouette). NO persiste nada ni cambia el k operativo (KMEANS_K).
    """
    k_operativo, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)
    n = len(filas)
    if n < 3:
        raise ValueError(
            f"Solo {n} recetas aptas para diagnosticar k (mínimo 3). "
            f"Cargue precios/nutrición o amplíe el recetario.")
    X = _transformar_features(np.array([[f[c] for c in FEATURES] for f in filas], dtype=float))
    scaler = RobustScaler()
    Xs = scaler.fit_transform(X)
    tope = min(k_max, n - 1)
    curva = []
    for kk in range(K_DIAG_MIN, tope + 1):
        km = KMeans(n_clusters=kk, random_state=RANDOM_STATE, n_init=N_INIT)
        lab = km.fit_predict(Xs)
        sil = 0.0
        if len(set(lab)) > 1 and n > len(set(lab)):
            sil = float(silhouette_score(Xs, lab))
        curva.append({'k': kk, 'silhouette': round(sil, 4), 'inercia': round(float(km.inertia_), 4)})
    recomendado = max(curva, key=lambda c: c['silhouette'])['k'] if curva else k_operativo
    return {
        'k_operativo': k_operativo,
        'k_recomendado': recomendado,
        'curva': curva,
        'n_recetas_aptas': n,
        'n_excluidas': len(excluidas),
        'scaler': 'RobustScaler',
        'transform': TRANSFORM,
        'features': FEATURES,
        'nota': ("El k operativo se mantiene por regla de negocio (KMEANS_K); la curva es "
                 "informativa para el comité de menú y la tesis."),
    }


# ==========================================
# ENTRENAMIENTO Y PERSISTENCIA (COM-72: espacio log1p)
# ==========================================
def entrenar_y_persistir(cur):
    """
    COM-71 + COM-72: pipeline completo: dataset (R0-R2 + flags R3/R4) -> log1p ->
    RobustScaler -> K-means(k=KMEANS_K) -> re-etiquetado por medianas -> métricas
    post-hoc (solo costeables) -> diagnóstico de k -> persistencia del modelo activo
    y su asignación receta->cluster (incluye costeable).
    COM-5 v6: centroides en UNIDADES REALES (inverse_transform + expm1 en COM-72).
    COM-37 v5-fix: silhouette solo si n_samples > n_clusters.
    COM-72: agrega tamanos_clusters y aviso_clusters_pequenos (singletons auditados).
    Retorna el resumen del entrenamiento (dict). El caller gestiona el commit.
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)
    n_no_costeables = sum(1 for f in filas if not f.get('costeable', True))
    if len(filas) < k:
        n_nut = sum(1 for e in excluidas if e.get('motivo') == 'nutricion_incompleta')
        raise ValueError(
            f"Solo {len(filas)} recetas con nutrición completa para k={k} ({n_nut} "
            f"excluidas por nutrición incompleta). Complete los 6 nutrientes o amplíe "
            f"el recetario. (Las recetas sin precio NO se excluyen: quedan costeable=False.)")
    # COM-72: log1p antes de RobustScaler (trazabilidad: antes solo RobustScaler)
    X = _transformar_features(np.array([[f[c] for c in FEATURES] for f in filas], dtype=float))
    scaler = RobustScaler()
    Xs = scaler.fit_transform(X)
    # COM-60 (trazabilidad): línea anterior sin log1p:
    # Xs = scaler.fit_transform(np.array([[f[c] for c in FEATURES] for f in filas], dtype=float))

    # COM-60: diagnóstico de k óptimo (informativo, se persiste en parametros)
    curva_k = []
    k_recomendado = k
    try:
        diag = diagnosticar_k(cur)
        curva_k = diag['curva']
        k_recomendado = diag['k_recomendado']
    except Exception as e:
        print(f"[COM-60] No se pudo calcular el diagnóstico de k: {e}")

    km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
    labels = km.fit_predict(Xs)
    inercia = float(km.inertia_)
    n_clusters_obtenidos = len(set(labels))
    if n_clusters_obtenidos > 1 and Xs.shape[0] > n_clusters_obtenidos:
        silhouette = float(silhouette_score(Xs, labels))
    else:
        silhouette = 0.0

    medianas_idx = _medianas_por_indice(filas, labels)
    asignacion = _etiquetar_por_medianas(medianas_idx)
    post_hoc_idx = _post_hoc_por_indice(filas, labels)

    # COM-72: centroides log-espacio -> unidades reales con expm1
    centros_log = scaler.inverse_transform(km.cluster_centers_)
    centros_crudos = _inv_transformar_features(centros_log)
    centroides = {}
    centroides_robustos = {}
    for i, codigo in asignacion.items():
        centroides[str(codigo)] = {
            FEATURES[j]: round(float(centros_crudos[i][j]), 2) for j in range(len(FEATURES))
        }
        centroides_robustos[str(codigo)] = {
            FEATURES[j]: round(float(km.cluster_centers_[i][j]), 4) for j in range(len(FEATURES))
        }
    etiquetas = {str(c): CODIGO_ETIQUETA[c] for c in asignacion.values()}

    medianas_por_codigo = {}
    post_hoc_por_codigo = {}
    for idx, codigo in asignacion.items():
        medianas_por_codigo[str(codigo)] = medianas_idx[idx]
        post_hoc_por_codigo[str(codigo)] = post_hoc_idx[idx]

    # COM-72: auditoría de tamaños de cluster (singletons)
    tamanos = {}
    for f, lab in zip(filas, labels):
        codigo = asignacion[lab]
        tamanos[codigo] = tamanos.get(codigo, 0) + 1
    aviso_pequenos = sorted([c for c, n in tamanos.items() if n < KMEANS_MIN_CLUSTER_RECETAS])

    cur.execute("UPDATE kmeans_modelos SET activo = FALSE WHERE activo = TRUE;")
    parametros = {
        'features': FEATURES,
        'random_state': RANDOM_STATE,
        'n_init': N_INIT,
        'precio_bajo_max': bajo_max,
        'precio_medio_max': medio_max,
        # COM-71: R3 informativa y R4 como flag (antes excluían del dataset)
        'reglas': ['R0_seis_nutrientes_completos_COM60v2.1', 'R1_proteina_permitida',
                   'R2_veto_configurable', 'R3_nivel_precio_informativo_COM71',
                   'R4_flag_costeable_COM71'],
        # COM-60: auditoría del modelo v2
        'scaler': 'RobustScaler',
        'transform': TRANSFORM,  # COM-72
        'centroides_z': centroides_robustos,  # clave histórica conservada (ahora robusta/log)
        'centroides_robustos': centroides_robustos,
        'k_evaluados': curva_k,
        'k_recomendado': k_recomendado,
        'n_imputadas': 0,  # COM-60 v2.1: ya no se imputa (R0); clave conservada en 0
        'medianas_por_cluster': medianas_por_codigo,
        'post_hoc_por_cluster': post_hoc_por_codigo,
        # COM-72: auditoría de singletons
        'tamanos_clusters': tamanos,
        'min_cluster_recetas': KMEANS_MIN_CLUSTER_RECETAS,
        'criterio': 'COM-72: clustering SOLO nutricional en espacio log1p+RobustScaler; '
                    'el precio no excluye (R3 informativa) y la completitud de precios es '
                    'un flag de elegibilidad (costeable) que aplica el greedy; prioridad '
                    'Anemia Cero y desempate Fe/S/ en el greedy (COM-60); holgura semanal '
                    'y stock remanente del subsidio en el greedy (COM-71).',
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
                 energia_kcal, proteina_g, hierro_mg, fibra_g,
                 vitamina_a_ug, zinc_mg, carbohidratos_g,
                 precio_soles, nivel_precio, costeable)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (modelo_id, receta_id) DO UPDATE
                SET cluster_codigo = EXCLUDED.cluster_codigo,
                    cluster_etiqueta = EXCLUDED.cluster_etiqueta,
                    costeable = EXCLUDED.costeable,
                    nivel_precio = EXCLUDED.nivel_precio,
                    precio_soles = EXCLUDED.precio_soles;
        """, (modelo_id, f['receta_id'], codigo, CODIGO_ETIQUETA[codigo],
              f['energia_kcal'], f['proteina_g'], f['hierro_mg'], f['fibra_g'],
              f['vitamina_a_ug'], f['zinc_mg'], f['carbohidratos_g'],
              f['precio_soles'], f['nivel_precio'], f['costeable']))

    resumen_clusters = []
    for codigo in sorted(CODIGO_ETIQUETA.keys()):
        miembros = [f for f, lab in zip(filas, labels) if asignacion[lab] == codigo]
        resumen_clusters.append({
            'codigo': codigo,
            'etiqueta': CODIGO_ETIQUETA[codigo],
            'n_recetas': len(miembros),
            'n_costeables': sum(1 for m in miembros if m.get('costeable', True)),
            'centroide': centroides[str(codigo)],
            'medianas': medianas_por_codigo[str(codigo)],
            'post_hoc': post_hoc_por_codigo[str(codigo)],
            'ejemplos': [m['nombre'] for m in miembros[:3]],
        })
    return {
        'modelo_id': modelo_id,
        'k': k,
        'n_recetas': len(filas),
        'n_excluidas': len(excluidas),
        'inercia': round(inercia, 4),
        'silhouette': round(silhouette, 4),
        'scaler': 'RobustScaler',
        'transform': TRANSFORM,
        'features': FEATURES,
        'k_recomendado': k_recomendado,
        'k_evaluados': curva_k,
        'n_imputadas': 0,
        'n_excluidas_nutricion_incompleta': sum(1 for e in excluidas if e.get('motivo') == 'nutricion_incompleta'),
        # COM-71: auditoría de elegibilidad económica (ya no es exclusión del modelo)
        'n_costeables': len(filas) - n_no_costeables,
        'n_no_costeables': n_no_costeables,
        # COM-72: auditoría de singletons
        'tamanos_clusters': tamanos,
        'aviso_clusters_pequenos': aviso_pequenos,
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
    """Recetas asignadas al modelo (opcionalmente filtradas por cluster). COM-71: costeable."""
    tablas = _tablas_public(cur)
    puente = _detectar_puente(cur, tablas)
    recetas_tabla = _detectar_recetas(cur, tablas, puente)
    cols_r = _columnas(cur, recetas_tabla)
    col_r_nom = _col(cols_r, ['nombre', 'nombre_receta', 'plato', 'titulo'], contiene='nombr')
    query = f"""
        SELECT rc.receta_id, rc.cluster_codigo, rc.cluster_etiqueta,
               rc.energia_kcal, rc.proteina_g, rc.hierro_mg, rc.fibra_g,
               rc.vitamina_a_ug, rc.zinc_mg, rc.carbohidratos_g,
               rc.precio_soles, rc.nivel_precio, rc.costeable, r.{col_r_nom} AS nombre
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
    Transparencia del modelo: recetas aptas (con flag costeable) y excluidas con su
    motivo (R0/R1/R2), recalculadas con los parámetros vigentes (sin persistir nada).
    COM-71: agrega n_costeables / n_no_costeables y el detalle de ingredientes sin
    precio en cada fila apta no costeable.
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)
    return {
        'k': k,
        'aptas': filas,
        'excluidas': excluidas,
        'n_costeables': sum(1 for f in filas if f.get('costeable', True)),
        'n_no_costeables': sum(1 for f in filas if not f.get('costeable', True)),
    }