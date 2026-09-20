"""
routers/municipalidades.py
Objetivo: CRUD del registro nacional de municipalidades (módulo de gestión de usuarios):
          listar con filtros, crear, consultar y actualizar municipalidades, y listar
          los comedores vinculados a cada una.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos: crear/actualizar exige el privilegio GESTION_MUNICIPALIDADES (o admin de
          sistemas); listar y consultar son de lectura para usuarios autenticados.
Nota: Mientras no exista middleware JWT, el solicitante se identifica mediante
      `usuario_solicitante_id` en el payload (el frontend lo envía desde la sesión).
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db
from schemas.gestion_usuarios import MunicipalidadCreate, MunicipalidadUpdate
from permisos import puede_gestionar_municipalidades

router = APIRouter(prefix="/municipalidades", tags=["Municipalidades"])


# ==========================================
# HELPERS INTERNOS
# ==========================================
def _existe_municipalidad(cur, municipalidad_id: int) -> bool:
    cur.execute("SELECT 1 FROM municipalidades WHERE id = %s;", (municipalidad_id,))
    return cur.fetchone() is not None


def _validar_permiso_gestion(cur, usuario_id: int):
    """Solo quien posee el privilegio de gestión de municipalidades puede escribir."""
    if not puede_gestionar_municipalidades(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: se requiere el privilegio de Gestión de Municipalidades."
        )


# ==========================================
# ENDPOINTS DE LECTURA
# ==========================================
@router.get("")
def listar_municipalidades(departamento: str = None, provincia: str = None,
                           distrito: str = None, nombre: str = None,
                           db=Depends(get_db)):
    """Lista municipalidades con filtros opcionales (lectura para autenticados)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = "SELECT * FROM municipalidades WHERE 1=1"
        params = []
        if departamento:
            query += " AND departamento ILIKE %s"
            params.append(departamento)
        if provincia:
            query += " AND provincia ILIKE %s"
            params.append(provincia)
        if distrito:
            query += " AND distrito ILIKE %s"
            params.append(distrito)
        if nombre:
            query += " AND nombre ILIKE %s"
            params.append(f"%{nombre}%")
        query += " ORDER BY departamento, provincia, distrito, nombre;"
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()


@router.get("/{municipalidad_id}")
def obtener_municipalidad(municipalidad_id: int, db=Depends(get_db)):
    """Detalle de una municipalidad por id."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM municipalidades WHERE id = %s;", (municipalidad_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Municipalidad no encontrada.")
        return row
    finally:
        cur.close()


@router.get("/{municipalidad_id}/comedores")
def comedores_de_municipalidad(municipalidad_id: int, db=Depends(get_db)):
    """Comedores vinculados a la municipalidad (vínculo opcional comedores.municipalidad_id)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_municipalidad(cur, municipalidad_id):
            raise HTTPException(status_code=404, detail="Municipalidad no encontrada.")
        cur.execute("""
            SELECT id, nombre, departamento, ciudad, distrito, zona, estado_activo
            FROM comedores
            WHERE municipalidad_id = %s
            ORDER BY nombre;
        """, (municipalidad_id,))
        return cur.fetchall()
    finally:
        cur.close()


# ==========================================
# ENDPOINTS DE ESCRITURA (privilegio requerido)
# ==========================================
@router.post("", status_code=201)
def crear_municipalidad(data: MunicipalidadCreate, db=Depends(get_db)):
    """Crea una municipalidad en el registro nacional."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_permiso_gestion(cur, data.usuario_solicitante_id)
        cur.execute("""
            INSERT INTO municipalidades
            (departamento, provincia, distrito, nombre, direccion, link_ubicacion)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (data.departamento, data.provincia, data.distrito, data.nombre,
              data.direccion, data.link_ubicacion))
        nuevo_id = cur.fetchone()["id"]
        db.commit()
        return {"id": nuevo_id, "message": "Municipalidad creada exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400,
                            detail="Ya existe una municipalidad con esa ubicación y nombre.")
        raise HTTPException(status_code=400, detail=f"Error al crear la municipalidad: {e}")
    finally:
        cur.close()


@router.put("/{municipalidad_id}")
def actualizar_municipalidad(municipalidad_id: int, data: MunicipalidadUpdate,
                             db=Depends(get_db)):
    """Actualización parcial de municipalidad (solo campos enviados)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_municipalidad(cur, municipalidad_id):
            raise HTTPException(status_code=404, detail="Municipalidad no encontrada.")
        _validar_permiso_gestion(cur, data.usuario_solicitante_id)

        # Construir SET dinámico solo con los campos enviados (excluye al solicitante)
        campos = {k: v for k, v in data.dict(exclude_unset=True).items()
                  if k != "usuario_solicitante_id" and v is not None}
        if not campos:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar.")
        sets = ", ".join([f"{k} = %s" for k in campos.keys()])
        cur.execute(f"UPDATE municipalidades SET {sets} WHERE id = %s RETURNING id;",
                    list(campos.values()) + [municipalidad_id])
        db.commit()
        return {"message": "Municipalidad actualizada exitosamente."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower():
            raise HTTPException(status_code=400,
                            detail="Ya existe una municipalidad con esa ubicación y nombre.")
        raise HTTPException(status_code=400, detail=f"Error al actualizar la municipalidad: {e}")
    finally:
        cur.close()