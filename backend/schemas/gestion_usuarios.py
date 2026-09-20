"""
schemas/gestion_usuarios.py
Objetivo: Modelos Pydantic del módulo de gestión de usuarios y entidades administrativas:
          municipalidades, creación/bloqueo de usuarios, política de contraseñas editable,
          roles temporales con vigencia y gestión de grupos con privilegios.
Uso: Importar en routers/municipalidades.py, routers/usuarios.py y routers/grupos.py
     para validar payloads de entrada y estructurar respuestas.
Nota: Los nombres de objetos describen funcionalidad (precepto de nomenclatura);
      el ticket COM-23 solo se referencia como trazabilidad en este docstring.
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
    link_ubicacion: Optional[str] = None   # URL de mapa (Google Maps / GeoURI)


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
# USUARIOS (creación y bloqueo)
# ==========================================
class UsuarioCreate(BaseModel):
    """
    Alta de usuario del sistema (privilegio GESTION_USUARIOS).
    La clave_inicial debe cumplir la política vigente y se marca como provisoria
    para forzar su cambio en el primer login.
    """
    tipo_documento: str = "DNI"
    documento_identidad: str
    nombres: str
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    fecha_nacimiento: Optional[str] = None
    clave_inicial: str
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
    """
    Modificación de la política de contraseñas (privilegio GESTION_POLITICAS_CLAVE).
    Campos opcionales: solo se actualizan los enviados.
    """
    longitud_min: Optional[int] = None
    longitud_max: Optional[int] = None
    meses_expiracion: Optional[int] = None
    max_intentos: Optional[int] = None
    usuario_solicitante_id: int


# ==========================================
# ROLES TEMPORALES (vigencia definida)
# ==========================================
class RolTemporalInput(BaseModel):
    """
    Otorga un rol de comedor por tiempo definido (ej. el tesorero asume al presidente).
    fecha_inicio/fecha_fin en formato ISO (YYYY-MM-DD o timestamp).
    """
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
    """
    Reemplaza el conjunto de privilegios de un grupo (privilegio GESTION_GRUPOS).
    Recibe la lista completa de ids de privilegios que el grupo debe poseer.
    """
    privilegio_ids: List[int]
    usuario_solicitante_id: int