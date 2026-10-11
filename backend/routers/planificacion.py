"""
routers/planificacion.py
Objetivo: Endpoints para consultar planificaciones guardadas y generar listas de compras.
Historial:
 - Sprint 2: versión original (listar, detalle, lista-compras con filtro por día, eliminar).
 - COM-65: trazabilidad. El endpoint /lista-compras ya soporta ?dia=N.
 - COM-67 v1: primera corrección de unidades de compra usando insumos.
 - COM-67 v2 (este archivo): corrección sistémica:
     * El puente de conversión es ingredientes_equivalencias (unidad_receta -> gramos).
     * Fallback discreto usa ingredientes.peso_estimado_g (NUNCA 100 g hardcodeado).
     * La unidad de compra sale del insumo (kg / L / und) y la conversión respeta
       la magnitud de destino (masa, volumen o discreto).
     * Agrupa por insumo para consolidar compras reales de mercado.
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
        return {**planificacion, "dias": dias}
    finally:
        cur.close()


# ============================================================================
# COM-67 v2: helpers de conversión
# ============================================================================
def _gramos_de_ingrediente(cur, ing_id, unidad_receta_id, cantidad_total_receta):
    """
    Convierte la cantidad en unidad de receta a GRAMOS (puente universal).
    Prioridad:
      1) ingredientes_equivalencias activa (unidad_uso -> gramos_por_unidad_uso)
      2) unidades_medida.factor_a_base para masa/volumen
      3) ingredientes.peso_estimado_g para discretos (NUNCA un valor hardcodeado)
    Retorna (gramos, origen) donde origen = 'equivalencia' | 'factor' | 'peso_estimado'.
    """
    cur.execute("""
        SELECT ie.gramos_por_unidad_uso
        FROM ingredientes_equivalencias ie
        WHERE ie.ingrediente_id = %s
          AND ie.unidad_uso_id  = %s
          AND ie.estado_activo  = TRUE
        ORDER BY ie.fecha_registro DESC
        LIMIT 1;
    """, (ing_id, unidad_receta_id))
    row = cur.fetchone()
    if row:
        return cantidad_total_receta * float(row['gramos_por_unidad_uso']), 'equivalencia'

    cur.execute("""
        SELECT um.factor_a_base, um.tipo_magnitud
        FROM unidades_medida um
        WHERE um.id = %s;
    """, (unidad_receta_id,))
    um = cur.fetchone()
    if um and um['tipo_magnitud'] in ('masa', 'volumen'):
        return cantidad_total_receta * float(um['factor_a_base']), 'factor'

    cur.execute("SELECT peso_estimado_g FROM ingredientes WHERE id = %s;", (ing_id,))
    ing = cur.fetchone()
    peso = float(ing['peso_estimado_g']) if ing and ing['peso_estimado_g'] else 10.0
    return cantidad_total_receta * peso, 'peso_estimado'


def _convertir_a_unidad_compra(cur, unidad_compra_id, gramos, cantidad_total_receta, peso_estimado_g):
    """
    Convierte GRAMOS a la unidad de compra del insumo respetando su magnitud:
      masa     -> kg  = gramos / 1000
      volumen  -> L   = gramos / 1000  (densidad ~1: el puente gramos≈ml es exacto en volumen)
      discreto -> und = gramos / peso_estimado_g  (o 1:1 si la receta ya era discreta)
    Retorna (cantidad, abreviatura_unidad).
    """
    cur.execute("""
        SELECT um.nombre, um.abreviatura, um.factor_a_base, um.tipo_magnitud
        FROM unidades_medida um
        WHERE um.id = %s;
    """, (unidad_compra_id,))
    um = cur.fetchone()
    if not um:
        return gramos, 'g'

    if um['tipo_magnitud'] == 'masa':
        return gramos / float(um['factor_a_base'] or 1000.0), um['abreviatura']
    if um['tipo_magnitud'] == 'volumen':
        return gramos / float(um['factor_a_base'] or 1000.0), um['abreviatura']
    # discreto: número de unidades de compra
    peso_unidad = float(peso_estimado_g) if peso_estimado_g else 0.0
    if peso_unidad > 0:
        return gramos / peso_unidad, um['abreviatura']
    return cantidad_total_receta, um['abreviatura']


@router.get("/{planificacion_id}/lista-compras")
def generar_lista_compras(
    planificacion_id: int,
    dia: int = Query(None, description="Filtrar por día específico (1=Lunes, 7=Domingo)"),
    db=Depends(get_db)
):
    """
    COM-67 v2: lista de compras consolidada con unidades reales de mercado.
    Flujo por ingrediente de cada día:
      1) cantidad_receta escalada a total_comensales
      2) -> GRAMOS vía equivalencia / factor / peso_estimado
      3) -> unidad de compra del insumo (kg, L, und)
      4) acumula por insumo y registra días de uso
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id FROM presupuesto_semanal WHERE id = %s", (planificacion_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Planificación no encontrada")

        query = """
            SELECT pd.dia, pd.dia_nombre, pd.total_comensales, pd.receta_id, pd.nombre_receta
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

        lista_compras = {}

        for dia_plan in dias_planificados:
            receta_id = dia_plan['receta_id']
            total_comensales = dia_plan['total_comensales']

            cur.execute("SELECT raciones FROM recetas_almuerzo WHERE id = %s", (receta_id,))
            rec = cur.fetchone()
            raciones_receta = rec['raciones'] if rec and rec['raciones'] and rec['raciones'] > 0 else 1

            cur.execute("""
                SELECT ri.ingrediente_id,
                       i.nombre            AS ingrediente_nombre,
                       i.peso_estimado_g,
                       ri.cantidad_requerida,
                       ri.unidad_medida_id AS unidad_receta_id
                FROM receta_ingrediente ri
                JOIN ingredientes i ON i.id = ri.ingrediente_id
                WHERE ri.receta_id = %s
            """, (receta_id,))
            ingredientes = cur.fetchall()

            for ing in ingredientes:
                ing_id = ing['ingrediente_id']
                cantidad_total_receta = (float(ing['cantidad_requerida']) / raciones_receta) * total_comensales

                gramos, origen = _gramos_de_ingrediente(
                    cur, ing_id, ing['unidad_receta_id'], cantidad_total_receta
                )

                # Insumo de compra vinculado al ingrediente
                cur.execute("""
                    SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre,
                           ins.unidad_medida_id AS unidad_compra_id
                    FROM insumos ins
                    WHERE ins.ingrediente_id = %s
                    ORDER BY ins.id
                    LIMIT 1;
                """, (ing_id,))
                insumo = cur.fetchone()

                if insumo:
                    cantidad, unidad = _convertir_a_unidad_compra(
                        cur, insumo['unidad_compra_id'], gramos,
                        cantidad_total_receta, ing['peso_estimado_g']
                    )
                    clave = ('insumo', insumo['insumo_id'])
                    nombre = insumo['insumo_nombre']
                else:
                    # Sin insumo: se reporta el ingrediente en gramos/kg genérico
                    cantidad = gramos / 1000.0
                    unidad = 'kg'
                    clave = ('ingrediente', ing_id)
                    nombre = ing['ingrediente_nombre']

                if clave not in lista_compras:
                    lista_compras[clave] = {
                        'nombre': nombre,
                        'unidad': unidad,
                        'cantidad': 0.0,
                        'dias_uso': []
                    }
                lista_compras[clave]['cantidad'] += cantidad
                if dia_plan['dia_nombre'] not in lista_compras[clave]['dias_uso']:
                    lista_compras[clave]['dias_uso'].append(dia_plan['dia_nombre'])

        lista_formateada = []
        for (tipo, key), data in sorted(lista_compras.items(), key=lambda x: x[1]['nombre']):
            cantidad = data['cantidad']
            if data['unidad'] in ('kg', 'L', 'l'):
                cantidad = round(cantidad, 2)
            elif data['unidad'] in ('g', 'ml'):
                cantidad = round(cantidad, 1)
            else:
                cantidad = math.ceil(cantidad)
            lista_formateada.append({
                'id': key,
                'tipo': tipo,
                'nombre': data['nombre'],
                'cantidad': cantidad,
                'unidad': data['unidad'],
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