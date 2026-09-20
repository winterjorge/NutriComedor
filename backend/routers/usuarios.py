"""
routers/usuarios.py
Objetivo: Endpoints del módulo de gestión de usuarios: creación y edición de usuarios
          mediante el flujo por perfil (corrección COM-26), contexto de creación para
          el formulario dinámico, detalle de flujo para precargar la edición, listado
          con filtros, bloqueo/desbloqueo administrativo, desbloqueo por intentos y
          edición de la política de contraseñas.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos (COM-26): la matriz de creación por perfil y el alcance del solicitante
     (municipalidades o comedores permitidos) se validan con permisos.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db, get_parametros_dict
from schemas.gestion_usuarios import (
    UsuarioCreate, UsuarioUpdate,
    CambiarEstadoCuentaInput, DesbloqueoReintentosInput, PoliticaClaveUpdate,
)
from seguridad import (
    hashear_clave, validar_politica_clave, politica_por_defecto,
    PARAM_LONG_MIN, PARAM_LONG_MAX, PARAM_MESES_EXPIRACION, PARAM_MAX_INTENTOS,
)
from permisos import (
    obtener_perfil_usuario, puede_crear_perfil, MATRIZ_CREACION_PERFILES,
    alcance_municipalidades, alcance_comedores,
    es_cargo_no_repetible, hay_cargo_permanente_ocupado,
    puede_gestionar_usuarios_global, puede_gestionar_politicas_clave,
    GRUPO_SISTEMA, GRUPO_ADMINISTRATIVO, GRUPO_DIRECTIVO, GRUPO_OPERATIVO,
    PERFIL_ADMIN_SISTEMA, PERFIL_ADMINISTRATIVO, PERFIL_DIRECTIVO, PERFIL_OPERATIVO,
)

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

# Rol global neutro para usuarios creados desde el módulo (legacy usuarios.rol)
ROL_USUARIO_BASE = "Usuario"

# COM-26: correspondencia perfil objetivo -> grupo del catálogo
GRUPO_POR_PERFIL = {
    PERFIL_ADMIN_SISTEMA: GRUPO_SISTEMA,
    PERFIL_ADMINISTRATIVO: GRUPO_ADMINISTRATIVO,
    PERFIL_DIRECTIVO: GRUPO_DIRECTIVO,
    PERFIL_OPERATIVO: GRUPO_OPERATIVO,
}

# COM-26: rol legacy de usuario_comedor según perfil objetivo del comedor
ROL_COMEDOR_POR_PERFIL = {
    PERFIL_DIRECTIVO: "Administrador",
    PERFIL_OPERATIVO: "Operativo",
}


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _politica_vigente(db) -> dict:
    """Política de contraseñas desde parametros_sistema con fallback a los defaults."""
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


def _validar_grupo_rol_perfil(cur, data) -> None:
    """
    COM-26: valida que el grupo enviado corresponda al perfil objetivo y que el rol
    pertenezca a ese grupo. Lanza HTTPException si no se cumple.
    """
    nombre_grupo_esperado = GRUPO_POR_PERFIL.get(data.perfil_objetivo)
    if not nombre_grupo_esperado:
        raise HTTPException(status_code=400, detail=f"Perfil objetivo inválido: {data.perfil_objetivo}.")
    cur.execute("SELECT nombre FROM grupos_usuario WHERE id = %s;", (data.grupo_id,))
    grupo = cur.fetchone()
    if not grupo or grupo["nombre"] != nombre_grupo_esperado:
        raise HTTPException(status_code=400,
                        detail=f"El grupo no corresponde al perfil {data.perfil_objetivo}.")
    cur.execute("SELECT 1 FROM roles_grupo WHERE id = %s AND grupo_id = %s;",
                (data.rol_id, data.grupo_id))
    if not cur.fetchone():
        raise HTTPException(status_code=400, detail="El rol no pertenece al grupo indicado.")


def _validar_alcance(cur, solicitante_id: int, data) -> None:
    """
    COM-26: valida el alcance según el perfil objetivo:
      - ADMINISTRATIVO: municipalidades obligatorias y dentro del alcance del solicitante.
      - DIRECTIVO/OPERATIVO: comedores obligatorios, dentro del alcance, y cargos
        permanentes no repetibles libres (Presidente/Tesorero/Secretario).
    """
    if data.perfil_objetivo == PERFIL_ADMINISTRATIVO:
        if not data.municipalidad_ids:
            raise HTTPException(status_code=400,
                            detail="Debe indicar al menos una municipalidad para el perfil Administrativo.")
        permitidas = {m["id"] for m in alcance_municipalidades(cur, solicitante_id)}
        if not set(data.municipalidad_ids) <= permitidas:
            raise HTTPException(status_code=403,
                            detail="Solo puede asignar municipalidades a las que usted pertenece.")
    elif data.perfil_objetivo in (PERFIL_DIRECTIVO, PERFIL_OPERATIVO):
        if not data.comedor_ids:
            raise HTTPException(status_code=400,
                            detail="Debe indicar al menos un comedor para este perfil.")
        permitidos = {c["id"] for c in alcance_comedores(cur, solicitante_id)}
        if not set(data.comedor_ids) <= permitidos:
            raise HTTPException(status_code=403,
                            detail="Solo puede asignar comedores a los que usted pertenece.")
        excluir = getattr(data, "_excluir_usuario_id", None)
        if es_cargo_no_repetible(cur, data.rol_id):
            for comedor_id in data.comedor_ids:
                if hay_cargo_permanente_ocupado(cur, comedor_id, data.rol_id, excluir):
                    raise HTTPException(
                        status_code=400,
                        detail=(f"El cargo ya está ocupado de forma permanente en el comedor "
                                f"(id {comedor_id}). Use una asignación temporal si desea cubrirlo."))
    # ADMINISTRADOR_SISTEMA: sin información adicional de alcance


def _insertar_membresias(cur, usuario_id: int, data) -> None:
    """
    COM-26: inserta las membresías del usuario según el perfil objetivo:
      - Sistema: membresía global al grupo de sistema.
      - Administrativo: membresía global + asociación a municipalidades.
      - Directivo/Operativo: membresía por comedor + vínculo legacy usuario_comedor.
    """
    if data.perfil_objetivo == PERFIL_ADMIN_SISTEMA:
        cur.execute("""
            INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
            VALUES (%s, %s, %s, NULL, TRUE)
            ON CONFLICT (usuario_id, grupo_id, rol_id, comedor_id) DO NOTHING;
        """, (usuario_id, data.grupo_id, data.rol_id))
    elif data.perfil_objetivo == PERFIL_ADMINISTRATIVO:
        cur.execute("""
            INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
            VALUES (%s, %s, %s, NULL, TRUE)
            ON CONFLICT (usuario_id, grupo_id, rol_id, comedor_id) DO NOTHING;
        """, (usuario_id, data.grupo_id, data.rol_id))
        for municipalidad_id in data.municipalidad_ids:
            cur.execute("""
                INSERT INTO usuario_municipalidad (usuario_id, municipalidad_id, estado_activo)
                VALUES (%s, %s, TRUE)
                ON CONFLICT (usuario_id, municipalidad_id)
                DO UPDATE SET estado_activo = TRUE;
            """, (usuario_id, municipalidad_id))
    else:
        rol_comedor = ROL_COMEDOR_POR_PERFIL[data.perfil_objetivo]
        for comedor_id in data.comedor_ids:
            cur.execute("""
                INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (usuario_id, grupo_id, rol_id, comedor_id) DO NOTHING;
            """, (usuario_id, data.grupo_id, data.rol_id, comedor_id))
            cur.execute("""
                INSERT INTO usuario_comedor (usuario_id, comedor_id, rol, estado_activo)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT (usuario_id, comedor_id)
                DO UPDATE SET estado_activo = TRUE, rol = EXCLUDED.rol;
            """, (usuario_id, comedor_id, rol_comedor))


# ==========================================
# CONTEXTO DE CREACIÓN (COM-26)
# ==========================================
@router.get("/contexto-creacion")
def contexto_creacion(usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-26: datos para el formulario dinámico de creación/edición de usuarios:
    perfil del creador, perfiles que puede crear, grupos/roles disponibles por perfil
    y alcance del solicitante (municipalidades y/o comedores permitidos).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        perfil_creador = obtener_perfil_usuario(cur, usuario_solicitante_id)
        if not perfil_creador:
            raise HTTPException(status_code=403,
                            detail="Su usuario no tiene perfil asignado; no puede crear ni editar usuarios.")
        perfiles_permitidos = sorted(MATRIZ_CREACION_PERFILES.get(perfil_creador, set()))

        grupos_disponibles = []
        for perfil in perfiles_permitidos:
            cur.execute("SELECT id, nombre FROM grupos_usuario WHERE nombre = %s;",
                        (GRUPO_POR_PERFIL[perfil],))
            grupo = cur.fetchone()
            if not grupo:
                continue
            cur.execute("SELECT id, nombre FROM roles_grupo WHERE grupo_id = %s ORDER BY id;",
                        (grupo["id"],))
            grupos_disponibles.append({
                "perfil": perfil,
                "grupo_id": grupo["id"],
                "grupo": grupo["nombre"],
                "roles": cur.fetchall()
            })

        municipalidades = []
        comedores = []
        if PERFIL_ADMINISTRATIVO in perfiles_permitidos:
            municipalidades = alcance_municipalidades(cur, usuario_solicitante_id)
        if PERFIL_DIRECTIVO in perfiles_permitidos or PERFIL_OPERATIVO in perfiles_permitidos:
            comedores = alcance_comedores(cur, usuario_solicitante_id)

        return {
            "perfil_creador": perfil_creador,
            "perfiles_permitidos": perfiles_permitidos,
            "grupos": grupos_disponibles,
            "municipalidades": municipalidades,
            "comedores": comedores
        }
    finally:
        cur.close()


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
    """Actualiza la política de contraseñas (exclusivo de quien posee el privilegio)."""
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

        if not (6 <= longitud_min <= 32):
            raise HTTPException(status_code=400, detail="La longitud mínima debe estar entre 6 y 32.")
        if not (longitud_min <= longitud_max <= 64):
            raise HTTPException(status_code=400, detail="La longitud máxima debe ser >= mínima y <= 64.")
        if not (1 <= meses <= 60):
            raise HTTPException(status_code=400, detail="Los meses de expiración deben estar entre 1 y 60.")
        if not (1 <= intentos <= 10):
            raise HTTPException(status_code=400, detail="Los intentos máximos deben estar entre 1 y 10.")

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
# LISTADO DE USUARIOS
# ==========================================
@router.get("")
def listar_usuarios(q: str = None, estado: str = None, comedor_id: int = None,
                    db=Depends(get_db), usuario_solicitante_id: int = None):
    """
    Lista usuarios con filtros:
      - Con comedor_id: usuarios del comedor (requiere permiso de gestión del comedor).
      - Sin comedor_id: listado global (requiere privilegio de gestión global).
    """
    if usuario_solicitante_id is None:
        raise HTTPException(status_code=400, detail="Debe indicar el usuario solicitante.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if comedor_id is not None:
            if not puede_gestionar_usuarios_global(cur, usuario_solicitante_id):
                from permisos import puede_gestionar_usuarios_comedor
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
# CREACIÓN DE USUARIOS (COM-26)
# ==========================================
@router.post("", status_code=201)
def crear_usuario(data: UsuarioCreate, db=Depends(get_db)):
    """
    COM-26: crea un usuario con membresías y alcance según el perfil objetivo,
    aplicando la matriz de creación del solicitante:
      - Admin de Sistemas: crea Sistema (sin datos extra), Administrativo (municipalidades)
        y Directivo (comedores). No crea Operativo.
      - Administrativo: solo crea Administrativo para sus propias municipalidades.
      - Directivo: crea Directivo y Operativo para sus propios comedores (cargos
        permanentes no repetibles validados).
      - Operativo: no crea usuarios.
    La clave inicial es provisoria (cambio obligatorio en el primer login).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_crear_perfil(cur, data.usuario_solicitante_id, data.perfil_objetivo):
            raise HTTPException(status_code=403,
                            detail=f"Su perfil no permite crear usuarios del perfil {data.perfil_objetivo}.")
        _validar_grupo_rol_perfil(cur, data)
        cur.execute("SELECT 1 FROM usuarios WHERE documento_identidad = %s;",
                    (data.documento_identidad.strip(),))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese documento.")
        politica = _politica_vigente(db)
        errores = validar_politica_clave(data.clave_inicial, data.documento_identidad.strip(), politica)
        if errores:
            raise HTTPException(status_code=400, detail=" ".join(errores))
        _validar_alcance(cur, data.usuario_solicitante_id, data)

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
        _insertar_membresias(cur, nuevo_id, data)

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
# EDICIÓN DE USUARIOS (COM-26)
# ==========================================
@router.put("/{usuario_id}")
def editar_usuario(usuario_id: int, data: UsuarioUpdate, db=Depends(get_db)):
    """
    COM-26: edita los datos personales del usuario y reemplaza las membresías del grupo
    correspondiente al perfil objetivo. Reglas:
      - El solicitante debe poder crear el perfil objetivo (matriz de creación).
      - No se permite la autoedición desde este flujo (evita auto-desasignaciones).
      - Alcance validado como en la creación; los cargos permanentes no repetibles se
        validan excluyendo al propio usuario editado.
      - Comedores/municipalidades retirados de la lista quedan desactivados (auditable).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if usuario_id == data.usuario_solicitante_id:
            raise HTTPException(status_code=400,
                            detail="No puedes editar tu propia cuenta desde este flujo.")
        if not _existe_usuario(cur, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if not puede_crear_perfil(cur, data.usuario_solicitante_id, data.perfil_objetivo):
            raise HTTPException(status_code=403,
                            detail=f"Su perfil no permite editar usuarios del perfil {data.perfil_objetivo}.")
        _validar_grupo_rol_perfil(cur, data)

        if data.documento_identidad:
            cur.execute("SELECT 1 FROM usuarios WHERE documento_identidad = %s AND id <> %s;",
                        (data.documento_identidad.strip(), usuario_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Ya existe otro usuario con ese documento.")

        data._excluir_usuario_id = usuario_id
        _validar_alcance(cur, data.usuario_solicitante_id, data)

        cur.execute("""
            UPDATE usuarios
            SET tipo_documento = COALESCE(%s, tipo_documento),
                documento_identidad = COALESCE(%s, documento_identidad),
                nombres = COALESCE(%s, nombres),
                apellido_paterno = COALESCE(%s, apellido_paterno),
                apellido_materno = COALESCE(%s, apellido_materno),
                fecha_nacimiento = COALESCE(%s, fecha_nacimiento)
            WHERE id = %s;
        """, (
            data.tipo_documento,
            data.documento_identidad.strip() if data.documento_identidad else None,
            data.nombres, data.apellido_paterno, data.apellido_materno,
            data.fecha_nacimiento, usuario_id,
        ))

        cur.execute("DELETE FROM usuario_grupo WHERE usuario_id = %s AND grupo_id = %s;",
                    (usuario_id, data.grupo_id))
        _insertar_membresias(cur, usuario_id, data)

        if data.perfil_objetivo == PERFIL_ADMINISTRATIVO:
            nuevas = set(data.municipalidad_ids)
            cur.execute("SELECT municipalidad_id FROM usuario_municipalidad WHERE usuario_id = %s;",
                        (usuario_id,))
            for fila in cur.fetchall():
                if fila["municipalidad_id"] not in nuevas:
                    cur.execute("""
                        UPDATE usuario_municipalidad
                        SET estado_activo = FALSE, desactivado_por = %s,
                            fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
                        WHERE usuario_id = %s AND municipalidad_id = %s;
                    """, (data.usuario_solicitante_id, usuario_id, fila["municipalidad_id"]))
        elif data.perfil_objetivo in (PERFIL_DIRECTIVO, PERFIL_OPERATIVO):
            nuevos = set(data.comedor_ids)
            for comedor_id in _comedores_del_usuario(cur, usuario_id):
                if comedor_id not in nuevos:
                    cur.execute("""
                        UPDATE usuario_comedor
                        SET estado_activo = FALSE, desactivado_por = %s,
                            fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
                        WHERE usuario_id = %s AND comedor_id = %s;
                    """, (data.usuario_solicitante_id, usuario_id, comedor_id))

        db.commit()
        return {"message": "Usuario actualizado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al editar el usuario: {e}")
    finally:
        cur.close()


# ==========================================
# DETALLE DE FLUJO PARA EDICIÓN (COM-26)
# ==========================================
@router.get("/{usuario_id}/detalle-flujo")
def detalle_flujo_usuario(usuario_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """
    COM-26: datos para precargar el formulario de edición: datos personales, perfil,
    grupo/rol actual y alcance vigente (municipalidades y/o comedores del usuario).
    Permiso: el solicitante debe poder editar el perfil del usuario objetivo
    (matriz de creación por perfil).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_usuario(cur, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        perfil_objetivo = obtener_perfil_usuario(cur, usuario_id)
        if not perfil_objetivo:
            raise HTTPException(status_code=400,
                            detail="El usuario no tiene membresías activas para editar en este flujo.")
        if not puede_crear_perfil(cur, usuario_solicitante_id, perfil_objetivo):
            raise HTTPException(status_code=403,
                            detail="Su perfil no permite editar usuarios de este perfil.")

        cur.execute("""
            SELECT id, tipo_documento, documento_identidad, nombres, apellido_paterno,
                   apellido_materno, fecha_nacimiento
            FROM usuarios WHERE id = %s;
        """, (usuario_id,))
        usuario = cur.fetchone()

        # Membresía activa en el grupo del perfil (grupo y rol actuales)
        cur.execute("""
            SELECT ug.grupo_id, ug.rol_id
            FROM usuario_grupo ug
            JOIN grupos_usuario g ON g.id = ug.grupo_id
            WHERE ug.usuario_id = %s AND g.nombre = %s AND ug.estado_activo = TRUE
            LIMIT 1;
        """, (usuario_id, GRUPO_POR_PERFIL[perfil_objetivo]))
        membresia = cur.fetchone()

        # Alcance vigente del usuario
        municipalidades = []
        comedores = []
        if perfil_objetivo == PERFIL_ADMINISTRATIVO:
            cur.execute("""
                SELECT m.id, m.nombre, m.departamento, m.provincia, m.distrito
                FROM usuario_municipalidad um
                JOIN municipalidades m ON m.id = um.municipalidad_id
                WHERE um.usuario_id = %s AND um.estado_activo = TRUE
                ORDER BY m.nombre;
            """, (usuario_id,))
            municipalidades = cur.fetchall()
        elif perfil_objetivo in (PERFIL_DIRECTIVO, PERFIL_OPERATIVO):
            cur.execute("""
                SELECT DISTINCT c.id, c.nombre, c.departamento, c.ciudad, c.distrito
                FROM usuario_grupo ug
                JOIN comedores c ON c.id = ug.comedor_id
                WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
                  AND ug.comedor_id IS NOT NULL
                ORDER BY c.nombre;
            """, (usuario_id,))
            comedores = cur.fetchall()

        return {
            "usuario": usuario,
            "perfil_objetivo": perfil_objetivo,
            "grupo_id": membresia["grupo_id"] if membresia else None,
            "rol_id": membresia["rol_id"] if membresia else None,
            "municipalidades": municipalidades,
            "comedores": comedores
        }
    finally:
        cur.close()


# ==========================================
# BLOQUEO / DESBLOQUEO ADMINISTRATIVO DE CUENTA
# ==========================================
@router.put("/{usuario_id}/estado-cuenta")
def cambiar_estado_cuenta(usuario_id: int, data: CambiarEstadoCuentaInput, db=Depends(get_db)):
    """Bloqueo/desbloqueo administrativo de la cuenta (usuarios.estado_activo)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_gestionar_usuarios_global(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: se requiere el privilegio de Gestión de Usuarios.")
        if not _existe_usuario(cur, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        if usuario_id == data.usuario_solicitante_id:
            raise HTTPException(status_code=400,
                            detail="No puedes bloquear o desbloquear tu propia cuenta.")
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
    Permitido a: admin de sistemas / gestión global, o admin de comedor con cobertura
    sobre algún comedor del usuario bloqueado.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_usuario(cur, usuario_id):
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        autorizado = puede_gestionar_usuarios_global(cur, data.usuario_solicitante_id)
        if not autorizado:
            from permisos import puede_gestionar_usuarios_comedor
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