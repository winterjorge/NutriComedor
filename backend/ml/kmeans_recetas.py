"""
ml/kmeans_recetas.py
Objetivo: Motor del modelo K-means del recetario (COM-5). Construye el dataset por
          ración con las 4 variables (energía kcal, hierro mg, proteína g, precio S/),
          aplica las reglas de negocio del comedor (R1 proteínas permitidas, R2 veto a
          res/cerdo, R3 sin recetas de precio alto, R4 precios completos), entrena
          K-means con k=4, etiqueta los centroides semánticamente (biyección
          determinista) y persiste el modelo activo con su asignación receta->cluster.
Historial:
 - COM-5 v1/v2/v3: reglas hardcodeadas; detección defensiva de esquema; FIX de precios
   por gramo vía insumos->historial_precios.
 - COM-5 v4: reglas R1/R2 configurables desde parametros_sistema (Admin en Clusters).
 - COM-5 v5: FIX KeyError 'energia_kcal' (columnas nutricionales en el SELECT).
 - COM-5 v6: centroides persistidos en UNIDADES REALES (inverse_transform); z-score en
   parametros.centroides_z.
 - COM-37 v2: regla R4 de PRECIOS COMPLETOS (motivo 'precio_incompleto').
 - COM-37 v5: costeo sobre precios_insumos.py (equivalencias uso->gramos + mejor insumo).
 - COM-37 v5-fix: fallback_ultima_fecha para días sin corrida del scraper; blindaje de
   silhouette_score (n_samples > n_clusters) y mensaje de error guía.
 - COM-37 v7: la predicción Random Forest cuenta como fuente de precio válida para la
   completitud (misma jerarquía que Evaluar).
 - COM-47 (este archivo): FIX de doble división nutricional. Los campos
   hierro_mg/proteina_g/energia_kcal de recetas_almuerzo YA ESTÁN POR RACIÓN; se usan
   SIN recalcular. Las líneas que los dividían entre `raciones` quedan COMENTADAS.
   Los precios y gramos de ingredientes SÍ se calculan sobre raciones (costo total de
   la preparación / raciones = costo por ración), sin cambios.
Uso: Importado por routers/kmeans.py y por ml/greedy_search.py (reglas R1/R2).
Referencia: tickets COM-5 / COM-37 / COM-47 (solo trazabilidad).
"""
import re
import json
import unicodedata
from datetime import date

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# COM-37 v5: resolución unificada de precios por insumo/ingrediente y conversión estándar
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
# CONSTRUCCIÓN DEL DATASET (por ración) + REGLAS R1-R4
# ==========================================
def construir_dataset(cur, precio_bajo_max, precio_medio_max):
    """
    Construye el dataset por ración de todas las recetas y aplica las reglas:
      R1/R2 (COM-5 v4): proteínas permitidas / veto res-cerdo, configurables.
      R3: sin recetas de precio alto (umbrales de parametros_sistema).
      R4 (COM-37 v2): PRECIOS COMPLETOS: si algún ingrediente no tiene NINGUNA fuente
          de precio (scraper día/última corrida, manual insumo, legacy ingrediente o
          predicción RF — COM-37 v7), la receta se excluye con motivo
          'precio_incompleto' y la lista de ingredientes faltantes.
    COM-37 v5: el costo por ración usa gramos de la unidad de USO (equivalencias o
    conversión estándar) × precio por gramo del MEJOR insumo del ingrediente.
    COM-47: la NUTRICIÓN (hierro/proteína/energía) se toma DIRECTA de la tabla
    recetas_almuerzo, que ya la almacena POR RACIÓN; no se divide entre raciones.
    El PRECIO sí se calcula sobre la preparación completa y se divide entre raciones.
    Retorna (filas, excluidas).
    """
    # COM-5 v4: reglas de proteínas configurables por el Admin de Sistemas
    re_permitida, re_vetada, _, _ = cargar_reglas_proteinas(cur)
    nutricion = _cargar_nutricion(cur)
    unidades = _cargar_unidades(cur)

    # COM-37 v5-fix/v7: contexto de precios y equivalencias a la fecha de hoy
    fecha_hoy = date.today()
    precios_insumo = precios_por_gramo_por_insumo(cur, fecha_hoy, fallback_ultima_fecha=True)
    eq_map = _cargar_equivalencias(cur)
    opciones_cache = {}

    def _opcion(ing_id, peso_estimado_g):
        key = (ing_id)
        if key not in opciones_cache:
            opciones_cache[key] = _opcion_con_prediccion(
                cur, ing_id, fecha_hoy, precios_insumo, peso_estimado_g)
        return opciones_cache[key]

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
    col_r_hie = _col(cols_r, ['hierro_mg', 'hierro'], contiene='hierro')
    col_r_pro = _col(cols_r, ['proteina_g', 'proteina'], contiene='proteina')
    col_r_ene = _col(cols_r, ['energia_kcal', 'energia'], contiene='energia')
    if not (col_r_hie and col_r_pro and col_r_ene):
        raise ValueError(
            f"La tabla de recetas '{recetas_tabla}' no tiene columnas nutricionales "
            f"(hierro_mg / proteina_g / energia_kcal). Columnas detectadas: {cols_r}")
    sel_nut = f", {col_r_hie} AS hierro_mg, {col_r_pro} AS proteina_g, {col_r_ene} AS energia_kcal"

    sel_rac = f"{col_r_rac} AS raciones" if col_r_rac else "NULL AS raciones"

    # COM-5 v5 (trazabilidad): SELECT anterior COMENTADO (sin columnas nutricionales).
    # cur.execute(f"SELECT id, {col_r_nom} AS nombre, {sel_rac} FROM {recetas_tabla}{filtro_estado};")
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
    # COM-37 v2: ingredientes SIN precio por receta (motivo 'precio_incompleto')
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
        # COM-5 v5: recetas sin nutrición cargada se omiten del modelo.
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

        # COM-5 v5 (trazabilidad): bloque muerto COMENTADO (match nutricional por nombre).
        # suma = {'energia': 0.0, 'proteina': 0.0, 'hierro': 0.0, 'fibra': 0.0}
        # nut_match = 0
        # for ing in items:
        #     nut = _match_nutricion(_normalizar(ing['nombre']), nutricion)
        #     if nut:
        #         nut_match += 1

        # COM-47: raciones se usa SOLO para el precio (costo preparación / raciones);
        # la nutrición de la tabla ya está por ración y no se recalcula.
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

        # COM-37 v2 (R4): regla de PRECIOS COMPLETOS para el flujo del comedor
        faltantes_precio = sin_precio_acum.get(rec['id'])
        if faltantes_precio:
            excluidas.append({
                'receta_id': rec['id'],
                'nombre': rec['nombre'],
                'motivo': 'precio_incompleto',
                'ingredientes_sin_precio': sorted(set(faltantes_precio)),
            })
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
            # COM-47 (trazabilidad): división anterior entre raciones COMENTADA; los
            # valores de recetas_almuerzo YA están por ración y se usan sin recalcular:
            # 'energia_kcal': round(float(rec['energia_kcal'] or 0) / rac, 2),
            # 'hierro_mg': round(float(rec['hierro_mg'] or 0) / rac, 2),
            # 'proteina_g': round(float(rec['proteina_g'] or 0) / rac, 2),
            'energia_kcal': round(float(rec['energia_kcal'] or 0), 2),
            'hierro_mg': round(float(rec['hierro_mg'] or 0), 2),
            'proteina_g': round(float(rec['proteina_g'] or 0), 2),
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
    COM-37 v5-fix: silhouette solo se calcula si n_samples > n_clusters.
    COM-47: el dataset nutricional proviene directo de la tabla (ya por ración).
    Retorna el resumen del entrenamiento (dict). El caller gestiona el commit.
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)

    if len(filas) < k:
        n_inc = sum(1 for e in excluidas if e.get('motivo') == 'precio_incompleto')
        raise ValueError(
            f"Solo {len(filas)} recetas aptas para k={k} ({n_inc} excluidas por precio "
            f"incompleto). Cargue precios manuales en Gestión de Ingredientes, espere la "
            f"corrida del scraper o amplíe el recetario.")

    X = np.array([[f['energia_kcal'], f['hierro_mg'], f['proteina_g'], f['precio_soles']] for f in filas])
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
    labels = km.fit_predict(Xs)

    inercia = float(km.inertia_)
    # COM-37 v5-fix (trazabilidad): línea anterior COMENTADA (crash con n_samples <= k):
    # silhouette = float(silhouette_score(Xs, labels)) if len(set(labels)) > 1 else 0.0
    n_clusters_obtenidos = len(set(labels))
    if n_clusters_obtenidos > 1 and Xs.shape[0] > n_clusters_obtenidos:
        silhouette = float(silhouette_score(Xs, labels))
    else:
        silhouette = 0.0

    asignacion = _etiquetar_centroides(km.cluster_centers_)

    # COM-5 v6 (FIX UX): centroides en UNIDADES REALES por ración para la UI.
    centros_crudos = scaler.inverse_transform(km.cluster_centers_)
    centroides = {}
    centroides_z = {}
    for i, codigo in asignacion.items():
        # COM-5 v6 (trazabilidad): bloque anterior COMENTADO (guardaba espacio z).
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
        'reglas': ['R1_proteina_permitida', 'R2_veto_res_cerdo', 'R3_sin_precio_alto',
                   'R4_precios_completos_COM37v2'],
        # COM-5 v6: espacio z conservado para auditoría.
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
        # COM-37 v2: resumen rápido de excluidas por precio incompleto
        'n_excluidas_precio_incompleto': sum(1 for e in excluidas if e.get('motivo') == 'precio_incompleto'),
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
    Transparencia del modelo: recetas aptas y excluidas con su motivo (incluye
    'precio_incompleto' con la lista de ingredientes sin precio, COM-37 v2),
    recalculadas con los parámetros vigentes (sin persistir nada).
    """
    k, bajo_max, medio_max = _parametros_kmeans(cur)
    filas, excluidas = construir_dataset(cur, bajo_max, medio_max)
    return {'k': k, 'aptas': filas, 'excluidas': excluidas}