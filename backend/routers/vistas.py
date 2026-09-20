"""
routers/vistas.py
Objetivo: Endpoints del módulo de permisos por vistas (diferenciación de módulos
          permitidos por grupo/rol): catálogo de módulos del sistema, matriz completa
          de permisos para el editor, reemplazo de módulos por rol (exclusivo del
          administrador de sistemas) y consulta de los módulos efectivos del usuario
          según sus membresías activas y roles temporales vigentes.
Uso: Registrado en main.py con prefijo /api/v1.
Nota: Mientras no exista middleware JWT, el solicitante se identifica mediante
      `usuario_solicitante_id` en el payload (el frontend lo envía desde la sesión).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db
from schemas.vistas import PermisosRolUpdate
from permisos import es_admin_sistema

router = APIRouter(prefix="/vistas", tags=["Permisos por Vistas"])


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _existe_rol(cur, rol_id: int) -> bool:
    cur.execute("SELECT 1 FROM roles_grupo WHERE id = %s;", (rol_id,))
    return cur.fetchone() is not None


# ==========================================
# CATÁLOGO DE MÓDULOS
# ==========================================
@router.get("/modulos")
def listar_modulos(db=Depends(get_db)):
    """Catálogo de módulos del sistema (vistas/pestañas) ordenado por `orden`."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, clave, nombre, descripcion, orden
            FROM modulos_sistema
            ORDER BY orden, id;
        """)
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# MATRIZ DE PERMISOS (editor Vistas)
# ==========================================
@router.get("/permisos")
def matriz_permisos(db=Depends(get_db)):
    """
    Matriz completa grupo -> rol -> módulos asignados para el editor de la
    sub-pestaña Vistas (solo el administrador de sistemas la modifica).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT g.id AS grupo_id, g.nombre AS grupo, g.ambito,
                   r.id AS rol_id, r.nombre AS rol
            FROM grupos_usuario g
            JOIN roles_grupo r ON r.grupo_id = g.id
            ORDER BY g.id, r.id;
        """)
        filas = cur.fetchall()

        cur.execute("SELECT rol_id, modulo_id FROM roles_modulos;")
        asignaciones = cur.fetchall()

        cur.execute("SELECT id, clave FROM modulos_sistema;")
        modulos = {m["id"]: m["clave"] for m in cur.fetchall()}

        # Agrupar roles por grupo con sus módulos asignados (claves)
        grupos = {}
        for f in filas:
            if f["grupo_id"] not in grupos:
                grupos[f["grupo_id"]] = {
                    "grupo_id": f["grupo_id"],
                    "grupo": f["grupo"],
                    "ambito": f["ambito"],
                    "roles": []
                }
            grupos[f["grupo_id"]]["roles"].append({
                "rol_id": f["rol_id"],
                "rol": f["rol"],
                "modulos": [
                    modulos[a["modulo_id"]]
                    for a in asignaciones
                    if a["rol_id"] == f["rol_id"] and a["modulo_id"] in modulos
                ]
            })
        return list(grupos.values())
    finally:
        cur.close()


@router.put("/permisos/{rol_id}")
def actualizar_permisos_rol(rol_id: int, data: PermisosRolUpdate, db=Depends(get_db)):
    """
    Reemplaza el conjunto de módulos permitidos de un rol por la lista enviada.
    Regla COM-25: exclusivo del administrador de sistemas. Lista vacía deja al rol
    sin módulos asignados.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not es_admin_sistema(cur, data.usuario_solicitante_id):
            raise HTTPException(status_code=403,
                            detail="Sin permiso: solo el Administrador de Sistemas puede editar los permisos por vistas.")
        if not _existe_rol(cur, rol_id):
            raise HTTPException(status_code=404, detail="Rol no encontrado.")

        # Validar que todos los módulos enviados existan
        if data.modulo_ids:
            cur.execute("SELECT COUNT(*) AS n FROM modulos_sistema WHERE id = ANY(%s);",
                        (data.modulo_ids,))
            if cur.fetchone()["n"] != len(data.modulo_ids):
                raise HTTPException(status_code=400, detail="Uno o más módulos enviados no existen.")

        # Reemplazo atómico de la asignación del rol
        cur.execute("DELETE FROM roles_modulos WHERE rol_id = %s;", (rol_id,))
        for modulo_id in data.modulo_ids:
            cur.execute("""
                INSERT INTO roles_modulos (rol_id, modulo_id)
                VALUES (%s, %s)
                ON CONFLICT (rol_id, modulo_id) DO NOTHING;
            """, (rol_id, modulo_id))
        db.commit()
        return {"message": "Permisos del rol actualizados exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al actualizar los permisos: {e}")
    finally:
        cur.close()


# ==========================================
# MÓDULOS EFECTIVOS DEL USUARIO
# ==========================================
@router.get("/mis-modulos")
def mis_modulos(usuario_id: int, db=Depends(get_db)):
    """
    Módulos efectivos del usuario: unión de los módulos de sus roles por membresías
    activas (usuario_grupo) y por roles temporales vigentes (dentro de su ventana
    fecha_inicio/fecha_fin y estado VIGENTE). El frontend usa esta lista para
    renderizar solo las pestañas/sub-pestañas permitidas.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT DISTINCT m.clave
            FROM (
                SELECT ug.rol_id
                FROM usuario_grupo ug
                WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
                UNION
                SELECT rt.rol_id
                FROM roles_temporales rt
                WHERE rt.usuario_id = %s AND rt.estado = 'VIGENTE'
                  AND CURRENT_TIMESTAMP BETWEEN rt.fecha_inicio AND rt.fecha_fin
            ) rm
            JOIN roles_modulos rmod ON rmod.rol_id = rm.rol_id
            JOIN modulos_sistema m ON m.id = rmod.modulo_id
            ORDER BY m.clave;
        """, (usuario_id, usuario_id))
        return {"modulos": [f["clave"] for f in cur.fetchall()]}
    finally:
        cur.close()