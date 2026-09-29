"""
nutricion_seed.py
Objetivo: Sembrar la composición nutricional por ingrediente (por 100 g) usada por el
          motor K-means (COM-5) para calcular energía, proteína, hierro y fibra por
          ración. Valores aproximados de las Tablas Peruanas de Composición de Alimentos
          (CENAN/INS), con fines académicos.
Uso: Importado por db_bootstrap.py, que ejecuta `seedar_nutricion(cur)`. Idempotente
     (ON CONFLICT DO NOTHING), puede ejecutarse en cada arranque.
Referencia: ticket COM-5 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""

# (nombre_normalizado, kcal_100g, proteina_g_100g, hierro_mg_100g, fibra_g_100g, gramos_por_unidad)
NUTRICION_INGREDIENTES = [
    # --- Fuentes de proteína permitidas por el comedor (COM-5) ---
    ('pollo', 170.00, 25.00, 1.00, 0.00, 100.00),
    ('gallina', 210.00, 22.00, 1.20, 0.00, 100.00),
    ('huevo', 143.00, 12.60, 1.80, 0.00, 55.00),
    ('higado de res', 136.00, 20.40, 6.50, 0.00, 100.00),
    ('pescado', 130.00, 22.00, 1.00, 0.00, 100.00),
    ('bonito', 150.00, 22.00, 1.20, 0.00, 100.00),
    ('jurel', 130.00, 22.00, 1.40, 0.00, 100.00),
    ('atun', 130.00, 26.00, 1.00, 0.00, 100.00),
    ('trucha', 140.00, 20.00, 0.70, 0.00, 100.00),
    ('sangrecita', 95.00, 19.00, 40.00, 0.00, 100.00),
    # --- Granos y carbohidratos base ---
    ('arroz', 355.00, 7.00, 0.80, 1.00, 100.00),
    ('fideos', 370.00, 12.00, 1.50, 3.00, 100.00),
    ('tallarines', 370.00, 12.00, 1.50, 3.00, 100.00),
    ('pan', 265.00, 9.00, 1.50, 3.00, 60.00),
    ('papa', 77.00, 2.00, 0.80, 2.00, 100.00),
    ('camote', 86.00, 1.60, 0.70, 3.00, 100.00),
    ('yuca', 140.00, 1.40, 0.40, 1.80, 100.00),
    ('quinua', 368.00, 14.00, 8.00, 7.00, 100.00),
    ('avena', 380.00, 13.00, 4.30, 10.00, 100.00),
    ('choclo', 110.00, 3.20, 0.50, 2.70, 100.00),
    ('platano', 89.00, 1.10, 0.30, 2.60, 120.00),
    # --- Menestras (hierro no hemo + fibra) ---
    ('frejol castilla', 330.00, 22.00, 7.00, 15.00, 100.00),
    ('frejol', 330.00, 22.00, 7.00, 15.00, 100.00),
    ('lenteja', 350.00, 24.00, 7.50, 11.00, 100.00),
    ('garbanzo', 360.00, 19.00, 6.00, 12.00, 100.00),
    ('arveja', 81.00, 5.40, 1.50, 5.00, 100.00),
    ('habas', 88.00, 7.90, 1.50, 5.00, 100.00),
    # --- Verduras y hortalizas ---
    ('cebolla', 40.00, 1.10, 0.40, 1.70, 100.00),
    ('tomate', 18.00, 0.90, 0.40, 1.20, 100.00),
    ('zanahoria', 41.00, 0.90, 0.30, 2.80, 100.00),
    ('zapallo', 30.00, 1.00, 0.40, 1.50, 100.00),
    ('espinaca', 23.00, 2.90, 2.70, 2.20, 100.00),
    ('acelga', 19.00, 1.80, 2.30, 1.60, 100.00),
    ('lechuga', 15.00, 1.40, 0.90, 1.30, 100.00),
    ('ajo', 149.00, 6.40, 1.70, 2.10, 5.00),
    ('aji amarillo', 60.00, 1.50, 1.00, 1.50, 20.00),
    ('limon', 29.00, 1.10, 0.60, 2.80, 60.00),
    ('naranja', 47.00, 0.90, 0.10, 2.40, 130.00),
    # --- Lácteos, grasas y otros ---
    ('leche evaporada', 134.00, 6.80, 0.20, 0.00, 100.00),
    ('queso', 350.00, 25.00, 0.40, 0.00, 100.00),
    ('aceite', 884.00, 0.00, 0.50, 0.00, 15.00),
    ('azucar', 387.00, 0.00, 0.40, 0.00, 10.00),
]


def seedar_nutricion(cur):
    """
    COM-5: Inserta la composición nutricional base si aún no existe. Idempotente.
    Retorna el número de filas insertadas. El caller es responsable del commit.
    """
    insertadas = 0
    for (nombre, kcal, prot, hierro, fibra, g_und) in NUTRICION_INGREDIENTES:
        cur.execute("""
            INSERT INTO ingredientes_nutricion
                (nombre_normalizado, energia_kcal_100g, proteina_g_100g,
                 hierro_mg_100g, fibra_g_100g, gramos_por_unidad)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (nombre_normalizado) DO NOTHING;
        """, (nombre, kcal, prot, hierro, fibra, g_und))
        insertadas += cur.rowcount
    return insertadas