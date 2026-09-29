"""
routers/ubicaciones.py
Objetivo: Endpoints de consulta de la ubicación geográfica (COM-27) para alimentar los
          selectores en cascada del frontend: departamentos, provincias, distritos y
          municipalidades. Cada nivel se filtra por el identificador del nivel superior.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos: Son endpoints de solo lectura para datos de catálogo público; no requieren
          privilegios especiales (el catálogo geográfico es información de referencia).
Referencia: ticket COM-27 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db
from typing import List
from schemas.ubicacion import (
    DepartamentoOut,
    ProvinciaOut,
    DistritoOut,
    MunicipalidadUbicacionOut,
)

router = APIRouter(prefix="/ubicaciones", tags=["Ubicaciones"])


# ==========================================
# NIVEL 1: DEPARTAMENTOS
# ==========================================
@router.get("/departamentos", response_model=List[DepartamentoOut])
def listar_departamentos(db=Depends(get_db)):
    """Lista todos los departamentos ordenados por nombre (nivel 1 de la cascada)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, codigo, nombre
            FROM departamentos
            ORDER BY nombre;
        """)
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# NIVEL 2: PROVINCIAS (por departamento)
# ==========================================
@router.get("/provincias", response_model=List[ProvinciaOut])
def listar_provincias(departamento_id: int, db=Depends(get_db)):
    """Lista las provincias de un departamento (nivel 2 de la cascada)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Validar que el departamento exista antes de consultar sus provincias
        cur.execute("SELECT 1 FROM departamentos WHERE id = %s;", (departamento_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Departamento no encontrado.")
        cur.execute("""
            SELECT id, departamento_id, codigo, nombre
            FROM provincias
            WHERE departamento_id = %s
            ORDER BY nombre;
        """, (departamento_id,))
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# NIVEL 3: DISTRITOS (por provincia)
# ==========================================
@router.get("/distritos", response_model=List[DistritoOut])
def listar_distritos(provincia_id: int, db=Depends(get_db)):
    """Lista los distritos de una provincia (nivel 3 de la cascada)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Validar que la provincia exista antes de consultar sus distritos
        cur.execute("SELECT 1 FROM provincias WHERE id = %s;", (provincia_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Provincia no encontrada.")
        cur.execute("""
            SELECT id, provincia_id, codigo, nombre
            FROM distritos
            WHERE provincia_id = %s
            ORDER BY nombre;
        """, (provincia_id,))
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# NIVEL 4: MUNICIPALIDADES (por distrito)
# ==========================================
@router.get("/municipalidades", response_model=List[MunicipalidadUbicacionOut])
def listar_municipalidades_por_distrito(distrito_id: int, db=Depends(get_db)):
    """Lista las municipalidades de un distrito (nivel 4 de la cascada)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Validar que el distrito exista antes de consultar sus municipalidades
        cur.execute("SELECT 1 FROM distritos WHERE id = %s;", (distrito_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Distrito no encontrado.")
        cur.execute("""
            SELECT id, distrito_id, nombre, direccion
            FROM municipalidades
            WHERE distrito_id = %s
            ORDER BY nombre;
        """, (distrito_id,))
        return cur.fetchall()
    finally:
        cur.close()