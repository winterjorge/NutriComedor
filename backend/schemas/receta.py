"""
schemas/receta.py
Objetivo: Modelos Pydantic del módulo de recetas (CRUD, ingredientes y listado).
Historial:
 - Sprint 1: versión original (nombre, descripción y nutrientes).
 - COM-45 (este archivo): el campo `raciones` deja de ser Optional sin uso:
     * RecetaBase/RecetaInput/RecetaResponse: `raciones: int` OBLIGATORIO con default 4
       y validación de entero mayor a cero (gt=0) y cota superior de seguridad (le=10000).
     * RecetaUpdate: `raciones: Optional[int]` con la misma validación cuando se envía
       (None = no modificar, para actualizaciones parciales).
   Las líneas anteriores (`raciones: Optional[int] = None`) quedan COMENTADAS por
   trazabilidad. Es el dato que permite nutrición y costo POR RACIÓN (COM-47 v2).
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class RecetaBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    # COM-45 (trazabilidad): línea anterior comentada (Optional sin validación ni uso):
    # raciones: Optional[int] = None  # NUEVO: Número de raciones
    # COM-45: raciones obligatorias con default 4; entero mayor a cero validado aquí y
    # reforzado por el CHECK chk_recetas_raciones_positivas de la base de datos.
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
    # COM-45 (trazabilidad): línea anterior comentada:
    # raciones: Optional[int] = None  # NUEVO
    # COM-45: si se envía, debe ser entero mayor a cero; None = no modificar.
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
    ingrediente_id: int
    cantidad_requerida: float
    unidad_medida_id: int