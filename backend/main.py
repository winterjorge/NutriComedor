"""
main.py
Objetivo: Punto de entrada de la aplicación FastAPI. Orquesta los routers, configuraciones globales y middleware.
Uso: Ejecutar con `uvicorn main:app --host 0.0.0.0 --port 8000`.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importación de Routers Modulares
from routers import health, presupuesto, recetas, ingredientes, padron, parametros, planificacion, auth
# Asegurado de esquema dinámico (parámetros, planificación, raciones, seguridad) al arrancar
from db_bootstrap import asegurar_esquema


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verificar/crear tablas dinámicas antes de atender peticiones.
    asegurar_esquema()
    yield


app = FastAPI(title="API - NutriComedor", version="2.3.0", lifespan=lifespan)

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
app.include_router(auth.router, prefix="/api/v1")
app.include_router(parametros.router, prefix="/api/v1")
app.include_router(presupuesto.router, prefix="/api/v1")
app.include_router(recetas.router, prefix="/api/v1")
app.include_router(ingredientes.router, prefix="/api/v1")
app.include_router(padron.router, prefix="/api/v1")
app.include_router(planificacion.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)