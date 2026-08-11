import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Configuración de base de datos
DB_URL = os.getenv("DATABASE_URL", "postgresql://nutri_admin:Nutri2026Secure!@localhost:5432/nutricomedor")

# Configuración de zona horaria
TIMEZONE = ZoneInfo("America/Lima")

# Configuración de logs
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def get_log_file_path():
    """Genera la ruta del archivo de log con la fecha actual"""
    fecha_actual = datetime.now(TIMEZONE).strftime("%m-%d-%Y")
    return os.path.join(LOG_DIR, f"scraper_{fecha_actual}.log")

LOG_FILE = get_log_file_path()

# Configuración del SISAP
SISAP_API_URL = "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/resumenes/filtrar"

# IDs de productos del SISAP
SISAP_PRODUCT_IDS = [
    "1001", "1018", "0202", "0203", "0204", "0206", "0207", "0401", "0301",
    "1005", "0640", "0209", "0902", "0101", "0212", "0641", "0603", "0403", 
    "0604", "0215", "0216", "0217", "1010", "0607", "0501", "0302", "0502", 
    "0608", "0609", "0303", "1011", "0218", "1105", "1104", "0220", "0504", 
    "0611", "0106", "0404", "0614", "0615", "0617", "0618", "0107", "0620", 
    "0619", "0621", "0622", "0102", "0904", "0408", "0638", "0506", "0305", 
    "0626", "0104", "1014", "0627", "0630", "0224", "0628", "0629", "1301", 
    "0405", "0633", "0306", "0228", "0636", "0637", "0229", "0105", "0230", 
    "0231"
]

# Headers para requests HTTP
HTTP_HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0"
}