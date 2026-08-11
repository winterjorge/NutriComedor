-- =========================================================================
-- Poblado de Datos Maestros - NutriComedor OSB
-- =========================================================================

-- Categorías
INSERT INTO categorias_alimentos (nombre) VALUES 
('Vegetales y Hortalizas'), 
('Frutas'), 
('Proteinas'), 
('Cereales, Tuberculos y Raices'), 
('Lacteos y derivados'), 
('Grasas saludables y aceites'), 
('Condimentos y Otros');

-- Unidades de medida (incluye unidades de cocina)
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
('Rodaja', 'rdj', 'discreto', 1.00);

-- Ingredientes CON PESOS ESTIMADOS (peso_estimado_g en gramos)
-- Proteínas
INSERT INTO ingredientes (nombre, categoria_id, unidad_medida_id, peso_estimado_g) VALUES 
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
('Queso', 5, 2, 100.00);

-- Insumos
INSERT INTO insumos (ingrediente_id, nombre, unidad_medida_id) VALUES 
((SELECT id FROM ingredientes WHERE nombre = 'Pollo'), 'Pollo (pierna)', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Pollo'), 'Pollo vivo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Arroz'), 'Arroz corriente', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Arroz'), 'Arroz extra', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Arroz'), 'Arroz superior', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Lentejas'), 'Lentejas', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa canchan', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa amarilla', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), 'Cebolla roja', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), 'Aceite vegetal granel', 3),
((SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), 'Aceite cocinero botella 900ml', 8),
((SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), 'Zanahoria', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), 'Cebolla cabeza blanca', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), 'Cebolla china', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Ajo'), 'Ajo criollo o napuri', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Ajo'), 'Ajo morado', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Tomate'), 'Tomate', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Pimenton'), 'Pimiento morron', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), 'Arveja verde americana', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), 'Arveja verde blanca serrana', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Limon'), 'Limon sutil bolsa', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Limon'), 'Limon sutil cajon', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa blanca', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa huayro', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa yungay', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa unica', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa peruanita', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa huamantanga', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa negra andina', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Papa'), 'Papa color', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), 'Sal yodada', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Palillo'), 'Palillo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Comino'), 'Comino', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), 'Pimienta', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), 'Hierbabuena', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Perejil'), 'Perejil', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Cilantro'), 'Cilantro', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Higado de res'), 'Higado de res', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Espinaca'), 'Espinaca', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Sillao'), 'Sillao', 4),
((SELECT id FROM ingredientes WHERE nombre = 'Kion'), 'Kion', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Vinagre'), 'Vinagre', 4),
((SELECT id FROM ingredientes WHERE nombre = 'Aceituna'), 'Aceituna', 8),
((SELECT id FROM ingredientes WHERE nombre = 'Pasas'), 'Pasas', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), 'Sangrecita', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Molleja'), 'Molleja', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Bofe'), 'Bofe', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Corazon de pollo'), 'Corazon de pollo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Higado de pollo'), 'Higado de pollo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Carne molida'), 'Carne molida', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Quinua'), 'Quinua', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Trigo'), 'Trigo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Mote de maiz'), 'Mote de maiz', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Tallarin'), 'Tallarin', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Olluco'), 'Olluco', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Choclo'), 'Choclo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Caigua'), 'Caigua', 8),
((SELECT id FROM ingredientes WHERE nombre = 'Brocoli'), 'Brocoli', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Pimiento'), 'Pimiento', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Apio'), 'Apio', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Habas verdes'), 'Habas verdes', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Vainitas'), 'Vainitas', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Habas secas'), 'Habas secas', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Garbanzo'), 'Garbanzo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Charqui'), 'Charqui', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Tomatillo'), 'Tomatillo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Fideos tornillo'), 'Fideos tornillo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Huevo'), 'Huevos rosados', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Lechuga'), 'Lechuga', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Zapallo'), 'Zapallo', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Yuca'), 'Yuca', 1),
((SELECT id FROM ingredientes WHERE nombre = 'Pan'), 'Pan', 8),
((SELECT id FROM ingredientes WHERE nombre = 'Leche'), 'Leche', 4),
((SELECT id FROM ingredientes WHERE nombre = 'Queso'), 'Queso', 1);

-- Historial de precios
INSERT INTO historial_precios (insumo_id, fecha, precio_prom) VALUES
(1, CURRENT_DATE, 8.50), (2, CURRENT_DATE, 6.00), (3, CURRENT_DATE, 1.92), 
(4, CURRENT_DATE, 2.88), (5, CURRENT_DATE, 2.02), (6, CURRENT_DATE, 3.89), 
(7, CURRENT_DATE, 5.50), (8, CURRENT_DATE, 2.00), (9, CURRENT_DATE, 4.50), 
(10, CURRENT_DATE, 1.80), (11, CURRENT_DATE, 6.50), (12, CURRENT_DATE, 0.85),
(13, CURRENT_DATE, 1.70), (14, CURRENT_DATE, 3.50), (15, CURRENT_DATE, 5.75),
(16, CURRENT_DATE, 7.75), (17, CURRENT_DATE, 3.06), (18, CURRENT_DATE, 2.08),
(19, CURRENT_DATE, 3.18), (20, CURRENT_DATE, 2.55), (21, CURRENT_DATE, 1.72),
(22, CURRENT_DATE, 2.07), (23, CURRENT_DATE, 1.08), (24, CURRENT_DATE, 1.58),
(25, CURRENT_DATE, 1.08), (26, CURRENT_DATE, 1.33), (27, CURRENT_DATE, 1.50),
(28, CURRENT_DATE, 1.53), (29, CURRENT_DATE, 1.13), (30, CURRENT_DATE, 1.13),
(31, CURRENT_DATE, 1.50), (32, CURRENT_DATE, 2.00), (33, CURRENT_DATE, 3.00),
(34, CURRENT_DATE, 4.00), (35, CURRENT_DATE, 2.50), (36, CURRENT_DATE, 2.00),
(37, CURRENT_DATE, 2.50), (38, CURRENT_DATE, 12.00), (39, CURRENT_DATE, 2.50),
(40, CURRENT_DATE, 8.00), (41, CURRENT_DATE, 15.00), (42, CURRENT_DATE, 3.00),
(43, CURRENT_DATE, 18.00), (44, CURRENT_DATE, 8.00), (45, CURRENT_DATE, 6.00),
(46, CURRENT_DATE, 10.00), (47, CURRENT_DATE, 15.00), (48, CURRENT_DATE, 4.00),
(49, CURRENT_DATE, 3.50), (50, CURRENT_DATE, 3.00), (51, CURRENT_DATE, 2.00),
(52, CURRENT_DATE, 2.50), (53, CURRENT_DATE, 2.00), (54, CURRENT_DATE, 3.00),
(55, CURRENT_DATE, 4.00), (56, CURRENT_DATE, 1.50), (57, CURRENT_DATE, 2.50),
(58, CURRENT_DATE, 3.00), (59, CURRENT_DATE, 2.00), (60, CURRENT_DATE, 5.00),
(61, CURRENT_DATE, 1.80), (62, CURRENT_DATE, 2.20), (63, CURRENT_DATE, 2.00),
(64, CURRENT_DATE, 1.50), (65, CURRENT_DATE, 1.20), (66, CURRENT_DATE, 1.00),
(67, CURRENT_DATE, 2.50), (68, CURRENT_DATE, 3.50), (69, CURRENT_DATE, 4.00);

-- Presupuesto
INSERT INTO presupuesto_semanal (fondo_total, dias_operativos, comensales_diarios, presupuesto_por_racion) VALUES 
(500.00, 5, 100, 1.00);

-- Usuario
INSERT INTO usuarios (documento_identidad, nombres, apellido_paterno, apellido_materno, fecha_nacimiento, clave_hash) VALUES 
('43604221', 'Jorge luis', 'Winter', 'Arboleda', '1986-04-23', 'hash_123456');

-- Comensales
INSERT INTO comensales (tipo_documento, documento_identidad, nombres, tipo_comensal) VALUES
('DNI', '10203040', 'Maria lopez', 'Afiliado'),
('DNI', '80901020', 'Don jose ramirez', 'Social'),
('DNI', '40506070', 'Carlos mendoza', 'Normal'),
('CE', '001122334', 'Ana perez', 'Social');

-- Padrón diario
INSERT INTO padron_diario (comensal_id, fecha, tipo_comensal_venta, tipo_menu, raciones, monto_pagado, observacion) VALUES
(1, CURRENT_DATE, 'Afiliado', 'Almuerzo regular', 2, 6.00, 'Vino con sus hijos'),
(2, CURRENT_DATE, 'Social', 'Menu social reforzado', 1, 0.00, ''),
(3, CURRENT_DATE, 'Normal', 'Almuerzo regular', 1, 5.00, '');