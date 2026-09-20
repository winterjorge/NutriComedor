"""
routers/grupos.py
Objetivo: Endpoints del ticket COM-22: catálogo de grupos y roles, asignación de
          usuarios a grupos con rol y alcance (global o por comedor), listado filtrado
          de membresías y activación/desactivación auditada.
Uso: Registrado en main.py con prefijo /api/v1.
Nota: Los grupos y roles base (Administrador de Sistemas, Administrativo,
      Directivo y Operativo) los siembra db_bootstrap; aquí solo se gestionan
      membresías, no se crean grupos nuevos (catálogo cerrado del negocio).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db
from schemas.grupo import AsignarGrupoInput, CambiarEstadoMembresiaInput
from permisos import puede_gestionar_grupos

router = APIRouter(prefix="/grupos", tags=["Grupos"])


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _existe_comedor(cur, comedor_id: int) -> bool:
    cur.execute("SELECT 1 FROM comedores WHERE id = %s;", (comedor_id,))
    return cur.fetchone() is not None


# ==========================================
# CATÁLOGO Y CONSULTAS
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
# GESTIÓN DE MEMBRESÍAS (COM-22)
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
        # Validaciones de catálogos
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

        # Reglas de alcance según ámbito del grupo
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

        # Permiso del solicitante según ámbito
        if not puede_gestionar_grupos(cur, data.usuario_solicitante_id, grupo["ambito"], comedor_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso para asignar membresías en este ámbito.")

        # Evitar duplicados exactos (usuario + rol + alcance)
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

        # Candado: nadie se desactiva a sí mismo
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