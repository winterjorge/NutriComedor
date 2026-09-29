"""
routers/grupos.py
Objetivo: Endpoints del módulo de grupos y privilegios: catálogo de grupos/roles,
          membresías de usuarios (asignación y estado), creación de grupos con ámbito,
          asignación de privilegios a grupos (COM-23) y roles temporales con vigencia
          y revocación (COM-23: ej. el tesorero asume al presidente por un periodo).
Uso: Registrado en main.py con prefijo /api/v1.
Permisos:
  - Crear grupos / asignar privilegios: privilegio GESTION_GRUPOS o admin de sistemas.
  - Membresías: reglas COM-22 (puede_gestionar_grupos por ámbito).
  - Roles temporales: privilegio GESTION_USUARIOS_COMEDOR con cobertura del comedor.
Nota: Mientras no exista middleware JWT, el solicitante se identifica mediante
      `usuario_solicitante_id` en el payload (el frontend lo envía desde la sesión).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db
from schemas.grupo import AsignarGrupoInput, CambiarEstadoMembresiaInput
from schemas.gestion_usuarios import (
    GrupoCreate,
    AsignarPrivilegiosInput,
    RolTemporalInput,
    RevocarRolTemporalInput,
)
from permisos import (
    puede_gestionar_grupos,
    puede_gestionar_grupos_y_privilegios,
    puede_gestionar_usuarios_comedor,
    expirar_roles_temporales,
)

router = APIRouter(prefix="/grupos", tags=["Grupos"])

# Ámbitos válidos para la creación de grupos (COM-23)
AMBITOS_VALIDOS = ("SISTEMA", "GLOBAL", "COMEDOR")


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _existe_comedor(cur, comedor_id: int) -> bool:
    cur.execute("SELECT 1 FROM comedores WHERE id = %s;", (comedor_id,))
    return cur.fetchone() is not None


def _existe_grupo(cur, grupo_id: int) -> bool:
    cur.execute("SELECT 1 FROM grupos_usuario WHERE id = %s;", (grupo_id,))
    return cur.fetchone() is not None


# ==========================================
# CATÁLOGOS
# ==========================================
@router.get("")
def listar_grupos(db=Depends(get_db)):
    """Catálogo de grupos con sus roles (para selects del frontend)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, nombre, ambito, descripcion FROM grupos_usuario ORDER BY id;")
        grupos = cur.fetchall()
        cur.execute("SELECT id, grupo_id, nombre, descripcion FROM roles_grupo ORDER BY grupo_id, id;")
        roles = cur.fetchall()
        for g in grupos:
            g["roles"] = [r for r in roles if r["grupo_id"] == g["id"]]
        return grupos
    finally:
        cur.close()


@router.get("/privilegios")
def listar_privilegios(db=Depends(get_db)):
    """Catálogo de privilegios del sistema con los grupos que los poseen (COM-23)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, clave, nombre, descripcion FROM privilegios ORDER BY id;")
        privilegios = cur.fetchall()
        cur.execute("""
            SELECT gp.privilegio_id, g.id AS grupo_id, g.nombre AS grupo
            FROM grupos_privilegios gp
            JOIN grupos_usuario g ON g.id = gp.grupo_id
            ORDER BY gp.privilegio_id;
        """)
        asignaciones = cur.fetchall()
        for p in privilegios:
            p["grupos"] = [a["grupo"] for a in asignaciones if a["privilegio_id"] == p["id"]]
        return privilegios
    finally:
        cur.close()


@router.get("/por-usuario/{usuario_id}")
def grupos_de_usuario(usuario_id: int, db=Depends(get_db)):
    """Grupos, roles y alcances (global o por comedor) de un usuario."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT ug.id, ug.estado_activo, ug.comedor_id,
                   ug.fecha_registro, ug.fecha_desactivacion,
                   g.nombre AS grupo, g.ambito, r.nombre AS rol, c.nombre AS comedor
            FROM usuario_grupo ug
            JOIN grupos_usuario g ON g.id = ug.grupo_id
            JOIN roles_grupo r ON r.id = ug.rol_id
            LEFT JOIN comedores c ON c.id = ug.comedor_id
            WHERE ug.usuario_id = %s
            ORDER BY g.nombre, r.nombre;
        """, (usuario_id,))
        return cur.fetchall()
    finally:
        cur.close()


@router.get("/membresias")
def listar_membresias(grupo_id: int = None, comedor_id: int = None,
                      estado: str = None, db=Depends(get_db)):
    """
    Listado filtrado de membresías usuario-grupo.
    estado: 'activas' | 'inactivas' | None (todas).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = """
            SELECT ug.id, ug.usuario_id, ug.grupo_id, ug.rol_id, ug.comedor_id,
                   ug.estado_activo, ug.fecha_registro, ug.fecha_desactivacion,
                   u.nombres, u.apellido_paterno, u.documento_identidad,
                   g.nombre AS grupo, g.ambito, r.nombre AS rol, c.nombre AS comedor
            FROM usuario_grupo ug
            JOIN usuarios u ON u.id = ug.usuario_id
            JOIN grupos_usuario g ON g.id = ug.grupo_id
            JOIN roles_grupo r ON r.id = ug.rol_id
            LEFT JOIN comedores c ON c.id = ug.comedor_id
            WHERE 1=1
        """
        params = []
        if grupo_id is not None:
            query += " AND ug.grupo_id = %s"
            params.append(grupo_id)
        if comedor_id is not None:
            query += " AND ug.comedor_id = %s"
            params.append(comedor_id)
        if estado == "activas":
            query += " AND ug.estado_activo = TRUE"
        elif estado == "inactivas":
            query += " AND ug.estado_activo = FALSE"
        query += " ORDER BY u.nombres, g.nombre;"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# CREACIÓN DE GRUPOS Y PRIVILEGIOS (COM-23)
# ==========================================
@router.post("", status_code=201)
def crear_grupo(data: GrupoCreate, db=Depends(get_db)):
    """Crea un grupo con ámbito SISTEMA/GLOBAL/COMEDOR (privilegio GESTION_GRUPOS)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_gestionar_grupos_y_privilegios(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: se requiere el privilegio de Gestión de Grupos y Privilegios.")
        if data.ambito not in AMBITOS_VALIDOS:
            raise HTTPException(status_code=400,
                            detail=f"Ámbito inválido. Permitidos: {', '.join(AMBITOS_VALIDOS)}.")
        cur.execute("""
            INSERT INTO grupos_usuario (nombre, ambito, descripcion)
            VALUES (%s, %s, %s)
            RETURNING id;
        """, (data.nombre, data.ambito, data.descripcion))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id, "message": "Grupo creado exitosamente. Asigne privilegios y roles según corresponda."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Ya existe un grupo con ese nombre.")
        raise HTTPException(status_code=400, detail=f"Error al crear el grupo: {e}")
    finally:
        cur.close()


@router.put("/{grupo_id}/privilegios")
def asignar_privilegios(grupo_id: int, data: AsignarPrivilegiosInput, db=Depends(get_db)):
    """
    Reemplaza el conjunto de privilegios del grupo por la lista enviada
    (privilegio GESTION_GRUPOS). Lista vacía deja al grupo sin privilegios.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_grupo(cur, grupo_id):
            raise HTTPException(status_code=404, detail="Grupo no encontrado.")
        if not puede_gestionar_grupos_y_privilegios(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: se requiere el privilegio de Gestión de Grupos y Privilegios.")

        # Validar que todos los privilegios enviados existan
        if data.privilegio_ids:
            cur.execute("SELECT COUNT(*) AS n FROM privilegios WHERE id = ANY(%s);",
                        (data.privilegio_ids,))
            if cur.fetchone()["n"] != len(data.privilegio_ids):
                raise HTTPException(status_code=400, detail="Uno o más privilegios enviados no existen.")

        # Reemplazo atómico del mapping grupo-privilegios
        cur.execute("DELETE FROM grupos_privilegios WHERE grupo_id = %s;", (grupo_id,))
        for privilegio_id in data.privilegio_ids:
            cur.execute("""
                INSERT INTO grupos_privilegios (grupo_id, privilegio_id)
                VALUES (%s, %s)
                ON CONFLICT (grupo_id, privilegio_id) DO NOTHING;
            """, (grupo_id, privilegio_id))
        db.commit()
        return {"message": "Privilegios del grupo actualizados exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al asignar privilegios: {e}")
    finally:
        cur.close()


# ==========================================
# MEMBRESÍAS (COM-22, se conserva)
# ==========================================
@router.post("/membresias", status_code=201)
def asignar_grupo(data: AsignarGrupoInput, db=Depends(get_db)):
    """
    Asigna un usuario a un grupo con rol y alcance.
    Reglas: el rol debe pertenecer al grupo; los grupos COMEDOR exigen comedor_id;
    los grupos SISTEMA fuerzan alcance global; permisos según ámbito (permisos.py).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, nombre, ambito FROM grupos_usuario WHERE id = %s;", (data.grupo_id,))
        grupo = cur.fetchone()
        if not grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado.")
        cur.execute("SELECT id FROM roles_grupo WHERE id = %s AND grupo_id = %s;",
                    (data.rol_id, data.grupo_id))
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="El rol no pertenece al grupo indicado.")
        cur.execute("SELECT 1 FROM usuarios WHERE id = %s;", (data.usuario_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        comedor_id = data.comedor_id
        if grupo["ambito"] == "SISTEMA":
            comedor_id = None
        elif grupo["ambito"] == "COMEDOR":
            if comedor_id is None:
                raise HTTPException(status_code=400,
                                detail="Los grupos de comedor exigen indicar el comedor (alcance).")
            if not _existe_comedor(cur, comedor_id):
                raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        elif grupo["ambito"] == "GLOBAL" and comedor_id is not None:
            if not _existe_comedor(cur, comedor_id):
                raise HTTPException(status_code=404, detail="Comedor no encontrado.")

        if not puede_gestionar_grupos(cur, data.usuario_solicitante_id, grupo["ambito"], comedor_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso para asignar membresías en este ámbito.")

        cur.execute("""
            SELECT 1 FROM usuario_grupo
            WHERE usuario_id = %s AND rol_id = %s
              AND comedor_id IS NOT DISTINCT FROM %s;
        """, (data.usuario_id, data.rol_id, comedor_id))
        if cur.fetchone():
            raise HTTPException(status_code=400,
                            detail="El usuario ya posee esa membresía con ese rol y alcance.")

        cur.execute("""
            INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
            VALUES (%s, %s, %s, %s, TRUE)
            RETURNING id;
        """, (data.usuario_id, data.grupo_id, data.rol_id, comedor_id))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id, "message": "Membresía asignada exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al asignar el grupo: {e}")
    finally:
        cur.close()


@router.put("/membresias/{membresia_id}")
def cambiar_estado_membresia(membresia_id: int,
                             data: CambiarEstadoMembresiaInput, db=Depends(get_db)):
    """
    Activa/desactiva una membresía dejando auditoría (desactivado_por y fecha).
    Reglas: permiso según ámbito del grupo; nadie puede desactivarse a sí mismo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT ug.*, g.ambito, g.nombre AS grupo
            FROM usuario_grupo ug
            JOIN grupos_usuario g ON g.id = ug.grupo_id
            WHERE ug.id = %s;
        """, (membresia_id,))
        membresia = cur.fetchone()
        if not membresia:
            raise HTTPException(status_code=404, detail="Membresía no encontrada.")

        if not puede_gestionar_grupos(cur, data.usuario_solicitante_id,
                                      membresia["ambito"], membresia["comedor_id"]):
            raise HTTPException(status_code=403,
                            detail="Sin permiso para gestionar esta membresía.")

        if not data.estado_activo and membresia["usuario_id"] == data.usuario_solicitante_id:
            raise HTTPException(status_code=400,
                            detail="No puedes desactivar tu propia membresía.")

        if data.estado_activo:
            cur.execute("""
                UPDATE usuario_grupo
                SET estado_activo = TRUE, desactivado_por = NULL, fecha_desactivacion = NULL
                WHERE id = %s;
            """, (membresia_id,))
        else:
            cur.execute("""
                UPDATE usuario_grupo
                SET estado_activo = FALSE, desactivado_por = %s,
                    fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
                WHERE id = %s;
            """, (data.usuario_solicitante_id, membresia_id))
        db.commit()
        accion = "activada" if data.estado_activo else "desactivada"
        return {"message": f"Membresía {accion} exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al cambiar el estado: {e}")
    finally:
        cur.close()


# ==========================================
# ROLES TEMPORALES CON VIGENCIA (COM-23)
# ==========================================
@router.get("/roles-temporales")
def listar_roles_temporales(comedor_id: int = None, estado: str = None, db=Depends(get_db)):
    """
    Lista roles temporales con datos de usuario, comedor y rol.
    Aplica sweep perezoso: los vigentes con fecha_fin pasada pasan a EXPIRADO.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        expirar_roles_temporales(cur)
        db.commit()
        query = """
            SELECT rt.id, rt.usuario_id, rt.comedor_id, rt.rol_id, rt.otorgado_por,
                   rt.motivo, rt.fecha_inicio, rt.fecha_fin, rt.estado, rt.fecha_registro,
                   u.nombres, u.documento_identidad,
                   c.nombre AS comedor, r.nombre AS rol, g.nombre AS grupo
            FROM roles_temporales rt
            JOIN usuarios u ON u.id = rt.usuario_id
            JOIN comedores c ON c.id = rt.comedor_id
            JOIN roles_grupo r ON r.id = rt.rol_id
            JOIN grupos_usuario g ON g.id = r.grupo_id
            WHERE 1=1
        """
        params = []
        if comedor_id is not None:
            query += " AND rt.comedor_id = %s"
            params.append(comedor_id)
        if estado:
            query += " AND rt.estado = %s"
            params.append(estado.upper())
        query += " ORDER BY rt.fecha_inicio DESC;"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()


@router.post("/roles-temporales", status_code=201)
def otorgar_rol_temporal(data: RolTemporalInput, db=Depends(get_db)):
    """
    Otorga un rol de comedor por tiempo definido a un usuario con membresía activa
    en ese comedor (ej. el tesorero asume al presidente durante un viaje).
    Permiso: GESTION_USUARIOS_COMEDOR con cobertura del comedor.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not puede_gestionar_usuarios_comedor(cur, data.usuario_solicitante_id, data.comedor_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso sobre los usuarios de este comedor.")
        if not _existe_comedor(cur, data.comedor_id):
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        cur.execute("SELECT 1 FROM usuarios WHERE id = %s;", (data.usuario_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")

        # El rol debe pertenecer a un grupo de ámbito COMEDOR
        cur.execute("""
            SELECT r.id, r.nombre
            FROM roles_grupo r
            JOIN grupos_usuario g ON g.id = r.grupo_id
            WHERE r.id = %s AND g.ambito = 'COMEDOR';
        """, (data.rol_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=400,
                            detail="El rol debe pertenecer a un grupo de ámbito COMEDOR.")

        # El usuario destino debe tener membresía activa en el comedor
        cur.execute("""
            SELECT 1 FROM usuario_comedor
            WHERE usuario_id = %s AND comedor_id = %s AND estado_activo = TRUE;
        """, (data.usuario_id, data.comedor_id))
        if not cur.fetchone():
            raise HTTPException(status_code=400,
                            detail="El usuario no tiene membresía activa en este comedor.")

        # Validación de vigencia
        if not (data.fecha_fin > data.fecha_inicio):
            raise HTTPException(status_code=400,
                            detail="La fecha de fin debe ser posterior a la de inicio.")

        cur.execute("""
            INSERT INTO roles_temporales
            (usuario_id, comedor_id, rol_id, otorgado_por, motivo, fecha_inicio, fecha_fin, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'VIGENTE')
            RETURNING id;
        """, (data.usuario_id, data.comedor_id, data.rol_id, data.usuario_solicitante_id,
              data.motivo, data.fecha_inicio, data.fecha_fin))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id, "message": "Rol temporal otorgado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al otorgar el rol temporal: {e}")
    finally:
        cur.close()


@router.put("/roles-temporales/{rol_temporal_id}/revocar")
def revocar_rol_temporal(rol_temporal_id: int, data: RevocarRolTemporalInput, db=Depends(get_db)):
    """Revoca anticipadamente un rol temporal (estado -> REVOCADO)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM roles_temporales WHERE id = %s;", (rol_temporal_id,))
        registro = cur.fetchone()
        if not registro:
            raise HTTPException(status_code=404, detail="Rol temporal no encontrado.")
        if registro["estado"] != "VIGENTE":
            raise HTTPException(status_code=400,
                            detail=f"El rol temporal ya se encuentra {registro['estado'].lower()}.")
        if not puede_gestionar_usuarios_comedor(cur, data.usuario_solicitante_id, registro["comedor_id"]):
            raise HTTPException(status_code=403,
                            detail="Sin permiso sobre los usuarios de este comedor.")

        cur.execute("UPDATE roles_temporales SET estado = 'REVOCADO' WHERE id = %s;",
                    (rol_temporal_id,))
        db.commit()
        return {"message": "Rol temporal revocado exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al revocar el rol temporal: {e}")
    finally:
        cur.close()