"""
schemas/gestion_usuarios.py
Objetivo: Modelos Pydantic del módulo de gestión de usuarios, municipalidades, grupos,
          roles temporales y política de contraseñas.
Uso: Importar en routers/usuarios.py, routers/municipalidades.py y routers/grupos.py.
Referencia: tickets COM-23 (municipalidades y usuarios), COM-26 (flujo CRUD por perfil),
            COM-27 (FK de ubicación geográfica en municipalidades).
"""
from pydantic import BaseModel
from typing import Optional, List


# ==========================================
# MUNICIPALIDADES
# ==========================================
class MunicipalidadBase(BaseModel):
    """
    Atributos de una municipalidad. COM-27: la fuente de verdad de la ubicación son los
    FK (departamento_id, provincia_id, distrito_id); los campos de texto se conservan
    por compatibilidad y se derivan automáticamente de los FK en el backend.
    """
    # Campos de texto legacy (COM-23). COM-27: ahora opcionales, el backend los deriva
    # de los FK para mantener consistencia con los datos sembrados por el CSV.
    departamento: Optional[str] = None
    provincia: Optional[str] = None
    distrito: Optional[str] = None
    nombre: str
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None
    # COM-27: FK de ubicación geográfica (fuente de verdad)
    departamento_id: Optional[int] = None
    provincia_id: Optional[int] = None
    distrito_id: Optional[int] = None


class MunicipalidadCreate(MunicipalidadBase):
    """Alta de municipalidad (privilegio GESTION_MUNICIPALIDADES)."""
    usuario_solicitante_id: int


class MunicipalidadUpdate(BaseModel):
    """Actualización parcial de municipalidad (todos los campos opcionales)."""
    departamento: Optional[str] = None
    provincia: Optional[str] = None
    distrito: Optional[str] = None
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None
    # COM-27: FK de ubicación geográfica
    departamento_id: Optional[int] = None
    provincia_id: Optional[int] = None
    distrito_id: Optional[int] = None
    usuario_solicitante_id: int


# ==========================================
# USUARIOS (flujo CRUD por perfil - COM-26 / COM-27)
# ==========================================
class UsuarioCreate(BaseModel):
    """
    COM-26: creación de usuario según el perfil del creador. COM-27: agrega la
    ubicación geográfica del usuario (departamento, provincia, distrito, municipalidad)
    para el personal que no es administrador de sistema.
    """
    tipo_documento: str = "DNI"
    documento_identidad: str
    nombres: str
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    fecha_nacimiento: Optional[str] = None
    clave_inicial: str
    perfil_objetivo: str
    grupo_id: int
    rol_id: int
    municipalidad_ids: List[int] = []
    comedor_ids: List[int] = []
    usuario_solicitante_id: int
    # COM-27: ubicación geográfica del usuario (solo personal no-admin-de-sistema)
    departamento_id: Optional[int] = None
    provincia_id: Optional[int] = None
    distrito_id: Optional[int] = None
    municipalidad_id: Optional[int] = None


class UsuarioUpdate(BaseModel):
    """COM-26/COM-27: edición de usuario (datos personales, perfil, alcance y ubicación)."""
    tipo_documento: Optional[str] = None
    documento_identidad: Optional[str] = None
    nombres: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    fecha_nacimiento: Optional[str] = None
    perfil_objetivo: Optional[str] = None
    grupo_id: Optional[int] = None
    rol_id: Optional[int] = None
    municipalidad_ids: List[int] = []
    comedor_ids: List[int] = []
    usuario_solicitante_id: int
    # COM-27: ubicación geográfica del usuario
    departamento_id: Optional[int] = None
    provincia_id: Optional[int] = None
    distrito_id: Optional[int] = None
    municipalidad_id: Optional[int] = None


class CambiarEstadoCuentaInput(BaseModel):
    """Bloqueo/desbloqueo administrativo de la cuenta (estado_activo de usuarios)."""
    estado_activo: bool
    usuario_solicitante_id: int


class DesbloqueoReintentosInput(BaseModel):
    """Reset de bloqueo por intentos fallidos (bloqueado/intentos_fallidos)."""
    usuario_solicitante_id: int


class PoliticaClaveUpdate(BaseModel):
    """Modificación de la política de contraseñas (privilegio GESTION_POLITICAS_CLAVE)."""
    longitud_min: Optional[int] = None
    longitud_max: Optional[int] = None
    meses_expiracion: Optional[int] = None
    max_intentos: Optional[int] = None
    usuario_solicitante_id: int


class RolTemporalInput(BaseModel):
    """Otorga un rol de comedor por tiempo definido a un usuario con membresía activa."""
    usuario_id: int
    comedor_id: int
    rol_id: int
    motivo: Optional[str] = None
    fecha_inicio: str
    fecha_fin: str
    usuario_solicitante_id: int


class RevocarRolTemporalInput(BaseModel):
    """Revoca anticipadamente un rol temporal (estado -> REVOCADO)."""
    usuario_solicitante_id: int


class GrupoCreate(BaseModel):
    """Creación de grupo con ámbito (privilegio GESTION_GRUPOS)."""
    nombre: str
    ambito: str                     # SISTEMA | GLOBAL | COMEDOR
    descripcion: Optional[str] = None
    usuario_solicitante_id: int


class AsignarPrivilegiosInput(BaseModel):
    """Reemplaza el conjunto de privilegios de un grupo por la lista enviada."""
    privilegio_ids: List[int]
    usuario_solicitante_id: int