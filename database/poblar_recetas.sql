-- =========================================================================
-- SCRIPT DE POBLACIÓN DE RECETAS (PASO 2 - DESPUÉS DE init.sql Y seed.sql)
-- Estructura: receta_ingrediente CON unidad_medida_id
-- =========================================================================

-- Ingredientes faltantes
INSERT INTO ingredientes (nombre, categoria_id, unidad_medida_id, peso_estimado_g) VALUES
('Aji amarillo molido', (SELECT id FROM categorias_alimentos WHERE nombre = 'Condimentos y Otros'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 10.00),
('Aji panca molido', (SELECT id FROM categorias_alimentos WHERE nombre = 'Condimentos y Otros'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 10.00)
ON CONFLICT (nombre) DO NOTHING;

-- RECETAS
INSERT INTO recetas_almuerzo (nombre, descripcion, hierro_mg, proteina_g, energia_kcal) VALUES
('Tortillas de sangrecita con quinua y espinaca', 'Tortilla de sangre de pollo con quinua y vegetales', 100.50, 31.00, 805.00),
('Arroz chaufa con higado', 'Chaufa peruano con higado de res', 56.80, 89.50, 2194.00),
('Saltado de molleja con yuca', 'Saltado con mollejas y yuca', 30.50, 117.50, 1945.50),
('Patachi', 'Sopa peruana de trigo con charqui', 37.50, 171.90, 1355.50),
('Chanfainita de bofe con mote', 'Chanfainita con mote de maiz', 37.10, 75.95, 2446.50),
('Locrito de zapallo con saltado de higado', 'Guiso de zapallo con higado de pollo', 45.50, 101.00, 3251.00),
('Chaufa de sangrecita con ensalada a la pañaquita', 'Chaufa de sangrecita con ensalada de tomate y limon', 104.00, 106.00, 3318.00),
('Sangrecita criolla', 'Sangrecita salteada con verduras y papa', 160.50, 117.50, 1450.50),
('Sangrecita primaveral', 'Saltado de sangrecita con verduras y arroz', 105.50, 93.40, 2203.76),
('Cau cau de sangrecita acompañado de trigo partido', 'Cau cau de sangrecita con trigo', 122.00, 115.50, 2343.00),
('Caigua rellena con higado', 'Caiguas rellenas de higado', 55.30, 171.20, 3695.00),
('Tallarines en salsa de bofe', 'Tallarines con salsa de bofe', 31.45, 97.75, 2365.00),
('Morcillita a la jardinera con ensalada de tomatillo', 'Morcillita con verduras', 102.00, 115.75, 2255.00),
('Causa rellena con sangrecita', 'Causa limeña rellena de sangrecita', 55.00, 59.50, 2265.00),
('Cau cau de bofe', 'Cau cau tradicional de bofe', 42.50, 120.00, 2820.00),
('Sangrecita multicolor', 'Saltado de sangrecita con verduras', 72.65, 83.40, 2666.50),
('Chaufa de sangrecita con quinua', 'Chaufa peruano de sangrecita y quinua', 166.35, 133.95, 3425.00),
('Ensalada de fideos con trocitos de higado', 'Ensalada de fideos con higado', 41.00, 96.50, 2642.00),
('Olluquito con sangrecita y carne molida', 'Olluquito con sangrecita', 60.20, 85.00, 2300.00),
('Seco de quinua con corazon de pollo', 'Seco de quinua con corazon de pollo', 25.50, 64.00, 2075.00)
ON CONFLICT (nombre) DO NOTHING;

-- RECETA 1: Tortillas de sangrecita con quinua y espinaca
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Tortillas de sangrecita con quinua y espinaca')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.75),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Espinaca'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Huevo'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Quinua'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Comino'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50);

-- RECETA 2: Arroz chaufa con higado
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Arroz chaufa con higado')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Higado de res'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimenton'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Huevo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Espinaca'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sillao'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.00);

-- RECETA 3: Saltado de molleja con yuca
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Saltado de molleja con yuca')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Yuca'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Molleja'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tomate'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sillao'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Vinagre'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Comino'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Perejil'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 2.00);

-- RECETA 4: Patachi
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Patachi')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Trigo'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 200.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Habas secas'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 100.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 100.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Garbanzo'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 50.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Charqui'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 200.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Mililitro'), 25.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Apio'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 5: Chanfainita de bofe con mote
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Chanfainita de bofe con mote')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Mote de maiz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.75),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Bofe'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Perejil'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Oregano'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 6: Locrito de zapallo con saltado de higado
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Locrito de zapallo con saltado de higado')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 10.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Higado de pollo'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Leche'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zapallo'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Habas verdes'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tomate'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Choclo'), (SELECT id FROM unidades_medida WHERE nombre = 'Rodaja'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Perejil'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Vinagre'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.00);

-- RECETA 7: Chaufa de sangrecita con ensalada a la pañaquita
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Chaufa de sangrecita con ensalada a la pañaquita')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 10.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla china'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Kion'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Huevo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sillao'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Azucar'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tomate'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Lechuga'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Limon'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00);

-- RECETA 8: Sangrecita criolla
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Sangrecita criolla')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa amarilla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Limon'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 6.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla china'), (SELECT id FROM unidades_medida WHERE nombre = 'Atado'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Comino'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Brocoli'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Vainitas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 2.50);

-- RECETA 9: Sangrecita primaveral
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Sangrecita primaveral')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Choclo'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Habas verdes'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Vainitas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.17),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Perejil'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Oregano'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla china'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.33),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Palillo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 0.50);

-- RECETA 10: Cau cau de sangrecita acompañado de trigo
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Cau cau de sangrecita acompañado de trigo partido')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Trigo'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50);

-- RECETA 11: Caigua rellena con higado
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Caigua rellena con higado')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Higado de res'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Caigua'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tomate'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji panca molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Comino'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Oregano'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceituna'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pasas'), (SELECT id FROM unidades_medida WHERE nombre = 'Gramo'), 10.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Huevo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pan'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00);

-- RECETA 12: Tallarines en salsa de bofe
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Tallarines en salsa de bofe')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Bofe'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tallarin'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tomate'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimiento'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.75),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Laurel'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Oregano'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 13: Morcillita a la jardinera con ensalada de tomatillo
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Morcillita a la jardinera con ensalada de tomatillo')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla china'), (SELECT id FROM unidades_medida WHERE nombre = 'Atado'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Tomatillo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Limon'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00);

-- RECETA 14: Causa rellena con sangrecita
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Causa rellena con sangrecita')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa amarilla'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.75),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Limon'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Caigua'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Lechuga'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 15: Cau cau de bofe
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Cau cau de bofe')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Bofe'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa blanca'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 4.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Limon'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Palillo'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 16: Sangrecita multicolor
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Sangrecita multicolor')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Choclo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Brocoli'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 17: Chaufa de sangrecita con quinua
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Chaufa de sangrecita con quinua')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Quinua'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Huevo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla china'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 5.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Perejil'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Hierbabuena'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Pimienta'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Comino'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sillao'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.00);

-- RECETA 18: Ensalada de fideos con trocitos de higado
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Ensalada de fideos con trocitos de higado')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Fideos tornillo'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Choclo'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Habas verdes'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Vainitas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Limon'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Higado de res'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.25),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);

-- RECETA 19: Olluquito con sangrecita y carne molida
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Olluquito con sangrecita y carne molida')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sangrecita'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Carne molida'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Olluco'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Diente'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Oregano'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Perejil'), (SELECT id FROM unidades_medida WHERE nombre = 'Rama'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50);

-- RECETA 20: Seco de quinua con corazon de pollo
WITH rec AS (SELECT id FROM recetas_almuerzo WHERE nombre = 'Seco de quinua con corazon de pollo')
INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida) VALUES
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Quinua'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Corazon de pollo'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arvejas'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.75),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Zanahoria'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Papa'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 3.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cebolla'), (SELECT id FROM unidades_medida WHERE nombre = 'Unidad'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Arroz'), (SELECT id FROM unidades_medida WHERE nombre = 'Kilogramo'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aceite vegetal'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 2.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Ajo'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Cilantro'), (SELECT id FROM unidades_medida WHERE nombre = 'Taza'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Aji amarillo molido'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharada'), 1.00),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Oregano'), (SELECT id FROM unidades_medida WHERE nombre = 'Cucharadita'), 0.50),
((SELECT id FROM rec), (SELECT id FROM ingredientes WHERE nombre = 'Sal yodada'), (SELECT id FROM unidades_medida WHERE nombre = 'Pizca'), 1.00);