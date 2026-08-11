"""
schemas/presupuesto.py
Objetivo: Definir los modelos de validación (Pydantic) para Presupuesto y Planificación.
Uso: Importar en los routers para validar payloads de entrada y estructurar respuestas.
"""
from pydantic import BaseModel
from typing import Optional, List

class PresupuestoInput(BaseModel):
    fondo: float
    dias: int
    comensales: int

class PrediccionDia(BaseModel):
    """Predicción de comensales por tipo para un día específico"""
    social: int
    afiliado: int
    normal: int

class PlanificacionInput(BaseModel):
    presupuesto: float
    dias_operativos: int
    prediccion_comensales: List[PrediccionDia]
    fecha_referencia: Optional[str] = None

class PlanificacionDia(BaseModel):
    dia: int
    dia_nombre: str
    comensales_social: int
    comensales_afiliado: int
    comensales_normal: int
    total_comensales: int
    receta_id: int
    nombre_receta: str
    costo_racion: float
    costo_total: float
    recoleccion_proyectada: float

class PlanificacionResponse(BaseModel):
    viable: bool
    presupuesto: float
    costo_total_semana: float
    recoleccion_total_proyectada: float
    margen: float
    dias: List[PlanificacionDia]

class GuardarPlanificacionInput(BaseModel):
    """Modelo para guardar la planificación en la base de datos"""
    presupuesto: float
    dias_operativos: int
    fecha_referencia: str
    costo_total_semana: float
    recoleccion_total_proyectada: float
    margen: float
    viable: bool
    dias: List[PlanificacionDia]

class GuardarPlanificacionResponse(BaseModel):
    id: int
    message: str