"""
routers/padron.py
Objetivo: Endpoints para la gestión del padrón, ventas diarias (POS) y predicción
          de demanda.
Historial:
 - Sprint 1/2: versión original (predicción, búsqueda/registro de comensales por DNI,
   CRUD de ventas y estadísticas del día).
 - COM-62 v2 (este archivo): atención ágil sin DNI:
     * GET  /comensales/buscar-por-nombre: autocompletado por nombre (excluye al
       Cliente Genérico) para seleccionar la ficha existente antes de vender.
     * PUT  /comensales/{comensal_id}: edición de ficha, incluido COMPLETAR/CORREGIR
       el DNI días después (el comedor puede empezar a pedir DNI sin migrar nada).
     * GET  /comensales/{documento}: si el documento es '00000000' devuelve el Cliente
       Genérico (reservado para cargas masivas históricas).
     * POST /comensales/registrar: documento OPCIONAL; sin DNI se guarda con '00000000'
       y se REUTILIZA la ficha si ya existe ese nombre (dedup por índice parcial).
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-62 (solo trazabilidad).
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
import psycopg2

from database import get_db, get_parametros_dict
from schemas.comensal import RegistroVentaInput, ModificarVentaInput
from ai_engine import predecir_demanda_raciones

router = APIRouter(tags=["Padrón y POS"])

# COM-62 v2: documento reservado para comensales atendidos solo por nombre.
DNI_SIN_DATO = '00000000'
TIPOS_COMENSAL_VALIDOS = ('Social', 'Afiliado', 'Normal')


# ==========================================
# COM-62 v2: MODELOS DE ENTRADA POS (locales, no rompen schemas.comensal)
# ==========================================
class NuevoComensalPOSInput(BaseModel):
    """Alta de comensal con documento OPCIONAL (sin DNI => '00000000')."""
    tipo_documento: str = 'DNI'
    documento_identidad: Optional[str] = ''
    nombres: str
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    tipo_comensal: str = 'Normal'


class EditarComensalPOSInput(BaseModel):
    """Edición de ficha; permite COMPLETAR el DNI tiempo después."""
    nombres: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    tipo_comensal: Optional[str] = None
    documento_identidad: Optional[str] = None


# ==========================================
# PREDICCIÓN DE DEMANDA
# ==========================================
@router.get("/padron/prediccion_demanda")
def predecir_demanda_diaria(fecha_str: str = None, db=Depends(get_db)):
    fecha_eval = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
    claves_ia = [
        'IA_MIN_SOCIAL', 'IA_MIN_AFILIADO', 'IA_MIN_NORMAL',
        'IA_FINDE_SOCIAL', 'IA_FINDE_AFILIADO', 'IA_FINDE_NORMAL'
    ]
    params = get_parametros_dict(db, claves_ia)
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
    pred = predecir_demanda_raciones(
        fecha_eval.weekday(), fecha_eval.day, limites_minimos, limites_finde
    )
    return {
        "fecha": fecha_eval.strftime("%Y-%m-%d"),
        "prediccion_social": pred[0],
        "prediccion_afiliado": pred[1],
        "prediccion_normal": pred[2],
        "total_raciones_sugeridas": sum(pred)
    }


# ==========================================
# COM-62 v2: AUTOCOMPLETADO POR NOMBRE (excluye al Cliente Genérico)
# ==========================================
@router.get("/comensales/buscar-por-nombre")
def buscar_comensales_por_nombre(q: str = '', limite: int = 8, db=Depends(get_db)):
    """
    COM-62 v2: sugerencias de comensales por nombre para la caja del POS. Excluye al
    Cliente Genérico (es_generico=TRUE) y marca cuáles tienen DNI real (tiene_dni).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT id, tipo_documento, documento_identidad, nombres,
                   apellido_paterno, apellido_materno, tipo_comensal,
                   (documento_identidad <> '00000000') AS tiene_dni
            FROM comensales
            WHERE es_generico = FALSE
              AND (%s = '' OR LOWER(nombres) LIKE LOWER(%s))
            ORDER BY tiene_dni DESC, nombres
            LIMIT %s;
        """, (q or '', f"%{(q or '').strip()}%", max(1, min(limite, 20))))
        return cur.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al buscar comensales por nombre: {e}")
    finally:
        cur.close()


# ==========================================
# BÚSQUEDA EXACTA POR DOCUMENTO
# ==========================================
@router.get("/comensales/{documento}")
def buscar_comensal(documento: str, db=Depends(get_db)):
    """
    Búsqueda exacta por documento. COM-62 v2: si el documento es '00000000' se devuelve
    el Cliente Genérico (reservado para cargas masivas); cualquier otro DNI busca la
    fila con ese DNI real.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if documento == DNI_SIN_DATO:
            cur.execute("SELECT * FROM comensales WHERE es_generico = TRUE LIMIT 1;")
        else:
            cur.execute("SELECT * FROM comensales WHERE documento_identidad = %s;", (documento,))
        res = cur.fetchone()
        if not res:
            raise HTTPException(status_code=404, detail="Comensal no encontrado")
        return res
    finally:
        cur.close()


# ==========================================
# COM-62 v2: EDICIÓN DE FICHA (incluye completar/corregir DNI después)
# ==========================================
@router.put("/comensales/{comensal_id}")
def editar_comensal(comensal_id: int, data: EditarComensalPOSInput, db=Depends(get_db)):
    """
    COM-62 v2: edita nombre/apellidos/tipo y permite ASIGNAR el DNI real tiempo después.
    Validaciones:
      - DNI real duplicado -> 400 (uq_comensales_dni_real).
      - Al quitar el DNI pasa a '00000000': si ya hubiera otra ficha sin DNI con ese
        nombre -> 400 (uq_comensales_nombre_sin_dni).
      - El Cliente Genérico no se edita (es reserva de cargas masivas).
    """
    if data.tipo_comensal is not None and data.tipo_comensal not in TIPOS_COMENSAL_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Tipo de comensal inválido: use uno de {TIPOS_COMENSAL_VALIDOS}.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT * FROM comensales WHERE id = %s;", (comensal_id,))
        fila = cur.fetchone()
        if not fila:
            raise HTTPException(status_code=404, detail="Comensal no encontrado.")
        if fila['es_generico']:
            raise HTTPException(status_code=400,
                                detail="El Cliente Genérico no se edita: es reserva para cargas masivas.")
        sets = []
        params = []
        if data.nombres is not None:
            nombres = data.nombres.strip()
            if len(nombres) < 2:
                raise HTTPException(status_code=400, detail="El nombre del comensal es obligatorio.")
            sets.append("nombres = %s"); params.append(nombres)
        if data.apellido_paterno is not None:
            sets.append("apellido_paterno = %s"); params.append(data.apellido_paterno.strip() or None)
        if data.apellido_materno is not None:
            sets.append("apellido_materno = %s"); params.append(data.apellido_materno.strip() or None)
        if data.tipo_comensal is not None:
            sets.append("tipo_comensal = %s"); params.append(data.tipo_comensal)
        if data.documento_identidad is not None:
            doc = data.documento_identidad.strip() or DNI_SIN_DATO
            sets.append("documento_identidad = %s"); params.append(doc)
        if not sets:
            raise HTTPException(status_code=400, detail="No hay campos que actualizar.")
        params.append(comensal_id)
        cur.execute(f"UPDATE comensales SET {', '.join(sets)} WHERE id = %s RETURNING *;", params)
        db.commit()
        return cur.fetchone()
    except psycopg2.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400,
                            detail="Conflicto de unicidad: ese DNI ya está registrado, o ya existe "
                                   "otro comensal sin DNI con ese mismo nombre.")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()


# ==========================================
# REGISTRO DE COMENSAL (COM-62 v2: documento OPCIONAL)
# ==========================================
@router.post("/comensales/registrar")
def registrar_comensal_manual(data: NuevoComensalPOSInput, db=Depends(get_db)):
    """
    COM-62 v2: alta de comensal con documento OPCIONAL.
      - Sin DNI (vacío o '00000000'): se guarda con '00000000'; si ya existe una ficha
        sin DNI con el mismo nombre normalizado, se REUTILIZA (creado=False).
      - Con DNI real: se inserta con ese DNI; la unicidad de DNI reales la garantiza
        uq_comensales_dni_real (IntegrityError -> 400 'Documento ya registrado').
    """
    if data.tipo_comensal not in TIPOS_COMENSAL_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Tipo de comensal inválido: use uno de {TIPOS_COMENSAL_VALIDOS}.")
    nombres = (data.nombres or '').strip()
    if len(nombres) < 2:
        raise HTTPException(status_code=400, detail="El nombre del comensal es obligatorio.")
    doc = (data.documento_identidad or '').strip() or DNI_SIN_DATO
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        if doc == DNI_SIN_DATO:
            cur.execute("""
                SELECT * FROM comensales
                WHERE es_generico = FALSE
                  AND documento_identidad = %s
                  AND LOWER(BTRIM(nombres)) = LOWER(BTRIM(%s))
                LIMIT 1;
            """, (DNI_SIN_DATO, nombres))
            existente = cur.fetchone()
            if existente:
                return {**existente, 'creado': False,
                        'message': 'Comensal sin DNI ya existía: se reutiliza su ficha.'}
        cur.execute(
            """INSERT INTO comensales
               (tipo_documento, documento_identidad, nombres, apellido_paterno, apellido_materno, tipo_comensal)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *;""",
            (data.tipo_documento or 'DNI', doc, nombres,
             (data.apellido_paterno or '').strip() or None,
             (data.apellido_materno or '').strip() or None,
             data.tipo_comensal)
        )
        db.commit()
        nuevo = cur.fetchone()
        return {**nuevo, 'creado': True,
                'message': ('Comensal registrado sin DNI (podrá completarse después).'
                            if doc == DNI_SIN_DATO else 'Comensal registrado con DNI.')}
    except psycopg2.IntegrityError:
        db.rollback()
        if doc == DNI_SIN_DATO:
            cur.execute("""
                SELECT * FROM comensales
                WHERE es_generico = FALSE AND documento_identidad = %s
                  AND LOWER(BTRIM(nombres)) = LOWER(BTRIM(%s)) LIMIT 1;
            """, (DNI_SIN_DATO, nombres))
            existente = cur.fetchone()
            if existente:
                return {**existente, 'creado': False,
                        'message': 'Comensal sin DNI ya existía: se reutiliza su ficha.'}
        raise HTTPException(status_code=400, detail="Documento ya registrado.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()


# ==========================================
# VENTAS (POS)
# ==========================================
@router.post("/padron")
def registrar_venta_padron(data: RegistroVentaInput, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
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
    if data.raciones < 1:
        raise HTTPException(status_code=400, detail="Las raciones deben ser al menos 1. Use el botón Eliminar si desea remover la venta.")
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM padron_diario WHERE id = %s;", (venta_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Venta no encontrada")
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
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM padron_diario WHERE id = %s;", (venta_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Venta no encontrada")
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
            """SELECT pd.*, c.nombres, c.documento_identidad, c.es_generico
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