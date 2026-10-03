"""
schemas/comedor.py
Objetivo: Definir los modelos de validación (Pydantic) para Comedores y la asociación
          usuario-comedor con estado activo/inactivo por comedor (ticket COM-21).
Historial:
 - COM-21: versión original con campos de texto obligatorios (departamento/ciudad/distrito).
 - COM-27 (UI): el frontend captura la ubicación mediante cascada y envía IDs, pero el
   schema no se actualizó => bug COM-44 (422 al crear comedor).
 - COM-44 (este archivo): alineación con COM-27. `ComedorCreate` y `ComedorUpdate`
   reciben los FK geográficos como OBLIGATORIOS (departamento_id, provincia_id,
   distrito_id). Los textos `departamento/ciudad/distrito` se vuelven opcionales
   (se calculan en el router desde las tablas geográficas y se guardan como cache
   para no romper el listado ni los filtros).
Uso: Importar en routers/comedores.py para validar payloads y estructurar respuestas.
Referencia: tickets COM-21 / COM-27 / COM-44 (solo trazabilidad).
"""
from pydantic import BaseModel
from typing import Optional

# Roles permitidos DENTRO de un comedor (el rol global de sistema vive en usuarios.rol)
ROLES_COMEDOR = ("Administrador", "Operador")


# COM-44 (trazabilidad): ComedorBase original COMENTADA (textos obligatorios, sin FK).
# class ComedorBase(BaseModel):
#     """Atributos obligatorios/descriptivos de un comedor (COM-21)."""
#     departamento: str
#     ciudad: str
#     distrito: str
#     zona: Optional[str] = None
#     nombre: str
#     direccion: Optional[str] = None
#     link_ubicacion: Optional[str] = None
#     fecha_fundacion: Optional[str] = None


class ComedorBase(BaseModel):
    """
    COM-44: atributos de un comedor alineados a la cascada geográfica COM-27.
    Los FK son obligatorios; los textos (cache de nombres) son opcionales porque
    el router los resuelve desde las tablas `departamentos`/`provincias`/`distritos`.
    """
    nombre: str
    # COM-44: FK de la cascada (fuente de verdad de la ubicación)
    departamento_id: int
    provincia_id: int
    distrito_id: int
    # Opcionales descriptivos
    zona: Optional[str] = None
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None       # URL de mapa (Google Maps / GeoURI)
    fecha_fundacion: Optional[str] = None      # ISO YYYY-MM-DD


class ComedorCreate(ComedorBase):
    """Alta de comedor. Solo lo ejecuta el Administrador del Sistema."""
    usuario_solicitante_id: int


class ComedorUpdate(BaseModel):
    """Actualización parcial de comedor (todos los campos opcionales)."""
    nombre: Optional[str] = None
    # COM-44: FK opcionales; si cambian, el router resuelve los textos de nuevo.
    departamento_id: Optional[int] = None
    provincia_id: Optional[int] = None
    distrito_id: Optional[int] = None
    zona: Optional[str] = None
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None
    fecha_fundacion: Optional[str] = None
    usuario_solicitante_id: int


class ComedorResponse(BaseModel):
    id: int
    nombre: str
    departamento: Optional[str] = None
    ciudad: Optional[str] = None
    distrito: Optional[str] = None
    # COM-44: nombres resueltos desde la cascada (para el listado del frontend)
    departamento_nombre: Optional[str] = None
    provincia_nombre: Optional[str] = None
    distrito_nombre: Optional[str] = None
    zona: Optional[str] = None
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None
    fecha_fundacion: Optional[str] = None

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