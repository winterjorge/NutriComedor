"""
routers/padron.py
Objetivo: Contener la lógica de los endpoints para la gestión del padrón, ventas diarias (POS) y predicción de demanda.
Uso: Registrado en main.py con prefijo /api/v1. Expone rutas como /padron/hoy, /comensales/registrar.
"""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor
import psycopg2

from database import get_db, get_parametros_dict
from schemas.comensal import NuevoComensalInput, RegistroVentaInput, ModificarVentaInput
from ai_engine import predecir_demanda_raciones

router = APIRouter(tags=["Padrón y POS"])

@router.get("/padron/prediccion_demanda")
def predecir_demanda_diaria(fecha_str: str = None, db=Depends(get_db)):
    """
    Predice la demanda diaria. 
    Ahora lee los umbrales mínimos y de fin de semana desde la tabla parametros_sistema.
    """
    fecha_eval = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
    
    # 1. Leer parámetros de IA desde la BD de forma centralizada
    claves_ia = [
        'IA_MIN_SOCIAL', 'IA_MIN_AFILIADO', 'IA_MIN_NORMAL',
        'IA_FINDE_SOCIAL', 'IA_FINDE_AFILIADO', 'IA_FINDE_NORMAL'
    ]
    params = get_parametros_dict(db, claves_ia)
    
    # 2. Estructurar diccionarios para el motor de IA
    limites_minimos = {
        'SOCIAL': params.get('IA_MIN_SOCIAL', 15),
        'AFILIADO': params.get('IA_MIN_AFILIADO', 35),
        'NORMAL': params.get('IA_MIN_NORMAL', 80)
    }
    limites_finde = {
        'SOCIAL': params.get('IA_FINDE_SOCIAL', 10),
        'AFILIADO': params.get('IA_FINDE_AFILIADO', 20),
        'NORMAL': params.get('IA_FINDE_NORMAL', 30)
    }
    
    # 3. Ejecutar predicción inyectando los parámetros
    pred = predecir_demanda_raciones(
        fecha_eval.weekday(), 
        fecha_eval.day, 
        limites_minimos, 
        limites_finde
    )
    
    return {
        "fecha": fecha_eval.strftime("%Y-%m-%d"), 
        "prediccion_social": pred[0], 
        "prediccion_afiliado": pred[1], 
        "prediccion_normal": pred[2], 
        "total_raciones_sugeridas": sum(pred)
    }

@router.get("/comensales/{documento}")
def buscar_comensal(documento: str, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM comensales WHERE documento_identidad = %s;", (documento,))
        res = cur.fetchone()
        if not res: 
            raise HTTPException(status_code=404, detail="Comensal no encontrado")
        return res
    finally: 
        cur.close()

@router.post("/comensales/registrar")
def registrar_comensal_manual(data: NuevoComensalInput, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "INSERT INTO comensales (tipo_documento, documento_identidad, nombres, tipo_comensal) VALUES (%s, %s, %s, %s) RETURNING *;", 
            (data.tipo_documento, data.documento_identidad, data.nombres, data.tipo_comensal)
        )
        db.commit()
        return cur.fetchone()
    except psycopg2.IntegrityError: 
        raise HTTPException(status_code=400, detail="Documento ya registrado.")
    except Exception as e: 
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally: 
        cur.close()

@router.post("/padron")
def registrar_venta_padron(data: RegistroVentaInput, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Validar que raciones sea al menos 1
        if data.raciones < 1:
            raise HTTPException(status_code=400, detail="Las raciones deben ser al menos 1")
            
        cur.execute(
            """INSERT INTO padron_diario (comensal_id, fecha, raciones, monto_pagado, tipo_menu, tipo_comensal_venta, observacion) 
               VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s) RETURNING *;""", 
            (data.comensal_id, data.raciones, data.monto_pagado, data.tipo_menu, data.tipo_comensal_venta, data.observacion)
        )
        db.commit()
        return cur.fetchone()
    except Exception as e: 
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally: 
        cur.close()

@router.put("/padron/{venta_id}")
def modificar_venta_padron(venta_id: int, data: ModificarVentaInput, db=Depends(get_db)):
    if not data.motivo_modificacion or data.motivo_modificacion.strip() == "": 
        raise HTTPException(status_code=400, detail="El motivo de modificación es obligatorio.")
    
    # Validar que raciones sea al menos 1
    if data.raciones < 1:
        raise HTTPException(status_code=400, detail="Las raciones deben ser al menos 1. Use el botón Eliminar si desea remover la venta.")
    
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Verificar si la venta existe
        cur.execute("SELECT id FROM padron_diario WHERE id = %s;", (venta_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Venta no encontrada")
        
        # Construir query dinámica para actualizar solo los campos proporcionados
        update_fields = [
            "raciones = %s",
            "monto_pagado = %s",
            "tipo_menu = %s",
            "tipo_comensal_venta = %s",
            "observacion = %s",
            "motivo_modificacion = %s"
        ]
        
        params = [
            data.raciones,
            data.monto_pagado,
            data.tipo_menu,
            data.tipo_comensal_venta,
            data.observacion,
            data.motivo_modificacion
        ]
        
        # Si se proporciona un nuevo comensal_id, incluirlo en el UPDATE
        if data.comensal_id is not None:
            update_fields.insert(0, "comensal_id = %s")
            params.insert(0, data.comensal_id)
        
        params.append(venta_id)
        
        query = f"""
            UPDATE padron_diario 
            SET {', '.join(update_fields)} 
            WHERE id = %s 
            RETURNING *;
        """
        
        cur.execute(query, params)
        db.commit()
        return cur.fetchone()
        
    except psycopg2.Error as e:
        db.rollback()
        print(f"Error de base de datos: {e}")
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {str(e)}")
    except Exception as e: 
        db.rollback()
        print(f"Error general: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally: 
        cur.close()

@router.delete("/padron/{venta_id}")
def eliminar_venta_padron(venta_id: int, db=Depends(get_db)):
    """
    Elimina físicamente una venta del padrón diario.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Verificar si la venta existe
        cur.execute("SELECT id FROM padron_diario WHERE id = %s;", (venta_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Venta no encontrada")
        
        # Eliminar la venta
        cur.execute("DELETE FROM padron_diario WHERE id = %s RETURNING id;", (venta_id,))
        db.commit()
        return {"message": "Venta eliminada exitosamente"}
        
    except psycopg2.Error as e:
        db.rollback()
        print(f"Error de base de datos: {e}")
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {str(e)}")
    except Exception as e: 
        db.rollback()
        print(f"Error general: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally: 
        cur.close()

@router.get("/padron/hoy")
def obtener_ventas_hoy(db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try: 
        cur.execute(
            """SELECT pd.*, c.nombres, c.documento_identidad 
               FROM padron_diario pd 
               JOIN comensales c ON pd.comensal_id = c.id 
               WHERE pd.fecha = CURRENT_DATE 
               ORDER BY pd.id DESC;"""
        )
        return cur.fetchall()
    finally: 
        cur.close()

@router.get("/padron/stats")
def obtener_estadisticas_padron(db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """SELECT pd.tipo_comensal_venta as tipo_comensal, 
                      SUM(pd.raciones) as total_raciones, 
                      SUM(pd.monto_pagado) as recaudacion 
               FROM padron_diario pd 
               WHERE pd.fecha = CURRENT_DATE 
               GROUP BY pd.tipo_comensal_venta;"""
        )
        resultados = cur.fetchall()
        stats = {"Social": 0, "Afiliado": 0, "Normal": 0, "recaudacion_total": 0.0}
        for row in resultados: 
            stats[row['tipo_comensal']] = int(row['total_raciones'])
            stats["recaudacion_total"] += float(row['recaudacion'])
        return stats
    finally: 
        cur.close()