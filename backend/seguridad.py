"""
seguridad.py
Objetivo: Centralizar la lógica de seguridad del sistema (COM-19): hash de contraseñas
          con PBKDF2-SHA256 (sin dependencias externas), validación de la política de
          contraseñas (8-12 caracteres, letras+números, sin contener el DNI) y las
          constantes de seguridad (intentos fallidos, expiración).
Uso: Importar desde routers/auth.py y db_bootstrap.py.
"""
import hashlib
import re
import secrets

# ==========================================
# CONSTANTES DE SEGURIDAD (COM-19)
# ==========================================
MAX_INTENTOS_FALLIDOS = 3          # Con 3 intentos fallidos el usuario se bloquea
MESES_EXPIRACION_CLAVE = 6         # La contraseña expira cada 6 meses
LONGITUD_MIN_CLAVE = 8
LONGITUD_MAX_CLAVE = 12
ITERACIONES_PBKDF2 = 200_000       # Coste computacional del hash

# Clave provisoria asignada a usuarios legacy (hash antiguo 'hash_123456').
# El sistema fuerza su cambio en el primer login (clave_provisoria = TRUE).
CLAVE_INICIAL = "Nutri2026"


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


def validar_politica_clave(clave: str, documento: str = "") -> list:
    """
    Valida la política de contraseñas (COM-19) y retorna una lista de mensajes
    de incumplimiento. Reglas: 8-12 caracteres, letras y números, sin contener el DNI.
    """
    errores = []
    if not (LONGITUD_MIN_CLAVE <= len(clave) <= LONGITUD_MAX_CLAVE):
        errores.append(f"La contraseña debe tener entre {LONGITUD_MIN_CLAVE} y {LONGITUD_MAX_CLAVE} caracteres.")
    if not (re.search(r'[A-Za-z]', clave) and re.search(r'\d', clave)):
        errores.append("La contraseña debe contener letras y números.")
    if documento and documento in clave:
        errores.append("La contraseña no puede contener su número de documento.")
    return errores