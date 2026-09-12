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
 - COM-19 (Login): columnas de seguridad en usuarios (intentos_fallidos, bloqueado,
   fecha_clave, clave_provisoria) y migración de hashes legacy a PBKDF2 con clave
   provisoria Nutri2026 (cambio obligatorio en primer login).
 - COM-19 (Admin respaldo): creación idempotente del usuario administrador con
   DNI 0000000 y clave provisoria Admin2026 (cambio obligatorio en primer login).
"""
import time
import psycopg2
from config import DB_URL
from seguridad import (
    hashear_clave,
    CLAVE_INICIAL,
    DNI_ADMIN_RESPALDO,
    CLAVE_INICIAL_ADMIN
)

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


def _migrar_claves_legacy(cur):
    """
    COM-19: Asigna la clave provisoria (Nutri2026) con hash PBKDF2 a los usuarios
    cuyo clave_hash antiguo no tiene formato pbkdf2 (ej. 'hash_123456' del seed).
    Idempotente: solo toca filas que aún no tengan el formato nuevo.
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
    COM-19: Crea el usuario administrador de respaldo (DNI 00000000) con clave
    provisoria (Admin2026) si aún no existe. Idempotente: si el usuario ya existe
    no se modifica nada (respeta la clave que el propio usuario haya definido).
    El primer login forzará el cambio de clave (clave_provisoria = TRUE).
    """
    cur.execute(
        "SELECT id FROM usuarios WHERE documento_identidad = %s;",
        (DNI_ADMIN_RESPALDO,)
    )
    if cur.fetchone():
        return False  # El usuario ya existe: no tocar
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
            # 7. COM-19: usuario administrador de respaldo (DNI 00000000)
            admin_creado = _asegurar_usuario_admin(cur)
            conn.commit()
            cur.close()
            if migrados:
                print(f"[BOOTSTRAP] {migrados} usuario(s) con clave provisoria asignada (cambio obligatorio en primer login).")
            if admin_creado:
                print(f"[BOOTSTRAP] Usuario admin de respaldo creado (DNI {DNI_ADMIN_RESPALDO}) con clave provisoria.")
            print("[BOOTSTRAP] Esquema dinámico verificado/creado correctamente (incluye seguridad COM-19).")
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