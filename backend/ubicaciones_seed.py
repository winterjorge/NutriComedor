"""
ubicaciones_seed.py
Objetivo: Importar el catálogo oficial de ubicación geográfica del Perú (departamentos,
          provincias, distritos y ubigeos) y el registro de municipalidades con su nombre
          oficial y dirección, a partir del archivo CSV `municipalidades_completo.csv`.
Uso: Importado por db_bootstrap.py, que ejecuta `importar_ubicaciones(cur)` SOLO cuando
     la tabla `departamentos` está vacía (carga inicial idempotente). El caller es
     responsable de la transacción y el commit.
Formato esperado del CSV (separador `|`, sin cabecera, 6 columnas):
    ubigeo(6)|departamento|provincia|distrito|nombre_municipalidad|direccion
    Ejemplo: 110210|ICA|CHINCHA|SUNAMPE|MUNICIPALIDAD DISTRITAL DE SUNAMPE|Plaza de Armas N° 100
Descomposición del ubigeo:
    - 2 primeros dígitos -> código de departamento
    - 4 primeros dígitos -> código de provincia
    - 6 dígitos completos -> código de distrito / ubigeo
Nota: El upsert en `municipalidades` conserva las columnas de texto libres legacy
      (departamento, provincia, distrito) junto con los nuevos FK (COM-27).
Referencia: ticket COM-27 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
import csv
import os

# Ruta absoluta del CSV dentro del backend: backend/data/municipalidades_completo.csv
RUTA_CSV_UBICACIONES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'data', 'municipalidades_completo.csv'
)


def _upsert_departamento(cur, codigo, nombre):
    """Inserta o actualiza un departamento por su código (2 dígitos) y retorna su id."""
    cur.execute("""
        INSERT INTO departamentos (codigo, nombre)
        VALUES (%s, %s)
        ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING id;
    """, (codigo, nombre))
    return cur.fetchone()[0]


def _upsert_provincia(cur, departamento_id, codigo, nombre):
    """Inserta o actualiza una provincia por su código (4 dígitos) y retorna su id."""
    cur.execute("""
        INSERT INTO provincias (departamento_id, codigo, nombre)
        VALUES (%s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE
            SET nombre = EXCLUDED.nombre,
                departamento_id = EXCLUDED.departamento_id
        RETURNING id;
    """, (departamento_id, codigo, nombre))
    return cur.fetchone()[0]


def _upsert_distrito(cur, provincia_id, codigo, nombre):
    """Inserta o actualiza un distrito por su código (6 dígitos) y retorna su id."""
    cur.execute("""
        INSERT INTO distritos (provincia_id, codigo, nombre)
        VALUES (%s, %s, %s)
        ON CONFLICT (codigo) DO UPDATE
            SET nombre = EXCLUDED.nombre,
                provincia_id = EXCLUDED.provincia_id
        RETURNING id;
    """, (provincia_id, codigo, nombre))
    return cur.fetchone()[0]


def _upsert_ubigeo(cur, distrito_id, codigo):
    """Inserta o actualiza un ubigeo por su código completo y retorna su id."""
    cur.execute("""
        INSERT INTO ubigeos (distrito_id, codigo)
        VALUES (%s, %s)
        ON CONFLICT (codigo) DO UPDATE SET distrito_id = EXCLUDED.distrito_id
        RETURNING id;
    """, (distrito_id, codigo))
    return cur.fetchone()[0]


def _upsert_municipalidad(cur, dep_nombre, prov_nombre, dist_nombre,
                          departamento_id, provincia_id, distrito_id, ubigeo_id,
                          nombre, direccion):
    """
    Inserta o actualiza una municipalidad por su distrito (cada distrito tiene una
    única municipalidad oficial). COM-27: se conservan las columnas de texto libres
    legacy (departamento, provincia, distrito) junto con los nuevos FK *_id.
    """
    cur.execute("""
        INSERT INTO municipalidades
            (departamento, provincia, distrito, nombre, direccion,
             departamento_id, provincia_id, distrito_id, ubigeo_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (distrito_id) DO UPDATE
            SET nombre = EXCLUDED.nombre,
                direccion = EXCLUDED.direccion,
                departamento = EXCLUDED.departamento,
                provincia = EXCLUDED.provincia,
                distrito = EXCLUDED.distrito,
                departamento_id = EXCLUDED.departamento_id,
                provincia_id = EXCLUDED.provincia_id,
                ubigeo_id = EXCLUDED.ubigeo_id
        RETURNING id;
    """, (dep_nombre, prov_nombre, dist_nombre, nombre, direccion,
          departamento_id, provincia_id, distrito_id, ubigeo_id))
    return cur.fetchone()[0]


def importar_ubicaciones(cur):
    """
    Lee el CSV de municipalidades y carga en orden: departamentos, provincias, distritos,
    ubigeos y municipalidades. Retorna el número de municipalidades procesadas.
    Asume que las tablas ya existen (creadas por aplicar_esquema_ubicaciones) y que
    el caller maneja la transacción (commit/rollback).
    Si el CSV no existe, retorna 0 sin lanzar excepción.
    """
    if not os.path.exists(RUTA_CSV_UBICACIONES):
        print(f"[UBICACIONES] CSV no encontrado en {RUTA_CSV_UBICACIONES}. Se omite la importación.")
        return 0

    procesadas = 0
    omitidas = 0
    with open(RUTA_CSV_UBICACIONES, 'r', encoding='utf-8-sig') as archivo:
        lector = csv.reader(archivo, delimiter='|')
        for fila in lector:
            # Cada fila debe tener exactamente 6 columnas
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

            # Descomposición del ubigeo en sus tres niveles
            dep_codigo = ubigeo[0:2]
            prov_codigo = ubigeo[0:4]
            dist_codigo = ubigeo  # los 6 dígitos completos

            # Upsert en cascada (jerarquía geográfica)
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