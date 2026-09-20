"""
db_bootstrap.py
Objetivo: Asegurar que el esquema dinámico del sistema exista en la base de datos al
          arrancar la API, sin importar si el volumen de PostgreSQL fue creado antes de
          que existieran los scripts actuales (el docker-entrypoint-initdb.d solo se
          ejecuta en la PRIMERA inicialización del volumen).
Uso: Importar en main.py y ejecutar `asegurar_esquema()` durante el startup (lifespan).
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING),
      por lo que pueden ejecutarse en cada arranque sin efectos secundarios.

Historial de correcciones:
 - FIX (error 500 en /parametros y /planificar): creación de parametros_sistema (+seed),
   planificacion_dia y columnas de planificación en presupuesto_semanal.
 - FIX COM-17: columna recetas_almuerzo.raciones con valor por defecto 4.
 - COM-19 (Login): columnas de seguridad en usuarios, migración de hashes legacy a
   PBKDF2 y usuario admin de respaldo (DNI 0000000).
 - COM-21 (Multi-comedor): tablas comedores y usuario_comedor, migración de roles
   legacy a 'Administrador Sistema', comedor default y asociación inicial.
 - COM-22 (Grupos de usuario): tablas grupos_usuario, roles_grupo y usuario_grupo;
   seed del catálogo cerrado (Sistema / Administrativo / Directivo / Operativo con sus
   roles) y migración idempotente de membresías legacy de COM-21 al modelo de grupos.
"""
import time
import psycopg2
from config import DB_URL
from seguridad import (
    hashear_clave,
    CLAVE_INICIAL,
    DNI_ADMIN_RESPALDO,
    CLAVE_INICIAL_ADMIN,
)

# ==========================================
# CONSTANTES DE ROLES (COM-21)
# Espejo de routers/comedores.py: rol global de sistema vs roles por comedor.
# ==========================================
ROL_SISTEMA = "Administrador Sistema"
ROL_ADMIN_COMEDOR = "Administrador"
NOMBRE_COMEDOR_DEFAULT = "Comedor Popular Cruz de Motupe - Grupo 2"

# =========================================================================
# DDL: Tabla de parámetros dinámicos (espejo de database/parametros.sql)
# =========================================================================
DDL_PARAMETROS_SISTEMA = """
CREATE TABLE IF NOT EXISTS parametros_sistema (
    id SERIAL PRIMARY KEY,
    clave VARCHAR(100) NOT NULL UNIQUE,
    valor VARCHAR(255) NOT NULL,
    descripcion TEXT,
    categoria VARCHAR(50) NOT NULL,
    tipo_dato VARCHAR(20) NOT NULL DEFAULT 'STRING',
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

SEED_PARAMETROS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('LIMITE_SOCIAL', '20', 'Cantidad máxima de menús sociales antes de mostrar alerta', 'POS', 'INTEGER'),
('LIMITE_AFILIADO', '45', 'Cantidad máxima de menús afiliados antes de mostrar alerta', 'POS', 'INTEGER'),
('ALERTA_RACIONES_MAX', '3', 'Cantidad de raciones por venta que dispara alerta de confirmación', 'POS', 'INTEGER'),
('PRECIO_SOCIAL', '0.00', 'Precio del menú para comensal Social', 'PRECIOS', 'FLOAT'),
('PRECIO_AFILIADO', '3.00', 'Precio del menú para comensal Afiliado', 'PRECIOS', 'FLOAT'),
('PRECIO_NORMAL', '5.00', 'Precio del menú para comensal Normal', 'PRECIOS', 'FLOAT'),
('IA_MIN_SOCIAL', '15', 'Mínimo absoluto de predicción social para la IA (Día laboral)', 'IA', 'INTEGER'),
('IA_MIN_AFILIADO', '35', 'Mínimo absoluto de predicción afiliado para la IA (Día laboral)', 'IA', 'INTEGER'),
('IA_MIN_NORMAL', '80', 'Mínimo absoluto de predicción normal para la IA (Día laboral)', 'IA', 'INTEGER'),
('IA_FINDE_SOCIAL', '10', 'Predicción base social para fines de semana', 'IA', 'INTEGER'),
('IA_FINDE_AFILIADO', '20', 'Predicción base afiliado para fines de semana', 'IA', 'INTEGER'),
('IA_FINDE_NORMAL', '30', 'Predicción base normal para fines de semana', 'IA', 'INTEGER')
ON CONFLICT (clave) DO NOTHING;
"""

DDL_PRESUPUESTO_COLUMNAS = """
ALTER TABLE presupuesto_semanal
ADD COLUMN IF NOT EXISTS fecha_referencia DATE,
ADD COLUMN IF NOT EXISTS costo_total_semana NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS recoleccion_total_proyectada NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS margen NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS viable BOOLEAN DEFAULT TRUE;
"""

DDL_PLANIFICACION_DIA = """
CREATE TABLE IF NOT EXISTS planificacion_dia (
    id SERIAL PRIMARY KEY,
    presupuesto_semanal_id INT REFERENCES presupuesto_semanal(id) ON DELETE CASCADE,
    dia INT NOT NULL,
    dia_nombre VARCHAR(50) NOT NULL,
    comensales_social INT DEFAULT 0,
    comensales_afiliado INT DEFAULT 0,
    comensales_normal INT DEFAULT 0,
    total_comensales INT NOT NULL,
    receta_id INT REFERENCES recetas_almuerzo(id),
    nombre_receta VARCHAR(150) NOT NULL,
    costo_racion NUMERIC(8, 2) NOT NULL,
    costo_total NUMERIC(10, 2) NOT NULL,
    recoleccion_proyectada NUMERIC(10, 2) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
CREATE INDEX IF NOT EXISTS idx_planificacion_dia_presupuesto
ON planificacion_dia(presupuesto_semanal_id);
"""

# =========================================================================
# DDL: FIX COM-17 - Columna 'raciones' en recetas_almuerzo.
# =========================================================================
DDL_RECETAS_RACIONES = """
ALTER TABLE recetas_almuerzo
ADD COLUMN IF NOT EXISTS raciones INT NOT NULL DEFAULT 4;
"""

# =========================================================================
# DDL: COM-19 (LOGIN) - Columnas de seguridad en la tabla usuarios.
# =========================================================================
DDL_USUARIOS_SEGURIDAD = """
ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS intentos_fallidos INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS bloqueado BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS fecha_clave TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
ADD COLUMN IF NOT EXISTS clave_provisoria BOOLEAN NOT NULL DEFAULT TRUE;
"""

# =========================================================================
# DDL: COM-21 (MULTI-COMEDOR) - Catálogo de comedores a nivel nacional.
# =========================================================================
DDL_COMEDORES = """
CREATE TABLE IF NOT EXISTS comedores (
    id SERIAL PRIMARY KEY,
    departamento VARCHAR(100) NOT NULL,
    ciudad VARCHAR(100) NOT NULL,
    distrito VARCHAR(100) NOT NULL,
    zona VARCHAR(150),
    nombre VARCHAR(150) NOT NULL UNIQUE,
    direccion TEXT,
    link_ubicacion TEXT,
    fecha_fundacion DATE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

# =========================================================================
# DDL: COM-21 - Asociación usuario-comedor (muchos a muchos).
# =========================================================================
DDL_USUARIO_COMEDOR = """
CREATE TABLE IF NOT EXISTS usuario_comedor (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    comedor_id INT NOT NULL REFERENCES comedores(id) ON DELETE CASCADE,
    rol VARCHAR(50) NOT NULL DEFAULT 'Operador',
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    desactivado_por INT REFERENCES usuarios(id),
    fecha_desactivacion TIMESTAMP,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE(usuario_id, comedor_id)
);
CREATE INDEX IF NOT EXISTS idx_usuario_comedor_comedor ON usuario_comedor(comedor_id);
CREATE INDEX IF NOT EXISTS idx_usuario_comedor_usuario ON usuario_comedor(usuario_id);
"""

# =========================================================================
# SEED: COM-21 - Comedor default (piloto de la tesis: Cruz de Motupe Grupo 2).
# =========================================================================
SEED_COMEDOR_DEFAULT = """
INSERT INTO comedores
(departamento, ciudad, distrito, zona, nombre, direccion, link_ubicacion, fecha_fundacion)
VALUES
('Lima', 'Lima', 'San Juan de Lurigancho', 'A.H. Cruz de Motupe',
 %s,
 'Parque Central Número 2, Calle 12 - A.H. Cruz de Motupe',
 'https://maps.google.com/?q=Comedor+Popular+Cruz+de+Motupe+Grupo+2+San+Juan+de+Lurigancho',
 '2015-03-15')
ON CONFLICT (nombre) DO NOTHING;
"""

# =========================================================================
# DDL: COM-22 (GRUPOS) - Catálogo de grupos de usuario por ámbito.
# =========================================================================
DDL_GRUPOS_USUARIO = """
CREATE TABLE IF NOT EXISTS grupos_usuario (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    ambito VARCHAR(20) NOT NULL CHECK (ambito IN ('SISTEMA','GLOBAL','COMEDOR')),
    descripcion TEXT,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

# =========================================================================
# DDL: COM-22 - Roles disponibles dentro de cada grupo.
# =========================================================================
DDL_ROLES_GRUPO = """
CREATE TABLE IF NOT EXISTS roles_grupo (
    id SERIAL PRIMARY KEY,
    grupo_id INT NOT NULL REFERENCES grupos_usuario(id) ON DELETE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE(grupo_id, nombre)
);
"""

# =========================================================================
# DDL: COM-22 - Membresías usuario-grupo-rol con alcance (global o por comedor).
# UNIQUE NULLS NOT DISTINCT garantiza una sola membresía por
# (usuario, grupo, rol, comedor) incluso cuando comedor_id es NULL (alcance global).
# =========================================================================
DDL_USUARIO_GRUPO = """
CREATE TABLE IF NOT EXISTS usuario_grupo (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    grupo_id INT NOT NULL REFERENCES grupos_usuario(id) ON DELETE CASCADE,
    rol_id INT NOT NULL REFERENCES roles_grupo(id) ON DELETE CASCADE,
    comedor_id INT REFERENCES comedores(id) ON DELETE CASCADE,
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    desactivado_por INT REFERENCES usuarios(id),
    fecha_desactivacion TIMESTAMP,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE NULLS NOT DISTINCT (usuario_id, grupo_id, rol_id, comedor_id)
);
CREATE INDEX IF NOT EXISTS idx_usuario_grupo_usuario ON usuario_grupo(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_grupo_comedor ON usuario_grupo(comedor_id);
CREATE INDEX IF NOT EXISTS idx_usuario_grupo_grupo ON usuario_grupo(grupo_id);
"""

# =========================================================================
# SEED: COM-22 - Catálogo cerrado de grupos (no se crean grupos desde la UI).
# =========================================================================
SEED_GRUPOS = """
INSERT INTO grupos_usuario (nombre, ambito, descripcion) VALUES
('Administrador de Sistemas', 'SISTEMA', 'Soporte y mantenimiento del sistema.'),
('Administrativo', 'GLOBAL', 'Grupo municipal: manejo global de todos los comedores o específico si se desea.'),
('Directivo', 'COMEDOR', 'Parte administrativa del comedor.'),
('Operativo', 'COMEDOR', 'Parte operativa del comedor.')
ON CONFLICT (nombre) DO NOTHING;
"""

# =========================================================================
# SEED: COM-22 - Roles por grupo (Auditor/Reportería; Presidente/Secretario/
# Tesorero; Cocinero; y el rol único del grupo de sistemas).
# =========================================================================
SEED_ROLES_GRUPO = """
INSERT INTO roles_grupo (grupo_id, nombre, descripcion)
SELECT g.id, r.nombre, r.descripcion
FROM (VALUES
  ('Administrador de Sistemas', 'Administrador de Sistemas', 'Soporte y mantenimiento integral del sistema.'),
  ('Administrativo', 'Auditor', 'Auditoría global o por comedor asignado.'),
  ('Administrativo', 'Reportería', 'Generación de reportes globales o por comedor asignado.'),
  ('Directivo', 'Presidente', 'Representación y gestión administrativa del comedor.'),
  ('Directivo', 'Secretario', 'Actas y documentación del comedor.'),
  ('Directivo', 'Tesorero', 'Manejo de fondos y presupuesto del comedor.'),
  ('Operativo', 'Cocinero', 'Preparación operativa de los menús del comedor.')
) AS r(grupo, nombre, descripcion)
JOIN grupos_usuario g ON g.nombre = r.grupo
ON CONFLICT (grupo_id, nombre) DO NOTHING;
"""


def _migrar_claves_legacy(cur):
    """
    COM-19: Asigna la clave provisoria (Nutri2026) con hash PBKDF2 a los usuarios
    cuyo clave_hash antiguo no tiene formato pbkdf2 (ej. 'hash_123456' del seed).
    """
    cur.execute("SELECT id FROM usuarios WHERE clave_hash NOT LIKE 'pbkdf2%';")
    filas = cur.fetchall()
    if not filas:
        return 0
    hash_inicial = hashear_clave(CLAVE_INICIAL)
    for fila in filas:
        cur.execute("""
            UPDATE usuarios
            SET clave_hash = %s, clave_provisoria = TRUE,
                fecha_clave = CURRENT_TIMESTAMP, intentos_fallidos = 0, bloqueado = FALSE
            WHERE id = %s;
        """, (hash_inicial, fila[0]))
    return len(filas)


def _asegurar_usuario_admin(cur):
    """
    COM-19: Crea el usuario administrador de respaldo (DNI 0000000) con clave
    provisoria (Admin2026) si aún no existe.
    """
    cur.execute(
        "SELECT id FROM usuarios WHERE documento_identidad = %s;",
        (DNI_ADMIN_RESPALDO,)
    )
    if cur.fetchone():
        return False
    cur.execute("""
        INSERT INTO usuarios
        (tipo_documento, documento_identidad, nombres, apellido_paterno, apellido_materno,
         fecha_nacimiento, clave_hash, rol, estado_activo, clave_provisoria, fecha_clave)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, CURRENT_TIMESTAMP);
    """, (
        'DNI',
        DNI_ADMIN_RESPALDO,
        'Administrador',
        'Sistema',
        'OSB',
        '1990-01-01',
        hashear_clave(CLAVE_INICIAL_ADMIN),
        'Administrador'
    ))
    return True


def _migrar_roles_legacy(cur):
    """
    COM-21: Los roles globales antiguos ('Administradora' / 'Administrador') pasan
    a 'Administrador Sistema'. Los roles operativos por comedor viven en
    usuario_comedor.rol y, desde COM-22, también en usuario_grupo.
    """
    cur.execute("""
        UPDATE usuarios
        SET rol = %s
        WHERE rol IN ('Administradora', 'Administrador');
    """, (ROL_SISTEMA,))
    return cur.rowcount


def _asociar_usuarios_existentes(cur):
    """
    COM-21: Todo usuario que aún no pertenece a ningún comedor se asocia al comedor
    default como Administrador activo (preserva el piloto de un solo comedor).
    """
    cur.execute("SELECT id FROM comedores WHERE nombre = %s;", (NOMBRE_COMEDOR_DEFAULT,))
    row = cur.fetchone()
    if not row:
        return 0
    comedor_id = row[0]
    cur.execute("""
        INSERT INTO usuario_comedor (usuario_id, comedor_id, rol, estado_activo)
        SELECT u.id, %s, %s, TRUE
        FROM usuarios u
        WHERE NOT EXISTS (
            SELECT 1 FROM usuario_comedor uc WHERE uc.usuario_id = u.id
        )
        ON CONFLICT (usuario_id, comedor_id) DO NOTHING;
    """, (comedor_id, ROL_ADMIN_COMEDOR))
    return cur.rowcount


def _migrar_membresias_legacy(cur):
    """
    COM-22: Migra el modelo COM-21 al modelo de grupos (idempotente):
      1) usuarios.rol = 'Administrador Sistema'  -> grupo 'Administrador de Sistemas'
         con alcance global (comedor_id NULL).
      2) usuario_comedor rol 'Administrador'    -> Directivo / Presidente del comedor.
      3) usuario_comedor rol 'Operador'         -> Operativo / Cocinero del comedor.
    Se conserva el estado activo/inactivo de la membresía original.
    """
    total = 0
    # 1) Administradores de sistemas (alcance global)
    cur.execute("""
        INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
        SELECT u.id, g.id, r.id, NULL, TRUE
        FROM usuarios u
        CROSS JOIN grupos_usuario g
        CROSS JOIN roles_grupo r
        WHERE u.rol = 'Administrador Sistema'
          AND g.nombre = 'Administrador de Sistemas'
          AND r.grupo_id = g.id AND r.nombre = 'Administrador de Sistemas'
          AND NOT EXISTS (
              SELECT 1 FROM usuario_grupo ug
              WHERE ug.usuario_id = u.id AND ug.rol_id = r.id
                AND ug.comedor_id IS NULL
          )
        ON CONFLICT DO NOTHING;
    """)
    total += cur.rowcount

    # 2) y 3) Membresías por comedor (Directivo/Presidente y Operativo/Cocinero)
    for rol_legacy, grupo_nombre, rol_nombre in (
        ('Administrador', 'Directivo', 'Presidente'),
        ('Operador', 'Operativo', 'Cocinero'),
    ):
        cur.execute("""
            INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
            SELECT uc.usuario_id, g.id, r.id, uc.comedor_id, uc.estado_activo
            FROM usuario_comedor uc
            CROSS JOIN grupos_usuario g
            CROSS JOIN roles_grupo r
            WHERE uc.rol = %s
              AND g.nombre = %s
              AND r.grupo_id = g.id AND r.nombre = %s
              AND NOT EXISTS (
                  SELECT 1 FROM usuario_grupo ug
                  WHERE ug.usuario_id = uc.usuario_id AND ug.rol_id = r.id
                    AND ug.comedor_id IS NOT DISTINCT FROM uc.comedor_id
              )
            ON CONFLICT DO NOTHING;
        """, (rol_legacy, grupo_nombre, rol_nombre))
        total += cur.rowcount
    return total


def asegurar_esquema(reintentos: int = 10, espera_segundos: int = 3):
    """
    Verifica/crea el esquema dinámico con reintentos, para tolerar el arranque
    en frío del contenedor PostgreSQL (que puede estar ejecutando init.sql).
    """
    conn = None
    for intento in range(1, reintentos + 1):
        try:
            conn = psycopg2.connect(DB_URL)
            cur = conn.cursor()
            # 1. Tabla de parámetros + seed idempotente
            cur.execute(DDL_PARAMETROS_SISTEMA)
            cur.execute(SEED_PARAMETROS)
            # 2. Columnas de planificación en presupuesto_semanal
            cur.execute(DDL_PRESUPUESTO_COLUMNAS)
            # 3. Tabla de días planificados + índice
            cur.execute(DDL_PLANIFICACION_DIA)
            # 4. FIX COM-17: columna raciones en recetas_almuerzo
            cur.execute(DDL_RECETAS_RACIONES)
            # 5. COM-19: columnas de seguridad en usuarios
            cur.execute(DDL_USUARIOS_SEGURIDAD)
            # 6. COM-19: migración de hashes legacy a PBKDF2 (clave provisoria)
            migrados = _migrar_claves_legacy(cur)
            # 7. COM-19: usuario administrador de respaldo (DNI 0000000)
            admin_creado = _asegurar_usuario_admin(cur)
            # 8. COM-21: tablas de comedores y asociación usuario-comedor
            cur.execute(DDL_COMEDORES)
            cur.execute(DDL_USUARIO_COMEDOR)
            # 9. COM-21: comedor default (piloto) y migración de roles globales
            cur.execute(SEED_COMEDOR_DEFAULT, (NOMBRE_COMEDOR_DEFAULT,))
            roles_migrados = _migrar_roles_legacy(cur)
            # 10. COM-21: asociación inicial de usuarios sin comedor
            asociados = _asociar_usuarios_existentes(cur)
            # 11. COM-22: tablas de grupos, roles y membresías
            cur.execute(DDL_GRUPOS_USUARIO)
            cur.execute(DDL_ROLES_GRUPO)
            cur.execute(DDL_USUARIO_GRUPO)
            # 12. COM-22: seed del catálogo cerrado de grupos y roles
            cur.execute(SEED_GRUPOS)
            cur.execute(SEED_ROLES_GRUPO)
            # 13. COM-22: migración de membresías legacy COM-21 al modelo de grupos
            membresias_migradas = _migrar_membresias_legacy(cur)
            conn.commit()
            cur.close()
            if migrados:
                print(f"[BOOTSTRAP] {migrados} usuario(s) con clave provisoria asignada (cambio obligatorio en primer login).")
            if admin_creado:
                print(f"[BOOTSTRAP] Usuario admin de respaldo creado (DNI {DNI_ADMIN_RESPALDO}) con clave provisoria.")
            if roles_migrados:
                print(f"[BOOTSTRAP] COM-21: {roles_migrados} rol(es) migrados a '{ROL_SISTEMA}'.")
            if asociados:
                print(f"[BOOTSTRAP] COM-21: {asociados} usuario(s) asociados al comedor default como administradores.")
            if membresias_migradas:
                print(f"[BOOTSTRAP] COM-22: {membresias_migradas} membresía(s) migradas al modelo de grupos.")
            print("[BOOTSTRAP] Esquema dinámico verificado/creado correctamente (incluye grupos COM-22).")
            return True
        except Exception as e:
            print(f"[BOOTSTRAP] Intento {intento}/{reintentos} fallido: {e}")
            if conn:
                conn.rollback()
                conn.close()
                conn = None
            if intento < reintentos:
                time.sleep(espera_segundos)
    print("[BOOTSTRAP] [ERROR] No se pudo asegurar el esquema tras los reintentos.")
    return False