"""
routers/reset_clave.py
Objetivo: COM-38: reseteo/cambio de contraseña de CUALQUIER usuario por parte de una
          cuenta Administrador de Sistemas, para el caso de olvido de clave.
          Dos modos:
            - modo='random':     genera una clave temporal aleatoria que se devuelve
                                 una única vez en la respuesta para comunicarla.
            - modo='especifica': el admin define la nueva clave (validada contra la
                                 política de contraseñas del sistema).
          En ambos modos se deja clave_provisoria=TRUE (cambio obligatorio en el primer
          login, flujo COM-19) salvo forzar_cambio=False, y se desbloquea la cuenta
          (bloqueado=FALSE, intentos_fallidos=0) y actualiza fecha_clave.
Permisos: SOLO es_admin_sistema(cur, solicitante). El usuario objetivo puede tener
          cualquier perfil (Sistema, Administrativo, Directivo, Operativo).
Uso: Registrado en main.py con prefijo /api/v1 (comparte prefijo /usuarios).
Referencia: ticket COM-38 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema
from seguridad import hashear_clave

router = APIRouter(prefix="/usuarios", tags=["Reset de Clave (COM-38)"])

# Alfabetos para clave temporal legible (sin caracteres ambiguos)
_ALFABETO_MAYUS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_ALFABETO_MINUS = "abcdefghijkmnopqrstuvwxyz"
_ALFABETO_DIGIT = "23456789"
_ALFABETO_EXTRA = "@#$%&*"


# ==========================================
# MODELO DE ENTRADA
# ==========================================
class ResetClaveInput(BaseModel):
    """Payload del reseteo/cambio de clave COM-38."""
    usuario_solicitante_id: int
    modo: str = "random"                      # 'random' | 'especifica'
    clave_nueva: Optional[str] = None         # obligatoria si modo='especifica'
    forzar_cambio: bool = True                # TRUE => clave_provisoria (cambio al login)


# ==========================================
# HELPERS
# ==========================================
def _generar_clave_temporal(longitud: int = 10) -> str:
    """
    COM-38: clave temporal aleatoria que cumple la política mínima
    (mayúscula, minúscula, dígito y símbolo) y evita caracteres ambiguos.
    """
    rnd = secrets.SystemRandom()
    while True:
        partes = [
            rnd.choice(_ALFABETO_MAYUS),
            rnd.choice(_ALFABETO_MINUS),
            rnd.choice(_ALFABETO_DIGIT),
            rnd.choice(_ALFABETO_EXTRA),
        ]
        pool = _ALFABETO_MAYUS + _ALFABETO_MINUS + _ALFABETO_DIGIT + _ALFABETO_EXTRA
        partes += [rnd.choice(pool) for _ in range(longitud - len(partes))]
        rnd.shuffle(partes)
        return "".join(partes)


def _validar_politica(cur, clave: str) -> Optional[str]:
    """
    COM-38: valida la clave contra la política del sistema (parámetros si existen,
    defaults si no). Retorna None si cumple, o el mensaje de error de política.
    """
    cur.execute("""
        SELECT clave, valor FROM parametros_sistema
        WHERE clave IN ('POLITICA_CLAVE_MIN_LONGITUD', 'POLITICA_CLAVE_REQ_MAYUS',
                        'POLITICA_CLAVE_REQ_MINUS', 'POLITICA_CLAVE_REQ_DIGITO');
    """)
    p = {r['clave']: r['valor'] for r in cur.fetchall()}
    min_len = int(float(p.get('POLITICA_CLAVE_MIN_LONGITUD', 8)))
    req_may = p.get('POLITICA_CLAVE_REQ_MAYUS', 'TRUE').upper() == 'TRUE'
    req_min = p.get('POLITICA_CLAVE_REQ_MINUS', 'TRUE').upper() == 'TRUE'
    req_dig = p.get('POLITICA_CLAVE_REQ_DIGITO', 'TRUE').upper() == 'TRUE'

    if len(clave) < min_len:
        return f"La clave debe tener al menos {min_len} caracteres."
    if req_may and not any(c.isupper() for c in clave):
        return "La clave debe incluir al menos una letra mayúscula."
    if req_min and not any(c.islower() for c in clave):
        return "La clave debe incluir al menos una letra minúscula."
    if req_dig and not any(c.isdigit() for c in clave):
        return "La clave debe incluir al menos un dígito."
    return None


# ==========================================
# ENDPOINT DE RESETEO / CAMBIO
# ==========================================
@router.post("/{usuario_id}/reset-clave")
def resetear_clave(usuario_id: int, data: ResetClaveInput, db=Depends(get_db)):
    """
    COM-38: resetea o cambia la clave de cualquier usuario, ejecutado por un
    Administrador de Sistemas. Devuelve la clave temporal SOLO en modo random.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # 1) Permiso: solo Admin de Sistemas
        if not data.usuario_solicitante_id or not es_admin_sistema(cur, data.usuario_solicitante_id):
            raise HTTPException(
                status_code=403,
                detail="Sin permiso: el reseteo de claves es exclusivo del Administrador de Sistemas.")

        # 2) Existencia del usuario objetivo
        cur.execute("""
            SELECT id, nombres, apellido_paterno, documento_identidad, rol
            FROM usuarios WHERE id = %s;
        """, (usuario_id,))
        objetivo = cur.fetchone()
        if not objetivo:
            raise HTTPException(status_code=404, detail="El usuario objetivo no existe.")

        # 3) Resolución de la nueva clave según modo
        modo = (data.modo or 'random').strip().lower()
        clave_temporal = None
        if modo == 'random':
            clave_final = _generar_clave_temporal()
            clave_temporal = clave_final
        elif modo == 'especifica':
            if not data.clave_nueva:
                raise HTTPException(status_code=400,
                                detail="En modo 'especifica' debe enviar clave_nueva.")
            error_politica = _validar_politica(cur, data.clave_nueva)
            if error_politica:
                raise HTTPException(status_code=400, detail=error_politica)
            clave_final = data.clave_nueva
        else:
            raise HTTPException(status_code=400,
                            detail="modo inválido: use 'random' o 'especifica'.")

        # 4) Aplicación: hash nuevo, provisoria según forzar_cambio, desbloqueo y fecha
        cur.execute("""
            UPDATE usuarios
            SET clave_hash = %s,
                clave_provisoria = %s,
                fecha_clave = CURRENT_TIMESTAMP - INTERVAL '5 hours',
                intentos_fallidos = 0,
                bloqueado = FALSE
            WHERE id = %s;
        """, (hashear_clave(clave_final), bool(data.forzar_cambio), usuario_id))
        if cur.rowcount != 1:
            raise HTTPException(status_code=500, detail="No se pudo actualizar la clave.")

        db.commit()
        print(f"[COM-38] Admin {data.usuario_solicitante_id} reseteó la clave del usuario "
              f"{usuario_id} ({objetivo['nombres']} {objetivo['apellido_paterno']}) "
              f"modo={modo} forzar_cambio={data.forzar_cambio}.")

        return {
            'mensaje': "Clave restablecida correctamente. Comuníquela por un canal seguro.",
            'usuario_id': usuario_id,
            'documento': objetivo['documento_identidad'],
            'modo': modo,
            'clave_temporal': clave_temporal,          # solo en modo random; null en específica
            'debe_cambiar_al_login': bool(data.forzar_cambio),
            'cuenta_desbloqueada': True,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al resetear la clave: {e}")
    finally:
        cur.close()