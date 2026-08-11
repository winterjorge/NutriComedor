"""
routers/recetas.py
Objetivo: Contener la lógica de los endpoints para el CRUD de recetas, sus ingredientes y evaluación de costos.
Uso: Registrado en main.py con prefijo /api/v1. Expone rutas como /recetas, /recetas/{id}/costo.
"""
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
        cur.execute("SELECT id, nombre, descripcion, energia_kcal, proteina_g, hierro_mg FROM recetas_almuerzo ORDER BY nombre;")
        recetas = cur.fetchall()
        fecha_calc = fecha or __import__('datetime').date.today().isoformat()
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
        # Validar columnas de ordenamiento permitidas
        allowed_sorts = ['nombre', 'energia_kcal', 'proteina_g', 'hierro_mg', 'vitamina_a_ug', 'zinc_mg', 'carbohidratos_g', 'fecha_creacion']
        if sort_by not in allowed_sorts:
            sort_by = 'nombre'
        
        order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"
        
        # Construir WHERE clause
        where_clause = "WHERE 1=1"
        params = []
        
        if search:
            where_clause += " AND nombre ILIKE %s"
            params.append(f"%{search}%")
        
        # Contar total
        cur.execute(f"SELECT COUNT(*) as total FROM recetas_almuerzo {where_clause}", params)
        total = cur.fetchone()['total']
        
        # Obtener datos paginados
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
        cur.execute("""
            SELECT ri.*, i.nombre as ingrediente_nombre, um.nombre as unidad_nombre, um.abreviatura as unidad_abrev
            FROM receta_ingrediente ri
            JOIN ingredientes i ON ri.ingrediente_id = i.id
            JOIN unidades_medida um ON ri.unidad_medida_id = um.id
            WHERE ri.receta_id = %s;
        """, (receta_id,))
        return {"receta": receta, "ingredientes": cur.fetchall()}
    finally:
        cur.close()

@router.post("", status_code=201)
def create_receta(data: RecetaInput, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO recetas_almuerzo 
            (nombre, descripcion, hierro_mg, proteina_g, energia_kcal, vitamina_a_ug, zinc_mg, carbohidratos_g)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            data.nombre, data.descripcion, data.hierro_mg, data.proteina_g,
            data.energia_kcal, data.vitamina_a_ug, data.zinc_mg, data.carbohidratos_g
        ))
        receta_id = cur.fetchone()['id']
        db.commit()
        return {"id": receta_id, "message": "Receta creada exitosamente"}
    except __import__('psycopg2').IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe una receta con ese nombre.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()

@router.put("/{receta_id}")
def update_receta(receta_id: int, data: RecetaUpdate, db=Depends(get_db)):
    """Actualiza una receta existente"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            UPDATE recetas_almuerzo 
            SET nombre = %s, descripcion = %s, hierro_mg = %s, proteina_g = %s,
                energia_kcal = %s, vitamina_a_ug = %s, zinc_mg = %s, carbohidratos_g = %s
            WHERE id = %s
            RETURNING id;
        """, (
            data.nombre, data.descripcion, data.hierro_mg, data.proteina_g,
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
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        for q, p in [
            ("SELECT id FROM recetas_almuerzo WHERE id = %s;", (receta_id,)),
            ("SELECT id FROM ingredientes WHERE id = %s;", (data.ingrediente_id,)),
            ("SELECT id FROM unidades_medida WHERE id = %s;", (data.unidad_medida_id,))
        ]:
            cur.execute(q, p)
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Entidad relacionada no encontrada")
        
        cur.execute("""
            INSERT INTO receta_ingrediente (receta_id, ingrediente_id, unidad_medida_id, cantidad_requerida)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (receta_id, ingrediente_id, unidad_medida_id) 
            DO UPDATE SET cantidad_requerida = EXCLUDED.cantidad_requerida
            RETURNING *;
        """, (receta_id, data.ingrediente_id, data.unidad_medida_id, data.cantidad_requerida))
        db.commit()
        return cur.fetchone()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()

@router.delete("/{receta_id}/ingredientes/{ingrediente_id}")
def delete_ingrediente_de_receta(receta_id: int, ingrediente_id: int, db=Depends(get_db)):
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