"""
routers/auth.py
Objetivo: Endpoints de autenticación (COM-19): login con bloqueo por intentos fallidos,
          detección de contraseña expirada/provisoria y cambio de contraseña con
          validación de política.
Uso: Registrado en main.py con prefijo /api/v1. Expone /auth/login y /auth/cambiar-clave.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from database import get_db
from seguridad import verificar_clave, hashear_clave, validar_politica_clave, MAX_INTENTOS_FALLIDOS

router = APIRouter(prefix="/auth", tags=["Autenticación"])

# Mensajes estándar del flujo de login (COM-19)
MSG_BLANCOS = "Debe ingresar el usuario y la contraseña. No pueden enviarse en blanco."
MSG_BLOQUEADO = "Usuario bloqueado por 3 intentos fallidos. Comuníquese con el administrador."
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


@router.post("/login")
def login(data: LoginInput, db=Depends(get_db)):
    """
    Autentica al usuario por tipo+documento y contraseña.
    Reglas COM-19: campos en blanco -> 400; credencial errada -> 401 con intentos
    restantes; al quedar 1 intento -> aviso ámbar de bloqueo inminente; 3er fallo ->
    bloqueo (403).
    """
    # 1) Validación de campos en blanco (requisito de negocio)
    if not data.documento_identidad.strip() or not data.clave.strip():
        raise HTTPException(status_code=400, detail={"mensaje": MSG_BLANCOS, "tipo": "error"})

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, nombres, apellido_paterno, apellido_materno, rol,
                   tipo_documento, documento_identidad, clave_hash,
                   intentos_fallidos, bloqueado, clave_provisoria,
                   (fecha_clave + INTERVAL '6 months') <= CURRENT_TIMESTAMP AS clave_expirada
            FROM usuarios
            WHERE tipo_documento = %s AND documento_identidad = %s;
        """, (data.tipo_documento, data.documento_identidad.strip()))
        usuario = cur.fetchone()

        # Usuario inexistente: mismo mensaje genérico (evita enumeración de usuarios)
        if not usuario:
            raise HTTPException(status_code=401, detail={"mensaje": MSG_CREDENCIAL, "tipo": "error"})

        # Usuario previamente bloqueado
        if usuario['bloqueado']:
            raise HTTPException(status_code=403, detail={"mensaje": MSG_BLOQUEADO, "tipo": "error"})

        # 2) Verificación de contraseña
        if not verificar_clave(data.clave, usuario['clave_hash']):
            intentos = usuario['intentos_fallidos'] + 1
            if intentos >= MAX_INTENTOS_FALLIDOS:
                # 3er intento fallido: bloqueo definitivo hasta desbloqueo manual
                cur.execute("UPDATE usuarios SET intentos_fallidos = %s, bloqueado = TRUE WHERE id = %s;",
                            (intentos, usuario['id']))
                db.commit()
                raise HTTPException(status_code=403, detail={"mensaje": MSG_BLOQUEADO, "tipo": "error"})

            cur.execute("UPDATE usuarios SET intentos_fallidos = %s WHERE id = %s;",
                        (intentos, usuario['id']))
            db.commit()
            restantes = MAX_INTENTOS_FALLIDOS - intentos
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

        # 3) Credencial correcta: se reinician intentos
        cur.execute("UPDATE usuarios SET intentos_fallidos = 0 WHERE id = %s;", (usuario['id'],))
        db.commit()

        requiere_cambio = bool(usuario['clave_provisoria'] or usuario['clave_expirada'])
        return {
            "usuario": {
                "id": usuario['id'],
                "nombres": usuario['nombres'],
                "apellido_paterno": usuario['apellido_paterno'],
                "apellido_materno": usuario['apellido_materno'],
                "rol": usuario['rol'],
                "tipo_documento": usuario['tipo_documento'],
                "documento_identidad": usuario['documento_identidad']
            },
            "requiere_cambio_clave": requiere_cambio
        }
    finally:
        cur.close()


@router.post("/cambiar-clave")
def cambiar_clave(data: CambioClaveInput, db=Depends(get_db)):
    """
    Cambia la contraseña validando la política COM-19 (8-12, letras+números, sin DNI).
    Reinicia la vigencia (6 meses) y la bandera de clave provisoria.
    """
    if not data.clave_actual.strip() or not data.clave_nueva.strip():
        raise HTTPException(status_code=400, detail={"mensaje": MSG_BLANCOS, "tipo": "error"})

    # Validación de política de contraseñas en el backend (fuente de verdad)
    errores = validar_politica_clave(data.clave_nueva, data.documento_identidad.strip())
    if errores:
        raise HTTPException(status_code=400, detail={"mensaje": " ".join(errores), "tipo": "error"})

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, clave_hash, bloqueado FROM usuarios WHERE tipo_documento = %s AND documento_identidad = %s;",
                    (data.tipo_documento, data.documento_identidad.strip()))
        usuario = cur.fetchone()
        if not usuario:
            raise HTTPException(status_code=404, detail={"mensaje": "Usuario no encontrado.", "tipo": "error"})
        if usuario['bloqueado']:
            raise HTTPException(status_code=403, detail={"mensaje": MSG_BLOQUEADO, "tipo": "error"})
        if not verificar_clave(data.clave_actual, usuario['clave_hash']):
            raise HTTPException(status_code=401, detail={"mensaje": "La contraseña actual es incorrecta.", "tipo": "error"})

        cur.execute("""
            UPDATE usuarios
            SET clave_hash = %s,
                fecha_clave = CURRENT_TIMESTAMP,
                clave_provisoria = FALSE,
                intentos_fallidos = 0
            WHERE id = %s;
        """, (hashear_clave(data.clave_nueva), usuario['id']))
        db.commit()
        return {"message": "Contraseña actualizada exitosamente."}
    finally:
        cur.close()