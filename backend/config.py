"""
config.py
Objetivo: Centralizar las variables de entorno y configuraciones globales del backend.
Uso: Importar desde cualquier módulo que necesite la URL de la base de datos o constantes.
"""
import os

DB_URL = os.getenv("DATABASE_URL", "postgresql://nutri_admin:Nutri2026Secure!@db:5432/nutricomedor")
DIAS_SEMANA = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]