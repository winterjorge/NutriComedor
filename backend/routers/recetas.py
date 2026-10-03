"""
routers/recetas.py
Objetivo: Endpoints del CRUD de recetas, sus ingredientes (ahora por componente, COM-48)
          y evaluación de costos.
Uso: Registrado en main.py con prefijo /api/v1.
Historial:
 - Sprint 1/2: versión original.
 - COM-45: CREATE/UPDATE persisten raciones; orden por raciones; artefactos corregidos.
 - COM-48 (este archivo): esquema multi-componente:
     * GET /recetas/componentes: catálogo activo de componentes (orden de exhibición).
     * POST /recetas/{id}/ingredientes exige componente_id y el ON CONFLICT usa la
       nueva unicidad (receta, ingrediente, componente, unidad).
     * GET /recetas/{id} devuelve cada línea con componente_id y componente_nombre.
     * DELETE /recetas/{id}/ingredientes (nuevo): limpia TODAS las líneas de la receta
       para la sincronización de edición del modal (con componentes, un ingrediente
       puede tener varias filas y borrarlo por id las perdería todas).
     * El DELETE por ingrediente_id se conserva COMENTADO su alcance anterior: ahora
       elimina las filas del ingrediente en TODOS los componentes de la receta.
   Los motores (optimizador/K-means/Greedy) no cambian: suman filas independientes.
"""
from datetime import date

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor

from database import get_db
from schemas.receta import RecetaInput, IngredienteRecetaInput, RecetaUpdate, RecetaListResponse, RecetaResponse
from optimizador import calcular_costo_receta
from typing import Optional

router = APIRouter(prefix="/recetas", tags=["Recetas"])


@router.get("/con-costo")
def get_recetas_con_costo(fecha: str = None, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, nombre, descripcion, raciones, energia_kcal, proteina_g, hierro_mg FROM recetas_almuerzo ORDER BY nombre;")
        recetas = cur.fetchall()
        fecha_calc = fecha or date.today().isoformat()
        recetas_con_costo = []
        for receta in recetas:
            try:
                resultado = calcular_costo_receta(receta['id'], fecha_calc)
                recetas_con_costo.append({**receta, 'costo_racion': resultado.get('costo_total_racion', 0.0)})
            except Exception:
                recetas_con_costo.append({**receta, 'costo_racion': 0.0})
        return recetas_con_costo
    finally:
        cur.close()


# COM-48: catálogo de componentes. Declarado ANTES de /{receta_id} para que la ruta
# literal gane el match (mismo patrón que /con-costo).
@router.get("/componentes")
def get_componentes_receta(db=Depends(get_db)):
    """COM-48: componentes activos de una receta (Ensalada, Plato de fondo, Refresco,
    Fruta y futuros como Sopa), ordenados para exhibición."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, nombre, descripcion, orden
            FROM recetas_componentes
            WHERE estado_activo = TRUE
            ORDER BY orden, id;
        """)
        return cur.fetchall()
    finally:
        cur.close()


@router.get("", response_model=RecetaListResponse)
def get_recetas(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    sort_by: str = Query("nombre"),
    sort_order: str = Query("asc"),
    search: Optional[str] = Query(None),
    db=Depends(get_db)
):
    """Obtiene recetas con paginación y ordenamiento"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # COM-45: 'raciones' ordenable
        allowed_sorts = ['nombre', 'energia_kcal', 'proteina_g', 'hierro_mg', 'vitamina_a_ug', 'zinc_mg', 'carbohidratos_g', 'fecha_creacion', 'raciones']
        if sort_by not in allowed_sorts:
            sort_by = 'nombre'
        order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"
        where_clause = "WHERE 1=1"
        params = []
        if search:
            where_clause += " AND nombre ILIKE %s"
            params.append(f"%{search}%")
        cur.execute(f"SELECT COUNT(*) as total FROM recetas_almuerzo {where_clause}", params)
        total = cur.fetchone()['total']
        offset = (page - 1) * per_page
        query = f"""
            SELECT * FROM recetas_almuerzo 
            {where_clause} 
            ORDER BY {sort_by} {order_dir} 
            LIMIT %s OFFSET %s
        """
        params.extend([per_page, offset])
        cur.execute(query, params)
        recetas = cur.fetchall()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        return RecetaListResponse(
            recetas=recetas,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
    finally:
        cur.close()


@router.get("/{receta_id}")
def get_receta_detalle(receta_id: int, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM recetas_almuerzo WHERE id = %s;", (receta_id,))
        receta = cur.fetchone()
        if not receta:
            raise HTTPException(status_code=404, detail="Receta no encontrada")
        # COM-48 (trazabilidad): consulta anterior sin componente, comentada:
        # cur.execute("""
        #     SELECT ri.*, i.nombre as ingrediente_nombre, um.nombre as unidad_nombre, um.abreviatura as unidad_abrev
        #     FROM receta_ingrediente ri
        #     JOIN ingredientes i ON ri.ingrediente_id = i.id
        #     JOIN unidades_medida um ON ri.unidad_medida_id = um.id
        #     WHERE ri.receta_id = %s;
        # """, (receta_id,))
        # COM-48: cada línea con su componente (nombre y orden) para el modal de edición
        cur.execute("""
            SELECT ri.*, i.nombre as ingrediente_nombre,
                   um.nombre as unidad_nombre, um.abreviatura as unidad_abrev,
                   rc.nombre as componente_nombre, rc.orden as componente_orden
            FROM receta_ingrediente ri
            JOIN ingredientes i ON ri.ingrediente_id = i.id
            JOIN unidades_medida um ON ri.unidad_medida_id = um.id
            JOIN recetas_componentes rc ON ri.componente_id = rc.id
            WHERE ri.receta_id = %s
            ORDER BY rc.orden, rc.id, i.nombre;
        """, (receta_id,))
        return {"receta": receta, "ingredientes": cur.fetchall()}
    finally:
        cur.close()


@router.post("", status_code=201)
def create_receta(data: RecetaInput, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # COM-45: se persiste raciones (validado >0 por Pydantic)
        cur.execute("""
            INSERT INTO recetas_almuerzo
            (nombre, descripcion, raciones, hierro_mg, proteina_g, energia_kcal, vitamina_a_ug, zinc_mg, carbohidratos_g)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            data.nombre, data.descripcion, data.raciones, data.hierro_mg, data.proteina_g,
            data.energia_kcal, data.vitamina_a_ug, data.zinc_mg, data.carbohidratos_g
        ))
        receta_id = cur.fetchone()['id']
        db.commit()
        return {"id": receta_id, "message": "Receta creada exitosamente"}
    except psycopg2.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una receta con ese nombre.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()


@router.put("/{receta_id}")
def update_receta(receta_id: int, data: RecetaUpdate, db=Depends(get_db)):
    """Actualiza una receta existente (COM-45: raciones con COALESCE)"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            UPDATE recetas_almuerzo
            SET nombre = %s, descripcion = %s, raciones = COALESCE(%s, raciones),
                hierro_mg = %s, proteina_g = %s,
                energia_kcal = %s, vitamina_a_ug = %s, zinc_mg = %s, carbohidratos_g = %s
            WHERE id = %s
            RETURNING id;
        """, (
            data.nombre, data.descripcion, data.raciones, data.hierro_mg, data.proteina_g,
            data.energia_kcal, data.vitamina_a_ug, data.zinc_mg, data.carbohidratos_g,
            receta_id
        ))
        updated = cur.fetchone()
        if not updated:
            db.rollback()
            raise HTTPException(status_code=404, detail="Receta no encontrada")
        db.commit()
        return {"message": "Receta actualizada exitosamente"}
    finally:
        cur.close()


@router.delete("/{receta_id}")
def delete_receta(receta_id: int, db=Depends(get_db)):
    """Elimina una receta"""
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM recetas_almuerzo WHERE id = %s RETURNING id;", (receta_id,))
        deleted = cur.fetchone()
        if not deleted:
            db.rollback()
            raise HTTPException(status_code=404, detail="Receta no encontrada")
        db.commit()
        return {"message": "Receta eliminada exitosamente"}
    finally:
        cur.close()


@router.post("/{receta_id}/ingredientes")
def add_ingrediente_a_receta(receta_id: int, data: IngredienteRecetaInput, db=Depends(get_db)):
    """
    COM-48: agrega (o actualiza) una línea ingrediente-componente-cantidad. El mismo
    ingrediente puede registrarse en componentes distintos con cantidades independientes;
    el ON CONFLICT aplica a la unicidad (receta, ingrediente, componente, unidad).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        for q, p in [
            ("SELECT id FROM recetas_almuerzo WHERE id = %s;", (receta_id,)),
            ("SELECT id FROM ingredientes WHERE id = %s;", (data.ingrediente_id,)),
            ("SELECT id FROM unidades_medida WHERE id = %s;", (data.unidad_medida_id,)),
            # COM-48: el componente debe existir y estar activo
            ("SELECT id FROM recetas_componentes WHERE id = %s AND estado_activo = TRUE;", (data.componente_id,))
        ]:
            cur.execute(q, p)
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Entidad relacionada no encontrada")
        # COM-48 (trazabilidad): INSERT anterior sin componente_id, comentado:
        # cur.execute("""
        #     INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida)
        #     VALUES (%s, %s, %s, %s)
        #     ON CONFLICT (receta_id, ingrediente_id, unidad_medida_id)
        #     DO UPDATE SET cantidad_requerida = EXCLUDED.cantidad_requerida
        #     RETURNING *;
        # """, (receta_id, data.ingrediente_id, data.unidad_medida_id, data.cantidad_requerida))
        cur.execute("""
            INSERT INTO receta_ingrediente (receta_id, ingrediente_id, componente_id, unidad_medida_id, cantidad_requerida)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (receta_id, ingrediente_id, componente_id, unidad_medida_id)
            DO UPDATE SET cantidad_requerida = EXCLUDED.cantidad_requerida
            RETURNING *;
        """, (receta_id, data.ingrediente_id, data.componente_id, data.unidad_medida_id, data.cantidad_requerida))
        db.commit()
        return cur.fetchone()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()


# COM-48: limpieza total de líneas de una receta (sincronización de edición del modal).
# Con componentes, un ingrediente puede tener varias filas; editar = limpiar y regrabar.
@router.delete("/{receta_id}/ingredientes")
def delete_ingredientes_de_receta(receta_id: int, db=Depends(get_db)):
    """COM-48: elimina TODAS las líneas de ingredientes de la receta (usada al editar)."""
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM receta_ingrediente WHERE receta_id = %s;", (receta_id,))
        db.commit()
        return {"message": "Ingredientes de la receta eliminados exitosamente"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()


@router.delete("/{receta_id}/ingredientes/{ingrediente_id}")
def delete_ingrediente_de_receta(receta_id: int, ingrediente_id: int, db=Depends(get_db)):
    """
    COM-48 (trazabilidad): se conserva el endpoint, pero su alcance cambia: elimina las
    filas del ingrediente en TODOS los componentes de la receta. Para borrar una sola
    fila use la sincronización de edición (DELETE /{receta_id}/ingredientes + re-grabado).
    """
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM receta_ingrediente WHERE receta_id = %s AND ingrediente_id = %s;", (receta_id, ingrediente_id))
        db.commit()
        return {"message": "Ingrediente eliminado exitosamente"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()


@router.get("/{receta_id}/costo")
def get_costo_receta(receta_id: int, fecha: str):
    resultado = calcular_costo_receta(receta_id, fecha)
    if "error" in resultado:
        raise HTTPException(status_code=400, detail=resultado["error"])
    return resultado