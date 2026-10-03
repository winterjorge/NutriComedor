"""
optimizador.py
Objetivo: Motor de cálculo de costos de recetas con predicción de precios basada en histórico.
Uso: Importar desde routers de FastAPI para calcular costos dinámicos de recetas en cualquier fecha.
Nota: Utiliza Random Forest para predicción de precios (consistente con ai_engine.py)
Historial:
 - Sprint 2: versión original (mejor insumo del día, predicción RF con R², filas de error).
 - COM-37 v1/v2: fallback de precio manual ("Obtenido de la Base de Datos"), ingrediente_id
   por fila y precio_completo para la regla del flujo del comedor.
 - COM-37 v5: costeo con el modelo de DOS CONCEPTOS: gramos de la unidad de USO vía
   ingredientes_equivalencias (o conversión estándar) × precio por gramo del MEJOR
   insumo (scraper día > manual insumo > legacy ingrediente > predicción RF).
 - COM-48 (este archivo): esquema multi-componente. La consulta de líneas de receta se
   une a recetas_componentes y CADA fila del detalle expone componente_nombre y
   componente_orden (Ensalada / Plato de fondo / Refresco / Fruta), ordenadas por
   componente, para el desglose agrupado del modal de Evaluar. Un ingrediente usado en
   dos componentes genera dos filas independientes (cantidades y costos separados).
   La nutrición sigue POR RACIÓN (tabla) y el costo total se divide entre raciones.
"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import math

# COM-37 v5: resolución unificada de precios, equivalencias y conversión de unidades
from precios_insumos import (
    precios_por_gramo_por_insumo,
    mejor_opcion_ingrediente,
    gramos_por_unidad_uso,
    gramos_por_unidad_compra,
)

DB_URL = os.getenv("DATABASE_URL", "postgresql://nutri_admin:Nutri2026Secure!@db:5432/nutricomedor")


def redondear_hacia_arriba_010(valor):
    """Redondea hacia arriba al múltiplo de 0.10 más cercano."""
    if valor <= 0:
        return 0.0
    return math.ceil(valor * 10) / 10


def predecir_precio_con_confianza(insumo_id, fecha_objetivo, conn, cur):
    """
    Predice el precio usando Random Forest con R².
    Busca hasta 90 días de histórico para tener mejor base de predicción.
    """
    # Buscar hasta 90 días de histórico para mejor predicción
    cur.execute("""
        SELECT fecha, precio_prom
        FROM historial_precios
        WHERE insumo_id = %s
        AND fecha >= %s
        AND fecha < %s
        AND precio_prom IS NOT NULL
        ORDER BY fecha ASC
    """, (insumo_id, fecha_objetivo - timedelta(days=90), fecha_objetivo))
    registros = cur.fetchall()
    # Necesitamos al menos 5 registros para Random Forest
    if len(registros) < 5:
        return None, 0, False
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import r2_score
        X = np.array([[i] for i in range(len(registros))])
        y = np.array([float(r['precio_prom']) for r in registros])
        # Random Forest con parámetros ajustados para series de precios
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=5,
            min_samples_split=3,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X, y)
        y_pred = model.predict(X)
        r2 = r2_score(y, y_pred)
        confianza = max(0, r2 * 100)
        dias_desde_ultimo = len(registros)
        precio_predicho = model.predict([[dias_desde_ultimo]])[0]
        precio_predicho = max(0.01, precio_predicho)
        return round(precio_predicho, 2), round(confianza, 1), True
    except ImportError:
        # Fallback: usar promedio si no hay sklearn
        precio_promedio = sum(float(r['precio_prom']) for r in registros) / len(registros)
        return round(precio_promedio, 2), 50.0, True


def calcular_costo_receta(receta_id: int, fecha_evaluacion: str):
    """
    Calcula el costo real de una receta considerando:
    1. La unidad de medida de USO de cada línea (receta_ingrediente) y su componente (COM-48)
    2. El número de raciones que produce la receta (costo total / raciones)
    COM-37 v5: gramos por línea vía equivalencias uso->gramos (o conversión estándar) y
    precio por gramo del MEJOR insumo con la jerarquía de fuentes acordada.
    COM-48: cada fila del detalle lleva componente_nombre/componente_orden para el
    desglose agrupado en el modal de Evaluar; líneas del mismo ingrediente en distintos
    componentes se costean de forma independiente.
    Retorna el costo POR RACIÓN
    """
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Obtener número de raciones de la receta
        cur.execute("""
            SELECT raciones FROM recetas_almuerzo WHERE id = %s
        """, (receta_id,))
        receta_info = cur.fetchone()
        if not receta_info:
            return {"error": "La receta no existe"}
        raciones_receta = receta_info['raciones'] if receta_info['raciones'] and receta_info['raciones'] > 0 else 1

        # COM-48 (trazabilidad): consulta anterior sin componentes, comentada:
        # cur.execute("""
        #     SELECT ri.id as receta_ingrediente_id, ri.ingrediente_id, i.nombre as ingrediente_nombre,
        #            COALESCE(i.peso_estimado_g, 100.0) as peso_estimado_g, ri.cantidad_requerida,
        #            ri.unidad_medida_id as receta_unidad_medida_id, um_receta.nombre as receta_unidad_nombre,
        #            um_receta.abreviatura as receta_unidad_abrev, um_receta.factor_a_base as receta_factor_a_base,
        #            cat.nombre as categoria_nombre
        #     FROM receta_ingrediente ri ... ORDER BY ri.id;
        # """, (receta_id,))
        # COM-48: líneas de receta con su componente (nombre y orden) y la unidad de USO
        cur.execute("""
            SELECT 
                ri.id as receta_ingrediente_id,
                ri.ingrediente_id,
                ri.componente_id,
                rc.nombre as componente_nombre,
                rc.orden as componente_orden,
                i.nombre as ingrediente_nombre,
                COALESCE(i.peso_estimado_g, 100.0) as peso_estimado_g,
                ri.cantidad_requerida,
                ri.unidad_medida_id as receta_unidad_medida_id,
                um_receta.nombre as receta_unidad_nombre,
                um_receta.abreviatura as receta_unidad_abrev,
                um_receta.factor_a_base as receta_factor_a_base,
                um_receta.tipo_magnitud as receta_tipo_magnitud,
                cat.nombre as categoria_nombre
            FROM receta_ingrediente ri
            JOIN ingredientes i ON ri.ingrediente_id = i.id
            JOIN unidades_medida um_receta ON ri.unidad_medida_id = um_receta.id
            LEFT JOIN categorias_alimentos cat ON i.categoria_id = cat.id
            LEFT JOIN recetas_componentes rc ON ri.componente_id = rc.id
            WHERE ri.receta_id = %s
            ORDER BY rc.orden, rc.id, ri.id;
        """, (receta_id,))
        ingredientes_receta = cur.fetchall()
        if not ingredientes_receta:
            return {"error": "La receta no tiene ingredientes asignados"}

        # COM-37 v5: mapa de precios por insumo para la fecha evaluada
        precios_insumo = precios_por_gramo_por_insumo(cur, fecha_evaluacion)

        costo_total_receta = 0.0
        detalle_costos = []
        fecha_objetivo = datetime.strptime(fecha_evaluacion, "%Y-%m-%d").date()

        for req in ingredientes_receta:
            categoria = req['categoria_nombre'] or ''
            unidad_abrev = (req['receta_unidad_abrev'] or '').lower()
            unidad_nombre = req['receta_unidad_nombre'] or ''
            cantidad_requerida = float(req['cantidad_requerida'])
            factor_receta = float(req['receta_factor_a_base'])
            peso_estimado_base = float(req['peso_estimado_g'])

            # Display de la cantidad en la unidad de USO de la receta (reglas históricas)
            if unidad_abrev in ['und', 'unidad', 'u']:
                peso_display_g = cantidad_requerida * peso_estimado_base
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()} ({peso_display_g}g)"
            elif unidad_abrev in ['kg', 'kilogramo', 'l', 'litro']:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['g', 'gramo', 'ml', 'mililitro', 'tz', 'taza', 'cda', 'cucharada',
                                  'cdta', 'cucharadita', 'pz', 'pizca']:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"
            elif unidad_abrev in ['dte', 'diente', 'rma', 'rama']:
                peso_display_g = cantidad_requerida * peso_estimado_base
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()} ({peso_display_g}g)"
            elif unidad_abrev in ['atd', 'atado']:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()} ({cantidad_requerida * 100}g)"
            elif unidad_abrev in ['rdj', 'rodaja']:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()} ({cantidad_requerida * 20}g)"
            else:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"

            # COM-37 v5 / COM-48: candidatos = insumos del ingrediente; cada uno con su
            # fuente de precio (scraper día, manual período) o predicción RF; gramos de
            # la unidad de USO vía equivalencia del insumo elegido o conversión estándar.
            cur.execute("""
                SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
                       um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo, um.factor_a_base AS u_factor
                FROM insumos ins
                JOIN unidades_medida um ON um.id = ins.unidad_medida_id
                WHERE ins.ingrediente_id = %s;
            """, (req['ingrediente_id'],))
            insumos_rows = cur.fetchall()

            mejor = None
            for ins in insumos_rows:
                opc = precios_insumo.get(ins['insumo_id'])
                confianza = None
                if opc:
                    ppg = opc['ppg']
                    fuente = opc['fuente']
                else:
                    pred, conf, ok = predecir_precio_con_confianza(ins['insumo_id'], fecha_objetivo, conn, cur)
                    if not (ok and pred):
                        continue
                    g_compra = gramos_por_unidad_compra(
                        ins['u_abrev'], ins['u_tipo'], ins['u_factor'], peso_estimado_base)
                    if g_compra <= 0:
                        continue
                    ppg = float(pred) / g_compra
                    fuente = 'PREDICHO'
                    confianza = conf
                gramos = gramos_por_unidad_uso(
                    cur, req['ingrediente_id'], ins['insumo_id'], req['receta_unidad_medida_id'],
                    unidad_abrev, req['receta_tipo_magnitud'], factor_receta, peso_estimado_base)
                costo_sin_redondear = gramos * ppg
                costo_linea = redondear_hacia_arriba_010(costo_sin_redondear)
                if mejor is None or costo_linea < mejor['costo']:
                    mejor = {
                        'insumo_id': ins['insumo_id'],
                        'insumo_nombre': ins['insumo_nombre'],
                        'ppg': ppg,
                        'fuente': fuente,
                        'confianza': confianza,
                        'gramos': gramos,
                        'costo': costo_linea,
                    }

            # COM-37 v5: si ningún insumo candidato tuvo precio/predicción, fallback
            # legacy de precio manual por ingrediente (mejor_opcion_ingrediente lo incluye)
            if mejor is None:
                legacy = mejor_opcion_ingrediente(cur, req['ingrediente_id'], fecha_objetivo, precios_insumo)
                if legacy and legacy['fuente'] == 'LEGACY_INGREDIENTE':
                    gramos = gramos_por_unidad_uso(
                        cur, req['ingrediente_id'], None, req['receta_unidad_medida_id'],
                        unidad_abrev, req['receta_tipo_magnitud'], factor_receta, peso_estimado_base)
                    costo_linea = redondear_hacia_arriba_010(gramos * legacy['ppg'])
                    mejor = {
                        'insumo_id': None,
                        'insumo_nombre': legacy['insumo_nombre'],
                        'ppg': legacy['ppg'],
                        'fuente': 'LEGACY_INGREDIENTE',
                        'confianza': None,
                        'gramos': gramos,
                        'costo': costo_linea,
                    }

            componente_nombre = req['componente_nombre'] or 'Plato de fondo'
            componente_orden = req['componente_orden'] if req['componente_orden'] is not None else 99

            if mejor is None:
                # Sin insumos o sin precios: comportamiento original (fila roja)
                detalle_costos.append({
                    "ingrediente": req['ingrediente_nombre'],
                    "ingrediente_id": req['ingrediente_id'],
                    "componente_nombre": componente_nombre,
                    "componente_orden": componente_orden,
                    "insumo_comprado": "Sin insumo disponible" if not insumos_rows else "Sin precios disponibles",
                    "cantidad_usada": unidad_display,
                    "costo_parcial": 0.0,
                    "peso_usado_g": 0.0,
                    "error": "Sin insumos disponibles" if not insumos_rows else "Sin precios para esta fecha",
                    "es_prediccion": False,
                    "es_manual": False,
                })
                continue

            costo_total_receta += mejor['costo']
            es_manual = mejor['fuente'] in ('MANUAL_PERIODO', 'LEGACY_INGREDIENTE')
            es_prediccion = mejor['fuente'] == 'PREDICHO'
            if es_manual:
                insumo_display = "Obtenido de la Base de Datos"
            elif es_prediccion:
                insumo_display = f"{mejor['insumo_nombre']} (PREDICHO {mejor['confianza']}%)"
            else:
                insumo_display = mejor['insumo_nombre']
            detalle_costos.append({
                "ingrediente": req['ingrediente_nombre'],
                "ingrediente_id": req['ingrediente_id'],
                # COM-48: componente de la línea para el desglose agrupado del modal
                "componente_nombre": componente_nombre,
                "componente_orden": componente_orden,
                "insumo_comprado": insumo_display,
                "cantidad_usada": unidad_display,
                "costo_parcial": round(mejor['costo'], 2),
                "peso_usado_g": round(mejor['gramos'], 2),
                "es_prediccion": es_prediccion,
                "es_manual": es_manual,
                "fuente_precio": mejor['fuente'],
                "confianza_prediccion": f"{mejor['confianza']}%" if es_prediccion else None,
            })

        # CALCULAR COSTO POR RACIÓN (dividir costo total entre número de raciones)
        costo_por_racion = costo_total_receta / raciones_receta
        return {
            "receta_id": receta_id,
            "fecha_calculo": fecha_evaluacion,
            "raciones_receta": raciones_receta,
            "costo_total_receta": round(costo_total_receta, 2),
            "costo_total_racion": round(costo_por_racion, 2),
            "detalle_insumos": detalle_costos,
            "total_ingredientes": len(detalle_costos),
            "ingredientes_con_precio": sum(1 for d in detalle_costos if d['costo_parcial'] > 0),
            "ingredientes_sin_precio": sum(1 for d in detalle_costos if d['costo_parcial'] == 0),
            "ingredientes_predichos": sum(1 for d in detalle_costos if d.get('es_prediccion', False)),
            # COM-37: cuántos ingredientes se costearon con precio manual de la BD
            "ingredientes_manuales": sum(1 for d in detalle_costos if d.get('es_manual', False)),
            # COM-37 v2: regla de negocio: solo recetas con precios completos entran
            # al flujo del comedor (propuestas/planificación).
            "precio_completo": sum(1 for d in detalle_costos if d['costo_parcial'] == 0) == 0,
            # COM-48: componentes presentes en la receta (para encabezados del modal)
            "componentes": sorted(
                {(d['componente_nombre'], d['componente_orden']) for d in detalle_costos},
                key=lambda t: t[1]
            ),
        }
    except Exception as e:
        print(f"Error en el motor de optimización: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        if cur: cur.close()
        if conn: conn.close()