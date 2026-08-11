"""
main.py
Objetivo: Punto de entrada de la aplicación FastAPI. Orquesta los routers, configuraciones globales y middleware.
Uso: Ejecutar con `uvicorn main:app --host 0.0.0.0 --port 8000`.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importación de Routers Modulares
from routers import health, presupuesto, recetas, ingredientes, padron, parametros, planificacion

app = FastAPI(title="API - NutriComedor", version="2.2.0")

# Configuración de CORS (Mantiene compatibilidad con tu Frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro de Routers con el prefijo global de la API
app.include_router(health.router, prefix="/api/v1")
app.include_router(parametros.router, prefix="/api/v1")
app.include_router(presupuesto.router, prefix="/api/v1")
app.include_router(recetas.router, prefix="/api/v1")
app.include_router(ingredientes.router, prefix="/api/v1")
app.include_router(padron.router, prefix="/api/v1")
app.include_router(planificacion.router, prefix="/api/v1")  # <-- NUEVO

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)