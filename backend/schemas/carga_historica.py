"""
schemas/carga_historica.py
Objetivo: COM-63: modelos de validación para la carga masiva de atenciones históricas.
Referencia: ticket COM-63.
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class FilaCargaHistorica(BaseModel):
    """Una fila del CSV: fecha + 4 tipos de comensal."""
    fecha: date
    afiliados: int = 0
    publico: int = 0  # mapeado a 'Normal'
    sociales: int = 0  # mapeado a 'Social'
    cocineras: int = 0  # nuevo tipo


class ResumenCargaMasiva(BaseModel):
    """Respuesta del endpoint de carga masiva."""
    filas_procesadas: int
    filas_omitidas: int
    ventas_creadas: int
    detalle_omitidas: List[dict]
    rango_fechas: Optional[dict]