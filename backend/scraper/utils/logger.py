from datetime import datetime
from ..config import LOG_FILE, TIMEZONE

def log(mensaje, nivel="INFO"):
    """
    Escribe un mensaje de log con timestamp y nivel.
    También lo imprime en consola.
    """
    timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{timestamp}] [{nivel}] {mensaje}"
    print(linea)
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception as e:
        print(f"[{timestamp}] [ERROR] No se pudo escribir en el log: {e}")