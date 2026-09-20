"""
routers/usuarios.py
Objetivo: Endpoints del módulo de gestión de usuarios: creación de usuarios con clave
          provisoria que cumple la política vigente, listado con filtros (global o por
          comedor), bloqueo/desbloqueo administrativo de cuentas, desbloqueo por intentos
          fallidos (admin de sistema o admin del comedor) y edición de la política de
          contraseñas (longitud, expiración e intentos) almacenada en parametros_sistema.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos:
  - Crear / bloquear cuenta / política de claves: privilegios globales (GESTION_USUARIOS,
    GESTION_POLITICAS_CLAVE) o administrador de sistemas.
  - Listar por comedor y desbloquear por intentos: privilegio GESTION_USUARIOS_COMEDOR
    con cobertura sobre el comedor correspondiente.
Nota: Mientras no exista middleware JWT, el solicitante se identifica mediante
      `usuario_solicitante_id` en el payload (el frontend lo envía desde la sesión).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db, get_parametros_dict
from schemas.gestion_usuarios import (
    UsuarioCreate,
    CambiarEstadoCuentaInput,
    DesbloqueoReintentosInput,
    PoliticaClaveUpdate,
)
from seguridad import (
    hashear_clave,
    validar_politica_clave,
    politica_por_defecto,
    PARAM_LONG_MIN, PARAM_LONG_MAX, PARAM_MESES_EXPIRACION, PARAM_MAX_INTENTOS,
)
from permisos import (
    puede_gestionar_usuarios_global,
    puede_gestionar_usuarios_comedor,
    puede_gestionar_politicas_clave,
)

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

# Rol global neutro para usuarios creados desde el módulo (el rol operativo vive
# en usuario_grupo / usuario_comedor; este campo es legacy de COM-19/COM-21)
ROL_USUARIO_BASE = "Usuario"


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _politica_vigente(db) -> dict:
    """
    Lee la política de contraseñas desde parametros_sistema (categoría SEGURIDAD)
    y la combina con los defaults de seguridad.py como respaldo.
    """
    params = get_parametros_dict(db, [
        PARAM_LONG_MIN, PARAM_LONG_MAX, PARAM_MESES_EXPIRACION, PARAM_MAX_INTENTOS
    ])
    politica = politica_por_defecto()
    politica.update(params)
    return politica


def _existe_usuario(cur, usuario_id: int) -> bool:
    cur.execute("SELECT 1 FROM usuarios WHERE id = %s;", (usuario_id,))
    return cur.fetchone() is not None


def _comedores_del_usuario(cur, usuario_id: int):
    """Comedores (id) donde el usuario tiene membresía, activos o no."""
    cur.execute("SELECT DISTINCT comedor_id FROM usuario_comedor WHERE usuario_id = %s;",
                (usuario_id,))
    return [row["comedor_id"] for row in cur.fetchall()]


# ==========================================
# POLÍTICA DE CONTRASEÑAS (lectura y edición)
# ==========================================
@router.get("/politica-clave")
def obtener_politica_clave(db=Depends(get_db)):
    """Política vigente: longitudes, meses de expiración e intentos máximos."""
    politica = _politica_vigente(db)
    return {
        "longitud_min": int(politica[PARAM_LONG_MIN]),
        "longitud_max": int(politica[PARAM_LONG_MAX]),
        "meses_expiracion": int(politica[PARAM_MESES_EXPIRACION]),
        "max_intentos": int(politica[PARAM_MAX_INTENTOS]),
    }


@router.put("/politica-clave")
def actualizar_politica_clave(data: PoliticaClaveUpdate, db=Depends(get_db)):
    """
    Actualiza la política de contraseñas en parametros_sistema (categoría SEGURIDAD).
    Valida rangos y coherencia (min <= max) antes de persistir.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_gestionar_politicas_clave(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: se requiere el privilegio de Políticas de Contraseñas.")

        vigente = _politica_vigente(db)
        longitud_min = data.longitud_min if data.longitud_min is not None else int(vigente[PARAM_LONG_MIN])
        longitud_max = data.longitud_max if data.longitud_max is not None else int(vigente[PARAM_LONG_MAX])
        meses = data.meses_expiracion if data.meses_expiracion is not None else int(vigente[PARAM_MESES_EXPIRACION])
        intentos = data.max_intentos if data.max_intentos is not None else int(vigente[PARAM_MAX_INTENTOS])

        # Validación de rangos y coherencia de la política
        if not (6 <= longitud_min <= 32):
            raise HTTPException(status_code=400, detail="La longitud mínima debe estar entre 6 y 32.")
        if not (longitud_min <= longitud_max <= 64):
            raise HTTPException(status_code=400, detail="La longitud máxima debe ser >= mínima y <= 64.")
        if not (1 <= meses <= 60):
            raise HTTPException(status_code=400, detail="Los meses de expiración deben estar entre 1 y 60.")
        if not (1 <= intentos <= 10):
            raise HTTPException(status_code=400, detail="Los intentos máximos deben estar entre 1 y 10.")

        # Upsert de cada parámetro de la política (categoría SEGURIDAD)
        cambios = [
            (PARAM_LONG_MIN, longitud_min, 'Longitud mínima de contraseña (política de seguridad)'),
            (PARAM_LONG_MAX, longitud_max, 'Longitud máxima de contraseña (política de seguridad)'),
            (PARAM_MESES_EXPIRACION, meses, 'Meses de vigencia de la contraseña (política de seguridad)'),
            (PARAM_MAX_INTENTOS, intentos, 'Intentos fallidos antes de bloqueo (política de seguridad)'),
        ]
        for clave, valor, descripcion in cambios:
            cur.execute("""
                INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato)
                VALUES (%s, %s, %s, 'SEGURIDAD', 'INTEGER')
                ON CONFLICT (clave) DO UPDATE
                  SET valor = EXCLUDED.valor,
                      fecha_actualizacion = CURRENT_TIMESTAMP - INTERVAL '5 hours';
            """, (clave, str(valor), descripcion))
        db.commit()
        return {"message": "Política de contraseñas actualizada exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al actualizar la política: {e}")
    finally:
        cur.close()


# ==========================================
# LISTADO DE USUARIOS (global o por comedor)
# ==========================================
@router.get("")
def listar_usuarios(q: str = None, estado: str = None, comedor_id: int = None,
                    db=Depends(get_db), usuario_solicitante_id: int = None):
    """
    Lista usuarios con filtros:
      - Con comedor_id: usuarios del comedor (requiere GESTION_USUARIOS_COMEDOR con
        cobertura) incluyendo estado de membresía y rol en el comedor.
      - Sin comedor_id: listado global (requiere GESTION_USUARIOS o admin de sistemas).
    estado: 'activos' | 'inactivos' | None (todos).
    """
    if usuario_solicitante_id is None:
        raise HTTPException(status_code=400, detail="Debe indicar el usuario solicitante.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if comedor_id is not None:
            # Ámbito comedor: usuarios con membresía en ese comedor
            if not puede_gestionar_usuarios_comedor(cur, usuario_solicitante_id, comedor_id):
                raise HTTPException(status_code=403,
                                detail="Sin permiso sobre los usuarios de este comedor.")
            query = """
                SELECT u.id, u.tipo_documento, u.documento_identidad, u.nombres,
                       u.apellido_paterno, u.apellido_materno, u.rol,
                       u.estado_activo, u.bloqueado, u.intentos_fallidos,
                       uc.estado_activo AS membresia_activa, uc.rol AS rol_comedor
                FROM usuario_comedor uc
                JOIN usuarios u ON u.id = uc.usuario_id
                WHERE uc.comedor_id = %s
            """
            params = [comedor_id]
        else:
            # Ámbito global
            if not puede_gestionar_usuarios_global(cur, usuario_solicitante_id):
                raise HTTPException(status_code=403,
                                detail="Sin permiso: se requiere el privilegio de Gestión de Usuarios.")
            query = """
                SELECT id, tipo_documento, documento_identidad, nombres,
                       apellido_paterno, apellido_materno, rol,
                       estado_activo, bloqueado, intentos_fallidos
                FROM usuarios
                WHERE 1=1
            """
            params = []
        if q:
            query += " AND (documento_identidad ILIKE %s OR nombres ILIKE %s OR apellido_paterno ILIKE %s)"
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if estado == "activos":
            query += " AND estado_activo = TRUE"
        elif estado == "inactivos":
            query += " AND estado_activo = FALSE"
        query += " ORDER BY nombres, apellido_paterno;"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# CREACIÓN DE USUARIOS
# ==========================================
@router.post("", status_code=201)
def crear_usuario(data: UsuarioCreate, db=Depends(get_db)):
    """
    Crea un usuario del sistema con clave inicial provisoria (cambio obligatorio en
    primer login). La clave debe cumplir la política vigente (parametros SEGURIDAD).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_gestionar_usuarios_global(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: se requiere el privilegio de Gestión de Usuarios.")

        # Unicidad del documento
        cur.execute("SELECT 1 FROM usuarios WHERE documento_identidad = %s;",
                    (data.documento_identidad.strip(),))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese documento.")

        # Validación de la clave inicial contra la política vigente
        politica = _politica_vigente(db)
        errores = validar_politica_clave(data.clave_inicial, data.documento_identidad.strip(), politica)
        if errores:
            raise HTTPException(status_code=400, detail=" ".join(errores))

        cur.execute("""
            INSERT INTO usuarios
            (tipo_documento, documento_identidad, nombres, apellido_paterno, apellido_materno,
             fecha_nacimiento, clave_hash, rol, estado_activo, bloqueado, intentos_fallidos,
             clave_provisoria, fecha_clave)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE, 0, TRUE, CURRENT_TIMESTAMP)
            RETURNING id;
        """, (
            data.tipo_documento, data.documento_identidad.strip(), data.nombres,
            data.apellido_paterno, data.apellido_materno, data.fecha_nacimiento,
            hashear_clave(data.clave_inicial), ROL_USUARIO_BASE,
        ))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id,
                "message": "Usuario creado exitosamente. Deberá cambiar su clave en el primer ingreso."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al crear el usuario: {e}")
    finally:
        cur.close()


# ==========================================
# BLOQUEO / DESBLOQUEO ADMINISTRATIVO DE CUENTA
# ==========================================
@router.put("/{usuario_id}/estado-cuenta")
def cambiar_estado_cuenta(usuario_id: int, data: CambiarEstadoCuentaInput, db=Depends(get_db)):
    """
    Bloqueo/desbloqueo administrativo de la cuenta (usuarios.estado_activo).
    Una cuenta inactiva no puede iniciar sesión. No permite auto-bloqueo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_gestionar_usuarios_global(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: se requiere el privilegio de Gestión de Usuarios.")
        if not _existe_usuario(cur, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if usuario_id == data.usuario_solicitante_id:
            raise HTTPException(status_code=400, detail="No puedes bloquear o desbloquear tu propia cuenta.")

        cur.execute("UPDATE usuarios SET estado_activo = %s WHERE id = %s;",
                    (data.estado_activo, usuario_id))
        db.commit()
        accion = "desbloqueada" if data.estado_activo else "bloqueada"
        return {"message": f"Cuenta {accion} exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al cambiar el estado de la cuenta: {e}")
    finally:
        cur.close()


# ==========================================
# DESBLOQUEO POR INTENTOS FALLIDOS
# ==========================================
@router.put("/{usuario_id}/desbloqueo-reintentos")
def desbloquear_reintentos(usuario_id: int, data: DesbloqueoReintentosInput, db=Depends(get_db)):
    """
    Resetea el bloqueo por intentos fallidos (bloqueado=FALSE, intentos=0).
    Permitido a: admin de sistemas / GESTION_USUARIOS global, o admin de comedor con
    cobertura sobre ALGÚN comedor donde el usuario bloqueado tenga membresía.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_usuario(cur, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        autorizado = puede_gestionar_usuarios_global(cur, data.usuario_solicitante_id)
        if not autorizado:
            # Buscar cobertura en los comedores del usuario bloqueado
            for comedor_id in _comedores_del_usuario(cur, usuario_id):
                if puede_gestionar_usuarios_comedor(cur, data.usuario_solicitante_id, comedor_id):
                    autorizado = True
                    break
        if not autorizado:
            raise HTTPException(status_code=403,
                            detail="Sin permiso: requiere Gestión de Usuarios global o ser admin de un comedor del usuario.")

        cur.execute("""
            UPDATE usuarios
            SET bloqueado = FALSE, intentos_fallidos = 0
            WHERE id = %s;
        """, (usuario_id,))
        db.commit()
        return {"message": "Bloqueo por intentos restablecido exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al desbloquear por intentos: {e}")
    finally:
        cur.close()