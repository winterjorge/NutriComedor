"""
ubicaciones_seed.py
Objetivo: Importar el catálogo oficial de ubicación geográfica del Perú (departamentos,
          provincias, distritos y ubigeos) y las municipalidades con su nombre oficial y
          dirección, desde el CSV oficial (COM-27). La carga es idempotente: el caller la
          ejecuta solo si la tabla departamentos está vacía.
Uso: Importado por db_bootstrap.py, que ejecuta `importar_ubicaciones(cur)`.
Referencia: ticket COM-27 (solo trazabilidad; los nombres obedecen a la funcionalidad).

Historial de correcciones:
 - FIX: el upsert de municipalidades usaba ON CONFLICT (distrito_id, nombre), pero la
   tabla municipalidades no posee restricción única sobre esas columnas (error:
   "there is no unique or exclusion constraint matching the ON CONFLICT specification").
   Se reemplaza por un patrón SELECT -> INSERT/UPDATE apoyado en la restricción única
   de texto ya existente (departamento, provincia, distrito, nombre), que no depende
   de índices nuevos y persiste también los FK geográficos.
"""
import csv
import os

# Ruta del CSV oficial dentro del backend: backend/data/municipalidades_completo.csv
RUTA_CSV_UBICACIONES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'data', 'municipalidades_completo.csv'
)


def _id(fila):
    """Extrae el id de una fila devuelta por RealDictCursor o por un cursor plano."""
    return fila["id"] if isinstance(fila, dict) else fila[0]


def _upsert_departamento(cur, codigo, nombre):
    """Inserta o actualiza un departamento por su código (2 dígitos) y retorna su id."""
    cur.execute("""
        INSERT INTO departamentos (codigo, nombre)
        VALUES (%s, %s)
        ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id;
    """, (codigo, nombre))
    return _id(cur.fetchone())


def _upsert_provincia(cur, departamento_id, codigo, nombre):
    """Inserta o actualiza una provincia por su código (4 dígitos) y retorna su id."""
    cur.execute("""
        INSERT INTO provincias (departamento_id, codigo, nombre)
        VALUES (%s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id;
    """, (departamento_id, codigo, nombre))
    return _id(cur.fetchone())


def _upsert_distrito(cur, provincia_id, codigo, nombre):
    """Inserta o actualiza un distrito por su código (6 dígitos) y retorna su id."""
    cur.execute("""
        INSERT INTO distritos (provincia_id, codigo, nombre)
        VALUES (%s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id;
    """, (provincia_id, codigo, nombre))
    return _id(cur.fetchone())


def _upsert_ubigeo(cur, distrito_id, codigo):
    """Inserta o actualiza un ubigeo por su código completo y retorna su id."""
    cur.execute("""
        INSERT INTO ubigeos (distrito_id, codigo)
        VALUES (%s, %s)
        ON CONFLICT (codigo) DO UPDATE SET distrito_id = EXCLUDED.distrito_id
        RETURNING id;
    """, (distrito_id, codigo))
    return _id(cur.fetchone())


def _upsert_municipalidad(cur, dep_nombre, prov_nombre, dist_nombre,
                          departamento_id, provincia_id, distrito_id, ubigeo_id,
                          nombre, direccion):
    """
    FIX COM-27: upsert SIN ON CONFLICT sobre columnas FK. Se busca por la clave única
    de texto existente (departamento, provincia, distrito, nombre) y se inserta o
    actualiza según corresponda, persistiendo también los FK geográficos y el ubigeo.
    """
    cur.execute("""
        SELECT id FROM municipalidades
        WHERE departamento = %s AND provincia = %s AND distrito = %s AND nombre = %s;
    """, (dep_nombre, prov_nombre, dist_nombre, nombre))
    fila = cur.fetchone()
    if fila:
        cur.execute("""
            UPDATE municipalidades
            SET direccion = %s,
                departamento_id = %s,
                provincia_id = %s,
                distrito_id = %s,
                ubigeo_id = %s
            WHERE id = %s;
        """, (direccion, departamento_id, provincia_id, distrito_id, ubigeo_id, _id(fila)))
        return _id(fila)
    cur.execute("""
        INSERT INTO municipalidades
            (departamento, provincia, distrito, nombre, direccion,
             departamento_id, provincia_id, distrito_id, ubigeo_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (dep_nombre, prov_nombre, dist_nombre, nombre, direccion,
          departamento_id, provincia_id, distrito_id, ubigeo_id))
    return _id(cur.fetchone())


def importar_ubicaciones(cur):
    """
    Lee el CSV oficial (separado por '|') y carga en cascada departamentos, provincias,
    distritos, ubigeos y municipalidades. Retorna el número de municipalidades
    procesadas. El caller (db_bootstrap) es responsable del commit.
    """
    if not os.path.exists(RUTA_CSV_UBICACIONES):
        print(f"[UBICACIONES] CSV no encontrado en {RUTA_CSV_UBICACIONES}. Se omite la importación.")
        return 0

    procesadas = 0
    omitidas = 0
    with open(RUTA_CSV_UBICACIONES, 'r', encoding='utf-8-sig') as archivo:
        lector = csv.reader(archivo, delimiter='|')
        next(lector, None)  # Omite la cabecera
        for fila in lector:
            if len(fila) < 6:
                omitidas += 1
                continue
            ubigeo = fila[0].strip()
            dep_nombre = fila[1].strip()
            prov_nombre = fila[2].strip()
            dist_nombre = fila[3].strip()
            nombre_municipalidad = fila[4].strip()
            direccion = fila[5].strip()

            # Validación básica del ubigeo (6 dígitos numéricos)
            if len(ubigeo) != 6 or not ubigeo.isdigit():
                omitidas += 1
                continue

            dep_codigo = ubigeo[0:2]
            prov_codigo = ubigeo[0:4]
            dist_codigo = ubigeo[0:6]

            departamento_id = _upsert_departamento(cur, dep_codigo, dep_nombre)
            provincia_id = _upsert_provincia(cur, departamento_id, prov_codigo, prov_nombre)
            distrito_id = _upsert_distrito(cur, provincia_id, dist_codigo, dist_nombre)
            ubigeo_id = _upsert_ubigeo(cur, distrito_id, dist_codigo)
            _upsert_municipalidad(
                cur, dep_nombre, prov_nombre, dist_nombre,
                departamento_id, provincia_id, distrito_id, ubigeo_id,
                nombre_municipalidad, direccion
            )
            procesadas += 1

    if omitidas > 0:
        print(f"[UBICACIONES] Se omitieron {omitidas} fila(s) con formato inválido.")
    return procesadas