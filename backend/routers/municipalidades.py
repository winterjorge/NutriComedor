"""
routers/municipalidades.py
Objetivo: CRUD del registro nacional de municipalidades. COM-27: la creación y edición
          persisten los FK de ubicación geográfica (departamento_id, provincia_id,
          distrito_id) y derivan automáticamente el ubigeo_id y los campos de texto,
          usando el catálogo geográfico como fuente única de verdad.
Uso: Registrado en main.py con prefijo /api/v1.
Permisos: crear/actualizar exige el privilegio GESTION_MUNICIPALIDADES (o admin de sistemas).
Referencia: tickets COM-23 (municipalidades) y COM-27 (FK de ubicación geográfica).
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


def _resolver_ubicacion(cur, departamento_id, provincia_id, distrito_id):
    """
    COM-27: Resuelve los nombres de texto y el ubigeo_id a partir de los FK de ubicación,
    validando la coherencia jerárquica (provincia->departamento, distrito->provincia).
    Retorna (departamento_nombre, provincia_nombre, distrito_nombre, ubigeo_id).
    """
    cur.execute("SELECT nombre FROM departamentos WHERE id = %s;", (departamento_id,))
    dep = cur.fetchone()
    if not dep:
        raise HTTPException(status_code=400, detail="El departamento indicado no existe.")

    cur.execute("SELECT nombre FROM provincias WHERE id = %s AND departamento_id = %s;",
                (provincia_id, departamento_id))
    prov = cur.fetchone()
    if not prov:
        raise HTTPException(status_code=400,
                        detail="La provincia no existe o no corresponde al departamento seleccionado.")

    cur.execute("SELECT nombre FROM distritos WHERE id = %s AND provincia_id = %s;",
                (distrito_id, provincia_id))
    dist = cur.fetchone()
    if not dist:
        raise HTTPException(status_code=400,
                        detail="El distrito no existe o no corresponde a la provincia seleccionada.")

    # El ubigeo se deriva del distrito (relación 1 a 1)
    cur.execute("SELECT id FROM ubigeos WHERE distrito_id = %s;", (distrito_id,))
    ubi = cur.fetchone()
    ubigeo_id = ubi["id"] if ubi else None

    return dep["nombre"], prov["nombre"], dist["nombre"], ubigeo_id


# ==========================================
# ENDPOINTS DE LECTURA
# ==========================================
@router.get("")
def listar_municipalidades(departamento_id: int = None, provincia_id: int = None,
                           distrito_id: int = None, nombre: str = None,
                           db=Depends(get_db)):
    """Lista municipalidades con filtros opcionales (por FK de ubicación o nombre)."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = "SELECT * FROM municipalidades WHERE 1=1"
        params = []
        # COM-27: filtros por FK de ubicación geográfica
        if departamento_id:
            query += " AND departamento_id = %s"
            params.append(departamento_id)
        if provincia_id:
            query += " AND provincia_id = %s"
            params.append(provincia_id)
        if distrito_id:
            query += " AND distrito_id = %s"
            params.append(distrito_id)
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
    """Comedores vinculados a la municipalidad."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_municipalidad(cur, municipalidad_id):
            raise HTTPException(status_code=404, detail="Municipalidad no encontrada.")
        cur.execute("""
            SELECT id, nombre, zona, direccion
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
    """
    Crea una municipalidad. COM-27: requiere los FK de ubicación (departamento_id,
    provincia_id, distrito_id); el backend valida la jerarquía, deriva el ubigeo_id
    y pobla los campos de texto desde el catálogo geográfico.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_permiso_gestion(cur, data.usuario_solicitante_id)

        # COM-27: los FK de ubicación son obligatorios en la creación
        if not data.departamento_id or not data.provincia_id or not data.distrito_id:
            raise HTTPException(status_code=400,
                            detail="Debe seleccionar la ubicación geográfica completa (departamento, provincia y distrito).")

        # COM-27: resolver nombres de texto y ubigeo_id desde los FK
        dep_nombre, prov_nombre, dist_nombre, ubigeo_id = _resolver_ubicacion(
            cur, data.departamento_id, data.provincia_id, data.distrito_id)

        cur.execute("""
            INSERT INTO municipalidades
            (departamento, provincia, distrito, nombre, direccion, link_ubicacion,
             departamento_id, provincia_id, distrito_id, ubigeo_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (dep_nombre, prov_nombre, dist_nombre, data.nombre,
              data.direccion, data.link_ubicacion,
              data.departamento_id, data.provincia_id, data.distrito_id, ubigeo_id))
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
    """
    Actualización parcial de municipalidad. COM-27: si se envían FK de ubicación, se
    revalida la jerarquía y se rederivan el ubigeo_id y los campos de texto.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if not _existe_municipalidad(cur, municipalidad_id):
            raise HTTPException(status_code=404, detail="Municipalidad no encontrada.")
        _validar_permiso_gestion(cur, data.usuario_solicitante_id)

        campos = {k: v for k, v in data.dict(exclude_unset=True).items()
                  if k != "usuario_solicitante_id"}
        if not campos:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar.")

        # COM-27: si cambió la ubicación, revalidar jerarquía y rederivar texto/ubigeo
        if any(k in campos for k in ("departamento_id", "provincia_id", "distrito_id")):
            # Completar con los valores actuales los FK que no se enviaron
            cur.execute("""
                SELECT departamento_id, provincia_id, distrito_id
                FROM municipalidades WHERE id = %s;
            """, (municipalidad_id,))
            actual = cur.fetchone()
            dep_id = campos.get("departamento_id", actual["departamento_id"])
            prov_id = campos.get("provincia_id", actual["provincia_id"])
            dist_id = campos.get("distrito_id", actual["distrito_id"])

            if not dep_id or not prov_id or not dist_id:
                raise HTTPException(status_code=400,
                                detail="La ubicación geográfica no puede quedar incompleta.")

            dep_nombre, prov_nombre, dist_nombre, ubigeo_id = _resolver_ubicacion(
                cur, dep_id, prov_id, dist_id)

            campos["departamento_id"] = dep_id
            campos["provincia_id"] = prov_id
            campos["distrito_id"] = dist_id
            campos["ubigeo_id"] = ubigeo_id
            # Mantener coherentes los campos de texto legacy
            campos["departamento"] = dep_nombre
            campos["provincia"] = prov_nombre
            campos["distrito"] = dist_nombre

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