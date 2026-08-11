"""
routers/parametros.py
Objetivo: Gestionar los parámetros dinámicos del sistema (Configuración global).
Uso: Registrado en main.py. Expone rutas como /parametros.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from database import get_db

router = APIRouter(prefix="/parametros", tags=["Parámetros"])

class ParametroUpdate(BaseModel):
    valor: str

@router.get("")
def get_parametros(categoria: str = None, db=Depends(get_db)):
    """Obtiene todos los parámetros o filtra por categoría. Devuelve un diccionario {clave: valor}"""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        query = "SELECT clave, valor, descripcion, categoria, tipo_dato FROM parametros_sistema"
        params = []
        if categoria:
            query += " WHERE categoria = %s"
            params.append(categoria.upper())
        
        cur.execute(query, params)
        registros = cur.fetchall()
        
        resultado = {}
        for r in registros:
            val = r['valor']
            if r['tipo_dato'] == 'INTEGER': val = int(val)
            elif r['tipo_dato'] == 'FLOAT': val = float(val)
            elif r['tipo_dato'] == 'BOOLEAN': val = val.lower() == 'true'
            resultado[r['clave']] = val
            
        return resultado
    finally:
        cur.close()

@router.put("/{clave}")
def update_parametro(clave: str, data: ParametroUpdate, db=Depends(get_db)):
    """Actualiza el valor de un parámetro específico."""
    cur = db.cursor()
    try:
        cur.execute(
            "UPDATE parametros_sistema SET valor = %s, fecha_actualizacion = CURRENT_TIMESTAMP WHERE clave = %s RETURNING clave;",
            (data.valor, clave)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Parámetro no encontrado")
        db.commit()
        return {"message": f"Parámetro {clave} actualizado exitosamente"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()