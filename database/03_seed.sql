-- =========================================================================
-- 03_seed.sql (antes seed.sql) - Poblado de Datos Maestros - NutriComedor OSB
-- =========================================================================
-- Historial:
--  - Sprint 1: categorías, unidades, ingredientes, insumos, precios, presupuesto,
--    usuario piloto, comensales y padrón inicial.
--  - COM-36 v2: se comentan los bloques de insumos e historial_precios (los trae el
--    scraper) y se corrige el INSERT de presupuesto_semanal (columnas eliminadas).
--  - COM-40: el usuario piloto se creaba con rol explícito de comedor.
--  - COM-40 v2 (este archivo): la carga inicial YA NO crea usuarios de comedor.
--    El INSERT de usuarios queda COMENTADO: los únicos usuarios de arranque son los
--    dos administradores de sistema canónicos (DNI 00000000 y 99999999), que crea el
--    db_bootstrap; todos los demás usuarios se crean manualmente desde la interfaz
--    (flujos COM-26 y COM-39). Los comensales y el padrón inicial se conservan
--    (son datos de negocio, no cuentas de acceso).
-- =========================================================================

-- ------------------------------------------
-- 1) Categorías
-- ------------------------------------------
INSERT INTO categorias_alimentos (nombre) VALUES
('Vegetales y Hortalizas'),
('Frutas'),
('Proteinas'),
('Cereales, Tuberculos y Raices'),
('Lacteos y derivados'),
('Grasas saludables y aceites'),
('Condimentos y Otros')
ON CONFLICT (nombre) DO NOTHING;

-- ------------------------------------------
-- 2) Unidades de medida (incluye unidades de cocina)
-- ------------------------------------------
INSERT INTO unidades_medida (nombre, abreviatura, tipo_magnitud, factor_a_base) VALUES
('Kilogramo', 'kg', 'masa', 1000.00),
('Gramo', 'g', 'masa', 1.00),
('Litro', 'l', 'volumen', 1000.00),
('Mililitro', 'ml', 'volumen', 1.00),
('Taza', 'tz', 'volumen', 250.00),
('Cucharada', 'cda', 'volumen', 15.00),
('Pizca', 'pz', 'masa', 1.00),
('Unidad', 'und', 'discreto', 1.00),
('Cucharadita', 'cdta', 'volumen', 5.00),
('Diente', 'dte', 'discreto', 1.00),
('Rama', 'rma', 'discreto', 1.00),
('Atado', 'atd', 'discreto', 1.00),
('Rodaja', 'rdj', 'discreto', 1.00)
ON CONFLICT (nombre) DO NOTHING;

-- ------------------------------------------
-- 3) Ingredientes CON PESOS ESTIMADOS (peso_estimado_g en gramos)
-- ------------------------------------------
INSERT INTO ingredientes (nombre, categoria_id, unidad_medida_id, peso_estimado_g) VALUES
-- Proteínas
('Pollo', 3, 2, 250.00),
('Higado de res', 3, 2, 250.00),
('Higado de pollo', 3, 2, 200.00),
('Molleja', 3, 2, 200.00),
('Bofe', 3, 2, 200.00),
('Corazon de pollo', 3, 2, 150.00),
('Carne molida', 3, 2, 200.00),
('Charqui', 3, 2, 150.00),
('Sangrecita', 3, 2, 150.00),
('Huevo', 3, 8, 50.00),
('Arvejas', 3, 2, 100.00),
('Habas secas', 3, 2, 100.00),
('Garbanzo', 3, 2, 100.00),
('Lentejas', 3, 2, 100.00),
-- Cereales y tubérculos
('Arroz', 4, 2, 1000.00),
('Quinua', 4, 2, 1000.00),
('Trigo', 4, 2, 1000.00),
('Mote de maiz', 4, 2, 1000.00),
('Tallarin', 4, 2, 1000.00),
('Fideos tornillo', 4, 2, 1000.00),
('Papa', 4, 8, 150.00),
('Papa amarilla', 4, 8, 150.00),
('Papa blanca', 4, 8, 150.00),
('Yuca', 4, 8, 300.00),
('Olluco', 4, 8, 150.00),
-- Vegetales y hortalizas
('Cebolla', 1, 8, 100.00),
('Cebolla china', 1, 8, 50.00),
('Espinaca', 1, 8, 100.00),
('Zapallo', 1, 8, 500.00),
('Tomate', 1, 8, 120.00),
('Tomatillo', 1, 8, 100.00),
('Choclo', 1, 8, 200.00),
('Caigua', 1, 8, 150.00),
('Brocoli', 1, 8, 200.00),
('Pimiento', 1, 8, 150.00),
('Pimenton', 1, 8, 150.00),
('Apio', 1, 8, 50.00),
('Lechuga', 1, 8, 200.00),
('Zanahoria', 1, 8, 70.00),
('Habas verdes', 1, 2, 100.00),
('Vainitas', 1, 2, 100.00),
-- Frutas
('Limon', 2, 8, 50.00),
('Pasas', 2, 2, 10.00),
-- Grasas
('Aceite vegetal', 6, 4, 1000.00),
('Aceituna', 6, 8, 5.00),
-- Condimentos
('Sal yodada', 7, 7, 5.00),
('Ajo', 7, 10, 10.00),
('Pimienta', 7, 7, 5.00),
('Comino', 7, 7, 5.00),
('Oregano', 7, 7, 5.00),
('Laurel', 7, 7, 5.00),
('Palillo', 7, 7, 5.00),
('Perejil', 7, 11, 20.00),
('Hierbabuena', 7, 11, 20.00),
('Cilantro', 7, 11, 20.00),
('Kion', 7, 2, 15.00),
('Sillao', 7, 4, 15.00),
('Vinagre', 7, 4, 15.00),
('Azucar', 7, 2, 10.00),
-- Lácteos
('Leche', 5, 4, 1000.00),
('Pan', 5, 8, 50.00),
('Queso', 5, 2, 100.00)
ON CONFLICT (nombre) DO NOTHING;

-- ------------------------------------------
-- 4) INSUMOS: BLOQUE COMENTADO (COM-36 v2).
--    El catálogo de insumos lo crea/actualiza el scraper SISAP al correr.
--    (El bloque original con ~70 insumos quedó comentado en COM-36 v2 para no
--     sembrar datos que el scraper trae reales; se conserva en el historial git.)
-- ------------------------------------------

-- ------------------------------------------
-- 5) HISTORIAL DE PRECIOS: BLOQUE COMENTADO (COM-36 v2).
--    NO se siembran precios ficticios: los precios reales los trae el scraper.
-- ------------------------------------------

-- ------------------------------------------
-- 6) Presupuesto semanal inicial
-- COM-36 v2 (trazabilidad): versión ROTA comentada (columnas eliminadas por init.sql):
-- INSERT INTO presupuesto_semanal (fondo_total, dias_operativos, comensales_diarios, presupuesto_por_racion) VALUES
-- (500.00, 5, 100, 1.00);
-- ------------------------------------------
INSERT INTO presupuesto_semanal (fondo_total, dias_operativos, fecha_referencia)
VALUES (500.00, 5, CURRENT_DATE);

-- ------------------------------------------
-- 7) USUARIOS: BLOQUE COMENTADO (COM-40 v2).
--    La carga inicial YA NO crea usuarios de comedor (antes: usuario piloto DNI
--    43604221 como 'Administrador'/'Administradora'). Los únicos usuarios de arranque
--    son los administradores de sistema canónicos DNI 00000000 y 99999999, creados por
--    db_bootstrap con clave provisoria Admin2026. Todos los demás usuarios se crean
--    manualmente desde la interfaz (COM-26 / COM-39).
-- COM-40 (trazabilidad): versión con rol explícito de comedor, comentada:
-- INSERT INTO usuarios (documento_identidad, nombres, apellido_paterno, apellido_materno, fecha_nacimiento, clave_hash, rol) VALUES
-- ('43604221', 'Jorge luis', 'Winter', 'Arboleda', '1986-04-23', 'hash_123456', 'Administrador')
-- ON CONFLICT (documento_identidad) DO NOTHING;
-- Sprint 1 (trazabilidad): versión original sin rol, comentada:
-- INSERT INTO usuarios (documento_identidad, nombres, apellido_paterno, apellido_materno, fecha_nacimiento, clave_hash) VALUES
-- ('43604221', 'Jorge luis', 'Winter', 'Arboleda', '1986-04-23', 'hash_123456');
-- ------------------------------------------

-- ------------------------------------------
-- 8) Comensales iniciales del padrón (datos de negocio, no cuentas de acceso)
-- ------------------------------------------
INSERT INTO comensales (tipo_documento, documento_identidad, nombres, tipo_comensal) VALUES
('DNI', '10203040', 'Maria lopez', 'Afiliado'),
('DNI', '80901020', 'Don jose ramirez', 'Social'),
('DNI', '40506070', 'Carlos mendoza', 'Normal'),
('CE', '001122334', 'Ana perez', 'Social')
ON CONFLICT (documento_identidad) DO NOTHING;

-- ------------------------------------------
-- 9) Padrón diario inicial (subconsultas por documento, sin ids hardcodeados)
-- ------------------------------------------
INSERT INTO padron_diario (comensal_id, fecha, tipo_comensal_venta, tipo_menu, raciones, monto_pagado, observacion) VALUES
((SELECT id FROM comensales WHERE documento_identidad = '10203040'), CURRENT_DATE, 'Afiliado', 'Almuerzo regular', 2, 6.00, 'Vino con sus hijos'),
((SELECT id FROM comensales WHERE documento_identidad = '80901020'), CURRENT_DATE, 'Social', 'Menu social reforzado', 1, 0.00, ''),
((SELECT id FROM comensales WHERE documento_identidad = '40506070'), CURRENT_DATE, 'Normal', 'Almuerzo regular', 1, 5.00, '');