"""
esquema_modelos_ml.py
Objetivo: Seeds del incremento COM-5 v4 / COM-8 v7:
          1) Parámetros de configuración del clustering: listas editables de proteínas
             permitidas e ingredientes vetados (antes estaban hardcodeadas en el motor).
          2) Módulos de vista 'clusters' y 'modelos_ml', asignados EXCLUSIVAMENTE al rol
             Administrador de Sistemas (las vistas de clustering y el panel de gráficos
             de ML dejan de ser visibles para el resto de perfiles).
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_modelos_ml(cur)`.
Nota: Idempotente (ON CONFLICT DO NOTHING). No elimina ni modifica seeds anteriores:
      el módulo 'recetario' conserva sus roles originales para el recetario operativo;
      la pestaña de clusters simplemente pasa a gatearse por el módulo 'clusters'.
Referencia: tickets COM-5 v4 / COM-8 v7 (solo trazabilidad).
"""

# =========================================================================
# SEED: Listas configurables de proteínas permitidas e ingredientes vetados.
# El motor K-means las lee de parametros_sistema en cada entrenamiento; la vista
# de Clusters (Admin de Sistemas) permite editarlas sin tocar código.
# =========================================================================
SEED_PARAMETROS_PROTEINAS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('KMEANS_PROTEINAS_PERMITIDAS',
 '["pollo","gallina","huevo","higado","pescado","atun","bonito","jurel","caballa","trucha","sangrecita"]',
 'COM-5 v4: listado configurable de proteínas permitidas para el clustering K-means',
 'IA', 'JSON'),
('KMEANS_INGREDIENTES_VETADOS',
 '["res","vaca","vacuno","cerdo","chancho","porcino","chorizo","salchicha","bistec","bisteck","lomo","panceta","tocino","chicharron"]',
 'COM-5 v4: listado configurable de ingredientes vetados por presupuesto (res/cerdo y derivados)',
 'IA', 'JSON')
ON CONFLICT (clave) DO NOTHING;
"""

# =========================================================================
# SEED: Módulos exclusivos del Administrador de Sistemas para las vistas de ML.
# 'clusters'   -> pestaña Clusters K-Means (antes gateada por 'recetario').
# 'modelos_ml' -> panel de gráficos de Random Forest, K-means y Greedy Search.
# =========================================================================
SEED_MODULOS_ML = """
INSERT INTO modulos_sistema (clave, nombre, descripcion) VALUES
('clusters', 'Clusters K-Means',
 'Vista de clustering de recetas y configuración de proteínas permitidas (exclusivo Admin de Sistemas, COM-5 v4)'),
('modelos_ml', 'Modelos ML',
 'Panel de gráficos de validación de Random Forest, K-means y Greedy Search (exclusivo Admin de Sistemas, COM-5 v4)')
ON CONFLICT (clave) DO NOTHING;

INSERT INTO roles_modulos (rol_id, modulo_id)
SELECT r.id, m.id
FROM roles_grupo r
JOIN modulos_sistema m ON m.clave IN ('clusters', 'modelos_ml')
WHERE r.nombre = 'Administrador de Sistemas'
ON CONFLICT (rol_id, modulo_id) DO NOTHING;
"""


def aplicar_esquema_modelos_ml(cur):
    """
    COM-5 v4 / COM-8 v7: siembra parámetros de proteínas configurables y registra los
    módulos exclusivos del Admin de Sistemas. Idempotente. El caller hace el commit.
    """
    cur.execute(SEED_PARAMETROS_PROTEINAS)
    cur.execute(SEED_MODULOS_ML)