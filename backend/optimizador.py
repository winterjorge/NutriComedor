"""
optimizador.py
Objetivo: Motor de cálculo de costos de recetas ("Evaluar" del Recetario) con
          predicción de precios basada en histórico (Random Forest) y, desde COM-37,
          fallback de precios manuales.
Historial:
 - Sprint 2: versión original (mejor insumo del día por precio, predicción RF con R²,
   filas de error rojas, costo por ración).
 - COM-37 v1/v2: fallback de precio manual por INGREDIENTE (precios_manuales.py),
   filas es_manual con texto "Obtenido de la Base de Datos", ingrediente_id y
   precio_completo en la respuesta.
 - COM-37 v5 (este archivo): REESCRITO sobre precios_insumos.py con el modelo de DOS
   CONCEPTOS:
     * INGREDIENTE (unidad de USO: pizca, cucharadita, taza, und...) e
       INSUMO (unidad de COMPRA: Kg, L, atado, und...; origen SCRAPER o MANUAL).
     * Los gramos de cada línea de receta se calculan con la equivalencia registrada
       (ingredientes_equivalencias) para el par (ingrediente, insumo elegido); si no
       existe, con la conversión estándar de la unidad de uso.
     * El precio por gramo de cada insumo candidato sale de
       precios_insumos.precios_por_gramo_por_insumo (scraper del día > período manual
       del insumo) y, si el insumo no tuvo precio ese día, de la predicción RF.
     * Selección por MENOR COSTO entre candidatos (criterio de compra económica); la
       fila expone la fuente: scraper / PREDICHO / manual ("Obtenido de la Base de
       Datos", es_manual=True, colores actuales del caso sin insumos).
     * Último fallback: precio manual legacy por ingrediente (COM-37 v1).
     * Se conservan precio_completo y contadores para la regla del flujo del comedor
       (solo recetas con precios completos entran a propuestas/planificación).
   Los bloques reemplazados (evaluar_mejor_insumo sobre historial del día y el LEFT
   JOIN de opciones) quedan COMENTADOS por trazabilidad.
Uso: Importado por routers/recetas.py (GET /recetas/{id}/costo?fecha=...).
Referencia: tickets COM-37 v1/v2/v5 (solo trazabilidad).
"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
import math

# COM-37 v5: resolución unificada de precios por insumo y equivalencias uso->gramos
from precios_insumos import (
    precios_por_gramo_por_insumo,
    gramos_por_unidad_uso,
    gramos_por_unidad_compra,
)
# COM-37 v1: fallback legacy de precio manual POR INGREDIENTE (última fuente)
from precios_manuales import obtener_precio_manual_por_gramo

DB_URL = os.getenv("DATABASE_URL", "postgresql://nutri_admin:Nutri2026Secure!@db:5432/nutricomedor")


def redondear_hacia_arriba_010(valor):
    """Redondea hacia arriba al múltiplo de 0.10 más cercano."""
    if valor <= 0:
        return 0.0
    return math.ceil(valor * 10) / 10


# =========================================================================
# COM-37 v5 (trazabilidad): función original COMENTADA. Evaluaba opciones del día
# (historial_precios con LEFT JOIN por fecha) y elegía por precio redondeado.
# Reemplazada por el bucle de candidatos sobre precios_insumos + equivalencias.
# =========================================================================
# def evaluar_mejor_insumo(opciones_insumos, peso_estimado_g):
#     mejor_opcion = None
#     menor_costo_real = float('inf')
#     for insumo in opciones_insumos:
#         precio_kg = float(insumo['precio_prom'])
#         precio_por_gramo = precio_kg / 1000.0
#         costo_sin_redondear = precio_por_gramo * peso_estimado_g
#         costo_redondeado = redondear_hacia_arriba_010(costo_sin_redondear)
#         insumo['costo_calculado'] = costo_redondeado
#         insumo['costo_sin_redondear'] = costo_sin_redondear
#         if costo_redondeado < menor_costo_real:
#             menor_costo_real = costo_redondeado
#             mejor_opcion = insumo
#     return mejor_opcion


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
    1. La unidad de medida de USO de cada línea de receta (receta_ingrediente).
    2. La equivalencia uso->gramos del insumo elegido (o conversión estándar).
    3. El número de raciones que produce la receta (costo final POR RACIÓN).
    COM-37 v5: fuentes de precio por insumo candidato: scraper del día > período
    manual del insumo > predicción RF; selección por menor costo; fallback final de
    precio manual legacy por ingrediente. Filas manuales => "Obtenido de la Base de
    Datos" con es_manual=True. Respuesta incluye precio_completo y contadores.
    """
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Número de raciones de la receta
        cur.execute("""
            SELECT raciones FROM recetas_almuerzo WHERE id = %s
        """, (receta_id,))
        receta_info = cur.fetchone()
        if not receta_info:
            return {"error": "La receta no existe"}
        raciones_receta = receta_info['raciones'] if receta_info['raciones'] and receta_info['raciones'] > 0 else 1

        # Ingredientes de la receta con su UNIDAD DE USO (incluye tipo de magnitud)
        cur.execute("""
            SELECT 
                ri.id as receta_ingrediente_id,
                ri.ingrediente_id,
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
            WHERE ri.receta_id = %s
            ORDER BY ri.id;
        """, (receta_id,))
        ingredientes_receta = cur.fetchall()
        if not ingredientes_receta:
            return {"error": "La receta no tiene ingredientes asignados"}

        # COM-37 v5: mapa de precios por gramo por insumo para la fecha evaluada
        # (scraper del día + períodos manuales vigentes de insumos)
        precios_insumo = precios_por_gramo_por_insumo(cur, fecha_evaluacion)
        fecha_objetivo = datetime.strptime(fecha_evaluacion, "%Y-%m-%d").date()

        costo_total_receta = 0.0
        detalle_costos = []

        for req in ingredientes_receta:
            unidad_abrev = (req['receta_unidad_abrev'] or '').lower()
            unidad_nombre = req['receta_unidad_nombre'] or ''
            cantidad_requerida = float(req['cantidad_requerida'])

            # Insumos candidatos del ingrediente (con su unidad de COMPRA)
            cur.execute("""
                SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
                       um.abreviatura AS compra_abrev, um.tipo_magnitud AS compra_tipo,
                       um.factor_a_base AS compra_factor
                FROM insumos ins
                JOIN unidades_medida um ON um.id = ins.unidad_medida_id
                WHERE ins.ingrediente_id = %s;
            """, (req['ingrediente_id'],))
            candidatos_ins = cur.fetchall()

            mejor = None  # {costo, costo_crudo, gramos, insumo_*, fuente, confianza, ppg}
            for ins in candidatos_ins:
                opc = precios_insumo.get(ins['insumo_id'])
                fuente = opc['fuente'] if opc else None
                ppg = opc['ppg'] if opc else None
                confianza = None

                # COM-37 v5: si el insumo no tuvo precio ese día, intentar predicción RF
                if opc is None:
                    precio_predicho, conf, ok = predecir_precio_con_confianza(
                        ins['insumo_id'], fecha_objetivo, conn, cur)
                    if ok and precio_predicho:
                        g_compra = gramos_por_unidad_compra(
                            ins['compra_abrev'], ins['compra_tipo'],
                            ins['compra_factor'], req['peso_estimado_g'])
                        if g_compra > 0:
                            ppg = precio_predicho / g_compra
                            fuente = 'PREDICHO'
                            confianza = conf
                if ppg is None or ppg <= 0:
                    continue

                # COM-37 v5: gramos de la cantidad de USO según equivalencia del insumo
                gramos = gramos_por_unidad_uso(
                    cur, req['ingrediente_id'], ins['insumo_id'],
                    req['receta_unidad_medida_id'], unidad_abrev,
                    req['receta_tipo_magnitud'], req['receta_factor_a_base'],
                    req['peso_estimado_g']
                ) * cantidad_requerida
                if gramos <= 0:
                    continue

                costo_crudo = gramos * ppg
                costo_cand = redondear_hacia_arriba_010(costo_crudo)
                if mejor is None or costo_cand < mejor['costo'] or \
                   (costo_cand == mejor['costo'] and costo_crudo < mejor['costo_crudo']):
                    mejor = {
                        'costo': costo_cand,
                        'costo_crudo': costo_crudo,
                        'gramos': gramos,
                        'insumo_id': ins['insumo_id'],
                        'insumo_nombre': ins['insumo_nombre'],
                        'origen': ins['origen'],
                        'fuente': fuente,
                        'confianza': confianza,
                        'ppg': ppg,
                    }

            # Texto de unidad de uso para exhibición (con gramos reales del elegido)
            if mejor:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()} ({round(mejor['gramos'], 1)}g)"
            else:
                unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"

            if mejor is not None:
                costo_total_receta += mejor['costo']
                if mejor['fuente'] == 'PREDICHO':
                    texto_insumo = f"{mejor['insumo_nombre']} (PREDICHO {mejor['confianza']}%)"
                    es_manual = False
                    es_pred = True
                elif mejor['fuente'] == 'MANUAL_PERIODO':
                    # COM-37: texto exigido para precios cargados manualmente
                    texto_insumo = "Obtenido de la Base de Datos"
                    es_manual = True
                    es_pred = False
                else:  # SCRAPER_DIA
                    texto_insumo = mejor['insumo_nombre']
                    es_manual = False
                    es_pred = False
                detalle_costos.append({
                    "ingrediente": req['ingrediente_nombre'],
                    "ingrediente_id": req['ingrediente_id'],
                    "insumo_id": mejor['insumo_id'],
                    "insumo_comprado": texto_insumo,
                    "cantidad_usada": unidad_display,
                    "costo_parcial": round(mejor['costo'], 2),
                    "peso_usado_g": round(mejor['gramos'], 2),
                    "es_prediccion": es_pred,
                    "es_manual": es_manual,
                    "fuente": mejor['fuente'],
                    "confianza_prediccion": f"{mejor['confianza']}%" if mejor['confianza'] else None,
                    "detalle_manual": (f"{mejor['insumo_nombre']} (precio manual)"
                                       if es_manual else None),
                })
                continue

            # COM-37 v5: fallback legacy de precio manual POR INGREDIENTE (v1)
            legacy = obtener_precio_manual_por_gramo(cur, req['ingrediente_id'], fecha_objetivo)
            if legacy:
                gramos = gramos_por_unidad_uso(
                    cur, req['ingrediente_id'], None,
                    req['receta_unidad_medida_id'], unidad_abrev,
                    req['receta_tipo_magnitud'], req['receta_factor_a_base'],
                    req['peso_estimado_g']
                ) * cantidad_requerida
                costo_ing = redondear_hacia_arriba_010(gramos * legacy['precio_por_gramo'])
                costo_total_receta += costo_ing
                detalle_costos.append({
                    "ingrediente": req['ingrediente_nombre'],
                    "ingrediente_id": req['ingrediente_id'],
                    "insumo_id": None,
                    "insumo_comprado": "Obtenido de la Base de Datos",
                    "cantidad_usada": f"{cantidad_requerida} {unidad_nombre.lower()} ({round(gramos, 1)}g)",
                    "costo_parcial": round(costo_ing, 2),
                    "peso_usado_g": round(gramos, 2),
                    "es_prediccion": False,
                    "es_manual": True,
                    "fuente": "LEGACY_INGREDIENTE",
                    "confianza_prediccion": None,
                    "detalle_manual": legacy['detalle'],
                })
                continue

            # Sin ninguna fuente de precio (comportamiento original de error)
            error_txt = ("Sin insumos disponibles" if not candidatos_ins
                         else "Sin precios para esta fecha")
            detalle_costos.append({
                "ingrediente": req['ingrediente_nombre'],
                "ingrediente_id": req['ingrediente_id'],
                "insumo_id": None,
                "insumo_comprado": ("Sin insumo disponible" if not candidatos_ins
                                    else "Sin precios disponibles"),
                "cantidad_usada": unidad_display,
                "costo_parcial": 0.0,
                "peso_usado_g": 0.0,
                "error": error_txt,
                "es_prediccion": False,
                "es_manual": False,
                "fuente": None,
                "confianza_prediccion": None,
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
            # COM-37: cuántos ingredientes se costearon con precio manual (insumo o legacy)
            "ingredientes_manuales": sum(1 for d in detalle_costos if d.get('es_manual', False)),
            # COM-37 v2/v5: regla de negocio: solo recetas con precios completos entran
            # al flujo del comedor (propuestas/planificación).
            "precio_completo": sum(1 for d in detalle_costos if d['costo_parcial'] == 0) == 0
        }
    except Exception as e:
        print(f"Error en el motor de optimización: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    finally:
        if cur: cur.close()
        if conn: conn.close()