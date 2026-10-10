"""
esquema_comensales_pos.py
Objetivo: COM-62 v2: modelo de identidad de comensales para atención ágil del POS:
          - El DNI YA NO es la identidad única: la mayoría de comensales se atiende solo
            por nombre (documento '00000000') y el DNI real se puede completar después
            (edición), sin duplicar filas ni romper ventas históricas.
          - Un único "Cliente Genérico" (es_generico=TRUE) reservado EXCLUSIVAMENTE para
            cargas masivas históricas de atenciones; nunca aparece en el autocompletado.
          - Los comensales "solo nombre" tienen fila propia y se deduplican por nombre
            normalizado (índice único parcial), de modo que el autocompletado del POS
            reutiliza la ficha existente en lugar de crear duplicados.
          Cambios idempotentes:
            1) comensales: columnas apellido_paterno, apellido_materno (nullable) y
               es_generico BOOLEAN NOT NULL DEFAULT FALSE.
            2) Cae el UNIQUE histórico de documento_identidad (cualquiera sea su nombre
               de constraint) y entran dos índices únicos parciales:
                 uq_comensales_dni_real        -> documento <> '00000000'
                 uq_comensales_nombre_sin_dni  -> LOWER(BTRIM(nombres)) con documento
                                                  '00000000' y es_generico=FALSE
            3) Índice de búsqueda por nombre para el autocompletado.
            4) Seed idempotente del Cliente Genérico (DNI 00000000, Cliente/Generico/-).
Uso: Importado por db_bootstrap.py (paso 16 COM-62); aplicar_esquema_comensales_pos(cur).
Referencia: ticket COM-62 (solo trazabilidad).
"""

# ==========================================
# 1) Columnas nuevas (apellidos + flag de genérico)
# ==========================================
DDL_COMENSALES_POS = """
ALTER TABLE comensales
    ADD COLUMN IF NOT EXISTS apellido_paterno VARCHAR(100),
    ADD COLUMN IF NOT EXISTS apellido_materno VARCHAR(100),
    ADD COLUMN IF NOT EXISTS es_generico BOOLEAN NOT NULL DEFAULT FALSE;
"""

# ==========================================
# 2) Retira el UNIQUE histórico de documento_identidad (nombre de constraint dinámico)
# ==========================================
DDL_DROP_UNIQ_DOCUMENTO = """
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
         AND kcu.table_schema = tc.table_schema
         AND kcu.table_name = tc.table_name
        WHERE tc.table_schema = 'public'
          AND tc.table_name = 'comensales'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'documento_identidad'
    LOOP
        EXECUTE format('ALTER TABLE public.comensales DROP CONSTRAINT %I', r.constraint_name);
    END LOOP;
END $$;
"""

# ==========================================
# 3) Índices únicos parciales (nueva identidad de negocio) + índice de búsqueda
# ==========================================
DDL_INDICES_COMENSALES = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_comensales_dni_real
    ON comensales (documento_identidad)
    WHERE documento_identidad <> '00000000';

CREATE UNIQUE INDEX IF NOT EXISTS uq_comensales_nombre_sin_dni
    ON comensales (LOWER(BTRIM(nombres)))
    WHERE documento_identidad = '00000000' AND es_generico = FALSE;

CREATE INDEX IF NOT EXISTS idx_comensales_nombres_busqueda
    ON comensales (LOWER(nombres));
"""

# ==========================================
# 4) Seed del Cliente Genérico (solo cargas masivas históricas)
# ==========================================
SEED_CLIENTE_GENERICO = """
INSERT INTO comensales
    (tipo_documento, documento_identidad, nombres, apellido_paterno, apellido_materno,
     tipo_comensal, es_generico)
SELECT 'DNI', '00000000', 'Cliente', 'Generico', '-', 'Normal', TRUE
WHERE NOT EXISTS (SELECT 1 FROM comensales WHERE es_generico = TRUE);
"""


def aplicar_esquema_comensales_pos(cur):
    """
    COM-62 v2: aplica columnas, drop del unique histórico, índices parciales y seed del
    cliente genérico. Todo idempotente. Retorna tupla de auditoría:
    (columnas_ok, unique_documento_retirado, idx_dni_real, idx_nombre_sin_dni, generico_ok)
    """
    cur.execute(DDL_COMENSALES_POS)
    cur.execute(DDL_DROP_UNIQ_DOCUMENTO)
    cur.execute(DDL_INDICES_COMENSALES)
    cur.execute(SEED_CLIENTE_GENERICO)

    cur.execute("""
        SELECT COUNT(*) AS n FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'comensales'
          AND column_name IN ('apellido_paterno', 'apellido_materno', 'es_generico');
    """)
    columnas_ok = int(cur.fetchone()['n']) == 3

    cur.execute("""
        SELECT COUNT(*) AS n
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_name = tc.constraint_name
         AND kcu.table_schema = tc.table_schema AND kcu.table_name = tc.table_name
        WHERE tc.table_schema = 'public' AND tc.table_name = 'comensales'
          AND tc.constraint_type = 'UNIQUE' AND kcu.column_name = 'documento_identidad';
    """)
    unique_documento_retirado = int(cur.fetchone()['n']) == 0

    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'comensales';
    """)
    indices = {r['indexname'] for r in cur.fetchall()}
    idx_dni_real = 'uq_comensales_dni_real' in indices
    idx_nombre_sin_dni = 'uq_comensales_nombre_sin_dni' in indices

    cur.execute("SELECT COUNT(*) AS n FROM comensales WHERE es_generico = TRUE;")
    generico_ok = int(cur.fetchone()['n']) == 1

    return (columnas_ok, unique_documento_retirado, idx_dni_real, idx_nombre_sin_dni, generico_ok)