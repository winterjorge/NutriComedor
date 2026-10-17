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
- COM-48: cada fila del detalle expone componente_nombre/componente_orden para el
  desglose agrupado del modal de Evaluar.
- COM-49: multiplicación explícita y auditable gramos_por_unidad × cantidad; detalle
  con factores de auditoría (gramos_totales, ppg, precio/unidad de compra, fuente);
  subtotal y costo por ración con costo SIN piso de 0.10 (el piso queda como
  referencia de compra en costo_parcial_compra / costo_total_receta_compra).
- COM-49 v2: FIX del TypeError "unsupported operand type(s) for *: 'decimal.Decimal'
  and 'float'". psycopg2 devuelve las columnas NUMERIC como decimal.Decimal; la
  equivalencia leída de ingredientes_equivalencias (gramos_por_unidad_uso,
  NUMERIC(12,4)) se castea EXPLÍCITAMENTE a float antes de multiplicar. Se blindan
  con float() todos los valores NUMERIC que entran al cálculo por si alguna ruta
  los devuelve sin castear. K-means/Greedy no requerían cambio (sus mapas ya
  casteaban al construirse).
- COM-80 (este archivo): el costeo por línea PREFIERE al insumo marcado
  es_principal=True cuando éste tiene precio/predicción en la fecha (decisión
  explícita del Admin), en lugar del mínimo costo por gramo entre todos los
  insumos del ingrediente. Sin principal marcado, el comportamiento es idéntico
  a COM-49 v2 (mínimo costo). Cada línea del detalle expone 'insumo_es_principal'
  para auditoría del modal de Evaluar.
- COM-84 (este archivo): FIX del falso "Costo incompleto" en el modal Evaluar.
  Los contadores ingredientes_con_precio / ingredientes_sin_precio / precio_completo
  se calculaban con `costo_parcial == 0`, pero costo_parcial está REDONDEADO a 2
  decimales: líneas con precio real cuyo costo es menor a un céntimo (ej. 1 g de
  sal yodada a S/ 0.0010/g = S/ 0.001 -> S/ 0.00) eran contadas como "sin precio",
  mostrando el banner "Costo incompleto (N ingrediente(s) sin precio)" y dejando
  precio_completo=False (la receta quedaba excluida de propuestas pese a estar
  costeada). Ahora cada línea del detalle expone el flag `tiene_precio`
  (True si hubo fuente de precio: SCRAPER_DIA/MANUAL_PERIODO/PREDICHO/
  SCRAPER_ULTIMO/LEGACY_INGREDIENTE; False solo si mejor is None) y los contadores
  y precio_completo usan ese flag. El costo total NO cambia (ya sumaba costo_crudo
  sin redondeo). Ninguna clave existente se elimina ni renombra.
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
    obtener_equivalencia,
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
    if len(registros) < 5:
        return None, 0, False
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import r2_score
        X = np.array([[i] for i in range(len(registros))])
        y = np.array([float(r['precio_prom']) for r in registros])
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
        return round(float(precio_predicho), 2), round(confianza, 1), True
    except ImportError:
        precio_promedio = sum(float(r['precio_prom']) for r in registros) / len(registros)
        return round(precio_promedio, 2), 50.0, True


def calcular_costo_receta(receta_id: int, fecha_evaluacion: str):
    """
    Calcula el costo real de una receta considerando:
    1. La unidad de medida de USO de cada línea y su componente (COM-48)
    2. El número de raciones que produce la receta (costo total / raciones)
    COM-49: costeo auditable por línea:
        gramos_totales = gramos_por_unidad_uso(equivalencia o estándar) × cantidad
        costo_linea    = gramos_totales × ppg (S/ por gramo del insumo elegido)
    COM-49 v2: todos los valores NUMERIC leídos de la BD se castea a float antes de
    operar (psycopg2 devuelve decimal.Decimal y Decimal*float lanza TypeError).
    El subtotal y el costo por ración usan el costo SIN piso de 0.10; el valor con
    piso se expone aparte como referencia de compra.
    COM-80: entre los insumos con precio de la línea, se PREFIERE al marcado
    es_principal=True (si lo hay y tiene precio); solo si no existe principal con
    precio se usa el de mínimo costo (comportamiento COM-49 v2).
    COM-84: cada línea expone `tiene_precio` (presencia de fuente de precio) y los
    contadores de completitud (ingredientes_con_precio / ingredientes_sin_precio /
    precio_completo) se calculan con ese flag, NO con costo_parcial redondeado
    (antes una línea de S/ 0.001 redondeada a S/ 0.00 contaba como "sin precio").
    """
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT raciones FROM recetas_almuerzo WHERE id = %s
        """, (receta_id,))
        receta_info = cur.fetchone()
        if not receta_info:
            return {"error": "La receta no existe"}
        raciones_receta = receta_info['raciones'] if receta_info['raciones'] and receta_info['raciones'] > 0 else 1

        # COM-48: líneas de receta con componente y unidad de USO
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

        precios_insumo = precios_por_gramo_por_insumo(cur, fecha_evaluacion)
        costo_total_receta = 0.0          # COM-49: suma de costos SIN piso
        costo_total_compra = 0.0          # COM-49: suma de costos con piso de 0.10
        detalle_costos = []
        fecha_objetivo = datetime.strptime(fecha_evaluacion, "%Y-%m-%d").date()

        for req in ingredientes_receta:
            unidad_abrev = (req['receta_unidad_abrev'] or '').lower()
            unidad_nombre = req['receta_unidad_nombre'] or ''
            # COM-49 v2: cast explícito de NUMERIC a float
            cantidad_requerida = float(req['cantidad_requerida'])
            factor_receta = float(req['receta_factor_a_base'])
            peso_estimado_base = float(req['peso_estimado_g'])
            unidad_display = f"{cantidad_requerida} {unidad_nombre.lower()}"

            # COM-80: se expone es_principal para la preferencia de costeo
            cur.execute("""
                SELECT ins.id AS insumo_id, ins.nombre AS insumo_nombre, ins.origen,
                       ins.es_principal,
                       um.abreviatura AS u_abrev, um.tipo_magnitud AS u_tipo, um.factor_a_base AS u_factor
                FROM insumos ins
                JOIN unidades_medida um ON um.id = ins.unidad_medida_id
                WHERE ins.ingrediente_id = %s;
            """, (req['ingrediente_id'],))
            insumos_rows = cur.fetchall()

            mejor = None
            mejor_principal = None   # COM-80
            for ins in insumos_rows:
                opc = precios_insumo.get(ins['insumo_id'])
                confianza = None
                if opc:
                    ppg = float(opc['ppg'])
                    fuente = opc['fuente']
                    precio_unidad_compra = opc.get('precio_por_unidad')
                    unidad_compra = opc.get('unidad_compra_abrev')
                else:
                    pred, conf, ok = predecir_precio_con_confianza(ins['insumo_id'], fecha_objetivo, conn, cur)
                    if not (ok and pred):
                        continue
                    g_compra = gramos_por_unidad_compra(
                        ins['u_abrev'], ins['u_tipo'], float(ins['u_factor']), peso_estimado_base)
                    if g_compra <= 0:
                        continue
                    ppg = float(pred) / g_compra
                    fuente = 'PREDICHO'
                    confianza = conf
                    precio_unidad_compra = pred
                    unidad_compra = ins['u_abrev']
                # COM-49 v2 (FIX): la equivalencia viene como decimal.Decimal desde
                # psycopg2 (NUMERIC); se castea a float antes de cualquier operación.
                # COM-49 v1 (trazabilidad): línea anterior sin cast, comentada:
                # gramos_por_unidad = eq['gramos_por_unidad_uso'] if eq else gramos_por_unidad_uso(...)
                eq = obtener_equivalencia(
                    cur, req['ingrediente_id'], ins['insumo_id'], req['receta_unidad_medida_id'])
                gramos_por_unidad = float(eq['gramos_por_unidad_uso']) if eq else gramos_por_unidad_uso(
                    cur, req['ingrediente_id'], ins['insumo_id'], req['receta_unidad_medida_id'],
                    unidad_abrev, req['receta_tipo_magnitud'], factor_receta, peso_estimado_base)
                gramos_totales = float(gramos_por_unidad) * cantidad_requerida
                costo_sin_redondear = gramos_totales * ppg
                costo_linea_compra = redondear_hacia_arriba_010(costo_sin_redondear)
                cand = {
                    'insumo_id': ins['insumo_id'],
                    'insumo_nombre': ins['insumo_nombre'],
                    'ppg': ppg,
                    'fuente': fuente,
                    'confianza': confianza,
                    'precio_unidad_compra': precio_unidad_compra,
                    'unidad_compra': unidad_compra,
                    'gramos_por_unidad': gramos_por_unidad,
                    'gramos_totales': gramos_totales,
                    'costo_crudo': costo_sin_redondear,
                    'costo_compra': costo_linea_compra,
                    'equivalencia_usada': bool(eq),
                    # COM-80: flag de principalidad para auditoría y preferencia
                    'es_principal': bool(ins['es_principal']),
                }
                # COM-80: el principal con precio se registra aparte (gana si existe)
                if cand['es_principal']:
                    if mejor_principal is None or costo_sin_redondear < mejor_principal['costo_crudo']:
                        mejor_principal = cand
                if mejor is None or costo_sin_redondear < mejor['costo_crudo']:
                    mejor = cand
            # COM-80: preferencia explícita del Admin sobre el mínimo costo
            if mejor_principal is not None:
                mejor = mejor_principal

            # COM-37 v5: fallback legacy si ningún insumo candidato tuvo precio/predicción
            if mejor is None:
                legacy = mejor_opcion_ingrediente(cur, req['ingrediente_id'], fecha_objetivo, precios_insumo)
                if legacy and legacy['fuente'] == 'LEGACY_INGREDIENTE':
                    gramos_por_unidad = gramos_por_unidad_uso(
                        cur, req['ingrediente_id'], None, req['receta_unidad_medida_id'],
                        unidad_abrev, req['receta_tipo_magnitud'], factor_receta, peso_estimado_base)
                    gramos_totales = float(gramos_por_unidad) * cantidad_requerida
                    costo_sin_redondear = gramos_totales * float(legacy['ppg'])
                    mejor = {
                        'insumo_id': None,
                        'insumo_nombre': legacy['insumo_nombre'],
                        'ppg': float(legacy['ppg']),
                        'fuente': 'LEGACY_INGREDIENTE',
                        'confianza': None,
                        'precio_unidad_compra': legacy.get('precio_por_unidad'),
                        'unidad_compra': legacy.get('unidad_compra_abrev'),
                        'gramos_por_unidad': gramos_por_unidad,
                        'gramos_totales': gramos_totales,
                        'costo_crudo': costo_sin_redondear,
                        'costo_compra': redondear_hacia_arriba_010(costo_sin_redondear),
                        'equivalencia_usada': False,
                        'es_principal': False,
                    }

            componente_nombre = req['componente_nombre'] or 'Plato de fondo'
            componente_orden = req['componente_orden'] if req['componente_orden'] is not None else 99

            if mejor is None:
                detalle_costos.append({
                    "ingrediente": req['ingrediente_nombre'],
                    "ingrediente_id": req['ingrediente_id'],
                    "componente_nombre": componente_nombre,
                    "componente_orden": componente_orden,
                    "insumo_comprado": "Sin insumo disponible" if not insumos_rows else "Sin precios disponibles",
                    "cantidad_usada": unidad_display,
                    "costo_parcial": 0.0,
                    "costo_parcial_compra": 0.0,
                    "peso_usado_g": 0.0,
                    "error": "Sin insumos disponibles" if not insumos_rows else "Sin precios para esta fecha",
                    "es_prediccion": False,
                    "es_manual": False,
                    # COM-80: conservado por compatibilidad
                    "insumo_es_principal": False,
                    # COM-84: sin fuente de precio para esta línea
                    "tiene_precio": False,
                })
                continue

            # COM-49: el subtotal analítico usa el costo SIN piso de 0.10
            costo_total_receta += mejor['costo_crudo']
            costo_total_compra += mejor['costo_compra']
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
                "componente_nombre": componente_nombre,
                "componente_orden": componente_orden,
                "insumo_comprado": insumo_display,
                "cantidad_usada": unidad_display,
                # COM-49: costo analítico (sin piso) y costo de compra (con piso 0.10)
                "costo_parcial": round(mejor['costo_crudo'], 2),
                "costo_parcial_compra": round(mejor['costo_compra'], 2),
                "peso_usado_g": round(mejor['gramos_totales'], 2),
                # COM-49: factores de auditoría del costeo
                "cantidad": cantidad_requerida,
                "unidad_uso_abrev": req['receta_unidad_abrev'],
                "gramos_por_unidad": round(float(mejor['gramos_por_unidad']), 4),
                "gramos_totales": round(float(mejor['gramos_totales']), 2),
                "ppg": round(float(mejor['ppg']), 6),
                "precio_por_unidad_compra": (round(float(mejor['precio_unidad_compra']), 2)
                                             if mejor['precio_unidad_compra'] is not None else None),
                "unidad_compra_abrev": mejor['unidad_compra'],
                "equivalencia_usada": mejor['equivalencia_usada'],
                "fuente_precio": mejor['fuente'],
                "es_prediccion": es_prediccion,
                "es_manual": es_manual,
                "confianza_prediccion": f"{mejor['confianza']}%" if es_prediccion else None,
                # COM-80: auditoría de si la línea usó el insumo principal
                "insumo_es_principal": bool(mejor.get('es_principal', False)),
                # COM-84: esta línea SÍ tiene fuente de precio (aunque su costo
                # redondeado sea S/ 0.00 por ser menor a un céntimo, ej. sal yodada)
                "tiene_precio": True,
            })

        costo_por_racion = costo_total_receta / raciones_receta
        return {
            "receta_id": receta_id,
            "fecha_calculo": fecha_evaluacion,
            "raciones_receta": raciones_receta,
            "costo_total_receta": round(costo_total_receta, 2),
            "costo_total_racion": round(costo_por_racion, 2),
            # COM-49: total bajo la regla de compra con piso de 0.10 (referencial)
            "costo_total_receta_compra": round(costo_total_compra, 2),
            "costo_total_racion_compra": round(costo_total_compra / raciones_receta, 2),
            "detalle_insumos": detalle_costos,
            "total_ingredientes": len(detalle_costos),
            # COM-84 (FIX): contadores de completitud basados en `tiene_precio`
            # (presencia de fuente de precio), NO en costo_parcial redondeado.
            # COM-49 (trazabilidad): cálculo anterior, comentado porque una línea
            # con costo real < S/ 0.005 redondeaba a 0.00 y contaba como "sin precio":
            #   "ingredientes_con_precio": sum(1 for d in detalle_costos if d['costo_parcial'] > 0),
            #   "ingredientes_sin_precio": sum(1 for d in detalle_costos if d['costo_parcial'] == 0),
            #   "precio_completo": sum(1 for d in detalle_costos if d['costo_parcial'] == 0) == 0,
            "ingredientes_con_precio": sum(1 for d in detalle_costos if d['tiene_precio']),
            "ingredientes_sin_precio": sum(1 for d in detalle_costos if not d['tiene_precio']),
            "ingredientes_predichos": sum(1 for d in detalle_costos if d.get('es_prediccion', False)),
            "ingredientes_manuales": sum(1 for d in detalle_costos if d.get('es_manual', False)),
            "precio_completo": sum(1 for d in detalle_costos if not d['tiene_precio']) == 0,
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