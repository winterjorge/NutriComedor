from ..utils.logger import log

def clasificar_heuristica_mejorada(nombre_insumo, mapa_categorias):
    """
    MOTOR HEURÍSTICO MEJORADO - Clasificación inteligente de insumos.
    Usa múltiples estrategias de matching para asignar categorías.
    
    Args:
        nombre_insumo: Nombre del insumo comercial
        mapa_categorias: Diccionario {nombre_categoria: id_categoria}
    
    Returns:
        Tupla (nombre_generico, id_categoria) o (None, None) si no se puede clasificar
    """
    nombre_lower = nombre_insumo.lower().strip()
    
    # Reglas de clasificación organizadas por categoría
    reglas = _obtener_reglas_clasificacion()
    
    # Estrategia 1: Matching exacto de palabras clave
    for clave, gen_nombre, cat_nombre in reglas:
        if clave in nombre_lower:
            return gen_nombre, mapa_categorias.get(cat_nombre)
    
    # Estrategia 2: Matching por raíz de palabra (último intento)
    palabras_clave = nombre_lower.split()
    for palabra in palabras_clave:
        for clave, gen_nombre, cat_nombre in reglas:
            if palabra == clave or palabra.startswith(clave[:4]):
                return gen_nombre, mapa_categorias.get(cat_nombre)
    
    return None, None

def _obtener_reglas_clasificacion():
    """
    Retorna la lista de reglas de clasificación heurística.
    Formato: (palabra_clave, nombre_generico, categoria)
    """
    return [
        # Proteínas
        ('pollo', 'Pollo', 'Proteinas'),
        ('gallina', 'Pollo', 'Proteinas'),
        ('pavo', 'Pollo', 'Proteinas'),
        ('res', 'Carne de Res', 'Proteinas'),
        ('vacuno', 'Carne de Res', 'Proteinas'),
        ('carne res', 'Carne de Res', 'Proteinas'),
        ('cerdo', 'Carne de Cerdo', 'Proteinas'),
        ('chancho', 'Carne de Cerdo', 'Proteinas'),
        ('pescado', 'Pescado', 'Proteinas'),
        ('jurel', 'Pescado', 'Proteinas'),
        ('bonito', 'Pescado', 'Proteinas'),
        ('caballa', 'Pescado', 'Proteinas'),
        ('perico', 'Pescado', 'Proteinas'),
        ('huevo', 'Huevo', 'Proteinas'),
        ('huevos', 'Huevo', 'Proteinas'),
        ('lenteja', 'Lentejas', 'Proteinas'),
        ('lentejas', 'Lentejas', 'Proteinas'),
        ('frijol', 'Frijol', 'Proteinas'),
        ('frijoles', 'Frijol', 'Proteinas'),
        ('frejol', 'Frijol', 'Proteinas'),
        ('frejoles', 'Frijol', 'Proteinas'),
        ('arveja', 'Arvejas', 'Proteinas'),
        ('arvejas', 'Arvejas', 'Proteinas'),
        ('garbanzo', 'Garbanzo', 'Proteinas'),
        ('garbanzos', 'Garbanzo', 'Proteinas'),
        ('haba', 'Habas', 'Proteinas'),
        ('habas', 'Habas', 'Proteinas'),
        ('tarwi', 'Tarwi', 'Proteinas'),
        ('chocho', 'Tarwi', 'Proteinas'),
        
        # Cereales y Tubérculos
        ('arroz', 'Arroz', 'Cereales, Tuberculos y Raices'),
        ('papa', 'Papa', 'Cereales, Tuberculos y Raices'),
        ('papas', 'Papa', 'Cereales, Tuberculos y Raices'),
        ('camote', 'Camote', 'Cereales, Tuberculos y Raices'),
        ('yuca', 'Yuca', 'Cereales, Tuberculos y Raices'),
        ('mandioca', 'Yuca', 'Cereales, Tuberculos y Raices'),
        ('fideo', 'Fideo', 'Cereales, Tuberculos y Raices'),
        ('fideos', 'Fideo', 'Cereales, Tuberculos y Raices'),
        ('tallarin', 'Tallarin', 'Cereales, Tuberculos y Raices'),
        ('tallarines', 'Tallarin', 'Cereales, Tuberculos y Raices'),
        ('quinua', 'Quinua', 'Cereales, Tuberculos y Raices'),
        ('avena', 'Avena', 'Cereales, Tuberculos y Raices'),
        ('trigo', 'Trigo', 'Cereales, Tuberculos y Raices'),
        ('mote', 'Mote de maiz', 'Cereales, Tuberculos y Raices'),
        ('maiz', 'Mote de maiz', 'Cereales, Tuberculos y Raices'),
        ('maíz', 'Mote de maiz', 'Cereales, Tuberculos y Raices'),
        ('choclo', 'Choclo', 'Cereales, Tuberculos y Raices'),
        ('olluco', 'Olluco', 'Cereales, Tuberculos y Raices'),
        ('ollucos', 'Olluco', 'Cereales, Tuberculos y Raices'),
        ('oca', 'Oca', 'Cereales, Tuberculos y Raices'),
        ('mashua', 'Mashua', 'Cereales, Tuberculos y Raices'),
        
        # Vegetales y Hortalizas
        ('cebolla', 'Cebolla', 'Vegetales y Hortalizas'),
        ('zanahoria', 'Zanahoria', 'Vegetales y Hortalizas'),
        ('tomate', 'Tomate', 'Vegetales y Hortalizas'),
        ('tomates', 'Tomate', 'Vegetales y Hortalizas'),
        ('pimenton', 'Pimenton', 'Vegetales y Hortalizas'),
        ('pimiento', 'Pimenton', 'Vegetales y Hortalizas'),
        ('pimientos', 'Pimenton', 'Vegetales y Hortalizas'),
        ('aji', 'Aji', 'Vegetales y Hortalizas'),
        ('ají', 'Aji', 'Vegetales y Hortalizas'),
        ('lechuga', 'Lechuga', 'Vegetales y Hortalizas'),
        ('espinaca', 'Espinaca', 'Vegetales y Hortalizas'),
        ('zapallo', 'Zapallo', 'Vegetales y Hortalizas'),
        ('caigua', 'Caigua', 'Vegetales y Hortalizas'),
        ('caiguas', 'Caigua', 'Vegetales y Hortalizas'),
        ('brocoli', 'Brocoli', 'Vegetales y Hortalizas'),
        ('brócoli', 'Brocoli', 'Vegetales y Hortalizas'),
        ('coliflor', 'Brocoli', 'Vegetales y Hortalizas'),
        ('apio', 'Apio', 'Vegetales y Hortalizas'),
        ('vainita', 'Vainitas', 'Vegetales y Hortalizas'),
        ('vainitas', 'Vainitas', 'Vegetales y Hortalizas'),
        ('haba verde', 'Habas verdes', 'Vegetales y Hortalizas'),
        ('habas verdes', 'Habas verdes', 'Vegetales y Hortalizas'),
        ('pepino', 'Pepino', 'Vegetales y Hortalizas'),
        ('betarraga', 'Betarraga', 'Vegetales y Hortalizas'),
        ('repollo', 'Repollo', 'Vegetales y Hortalizas'),
        ('col', 'Repollo', 'Vegetales y Hortalizas'),
        ('nabo', 'Nabo', 'Vegetales y Hortalizas'),
        ('rabano', 'Rabano', 'Vegetales y Hortalizas'),
        ('rábano', 'Rabano', 'Vegetales y Hortalizas'),
        
        # Frutas
        ('limon', 'Limon', 'Frutas'),
        ('limón', 'Limon', 'Frutas'),
        ('lima', 'Limon', 'Frutas'),
        ('naranja', 'Naranja', 'Frutas'),
        ('manzana', 'Manzana', 'Frutas'),
        ('platano', 'Platano', 'Frutas'),
        ('plátano', 'Platano', 'Frutas'),
        ('banana', 'Platano', 'Frutas'),
        ('pasas', 'Pasas', 'Frutas'),
        ('uva', 'Uva', 'Frutas'),
        ('uvas', 'Uva', 'Frutas'),
        ('pera', 'Pera', 'Frutas'),
        ('durazno', 'Durazno', 'Frutas'),
        ('melocoton', 'Durazno', 'Frutas'),
        ('melocotón', 'Durazno', 'Frutas'),
        
        # Lácteos
        ('leche', 'Leche', 'Lacteos y derivados'),
        ('queso', 'Queso', 'Lacteos y derivados'),
        ('yogur', 'Yogur', 'Lacteos y derivados'),
        ('yogurt', 'Yogur', 'Lacteos y derivados'),
        ('pan', 'Pan', 'Lacteos y derivados'),
        
        # Grasas
        ('aceite', 'Aceite vegetal', 'Grasas saludables y Aceites'),
        ('manteca', 'Aceite vegetal', 'Grasas saludables y Aceites'),
        ('aceituna', 'Aceituna', 'Grasas saludables y Aceites'),
        ('aceitunas', 'Aceituna', 'Grasas saludables y Aceites'),
        ('palta', 'Palta', 'Grasas saludables y Aceites'),
        ('aguacate', 'Palta', 'Grasas saludables y Aceites'),
        
        # Condimentos
        ('sal', 'Sal yodada', 'Condimentos y Otros'),
        ('azucar', 'Azucar', 'Condimentos y Otros'),
        ('azúcar', 'Azucar', 'Condimentos y Otros'),
        ('ajo', 'Ajo', 'Condimentos y Otros'),
        ('ajos', 'Ajo', 'Condimentos y Otros'),
        ('pimienta', 'Pimienta', 'Condimentos y Otros'),
        ('comino', 'Comino', 'Condimentos y Otros'),
        ('oregano', 'Oregano', 'Condimentos y Otros'),
        ('orégano', 'Oregano', 'Condimentos y Otros'),
        ('laurel', 'Laurel', 'Condimentos y Otros'),
        ('palillo', 'Palillo', 'Condimentos y Otros'),
        ('achiote', 'Palillo', 'Condimentos y Otros'),
        ('perejil', 'Perejil', 'Condimentos y Otros'),
        ('cilantro', 'Cilantro', 'Condimentos y Otros'),
        ('hierbabuena', 'Hierbabuena', 'Condimentos y Otros'),
        ('hierba buena', 'Hierbabuena', 'Condimentos y Otros'),
        ('kion', 'Kion', 'Condimentos y Otros'),
        ('jengibre', 'Kion', 'Condimentos y Otros'),
        ('sillao', 'Sillao', 'Condimentos y Otros'),
        ('salsa soya', 'Sillao', 'Condimentos y Otros'),
        ('vinagre', 'Vinagre', 'Condimentos y Otros'),
        ('mostaza', 'Mostaza', 'Condimentos y Otros'),
        ('ketchup', 'Ketchup', 'Condimentos y Otros'),
        ('salsa tomate', 'Ketchup', 'Condimentos y Otros'),
        ('salsa de tomate', 'Ketchup', 'Condimentos y Otros'),
    ]