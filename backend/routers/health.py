"""
routers/health.py
Objetivo: Exponer endpoints de monitoreo y estado de salud del servicio.
Uso: Registrado en main.py con prefijo /api/v1 para verificación de disponibilidad.
"""
from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.get("/health")
def health_check():
    return {"status": "ok"}