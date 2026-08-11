"""
routers/ingredientes.py
Objetivo: Contener la lógica de los endpoints para consultar unidades de medida, ingredientes y su histórico de precios.
Uso: Registrado en main.py con prefijo /api/v1. Expone rutas como /ingredientes, /unidades-medida.
"""
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
from database import get_db

router = APIRouter(tags=["Ingredientes"])

@router.get("/unidades-medida")
def get_unidades_medida(db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try: cur.execute("SELECT id, nombre, abreviatura FROM unidades_medida ORDER BY nombre;"); return cur.fetchall()
    finally: cur.close()

@router.get("/ingredientes-disponibles")
def get_ingredientes_disponibles(db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try: cur.execute("""SELECT DISTINCT i.id, i.nombre, cat.nombre as categoria FROM ingredientes i LEFT JOIN categorias_alimentos cat ON i.categoria_id = cat.id ORDER BY i.nombre;"""); return cur.fetchall()
    finally: cur.close()

@router.get("/ingredientes")
def get_ingredientes_por_fecha(fecha: str, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""SELECT ins.id, ins.nombre, COALESCE(cat.nombre, 'Sin clasificar') as categoria, hp.precio_prom as precio, COALESCE(um.abreviatura, 'kg') as unidad
            FROM historial_precios hp JOIN insumos ins ON hp.insumo_id = ins.id LEFT JOIN ingredientes ing ON ins.ingrediente_id = ing.id LEFT JOIN categorias_alimentos cat ON ing.categoria_id = cat.id LEFT JOIN unidades_medida um ON ins.unidad_medida_id = um.id WHERE hp.fecha = %s ORDER BY ins.nombre;""", (fecha,))
        return cur.fetchall()
    finally: cur.close()

@router.get("/ingredientes/{insumo_id}/historico")
def get_historico_precios(insumo_id: int, rango: str = '1w', db=Depends(get_db)):
    dias = 7 if rango == '1w' else 30 if rango == '1m' else 180 if rango == '6m' else 365
    cur = db.cursor(cursor_factory=RealDictCursor)
    try: cur.execute(f"SELECT TO_CHAR(fecha, 'DD/MM') as label, precio_prom as precio FROM historial_precios WHERE insumo_id = %s AND fecha >= CURRENT_DATE - INTERVAL '{dias} days' ORDER BY fecha ASC;", (insumo_id,)); return cur.fetchall()
    finally: cur.close()