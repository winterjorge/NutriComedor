"""
routers/planificacion.py
Objetivo: Endpoints para consultar planificaciones guardadas y generar listas de compras.
Historial:
 - Sprint 2: versión original (listar, detalle, lista-compras con filtro por día, eliminar).
 - COM-65 (este archivo): trazabilidad. El endpoint /lista-compras ya soporta ?dia=N
   para generar la lista consolidada semanal o filtrada por un día específico.
   El frontend (PlanificacionesView.jsx) fue corregido para leer data.lista_compras
   (antes leía data.items/data.grupos, que no existían).
Uso: Registrado en main.py con prefijo /api/v1.
"""
import math
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from database import get_db

router = APIRouter(prefix="/planificaciones", tags=["Planificaciones"])


@router.get("")
def listar_planificaciones(db=Depends(get_db)):
    """Lista todas las planificaciones guardadas ordenadas por fecha de referencia descendente."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT
                ps.id,
                ps.fondo_total as presupuesto,
                ps.dias_operativos,
                ps.fecha_referencia,
                ps.costo_total_semana,
                ps.recoleccion_total_proyectada,
                ps.margen,
                ps.viable,
                ps.fecha_registro,
                COUNT(pd.id) as total_dias
            FROM presupuesto_semanal ps
            LEFT JOIN planificacion_dia pd ON ps.id = pd.presupuesto_semanal_id
            GROUP BY ps.id
            ORDER BY ps.fecha_referencia DESC, ps.fecha_registro DESC
        """)
        return cur.fetchall()
    finally:
        cur.close()


@router.get("/{planificacion_id}")
def obtener_planificacion_detalle(planificacion_id: int, db=Depends(get_db)):
    """Obtiene el detalle completo de una planificación específica."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT
                ps.id,
                ps.fondo_total as presupuesto,
                ps.dias_operativos,
                ps.fecha_referencia,
                ps.costo_total_semana,
                ps.recoleccion_total_proyectada,
                ps.margen,
                ps.viable,
                ps.fecha_registro
            FROM presupuesto_semanal ps
            WHERE ps.id = %s
        """, (planificacion_id,))
        planificacion = cur.fetchone()
        if not planificacion:
            raise HTTPException(status_code=404, detail="Planificación no encontrada")
        cur.execute("""
            SELECT 
                pd.dia,
                pd.dia_nombre,
                pd.comensales_social,
                pd.comensales_afiliado,
                pd.comensales_normal,
                pd.total_comensales,
                pd.receta_id,
                pd.nombre_receta,
                pd.costo_racion,
                pd.costo_total,
                pd.recoleccion_proyectada
            FROM planificacion_dia pd
            WHERE pd.presupuesto_semanal_id = %s
            ORDER BY pd.dia
        """, (planificacion_id,))
        dias = cur.fetchall()
        return {
            **planificacion,
            "dias": dias
        }
    finally:
        cur.close()


@router.get("/{planificacion_id}/lista-compras")
def generar_lista_compras(
    planificacion_id: int,
    dia: int = Query(None, description="Filtrar por día específico (1=Lunes, 7=Domingo)"),
    db=Depends(get_db)
):
    """
    COM-65: Genera la lista de compras consolidada para una planificación.
    Si se especifica 'dia', genera la lista solo para ese día.
    LÓGICA DE CÁLCULO:
      1. Cada receta tiene un campo 'raciones' que indica para cuántas personas alcanza
      2. Cantidad por ración = cantidad_requerida / raciones
      3. Cantidad total = total_comensales * (cantidad_requerida / raciones)
      4. Convertir a unidades de compra estándar (kg para sólidos, L para líquidos)
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM presupuesto_semanal WHERE id = %s", (planificacion_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Planificación no encontrada")

        query = """
            SELECT 
                pd.dia,
                pd.dia_nombre,
                pd.total_comensales,
                pd.receta_id,
                pd.nombre_receta
            FROM planificacion_dia pd
            WHERE pd.presupuesto_semanal_id = %s
        """
        params = [planificacion_id]
        if dia is not None:
            query += " AND pd.dia = %s"
            params.append(dia)
        query += " ORDER BY pd.dia"
        cur.execute(query, params)
        dias_planificados = cur.fetchall()
        if not dias_planificados:
            raise HTTPException(status_code=404, detail="No hay días planificados")

        # Consolidar ingredientes
        lista_compras = {}
        for dia_plan in dias_planificados:
            receta_id = dia_plan['receta_id']
            total_comensales = dia_plan['total_comensales']
            cur.execute("SELECT raciones FROM recetas_almuerzo WHERE id = %s", (receta_id,))
            receta_info = cur.fetchone()
            raciones_receta = receta_info['raciones'] if receta_info and receta_info['raciones'] and receta_info['raciones'] > 0 else 1

            cur.execute("""
                SELECT 
                    ri.ingrediente_id,
                    i.nombre as ingrediente_nombre,
                    ri.cantidad_requerida,
                    ri.unidad_medida_id,
                    um.nombre as unidad_nombre,
                    um.abreviatura as unidad_abrev,
                    um.factor_a_base,
                    um.tipo_magnitud
                FROM receta_ingrediente ri
                JOIN ingredientes i ON ri.ingrediente_id = i.id
                JOIN unidades_medida um ON ri.unidad_medida_id = um.id
                WHERE ri.receta_id = %s
            """, (receta_id,))
            ingredientes = cur.fetchall()
            for ing in ingredientes:
                ing_id = ing['ingrediente_id']
                cantidad_requerida = float(ing['cantidad_requerida'])
                factor = float(ing['factor_a_base'])
                tipo_magnitud = ing['tipo_magnitud']
                cantidad_por_racion = cantidad_requerida / raciones_receta
                cantidad_total = cantidad_por_racion * total_comensales
                if tipo_magnitud == 'masa':
                    cantidad_base = cantidad_total * factor
                elif tipo_magnitud == 'volumen':
                    cantidad_base = cantidad_total * factor
                else:
                    cantidad_base = cantidad_total

                if ing_id not in lista_compras:
                    lista_compras[ing_id] = {
                        'ingrediente_id': ing_id,
                        'nombre': ing['ingrediente_nombre'],
                        'unidad_nombre': ing['unidad_nombre'],
                        'unidad_abrev': ing['unidad_abrev'],
                        'tipo_magnitud': tipo_magnitud,
                        'cantidad_base': 0,
                        'dias_uso': []
                    }
                lista_compras[ing_id]['cantidad_base'] += cantidad_base
                if dia_plan['dia_nombre'] not in lista_compras[ing_id]['dias_uso']:
                    lista_compras[ing_id]['dias_uso'].append(dia_plan['dia_nombre'])

        # Formatear para presentación
        lista_formateada = []
        for ing_id, data in sorted(lista_compras.items(), key=lambda x: x[1]['nombre']):
            cantidad = data['cantidad_base']
            if data['tipo_magnitud'] == 'masa':
                cantidad_display = math.ceil((cantidad / 1000.0) * 10) / 10
                unidad_display = 'kg'
            elif data['tipo_magnitud'] == 'volumen':
                cantidad_display = math.ceil((cantidad / 1000.0) * 10) / 10
                unidad_display = 'L'
            else:
                cantidad_display = math.ceil(cantidad)
                unidad_display = 'und'
            lista_formateada.append({
                'ingrediente_id': ing_id,
                'nombre': data['nombre'],
                'cantidad': cantidad_display,
                'unidad': unidad_display,
                'dias_uso': data['dias_uso']
            })

        return {
            'planificacion_id': planificacion_id,
            'tipo': 'diaria' if dia is not None else 'semanal',
            'dia_especifico': dia,
            'total_dias': len(dias_planificados),
            'total_ingredientes': len(lista_formateada),
            'lista_compras': lista_formateada
        }
    finally:
        cur.close()


@router.delete("/{planificacion_id}")
def eliminar_planificacion(planificacion_id: int, db=Depends(get_db)):
    """Elimina una planificación y sus días asociados."""
    cur = db.cursor()
    try:
        cur.execute("SELECT id FROM presupuesto_semanal WHERE id = %s", (planificacion_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Planificación no encontrada")
        cur.execute("DELETE FROM planificacion_dia WHERE presupuesto_semanal_id = %s", (planificacion_id,))
        cur.execute("DELETE FROM presupuesto_semanal WHERE id = %s RETURNING id", (planificacion_id,))
        db.commit()
        return {"message": "Planificación eliminada exitosamente"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()