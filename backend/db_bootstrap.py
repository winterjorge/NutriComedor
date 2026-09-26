"""
db_bootstrap.py
Objetivo: Asegurar que el esquema dinámico del sistema exista en la base de datos al
          arrancar la API, sin importar si el volumen de PostgreSQL fue creado antes de
          que existieran los scripts actuales (el docker-entrypoint-initdb.d solo se
          ejecuta en la PRIMERA inicialización del volumen).
Uso: Importar en main.py y ejecutar `asegurar_esquema()` durante el startup (lifespan).
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING /
      NOT EXISTS / UPDATE condicionales), por lo que pueden ejecutarse en cada arranque
      sin efectos secundarios.

Historial de integraciones:
 - COM-17: tabla parametros_sistema + seed de parámetros operativos.
 - COM-19: columnas de seguridad en usuarios, migración de hashes legacy a PBKDF2
           y usuario administrador de respaldo.
 - COM-21: tablas comedores y usuario_comedor, comedor default y asociación inicial.
 - COM-22: tablas grupos_usuario, roles_grupo y usuario_grupo; seed del catálogo
           cerrado y migración de membresías legacy.
 - COM-23: esquema de gestión de usuarios (municipalidades, usuario_municipalidad).
 - COM-25: esquema de permisos por vistas (modulos_sistema, roles_modulos).
 - COM-26: esquema del flujo CRUD de usuarios por perfil (esquema_flujo_usuario).
 - COM-27: esquema de ubicación geográfica + importación del CSV oficial.
 - COM-5:  esquema K-means + seed de composición nutricional por ingrediente.
 - COM-8:  esquema de propuestas de menú semanal + parámetros del motor greedy.
 - COM-5 v4 / COM-8 v7 / COM-36: módulos ML exclusivos del Admin + proteínas
           configurables + auditoría automática de módulos en cada arranque.
 - COM-40: separación de deberes: solo los DNIs canónicos 00000000 y 99999999 son
           Administrador de Sistema; los no canónicos se degradan a ámbito comedor;
           se purgan membresías de comedor de los admins; el bootstrap ya no inventa
           membresías (se comentaron _asociar_usuarios_existentes y
           _migrar_membresias_legacy).
 - COM-40 v2 (este archivo): la carga inicial NO crea usuarios de comedor ni membresías
           de piloto: se COMENTA _asegurar_membresias_piloto y su llamada. Los únicos
           usuarios de arranque son los dos admins canónicos (clave provisoria
           Admin2026); todos los demás se crean manualmente desde la interfaz
           (COM-26 / COM-39). En BDs existentes, los usuarios previos conservan sus
           membresías reales: solo se degrada su rol de sistema si no es canónico.
"""
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_URL
from seguridad import (
    hashear_clave,
    CLAVE_INICIAL,
    CLAVE_INICIAL_ADMIN,
)
# COM-40 (trazabilidad): el DNI de respaldo ya no se importa; los DNIs canónicos de
# administración del sistema se definen localmente en este módulo.
# from seguridad import DNI_ADMIN_RESPALDO
# COM-23: esquema del módulo de gestión de usuarios (municipalidades)
from esquema_gestion_usuarios import aplicar_esquema_gestion_usuarios
# COM-25: esquema de permisos por vistas (módulos del sistema)
from esquema_permisos_vistas import aplicar_esquema_permisos_vistas
# COM-26: esquema del flujo CRUD de usuarios por perfil
from esquema_flujo_usuario import aplicar_esquema_flujo_usuario
# COM-27: esquema de ubicación geográfica + importación del CSV oficial
from esquema_ubicaciones import aplicar_esquema_ubicaciones
from ubicaciones_seed import importar_ubicaciones
# COM-5: esquema del módulo K-means y seed nutricional de ingredientes
from esquema_kmeans import aplicar_esquema_kmeans
from nutricion_seed import seedar_nutricion
# COM-8: esquema de propuestas de menú semanal (candidatas + parámetros + módulo)
from esquema_planificaciones import aplicar_esquema_planificaciones
# COM-5 v4 / COM-8 v7 / COM-36: módulos ML exclusivos del Admin + proteínas configurables
from esquema_modelos_ml import aplicar_esquema_modelos_ml, auditar_modulos_ml

# ==========================================
# CONSTANTES DE ROLES (COM-21)
# ==========================================
ROL_SISTEMA = "Administrador Sistema"
ROL_ADMIN_COMEDOR = "Administrador"
NOMBRE_COMEDOR_DEFAULT = "Comedor Popular Cruz de Motupe - Grupo 2"

# ==========================================
# COM-40: IDENTIDADES CANÓNICAS DE ADMINISTRACIÓN DEL SISTEMA
# Únicos DNIs que pueden poseer el rol 'Administrador Sistema' y membresías de ámbito
# SISTEMA/GLOBAL. Ningún otro usuario (ingesta seed incluida) es admin de sistema.
# COM-40 v2: son también los ÚNICOS usuarios que crea el arranque; el resto se crea
# manualmente desde la interfaz (COM-26 / COM-39).
# ==========================================
DNI_ADMIN_CEROS = "00000000"    # 8 ceros
DNI_ADMIN_NUEVES = "99999999"   # 8 nueves (según especificación original COM-37/COM-40)
DNIS_ADMIN_SISTEMA = (DNI_ADMIN_CEROS, DNI_ADMIN_NUEVES)
# COM-40 v2 (trazabilidad): DNI del usuario piloto del seed que recibía membresía
# Directivo/Presidente del comedor default. Ya no se crea ni se asegura nada para él:
# el seed no crea usuarios de comedor y las membresías se gestionan desde la interfaz.
# DNI_USUARIO_PILOTO = "43604221"

# =========================================================================
# DDL: Tabla de parámetros dinámicos (COM-17)
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
# COM-40 v2: el comedor default se conserva (es catálogo, no usuario); lo que se
# retiró es la creación/asegurado de USUARIOS de comedor en el arranque.
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
# SEED: COM-22 - Catálogo cerrado de grupos.
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
# SEED: COM-22 - Roles por grupo.
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
        """, (hash_inicial, fila['id']))
    return len(filas)


# =========================================================================
# COM-40 (trazabilidad): función COM-19 original COMENTADA (creaba un único admin de
# respaldo con DNI no canónico). Reemplazada por _asegurar_admins_canonicos.
# =========================================================================
# def _asegurar_usuario_admin(cur):
#     cur.execute(
#         "SELECT id FROM usuarios WHERE documento_identidad = %s;",
#         (DNI_ADMIN_RESPALDO,)
#     )
#     if cur.fetchone():
#         return False
#     cur.execute("""
#         INSERT INTO usuarios
#         (tipo_documento, documento_identidad, nombres, apellido_paterno, apellido_materno,
#          fecha_nacimiento, clave_hash, rol, estado_activo, clave_provisoria, fecha_clave)
#         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, TRUE, CURRENT_TIMESTAMP);
#     """, (
#         'DNI', DNI_ADMIN_RESPALDO, 'Administrador', 'Sistema', 'OSB',
#         '1990-01-01', hashear_clave(CLAVE_INICIAL_ADMIN), 'Administrador'
#     ))
#     return True


def _asegurar_admins_canonicos(cur):
    """
    COM-40 / COM-40 v2: garantiza que SOLO existan como 'Administrador Sistema' los DNIs
    canónicos 00000000 y 99999999. Los crea si faltan (clave provisoria Admin2026,
    cambio obligatorio en primer login) y canonicaliza el rol si el DNI canónico
    existiera con otro rol. SON LOS ÚNICOS USUARIOS QUE CREA EL ARRANQUE: ningún otro
    usuario (de comedor o administrativo) se crea aquí; se crean desde la interfaz.
    Retorna (creados, canonicalizados).
    """
    creados = 0
    canonicalizados = 0
    hash_admin = hashear_clave(CLAVE_INICIAL_ADMIN)
    nombres_canonicos = {
        DNI_ADMIN_CEROS: ('Administrador', 'Sistema', 'OSB'),
        DNI_ADMIN_NUEVES: ('Administrador', 'Sistema', 'Respaldo'),
    }
    for dni in DNIS_ADMIN_SISTEMA:
        cur.execute("SELECT id, rol FROM usuarios WHERE documento_identidad = %s;", (dni,))
        fila = cur.fetchone()
        if not fila:
            n, ap, am = nombres_canonicos[dni]
            cur.execute("""
                INSERT INTO usuarios
                (tipo_documento, documento_identidad, nombres, apellido_paterno,
                 apellido_materno, fecha_nacimiento, clave_hash, rol, estado_activo,
                 clave_provisoria, fecha_clave)
                VALUES ('DNI', %s, %s, %s, %s, '1990-01-01', %s, %s, TRUE, TRUE,
                        CURRENT_TIMESTAMP - INTERVAL '5 hours');
            """, (dni, n, ap, am, hash_admin, ROL_SISTEMA))
            creados += 1
        elif fila['rol'] != ROL_SISTEMA:
            cur.execute("UPDATE usuarios SET rol = %s WHERE id = %s;", (ROL_SISTEMA, fila['id']))
            canonicalizados += 1
    return creados, canonicalizados


def _demotar_admins_no_canonicos(cur):
    """
    COM-40: todo usuario con rol 'Administrador Sistema' cuyo DNI NO sea canónico se
    degrada a 'Administrador' (ámbito comedor). Así la ingesta histórica y los usuarios
    creados antes de COM-40 nunca conservan privilegios de administración del sistema.
    Retorna el número de usuarios degradados.
    """
    cur.execute("""
        UPDATE usuarios
        SET rol = %s
        WHERE rol = %s
          AND documento_identidad NOT IN %s;
    """, (ROL_ADMIN_COMEDOR, ROL_SISTEMA, DNIS_ADMIN_SISTEMA))
    return cur.rowcount or 0


def _purgar_membresias_comedor_de_admins(cur):
    """
    COM-40: separación de deberes. Desactiva (baja lógica con fecha de auditoría) toda
    membresía de ámbito COMEDOR que posea un Administrador de Sistema: filas de
    usuario_comedor y filas de usuario_grupo con comedor_id o grupo de ámbito COMEDOR.
    Los admins de sistema quedan solo con alcance SISTEMA/GLOBAL.
    Retorna (purgadas_comedor, purgadas_grupo).
    """
    cur.execute("""
        UPDATE usuario_comedor uc
        SET estado_activo = FALSE,
            fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
        WHERE uc.estado_activo = TRUE
          AND uc.usuario_id IN (
              SELECT id FROM usuarios WHERE rol = 'Administrador Sistema'
          );
    """)
    purgadas_comedor = cur.rowcount or 0

    cur.execute("""
        UPDATE usuario_grupo ug
        SET estado_activo = FALSE,
            fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
        WHERE ug.estado_activo = TRUE
          AND (ug.comedor_id IS NOT NULL
               OR ug.grupo_id IN (SELECT id FROM grupos_usuario WHERE ambito = 'COMEDOR'))
          AND ug.usuario_id IN (
              SELECT id FROM usuarios WHERE rol = 'Administrador Sistema'
          );
    """)
    purgadas_grupo = cur.rowcount or 0
    return purgadas_comedor, purgadas_grupo


def _asegurar_membresia_sistema_admins(cur):
    """
    COM-40: otorga (idempotente) la membresía del grupo 'Administrador de Sistemas'
    (ámbito SISTEMA, comedor NULL) a los DNIs canónicos. Sin ella, /vistas/mis-modulos
    no devolvería módulos de admin. Es la ÚNICA membresía que el bootstrap asegura.
    """
    cur.execute("""
        INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
        SELECT u.id, g.id, r.id, NULL, TRUE
        FROM usuarios u
        CROSS JOIN grupos_usuario g
        CROSS JOIN roles_grupo r
        WHERE u.rol = 'Administrador Sistema'
          AND u.documento_identidad IN %s
          AND g.nombre = 'Administrador de Sistemas'
          AND r.grupo_id = g.id AND r.nombre = 'Administrador de Sistemas'
          AND NOT EXISTS (
              SELECT 1 FROM usuario_grupo ug
              WHERE ug.usuario_id = u.id AND ug.rol_id = r.id AND ug.comedor_id IS NULL
          )
        ON CONFLICT DO NOTHING;
    """, (DNIS_ADMIN_SISTEMA,))
    return cur.rowcount or 0


# =========================================================================
# COM-40 v2 (trazabilidad): función COMENTADA. En COM-40 v1 aseguraba la membresía
# Directivo/Presidente del comedor default para el usuario piloto del seed
# (DNI 43604221). Con COM-40 v2 la carga inicial NO crea usuarios de comedor ni les
# asigna cargos: todo se gestiona manualmente desde la interfaz (COM-26 / COM-39).
# =========================================================================
# def _asegurar_membresias_piloto(cur):
#     cur.execute("SELECT id FROM comedores WHERE nombre = %s;", (NOMBRE_COMEDOR_DEFAULT,))
#     row = cur.fetchone()
#     if not row:
#         return 0
#     comedor_id = row['id']
#     cur.execute("SELECT id FROM usuarios WHERE documento_identidad = %s;", (DNI_USUARIO_PILOTO,))
#     urow = cur.fetchone()
#     if not urow:
#         return 0
#     usuario_id = urow['id']
#     creadas = 0
#     cur.execute("""
#         INSERT INTO usuario_comedor (usuario_id, comedor_id, rol, estado_activo)
#         VALUES (%s, %s, %s, TRUE)
#         ON CONFLICT (usuario_id, comedor_id) DO NOTHING;
#     """, (usuario_id, comedor_id, ROL_ADMIN_COMEDOR))
#     creadas += cur.rowcount or 0
#     cur.execute("""
#         INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
#         SELECT %s, g.id, r.id, %s, TRUE
#         FROM grupos_usuario g
#         JOIN roles_grupo r ON r.grupo_id = g.id
#         WHERE g.nombre = 'Directivo' AND r.nombre = 'Presidente'
#           AND NOT EXISTS (
#               SELECT 1 FROM usuario_grupo ug
#               WHERE ug.usuario_id = %s AND ug.rol_id = r.id
#                 AND ug.comedor_id IS NOT DISTINCT FROM %s
#           )
#         ON CONFLICT DO NOTHING;
#     """, (usuario_id, comedor_id, usuario_id, comedor_id))
#     creadas += cur.rowcount or 0
#     return creadas


# =========================================================================
# COM-40 (trazabilidad): funciones COM-21/COM-22 COMENTADAS en su USO (las definiciones
# se conservan para historia). El bootstrap ya no auto-asocia usuarios al comedor
# default ni convierte asociaciones legacy en membresías Directivo/Presidente:
# eso causaba que TODO usuario nuevo (incluidos admins de sistema) apareciera como
# Presidente del comedor.
# =========================================================================
def _asociar_usuarios_existentes(cur):
    """
    COM-21 (DEPRECADA por COM-40): asociaba a todo usuario sin comedor al comedor
    default como 'Administrador'. Ya no se llama desde asegurar_esquema.
    """
    cur.execute("SELECT id FROM comedores WHERE nombre = %s;", (NOMBRE_COMEDOR_DEFAULT,))
    row = cur.fetchone()
    if not row:
        return 0
    comedor_id = row['id']
    cur.execute("""
        INSERT INTO usuario_comedor (usuario_id, comedor_id, rol, estado_activo)
        SELECT u.id, %s, %s, TRUE
        FROM usuarios u
        WHERE NOT EXISTS (
            SELECT 1 FROM usuario_comedor uc WHERE uc.usuario_id = u.id
        )
        ON CONFLICT (usuario_id, comedor_id) DO NOTHING;
    """, (comedor_id, ROL_ADMIN_COMEDOR))
    return cur.rowcount or 0


def _migrar_roles_legacy(cur):
    """
    COM-21 (DEPRECADA por COM-40): promovía roles legacy 'Administradora'/'Administrador'
    a 'Administrador Sistema'. Ya no se llama: la ingesta nunca crea admins de sistema.
    """
    cur.execute("""
        UPDATE usuarios
        SET rol = %s
        WHERE rol IN ('Administradora', 'Administrador');
    """, (ROL_SISTEMA,))
    return cur.rowcount or 0


def _migrar_membresias_legacy(cur):
    """
    COM-22 (DEPRECADA por COM-40): convertía usuario_comedor legacy en membresías de
    grupos (Administrador->Presidente, Operador->Cocinero) y otorgaba el grupo SISTEMA
    a todo rol 'Administrador Sistema'. Ya no se llama: las membresías nacen solo de
    flujos explícitos de la interfaz (COM-26, COM-39, GruposView) y del asegurado
    idempotente _asegurar_membresia_sistema_admins.
    """
    total = 0
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
    total += cur.rowcount or 0
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
        total += cur.rowcount or 0
    return total


def asegurar_esquema(reintentos: int = 10, espera_segundos: int = 3):
    """
    Verifica/crea el esquema dinámico con reintentos, para tolerar el arranque
    en frío del contenedor PostgreSQL (que puede estar ejecutando init.sql).
    COM-36: incluye la auditoría final de módulos ML en cada arranque.
    COM-40: canonicalización de admins de sistema, degradación de no canónicos y
    purga de membresías de comedor de admins.
    COM-40 v2: el arranque NO crea usuarios de comedor ni membresías de piloto;
    los únicos usuarios creados son los admins canónicos 00000000 y 99999999.
    """
    conn = None
    for intento in range(1, reintentos + 1):
        try:
            conn = psycopg2.connect(DB_URL)
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # 1. COM-17: tabla de parámetros + seed idempotente
            cur.execute(DDL_PARAMETROS_SISTEMA)
            cur.execute(SEED_PARAMETROS)
            # 2. COM-19: columnas de seguridad en usuarios
            cur.execute(DDL_USUARIOS_SEGURIDAD)
            migrados = _migrar_claves_legacy(cur)
            # 3. COM-40: identidades canónicas de administración del sistema
            #    (únicos usuarios que crea el arranque)
            admins_creados, admins_canonicalizados = _asegurar_admins_canonicos(cur)
            degradados = _demotar_admins_no_canonicos(cur)
            # 4. COM-21: tablas de comedores y asociación usuario-comedor
            cur.execute(DDL_COMEDORES)
            cur.execute(DDL_USUARIO_COMEDOR)
            cur.execute(SEED_COMEDOR_DEFAULT, (NOMBRE_COMEDOR_DEFAULT,))
            # COM-40 (trazabilidad): llamadas deprecadas, comentadas:
            # roles_migrados = _migrar_roles_legacy(cur)          # promovía ingesta a Admin Sistema
            # asociados = _asociar_usuarios_existentes(cur)       # auto-asociaba todo usuario al comedor
            # COM-40 v2 (trazabilidad): asegurado de membresías del piloto, comentado:
            # membresias_piloto = _asegurar_membresias_piloto(cur)  # creaba Presidente del comedor default
            # 5. COM-22: tablas de grupos, roles y membresías
            cur.execute(DDL_GRUPOS_USUARIO)
            cur.execute(DDL_ROLES_GRUPO)
            cur.execute(DDL_USUARIO_GRUPO)
            cur.execute(SEED_GRUPOS)
            cur.execute(SEED_ROLES_GRUPO)
            # COM-40 (trazabilidad): migración legacy deprecada, comentada:
            # membresias_migradas = _migrar_membresias_legacy(cur)
            # 6. COM-40: membresía SISTEMA de admins canónicos + purga de sus membresías de comedor
            membresias_sistema = _asegurar_membresia_sistema_admins(cur)
            purga_comedor, purga_grupo = _purgar_membresias_comedor_de_admins(cur)
            # 7. COM-23: esquema de gestión de usuarios (municipalidades)
            aplicar_esquema_gestion_usuarios(cur)
            # 8. COM-25: esquema de permisos por vistas (módulos del sistema)
            aplicar_esquema_permisos_vistas(cur)
            # COM-26: esquema del flujo CRUD de usuarios por perfil.
            aplicar_esquema_flujo_usuario(cur)
            # 9. COM-27: esquema de ubicación geográfica + importación del CSV oficial
            aplicar_esquema_ubicaciones(cur)
            cur.execute("SELECT COUNT(*) AS total FROM departamentos;")
            if cur.fetchone()["total"] == 0:
                importadas = importar_ubicaciones(cur)
            else:
                importadas = 0
            # 10. COM-5: esquema K-means + seed nutricional
            aplicar_esquema_kmeans(cur)
            nutricion_sembrada = seedar_nutricion(cur)
            # 11. COM-8: esquema de propuestas semanales
            aplicar_esquema_planificaciones(cur)
            # 12. COM-5 v4 / COM-36: módulos ML exclusivos del Admin + proteínas configurables
            aplicar_esquema_modelos_ml(cur)
            modulos_ok, enlaces_ok = auditar_modulos_ml(cur)
            conn.commit()
            cur.close()
            if migrados:
                print(f"[BOOTSTRAP] {migrados} usuario(s) con clave provisoria asignada (cambio obligatorio en primer login).")
            # COM-40 / COM-40 v2: auditoría de identidades y separación de deberes
            print(f"[BOOTSTRAP] COM-40: admins canónicos creados={admins_creados}, canonicalizados={admins_canonicalizados}, "
                  f"admins no canónicos degradados a comedor={degradados}, membresías SISTEMA aseguradas={membresias_sistema}, "
                  f"membresías de comedor purgadas a admins (usuario_comedor={purga_comedor}, usuario_grupo={purga_grupo}). "
                  f"COM-40 v2: no se crean usuarios de comedor ni membresías de piloto en el arranque.")
            if importadas:
                print(f"[BOOTSTRAP] COM-27: {importadas} municipalidades importadas del CSV oficial.")
            if nutricion_sembrada:
                print(f"[BOOTSTRAP] COM-5: {nutricion_sembrada} ingredientes nutricionales sembrados.")
            print(f"[BOOTSTRAP] COM-36: auditoría módulos ML -> módulos={modulos_ok}/2, enlaces_admin={enlaces_ok}/2.")
            if modulos_ok < 2 or enlaces_ok < 2:
                print("[BOOTSTRAP] COM-36: [AVISO] Faltan módulos/enlaces ML; se reintentará en el próximo arranque.")
            print("[BOOTSTRAP] Esquema dinámico verificado/creado correctamente "
                  "(incluye ubicación COM-27, K-means COM-5, propuestas COM-8, módulos ML COM-36 "
                  "y separación de deberes COM-40/COM-40 v2).")
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