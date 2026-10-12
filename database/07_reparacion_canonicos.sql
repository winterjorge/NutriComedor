-- ============================================================================
-- 07_reparacion_canonicos.sql
-- COM-68: reparación de datos maestros de ingredientes:
--   1) Reactiva canónicos genéricos (Papa, Cebolla, Papaya, Habas verdes)
--      quitando el prefijo [OBSOLETO] (solo si el nombre activo está libre).
--   2) Mueve insumos-variedad al canónico correcto (papas frescas -> Papa,
--      Papaya -> Papaya, Haba verde serrana -> Habas verdes).
--   3) Re-apunta líneas de receta que quedaron en el destino equivocado de una
--      fusión (ajiaco/chaufa/arroz-pescado -> Papa), conservando Carapulcra.
--   4) Re-sembrar equivalencias curadas (Unidad/Rodaja/Taza) para los canónicos.
--   5) Purga obsoletos totalmente vacíos (sin líneas, insumos, equivalencias ni
--      precios legacy): ruido sin valor de trazabilidad.
-- Re-ejecutable: cada paso es condicional.
-- ============================================================================
BEGIN;

-- ----------------------------------------------------------------------------
-- PASO 1: reactivar canónicos genéricos
-- ----------------------------------------------------------------------------
UPDATE ingredientes SET nombre = 'Papa', peso_estimado_g = 150.00
WHERE id = 21 AND nombre = '[OBSOLETO] Papa'
  AND NOT EXISTS (SELECT 1 FROM ingredientes x
                  WHERE x.id <> 21 AND x.nombre NOT LIKE '[OBSOLETO]%'
                    AND LOWER(x.nombre) = 'papa');

UPDATE ingredientes SET nombre = 'Cebolla', peso_estimado_g = 100.00
WHERE id = 26 AND nombre = '[OBSOLETO] Cebolla'
  AND NOT EXISTS (SELECT 1 FROM ingredientes x
                  WHERE x.id <> 26 AND x.nombre NOT LIKE '[OBSOLETO]%'
                    AND LOWER(x.nombre) = 'cebolla');

UPDATE ingredientes SET nombre = 'Papaya', peso_estimado_g = 250.00
WHERE id = 148 AND nombre = '[OBSOLETO] Papaya'
  AND NOT EXISTS (SELECT 1 FROM ingredientes x
                  WHERE x.id <> 148 AND x.nombre NOT LIKE '[OBSOLETO]%'
                    AND LOWER(x.nombre) = 'papaya');

UPDATE ingredientes SET nombre = 'Habas verdes', peso_estimado_g = 100.00
WHERE id = 40 AND nombre = '[OBSOLETO] Habas verdes'
  AND NOT EXISTS (SELECT 1 FROM ingredientes x
                  WHERE x.id <> 40 AND x.nombre NOT LIKE '[OBSOLETO]%'
                    AND LOWER(x.nombre) = 'habas verdes');

-- ----------------------------------------------------------------------------
-- PASO 2: mover insumos-variedad al canónico correcto
-- ----------------------------------------------------------------------------
-- Papas frescas (variedades) -> Papa (21). El insumo 131 (Papa seca) se queda en 107.
UPDATE insumos SET ingrediente_id = 21
WHERE ingrediente_id = 107
  AND id IN (128, 129, 130, 132, 185, 186, 187, 188, 189, 190);

-- Papaya (mal emparejada por el scraper con "papa") -> Papaya (148)
UPDATE insumos SET ingrediente_id = 148
WHERE id = 133 AND ingrediente_id = 107;

-- Haba verde serrana -> Habas verdes (40)
UPDATE insumos SET ingrediente_id = 40
WHERE id = 70 AND ingrediente_id = 74;

-- ----------------------------------------------------------------------------
-- PASO 3: re-apuntar líneas de receta al canónico Papa (21)
--         (Carapulcra 62 se conserva en Papa seca 107: uso legítimo)
-- ----------------------------------------------------------------------------
UPDATE receta_ingrediente ri SET ingrediente_id = 21
WHERE ri.ingrediente_id = 107
  AND ri.receta_id IN (60, 44, 51)
  AND NOT EXISTS (
      SELECT 1 FROM receta_ingrediente r2
      WHERE r2.receta_id = ri.receta_id
        AND r2.ingrediente_id = 21
        AND r2.componente_id = ri.componente_id
        AND r2.unidad_medida_id = ri.unidad_medida_id
  );

-- ----------------------------------------------------------------------------
-- PASO 4: equivalencias curadas para canónicos reactivados
--         (Unidad/Rodaja/Taza; Kg y g ya caen al fallback exacto)
-- ----------------------------------------------------------------------------
UPDATE ingredientes_equivalencias SET ingrediente_id = 21
WHERE ingrediente_id = 107
  AND insumo_id IN (128, 129, 130, 132, 185, 186, 187, 188, 189, 190);

UPDATE ingredientes_equivalencias SET gramos_por_unidad_uso = 150.00,
       observacion = 'Reparación COM-68: 1 papa mediana = 150 g'
WHERE ingrediente_id = 21
  AND unidad_uso_id = (SELECT id FROM unidades_medida WHERE nombre = 'Unidad');

UPDATE ingredientes_equivalencias SET gramos_por_unidad_uso = 100.00,
       observacion = 'Reparación COM-68: 1 rodaja de papa = 100 g'
WHERE ingrediente_id = 21
  AND unidad_uso_id = (SELECT id FROM unidades_medida WHERE nombre = 'Rodaja');

INSERT INTO ingredientes_equivalencias
    (ingrediente_id, insumo_id, unidad_uso_id, gramos_por_unidad_uso, observacion, estado_activo)
SELECT ins.ingrediente_id, ins.id, um.id,
       CASE um.nombre
           WHEN 'Unidad'  THEN COALESCE(i.peso_estimado_g, 100)
           WHEN 'Rodaja'  THEN 100.0
           WHEN 'Taza'    THEN CASE WHEN i.id = 26 THEN 120.0 ELSE 150.0 END
       END,
       'Reparación COM-68', TRUE
FROM insumos ins
JOIN ingredientes i ON i.id = ins.ingrediente_id
CROSS JOIN unidades_medida um
WHERE ins.ingrediente_id IN (21, 26, 40, 148)
  AND um.nombre IN ('Unidad', 'Rodaja', 'Taza')
ON CONFLICT (ingrediente_id, insumo_id, unidad_uso_id)
DO UPDATE SET gramos_por_unidad_uso = EXCLUDED.gramos_por_unidad_uso,
              estado_activo = TRUE,
              observacion = EXCLUDED.observacion;

-- ----------------------------------------------------------------------------
-- PASO 5: purga de obsoletos totalmente vacíos (sin referencias FK vivas)
-- ----------------------------------------------------------------------------
DELETE FROM ingredientes i
WHERE i.nombre LIKE '[OBSOLETO]%'
  AND NOT EXISTS (SELECT 1 FROM receta_ingrediente ri WHERE ri.ingrediente_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM insumos ins WHERE ins.ingrediente_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM ingredientes_equivalencias eq WHERE eq.ingrediente_id = i.id)
  AND NOT EXISTS (SELECT 1 FROM ingredientes_precios_manuales pm WHERE pm.ingrediente_id = i.id);

COMMIT;

-- ----------------------------------------------------------------------------
-- AUDITORÍA POST-REPARACIÓN
-- ----------------------------------------------------------------------------
-- 1) Canónicos activos con sus insumos
SELECT i.id, i.nombre, i.peso_estimado_g, COUNT(ins.id) AS n_insumos
FROM ingredientes i LEFT JOIN insumos ins ON ins.ingrediente_id = i.id
WHERE i.nombre IN ('Papa','Cebolla','Papaya','Habas verdes','Papa seca')
GROUP BY i.id, i.nombre, i.peso_estimado_g ORDER BY i.nombre;

-- 2) Obsoletos restantes (debería quedar vacío o casi vacío)
SELECT id, nombre FROM ingredientes WHERE nombre LIKE '[OBSOLETO]%' ORDER BY nombre;

-- 3) Líneas de receta de papa: ajiaco/chaufa/arroz-pescado -> Papa; carapulcra -> Papa seca
SELECT ri.receta_id, ra.nombre, i.nombre AS ingrediente, ri.cantidad_requerida, um.nombre
FROM receta_ingrediente ri
JOIN ingredientes i ON i.id = ri.ingrediente_id
JOIN recetas_almuerzo ra ON ra.id = ri.receta_id
JOIN unidades_medida um ON um.id = ri.unidad_medida_id
WHERE i.nombre IN ('Papa','Papa seca') ORDER BY ri.receta_id;