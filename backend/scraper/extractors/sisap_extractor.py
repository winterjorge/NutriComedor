import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ..config import SISAP_API_URL, SISAP_PRODUCT_IDS, HTTP_HEADERS, TIMEZONE
from ..utils.logger import log
from ..utils.normalizer import normalizar_nombre, formatear_precio

class SISAPExtractor:
    """Extractor de precios del sistema SISAP del MIDAGRI"""
    
    def __init__(self):
        self.headers = HTTP_HEADERS
    
    def construir_payload(self, fecha_objetivo):
        """Construye el payload para la API del SISAP - SIN ESPACIOS"""
        fecha_str_api = fecha_objetivo.strftime("%d/%m/%Y")
        anio = fecha_objetivo.strftime("%Y")
        mes = fecha_objetivo.strftime("%m")
        semana = str(fecha_objetivo.isocalendar()[1])
        
        productos_str = "&".join([f"productos[]={p}" for p in SISAP_PRODUCT_IDS])
        
        payload = (
            f"mercado=*&variables[]=precio_max&variables[]=precio_prom&variables[]=precio_min"
            f"&fecha={fecha_str_api}&desde={fecha_str_api}&hasta={fecha_str_api}"
            f"&anios[]={anio}&meses[]={mes}&semanas[]={semana}"
            f"&{productos_str}&periodicidad=dia&__ajax_carga_final=consulta&ajax=true"
        )
        
        return payload
    
    def obtener_precios_api(self, fecha_objetivo):
        """
        Consulta la API del SISAP para obtener los precios de la fecha objetivo.
        """
        log(f"Iniciando consulta API para la fecha: {fecha_objetivo.strftime('%Y-%m-%d')}")
        
        payload = self.construir_payload(fecha_objetivo)
        
        try:
            response = requests.post(
                SISAP_API_URL, 
                data=payload, 
                headers=self.headers, 
                timeout=30
            )
            response.raise_for_status()
            log(f"Conexión exitosa. Código HTTP: {response.status_code}")
            log(f"Tamaño de la respuesta: {len(response.text)} bytes")
            
            return response.text, fecha_objetivo.strftime("%Y-%m-%d")
        except Exception as e:
            log(f"Error en conexión API: {e}", nivel="ERROR")
            return None, None
    
    def procesar_html(self, html_content, fecha_db):
        """
        Procesa el HTML de la respuesta y extrae los registros de precios.
        CORRECCIÓN: Usa SOLO la columna 'Variedad' como nombre del insumo.
        La columna 'Producto' solo se usa para clasificación en categorías.
        """
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        tabla = soup.find('table')
        
        if not tabla:
            log("ERROR: No se encontró tabla en la respuesta HTML", nivel="ERROR")
            return []
        
        # Buscar todas las filas
        todas_filas = tabla.find_all('tr')
        
        # Filtrar filas con clase 'contenido'
        filas = []
        for fila in todas_filas:
            clase = fila.get('class', [])
            if isinstance(clase, list) and 'contenido' in clase:
                filas.append(fila)
            elif isinstance(clase, str) and 'contenido' in clase:
                filas.append(fila)
        
        if not filas:
            return []
        
        log(f"Se encontraron {len(filas)} filas con clase 'contenido'")
        
        registros_a_insertar = []
        mercado_origen = "SISAP"
        producto_actual = None
        
        for fila in filas:
            columnas = fila.find_all('td')
            cantidad_cols = len(columnas)
            
            if cantidad_cols < 4:
                continue
            
            try:
                # Si hay 5 columnas, la primera es el Producto (con rowspan)
                # Si hay 4 columnas, el Producto viene del rowspan anterior
                if cantidad_cols == 5:
                    producto_actual = columnas[0].text.strip()
                    variedad = columnas[1].text.strip()
                    idx_max, idx_prom, idx_min = 2, 3, 4
                else:
                    # cantidad_cols == 4, usar producto_actual del rowspan
                    variedad = columnas[0].text.strip()
                    idx_max, idx_prom, idx_min = 1, 2, 3
                
                # CORRECCIÓN CLAVE: Usar SOLO la variedad como nombre del insumo
                # El producto se usa solo para clasificación
                nombre_insumo = variedad
                
                # Normalizar: primera letra mayúscula, sin tildes, conservando ñ
                nombre_limpio = normalizar_nombre(nombre_insumo)
                p_max = formatear_precio(columnas[idx_max].text.strip())
                p_prom = formatear_precio(columnas[idx_prom].text.strip())
                p_min = formatear_precio(columnas[idx_min].text.strip())
                
                # Solo registrar si hay precio válido
                if p_prom > 0:
                    registros_a_insertar.append((
                        nombre_limpio, 
                        fecha_db, 
                        mercado_origen, 
                        p_min, 
                        p_prom, 
                        p_max
                    ))
            except Exception as e:
                log(f"Error al procesar fila: {e}", nivel="WARNING")
                continue
        
        log(f"Se extrajeron {len(registros_a_insertar)} registros válidos del HTML")
        return registros_a_insertar