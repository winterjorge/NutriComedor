"""
db_bootstrap.py
Objetivo: Asegurar que el esquema dinámico del sistema exista en la base de datos al
          arrancar la API, sin importar si el volumen de PostgreSQL fue creado antes de
          que existieran los scripts parametros.sql / planificacion_dia, o si dichos
          scripts no fueron montados en el docker-entrypoint-initdb.d.
Uso: Importar en main.py y ejecutar `asegurar_esquema()` durante el startup (lifespan).
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS / ON CONFLICT DO NOTHING),
      por lo que pueden ejecutarse en cada arranque sin efectos secundarios.
"""
import time
import psycopg2
from config import DB_URL

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

# =========================================================================
# SEED: Poblado inicial de parámetros (mismos valores que parametros.sql)
# =========================================================================
SEED_PARAMETROS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
-- POS y Límites de Alerta
('LIMITE_SOCIAL', '20', 'Cantidad máxima de menús sociales antes de mostrar alerta', 'POS', 'INTEGER'),
('LIMITE_AFILIADO', '45', 'Cantidad máxima de menús afiliados antes de mostrar alerta', 'POS', 'INTEGER'),
('ALERTA_RACIONES_MAX', '3', 'Cantidad de raciones por venta que dispara alerta de confirmación', 'POS', 'INTEGER'),
-- Precios de Venta (Recolección)
('PRECIO_SOCIAL', '0.00', 'Precio del menú para comensal Social', 'PRECIOS', 'FLOAT'),
('PRECIO_AFILIADO', '3.00', 'Precio del menú para comensal Afiliado', 'PRECIOS', 'FLOAT'),
('PRECIO_NORMAL', '5.00', 'Precio del menú para comensal Normal', 'PRECIOS', 'FLOAT'),
-- Motor de IA (Predicción de Demanda - Umbrales)
('IA_MIN_SOCIAL', '15', 'Mínimo absoluto de predicción social para la IA (Día laboral)', 'IA', 'INTEGER'),
('IA_MIN_AFILIADO', '35', 'Mínimo absoluto de predicción afiliado para la IA (Día laboral)', 'IA', 'INTEGER'),
('IA_MIN_NORMAL', '80', 'Mínimo absoluto de predicción normal para la IA (Día laboral)', 'IA', 'INTEGER'),
('IA_FINDE_SOCIAL', '10', 'Predicción base social para fines de semana', 'IA', 'INTEGER'),
('IA_FINDE_AFILIADO', '20', 'Predicción base afiliado para fines de semana', 'IA', 'INTEGER'),
('IA_FINDE_NORMAL', '30', 'Predicción base normal para fines de semana', 'IA', 'INTEGER')
ON CONFLICT (clave) DO NOTHING;
"""

# =========================================================================
# DDL: Columnas de planificación en presupuesto_semanal (espejo de init.sql)
# =========================================================================
DDL_PRESUPUESTO_COLUMNAS = """
ALTER TABLE presupuesto_semanal
ADD COLUMN IF NOT EXISTS fecha_referencia DATE,
ADD COLUMN IF NOT EXISTS costo_total_semana NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS recoleccion_total_proyectada NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS margen NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS viable BOOLEAN DEFAULT TRUE;
"""

# =========================================================================
# DDL: Tabla de días planificados (espejo de init.sql)
# =========================================================================
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
            conn.commit()
            cur.close()
            print("[BOOTSTRAP] Esquema dinámico verificado/creado correctamente.")
            return True
        except Exception as e:
            print(f"[BOOTSTRAP] Intento {intento}/{reintentos} fallido: {e}")
            if conn:
                conn.rollback()
                conn.close()
                conn = None
            if intento < reintentos:
                time.sleep(espera_segundos)
    print("[BOOTSTRAP] No se pudo asegurar el esquema tras los reintentos.", nivel="ERROR")
    return False