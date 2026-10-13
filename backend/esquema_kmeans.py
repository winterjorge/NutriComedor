"""
esquema_kmeans.py
Objetivo: DDL del módulo de clustering nutricional (COM-5): tabla de composición
nutricional por ingrediente (por 100 g), tabla de modelos K-means entrenados
y tabla de asignación receta->cluster con el snapshot de features.
Historial:
 - COM-5: versión original (3 tablas + seed de parámetros KMEANS_*).
 - COM-60: migración idempotente de recetas_clusters para el snapshot de las 6
   variables nutricionales (vitamina_a_ug, zinc_mg, carbohidratos_g con DEFAULT 0),
   y seed de KMEANS_CUOTA_CLUSTER_FEO / KMEANS_FE_SO_DESEMPATE (prioridad Anemia
   Cero y desempate Fe/S/ en el greedy).
 - COM-71 (este archivo):
   * recetas_clusters gana la columna `costeable BOOLEAN NOT NULL DEFAULT TRUE`:
     marca si la receta tenía precios completos al entrenar (R4 pasa de EXCLUSIÓN
     a FLAG de elegibilidad; el greedy no selecciona no-costeables).
   * Seed del parámetro PLANIFICACION_FLEX_DIA ('2.0'): holgura diaria del greedy
     (un día puede gastar hasta flex × (presupuesto restante / días restantes),
     siempre dentro del tope semanal). Es leído por cargar_parametros() del greedy
     porque su consulta usa LIKE 'PLANIFICACION_%'.
   * KMEANS_PRECIO_BAJO_MAX / MEDIO_MAX se conservan pero pasan a ser SOLO
     informativos (nivel_precio del snapshot); ya no excluyen recetas (R3 sale del
     clustering, criterio COM-71 D1).
   Nada existente se elimina; el bootstrap aplica esto en cada arranque.
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_kmeans(cur)`.
Nota: Sentencias idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING).
Referencia: tickets COM-5 / COM-60 / COM-71 (solo trazabilidad).
"""

# =========================================================================
# DDL: Composición nutricional por ingrediente (por cada 100 g, crudo/comercial)
# gramos_por_unidad: equivalencia en gramos cuando la unidad de la receta es "und"
# =========================================================================
DDL_INGREDIENTES_NUTRICION = """
CREATE TABLE IF NOT EXISTS ingredientes_nutricion (
    id SERIAL PRIMARY KEY,
    nombre_normalizado VARCHAR(150) NOT NULL UNIQUE,
    energia_kcal_100g NUMERIC(8,2) NOT NULL,
    proteina_g_100g NUMERIC(8,2) NOT NULL,
    hierro_mg_100g NUMERIC(8,2) NOT NULL,
    fibra_g_100g NUMERIC(8,2) NOT NULL DEFAULT 0,
    gramos_por_unidad NUMERIC(8,2) NOT NULL DEFAULT 100,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

# =========================================================================
# DDL: Modelos K-means entrenados (uno activo a la vez)
# =========================================================================
DDL_KMEANS_MODELOS = """
CREATE TABLE IF NOT EXISTS kmeans_modelos (
    id SERIAL PRIMARY KEY,
    fecha_entrenamiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    k INT NOT NULL,
    n_recetas INT NOT NULL,
    n_excluidas INT NOT NULL,
    inercia NUMERIC(12,4),
    silhouette NUMERIC(8,4),
    centroides JSONB NOT NULL,
    etiquetas JSONB NOT NULL,
    parametros JSONB NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_kmeans_modelos_activo ON kmeans_modelos(activo);
"""

# =========================================================================
# DDL: Asignación receta -> cluster (snapshot de features al entrenar)
# COM-60: el snapshot incluye las 6 variables nutricionales (antes 4 columnas).
# COM-71: columna `costeable` (flag R4; antes la receta se excluía del modelo).
# =========================================================================
DDL_RECETAS_CLUSTERS = """
CREATE TABLE IF NOT EXISTS recetas_clusters (
    id SERIAL PRIMARY KEY,
    modelo_id INT NOT NULL REFERENCES kmeans_modelos(id) ON DELETE CASCADE,
    receta_id INT NOT NULL REFERENCES recetas_almuerzo(id) ON DELETE CASCADE,
    cluster_codigo INT NOT NULL,
    cluster_etiqueta VARCHAR(60) NOT NULL,
    energia_kcal NUMERIC(8,2) NOT NULL,
    proteina_g NUMERIC(8,2) NOT NULL,
    hierro_mg NUMERIC(8,2) NOT NULL,
    fibra_g NUMERIC(8,2) NOT NULL DEFAULT 0,
    -- COM-60: snapshot de las 3 variables nutricionales adicionales (6 features)
    vitamina_a_ug NUMERIC(8,2) NOT NULL DEFAULT 0,
    zinc_mg NUMERIC(8,2) NOT NULL DEFAULT 0,
    carbohidratos_g NUMERIC(8,2) NOT NULL DEFAULT 0,
    precio_soles NUMERIC(8,2) NOT NULL,
    nivel_precio VARCHAR(10) NOT NULL,
    -- COM-71: flag de elegibilidad económica (R4 como flag, no como exclusión)
    costeable BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_asignacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE (modelo_id, receta_id)
);
CREATE INDEX IF NOT EXISTS idx_recetas_clusters_receta ON recetas_clusters(receta_id);
CREATE INDEX IF NOT EXISTS idx_recetas_clusters_cluster ON recetas_clusters(modelo_id, cluster_codigo);
"""

# =========================================================================
# COM-60: migración idempotente para volúmenes creados antes del ticket
# =========================================================================
MIGRAR_RECETAS_CLUSTERS_COM60 = [
    """
    ALTER TABLE recetas_clusters
        ADD COLUMN IF NOT EXISTS vitamina_a_ug NUMERIC(8,2) NOT NULL DEFAULT 0;
    """,
    """
    ALTER TABLE recetas_clusters
        ADD COLUMN IF NOT EXISTS zinc_mg NUMERIC(8,2) NOT NULL DEFAULT 0;
    """,
    """
    ALTER TABLE recetas_clusters
        ADD COLUMN IF NOT EXISTS carbohidratos_g NUMERIC(8,2) NOT NULL DEFAULT 0;
    """,
]

# =========================================================================
# COM-71: migración idempotente de la columna `costeable`
# =========================================================================
MIGRAR_RECETAS_CLUSTERS_COM71 = [
    """
    ALTER TABLE recetas_clusters
        ADD COLUMN IF NOT EXISTS costeable BOOLEAN NOT NULL DEFAULT TRUE;
    """,
]

# =========================================================================
# SEED: Parámetros operativos del clustering y del greedy
# COM-60: prioridad Anemia Cero y desempate Fe/S/.
# COM-71: PLANIFICACION_FLEX_DIA (holgura diaria del greedy) y actualización de la
#         descripción de los umbrales de precio (ahora solo informativos).
# =========================================================================
SEED_PARAMETROS_KMEANS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('KMEANS_K', '4', 'Número de clusters del modelo K-means de recetas', 'IA', 'INTEGER'),
('KMEANS_PRECIO_BAJO_MAX', '2.20', 'COM-71: costo por ración para nivel de precio BAJO (SOLO informativo del snapshot; ya no excluye)', 'IA', 'FLOAT'),
('KMEANS_PRECIO_MEDIO_MAX', '3.50', 'COM-71: costo por ración para nivel MEDIO; por encima ALTO (SOLO informativo; ya no excluye)', 'IA', 'FLOAT'),
('KMEANS_CUOTA_CLUSTER_FEO', '2', 'COM-60: días mínimos por semana que el greedy debe asignar al cluster Anti-Anemia', 'IA', 'INTEGER'),
('KMEANS_FE_SO_DESEMPATE', 'true', 'COM-60: true para desempatar recetas del greedy por hierro por sol (Fe/S/)', 'IA', 'BOOLEAN'),
('PLANIFICACION_FLEX_DIA', '2.0', 'COM-71: holgura diaria del greedy: un día puede gastar hasta flex × (presupuesto restante / días restantes), siempre dentro del tope semanal', 'IA', 'FLOAT')
ON CONFLICT (clave) DO NOTHING;
"""


def aplicar_esquema_kmeans(cur):
    """
    COM-5 + COM-60 + COM-71: crea/migra las tablas del módulo de clustering y siembra
    los parámetros. Es idempotente. El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_INGREDIENTES_NUTRICION)
    cur.execute(DDL_KMEANS_MODELOS)
    cur.execute(DDL_RECETAS_CLUSTERS)
    # COM-60: migración de volúmenes existentes (columnas nuevas del snapshot)
    for sentencia in MIGRAR_RECETAS_CLUSTERS_COM60:
        cur.execute(sentencia)
    # COM-71: migración de la columna costeable (flag R4)
    for sentencia in MIGRAR_RECETAS_CLUSTERS_COM71:
        cur.execute(sentencia)
    cur.execute(SEED_PARAMETROS_KMEANS)