"""
main.py
Objetivo: Punto de entrada de la aplicación FastAPI. Orquesta los routers, configuraciones globales y middleware.
Uso: Ejecutar con `uvicorn main:app --host 0.0.0.0 --port 8000`.
Historial:
 - COM-21/22/23/25/26/27: routers de gestión (comedores, grupos, usuarios, municipalidades, vistas, ubicaciones).
 - COM-5: router de clustering K-means del recetario.
 - COM-8: router de propuestas de menú semanal (motor greedy).
 - COM-5 v4 / COM-8 v7: router del panel de gráficos de Machine Learning (modelos_ml),
   exclusivo del Administrador de Sistemas.
 - COM-38: router de reseteo/cambio de clave por Admin de Sistemas (reset_clave).
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importación de Routers Modulares
from routers import (
    health,
    presupuesto,
    recetas,
    ingredientes,
    padron,
    parametros,
    planificacion,
    auth,
    comedores,        # COM-21: gestión multi-comedor y asociación de usuarios
    grupos,           # COM-22/COM-23: grupos, privilegios y roles temporales
    usuarios,         # COM-23/COM-26: gestión de usuarios y flujo CRUD por perfil
    municipalidades,  # COM-23: registro nacional de municipalidades
    vistas,           # COM-25: permisos por vistas (módulos por grupo/rol)
    ubicaciones,      # COM-27: catálogo geográfico en cascada
    kmeans,           # COM-5: clustering nutricional del recetario (K-means k=4)
    propuestas_menu,  # COM-8: propuestas de menú semanal (motor greedy search)
    modelos_ml,       # COM-5 v4 / COM-8 v7: panel de gráficos de ML (solo Admin de Sistemas)
    reset_clave,      # COM-38: reseteo/cambio de clave por Admin de Sistemas
)
# Asegurado de esquema dinámico (parámetros, planificación, raciones, seguridad,
# comedores, grupos, gestión de usuarios, permisos por vistas, ubicaciones,
# esquema K-means con seed nutricional, esquema de propuestas COM-8 y seeds de
# módulos ML / proteínas configurables COM-5 v4) al arrancar
from db_bootstrap import asegurar_esquema


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verificar/crear tablas dinámicas antes de atender peticiones.
    asegurar_esquema()
    yield


app = FastAPI(title="API - NutriComedor", version="2.12.0", lifespan=lifespan)

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
app.include_router(comedores.router, prefix="/api/v1")        # COM-21
app.include_router(grupos.router, prefix="/api/v1")           # COM-22/COM-23
app.include_router(usuarios.router, prefix="/api/v1")         # COM-23/COM-26
app.include_router(municipalidades.router, prefix="/api/v1")  # COM-23
app.include_router(vistas.router, prefix="/api/v1")           # COM-25
app.include_router(ubicaciones.router, prefix="/api/v1")      # COM-27
app.include_router(kmeans.router, prefix="/api/v1")           # COM-5
app.include_router(propuestas_menu.router, prefix="/api/v1")  # COM-8
app.include_router(modelos_ml.router, prefix="/api/v1")       # COM-5 v4 / COM-8 v7
app.include_router(reset_clave.router, prefix="/api/v1")      # COM-38
app.include_router(parametros.router, prefix="/api/v1")
app.include_router(presupuesto.router, prefix="/api/v1")
app.include_router(recetas.router, prefix="/api/v1")
app.include_router(ingredientes.router, prefix="/api/v1")
app.include_router(padron.router, prefix="/api/v1")
app.include_router(planificacion.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)