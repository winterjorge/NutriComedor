"""
routers/presupuesto.py
Objetivo: Contener la lógica de los endpoints de cálculo de presupuestos y planificación semanal.
Uso: Registrado en main.py con prefijo /api/v1. Expone rutas como /presupuesto/calcular.
"""
import random
from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import RealDictCursor

from database import get_db, get_parametros_dict
from schemas.presupuesto import (
    PresupuestoInput, PlanificacionInput, PlanificacionResponse, PlanificacionDia,
    GuardarPlanificacionInput, GuardarPlanificacionResponse
)
from config import DIAS_SEMANA
from optimizador import calcular_costo_receta

router = APIRouter(prefix="/presupuesto", tags=["Presupuesto"])

@router.post("/calcular")
def calcular_presupuesto(data: PresupuestoInput):
    if data.fondo <= 0 or data.dias <= 0 or data.comensales <= 0:
        raise HTTPException(status_code=400, detail="Valores inválidos.")
    return {
        "presupuesto_diario": round(data.fondo / data.dias, 2),
        "presupuesto_por_racion": round((data.fondo / data.dias) / data.comensales, 2)
    }

@router.post("/planificar", response_model=PlanificacionResponse)
def planificar_semana(data: PlanificacionInput, db=Depends(get_db)):
    """
    Planificación semanal con:
    - Predicción de comensales por tipo
    - Cálculo de recolección proyectada usando PRECIOS DINÁMICOS de la BD
    - Costos reales de recetas usando calcular_costo_receta
    - Sin repetir recetas en la misma semana
    """
    if data.presupuesto <= 0 or data.dias_operativos <= 0:
        raise HTTPException(status_code=400, detail="Valores inválidos")
    if len(data.prediccion_comensales) != data.dias_operativos:
        raise HTTPException(status_code=400, detail=f"Se requieren {data.dias_operativos} predicciones")

    fecha_calc = data.fecha_referencia or __import__('datetime').date.today().isoformat()
    
    # 1. LEER PRECIOS DINÁMICOS DESDE LA BD
    claves_precios = ['PRECIO_SOCIAL', 'PRECIO_AFILIADO', 'PRECIO_NORMAL']
    params = get_parametros_dict(db, claves_precios)
    precio_soc = params.get('PRECIO_SOCIAL', 0.0)
    precio_afi = params.get('PRECIO_AFILIADO', 3.0)
    precio_nor = params.get('PRECIO_NORMAL', 5.0)

    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, nombre FROM recetas_almuerzo ORDER BY nombre;")
        recetas_db = cur.fetchall()
        if not recetas_db:
            raise HTTPException(status_code=404, detail="No hay recetas disponibles")

        recetas_con_costo = []
        for receta in recetas_db:
            try:
                resultado = calcular_costo_receta(receta['id'], fecha_calc)
                costo = resultado.get('costo_total_racion', 0.0)
                if costo > 0:
                    recetas_con_costo.append({
                        'id': receta['id'],
                        'nombre': receta['nombre'],
                        'costo_racion': costo
                    })
            except Exception as e:
                print(f"Error en receta {receta['nombre']}: {e}")

        if not recetas_con_costo:
            raise HTTPException(status_code=404, detail="No hay recetas con costo calculado")
        if len(recetas_con_costo) < data.dias_operativos:
            raise HTTPException(status_code=400, detail=f"No hay suficientes recetas disponibles ({len(recetas_con_costo)}) para {data.dias_operativos} días sin repetir")

        max_intentos = 100
        mejor_planificacion = None
        menor_diferencia = float('inf')

        for _ in range(max_intentos):
            dias_plan = []
            costo_total = 0.0
            recoleccion_total = 0.0
            recetas_usadas = set()

            for i in range(data.dias_operativos):
                prediccion = data.prediccion_comensales[i]
                total_comensales = prediccion.social + prediccion.afiliado + prediccion.normal
                
                # 2. CÁLCULO DE RECOLECCIÓN USANDO PRECIOS DE LA BD
                recoleccion_dia = (prediccion.social * precio_soc) + \
                                  (prediccion.afiliado * precio_afi) + \
                                  (prediccion.normal * precio_nor)
                recoleccion_total += recoleccion_dia

                recetas_disponibles = [r for r in recetas_con_costo if r['id'] not in recetas_usadas]
                if not recetas_disponibles:
                    receta_sel = min(recetas_con_costo, key=lambda r: abs(r['costo_racion'] * total_comensales - data.presupuesto / data.dias_operativos))
                else:
                    receta_sel = random.choice(recetas_disponibles)
                
                recetas_usadas.add(receta_sel['id'])
                costo_dia = receta_sel['costo_racion'] * total_comensales

                dias_plan.append(PlanificacionDia(
                    dia=i + 1,
                    dia_nombre=DIAS_SEMANA[i] if i < len(DIAS_SEMANA) else f"Día {i+1}",
                    comensales_social=prediccion.social,
                    comensales_afiliado=prediccion.afiliado,
                    comensales_normal=prediccion.normal,
                    total_comensales=total_comensales,
                    receta_id=receta_sel['id'],
                    nombre_receta=receta_sel['nombre'],
                    costo_racion=round(receta_sel['costo_racion'], 2),
                    costo_total=round(costo_dia, 2),
                    recoleccion_proyectada=round(recoleccion_dia, 2)
                ))
                costo_total += costo_dia

            if costo_total <= data.presupuesto:
                return PlanificacionResponse(
                    viable=True, presupuesto=data.presupuesto,
                    costo_total_semana=round(costo_total, 2),
                    recoleccion_total_proyectada=round(recoleccion_total, 2),
                    margen=round(data.presupuesto - costo_total, 2),
                    dias=dias_plan
                )

            if abs(costo_total - data.presupuesto) < menor_diferencia:
                menor_diferencia = abs(costo_total - data.presupuesto)
                mejor_planificacion = (dias_plan, costo_total, recoleccion_total)

        if mejor_planificacion:
            dias_plan, costo_total, recoleccion_total = mejor_planificacion
            return PlanificacionResponse(
                viable=False, presupuesto=data.presupuesto,
                costo_total_semana=round(costo_total, 2),
                recoleccion_total_proyectada=round(recoleccion_total, 2),
                margen=round(data.presupuesto - costo_total, 2),
                dias=dias_plan
            )

        raise HTTPException(status_code=500, detail="Error generando planificación")
    finally:
        cur.close()

@router.post("/guardar", response_model=GuardarPlanificacionResponse)
def guardar_planificacion(data: GuardarPlanificacionInput, db=Depends(get_db)):
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO presupuesto_semanal
            (fondo_total, dias_operativos, fecha_referencia, costo_total_semana,
            recoleccion_total_proyectada, margen, viable)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            data.presupuesto, data.dias_operativos, data.fecha_referencia,
            data.costo_total_semana, data.recoleccion_total_proyectada,
            data.margen, data.viable
        ))
        presupuesto_id = cur.fetchone()['id']

        for dia in data.dias:
            cur.execute("""
                INSERT INTO planificacion_dia 
                (presupuesto_semanal_id, dia, dia_nombre, comensales_social, 
                 comensales_afiliado, comensales_normal, total_comensales, 
                 receta_id, nombre_receta, costo_racion, costo_total, recoleccion_proyectada)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                presupuesto_id, dia.dia, dia.dia_nombre, dia.comensales_social,
                dia.comensales_afiliado, dia.comensales_normal, dia.total_comensales,
                dia.receta_id, dia.nombre_receta, dia.costo_racion, dia.costo_total,
                dia.recoleccion_proyectada
            ))
        db.commit()
        return GuardarPlanificacionResponse(
            id=presupuesto_id,
            message=f"Planificación guardada exitosamente con ID {presupuesto_id}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar planificación: {str(e)}")
    finally:
        cur.close()

@router.get("/tipos-platos")
def get_tipos_platos():
    return {
        1: {"nombre": "Tipo 1 - Básico", "precio": 1.6},
        2: {"nombre": "Tipo 2 - Económico", "precio": 2.0},
        3: {"nombre": "Tipo 3 - Regular", "precio": 4.0},
        4: {"nombre": "Tipo 4 - Medio", "precio": 3.0},
        5: {"nombre": "Tipo 5 - Especial", "precio": 2.5},
        6: {"nombre": "Tipo 6 - Premium", "precio": 6.0}
    }