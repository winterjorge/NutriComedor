"""
esquema_kmeans.py
Objetivo: DDL del módulo de clustering nutricional (COM-5): tabla de composición
          nutricional por ingrediente (por 100 g), tabla de modelos K-means entrenados
          y tabla de asignación receta->cluster con el snapshot de features.
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_kmeans(cur)`.
Nota: Sentencias idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING).
Referencia: ticket COM-5 (solo trazabilidad; los nombres obedecen a la funcionalidad).
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
    precio_soles NUMERIC(8,2) NOT NULL,
    nivel_precio VARCHAR(10) NOT NULL,
    fecha_asignacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE (modelo_id, receta_id)
);
CREATE INDEX IF NOT EXISTS idx_recetas_clusters_receta ON recetas_clusters(receta_id);
CREATE INDEX IF NOT EXISTS idx_recetas_clusters_cluster ON recetas_clusters(modelo_id, cluster_codigo);
"""

# =========================================================================
# SEED: Parámetros operativos del clustering (umbrales de precio por ración)
# =========================================================================
SEED_PARAMETROS_KMEANS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('KMEANS_K', '4', 'Número de clusters del modelo K-means de recetas', 'IA', 'INTEGER'),
('KMEANS_PRECIO_BAJO_MAX', '2.20', 'Costo máximo por ración para nivel de precio BAJO', 'IA', 'FLOAT'),
('KMEANS_PRECIO_MEDIO_MAX', '3.50', 'Costo máximo por ración para nivel MEDIO; por encima es ALTO y se excluye', 'IA', 'FLOAT')
ON CONFLICT (clave) DO NOTHING;
"""


def aplicar_esquema_kmeans(cur):
    """
    COM-5: Crea las tablas del módulo de clustering y siembra los parámetros.
    Es idempotente. El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_INGREDIENTES_NUTRICION)
    cur.execute(DDL_KMEANS_MODELOS)
    cur.execute(DDL_RECETAS_CLUSTERS)
    cur.execute(SEED_PARAMETROS_KMEANS)