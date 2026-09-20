"""
seguridad.py
Objetivo: Centralizar la lógica de seguridad del sistema (COM-19/COM-23): hash de
          contraseñas con PBKDF2-SHA256 (sin dependencias externas), validación de la
          política de contraseñas (longitud parametrizable, letras+números, sin contener
          el DNI) y constantes de seguridad (intentos fallidos, expiración, bootstrap).
Uso: Importar desde routers/auth.py, routers/usuarios.py y db_bootstrap.py.

Historial:
 - COM-19: hash PBKDF2, política base (8-12 caracteres) y constantes de bootstrap.
 - COM-23: `validar_politica_clave` acepta un diccionario `politica` leído de
   parametros_sistema (categoría SEGURIDAD); si una clave no existe, usa el default.
"""
import hashlib
import re
import secrets

# ==========================================
# CONSTANTES DE SEGURIDAD (defaults COM-19)
# ==========================================
MAX_INTENTOS_FALLIDOS = 3          # Con 3 intentos fallidos el usuario se bloquea
MESES_EXPIRACION_CLAVE = 6         # La contraseña expira cada 6 meses
LONGITUD_MIN_CLAVE = 8
LONGITUD_MAX_CLAVE = 12
ITERACIONES_PBKDF2 = 200_000       # Coste computacional del hash

# Clave provisoria asignada a usuarios legacy (hash antiguo 'hash_123456').
CLAVE_INICIAL = "Nutri2026"

# COM-19: Usuario administrador de respaldo creado idempotentemente por db_bootstrap.
DNI_ADMIN_RESPALDO = "0000000"
CLAVE_INICIAL_ADMIN = "Admin2026"

# ==========================================
# CLAVES DE PARÁMETROS DE POLÍTICA (COM-23)
# Categoría SEGURIDAD en parametros_sistema.
# ==========================================
PARAM_LONG_MIN = 'CLAVE_LONGITUD_MIN'
PARAM_LONG_MAX = 'CLAVE_LONGITUD_MAX'
PARAM_MESES_EXPIRACION = 'CLAVE_MESES_EXPIRACION'
PARAM_MAX_INTENTOS = 'CLAVE_MAX_INTENTOS'


def politica_por_defecto() -> dict:
    """
    COM-23: Política de contraseñas por defecto (fallback cuando los parámetros
    de la BD no están disponibles o aún no se han configurado.
    """
    return {
        PARAM_LONG_MIN: LONGITUD_MIN_CLAVE,
        PARAM_LONG_MAX: LONGITUD_MAX_CLAVE,
        PARAM_MESES_EXPIRACION: MESES_EXPIRACION_CLAVE,
        PARAM_MAX_INTENTOS: MAX_INTENTOS_FALLIDOS,
    }


def hashear_clave(clave: str) -> str:
    """
    Genera un hash PBKDF2-SHA256 con sal aleatoria.
    Formato de almacenamiento: pbkdf2_sha256$<iteraciones>$<sal_hex>$<hash_hex>
    """
    sal = secrets.token_hex(16)
    derivada = hashlib.pbkdf2_hmac('sha256', clave.encode('utf-8'), bytes.fromhex(sal), ITERACIONES_PBKDF2)
    return f"pbkdf2_sha256${ITERACIONES_PBKDF2}${sal}${derivada.hex()}"


def verificar_clave(clave: str, clave_almacenada: str) -> bool:
    """
    Compara una clave en texto plano contra su hash almacenado.
    Retorna False para hashes legacy que no tengan el formato pbkdf2 (ej. 'hash_123456').
    """
    try:
        algoritmo, iteraciones, sal, hash_hex = clave_almacenada.split('$')
        if algoritmo != 'pbkdf2_sha256':
            return False
        derivada = hashlib.pbkdf2_hmac('sha256', clave.encode('utf-8'), bytes.fromhex(sal), int(iteraciones))
        # Comparación de tiempo constante para evitar ataques de timing
        return secrets.compare_digest(derivada.hex(), hash_hex)
    except Exception:
        return False


def validar_politica_clave(clave: str, documento: str = "", politica: dict = None) -> list:
    """
    Valida la política de contraseñas y retorna una lista de mensajes de incumplimiento.
    COM-23: la longitud mínima/máxima se toma del diccionario `politica` (parametros_sistema,
    categoría SEGURIDAD); si no se provee o falta una clave, se usan los defaults.
    Reglas fijas: debe contener letras y números, y no puede contener el DNI.
    """
    pol = politica or {}
    long_min = int(pol.get(PARAM_LONG_MIN, LONGITUD_MIN_CLAVE))
    long_max = int(pol.get(PARAM_LONG_MAX, LONGITUD_MAX_CLAVE))

    errores = []
    if not (long_min <= len(clave) <= long_max):
        errores.append(f"La contraseña debe tener entre {long_min} y {long_max} caracteres.")
    if not (re.search(r'[A-Za-z]', clave) and re.search(r'\d', clave)):
        errores.append("La contraseña debe contener letras y números.")
    if documento and documento in clave:
        errores.append("La contraseña no puede contener su número de documento.")
    return errores