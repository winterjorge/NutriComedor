"""
schemas/ubicacion.py
Objetivo: Modelos Pydantic del módulo de ubicación geográfica (COM-27): departamentos,
          provincias, distritos y municipalidades. Sirven como contrato de respuesta de
          los endpoints de consulta en cascada que alimentan los selectores del frontend.
Uso: Importar en routers/ubicaciones.py.
Nota: Son modelos de solo lectura (Out). La escritura/creación de estas entidades no
      forma parte del alcance de COM-27 (el catálogo se carga desde el CSV oficial).
Referencia: ticket COM-27 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from pydantic import BaseModel
from typing import Optional


class DepartamentoOut(BaseModel):
    """Departamento geográfico (nivel 1 de la cascada)."""
    id: int
    codigo: str
    nombre: str

    class Config:
        from_attributes = True


class ProvinciaOut(BaseModel):
    """Provincia geográfica (nivel 2 de la cascada), pertenece a un departamento."""
    id: int
    departamento_id: int
    codigo: str
    nombre: str

    class Config:
        from_attributes = True


class DistritoOut(BaseModel):
    """Distrito geográfico (nivel 3 de la cascada), pertenece a una provincia."""
    id: int
    provincia_id: int
    codigo: str
    nombre: str

    class Config:
        from_attributes = True


class MunicipalidadUbicacionOut(BaseModel):
    """
    Municipalidad (nivel 4 de la cascada), pertenece a un distrito.
    Expone el nombre oficial y la dirección cargados desde el CSV.
    """
    id: int
    distrito_id: Optional[int] = None
    nombre: str
    direccion: Optional[str] = None

    class Config:
        from_attributes = True