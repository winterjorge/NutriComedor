"""
schemas/grupo.py
Objetivo: Modelos Pydantic del ticket COM-22 (grupos de usuario, roles y membresías
          con alcance global o por comedor).
Uso: Importar en routers/grupos.py para validar payloads de asignación y cambio de estado.
"""
from pydantic import BaseModel
from typing import Optional


class AsignarGrupoInput(BaseModel):
    """Asigna un usuario a un grupo con rol y alcance (COM-22)."""
    usuario_id: int
    grupo_id: int
    rol_id: int
    # NULL = alcance global (grupos SISTEMA/GLOBAL); obligatorio en grupos COMEDOR
    comedor_id: Optional[int] = None
    usuario_solicitante_id: int


class CambiarEstadoMembresiaInput(BaseModel):
    """Activa/desactiva una membresía usuario-grupo dejando auditoría (COM-22)."""
    estado_activo: bool
    usuario_solicitante_id: int