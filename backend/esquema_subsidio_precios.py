"""
esquema_subsidio_precios.py
Objetivo: COM-59A: esquema del modelo de negocio del comedor autogestionado:
          1) `subsidio_mensual`: víveres recibidos del municipio por MES CALENDARIO
             (anio, mes, COMEDOR, ingrediente, cantidad, unidad). Configurable, no hardcoded.
          2) `precios_venta`: precio de venta por tipo de comensal con HISTORIAL;
             rige el precio único más reciente (vigente hasta nuevo cambio), que es la
             política de estabilidad de precio del comedor.
          3) Parámetro `MARGEN_SEMANAL_OBJETIVO`: margen de ganancia objetivo SEMANAL
             sobre el costo real post-subsidio, para absorber días de menor venta.
          4) Módulos de vista `subsidio` y `precios_venta` con permisos por rol.
Historial:
 - COM-59A v1: versión original (subsidio sin comedor_id).
 - COM-59A v2 (este archivo): el subsidio es POR COMEDOR (lo recibe cada OSB de su
   municipalidad y lo configura su directiva): se agrega `comedor_id` NOT NULL y la
   unicidad pasa a (anio, mes, comedor_id, ingrediente_id). Migración idempotente para
   volúmenes donde la v1 ya creó la tabla: ALTER ADD COLUMN IF NOT EXISTS + reconstrucción
   de la restricción única + SET NOT NULL condicional (solo si no hay filas NULL).
Uso: Importado por db_bootstrap.py; `aplicar_esquema_subsidio_precios(cur)` es idempotente.
Referencia: tickets COM-59 / HU de autogestión (solo trazabilidad).
"""

# ==========================================
# DDL: Subsidio mensual de víveres (mes calendario, por comedor)
# ==========================================
DDL_SUBSIDIO_MENSUAL = """
CREATE TABLE IF NOT EXISTS subsidio_mensual (
    id SERIAL PRIMARY KEY,
    anio INT NOT NULL,
    mes INT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    -- COM-59A v2: el subsidio lo recibe cada comedor de su municipalidad
    comedor_id INT NOT NULL REFERENCES comedores(id) ON DELETE CASCADE,
    ingrediente_id INT NOT NULL REFERENCES ingredientes(id) ON DELETE CASCADE,
    cantidad_recibida NUMERIC(12,2) NOT NULL CHECK (cantidad_recibida >= 0),
    unidad_medida_id INT NOT NULL REFERENCES unidades_medida(id),
    observacion TEXT,
    creado_por INT REFERENCES usuarios(id),
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE(anio, mes, comedor_id, ingrediente_id)
);
CREATE INDEX IF NOT EXISTS idx_subsidio_periodo ON subsidio_mensual(anio, mes);
CREATE INDEX IF NOT EXISTS idx_subsidio_comedor ON subsidio_mensual(comedor_id);
CREATE INDEX IF NOT EXISTS idx_subsidio_ingrediente ON subsidio_mensual(ingrediente_id);
"""

# ==========================================
# COM-59A v2: migración idempotente para volúmenes con la tabla v1 (sin comedor_id)
# ==========================================
MIGRAR_SUBSIDIO_COMEDOR = [
    """
    ALTER TABLE subsidio_mensual
        ADD COLUMN IF NOT EXISTS comedor_id INT REFERENCES comedores(id) ON DELETE CASCADE;
    """,
    # Reconstrucción de la unicidad: cae la v1 (anio, mes, ingrediente) y entra la v2
    """
    ALTER TABLE subsidio_mensual
        DROP CONSTRAINT IF EXISTS subsidio_mensual_anio_mes_ingrediente_id_key;
    """,
    """
    ALTER TABLE subsidio_mensual
        DROP CONSTRAINT IF EXISTS uq_subsidio_periodo_comedor_ingrediente;
    """,
    """
    ALTER TABLE subsidio_mensual
        ADD CONSTRAINT uq_subsidio_periodo_comedor_ingrediente
        UNIQUE (anio, mes, comedor_id, ingrediente_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_subsidio_comedor ON subsidio_mensual(comedor_id);
    """,
    # NOT NULL condicional: solo si no quedaron filas NULL (la funcionalidad es nueva)
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM subsidio_mensual WHERE comedor_id IS NULL) THEN
            ALTER TABLE subsidio_mensual ALTER COLUMN comedor_id SET NOT NULL;
        END IF;
    END $$;
    """,
]

# ==========================================
# DDL: Precios de venta por tipo de comensal (precio único vigente hasta cambio)
# ==========================================
DDL_PRECIOS_VENTA = """
CREATE TABLE IF NOT EXISTS precios_venta (
    id SERIAL PRIMARY KEY,
    tipo_comensal VARCHAR(20) NOT NULL CHECK (tipo_comensal IN ('Social','Afiliado','Normal')),
    precio NUMERIC(8,2) NOT NULL CHECK (precio >= 0),
    vigente_desde TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    creado_por INT REFERENCES usuarios(id),
    observacion TEXT
);
CREATE INDEX IF NOT EXISTS idx_precios_venta_tipo ON precios_venta(tipo_comensal, vigente_desde DESC);
"""

# ==========================================
# SEED: precios de venta iniciales (migrados de los valores fijos legacy)
# Idempotente: solo si el tipo aún no tiene NINGÚN precio registrado.
# ==========================================
SEED_PRECIOS_VENTA_INICIAL = """
INSERT INTO precios_venta (tipo_comensal, precio, observacion)
SELECT t.tipo, t.precio, 'Precio inicial COM-59A (migrado de valores fijos legacy)'
FROM (VALUES ('Social', 0.00), ('Afiliado', 3.00), ('Normal', 5.00)) AS t(tipo, precio)
WHERE NOT EXISTS (
    SELECT 1 FROM precios_venta pv WHERE pv.tipo_comensal = t.tipo
);
"""

# ==========================================
# SEED: parámetro de margen semanal objetivo
# ==========================================
SEED_PARAMETRO_MARGEN = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato)
VALUES ('MARGEN_SEMANAL_OBJETIVO', '0.15',
        'Margen de ganancia objetivo SEMANAL sobre el costo real post-subsidio (0.15 = 15%)',
        'PRESUPUESTO', 'FLOAT')
ON CONFLICT (clave) DO NOTHING;
"""

# ==========================================
# SEED: módulos de vista y permisos por rol
# ==========================================
SEED_MODULOS_SUBSIDIO_PRECIOS = """
INSERT INTO modulos_sistema (clave, nombre, descripcion) VALUES
('subsidio', 'Subsidio de Víveres', 'Configuración del subsidio mensual de víveres del municipio'),
('precios_venta', 'Precios de Venta', 'Configuración de precios de venta por tipo de comensal')
ON CONFLICT (clave) DO NOTHING;
"""

# Enlaces rol->módulo.
#  subsidio: gestión para Admin de Sistemas y Directivos; lectura para Administrativo/Auditor/Reportería.
#  precios_venta: SOLO Admin de Sistemas (política global de estabilidad de precio).
SEED_PERMISOS_SUBSIDIO_PRECIOS = """
INSERT INTO roles_modulos (rol_id, modulo_id)
SELECT r.id, m.id
FROM roles_grupo r
CROSS JOIN modulos_sistema m
WHERE (m.clave = 'subsidio' AND r.nombre IN
       ('Administrador de Sistemas', 'Presidente', 'Tesorero', 'Secretario',
        'Auditor', 'Reportería'))
   OR (m.clave = 'precios_venta' AND r.nombre IN ('Administrador de Sistemas'))
ON CONFLICT (rol_id, modulo_id) DO NOTHING;
"""


def aplicar_esquema_subsidio_precios(cur):
    """
    COM-59A v2: aplica DDL + migración v1->v2 + seeds idempotentes del modelo de
    subsidio y precios. Retorna tupla de auditoría (tabla_subsidio, columna_comedor,
    tabla_precios, precios_sembrados, parametro_margen, modulos, permisos).
    """
    cur.execute(DDL_SUBSIDIO_MENSUAL)
    # COM-59A v2: si la tabla ya existía (v1 sin comedor_id), la migración la completa
    for sentencia in MIGRAR_SUBSIDIO_COMEDOR:
        cur.execute(sentencia)
    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subsidio_mensual'
          AND column_name = 'comedor_id' AND is_nullable = 'NO';
    """)
    columna_comedor_not_null = int(cur.fetchone()['n']) == 1
    cur.execute(DDL_PRECIOS_VENTA)
    cur.execute(SEED_PRECIOS_VENTA_INICIAL)
    precios_sembrados = cur.rowcount or 0
    cur.execute(SEED_PARAMETRO_MARGEN)
    parametro_margen = cur.rowcount or 0
    cur.execute(SEED_MODULOS_SUBSIDIO_PRECIOS)
    modulos = cur.rowcount or 0
    cur.execute(SEED_PERMISOS_SUBSIDIO_PRECIOS)
    permisos = cur.rowcount or 0

    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'subsidio_mensual';
    """)
    tabla_subsidio = int(cur.fetchone()['n']) == 1
    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'precios_venta';
    """)
    tabla_precios = int(cur.fetchone()['n']) == 1
    return (tabla_subsidio, columna_comedor_not_null, tabla_precios,
            precios_sembrados, parametro_margen, modulos, permisos)