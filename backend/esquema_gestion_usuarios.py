"""
esquema_gestion_usuarios.py
Objetivo: Concentrar el DDL y los seeds del módulo de gestión de usuarios:
          municipalidades, vínculo municipalidad-comedor, catálogo de privilegios con su
          asignación inicial a grupos, roles temporales con vigencia y parámetros editables
          de política de contraseñas (categoría SEGURIDAD).
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_gestion_usuarios(cur)`
     durante el startup para garantizar un esquema idempotente.
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING),
      por lo que pueden ejecutarse en cada arranque sin efectos secundarios.
Referencia: ticket COM-23 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""

# =========================================================================
# DDL: Municipalidades (registro nacional de municipalidades supervisoras)
# =========================================================================
DDL_MUNICIPALIDADES = """
CREATE TABLE IF NOT EXISTS municipalidades (
    id SERIAL PRIMARY KEY,
    departamento VARCHAR(100) NOT NULL,
    provincia VARCHAR(100) NOT NULL,
    distrito VARCHAR(100) NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    direccion TEXT,
    link_ubicacion TEXT,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE (departamento, provincia, distrito, nombre)
);
"""

# =========================================================================
# DDL: Vínculo opcional comedor -> municipalidad que lo supervisa
# =========================================================================
DDL_COMEDORES_MUNICIPALIDAD = """
ALTER TABLE comedores
ADD COLUMN IF NOT EXISTS municipalidad_id INT REFERENCES municipalidades(id);
CREATE INDEX IF NOT EXISTS idx_comedores_municipalidad ON comedores(municipalidad_id);
"""

# =========================================================================
# DDL: Catálogo de privilegios del sistema y su asignación a grupos
# =========================================================================
DDL_PRIVILEGIOS = """
CREATE TABLE IF NOT EXISTS privilegios (
    id SERIAL PRIMARY KEY,
    clave VARCHAR(80) NOT NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

DDL_GRUPOS_PRIVILEGIOS = """
CREATE TABLE IF NOT EXISTS grupos_privilegios (
    id SERIAL PRIMARY KEY,
    grupo_id INT NOT NULL REFERENCES grupos_usuario(id) ON DELETE CASCADE,
    privilegio_id INT NOT NULL REFERENCES privilegios(id) ON DELETE CASCADE,
    UNIQUE (grupo_id, privilegio_id)
);
CREATE INDEX IF NOT EXISTS idx_grupos_privilegios_grupo ON grupos_privilegios(grupo_id);
"""

# =========================================================================
# SEED: Catálogo cerrado de privilegios del sistema
# =========================================================================
SEED_PRIVILEGIOS = """
INSERT INTO privilegios (clave, nombre, descripcion) VALUES
('GESTION_MUNICIPALIDADES', 'Gestión de Municipalidades', 'Crear y editar municipalidades del registro nacional.'),
('GESTION_COMEDORES', 'Gestión de Comedores', 'Crear y editar comedores a nivel nacional.'),
('GESTION_GRUPOS', 'Gestión de Grupos y Privilegios', 'Crear grupos y asignarles privilegios.'),
('GESTION_USUARIOS', 'Gestión de Usuarios (Global)', 'Crear usuarios y bloquear/desbloquear cuentas.'),
('GESTION_POLITICAS_CLAVE', 'Políticas de Contraseñas', 'Modificar longitud, expiración e intentos de clave.'),
('GESTION_USUARIOS_COMEDOR', 'Gestión de Usuarios de Comedor', 'Activar/desactivar usuarios, modificar grupos, otorgar roles temporales y desbloquear por intentos en el comedor.'),
('REPORTES', 'Reportería', 'Generar y consultar reportes del sistema.'),
('AUDITORIA', 'Auditoría', 'Consultar auditoría y trazabilidad de operaciones.')
ON CONFLICT (clave) DO NOTHING;
"""

# =========================================================================
# SEED: Asignación inicial de privilegios por grupo
#   - Administrador de Sistemas: todos.
#   - Administrativo (municipal): reportería, auditoría y gestión de usuarios de comedor.
#   - Directivo (comedor): gestión de usuarios de su comedor.
# =========================================================================
SEED_GRUPOS_PRIVILEGIOS = """
INSERT INTO grupos_privilegios (grupo_id, privilegio_id)
SELECT g.id, p.id
FROM grupos_usuario g
CROSS JOIN privilegios p
WHERE g.nombre = 'Administrador de Sistemas'
   OR (g.nombre = 'Administrativo' AND p.clave IN ('REPORTES', 'AUDITORIA', 'GESTION_USUARIOS_COMEDOR'))
   OR (g.nombre = 'Directivo' AND p.clave IN ('GESTION_USUARIOS_COMEDOR'))
ON CONFLICT (grupo_id, privilegio_id) DO NOTHING;
"""

# =========================================================================
# DDL: Roles temporales con vigencia
# Permiten que un usuario asuma un rol de su comedor por tiempo definido
# (ej. el tesorero asume al presidente durante un viaje).
# =========================================================================
DDL_ROLES_TEMPORALES = """
CREATE TABLE IF NOT EXISTS roles_temporales (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    comedor_id INT NOT NULL REFERENCES comedores(id) ON DELETE CASCADE,
    rol_id INT NOT NULL REFERENCES roles_grupo(id) ON DELETE CASCADE,
    otorgado_por INT REFERENCES usuarios(id),
    motivo TEXT,
    fecha_inicio TIMESTAMP NOT NULL,
    fecha_fin TIMESTAMP NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE',
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    CHECK (fecha_fin > fecha_inicio)
);
CREATE INDEX IF NOT EXISTS idx_roles_temporales_usuario ON roles_temporales(usuario_id, comedor_id);
CREATE INDEX IF NOT EXISTS idx_roles_temporales_estado ON roles_temporales(estado);
"""

# =========================================================================
# SEED: Parámetros editables de política de contraseñas (categoría SEGURIDAD)
# El sistema los lee con fallback a las constantes de seguridad.py.
# =========================================================================
SEED_PARAMETROS_CLAVE = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('CLAVE_LONGITUD_MIN', '8', 'Longitud mínima de contraseña (política de seguridad)', 'SEGURIDAD', 'INTEGER'),
('CLAVE_LONGITUD_MAX', '12', 'Longitud máxima de contraseña (política de seguridad)', 'SEGURIDAD', 'INTEGER'),
('CLAVE_MESES_EXPIRACION', '6', 'Meses de vigencia de la contraseña (política de seguridad)', 'SEGURIDAD', 'INTEGER'),
('CLAVE_MAX_INTENTOS', '3', 'Intentos fallidos antes de bloqueo (política de seguridad)', 'SEGURIDAD', 'INTEGER')
ON CONFLICT (clave) DO NOTHING;
"""


def aplicar_esquema_gestion_usuarios(cur):
    """
    Ejecuta en orden todo el esquema del módulo de gestión de usuarios sobre un
    cursor abierto (municipalidades, privilegios, roles temporales y parámetros
    de política de claves). El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_MUNICIPALIDADES)
    cur.execute(DDL_COMEDORES_MUNICIPALIDAD)
    cur.execute(DDL_PRIVILEGIOS)
    cur.execute(DDL_GRUPOS_PRIVILEGIOS)
    cur.execute(SEED_PRIVILEGIOS)
    cur.execute(SEED_GRUPOS_PRIVILEGIOS)
    cur.execute(DDL_ROLES_TEMPORALES)
    cur.execute(SEED_PARAMETROS_CLAVE)