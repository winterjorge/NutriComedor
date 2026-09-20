"""
esquema_permisos_vistas.py
Objetivo: Concentrar el DDL y los seeds del módulo de permisos por vistas (diferenciación
          de módulos permitidos por grupo/rol): catálogo de módulos del sistema y matriz
          de asignación rol -> módulos, con la semilla de la matriz base del negocio.
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_permisos_vistas(cur)`
     durante el startup.
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING),
      por lo que pueden ejecutarse en cada arranque sin efectos secundarios.
Referencia: ticket COM-25 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""

# =========================================================================
# DDL: Catálogo de módulos del sistema (vistas/pestañas de la aplicación)
# =========================================================================
DDL_MODULOS_SISTEMA = """
CREATE TABLE IF NOT EXISTS modulos_sistema (
    id SERIAL PRIMARY KEY,
    clave VARCHAR(60) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    descripcion TEXT,
    orden INT NOT NULL DEFAULT 0,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

# =========================================================================
# DDL: Matriz rol -> módulos permitidos.
# Un rol ya pertenece a un grupo (roles_grupo), por lo que la asignación por
# rol cubre la combinación grupo|rol definida por el negocio.
# =========================================================================
DDL_ROLES_MODULOS = """
CREATE TABLE IF NOT EXISTS roles_modulos (
    id SERIAL PRIMARY KEY,
    rol_id INT NOT NULL REFERENCES roles_grupo(id) ON DELETE CASCADE,
    modulo_id INT NOT NULL REFERENCES modulos_sistema(id) ON DELETE CASCADE,
    UNIQUE (rol_id, modulo_id)
);
CREATE INDEX IF NOT EXISTS idx_roles_modulos_rol ON roles_modulos(rol_id);
"""

# =========================================================================
# SEED: Catálogo cerrado de módulos del sistema (clave estable para el frontend)
# =========================================================================
SEED_MODULOS_SISTEMA = """
INSERT INTO modulos_sistema (clave, nombre, descripcion, orden) VALUES
('municipalidades', 'Municipalidades', 'Registro nacional de municipalidades.', 10),
('comedores', 'Comedores', 'Gestión multi-comedor y usuarios por comedor.', 20),
('grupos', 'Grupos', 'Catálogo de grupos y membresías de usuarios.', 30),
('roles', 'Roles', 'Gestión de grupos, roles y privilegios.', 40),
('bloqueos', 'Bloqueos', 'Gestión de usuarios, cuentas, bloqueos y política de claves.', 50),
('vistas', 'Vistas', 'Editor de permisos de módulos por rol.', 60),
('recetario', 'Recetario', 'Gestión de recetas del comedor.', 70),
('presupuesto', 'Presupuesto', 'Planificación presupuestal semanal.', 80),
('planificaciones', 'Planificaciones', 'Planificaciones guardadas y listas de compras.', 90),
('catalogo', 'Catálogo', 'Catálogo de insumos y precios.', 100),
('ventas', 'Ventas y Demanda', 'Punto de venta y proyección de demanda.', 110),
('reportes', 'Reportes', 'Reportes operativos y de gestión del comedor.', 120)
ON CONFLICT (clave) DO NOTHING;
"""

# =========================================================================
# SEED: Matriz base de permisos por rol (regla de negocio COM-25)
#   Administrador de Sistemas | Administrador de Sistemas -> administración global
#   Administrativo            | Auditor                    -> reportes
#   Directivo                 | Presidente                 -> recetario, reportes, catalogo
#   Directivo                 | Tesorero                   -> recetario, planificaciones,
#                                                             presupuesto, catalogo, reportes
#   Operativo                 | Cocinero                   -> planificaciones, ventas
# =========================================================================
SEED_ROLES_MODULOS = """
INSERT INTO roles_modulos (rol_id, modulo_id)
SELECT r.id, m.id
FROM roles_grupo r
JOIN grupos_usuario g ON g.id = r.grupo_id
CROSS JOIN modulos_sistema m
WHERE (g.nombre = 'Administrador de Sistemas' AND r.nombre = 'Administrador de Sistemas'
       AND m.clave IN ('municipalidades', 'comedores', 'grupos', 'roles', 'bloqueos', 'vistas'))
   OR (g.nombre = 'Administrativo' AND r.nombre = 'Auditor'
       AND m.clave IN ('reportes'))
   OR (g.nombre = 'Directivo' AND r.nombre = 'Presidente'
       AND m.clave IN ('recetario', 'reportes', 'catalogo'))
   OR (g.nombre = 'Directivo' AND r.nombre = 'Tesorero'
       AND m.clave IN ('recetario', 'planificaciones', 'presupuesto', 'catalogo', 'reportes'))
   OR (g.nombre = 'Operativo' AND r.nombre = 'Cocinero'
       AND m.clave IN ('planificaciones', 'ventas'))
ON CONFLICT (rol_id, modulo_id) DO NOTHING;
"""


def aplicar_esquema_permisos_vistas(cur):
    """
    Ejecuta en orden el esquema de permisos por vistas sobre un cursor abierto
    (catálogo de módulos + matriz rol->módulos + semillas). El caller
    (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_MODULOS_SISTEMA)
    cur.execute(DDL_ROLES_MODULOS)
    cur.execute(SEED_MODULOS_SISTEMA)
    cur.execute(SEED_ROLES_MODULOS)