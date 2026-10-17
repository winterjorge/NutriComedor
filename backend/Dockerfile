# ==========================================
# Dockerfile - NutriComedor API (Backend)
# Objetivo: Construir la imagen del backend FastAPI con todas sus dependencias.
# Historial:
#  - Sprint 1/2: versión original con `RUN echo "..." > requirements.txt`.
#  - COM-63: refactorización para usar `requirements.txt` real en disco.
#    Ventajas:
#      1) Las dependencias son versionables con git (auditoría y diff).
#      2) El build reutiliza la capa de `pip install` cuando solo cambia código Python
#         (acelera builds de ~40s a ~5s en iteraciones normales).
#      3) Agregar una librería nueva es un cambio de una línea en requirements.txt,
#         no tocar el Dockerfile.
# ==========================================

FROM python:3.10-slim

# Evitar prompts interactivos en installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ==========================================
# 1) Dependencias de Python (capa cacheable)
# ==========================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==========================================
# 2) Código de la aplicación (capa que cambia con cada commit)
# ==========================================
COPY . .

# ==========================================
# 3) Configuración de red y puerto
# ==========================================
EXPOSE 8000

# ==========================================
# 4) Comando de arranque (uvicorn en modo producción)
# ==========================================
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]