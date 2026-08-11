-- =========================================================================
-- SCRIPT DE POBLACIÓN DE DATOS FICTICIOS - ÚLTIMO AÑO
-- Genera comensales ficticios y atenciones reales de lunes a viernes
-- =========================================================================

-- ==========================================
-- PASO 1: POBLAR COMENSALES FICTICIOS
-- ==========================================
-- Generamos 200 comensales ficticios para tener variedad en el padrón
INSERT INTO comensales (tipo_documento, documento_identidad, nombres, tipo_comensal)
SELECT 
    'DNI',
    LPAD((10000000 + g)::text, 8, '0'),
    'Comensal ' || g,
    CASE 
        WHEN g <= 50 THEN 'Social'
        WHEN g <= 150 THEN 'Afiliado'
        ELSE 'Normal'
    END
FROM generate_series(1, 200) g
ON CONFLICT (documento_identidad) DO NOTHING;

-- ==========================================
-- PASO 2: POBLAR ATENCIONES DEL ÚLTIMO AÑO
-- ==========================================
-- Genera atenciones de lunes a viernes durante el último año
-- Reglas:
-- - Sociales: entre 20 y 25 diarios
-- - Afiliados: entre 45 y 50 diarios
-- - Normales: suficientes para completar 120 raciones totales

WITH fechas_laborables AS (
    -- Generar todas las fechas del último año (365 días hacia atrás)
    SELECT 
        (CURRENT_DATE - g)::date as fecha
    FROM generate_series(1, 365) g
    WHERE EXTRACT(DOW FROM (CURRENT_DATE - g)::date) BETWEEN 1 AND 5  -- Solo lunes(1) a viernes(5)
),
comensales_sociales AS (
    -- Obtener IDs de comensales sociales (mínimo 50 para rotación)
    SELECT id FROM comensales WHERE tipo_comensal = 'Social' LIMIT 50
),
comensales_afiliados AS (
    -- Obtener IDs de comensales afiliados (mínimo 100 para rotación)
    SELECT id FROM comensales WHERE tipo_comensal = 'Afiliado' LIMIT 100
),
comensales_normales AS (
    -- Obtener IDs de comensales normales (mínimo 50 para rotación)
    SELECT id FROM comensales WHERE tipo_comensal = 'Normal' LIMIT 50
)
INSERT INTO padron_diario (comensal_id, fecha, tipo_comensal_venta, tipo_menu, raciones, monto_pagado, observacion)
SELECT 
    comensal_id,
    fecha,
    tipo_comensal_venta,
    'Almuerzo regular',
    raciones,
    monto_pagado,
    'Registro ficticio - generado automáticamente'
FROM (
    -- Generar registros SOCIALES (20-25 por día)
    SELECT 
        (SELECT id FROM comensales_sociales ORDER BY RANDOM() LIMIT 1) as comensal_id,
        f.fecha,
        'Social' as tipo_comensal_venta,
        1 as raciones,
        0.00 as monto_pagado
    FROM fechas_laborables f,
    LATERAL generate_series(1, (20 + floor(random() * 6))::int) -- 20 a 25
    
    UNION ALL
    
    -- Generar registros AFILIADOS (45-50 por día)
    SELECT 
        (SELECT id FROM comensales_afiliados ORDER BY RANDOM() LIMIT 1) as comensal_id,
        f.fecha,
        'Afiliado' as tipo_comensal_venta,
        1 as raciones,
        3.00 as monto_pagado
    FROM fechas_laborables f,
    LATERAL generate_series(1, (45 + floor(random() * 6))::int) -- 45 a 50
    
    UNION ALL
    
    -- Generar registros NORMALES (hasta completar 120 raciones totales)
    SELECT 
        (SELECT id FROM comensales_normales ORDER BY RANDOM() LIMIT 1) as comensal_id,
        f.fecha,
        'Normal' as tipo_comensal_venta,
        1 as raciones,
        5.00 as monto_pagado
    FROM fechas_laborables f,
    LATERAL generate_series(1, (45 + floor(random() * 11))::int) -- 45 a 55 (para llegar a ~120 total)
) as registros;

-- ==========================================
-- VERIFICACIÓN
-- ==========================================
-- Mostrar resumen de datos generados
SELECT 
    'Comensales totales' as concepto,
    COUNT(*) as cantidad
FROM comensales

UNION ALL

SELECT 
    'Atenciones totales' as concepto,
    COUNT(*) as cantidad
FROM padron_diario

UNION ALL

SELECT 
    'Días con atenciones' as concepto,
    COUNT(DISTINCT fecha) as cantidad
FROM padron_diario

UNION ALL

SELECT 
    'Promedio social/día' as concepto,
    ROUND(AVG(cantidad)::numeric, 1) as cantidad
FROM (
    SELECT fecha, COUNT(*) as cantidad 
    FROM padron_diario 
    WHERE tipo_comensal_venta = 'Social' 
    GROUP BY fecha
) sub

UNION ALL

SELECT 
    'Promedio afiliado/día' as concepto,
    ROUND(AVG(cantidad)::numeric, 1) as cantidad
FROM (
    SELECT fecha, COUNT(*) as cantidad 
    FROM padron_diario 
    WHERE tipo_comensal_venta = 'Afiliado' 
    GROUP BY fecha
) sub

UNION ALL

SELECT 
    'Promedio normal/día' as concepto,
    ROUND(AVG(cantidad)::numeric, 1) as cantidad
FROM (
    SELECT fecha, COUNT(*) as cantidad 
    FROM padron_diario 
    WHERE tipo_comensal_venta = 'Normal' 
    GROUP BY fecha
) sub;