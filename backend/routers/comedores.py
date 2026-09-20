"""
routers/comedores.py
Objetivo: Endpoints de comedores (COM-21): CRUD, asociación de usuarios, estado por
          comedor, contexto de selección (COM-20) y búsqueda para el autocompletado
          del flujo de creación/edición de usuarios (corrección COM-26).
Uso: Registrado en main.py con prefijo /api/v1.
Nota: Mientras no exista middleware JWT, el solicitante se identifica mediante
      `usuario_solicitante_id` en el payload (el frontend lo envía desde la sesión).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db
from schemas.comedor import (
    ComedorCreate, ComedorUpdate, AsociarUsuarioInput,
    CambiarEstadoUsuarioComedorInput, ROLES_COMEDOR
)
from permisos import es_admin_sistema, es_admin_comedor, GRUPO_ADMINISTRATIVO

router = APIRouter(prefix="/comedores", tags=["Comedores"])

ROL_SISTEMA = "Administrador Sistema"
ROL_ADMIN_COMEDOR = "Administrador"


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _existe_comedor(cur, comedor_id: int) -> bool:
    cur.execute("SELECT 1 FROM comedores WHERE id = %s;", (comedor_id,))
    return cur.fetchone() is not None


def _validar_permiso_admin(cur, usuario_id: int, comedor_id: int):
    """Regla COM-21/COM-22: pueden operar cambios sobre el comedor el admin de sistemas,
    el admin del comedor, un Directivo Presidente/Tesorero o un Administrativo con cobertura."""
    if not (es_admin_sistema(cur, usuario_id) or
            es_admin_comedor(cur, usuario_id, comedor_id)):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: solo el administrador del comedor o del sistema puede ejecutar esta acción."
        )


# ==========================================
# ENDPOINTS DE COMEDORES (CATÁLOGO)
# ==========================================
@router.get("")
def listar_comedores(departamento: str = None, distrito: str = None,
                     nombre: str = None, db=Depends(get_db)):
    """Lista comedores con filtros opcionales por departamento, distrito o nombre."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = "SELECT * FROM comedores WHERE 1=1"
        params = []
        if departamento:
            query += " AND departamento ILIKE %s"
            params.append(departamento)
        if distrito:
            query += " AND distrito ILIKE %s"
            params.append(distrito)
        if nombre:
            query += " AND nombre ILIKE %s"
            params.append(f"%{nombre}%")
        query += " ORDER BY departamento, ciudad, distrito, nombre;"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()


# IMPORTANTE: rutas fijas declaradas ANTES de /{comedor_id} para evitar conflictos
@router.get("/por-usuario/{usuario_id}")
def comedores_de_usuario(usuario_id: int, db=Depends(get_db)):
    """Devuelve los comedores (y su estado/rol) a los que pertenece un usuario."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT c.*, uc.rol AS rol_comedor, uc.estado_activo
            FROM usuario_comedor uc
            JOIN comedores c ON c.id = uc.comedor_id
            WHERE uc.usuario_id = %s
            ORDER BY c.nombre;
        """, (usuario_id,))
        return cur.fetchall()
    finally:
        cur.close()


@router.get("/usuarios/buscar")
def buscar_usuario_por_documento(documento: str, db=Depends(get_db)):
    """COM-21: búsqueda de usuario por documento para el flujo de asociación."""
    if not documento or not documento.strip():
        raise HTTPException(status_code=400, detail="Debe indicar un documento de búsqueda.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, tipo_documento, documento_identidad, nombres,
                   apellido_paterno, apellido_materno, rol, estado_activo
            FROM usuarios
            WHERE documento_identidad = %s;
        """, (documento.strip(),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Usuario no encontrado con ese documento.")
        return row
    finally:
        cur.close()


# ==========================================
# BÚSQUEDA DE COMEDORES PARA AUTOCOMPLETADO (COM-26)
# IMPORTANTE: se declara antes de las rutas /{comedor_id} para evitar conflictos.
# ==========================================
@router.get("/buscar")
def buscar_comedores(q: str = "", db=Depends(get_db)):
    """
    COM-26: búsqueda de comedores por nombre o ubicación (departamento, ciudad, distrito).
    Alimenta el campo de texto con autocompletado del formulario de usuarios.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        like = f"%{q}%" if q.strip() else "%"
        cur.execute("""
            SELECT id, nombre, departamento, ciudad, distrito, zona
            FROM comedores
            WHERE nombre ILIKE %s OR departamento ILIKE %s
               OR ciudad ILIKE %s OR distrito ILIKE %s
            ORDER BY nombre
            LIMIT 15;
        """, (like, like, like, like))
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# COM-20: CONTEXTO DE SELECCIÓN Y VERIFICACIÓN
# ==========================================
@router.get("/contexto-seleccion")
def contexto_seleccion(usuario_id: int, db=Depends(get_db)):
    """
    COM-20: datos para la pantalla de selección de comedor post-login: perfil,
    membresías activas y alcance global (solo para Administrativos).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Perfil del usuario según grupos/roles (COM-22)
        if es_admin_sistema(cur, usuario_id):
            perfil = "SISTEMA"
        else:
            cur.execute("""
                SELECT 1 FROM usuario_grupo ug
                JOIN grupos_usuario g ON g.id = ug.grupo_id
                WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND g.nombre = %s
                LIMIT 1;
            """, (usuario_id, GRUPO_ADMINISTRATIVO))
            perfil = "ADMINISTRATIVO" if cur.fetchone() else "COMEDOR"

        # Membresías activas (única fuente de opciones para el usuario)
        cur.execute("""
            SELECT uc.comedor_id, uc.rol AS rol_comedor,
                   c.departamento, c.ciudad, c.distrito, c.zona, c.nombre
            FROM usuario_comedor uc
            JOIN comedores c ON c.id = uc.comedor_id
            WHERE uc.usuario_id = %s AND uc.estado_activo = TRUE
            ORDER BY c.departamento, c.ciudad, c.distrito, c.nombre;
        """, (usuario_id,))
        membresias = cur.fetchall()

        alcance_global = False
        if perfil == "ADMINISTRATIVO":
            cur.execute("""
                SELECT 1 FROM usuario_grupo ug
                JOIN grupos_usuario g ON g.id = ug.grupo_id
                WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
                  AND g.nombre = %s AND ug.comedor_id IS NULL
                LIMIT 1;
            """, (usuario_id, GRUPO_ADMINISTRATIVO))
            alcance_global = cur.fetchone() is not None

        return {"perfil": perfil, "membresias_activas": membresias, "alcance_global": alcance_global}
    finally:
        cur.close()


@router.get("/verificar-membresia")
def verificar_membresia(usuario_id: int, comedor_id: int = None,
                        perfil: str = "COMEDOR", db=Depends(get_db)):
    """
    COM-20: verifica que el usuario SIGUE activo en el contexto recordado
    (se llama en login recordado y al restaurar sesión).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if perfil == "SISTEMA":
            activo = es_admin_sistema(cur, usuario_id)
        elif perfil == "ADMINISTRATIVO":
            cur.execute("""
                SELECT 1 FROM usuario_grupo ug
                JOIN grupos_usuario g ON g.id = ug.grupo_id
                WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND g.nombre = %s
                LIMIT 1;
            """, (usuario_id, GRUPO_ADMINISTRATIVO))
            activo = cur.fetchone() is not None
        else:
            if comedor_id is None:
                activo = False
            else:
                cur.execute("""
                    SELECT 1 FROM usuario_comedor
                    WHERE usuario_id = %s AND comedor_id = %s AND estado_activo = TRUE;
                """, (usuario_id, comedor_id))
                activo = cur.fetchone() is not None
        return {"activo": bool(activo)}
    finally:
        cur.close()


# ==========================================
# CRUD DE COMEDORES (COM-21)
# ==========================================
@router.post("", status_code=201)
def crear_comedor(data: ComedorCreate, db=Depends(get_db)):
    """Crea un comedor. Regla COM-21/COM-22: exclusivo del Administrador de Sistemas."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not es_admin_sistema(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Solo el Administrador del Sistema puede crear comedores.")
        cur.execute("""
            INSERT INTO comedores
            (departamento, ciudad, distrito, zona, nombre, direccion, link_ubicacion, fecha_fundacion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (data.departamento, data.ciudad, data.distrito, data.zona,
              data.nombre, data.direccion, data.link_ubicacion, data.fecha_fundacion))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id, "message": "Comedor creado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Ya existe un comedor con ese nombre.")
        raise HTTPException(status_code=400, detail=f"Error al crear el comedor: {e}")
    finally:
        cur.close()


@router.get("/{comedor_id}")
def obtener_comedor(comedor_id: int, db=Depends(get_db)):
    """Detalle de un comedor por id."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM comedores WHERE id = %s;", (comedor_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        return row
    finally:
        cur.close()


@router.put("/{comedor_id}")
def actualizar_comedor(comedor_id: int, data: ComedorUpdate, db=Depends(get_db)):
    """Actualización parcial de comedor (admin sistema o quien gestiona el comedor)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_comedor(cur, comedor_id):
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        _validar_permiso_admin(cur, data.usuario_solicitante_id, comedor_id)

        campos = {k: v for k, v in data.dict(exclude_unset=True).items()
                  if k != "usuario_solicitante_id" and v is not None}
        if not campos:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar.")
        sets = ", ".join([f"{k} = %s" for k in campos.keys()])
        cur.execute(f"UPDATE comedores SET {sets} WHERE id = %s RETURNING id;",
                    list(campos.values()) + [comedor_id])
        db.commit()
        return {"message": "Comedor actualizado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al actualizar el comedor: {e}")
    finally:
        cur.close()


# ==========================================
# ASOCIACIÓN USUARIO-COMEDOR (COM-21)
# ==========================================
@router.get("/{comedor_id}/usuarios")
def usuarios_del_comedor(comedor_id: int, db=Depends(get_db)):
    """Lista los usuarios asociados al comedor con su rol y estado."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_comedor(cur, comedor_id):
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        cur.execute("""
            SELECT uc.id, uc.usuario_id, uc.rol, uc.estado_activo,
                   uc.desactivado_por, uc.fecha_desactivacion,
                   u.nombres, u.apellido_paterno, u.apellido_materno,
                   u.tipo_documento, u.documento_identidad
            FROM usuario_comedor uc
            JOIN usuarios u ON u.id = uc.usuario_id
            WHERE uc.comedor_id = %s
            ORDER BY u.nombres;
        """, (comedor_id,))
        return cur.fetchall()
    finally:
        cur.close()


@router.post("/{comedor_id}/usuarios", status_code=201)
def asociar_usuario(comedor_id: int, data: AsociarUsuarioInput, db=Depends(get_db)):
    """Asocia un usuario existente al comedor (cero o varios comedores por usuario)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_comedor(cur, comedor_id):
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        _validar_permiso_admin(cur, data.usuario_solicitante_id, comedor_id)

        if data.rol not in ROLES_COMEDOR:
            raise HTTPException(status_code=400,
                            detail=f"Rol inválido. Permitidos: {', '.join(ROLES_COMEDOR)}.")
        cur.execute("SELECT 1 FROM usuarios WHERE id = %s;", (data.usuario_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        cur.execute("SELECT 1 FROM usuario_comedor WHERE usuario_id = %s AND comedor_id = %s;",
                    (data.usuario_id, comedor_id))
        if cur.fetchone():
            raise HTTPException(status_code=400,
                            detail="El usuario ya está asociado a este comedor. Use el endpoint de estado para reactivarlo.")
        cur.execute("""
            INSERT INTO usuario_comedor (usuario_id, comedor_id, rol, estado_activo)
            VALUES (%s, %s, %s, TRUE)
            RETURNING id;
        """, (data.usuario_id, comedor_id, data.rol))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id, "message": "Usuario asociado al comedor exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al asociar el usuario: {e}")
    finally:
        cur.close()


@router.put("/{comedor_id}/usuarios/{usuario_id}")
def cambiar_estado_usuario(comedor_id: int, usuario_id: int,
                           data: CambiarEstadoUsuarioComedorInput, db=Depends(get_db)):
    """
    Activa/desactiva a un usuario DENTRO de un comedor (el estado es por comedor).
    Reglas COM-21: solo quien gestiona el comedor o el admin del sistema;
    nadie se desactiva a sí mismo; el comedor no queda sin su último admin activo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_comedor(cur, comedor_id):
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        _validar_permiso_admin(cur, data.usuario_solicitante_id, comedor_id)

        cur.execute("SELECT * FROM usuario_comedor WHERE usuario_id = %s AND comedor_id = %s;",
                    (usuario_id, comedor_id))
        registro = cur.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="El usuario no está asociado a este comedor.")

        if not data.estado_activo and usuario_id == data.usuario_solicitante_id:
            raise HTTPException(status_code=400, detail="No puedes desactivarte a ti mismo en este comedor.")

        if not data.estado_activo and registro["rol"] == ROL_ADMIN_COMEDOR and registro["estado_activo"]:
            if not es_admin_sistema(cur, data.usuario_solicitante_id):
                cur.execute("""
                    SELECT COUNT(*) AS n FROM usuario_comedor
                    WHERE comedor_id = %s AND rol = %s AND estado_activo = TRUE;
                """, (comedor_id, ROL_ADMIN_COMEDOR))
                if cur.fetchone()["n"] <= 1:
                    raise HTTPException(status_code=400,
                                    detail="No se puede desactivar al último administrador activo del comedor.")

        if data.estado_activo:
            cur.execute("""
                UPDATE usuario_comedor
                SET estado_activo = TRUE, desactivado_por = NULL, fecha_desactivacion = NULL
                WHERE usuario_id = %s AND comedor_id = %s;
            """, (usuario_id, comedor_id))
        else:
            cur.execute("""
                UPDATE usuario_comedor
                SET estado_activo = FALSE, desactivado_por = %s,
                    fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
                WHERE usuario_id = %s AND comedor_id = %s;
            """, (data.usuario_solicitante_id, usuario_id, comedor_id))
        db.commit()
        accion = "activado" if data.estado_activo else "desactivado"
        return {"message": f"Usuario {accion} en el comedor exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al cambiar el estado: {e}")
    finally:
        cur.close()