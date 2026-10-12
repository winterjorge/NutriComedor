"""
routers/padron.py
Objetivo: Endpoints para la gestión del padrón, ventas diarias (POS), predicción
          de demanda y carga masiva de atenciones históricas.
Historial:
 - Sprint 1/2: versión original (predicción, búsqueda/registro de comensales por DNI,
   CRUD de ventas y estadísticas del día).
 - COM-62 v2: atención ágil sin DNI (autocompletado por nombre, DNI opcional, edición
   de ficha, Cliente Genérico reservado para cargas masivas).
 - COM-63: carga masiva de atenciones históricas desde CSV + tipo "Cocinera"
   (menú a costo cero, comensal genérico CO000000).
 - COM-64: predicción de demanda con datos reales de padron_diario (pasa el cursor
   al motor de IA para entrenar con historial real ≥30 días).
 - COM-64 v3 (este archivo): dos blindajes de lectura, sin tocar datos:
     1) /padron/prediccion_demanda es NULL-SAFE: si el motor devuelve None (menos de
        4 históricos del día de semana), responde 200 con sin_datos=True y valores
        null. ANTES hacía pred[0] sobre None -> TypeError -> HTTP 500, y ese 500
        tumbaba el Promise.all de usePOS.js dejando la vista SIN stats y SIN ventas
        del día ("No hay ventas hoy" aunque sí existieran en BD). Ningún fix anterior
        borró ventas: era un fallo de lectura, no de escritura.
     2) /padron/hoy usa LEFT JOIN + COALESCE para que las filas del día sin comensal
        vinculado (comensal_id NULL, p.ej. una carga masiva COM-63 del día) NO queden
        ocultas por el INNER JOIN anterior (que se conserva comentado por trazabilidad).
Uso: Registrado en main.py sin prefijo propio (rutas /padron/* y /comensales/*).
Referencia: tickets COM-62, COM-63, COM-64 (solo trazabilidad).
"""
from datetime import date, datetime
from typing import Optional
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor
import psycopg2

from database import get_db, get_parametros_dict
from schemas.comensal import RegistroVentaInput, ModificarVentaInput
from ai_engine import predecir_demanda_raciones

router = APIRouter(tags=["Padrón y POS"])

# COM-62 v2: documento reservado para comensales atendidos solo por nombre.
DNI_SIN_DATO = '00000000'
TIPOS_COMENSAL_VALIDOS = ('Social', 'Afiliado', 'Normal', 'Cocinera')


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
# PREDICCIÓN DE DEMANDA (COM-64 / COM-64 v3: null-safe)
# ==========================================
@router.get("/padron/prediccion_demanda")
def predecir_demanda_diaria(fecha_str: str = None, db=Depends(get_db)):
    """
    COM-64: predice la demanda diaria usando datos reales de padron_diario cuando
    existen ≥30 días de historial y ≥4 del mismo día de semana; el motor entrena un
    Random Forest en el momento con ese historial.
    COM-64 v3: si el motor devuelve None (datos insuficientes para ESE día de la
    semana), se responde 200 con sin_datos=True y valores null para que la UI muestre
    el mensaje ámbar de advertencia. Nunca se responde 500: el TypeError anterior
    (pred[0] sobre None) rompía el Promise.all de usePOS.js y vaciaba stats y ventas
    del día en pantalla.
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

    # 3. COM-64: ejecutar predicción pasando el cursor para usar datos reales
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        pred = predecir_demanda_raciones(
            fecha_eval.weekday(),
            fecha_eval.day,
            limites_minimos,
            limites_finde,
            cur=cur  # <-- COM-64: pasar cursor para datos reales
        )
    finally:
        cur.close()

    # COM-64 v3: sin datos suficientes -> flag explícito, nunca excepción.
    # Trazabilidad: la versión COM-64 hacía directamente pred[0]/pred[1]/pred[2] y
    # sum(pred), tronando con TypeError cuando el motor devolvía None.
    if pred is None:
        return {
            "fecha": fecha_eval.strftime("%Y-%m-%d"),
            "sin_datos": True,
            "prediccion_social": None,
            "prediccion_afiliado": None,
            "prediccion_normal": None,
            "total_raciones_sugeridas": None,
        }

    return {
        "fecha": fecha_eval.strftime("%Y-%m-%d"),
        "sin_datos": False,
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
    """
    Ventas del día para la tabla del POS.
    COM-62 v2: incluye es_generico para el render de 'Genérico'/'Sin DNI' en la tabla.
    COM-64 v3: LEFT JOIN + COALESCE para que las filas del día SIN comensal vinculado
    (comensal_id NULL, p.ej. una carga masiva COM-63 hecha con fecha de hoy) NO queden
    ocultas: el INNER JOIN anterior las descartaba silenciosamente del listado.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """SELECT pd.*,
                      COALESCE(c.nombres, 'Carga masiva (sin comensal)') AS nombres,
                      c.documento_identidad,
                      COALESCE(c.es_generico, FALSE) AS es_generico
               FROM padron_diario pd
               LEFT JOIN comensales c ON pd.comensal_id = c.id
               WHERE pd.fecha = CURRENT_DATE
               ORDER BY pd.id DESC;
               -- COM-62 v2 / COM-64 (trazabilidad): versión anterior con INNER JOIN,
               -- que ocultaba filas con comensal_id NULL:
               -- SELECT pd.*, c.nombres, c.documento_identidad, c.es_generico
               -- FROM padron_diario pd
               -- JOIN comensales c ON pd.comensal_id = c.id
               -- WHERE pd.fecha = CURRENT_DATE
               -- ORDER BY pd.id DESC;
            """
        )
        return cur.fetchall()
    finally:
        cur.close()


@router.get("/padron/stats")
def obtener_estadisticas_padron(db=Depends(get_db)):
    """Totales del día por tipo de comensal (COM-63: incluye 'Cocinera')."""
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
        stats = {"Social": 0, "Afiliado": 0, "Normal": 0, "Cocinera": 0, "recaudacion_total": 0.0}
        for row in resultados:
            stats[row['tipo_comensal']] = int(row['total_raciones'])
            stats["recaudacion_total"] += float(row['recaudacion'])
        return stats
    finally:
        cur.close()


# ==========================================
# COM-63: CARGA MASIVA DE ATENCIONES HISTÓRICAS
# ==========================================
@router.post("/padron/carga-masiva")
async def carga_masiva_historica(
    file: UploadFile = File(...),
    db=Depends(get_db)
):
    """
    COM-63: carga masiva de atenciones históricas desde CSV.
    Estructura del CSV: fecha;afiliados;publico;sociales;cocineras
    - fecha: YYYY-MM-DD o DD/MM/YYYY
    - afiliados: int >= 0
    - publico: int >= 0 (mapeado a 'Normal')
    - sociales: int >= 0 (mapeado a 'Social')
    - cocineras: int >= 0 (nuevo tipo, precio 0.00, comensal genérico CO000000)

    Las filas históricas de Social/Afiliado/Normal se insertan con comensal_id NULL
    (no existen fichas individuales para atenciones pasadas); las de Cocinera se
    vinculan al comensal genérico. Retorna resumen con procesadas/omitidas/creadas.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="El archivo debe ser CSV")

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Leer contenido del CSV
        contenido = await file.read()
        texto = contenido.decode('utf-8-sig')  # utf-8-sig maneja BOM de Excel

        # Parsear CSV con separador ;
        reader = csv.DictReader(io.StringIO(texto), delimiter=';')

        filas_procesadas = 0
        filas_omitidas = 0
        ventas_creadas = 0
        detalle_omitidas = []
        fechas = []

        # Obtener comensal genérico "Cocinera"
        cur.execute("SELECT id FROM comensales WHERE documento_identidad = 'CO000000';")
        comensal_cocinera = cur.fetchone()
        if not comensal_cocinera:
            raise HTTPException(status_code=500, detail="Comensal genérico 'Cocinera' no existe")
        cocinera_id = comensal_cocinera['id']

        for idx, fila in enumerate(reader, start=2):  # start=2 porque fila 1 es header
            try:
                # Parsear fecha (aceptar YYYY-MM-DD o DD/MM/YYYY)
                fecha_str = fila.get('fecha', '').strip()
                if not fecha_str:
                    detalle_omitidas.append({"fila": idx, "razon": "fecha vacía"})
                    filas_omitidas += 1
                    continue

                try:
                    fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        fecha = datetime.strptime(fecha_str, "%d/%m/%Y").date()
                    except ValueError:
                        detalle_omitidas.append({"fila": idx, "razon": f"fecha inválida: {fecha_str}"})
                        filas_omitidas += 1
                        continue

                # Parsear cantidades
                afiliados = int(fila.get('afiliados', 0) or 0)
                publico = int(fila.get('publico', 0) or 0)
                sociales = int(fila.get('sociales', 0) or 0)
                cocineras = int(fila.get('cocineras', 0) or 0)

                if afiliados + publico + sociales + cocineras == 0:
                    detalle_omitidas.append({"fila": idx, "razon": "todos los tipos en 0"})
                    filas_omitidas += 1
                    continue

                # Insertar ventas para cada tipo
                tipos_venta = [
                    ('Afiliado', afiliados),
                    ('Normal', publico),
                    ('Social', sociales),
                    ('Cocinera', cocineras),
                ]

                for tipo, cantidad in tipos_venta:
                    if cantidad > 0:
                        # Determinar comensal_id y precio
                        if tipo == 'Cocinera':
                            comensal_id = cocinera_id
                            precio = 0.00
                        else:
                            # Históricos sin ficha individual: comensal_id NULL
                            comensal_id = None
                            precio = {'Afiliado': 3.00, 'Normal': 5.00, 'Social': 0.00}[tipo]

                        monto = precio * cantidad

                        cur.execute("""
                            INSERT INTO padron_diario
                            (comensal_id, fecha, tipo_comensal_venta, raciones, monto_pagado, tipo_menu, observacion)
                            VALUES (%s, %s, %s, %s, %s, 'Almuerzo regular', 'Carga histórica COM-63')
                            ON CONFLICT DO NOTHING
                            RETURNING id;
                        """, (comensal_id, fecha, tipo, cantidad, monto))

                        if cur.fetchone():
                            ventas_creadas += 1

                filas_procesadas += 1
                fechas.append(fecha)

            except Exception as e:
                detalle_omitidas.append({"fila": idx, "razon": str(e)})
                filas_omitidas += 1

        db.commit()

        rango = {
            "desde": min(fechas).isoformat() if fechas else None,
            "hasta": max(fechas).isoformat() if fechas else None
        }

        return {
            "filas_procesadas": filas_procesadas,
            "filas_omitidas": filas_omitidas,
            "ventas_creadas": ventas_creadas,
            "detalle_omitidas": detalle_omitidas[:10],
            "rango_fechas": rango
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al procesar CSV: {str(e)}")
    finally:
        cur.close()