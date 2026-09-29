"""
esquema_ubicaciones.py
Objetivo: DDL del modelo de ubicación geográfica normalizada (COM-27): tablas
          departamentos, provincias, distritos y ubigeos, y las columnas de clave
          foránea que vinculan las tablas municipalidades y comedores a esta nueva
          fuente única de verdad geográfica.
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_ubicaciones(cur)`
     DESPUÉS de crear las tablas municipalidades y comedores (ver Parte 3).
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS / ADD COLUMN IF NOT EXISTS),
      por lo que pueden ejecutarse en cada arranque sin efectos secundarios.
Referencia: ticket COM-27 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""

# =========================================================================
# DDL: Catálogo de departamentos del Perú
# codigo = 2 primeros dígitos del ubigeo (único a nivel nacional)
# =========================================================================
DDL_DEPARTAMENTOS = """
CREATE TABLE IF NOT EXISTS departamentos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(2) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
"""

# =========================================================================
# DDL: Catálogo de provincias (cada una pertenece a un departamento)
# codigo = 4 primeros dígitos del ubigeo (único a nivel nacional)
# =========================================================================
DDL_PROVINCIAS = """
CREATE TABLE IF NOT EXISTS provincias (
    id SERIAL PRIMARY KEY,
    departamento_id INT NOT NULL REFERENCES departamentos(id) ON DELETE CASCADE,
    codigo VARCHAR(4) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
CREATE INDEX IF NOT EXISTS idx_provincias_departamento ON provincias(departamento_id);
"""

# =========================================================================
# DDL: Catálogo de distritos (cada uno pertenece a una provincia)
# codigo = 6 dígitos completos del ubigeo (único a nivel nacional)
# =========================================================================
DDL_DISTRITOS = """
CREATE TABLE IF NOT EXISTS distritos (
    id SERIAL PRIMARY KEY,
    provincia_id INT NOT NULL REFERENCES provincias(id) ON DELETE CASCADE,
    codigo VARCHAR(6) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
CREATE INDEX IF NOT EXISTS idx_distritos_provincia ON distritos(provincia_id);
"""

# =========================================================================
# DDL: Catálogo de ubigeos (cada uno pertenece a un distrito)
# El ubigeo es el código oficial de 6 dígitos del distrito.
# =========================================================================
DDL_UBIGEOS = """
CREATE TABLE IF NOT EXISTS ubigeos (
    id SERIAL PRIMARY KEY,
    distrito_id INT NOT NULL REFERENCES distritos(id) ON DELETE CASCADE,
    codigo VARCHAR(6) NOT NULL UNIQUE,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
CREATE INDEX IF NOT EXISTS idx_ubigeos_distrito ON ubigeos(distrito_id);
"""

# =========================================================================
# FK hacia la ubicación geográfica en municipalidades.
# COM-27: Se CONSERVAN las columnas de texto libres (departamento, provincia,
# distrito) como legado; las nuevas columnas *_id son la fuente de verdad.
# =========================================================================
DDL_MUNICIPALIDADES_UBICACION_FK = """
ALTER TABLE municipalidades
ADD COLUMN IF NOT EXISTS departamento_id INT REFERENCES departamentos(id),
ADD COLUMN IF NOT EXISTS provincia_id INT REFERENCES provincias(id),
ADD COLUMN IF NOT EXISTS distrito_id INT REFERENCES distritos(id),
ADD COLUMN IF NOT EXISTS ubigeo_id INT REFERENCES ubigeos(id);
CREATE INDEX IF NOT EXISTS idx_municipalidades_distrito ON municipalidades(distrito_id);
"""

# =========================================================================
# FK hacia la ubicación geográfica en comedores.
# COM-27: Se CONSERVAN las columnas de texto libres como legado; las nuevas
# columnas *_id son la fuente de verdad.
# =========================================================================
DDL_COMEDORES_UBICACION_FK = """
ALTER TABLE comedores
ADD COLUMN IF NOT EXISTS departamento_id INT REFERENCES departamentos(id),
ADD COLUMN IF NOT EXISTS provincia_id INT REFERENCES provincias(id),
ADD COLUMN IF NOT EXISTS distrito_id INT REFERENCES distritos(id);
CREATE INDEX IF NOT EXISTS idx_comedores_distrito ON comedores(distrito_id);
"""


def aplicar_esquema_ubicaciones(cur):
    """
    COM-27: Crea las tablas de ubicación geográfica y agrega las columnas FK a
    municipalidades y comedores. Es idempotente. El caller (db_bootstrap) es
    responsable del commit y de invocar esta función DESPUÉS de que existan las
    tablas municipalidades y comedores.
    """
    # 1. Tablas del catálogo geográfico (sin dependencias previas)
    cur.execute(DDL_DEPARTAMENTOS)
    cur.execute(DDL_PROVINCIAS)
    cur.execute(DDL_DISTRITOS)
    cur.execute(DDL_UBIGEOS)
    # 2. Columnas FK en municipalidades y comedores (requieren que esas tablas existan)
    cur.execute(DDL_MUNICIPALIDADES_UBICACION_FK)
    cur.execute(DDL_COMEDORES_UBICACION_FK)