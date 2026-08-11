"""
schemas/comensal.py
Objetivo: Definir los modelos de validación (Pydantic) para Comensales y Padrón (POS).
Uso: Importar en los routers para validar payloads de entrada y estructurar respuestas.
"""
from pydantic import BaseModel
from typing import Optional

class NuevoComensalInput(BaseModel):
    tipo_documento: str
    documento_identidad: str
    nombres: str
    tipo_comensal: str

class RegistroVentaInput(BaseModel):
    comensal_id: int
    raciones: int
    monto_pagado: float
    tipo_menu: str = "Almuerzo regular"
    tipo_comensal_venta: str
    observacion: Optional[str] = None

class ModificarVentaInput(BaseModel):
    comensal_id: Optional[int] = None  # <-- NUEVO: Campo opcional para cambiar de comensal
    raciones: int
    monto_pagado: float
    tipo_menu: str
    tipo_comensal_venta: str
    observacion: Optional[str] = None
    motivo_modificacion: str