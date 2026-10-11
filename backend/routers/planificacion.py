"""
routers/planificacion.py
Objetivo: Endpoints para consultar planificaciones guardadas y generar listas de compras.
Historial:
 - Sprint 2: versión original (listar, detalle, lista-compras con filtro por día, eliminar).
 - COM-65: trazabilidad. El endpoint /lista-compras ya soporta ?dia=N.
 - COM-67 (este archivo): FIX de unidades de compra usando equivalencias existentes.
   La lógica ahora:
   1) Obtiene equivalencia unidad_receta → gramos (tabla ingredientes_equivalencias)
   2) Obtiene unidad de compra del insumo (tabla insumos.unidad_medida_id)
   3) Convierte gramos → unidad_compra usando unidades_medida.factor_a_base
   4) Agrupa por insumo (no por ingrediente) para consolidar compras
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
    COM-67: Genera la lista de compras consolidada usando equivalencias existentes.
    
    LÓGICA DE CONVERSIÓN:
    1. Para cada ingrediente en la receta, buscar equivalencia activa (unidad_receta → gramos)
    2. Calcular cantidad total en gramos: cantidad_receta × gramos_por_unidad_uso × (total_comensales / raciones_receta)
    3. Buscar el insumo vinculado al ingrediente
    4. Obtener unidad de compra del insumo (insumos.unidad_medida_id)
    5. Convertir gramos a unidad de compra: cantidad_gramos / factor_a_base_unidad_compra
    6. Agrupar por insumo (no por ingrediente) para consolidar compras
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

        # Consolidar ingredientes por insumo
        lista_compras = {}
        
        for dia_plan in dias_planificados:
            receta_id = dia_plan['receta_id']
            total_comensales = dia_plan['total_comensales']
            
            # Obtener raciones de la receta
            cur.execute("SELECT raciones FROM recetas_almuerzo WHERE id = %s", (receta_id,))
            receta_info = cur.fetchone()
            raciones_receta = receta_info['raciones'] if receta_info and receta_info['raciones'] and receta_info['raciones'] > 0 else 1

            # Obtener ingredientes de la receta
            cur.execute("""
                SELECT 
                    ri.ingrediente_id,
                    i.nombre as ingrediente_nombre,
                    ri.cantidad_requerida,
                    ri.unidad_medida_id as unidad_receta_id
                FROM receta_ingrediente ri
                JOIN ingredientes i ON ri.ingrediente_id = i.id
                WHERE ri.receta_id = %s
            """, (receta_id,))
            ingredientes = cur.fetchall()
            
            for ing in ingredientes:
                ing_id = ing['ingrediente_id']
                ing_nombre = ing['ingrediente_nombre']
                cantidad_requerida = float(ing['cantidad_requerida'])
                unidad_receta_id = ing['unidad_receta_id']
                
                # Calcular cantidad total para todos los comensales
                cantidad_por_racion = cantidad_requerida / raciones_receta
                cantidad_total_receta = cantidad_por_racion * total_comensales
                
                # COM-67: Buscar equivalencia activa (unidad_receta → gramos)
                cur.execute("""
                    SELECT ie.gramos_por_unidad_uso
                    FROM ingredientes_equivalencias ie
                    WHERE ie.ingrediente_id = %s 
                      AND ie.unidad_uso_id = %s
                      AND ie.estado_activo = TRUE
                    ORDER BY ie.fecha_registro DESC
                    LIMIT 1
                """, (ing_id, unidad_receta_id))
                equivalencia = cur.fetchone()
                
                if equivalencia:
                    # Usar equivalencia: cantidad_gramos = cantidad_receta × gramos_por_unidad_uso
                    cantidad_gramos = cantidad_total_receta * float(equivalencia['gramos_por_unidad_uso'])
                else:
                    # Fallback: usar factor_a_base de la unidad de receta
                    cur.execute("""
                        SELECT um.factor_a_base, um.tipo_magnitud
                        FROM unidades_medida um
                        WHERE um.id = %s
                    """, (unidad_receta_id,))
                    unidad_info = cur.fetchone()
                    if unidad_info:
                        factor = float(unidad_info['factor_a_base'])
                        tipo = unidad_info['tipo_magnitud']
                        if tipo in ('masa', 'volumen'):
                            cantidad_gramos = cantidad_total_receta * factor
                        else:
                            # Discreto: asumir 1 unidad = 100g (peso estimado)
                            cantidad_gramos = cantidad_total_receta * 100.0
                    else:
                        cantidad_gramos = cantidad_total_receta * 100.0
                
                # COM-67: Buscar insumo vinculado al ingrediente
                cur.execute("""
                    SELECT ins.id as insumo_id, ins.nombre as insumo_nombre,
                           ins.unidad_medida_id as unidad_compra_id
                    FROM insumos ins
                    WHERE ins.ingrediente_id = %s
                    ORDER BY ins.id
                    LIMIT 1
                """, (ing_id,))
                insumo = cur.fetchone()
                
                if insumo:
                    insumo_id = insumo['insumo_id']
                    insumo_nombre = insumo['insumo_nombre']
                    unidad_compra_id = insumo['unidad_compra_id']
                    
                    # Obtener factor de conversión de la unidad de compra
                    cur.execute("""
                        SELECT um.nombre as unidad_nombre, um.abreviatura, um.factor_a_base
                        FROM unidades_medida um
                        WHERE um.id = %s
                    """, (unidad_compra_id,))
                    unidad_compra = cur.fetchone()
                    
                    if unidad_compra:
                        factor_compra = float(unidad_compra['factor_a_base'])
                        # Convertir gramos a unidad de compra
                        cantidad_compra = cantidad_gramos / factor_compra
                        
                        # Agrupar por insumo
                        if insumo_id not in lista_compras:
                            lista_compras[insumo_id] = {
                                'insumo_id': insumo_id,
                                'nombre': insumo_nombre,
                                'unidad': unidad_compra['abreviatura'],
                                'cantidad': 0,
                                'dias_uso': []
                            }
                        
                        lista_compras[insumo_id]['cantidad'] += cantidad_compra
                        if dia_plan['dia_nombre'] not in lista_compras[insumo_id]['dias_uso']:
                            lista_compras[insumo_id]['dias_uso'].append(dia_plan['dia_nombre'])
                else:
                    # Sin insumo vinculado: usar nombre del ingrediente y unidad genérica
                    if ing_id not in lista_compras:
                        lista_compras[ing_id] = {
                            'ingrediente_id': ing_id,
                            'nombre': ing_nombre,
                            'unidad': 'g',
                            'cantidad': 0,
                            'dias_uso': []
                        }
                    lista_compras[ing_id]['cantidad'] += cantidad_gramos
                    if dia_plan['dia_nombre'] not in lista_compras[ing_id]['dias_uso']:
                        lista_compras[ing_id]['dias_uso'].append(dia_plan['dia_nombre'])

        # Formatear lista final
        lista_formateada = []
        for key, data in sorted(lista_compras.items(), key=lambda x: x[1]['nombre']):
            cantidad = data['cantidad']
            unidad = data['unidad']
            
            # Redondear según unidad
            if unidad in ('kg', 'L'):
                cantidad = round(cantidad, 2)
            elif unidad == 'g' or unidad == 'ml':
                cantidad = round(cantidad, 1)
            else:
                cantidad = math.ceil(cantidad)
            
            lista_formateada.append({
                'insumo_id' if 'insumo_id' in data else 'ingrediente_id': key,
                'nombre': data['nombre'],
                'cantidad': cantidad,
                'unidad': unidad,
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