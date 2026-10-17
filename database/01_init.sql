-- =========================================================================
-- Script de Creación de Tablas - NutriComedor OSB
-- =========================================================================
-- Historial:
--  - Sprint 1/2: versión original.
--  - COM-48 (este archivo): esquema multi-componente de recetas:
--      * Nueva tabla recetas_componentes (catálogo extensible: Ensalada, Plato de
--        fondo, Refresco, Fruta; permite agregar Sopa u otros sin tocar código).
--      * receta_ingrediente gana componente_id (FK NOT NULL) y la unicidad pasa a ser
--        (receta_id, ingrediente_id, componente_id, unidad_medida_id): el mismo
--        ingrediente puede usarse en varios componentes con cantidades INDEPENDIENTES
--        (ej. limón en Ensalada y en Refresco).
--      * COM-48 Parte 2: componente_id tiene DEFAULT fn_componente_default()
--        ('Plato de fondo'), de modo que los scripts de carga iniciales HISTÓRICOS
--        (04_poblar_recetas.sql sin columna de componente) sigan funcionando sin
--        modificarse: todas las líneas legacy caen en 'Plato de fondo', que es lo que
--        eran las recetas hasta COM-48. La nutrición (6 campos) sigue POR RACIÓN en
--        recetas_almuerzo; cantidades y precios se dividen entre raciones (COM-47 v2).
--    Las definiciones anteriores (UNIQUE sin componente, columna sin default) quedan
--    COMENTADAS por trazabilidad.
DROP TABLE IF EXISTS padron_diario CASCADE;
DROP TABLE IF EXISTS comensales CASCADE;
DROP TABLE IF EXISTS presupuesto_semanal CASCADE;
DROP TABLE IF EXISTS receta_ingrediente CASCADE;
DROP TABLE IF EXISTS recetas_componentes CASCADE;
DROP TABLE IF EXISTS recetas_almuerzo CASCADE;
DROP TABLE IF EXISTS historial_precios CASCADE;
DROP TABLE IF EXISTS insumos CASCADE;
DROP TABLE IF EXISTS ingredientes CASCADE;
DROP TABLE IF EXISTS categorias_alimentos CASCADE;
DROP TABLE IF EXISTS unidades_medida CASCADE;
DROP TABLE IF EXISTS usuarios CASCADE;

CREATE TABLE categorias_alimentos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT
);

CREATE TABLE unidades_medida (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    abreviatura VARCHAR(10) NOT NULL UNIQUE,
    tipo_magnitud VARCHAR(20) NOT NULL,
    factor_a_base NUMERIC(10, 4) NOT NULL
);

CREATE TABLE ingredientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    categoria_id INT REFERENCES categorias_alimentos(id),
    unidad_medida_id INT REFERENCES unidades_medida(id),
    peso_estimado_g NUMERIC(8, 2) DEFAULT 100.00,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

CREATE TABLE insumos (
    id SERIAL PRIMARY KEY,
    ingrediente_id INT REFERENCES ingredientes(id) ON DELETE SET NULL,
    nombre VARCHAR(150) NOT NULL UNIQUE,
    unidad_medida_id INT REFERENCES unidades_medida(id),
    kcal_por_unidad NUMERIC(8, 2) NOT NULL DEFAULT 0.00,
    proteinas_por_unidad NUMERIC(8, 2) NOT NULL DEFAULT 0.00,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

CREATE TABLE historial_precios (
    id SERIAL PRIMARY KEY,
    insumo_id INT REFERENCES insumos(id) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    mercado VARCHAR(50) DEFAULT 'SISAP',
    precio_min NUMERIC(8, 2),
    precio_prom NUMERIC(8, 2) NOT NULL,
    precio_max NUMERIC(8, 2),
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE(fecha, insumo_id, mercado)
);

-- Tabla de recetas: nutrición POR RACIÓN (6 valores) y raciones para análisis por porción
CREATE TABLE recetas_almuerzo (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE,
    descripcion TEXT,
    raciones INT NOT NULL DEFAULT 4,
    viabilidad_historica BOOLEAN DEFAULT TRUE,
    hierro_mg NUMERIC(8, 2),
    proteina_g NUMERIC(8, 2),
    energia_kcal NUMERIC(8, 2),
    vitamina_a_ug NUMERIC(8, 2),
    zinc_mg NUMERIC(8, 2),
    carbohidratos_g NUMERIC(8, 2),
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

-- COM-48: catálogo de componentes (categorías) dentro de una receta.
-- Extensible: basta INSERTar 'Sopa' para habilitarlo en toda la aplicación.
CREATE TABLE recetas_componentes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT,
    orden INT NOT NULL DEFAULT 0,
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

-- COM-48 Parte 2: función de default para compatibilidad con cargas iniciales
-- históricas (04_poblar_recetas.sql sin columna componente_id). Devuelve el id del
-- componente 'Plato de fondo'; se evalúa al momento de cada INSERT.
CREATE OR REPLACE FUNCTION fn_componente_default() RETURNS INT AS $$
    SELECT id FROM recetas_componentes WHERE nombre = 'Plato de fondo';
$$ LANGUAGE sql STABLE;

-- COM-48: puente receta-ingrediente CON componente. Cada fila es independiente:
-- el mismo ingrediente puede repetirse en componentes distintos con cantidades propias.
CREATE TABLE receta_ingrediente (
    id SERIAL PRIMARY KEY,
    receta_id INT REFERENCES recetas_almuerzo(id) ON DELETE CASCADE,
    ingrediente_id INT REFERENCES ingredientes(id) ON DELETE CASCADE,
    -- COM-48 Parte 2 (trazabilidad): definición anterior comentada:
    -- componente_id INT NOT NULL REFERENCES recetas_componentes(id),
    componente_id INT NOT NULL DEFAULT fn_componente_default() REFERENCES recetas_componentes(id),
    unidad_medida_id INT REFERENCES unidades_medida(id),
    cantidad_requerida NUMERIC(8, 2) NOT NULL,
    -- COM-48 (trazabilidad): unicidad anterior COMENTADA (no distinguía componente):
    -- UNIQUE(receta_id, ingrediente_id, unidad_medida_id)
    UNIQUE(receta_id, ingrediente_id, componente_id, unidad_medida_id)
);

CREATE TABLE presupuesto_semanal (
    id SERIAL PRIMARY KEY,
    fondo_total NUMERIC(10, 2) NOT NULL,
    dias_operativos INT NOT NULL,
    comensales_diarios INT NOT NULL,
    presupuesto_por_racion NUMERIC(8, 2) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    tipo_documento VARCHAR(20) NOT NULL DEFAULT 'DNI',
    documento_identidad VARCHAR(13) UNIQUE NOT NULL,
    nombres VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    nacionalidad VARCHAR(50) NOT NULL DEFAULT 'Peruana',
    direccion TEXT,
    telefono_celular VARCHAR(15),
    clave_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(50) NOT NULL DEFAULT 'Administradora',
    estado_activo BOOLEAN DEFAULT TRUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

CREATE TABLE comensales (
    id SERIAL PRIMARY KEY,
    tipo_documento VARCHAR(20) NOT NULL DEFAULT 'DNI',
    documento_identidad VARCHAR(15) UNIQUE NOT NULL,
    nombres VARCHAR(150) NOT NULL,
    edad INT,
    ingreso_mensual NUMERIC(8, 2),
    indice_desnutricion INT CHECK (indice_desnutricion >= 1 AND indice_desnutricion <= 10),
    tipo_comensal VARCHAR(20) NOT NULL CHECK (tipo_comensal IN ('Social', 'Afiliado', 'Normal')),
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

CREATE TABLE padron_diario (
    id SERIAL PRIMARY KEY,
    comensal_id INT REFERENCES comensales(id),
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    tipo_menu VARCHAR(100) DEFAULT 'Almuerzo regular',
    tipo_comensal_venta VARCHAR(20) NOT NULL CHECK (tipo_comensal_venta IN ('Social', 'Afiliado', 'Normal')),
    raciones INT NOT NULL CHECK (raciones > 0),
    monto_pagado NUMERIC(8, 2) NOT NULL DEFAULT 0.00,
    observacion TEXT,
    motivo_modificacion TEXT,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);

-- ==============================================================================================
-- Modificar tabla presupuesto_semanal para almacenar planificación completa
ALTER TABLE presupuesto_semanal
DROP COLUMN IF EXISTS comensales_diarios,
DROP COLUMN IF EXISTS presupuesto_por_racion;
ALTER TABLE presupuesto_semanal
ADD COLUMN IF NOT EXISTS fecha_referencia DATE,
ADD COLUMN IF NOT EXISTS costo_total_semana NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS recoleccion_total_proyectada NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS margen NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS viable BOOLEAN DEFAULT TRUE;

-- Crear tabla para almacenar los días de la planificación
CREATE TABLE IF NOT EXISTS planificacion_dia (
    id SERIAL PRIMARY KEY,
    presupuesto_semanal_id INT REFERENCES presupuesto_semanal(id) ON DELETE CASCADE,
    dia INT NOT NULL,
    dia_nombre VARCHAR(50) NOT NULL,
    comensales_social INT DEFAULT 0,
    comensales_afiliado INT DEFAULT 0,
    comensales_normal INT DEFAULT 0,
    total_comensales INT NOT NULL,
    receta_id INT REFERENCES recetas_almuerzo(id),
    nombre_receta VARCHAR(150) NOT NULL,
    costo_racion NUMERIC(8, 2) NOT NULL,
    costo_total NUMERIC(10, 2) NOT NULL,
    recoleccion_proyectada NUMERIC(10, 2) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
CREATE INDEX IF NOT EXISTS idx_planificacion_dia_presupuesto ON planificacion_dia(presupuesto_semanal_id);