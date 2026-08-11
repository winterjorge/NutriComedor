from pydantic import BaseModel
from typing import Optional, List

class RecetaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    raciones: Optional[int] = None  # NUEVO: Número de raciones
    hierro_mg: Optional[float] = None
    proteina_g: Optional[float] = None
    energia_kcal: Optional[float] = None
    vitamina_a_ug: Optional[float] = None
    zinc_mg: Optional[float] = None
    carbohidratos_g: Optional[float] = None

class RecetaCreate(RecetaBase):
    pass

class RecetaUpdate(BaseModel):
    """Todos los campos opcionales para actualización parcial"""
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    raciones: Optional[int] = None  # NUEVO
    hierro_mg: Optional[float] = None
    proteina_g: Optional[float] = None
    energia_kcal: Optional[float] = None
    vitamina_a_ug: Optional[float] = None
    zinc_mg: Optional[float] = None
    carbohidratos_g: Optional[float] = None

class RecetaInput(RecetaBase):
    """Alias de RecetaCreate para compatibilidad con el router"""
    pass

class RecetaResponse(RecetaBase):
    id: int
    
    class Config:
        from_attributes = True

class RecetaListResponse(BaseModel):
    recetas: List[RecetaResponse]
    total: int
    page: int
    per_page: int
    total_pages: int

class IngredienteRecetaInput(BaseModel):
    ingrediente_id: int
    cantidad_requerida: float
    unidad_medida_id: int