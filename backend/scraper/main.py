import argparse
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from .config import TIMEZONE
from .utils.logger import log
from .database.db_handler import DatabaseHandler
from .extractors.sisap_extractor import SISAPExtractor

def ejecutar_scraper(fecha_ejecucion=None):
    """
    Función principal que orquesta todo el proceso de scraping.
    """
    if fecha_ejecucion is None:
        fecha_ejecucion = datetime.now(TIMEZONE)
    
    log("=" * 60)
    log(f"Iniciando proceso de scraping para fecha: {fecha_ejecucion.strftime('%Y-%m-%d')}")
    log("=" * 60)
    
    # Inicializar componentes
    db_handler = DatabaseHandler()
    extractor = SISAPExtractor()
    
    try:
        # 1. Conectar a la base de datos
        if not db_handler.connect():
            log("No se pudo conectar a la base de datos. Terminando ejecución.", nivel="ERROR")
            return False
        
        # 2. Cargar datos maestros
        log("Cargando datos maestros...")
        datos_maestros = db_handler.cargar_datos_maestros()
        
        if not datos_maestros:
            log("No se pudieron cargar los datos maestros. Terminando ejecución.", nivel="ERROR")
            return False
        
        log(f"Datos maestros cargados: {len(datos_maestros['categorias'])} categorías, {len(datos_maestros['ingredientes'])} ingredientes")
        
        # 3. Extraer precios de la API
        log("Consultando API del SISAP...")
        html_content, fecha_db = extractor.obtener_precios_api(fecha_ejecucion)
        
        if not html_content:
            log("No se obtuvo contenido HTML de la API. Terminando ejecución.", nivel="ERROR")
            return False
        
        # 4. Procesar HTML y extraer registros
        log("Procesando HTML...")
        registros_crudos = extractor.procesar_html(html_content, fecha_db)
        
        if not registros_crudos:
            log("No se extrajeron registros válidos del HTML. Terminando ejecución.", nivel="WARNING")
            return False
        
        # 5. Clasificar y procesar insumos
        log("Clasificando insumos...")
        registros_historial = db_handler.procesar_y_clasificar_insumos(registros_crudos, datos_maestros)
        
        # 6. Guardar historial de precios
        log("Guardando historial de precios...")
        db_handler.guardar_historial_precios(registros_historial)
        
        log("=" * 60)
        log("Proceso de scraping completado exitosamente")
        log("=" * 60)
        return True
        
    except Exception as e:
        log(f"ERROR CRÍTICO: {str(e)}\n{traceback.format_exc()}", nivel="ERROR")
        return False
    
    finally:
        # Asegurar que se cierre la conexión
        db_handler.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper de precios SISAP")
    parser.add_argument("--fecha", type=str, help="Fecha en formato YYYY-MM-DD (opcional, default: hoy)")
    args = parser.parse_args()
    
    if args.fecha:
        try:
            fecha_ejecucion = datetime.strptime(args.fecha, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
        except ValueError:
            log(f"Formato de fecha inválido: {args.fecha}. Use YYYY-MM-DD", nivel="ERROR")
            exit(1)
    else:
        fecha_ejecucion = datetime.now(TIMEZONE)
    
    exito = ejecutar_scraper(fecha_ejecucion)
    exit(0 if exito else 1)