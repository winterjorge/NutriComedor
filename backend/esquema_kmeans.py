"""
esquema_kmeans.py
Objetivo: DDL del módulo de clustering nutricional (COM-5): tabla de composición
nutricional por ingrediente (por 100 g), tabla de modelos K-means entrenados
y tabla de asignación receta->cluster con el snapshot de features.
Historial:
 - COM-5: versión original (3 tablas + seed de parámetros KMEANS_*).
 - COM-60 (este archivo): migración idempotente de recetas_clusters para el
   snapshot de las 6 variables nutricionales (se agregan vitamina_a_ug, zinc_mg
   y carbohidratos_g con DEFAULT 0), y seed de los parámetros nuevos del ticket:
     * KMEANS_CUOTA_CLUSTER_FEO: días mínimos/semana del cluster anti-anemia en el
       greedy (prioridad Anemia Cero fuera del clustering, criterio D3).
     * KMEANS_FE_SO_DESEMPATE: 'true' para desempatar por hierro-por-sol en el greedy.
   Nada existente se elimina; el bootstrap aplica esto en cada arranque.
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_kmeans(cur)`.
Nota: Sentencias idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING).
Referencia: tickets COM-5 / COM-60 (solo trazabilidad).
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
# SEED: Parámetros operativos del clustering (umbrales de precio por ración)
# COM-60: se agregan los parámetros de la prioridad Anemia Cero en el greedy.
# =========================================================================
SEED_PARAMETROS_KMEANS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('KMEANS_K', '4', 'Número de clusters del modelo K-means de recetas', 'IA', 'INTEGER'),
('KMEANS_PRECIO_BAJO_MAX', '2.20', 'Costo máximo por ración para nivel de precio BAJO', 'IA', 'FLOAT'),
('KMEANS_PRECIO_MEDIO_MAX', '3.50', 'Costo máximo por ración para nivel MEDIO; por encima es ALTO y se excluye', 'IA', 'FLOAT'),
('KMEANS_CUOTA_CLUSTER_FEO', '2', 'COM-60: días mínimos por semana que el greedy debe asignar al cluster Anti-Anemia', 'IA', 'INTEGER'),
('KMEANS_FE_SO_DESEMPATE', 'true', 'COM-60: true para desempatar recetas del greedy por hierro por sol (Fe/S/)', 'IA', 'BOOLEAN')
ON CONFLICT (clave) DO NOTHING;
"""


def aplicar_esquema_kmeans(cur):
    """
    COM-5 + COM-60: crea/migra las tablas del módulo de clustering y siembra los
    parámetros. Es idempotente. El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_INGREDIENTES_NUTRICION)
    cur.execute(DDL_KMEANS_MODELOS)
    cur.execute(DDL_RECETAS_CLUSTERS)
    # COM-60: migración de volúmenes existentes (columnas nuevas del snapshot)
    for sentencia in MIGRAR_RECETAS_CLUSTERS_COM60:
        cur.execute(sentencia)
    cur.execute(SEED_PARAMETROS_KMEANS)