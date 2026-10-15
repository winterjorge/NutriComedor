"""
routers/planificacion.py
Objetivo: Endpoints para consultar planificaciones guardadas y generar listas de compras.
Historial:
Sprint 2: versión original (listar, detalle, lista-compras con filtro por día, eliminar).
COM-65: trazabilidad. El endpoint /lista-compras ya soporta ?dia=N para generar la
lista consolidada semanal o filtrada por un día específico. El frontend
(PlanificacionesView.jsx) fue corregido para leer data.lista_compras.
COM-67 v2: unidades reales de compra: puente unidad_receta -> gramos vía
ingredientes_equivalencias (o factor_a_base / peso_estimado_g) y conversión final a
la unidad de COMPRA del insumo (kg / L / und), agrupando por insumo.
COM-69 (este archivo): SOLUCIÓN B de subsidio en la lista de compras:
Nuevo parámetro opcional comedor_id. Con él, se lee el stock del subsidio del
mes de la planificación (subsidio_motor.subsidio_gramos_del_mes) y cada ítem se
cubre primero con ese stock: gramos_cubiertos = min(requerido, stock).
El costo estimado se calcula SOLO sobre los gramos que sí se compran
(requerido - cubierto) al mejor precio por gramo vigente
(precios_insumos.precios_por_gramo_por_ingrediente).
Cada ítem expone: subsidio_completo / subsidio_parcial / cantidad_subsidio /
costo_estimado / ahorro_subsidio_estimado, para que la UI muestre "SUBSIDIADO"
en rojo en lugar del precio cuando corresponda.
El resumen incluye el bloque 'subsidio' (mes, comedor, ahorro y costo total).
Regla v1 (documentada): la lista cubre contra el stock mensual COMPLETO; el
control acumulado entre semanas del mismo mes vive en el reporte de uso
(GET /subsidio/reporte-uso, COM-69), que alerta si el consumo supera el stock.
COM-75 (este archivo): FIX de correspondencia ingrediente->insumo en la lista de
compras. Ahora busca el insumo vinculado en la equivalencia activa en lugar del
primer insumo por ID, evitando nombres incorrectos y precios faltantes. También
limpia el sufijo "(manual)" de los nombres para presentación.
Trazabilidad: el formateo anterior sin subsidio queda comentado al final.
Uso: Registrado en main.py con prefijo /api/v1.
Referencia: tickets COM-65 / COM-67 / COM-69 / COM-75 (solo trazabilidad).
"""
import math
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import RealDictCursor
from database import get_db
# COM-69: stock del subsidio del mes (gramos/ml base por ingrediente) y precios por gramo
from subsidio_motor import subsidio_gramos_del_mes
from precios_insumos import precios_por_gramo_por_ingrediente

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
# COM-67 v2 / COM-69 / COM-75: helpers de conversión
# ============================================================================
def _gramos_de_ingrediente(cur, ing_id, unidad_receta_id, cantidad_total_receta):
    """
    COM-67 v2: convierte la cantidad en unidad de RECETA a GRAMOS (puente universal).
    Prioridad: equivalencia activa -> factor_a_base (masa/volumen) -> peso_estimado_g
    (discretos). Retorna (gramos, origen).
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
    COM-67 v2: convierte GRAMOS a la unidad de COMPRA del insumo respetando magnitud:
    masa -> /factor (kg), volumen -> /factor (L), discreto -> /peso_estimado_g (und).
    Retorna (cantidad, abreviatura).
    """
    cur.execute("""
        SELECT um.nombre, um.abreviatura, um.factor_a_base, um.tipo_magnitud
        FROM unidades_medida um
        WHERE um.id = %s;
    """, (unidad_compra_id,))
    um = cur.fetchone()
    if not um:
        return gramos, 'g'
    if um['tipo_magnitud'] in ('masa', 'volumen'):
        return gramos / float(um['factor_a_base'] or 1000.0), um['abreviatura']
    peso_unidad = float(peso_estimado_g) if peso_estimado_g else 0.0
    if peso_unidad > 0:
        return gramos / peso_unidad, um['abreviatura']
    return cantidad_total_receta, um['abreviatura']

def _limpiar_nombre_insumo(nombre: str) -> str:
    """
    COM-75: limpia sufijos como '(manual)' del nombre del insumo para presentación.
    """
    if not nombre:
        return nombre
    return nombre.replace(' (manual)', '').replace('(manual)', '').strip()

@router.get("/{planificacion_id}/lista-compras")
def generar_lista_compras(
    planificacion_id: int,
    dia: int = Query(None, description="Filtrar por día específico (1=Lunes, 7=Domingo)"),
    comedor_id: int = Query(None, description="COM-69: comedor para aplicar el subsidio del mes"),
    db=Depends(get_db)
):
    """
    COM-67 v2 + COM-69 + COM-75: lista de compras consolidada (semanal o por día) con unidades
    reales de mercado y cobertura de SUBSIDIO (Solución B):
    1) requerido en gramos/ml base por ingrediente (equivalencias -> factor -> peso);
    2) COM-69: cubierto = min(requerido, stock del subsidio del mes del comedor);
       compra = requerido - cubierto; el costo estimado va SOLO sobre la compra;
    3) conversión a unidad de compra del insumo (kg/L/und) para mostrar cantidades;
    4) agrupación por insumo con días de uso.
    COM-75: FIX de correspondencia ingrediente->insumo. Ahora busca el insumo vinculado
    en la equivalencia activa en lugar del primer insumo por ID. También limpia el
    sufijo "(manual)" de los nombres para presentación.
    Si no se envía comedor_id, se comporta exactamente como COM-67 v2 (sin subsidio).
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT id, fecha_referencia FROM presupuesto_semanal WHERE id = %s", (planificacion_id,))
        plan = cur.fetchone()
        if not plan:
            raise HTTPException(status_code=404, detail="Planificación no encontrada")
        fecha_ref = plan['fecha_referencia'] or date.today()

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
                       i.nombre AS ingrediente_nombre,
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
                gramos, _origen = _gramos_de_ingrediente(
                    cur, ing_id, ing['unidad_receta_id'], cantidad_total_receta)

                # COM-75: Buscar el insumo vinculado en la equivalencia activa
                cur.execute("""
                    SELECT ie.insumo_id
                    FROM ingredientes_equivalencias ie
                    WHERE ie.ingrediente_id = %s
                      AND ie.unidad_uso_id = %s
                      AND ie.estado_activo = TRUE
                    ORDER BY ie.fecha_registro DESC
                    LIMIT 1;
                """, (ing_id, ing['unidad_receta_id']))
                
                equiv_row = cur.fetchone()
                
                if equiv_row:
                    # Usar el insumo de la equivalencia activa
                    cur.execute("""
                        SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre,
                               ins.unidad_medida_id AS unidad_compra_id
                        FROM insumos ins
                        WHERE ins.id = %s;
                    """, (equiv_row['insumo_id'],))
                    insumo = cur.fetchone()
                else:
                    # Fallback: buscar insumo con precio disponible
                    cur.execute("""
                        SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre,
                               ins.unidad_medida_id AS unidad_compra_id
                        FROM insumos ins
                        LEFT JOIN historial_precios hp ON hp.insumo_id = ins.id
                        WHERE ins.ingrediente_id = %s
                        GROUP BY ins.id, ins.nombre, ins.unidad_medida_id
                        ORDER BY MAX(hp.fecha) DESC NULLS LAST, ins.id
                        LIMIT 1;
                    """, (ing_id,))
                    insumo = cur.fetchone()

                if insumo:
                    clave = ('insumo', insumo['insumo_id'])
                    # COM-75: limpiar nombre "(manual)" para presentación
                    nombre = _limpiar_nombre_insumo(insumo['insumo_nombre'])
                    unidad_compra_id = insumo['unidad_compra_id']
                else:
                    clave = ('ingrediente', ing_id)
                    nombre = _limpiar_nombre_insumo(ing['ingrediente_nombre'])
                    unidad_compra_id = None

                if clave not in lista_compras:
                    lista_compras[clave] = {
                        'ingrediente_id': ing_id,
                        'unidad_compra_id': unidad_compra_id,
                        'nombre': nombre,
                        'gramos': 0.0,
                        'peso_estimado_g': ing['peso_estimado_g'],
                        'dias_uso': [],
                    }
                lista_compras[clave]['gramos'] += gramos
                if dia_plan['dia_nombre'] not in lista_compras[clave]['dias_uso']:
                    lista_compras[clave]['dias_uso'].append(dia_plan['dia_nombre'])

        # ------------------------------------------------------------------
        # COM-69: stock del subsidio del mes de la planificación y precios por gramo
        # ------------------------------------------------------------------
        stock = {}
        if comedor_id:
            try:
                stock = subsidio_gramos_del_mes(cur, comedor_id, fecha_ref.year, fecha_ref.month) or {}
            except Exception as e:
                print(f"[COM-69] No se pudo leer el subsidio del mes: {e}")
                stock = {}
        try:
            ppg_map = precios_por_gramo_por_ingrediente(
                cur, fecha_ref.isoformat(), fallback_ultima_fecha=True) or {}
        except Exception as e:
            print(f"[COM-69] No se pudieron leer precios por gramo: {e}")
            ppg_map = {}

        lista_formateada = []
        items_subsididados = 0
        ahorro_total = 0.0
        costo_total_compra = 0.0

        for (tipo, key), data in sorted(lista_compras.items(), key=lambda x: x[1]['nombre']):
            requerido = data['gramos']
            ing_id = data['ingrediente_id']
            stock_ing = float(stock.get(ing_id, 0.0) or 0.0)

            # COM-69 (Solución B): cobertura topada por el stock del subsidio
            cubierto = min(requerido, stock_ing) if stock_ing > 0 else 0.0
            compra = max(0.0, requerido - cubierto)
            subsidio_completo = (cubierto > 0 and compra <= 0.0001)
            subsidio_parcial = (cubierto > 0 and compra > 0.0001)
            if subsidio_completo or subsidio_parcial:
                items_subsididados += 1

            ppg = ppg_map.get(ing_id)
            costo_estimado = round(compra * ppg, 2) if (ppg is not None and compra > 0) else None
            ahorro_estimado = round(cubierto * ppg, 2) if (ppg is not None and cubierto > 0) else None
            if costo_estimado:
                costo_total_compra += costo_estimado
            if ahorro_estimado:
                ahorro_total += ahorro_estimado

            # Conversión a unidad de compra (COM-67 v2) de la COMPRA y del CUBIERTO
            if data['unidad_compra_id']:
                cant_compra, unidad = _convertir_a_unidad_compra(
                    cur, data['unidad_compra_id'], compra, compra, data['peso_estimado_g'])
                cant_subsidio, _ = _convertir_a_unidad_compra(
                    cur, data['unidad_compra_id'], cubierto, cubierto, data['peso_estimado_g'])
                cant_req, _ = _convertir_a_unidad_compra(
                    cur, data['unidad_compra_id'], requerido, requerido, data['peso_estimado_g'])
            else:
                cant_compra, unidad = compra / 1000.0, 'kg'
                cant_subsidio = cubierto / 1000.0
                cant_req = requerido / 1000.0

            def _redondear(v, u):
                if u in ('kg', 'l', 'L'):
                    return round(v, 2)
                if u in ('g', 'ml'):
                    return round(v, 1)
                return math.ceil(v)

            lista_formateada.append({
                'id': key,
                'tipo': tipo,
                'ingrediente_id': ing_id,
                'nombre': data['nombre'],
                'cantidad': _redondear(cant_compra, unidad),
                'unidad': unidad,
                'dias_uso': data['dias_uso'],
                # COM-69: campos de subsidio para la UI (badge SUBSIDIADO en rojo)
                'cantidad_requerida': _redondear(cant_req, unidad),
                'cantidad_subsidio': _redondear(cant_subsidio, unidad),
                'subsidio_completo': subsidio_completo,
                'subsidio_parcial': subsidio_parcial,
                'costo_estimado': costo_estimado,
                'ahorro_subsidio_estimado': ahorro_estimado,
            })

        return {
            'planificacion_id': planificacion_id,
            'tipo': 'diaria' if dia is not None else 'semanal',
            'dia_especifico': dia,
            'total_dias': len(dias_planificados),
            'total_ingredientes': len(lista_formateada),
            'lista_compras': lista_formateada,
            # COM-69: resumen de subsidio aplicado a esta lista
            'subsidio': {
                'comedor_id': comedor_id,
                'anio': fecha_ref.year,
                'mes': fecha_ref.month,
                'stock_registrado': bool(stock),
                'items_subsididados': items_subsididados,
                'ahorro_total_estimado': round(ahorro_total, 2),
                'costo_total_compra_estimado': round(costo_total_compra, 2),
            },
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

# ============================================================================
# COM-69 (TRAZABILIDAD): formateo COM-67 v2 sin subsidio, COMENTADO.
# Antes cada ítem se convertía y mostraba sin campos de cobertura:
#     cantidad_display = math.ceil((cantidad / 1000.0) * 10) / 10  # kg o L
#     lista_formateada.append({'ingrediente_id', 'nombre', 'cantidad', 'unidad', 'dias_uso'})
# Desde COM-69 se agregan: cantidad_requerida, cantidad_subsidio, subsidio_completo,
# subsidio_parcial, costo_estimado y ahorro_subsidio_estimado por ítem.
# ============================================================================