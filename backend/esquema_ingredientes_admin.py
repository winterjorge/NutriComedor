"""
esquema_ingredientes_admin.py
Objetivo: Esquema dinámico del módulo "Gestión de Ingredientes" (exclusivo del
Administrador de Sistemas) y del modelo COM-37 v5 de dos conceptos:
- INGREDIENTE: lo que se cocina; su unidad es de USO (pizca, cucharadita,
  taza, rodaja, unidad...). Vive en ingredientes y en cada línea de
  receta_ingrediente.unidad_medida_id.
- INSUMO: lo que se compra (scraper SISAP o registro manual); su unidad es
  de COMPRA/VENTA (Kg, L, atado, unidad...). Vive en insumos.unidad_medida_id.
- EQUIVALENCIA: tabla ingredientes_equivalencias con gramos por unidad de USO
  para cada par (ingrediente, insumo); si no existe, el motor aplica la
  conversión estándar (factor_a_base para masa/volumen, peso_estimado_g para
  discretas, atado=100 g, rodaja=20 g).
- PRECIO MANUAL: períodos con vigencia por INSUMO (insumos_precios_manuales),
  incluidos insumos manuales (insumos.origen='MANUAL'). La tabla legacy por
  ingrediente (ingredientes_precios_manuales, COM-37 v1) se conserva como
  último fallback para no perder cargas previas.
Historial:
- COM-37 v1: tabla ingredientes_precios_manuales + módulo 'gestion_ingredientes'.
- COM-37 v3: migración de unidades estándar de ingredientes (Kg/L). CANCELADA en v5:
  el ingrediente conserva su unidad de USO; la unidad de VENTA vive en el insumo.
  La migración queda COMENTADA por trazabilidad (si ya corrió en alguna BD, es
  inofensiva: los cálculos usan la unidad de uso de receta_ingrediente).
- COM-37 v5: columna insumos.origen, tablas insumos_precios_manuales e
  ingredientes_equivalencias, seeds del módulo. Todo idempotente.
- COM-80 (este archivo): columna insumos.es_principal (flag de insumo canónico
  por ingrediente) + backfill idempotente por coincidencia exacta de nombre
  normalizado (solo si el ingrediente aún no tiene principal, para respetar
  decisiones manuales) + herencia de equivalencias activas desde insumos
  hermanos cuando el principal no las tiene (observación 'Heredada COM-80...').
  La migración corre dentro de aplicar_esquema_ingredientes_admin, que el
  db_bootstrap ya ejecuta en cada arranque (no requiere cambios de bootstrap).
Uso: Importado por db_bootstrap.py (aplicar_esquema_ingredientes_admin(cur)); el
bootstrap ya está registrado desde COM-37 v1, no requiere cambios.
Referencia: tickets COM-37 v5 / COM-80 (solo trazabilidad).
"""
import unicodedata

# =========================================================================
# DDL legacy (COM-37 v1): precios manuales POR INGREDIENTE. Se conserva activa
# como último fallback de resolución de precios (datos ya cargados no se pierden).
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
"""

# =========================================================================
# COM-37 v5: origen del insumo (SCRAPER | MANUAL)
# =========================================================================
DDL_INSUMOS_ORIGEN = """
ALTER TABLE insumos
    ADD COLUMN IF NOT EXISTS origen VARCHAR(20) NOT NULL DEFAULT 'SCRAPER';
CREATE INDEX IF NOT EXISTS idx_insumos_origen ON insumos(origen);
"""

# =========================================================================
# COM-80: flag de INSUMO PRINCIPAL por ingrediente. El motor de costeo
# (precios_insumos.mejor_opcion_ingrediente y optimizador.calcular_costo_receta)
# prefiere al principal cuando tiene precio en la fecha; si no, legacy más barato.
# =========================================================================
DDL_INSUMOS_PRINCIPAL = """
ALTER TABLE insumos
    ADD COLUMN IF NOT EXISTS es_principal BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_insumos_principal ON insumos(ingrediente_id, es_principal);
"""

# =========================================================================
# COM-37 v5: períodos de precio manual POR INSUMO (unidad de COMPRA), con vigencia
# opcional (fecha_inicio NULL = rige siempre). Aplican a insumos manuales y también
# permiten corregir/suplir precios de insumos del scraper si fuera necesario.
# =========================================================================
DDL_INSUMOS_PRECIOS_MANUALES = """
CREATE TABLE IF NOT EXISTS insumos_precios_manuales (
    id SERIAL PRIMARY KEY,
    insumo_id INT NOT NULL REFERENCES insumos(id) ON DELETE CASCADE,
    precio_por_unidad NUMERIC(10,2) NOT NULL CHECK (precio_por_unidad > 0),
    fecha_inicio DATE,
    fecha_fin DATE,
    observacion TEXT,
    creado_por INT REFERENCES usuarios(id),
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    CHECK (fecha_inicio IS NULL OR fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);
CREATE INDEX IF NOT EXISTS idx_insumos_precios_manuales_insumo
    ON insumos_precios_manuales(insumo_id, estado_activo);
CREATE INDEX IF NOT EXISTS idx_insumos_precios_manuales_vigencia
    ON insumos_precios_manuales(fecha_inicio, fecha_fin);
"""

# =========================================================================
# COM-37 v5: equivalencias unidad de USO (ingrediente/receta) <-> unidad de COMPRA
# (insumo). gramos_por_unidad_uso = gramos reales que representa 1 unidad de USO de
# ese ingrediente cuando se consume desde ese insumo (ej. 1 pizca de sal = 0.5 g).
# Si no hay fila activa, el motor usa la conversión estándar de la unidad de uso.
# =========================================================================
DDL_INGREDIENTES_EQUIVALENCIAS = """
CREATE TABLE IF NOT EXISTS ingredientes_equivalencias (
    id SERIAL PRIMARY KEY,
    ingrediente_id INT NOT NULL REFERENCES ingredientes(id) ON DELETE CASCADE,
    insumo_id INT NOT NULL REFERENCES insumos(id) ON DELETE CASCADE,
    unidad_uso_id INT NOT NULL REFERENCES unidades_medida(id),
    gramos_por_unidad_uso NUMERIC(12,4) NOT NULL CHECK (gramos_por_unidad_uso > 0),
    observacion TEXT,
    creado_por INT REFERENCES usuarios(id),
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE (ingrediente_id, insumo_id, unidad_uso_id)
);
CREATE INDEX IF NOT EXISTS idx_equivalencias_ing
    ON ingredientes_equivalencias(ingrediente_id, insumo_id, estado_activo);
"""

# =========================================================================
# SEED: módulo de vista exclusivo del Admin de Sistemas
# =========================================================================
SEED_MODULO_GESTION_INGREDIENTES = """
INSERT INTO modulos_sistema (clave, nombre, descripcion) VALUES
('gestion_ingredientes', 'Gestión de Ingredientes',
 'Emparejamiento ingrediente-insumo, equivalencias de unidades y precios manuales (exclusivo Admin de Sistemas, COM-37)')
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

# =========================================================================
# COM-37 v3 (trazabilidad): migración de unidades estándar de ingredientes CANCELADA
# en COM-37 v5. El ingrediente conserva su unidad de USO; la unidad de VENTA vive en
# el insumo y la conversión la resuelve ingredientes_equivalencias (o la regla
# estándar). Se deja comentada para historia; NO se ejecuta.
# =========================================================================
# MIGRACION_UNIDADES_ESTANDAR = """
# UPDATE ingredientes SET unidad_medida_id = (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo') WHERE ... ;
# UPDATE ingredientes SET unidad_medida_id = (SELECT id FROM unidades_medida WHERE nombre = 'Litro') WHERE ... ;
# """


def _normalizar(texto):
    """COM-80: minúsculas, sin tildes ni espacios extra (misma regla del router)."""
    if not texto:
        return ''
    txt = unicodedata.normalize('NFD', str(texto).lower())
    return ''.join(c for c in txt if unicodedata.category(c) != 'Mn').strip()


def _backfill_insumo_principal(cur):
    """
    COM-80: marca como principal el insumo cuyo nombre normalizado coincide
    EXACTAMENTE con el nombre normalizado de su ingrediente, SOLO si el
    ingrediente aún no tiene ningún principal (así se respeta una decisión
    manual previa del Admin). Idempotente: en el segundo arranque no hace nada.
    Retorna el número de filas marcadas.
    """
    cur.execute("""
        SELECT i.id AS insumo_id, i.nombre AS insumo_nombre, i.ingrediente_id, g.nombre AS ing_nombre
        FROM insumos i
        JOIN ingredientes g ON g.id = i.ingrediente_id
        WHERE i.ingrediente_id IS NOT NULL AND i.es_principal = FALSE;
    """)
    candidatos = cur.fetchall()
    cur.execute("SELECT ingrediente_id FROM insumos WHERE es_principal = TRUE GROUP BY ingrediente_id;")
    con_principal = {r['ingrediente_id'] for r in cur.fetchall()}
    marcados = 0
    for c in candidatos:
        if c['ingrediente_id'] in con_principal:
            continue
        if _normalizar(c['insumo_nombre']) == _normalizar(c['ing_nombre']):
            cur.execute("UPDATE insumos SET es_principal = TRUE WHERE id = %s;", (c['insumo_id'],))
            marcados += 1
            con_principal.add(c['ingrediente_id'])  # uno solo por ingrediente en este arranque
    return marcados


def heredar_equivalencias_de_hermanos(cur, ingrediente_id, insumo_id):
    """
    COM-80: para el insumo indicado (típicamente el nuevo principal), copia las
    equivalencias ACTIVAS de otros insumos del mismo ingrediente para aquellas
    unidades de USO que el insumo aún no tenga activas. Las copias se marcan con
    observación 'Heredada COM-80 ...' para auditoría. Idempotente.
    Retorna el número de equivalencias heredadas.
    """
    cur.execute("""
        SELECT eq.unidad_uso_id, eq.gramos_por_unidad_uso
        FROM ingredientes_equivalencias eq
        WHERE eq.ingrediente_id = %s AND eq.insumo_id <> %s AND eq.estado_activo = TRUE
        ORDER BY eq.id;
    """, (ingrediente_id, insumo_id))
    hermanas = cur.fetchall()
    heredadas = 0
    for eq in hermanas:
        cur.execute("""
            SELECT 1 FROM ingredientes_equivalencias e2
            WHERE e2.ingrediente_id = %s AND e2.insumo_id = %s
              AND e2.unidad_uso_id = %s AND e2.estado_activo = TRUE;
        """, (ingrediente_id, insumo_id, eq['unidad_uso_id']))
        if cur.fetchone():
            continue  # el principal ya tiene equivalencia propia para esa unidad
        cur.execute("""
            INSERT INTO ingredientes_equivalencias
                (ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso,
                 observacion, creado_por, estado_activo)
            VALUES (%s, %s, %s, %s, %s, NULL, TRUE);
        """, (ingrediente_id, insumo_id, eq['unidad_uso_id'], eq['gramos_por_unidad_uso'],
              'Heredada COM-80 de insumo hermano del mismo ingrediente'))
        heredadas += 1
    return heredadas


def _backfill_herencia_equivalencias(cur):
    """
    COM-80: en cada arranque, para todo insumo PRINCIPAL sin equivalencias activas,
    hereda las de sus hermanos (usa heredar_equivalencias_de_hermanos). Idempotente.
    """
    cur.execute("""
        SELECT i.id AS insumo_id, i.ingrediente_id
        FROM insumos i
        WHERE i.es_principal = TRUE AND i.ingrediente_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM ingredientes_equivalencias eq
              WHERE eq.ingrediente_id = i.ingrediente_id
                AND eq.insumo_id = i.id AND eq.estado_activo = TRUE
          );
    """)
    total = 0
    for f in cur.fetchall():
        total += heredar_equivalencias_de_hermanos(cur, f['ingrediente_id'], f['insumo_id'])
    return total


def aplicar_esquema_ingredientes_admin(cur):
    """
    COM-37 v1/v5 + COM-80: crea/amplía tablas de precios manuales (ingrediente legacy
    e insumo), equivalencias de unidades uso<->compra, columnas insumos.origen e
    insumos.es_principal, y el módulo de vista 'gestion_ingredientes' para el rol
    Administrador de Sistemas. Idempotente: se ejecuta en cada arranque sin efectos
    secundarios. El caller (db_bootstrap) hace commit.
    COM-80: además corre el backfill de principal por nombre exacto y la herencia de
    equivalencias para principales sin equivalencias (ambos idempotentes).
    """
    cur.execute(DDL_INGREDIENTES_PRECIOS_MANUALES)   # legacy v1 (fallback)
    cur.execute(DDL_INSUMOS_ORIGEN)                  # v5
    cur.execute(DDL_INSUMOS_PRINCIPAL)               # COM-80
    cur.execute(DDL_INSUMOS_PRECIOS_MANUALES)        # v5
    cur.execute(DDL_INGREDIENTES_EQUIVALENCIAS)      # v5
    cur.execute(SEED_MODULO_GESTION_INGREDIENTES)    # v1/v5
    # COM-80: backfills idempotentes de principalidad y herencia de equivalencias
    marcados = _backfill_insumo_principal(cur)
    heredadas = _backfill_herencia_equivalencias(cur)
    if marcados or heredadas:
        print(f"[BOOTSTRAP] COM-80: insumos principales marcados por nombre={marcados}, "
              f"equivalencias heredadas a principales={heredadas}.")
    # COM-37 v5: la migración de unidades de v3 queda cancelada (ver comentario arriba).