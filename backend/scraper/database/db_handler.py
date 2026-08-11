import psycopg2
from psycopg2 import extras
from ..config import DB_URL
from ..utils.logger import log
from ..classifiers.heuristics import clasificar_heuristica_mejorada

class DatabaseHandler:
    """Manejador de operaciones de base de datos para el scraper"""
    
    def __init__(self):
        self.conn = None
        self.cur = None
    
    def connect(self):
        """Establece conexión con la base de datos"""
        try:
            self.conn = psycopg2.connect(DB_URL)
            self.cur = self.conn.cursor()
            log("Conexión a base de datos establecida")
            return True
        except Exception as e:
            log(f"Error al conectar a la base de datos: {e}", nivel="ERROR")
            return False
    
    def disconnect(self):
        """Cierra la conexión con la base de datos"""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
            log("Conexión a base de datos cerrada")
    
    def cargar_datos_maestros(self):
        """
        Carga los datos maestros (categorías, ingredientes, insumos, unidades)
        para el motor heurístico.
        """
        try:
            # Cargar categorías
            self.cur.execute("SELECT nombre, id FROM categorias_alimentos;")
            mapa_categorias = {row[0]: row[1] for row in self.cur.fetchall()}
            
            # Cargar ingredientes
            self.cur.execute("SELECT LOWER(nombre), id FROM ingredientes;")
            mapa_ingredientes = {row[0]: row[1] for row in self.cur.fetchall()}
            
            # Cargar insumos
            self.cur.execute("SELECT LOWER(nombre), id FROM insumos;")
            mapa_insumos = {row[0]: row[1] for row in self.cur.fetchall()}
            
            # Obtener ID de unidad kg
            self.cur.execute("SELECT id FROM unidades_medida WHERE abreviatura = 'kg' LIMIT 1;")
            unidad_res = self.cur.fetchone()
            unidad_kg_id = unidad_res[0] if unidad_res else 1
            
            return {
                'categorias': mapa_categorias,
                'ingredientes': mapa_ingredientes,
                'insumos': mapa_insumos,
                'unidad_kg_id': unidad_kg_id
            }
        except Exception as e:
            log(f"Error al cargar datos maestros: {e}", nivel="ERROR")
            return None
    
    def procesar_y_clasificar_insumos(self, registros_crudos, datos_maestros):
        """
        Procesa los registros crudos, clasifica los insumos y prepara
        los registros para el historial de precios.
        """
        mapa_categorias = datos_maestros['categorias']
        mapa_ingredientes = datos_maestros['ingredientes']
        mapa_insumos = datos_maestros['insumos']
        unidad_kg_id = datos_maestros['unidad_kg_id']
        
        registros_historial = []
        insumos_clasificados = 0
        insumos_sin_clasificar = 0
        
        for reg in registros_crudos:
            nombre, fecha, mercado, p_min, p_prom, p_max = reg
            nombre_lower = nombre.lower()
            
            if nombre_lower not in mapa_insumos:
                # El insumo es nuevo. Usamos la heurística para clasificarlo.
                gen_nombre, cat_id = clasificar_heuristica_mejorada(nombre, mapa_categorias)
                
                ingrediente_final_id = None
                
                if gen_nombre:
                    gen_lower = gen_nombre.lower()
                    if gen_lower in mapa_ingredientes:
                        ingrediente_final_id = mapa_ingredientes[gen_lower]
                    else:
                        # Crear el Ingrediente Genérico automáticamente
                        ingrediente_final_id = self._crear_ingrediente(
                            gen_nombre, cat_id, unidad_kg_id
                        )
                        if ingrediente_final_id:
                            mapa_ingredientes[gen_lower] = ingrediente_final_id
                            log(f"Heurística: Creado ingrediente padre '{gen_nombre}'")
                            insumos_clasificados += 1
                
                # Crear el Insumo Comercial
                insumo_id = self._crear_insumo(
                    nombre, ingrediente_final_id, unidad_kg_id
                )
                
                if insumo_id:
                    mapa_insumos[nombre_lower] = insumo_id
                    
                    if ingrediente_final_id:
                        log(f"Insumo clasificado: '{nombre}' asignado a -> '{gen_nombre}'")
                    else:
                        log(f"Insumo desconocido: '{nombre}' guardado como 'Sin clasificar'", nivel="WARNING")
                        insumos_sin_clasificar += 1
            
            insumo_id = mapa_insumos[nombre_lower]
            registros_historial.append((insumo_id, fecha, mercado, p_min, p_prom, p_max))
        
        log(f"Resumen clasificación: {insumos_clasificados} clasificados, {insumos_sin_clasificar} sin clasificar")
        return registros_historial
    
    def _crear_ingrediente(self, nombre, categoria_id, unidad_medida_id):
        """Crea un nuevo ingrediente genérico en la base de datos"""
        try:
            self.cur.execute("""
                INSERT INTO ingredientes (nombre, categoria_id, unidad_medida_id)
                VALUES (%s, %s, %s) RETURNING id;
            """, (nombre, categoria_id, unidad_medida_id))
            self.conn.commit()
            return self.cur.fetchone()[0]
        except Exception as e:
            log(f"Error al crear ingrediente '{nombre}': {e}", nivel="ERROR")
            self.conn.rollback()
            return None
    
    def _crear_insumo(self, nombre, ingrediente_id, unidad_medida_id):
        """Crea un nuevo insumo comercial en la base de datos"""
        try:
            self.cur.execute("""
                INSERT INTO insumos (nombre, ingrediente_id, unidad_medida_id, kcal_por_unidad, proteinas_por_unidad)
                VALUES (%s, %s, %s, 0.00, 0.00)
                RETURNING id;
            """, (nombre, ingrediente_id, unidad_medida_id))
            self.conn.commit()
            return self.cur.fetchone()[0]
        except Exception as e:
            log(f"Error al crear insumo '{nombre}': {e}", nivel="ERROR")
            self.conn.rollback()
            return None
    
    def guardar_historial_precios(self, registros_historial):
        """
        Guarda o actualiza los registros de historial de precios.
        Usa UPSERT (INSERT ... ON CONFLICT) para evitar duplicados.
        """
        if not registros_historial:
            log("No hay registros de historial para guardar")
            return
        
        query_historial = """
            INSERT INTO historial_precios (insumo_id, fecha, mercado, precio_min, precio_prom, precio_max)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (fecha, insumo_id, mercado)
            DO UPDATE SET
                precio_min = EXCLUDED.precio_min,
                precio_prom = EXCLUDED.precio_prom,
                precio_max = EXCLUDED.precio_max;
        """
        
        try:
            extras.execute_batch(self.cur, query_historial, registros_historial)
            self.conn.commit()
            log(f"Se insertaron o actualizaron correctamente {len(registros_historial)} precios.")
        except Exception as e:
            log(f"Error al guardar historial de precios: {e}", nivel="ERROR")
            self.conn.rollback()