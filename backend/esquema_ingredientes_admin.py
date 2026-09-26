"""
esquema_ingredientes_admin.py
Objetivo: COM-37: esquema y seeds del módulo "Gestión de Ingredientes" (exclusivo del
          Administrador de Sistemas): tabla de precios promedio manuales con vigencia
          por ingrediente, y el módulo de vista 'gestion_ingredientes' ligado al rol
          Administrador de Sistemas en la matriz de permisos (COM-25).
Uso: Importado por db_bootstrap.py, que ejecuta aplicar_esquema_ingredientes_admin(cur).
Nota: Idempotente (IF NOT EXISTS / ON CONFLICT DO NOTHING / NOT EXISTS). No modifica
      tablas existentes: ingredientes y unidades_medida se conservan intactas.
Referencia: ticket COM-37 (solo trazabilidad).
"""

# =========================================================================
# DDL: precios promedio manuales con vigencia (fallback del scraper/RF)
# =========================================================================
DDL_INGREDIENTES_PRECIOS_MANUALES = """
CREATE TABLE IF NOT EXISTS ingredientes_precios_manuales (
    id SERIAL PRIMARY KEY,
    ingrediente_id INT NOT NULL REFERENCES ingredientes(id) ON DELETE CASCADE,
    precio_por_unidad NUMERIC(10,2) NOT NULL CHECK (precio_por_unidad > 0),
    fecha_inicio DATE,
    fecha_fin DATE,
    observacion TEXT,
    creado_por INT REFERENCES usuarios(id),
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);
CREATE INDEX IF NOT EXISTS idx_precios_manuales_ing
    ON ingredientes_precios_manuales(ingrediente_id, estado_activo);
CREATE INDEX IF NOT EXISTS idx_precios_manuales_vigencia
    ON ingredientes_precios_manuales(fecha_inicio, fecha_fin);
"""

# =========================================================================
# SEED: módulo de vista exclusivo del Admin de Sistemas
# =========================================================================
SEED_MODULO_GESTION_INGREDIENTES = """
INSERT INTO modulos_sistema (clave, nombre, descripcion) VALUES
('gestion_ingredientes', 'Gestión de Ingredientes',
 'CRUD de ingredientes y precios manuales con vigencia (exclusivo Admin de Sistemas, COM-37)')
ON CONFLICT (clave) DO NOTHING;

INSERT INTO roles_modulos (rol_id, modulo_id)
SELECT r.id, m.id
FROM roles_grupo r
JOIN modulos_sistema m ON m.clave = 'gestion_ingredientes'
WHERE r.nombre ILIKE 'administrador de sistema%'
  AND NOT EXISTS (
      SELECT 1 FROM roles_modulos rm
      WHERE rm.rol_id = r.id AND rm.modulo_id = m.id
  );
"""


def aplicar_esquema_ingredientes_admin(cur):
    """
    COM-37: crea la tabla de precios manuales con vigencia y registra el módulo
    'gestion_ingredientes' para el rol Administrador de Sistemas. Idempotente.
    El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_INGREDIENTES_PRECIOS_MANUALES)
    cur.execute(SEED_MODULO_GESTION_INGREDIENTES)