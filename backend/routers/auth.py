"""
routers/auth.py
Objetivo: Endpoints de autenticación: login con bloqueo por intentos fallidos,
          detección de contraseña expirada/provisoria y cambio de contraseña con
          validación de política vigente.
Uso: Registrado en main.py con prefijo /api/v1. Expone /auth/login y /auth/cambiar-clave.

Historial:
 - COM-19: login, intentos fallidos, expiración fija a 6 meses y cambio de clave.
 - COM-23: rechazo de cuentas administrativamente inactivas (estado_activo=FALSE);
   intentos máximos y meses de expiración leídos de la política parametrizada
   (parametros_sistema, categoría SEGURIDAD) con fallback a las constantes.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from database import get_db, get_parametros_dict
from seguridad import (
    verificar_clave,
    hashear_clave,
    validar_politica_clave,
    politica_por_defecto,
    PARAM_MESES_EXPIRACION,
    PARAM_MAX_INTENTOS,
)

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Mensajes estándar del flujo de login
MSG_BLANCOS = "Debe ingresar el usuario y la contraseña. No pueden enviarse en blanco."
MSG_BLOQUEADO = "Usuario bloqueado por intentos fallidos. Comuníquese con el administrador."
MSG_CUENTA_INACTIVA = "Cuenta desactivada por el administrador. Comuníquese con las personas encargadas."
MSG_CREDENCIAL = "Usuario o contraseña incorrectos."


class LoginInput(BaseModel):
    tipo_documento: str = "DNI"
    documento_identidad: str
    clave: str


class CambioClaveInput(BaseModel):
    tipo_documento: str = "DNI"
    documento_identidad: str
    clave_actual: str
    clave_nueva: str


def _politica_vigente(db) -> dict:
    """
    COM-23: política de contraseñas desde parametros_sistema (categoría SEGURIDAD)
    combinada con los defaults de seguridad.py como respaldo.
    """
    params = get_parametros_dict(db, [PARAM_MESES_EXPIRACION, PARAM_MAX_INTENTOS])
    politica = politica_por_defecto()
    politica.update(params)
    return politica


@router.post("/login")
def login(data: LoginInput, db=Depends(get_db)):
    """
    Autentica al usuario por tipo+documento y contraseña.
    Reglas:
      - Campos en blanco -> 400.
      - COM-23: cuenta administrativamente inactiva (estado_activo=FALSE) -> 403.
      - Bloqueado por intentos -> 403.
      - Credencial errada -> 401 con intentos restantes (máximo parametrizado COM-23);
        aviso ámbar al quedar 1 intento.
      - Expiración de clave calculada con los meses parametrizados (COM-23).
    """
    if not data.documento_identidad.strip() or not data.clave.strip():
        raise HTTPException(status_code=400, detail={"mensaje": MSG_BLANCOS, "tipo": "error"})

    politica = _politica_vigente(db)
    max_intentos = int(politica[PARAM_MAX_INTENTOS])
    meses_expiracion = int(politica[PARAM_MESES_EXPIRACION])

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, nombres, apellido_paterno, apellido_materno, rol,
                   tipo_documento, documento_identidad, clave_hash,
                   intentos_fallidos, bloqueado, estado_activo, clave_provisoria,
                   (fecha_clave + MAKE_INTERVAL(months => %s)) <= CURRENT_TIMESTAMP AS clave_expirada
            FROM usuarios
            WHERE tipo_documento = %s AND documento_identidad = %s;
        """, (meses_expiracion, data.tipo_documento, data.documento_identidad.strip()))
        usuario = cur.fetchone()

        # Usuario inexistente: mismo mensaje genérico (evita enumeración de usuarios)
        if not usuario:
            raise HTTPException(status_code=401, detail={"mensaje": MSG_CREDENCIAL, "tipo": "error"})

        # COM-23: bloqueo administrativo de la cuenta (gestión de usuarios)
        if not usuario["estado_activo"]:
            raise HTTPException(status_code=403, detail={"mensaje": MSG_CUENTA_INACTIVA, "tipo": "error"})

        # Bloqueo por intentos fallidos (COM-19)
        if usuario["bloqueado"]:
            raise HTTPException(status_code=403, detail={"mensaje": MSG_BLOQUEADO, "tipo": "error"})

        # Verificación de contraseña con contador de intentos parametrizado
        if not verificar_clave(data.clave, usuario["clave_hash"]):
            intentos = usuario["intentos_fallidos"] + 1
            if intentos >= max_intentos:
                # Último intento permitido: bloqueo definitivo hasta desbloqueo manual
                cur.execute("UPDATE usuarios SET intentos_fallidos = %s, bloqueado = TRUE WHERE id = %s;",
                            (intentos, usuario["id"]))
                db.commit()
                raise HTTPException(status_code=403, detail={"mensaje": MSG_BLOQUEADO, "tipo": "error"})

            cur.execute("UPDATE usuarios SET intentos_fallidos = %s WHERE id = %s;",
                        (intentos, usuario["id"]))
            db.commit()
            restantes = max_intentos - intentos
            if restantes == 1:
                # AVISO (caja ámbar): queda 1 intento antes del bloqueo
                raise HTTPException(status_code=401, detail={
                    "mensaje": f"Advertencia: lleva {intentos} intentos fallidos. Si se equivoca una vez más, su usuario se bloqueará.",
                    "tipo": "aviso"
                })
            raise HTTPException(status_code=401, detail={
                "mensaje": f"{MSG_CREDENCIAL} Le quedan {restantes} intentos.",
                "tipo": "error"
            })

        # Credencial correcta: se reinician intentos
        cur.execute("UPDATE usuarios SET intentos_fallidos = 0 WHERE id = %s;", (usuario["id"],))
        db.commit()

        requiere_cambio = bool(usuario["clave_provisoria"] or usuario["clave_expirada"])
        return {
            "usuario": {
                "id": usuario["id"],
                "nombres": usuario["nombres"],
                "apellido_paterno": usuario["apellido_paterno"],
                "apellido_materno": usuario["apellido_materno"],
                "rol": usuario["rol"],
                "tipo_documento": usuario["tipo_documento"],
                "documento_identidad": usuario["documento_identidad"]
            },
            "requiere_cambio_clave": requiere_cambio
        }
    finally:
        cur.close()


@router.post("/cambiar-clave")
def cambiar_clave(data: CambioClaveInput, db=Depends(get_db)):
    """
    Cambia la contraseña validando la política vigente (COM-23: longitudes parametrizadas,
    letras+números, sin contener el DNI). Reinicia la vigencia y la bandera provisoria.
    """
    if not data.clave_actual.strip() or not data.clave_nueva.strip():
        raise HTTPException(status_code=400, detail={"mensaje": MSG_BLANCOS, "tipo": "error"})

    politica = _politica_vigente(db)
    errores = validar_politica_clave(data.clave_nueva, data.documento_identidad.strip(), politica)
    if errores:
        raise HTTPException(status_code=400, detail={"mensaje": " ".join(errores), "tipo": "error"})

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, clave_hash, bloqueado, estado_activo
            FROM usuarios
            WHERE tipo_documento = %s AND documento_identidad = %s;
        """, (data.tipo_documento, data.documento_identidad.strip()))
        usuario = cur.fetchone()
        if not usuario:
            raise HTTPException(status_code=404, detail={"mensaje": "Usuario no encontrado.", "tipo": "error"})
        if not usuario["estado_activo"]:
            raise HTTPException(status_code=403, detail={"mensaje": MSG_CUENTA_INACTIVA, "tipo": "error"})
        if usuario["bloqueado"]:
            raise HTTPException(status_code=403, detail={"mensaje": MSG_BLOQUEADO, "tipo": "error"})
        if not verificar_clave(data.clave_actual, usuario["clave_hash"]):
            raise HTTPException(status_code=401, detail={"mensaje": "La contraseña actual es incorrecta.", "tipo": "error"})

        cur.execute("""
            UPDATE usuarios
            SET clave_hash = %s,
                fecha_clave = CURRENT_TIMESTAMP,
                clave_provisoria = FALSE,
                intentos_fallidos = 0
            WHERE id = %s;
        """, (hashear_clave(data.clave_nueva), usuario["id"]))
        db.commit()
        return {"message": "Contraseña actualizada exitosamente."}
    finally:
        cur.close()