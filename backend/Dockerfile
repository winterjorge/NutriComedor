# Usar imagen ligera de Python 3.10
FROM python:3.10-slim

# Evitar escritura de bytecode y forzar logs directos a la consola
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Instalar dependencias del SO necesarias para compilar librerías de Machine Learning
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Crear requirements e instalarlos
RUN echo "fastapi\nuvicorn\npandas\nscikit-learn\npsycopg2-binary\npydantic" > requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente del backend
COPY . .

EXPOSE 8000

# Arrancar la API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]