"""
schemas/comedor.py
Objetivo: Definir los modelos de validación (Pydantic) para Comedores y la asociación
          usuario-comedor con estado activo/inactivo por comedor (ticket COM-21).
Uso: Importar en routers/comedores.py para validar payloads y estructurar respuestas.
"""
from pydantic import BaseModel
from typing import Optional

# Roles permitidos DENTRO de un comedor (el rol global de sistema vive en usuarios.rol)
ROLES_COMEDOR = ("Administrador", "Operador")


class ComedorBase(BaseModel):
    """Atributos obligatorios/descriptivos de un comedor (COM-21)."""
    departamento: str
    ciudad: str
    distrito: str
    zona: Optional[str] = None
    nombre: str
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None       # URL de mapa (Google Maps / GeoURI)
    fecha_fundacion: Optional[str] = None      # ISO YYYY-MM-DD


class ComedorCreate(ComedorBase):
    """Alta de comedor. Solo lo ejecuta el Administrador del Sistema."""
    usuario_solicitante_id: int


class ComedorUpdate(BaseModel):
    """Actualización parcial de comedor (todos los campos opcionales)."""
    departamento: Optional[str] = None
    ciudad: Optional[str] = None
    distrito: Optional[str] = None
    zona: Optional[str] = None
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None
    fecha_fundacion: Optional[str] = None
    usuario_solicitante_id: int


class ComedorResponse(ComedorBase):
    id: int

    class Config:
        from_attributes = True


class AsociarUsuarioInput(BaseModel):
    """Asocia un usuario existente a un comedor con un rol inicial."""
    usuario_id: int
    rol: str = "Operador"
    usuario_solicitante_id: int


class CambiarEstadoUsuarioComedorInput(BaseModel):
    """Activa/desactiva a un usuario dentro de un comedor específico (COM-21)."""
    estado_activo: bool
    usuario_solicitante_id: int


class UsuarioComedorResponse(BaseModel):
    """Vista de un usuario dentro de un comedor, con su estado y rol."""
    id: int
    usuario_id: int
    nombres: str
    apellido_paterno: Optional[str] = None
    tipo_documento: str
    documento_identidad: str
    rol: str
    estado_activo: bool