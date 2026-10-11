-- ============================================================================
-- 06_correccion_equivalencias.sql
-- COM-67 v2: corrección sistémica de unidades de compra y equivalencias.
--  PASO 0: pesos estimados realistas por unidad discreta (gramos/unidad)
--  PASO 1: insumos líquidos envasados por volumen -> unidad de compra Litro
--  PASO 2: desactivar equivalencias que serán reemplazadas por valores curados
--  PASO 3: insertar equivalencias curadas (referencia culinaria + dato de campo)
--  PASO 4: seed automático de equivalencias faltantes para todo lo usado en recetas
-- Todo idempotente y reversible (estado_activo = FALSE no borra historial).
-- ============================================================================
BEGIN;

-- ----------------------------------------------------------------------------
-- PASO 0: pesos estimados por unidad (gramos). Solo ingredientes existentes.
-- Fuente: dato de campo del usuario (culantro) y referencia culinaria estándar.
-- ----------------------------------------------------------------------------
UPDATE ingredientes SET peso_estimado_g = 3    WHERE LOWER(nombre) = 'culantro';
UPDATE ingredientes SET peso_estimado_g = 200  WHERE LOWER(nombre) = 'pescado';
UPDATE ingredientes SET peso_estimado_g = 60   WHERE LOWER(nombre) = 'huevo';
UPDATE ingredientes SET peso_estimado_g = 50   WHERE LOWER(nombre) = 'limon';
UPDATE ingredientes SET peso_estimado_g = 50   WHERE LOWER(nombre) = 'aji amarillo';
UPDATE ingredientes SET peso_estimado_g = 100  WHERE LOWER(nombre) = 'zanahoria';
UPDATE ingredientes SET peso_estimado_g = 150  WHERE LOWER(nombre) = 'cebolla';
UPDATE ingredientes SET peso_estimado_g = 150  WHERE LOWER(nombre) = 'papa';
UPDATE ingredientes SET peso_estimado_g = 100  WHERE LOWER(nombre) = 'platano de seda';
UPDATE ingredientes SET peso_estimado_g = 90   WHERE LOWER(nombre) = 'mandarina';
UPDATE ingredientes SET peso_estimado_g = 130  WHERE LOWER(nombre) = 'naranja';
UPDATE ingredientes SET peso_estimado_g = 80   WHERE LOWER(nombre) = 'melon';
UPDATE ingredientes SET peso_estimado_g = 150  WHERE LOWER(nombre) = 'pina';
UPDATE ingredientes SET peso_estimado_g = 200  WHERE LOWER(nombre) = 'camote';
UPDATE ingredientes SET peso_estimado_g = 250  WHERE LOWER(nombre) = 'choclo';
UPDATE ingredientes SET peso_estimado_g = 30   WHERE LOWER(nombre) = 'queso';
UPDATE ingredientes SET peso_estimado_g = 15   WHERE LOWER(nombre) = 'tocino';
UPDATE ingredientes SET peso_estimado_g = 3    WHERE LOWER(nombre) = 'canela';
UPDATE ingredientes SET peso_estimado_g = 8    WHERE LOWER(nombre) = 'uva';

-- ----------------------------------------------------------------------------
-- PASO 1: insumos líquidos envasados por volumen (ml / litro / lt) pasan a
-- unidad de compra Litro. Los envasados por masa (gr, latas de polvo) quedan kg.
-- ----------------------------------------------------------------------------
UPDATE insumos ins
SET unidad_medida_id = (SELECT id FROM unidades_medida WHERE LOWER(nombre) = 'litro')
WHERE ins.unidad_medida_id = (SELECT id FROM unidades_medida WHERE LOWER(nombre) = 'kilogramo')
  AND (
       ins.nombre ILIKE '%ml)%'
    OR ins.nombre ILIKE '%ml %'
    OR ins.nombre ILIKE '%litro%'
    OR ins.nombre ILIKE '%lt.%'
    OR ins.nombre ILIKE '%lt)'
  );

-- ----------------------------------------------------------------------------
-- PASO 2: desactivar equivalencias activas de los pares que vamos a curar
-- (no se borran: se conservan para auditoría con estado_activo = FALSE)
-- ----------------------------------------------------------------------------
UPDATE ingredientes_equivalencias ie
SET estado_activo = FALSE
WHERE ie.estado_activo = TRUE
  AND EXISTS (
    SELECT 1
    FROM (VALUES
      ('culantro','rama'), ('culantro','pizca'), ('culantro','taza'),
      ('leche','taza'), ('leche','litro'),
      ('aceite vegetal','cucharada'), ('aceite vegetal','cucharadita'), ('aceite vegetal','taza'),
      ('arroz','taza'), ('azucar','cucharadita'), ('azucar','taza'),
      ('sal yodada','pizca'), ('sal yodada','cucharadita'),
      ('pimienta','pizca'), ('pimienta','cucharadita'),
      ('ajo','cucharadita'), ('ajo','unidad'),
      ('harina de trigo','cucharada'), ('harina de trigo','taza'),
      ('lentejas','taza'), ('garbanzo','taza'), ('arveja fresca','taza'),
      ('vainitas','taza'), ('espinaca','taza'),
      ('pescado','unidad'), ('huevo','unidad'), ('queso','rodaja'),
      ('pina','taza'), ('melon','rodaja'), ('camote','unidad'),
      ('aji amarillo','unidad'), ('aji amarillo molido','cucharada'),
      ('choclo','unidad'), ('choclo','taza'), ('zapallo','taza'),
      ('tocino','rodaja'), ('canela','unidad'),
      ('comino','pizca'), ('comino','cucharadita'),
      ('oregano','pizca'), ('oregano','cucharada'),
      ('aji colorado','cucharada'), ('aji colorado','unidad'),
      ('platano de seda','unidad'), ('mandarina','unidad'), ('naranja','unidad'),
      ('uva','unidad'), ('zanahoria','unidad'), ('zanahoria','taza'),
      ('cebolla','unidad'), ('papa','unidad'), ('limon','unidad')
    ) AS v(ing, uni)
    JOIN ingredientes i  ON LOWER(i.nombre)  = v.ing
    JOIN unidades_medida um ON LOWER(um.nombre) = v.uni
    WHERE i.id  = ie.ingrediente_id
      AND um.id = ie.unidad_uso_id
  );

-- ----------------------------------------------------------------------------
-- PASO 3: equivalencias curadas.
-- Convención del puente "gramos":
--   * Ingredientes comprados por KILOGRAMO: gramos reales de masa.
--   * Ingredientes comprados por LITRO: gramos ≈ mililitros (densidad ~1),
--     para que la conversión gramos/1000 -> Litros sea exacta en volumen.
-- ----------------------------------------------------------------------------
INSERT INTO ingredientes_equivalencias
    (ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso, observacion, estado_activo)
SELECT i.id,
       (SELECT MIN(ins.id) FROM insumos ins WHERE ins.ingrediente_id = i.id),
       um.id,
       v.gramos,
       'Curada COM-67 v2',
       TRUE
FROM (VALUES
  -- Hierbas y condimentos frescos
  ('culantro','rama',3.0),        -- dato de campo del usuario
  ('culantro','pizca',1.0),
  ('culantro','taza',40.0),       -- culantro picado
  -- Líquidos (comprados por Litro: gramos ≈ ml)
  ('leche','taza',250.0),
  ('leche','litro',1000.0),
  ('aceite vegetal','cucharada',15.0),
  ('aceite vegetal','cucharadita',5.0),
  ('aceite vegetal','taza',250.0),
  -- Granos y secos (comprados por Kilogramo: gramos reales)
  ('arroz','taza',200.0),
  ('lentejas','taza',200.0),
  ('garbanzo','taza',200.0),
  ('arveja fresca','taza',140.0),
  ('azucar','cucharadita',5.0),
  ('azucar','taza',200.0),
  ('harina de trigo','cucharada',8.0),
  ('harina de trigo','taza',120.0),
  ('cebada','taza',180.0),
  -- Condimentos secos
  ('sal yodada','pizca',1.0),
  ('sal yodada','cucharadita',6.0),
  ('pimienta','pizca',0.5),
  ('pimienta','cucharadita',3.0),
  ('comino','pizca',0.5),
  ('comino','cucharadita',2.0),
  ('oregano','pizca',0.5),
  ('oregano','cucharada',3.0),
  ('canela','unidad',3.0),
  -- Ajos, cebollas y raíces
  ('ajo','unidad',5.0),           -- 1 diente
  ('ajo','cucharadita',3.0),      -- ajo picado
  ('cebolla','unidad',150.0),
  ('zanahoria','unidad',100.0),
  ('zanahoria','taza',120.0),     -- rallada/picada
  ('papa','unidad',150.0),
  ('camote','unidad',200.0),
  -- Ajíes
  ('aji amarillo','unidad',50.0),
  ('aji amarillo molido','cucharada',15.0),
  ('aji colorado','unidad',30.0),
  ('aji colorado','cucharada',15.0),
  -- Proteínas
  ('pescado','unidad',200.0),     -- 1 presa/filete por ración
  ('huevo','unidad',60.0),
  ('queso','rodaja',30.0),
  ('tocino','rodaja',15.0),
  -- Verduras de hoja y frutos
  ('espinaca','taza',30.0),
  ('vainitas','taza',100.0),
  ('zapallo','taza',150.0),
  ('choclo','unidad',250.0),
  ('choclo','taza',150.0),        -- desgranado
  -- Frutas
  ('pina','taza',150.0),
  ('melon','rodaja',80.0),
  ('platano de seda','unidad',100.0),
  ('mandarina','unidad',90.0),
  ('naranja','unidad',130.0),
  ('uva','unidad',8.0),
  ('limon','unidad',50.0)
) AS v(ing, uni, gramos)
JOIN ingredientes i    ON LOWER(i.nombre)    = v.ing
JOIN unidades_medida um ON LOWER(um.nombre)   = v.uni
WHERE EXISTS (SELECT 1 FROM insumos ins WHERE ins.ingrediente_id = i.id);

-- ----------------------------------------------------------------------------
-- PASO 4: seed automático de equivalencias FALTANTES para todo par
-- (ingrediente, unidad) usado en recetas que aún no tenga equivalencia activa.
--   masa     -> gramos = factor_a_base de la unidad
--   volumen  -> gramos = factor_a_base (densidad ~1)
--   discreto -> gramos = peso_estimado_g del ingrediente (ya corregido en PASO 0)
-- ----------------------------------------------------------------------------
INSERT INTO ingredientes_equivalencias
    (ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso, observacion, estado_activo)
SELECT DISTINCT
    ri.ingrediente_id,
    (SELECT MIN(ins.id) FROM insumos ins WHERE ins.ingrediente_id = ri.ingrediente_id),
    ri.unidad_medida_id,
    CASE
      WHEN um.tipo_magnitud = 'masa'     THEN um.factor_a_base
      WHEN um.tipo_magnitud = 'volumen'  THEN um.factor_a_base
      ELSE COALESCE(i.peso_estimado_g, 10)
    END,
    'Seed automático COM-67 v2',
    TRUE
FROM receta_ingrediente ri
JOIN ingredientes i     ON i.id  = ri.ingrediente_id
JOIN unidades_medida um ON um.id = ri.unidad_medida_id
WHERE EXISTS (SELECT 1 FROM insumos ins WHERE ins.ingrediente_id = ri.ingrediente_id)
  AND NOT EXISTS (
        SELECT 1 FROM ingredientes_equivalencias ie
        WHERE ie.ingrediente_id = ri.ingrediente_id
          AND ie.unidad_uso_id  = ri.unidad_medida_id
          AND ie.estado_activo  = TRUE
      );

COMMIT;