"""
esquema_carga_historica.py
Objetivo: COM-63: prepara el schema para el nuevo tipo de comensal "Cocinera"
          (menú a costo cero, sin DNI individual) y el endpoint de carga masiva.
Cambios idempotentes:
  1) Comensales: agregar 'Cocinera' al CHECK de tipo_comensal.
  2) Padron diario: agregar 'Cocinera' al CHECK de tipo_comensal_venta.
  3) Precios venta: agregar 'Cocinera' al CHECK (precio 0.00).
  4) Seed: comensal genérico "Cocinera" (DNI='CO000000', tipo='Cocinera').
  5) Seed: precio 0.00 para Cocinera en precios_venta.
  6) Seed: parámetro PRECIO_COCINERA=0.00 y LIMITE_COCINERA=10.
Uso: Importado por db_bootstrap.py (paso 17 COM-63).
Referencia: ticket COM-63.
"""

# 1) Agregar 'Cocinera' al CHECK de comensales.tipo_comensal
DDL_COMENSALES_COCINERA = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'comensales_tipo_comensal_check'
    ) THEN
        ALTER TABLE comensales DROP CONSTRAINT IF EXISTS comensales_tipo_comensal_check;
        ALTER TABLE comensales ADD CONSTRAINT comensales_tipo_comensal_check
            CHECK (tipo_comensal IN ('Social', 'Afiliado', 'Normal', 'Cocinera'));
    ELSE
        ALTER TABLE comensales DROP CONSTRAINT comensales_tipo_comensal_check;
        ALTER TABLE comensales ADD CONSTRAINT comensales_tipo_comensal_check
            CHECK (tipo_comensal IN ('Social', 'Afiliado', 'Normal', 'Cocinera'));
    END IF;
END $$;
"""

# 2) Agregar 'Cocinera' al CHECK de padron_diario.tipo_comensal_venta
DDL_PADRON_COCINERA = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'padron_diario_tipo_comensal_venta_check'
    ) THEN
        ALTER TABLE padron_diario DROP CONSTRAINT IF EXISTS padron_diario_tipo_comensal_venta_check;
        ALTER TABLE padron_diario ADD CONSTRAINT padron_diario_tipo_comensal_venta_check
            CHECK (tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal', 'Cocinera'));
    ELSE
        ALTER TABLE padron_diario DROP CONSTRAINT padron_diario_tipo_comensal_venta_check;
        ALTER TABLE padron_diario ADD CONSTRAINT padron_diario_tipo_comensal_venta_check
            CHECK (tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal', 'Cocinera'));
    END IF;
END $$;
"""

# 3) Agregar 'Cocinera' al CHECK de precios_venta.tipo_comensal
DDL_PRECIOS_COCINERA = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'precios_venta_tipo_comensal_check'
    ) THEN
        ALTER TABLE precios_venta DROP CONSTRAINT IF EXISTS precios_venta_tipo_comensal_check;
        ALTER TABLE precios_venta ADD CONSTRAINT precios_venta_tipo_comensal_check
            CHECK (tipo_comensal IN ('Social', 'Afiliado', 'Normal', 'Cocinera'));
    ELSE
        ALTER TABLE precios_venta DROP CONSTRAINT precios_venta_tipo_comensal_check;
        ALTER TABLE precios_venta ADD CONSTRAINT precios_venta_tipo_comensal_check
            CHECK (tipo_comensal IN ('Social', 'Afiliado', 'Normal', 'Cocinera'));
    END IF;
END $$;
"""

# 4) Seed: comensal genérico "Cocinera" (FIX: usa WHERE NOT EXISTS porque el UNIQUE de documento_identidad fue eliminado en COM-62)
SEED_COMENSAL_COCINERA = """
INSERT INTO comensales (tipo_documento, documento_identidad, nombres, tipo_comensal)
SELECT 'DNI', 'CO000000', 'Cocinera', 'Cocinera'
WHERE NOT EXISTS (
    SELECT 1 FROM comensales WHERE documento_identidad = 'CO000000' AND tipo_comensal = 'Cocinera'
);
"""

# 5) Seed: precio 0.00 para Cocinera (FIX: usa WHERE NOT EXISTS porque no hay UNIQUE en tipo_comensal, vigente_desde)
SEED_PRECIO_COCINERA = """
INSERT INTO precios_venta (tipo_comensal, precio, observacion)
SELECT 'Cocinera', 0.00, 'Menú a costo cero para staff del comedor'
WHERE NOT EXISTS (
    SELECT 1 FROM precios_venta WHERE tipo_comensal = 'Cocinera'
);
"""

# 6) Seed: parámetros PRECIO_COCINERA y LIMITE_COCINERA
SEED_PARAMETROS_COCINERA = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato)
VALUES 
    ('PRECIO_COCINERA', '0.00', 'Precio del menú para Cocinera (staff)', 'PRECIOS', 'FLOAT'),
    ('LIMITE_COCINERA', '10', 'Cantidad máxima de menús para cocineras antes de mostrar alerta', 'POS', 'INTEGER')
ON CONFLICT (clave) DO NOTHING;
"""


def aplicar_esquema_carga_historica(cur):
    """COM-63: aplica todos los cambios del schema para Cocinera y carga histórica."""
    cur.execute(DDL_COMENSALES_COCINERA)
    cur.execute(DDL_PADRON_COCINERA)
    cur.execute(DDL_PRECIOS_COCINERA)
    cur.execute(SEED_COMENSAL_COCINERA)
    cur.execute(SEED_PRECIO_COCINERA)
    cur.execute(SEED_PARAMETROS_COCINERA)
    
    # Auditoría
    cur.execute("""
        SELECT COUNT(*) AS n FROM comensales WHERE documento_identidad = 'CO000000' AND tipo_comensal = 'Cocinera';
    """)
    comensal_ok = int(cur.fetchone()['n']) == 1
    
    cur.execute("""
        SELECT COUNT(*) AS n FROM precios_venta WHERE tipo_comensal = 'Cocinera';
    """)
    precio_ok = int(cur.fetchone()['n']) >= 1
    
    cur.execute("""
        SELECT COUNT(*) AS n FROM parametros_sistema 
        WHERE clave IN ('PRECIO_COCINERA', 'LIMITE_COCINERA');
    """)
    params_ok = int(cur.fetchone()['n']) == 2
    
    return (comensal_ok, precio_ok, params_ok)