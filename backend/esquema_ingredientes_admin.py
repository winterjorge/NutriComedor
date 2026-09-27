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
 - COM-37 v5 (este archivo): columna insumos.origen, tablas insumos_precios_manuales e
   ingredientes_equivalencias, seeds del módulo. Todo idempotente.
Uso: Importado por db_bootstrap.py (aplicar_esquema_ingredientes_admin(cur)); el
     bootstrap ya está registrado desde COM-37 v1, no requiere cambios.
Referencia: ticket COM-37 v5 (solo trazabilidad).
"""

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


def aplicar_esquema_ingredientes_admin(cur):
    """
    COM-37 v1/v5: crea/amplía tablas de precios manuales (ingrediente legacy e insumo),
    equivalencias de unidades uso<->compra, columna insumos.origen y el módulo de vista
    'gestion_ingredientes' para el rol Administrador de Sistemas. Idempotente: se
    ejecuta en cada arranque sin efectos secundarios. El caller (db_bootstrap) hace commit.
    """
    cur.execute(DDL_INGREDIENTES_PRECIOS_MANUALES)   # legacy v1 (fallback)
    cur.execute(DDL_INSUMOS_ORIGEN)                  # v5
    cur.execute(DDL_INSUMOS_PRECIOS_MANUALES)        # v5
    cur.execute(DDL_INGREDIENTES_EQUIVALENCIAS)      # v5
    cur.execute(SEED_MODULO_GESTION_INGREDIENTES)    # v1/v5
    # COM-37 v5: la migración de unidades de v3 queda cancelada (ver comentario arriba).