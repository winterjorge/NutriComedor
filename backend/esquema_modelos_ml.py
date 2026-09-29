"""
esquema_modelos_ml.py
Objetivo: Seeds del incremento COM-5 v4 / COM-8 v7, endurecidos en COM-36:
          1) Parámetros de configuración del clustering: listas editables de proteínas
             permitidas e ingredientes vetados (antes hardcodeadas en el motor).
          2) Módulos de vista 'clusters' y 'modelos_ml', asignados EXCLUSIVAMENTE al rol
             Administrador de Sistemas (las vistas de clustering y el panel de gráficos
             de ML no son visibles para el resto de perfiles).
          COM-36: el enlace rol->módulo se resuelve con ILIKE 'administrador de sistema%'
          para tolerar variantes de nombre del rol, y se expone `auditar_modulos_ml(cur)`
          para que el bootstrap registre en logs cuántos enlaces quedaron vigentes
          (verificación automática en cada arranque / despliegue).
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_modelos_ml(cur)` y
     `auditar_modulos_ml(cur)` en cada arranque (idempotente).
Nota: No elimina ni modifica seeds anteriores: el módulo 'recetario' conserva sus roles
      originales; la pestaña de clusters simplemente pasa a gatearse por 'clusters'.
Referencia: tickets COM-5 v4 / COM-8 v7 / COM-36 (solo trazabilidad).
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
# COM-36: el enlace al rol usa ILIKE para tolerar 'Administrador de Sistemas' /
# 'Administrador Sistema' y NOT EXISTS para ser re-ejecutable sin duplicados.
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
WHERE r.nombre ILIKE 'administrador de sistema%'
  AND NOT EXISTS (
      SELECT 1 FROM roles_modulos rm
      WHERE rm.rol_id = r.id AND rm.modulo_id = m.id
  );
"""


def aplicar_esquema_modelos_ml(cur):
    """
    COM-5 v4 / COM-36: siembra parámetros de proteínas configurables y registra los
    módulos exclusivos del Admin de Sistemas con su enlace al rol. Idempotente: puede
    ejecutarse en cada arranque sin efectos secundarios (ON CONFLICT / NOT EXISTS).
    El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(SEED_PARAMETROS_PROTEINAS)
    cur.execute(SEED_MODULOS_ML)


def auditar_modulos_ml(cur):
    """
    COM-36: verificación automática post-seed. Retorna (modulos_ok, enlaces_ok):
      modulos_ok: número de módulos ('clusters','modelos_ml') presentes en el catálogo.
      enlaces_ok: número de enlaces rol Admin -> módulo vigentes (esperado 2).
    El bootstrap registra estos valores en los logs para detectar despliegues parciales.
    """
    cur.execute("""
        SELECT COUNT(*) AS n FROM modulos_sistema
        WHERE clave IN ('clusters', 'modelos_ml');
    """)
    modulos_ok = int(cur.fetchone()['n'])
    cur.execute("""
        SELECT COUNT(*) AS n
        FROM roles_modulos rm
        JOIN modulos_sistema m ON m.id = rm.modulo_id
        JOIN roles_grupo r ON r.id = rm.rol_id
        WHERE m.clave IN ('clusters', 'modelos_ml')
          AND r.nombre ILIKE 'administrador de sistema%';
    """)
    enlaces_ok = int(cur.fetchone()['n'])
    return modulos_ok, enlaces_ok