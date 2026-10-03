"""
schemas/receta.py
Objetivo: Modelos Pydantic del módulo de recetas (CRUD, ingredientes y listado).
Historial:
 - Sprint 1: versión original (nombre, descripción y nutrientes).
 - COM-45: `raciones` obligatorio con default 4 y validación gt=0 en creación;
   opcional validado en edición parcial.
 - COM-48 (este archivo): el payload de ingrediente de receta (`IngredienteRecetaInput`)
   exige `componente_id` (FK a recetas_componentes: Ensalada, Plato de fondo, Refresco,
   Fruta...), habilitando el mismo ingrediente en varios componentes con cantidades
   independientes. La nutrición (6 campos) sigue POR RACIÓN en RecetaBase.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class RecetaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    # COM-45: raciones obligatorias con default 4; entero mayor a cero.
    raciones: int = Field(4, gt=0, le=10000,
                          description="Número de raciones que produce la receta")
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
    # COM-45: si se envía, entero mayor a cero; None = no modificar.
    raciones: Optional[int] = Field(None, gt=0, le=10000,
                                    description="Número de raciones que produce la receta")
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
    """
    COM-48: línea de ingrediente de una receta, ahora vinculada a un componente
    (Ensalada / Plato de fondo / Refresco / Fruta / futuros). El mismo ingrediente
    puede enviarse varias veces con componente_id distinto y cantidades independientes.
    """
    ingrediente_id: int
    cantidad_requerida: float
    unidad_medida_id: int
    componente_id: int = Field(..., gt=0, description="Componente de la receta (recetas_componentes.id)")