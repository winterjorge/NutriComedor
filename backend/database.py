"""
database.py
Objetivo: Gestionar las conexiones a PostgreSQL mediante el sistema de dependencias de FastAPI.
Uso: Inyectar en los endpoints usando `Depends(get_db)` para asegurar el cierre automático.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_URL

def get_db():
    """Generador que provee una conexión activa y la cierra al terminar el request."""
    conn = psycopg2.connect(DB_URL)
    try:
        yield conn
    finally:
        conn.close()

def get_parametros_dict(db, claves: list) -> dict:
    """
    Helper modular para obtener parámetros de la BD como un diccionario.
    Realiza el casteo automático según el campo 'tipo_dato'.
    """
    if not claves:
        return {}
    
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # Usamos ANY para buscar múltiples claves de forma eficiente
        cur.execute("SELECT clave, valor, tipo_dato FROM parametros_sistema WHERE clave = ANY(%s)", (claves,))
        params = {}
        for row in cur.fetchall():
            val = row['valor']
            # Casteo dinámico según el tipo de dato definido en la BD
            if row['tipo_dato'] == 'INTEGER': 
                val = int(val)
            elif row['tipo_dato'] == 'FLOAT': 
                val = float(val)
            elif row['tipo_dato'] == 'BOOLEAN': 
                val = val.lower() == 'true'
            params[row['clave']] = val
        return params
    except Exception as e:
        print(f"Error leyendo parámetros: {e}")
        return {}
    finally:
        cur.close()