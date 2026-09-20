"""
schemas/gestion_usuarios.py
Objetivo: Modelos Pydantic del módulo de gestión de usuarios: creación y edición de
          usuarios según perfil del creador (corrección COM-26), bloqueo/desbloqueo,
          política de contraseñas, roles temporales y gestión de grupos/privilegios.
Uso: Importar en routers/usuarios.py y routers/grupos.py.
Referencia: tickets COM-23/COM-26 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from pydantic import BaseModel
from typing import Optional, List


# ==========================================
# MUNICIPALIDADES
# ==========================================
class MunicipalidadBase(BaseModel):
    """Atributos obligatorios/descriptivos de una municipalidad."""
    departamento: str
    provincia: str
    distrito: str
    nombre: str
    direccion: Optional[str] = None
    link_ubicacion: Optional[str] = None


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
    usuario_solicitante_id: int


# ==========================================
# USUARIOS: FLUJO CRUD POR PERFIL (COM-26)
# ==========================================
class UsuarioCreate(BaseModel):
    """
    COM-26: creación de usuario según el perfil del creador.
      - perfil_objetivo: ADMINISTRADOR_SISTEMA | ADMINISTRATIVO | DIRECTIVO | OPERATIVO.
      - grupo_id/rol_id: deben corresponder al grupo del perfil objetivo.
      - municipalidad_ids: obligatorio cuando el perfil objetivo es ADMINISTRATIVO
        (solo municipalidades del alcance del solicitante).
      - comedor_ids: obligatorio cuando el perfil objetivo es DIRECTIVO u OPERATIVO
        (solo comedores del alcance del solicitante; cargos no repetibles se validan).
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


class UsuarioUpdate(BaseModel):
    """
    COM-26: edición de usuario (datos personales + reemplazo de las membresías del
    grupo del perfil objetivo). Las membresías de otros grupos no se alteran.
    """
    tipo_documento: Optional[str] = None
    documento_identidad: Optional[str] = None
    nombres: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    fecha_nacimiento: Optional[str] = None
    perfil_objetivo: str
    grupo_id: int
    rol_id: int
    municipalidad_ids: List[int] = []
    comedor_ids: List[int] = []
    usuario_solicitante_id: int


class CambiarEstadoCuentaInput(BaseModel):
    """Bloqueo/desbloqueo administrativo de la cuenta (estado_activo de usuarios)."""
    estado_activo: bool
    usuario_solicitante_id: int


class DesbloqueoReintentosInput(BaseModel):
    """Reset de bloqueo por intentos fallidos (bloqueado/intentos_fallidos)."""
    usuario_solicitante_id: int


# ==========================================
# POLÍTICA DE CONTRASEÑAS (editable)
# ==========================================
class PoliticaClaveUpdate(BaseModel):
    """Modificación de la política de contraseñas (privilegio GESTION_POLITICAS_CLAVE)."""
    longitud_min: Optional[int] = None
    longitud_max: Optional[int] = None
    meses_expiracion: Optional[int] = None
    max_intentos: Optional[int] = None
    usuario_solicitante_id: int


# ==========================================
# ROLES TEMPORALES (vigencia definida)
# ==========================================
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


# ==========================================
# GRUPOS Y PRIVILEGIOS
# ==========================================
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