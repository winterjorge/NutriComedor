# ==========================================
# Etapa 1: Compilación de React y Node.js
# ==========================================
FROM node:20-alpine AS build-stage

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el listado de dependencias para aprovechar la caché de Docker
COPY package*.json ./

# Instalar todas las dependencias listadas en tu package.json local
RUN npm install

# Asegurar la instalación de lucide-react (iconos) y tailwindcss (estilos)
RUN npm install lucide-react tailwindcss@3 postcss autoprefixer @tailwindcss/postcss

# Copiar el resto del código fuente (src, index.html, vite.config.js, etc.)
COPY . .

# ==========================================
# Configuración de Tailwind CSS v3
# ==========================================

# 1. Crear configuracion de Tailwind
RUN echo 'export default { content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"], theme: { extend: {} }, plugins: [] }' > tailwind.config.js

# 2. Crear configuracion de PostCSS usando el nuevo paquete @tailwindcss/postcss
RUN echo 'export default { plugins: { tailwindcss: {}, autoprefixer: {} } }' > postcss.config.js

# 3. Inyectar las directivas obligatorias en el CSS global
RUN echo "@tailwind base;" > src/index.css && \
	echo "@tailwind components;" >> src/index.css && \
	echo "@tailwind utilities;" >> src/index.css

# Construir la aplicacion para produccion
RUN npm run build

# ==========================================
# Etapa 2: Servidor Web con Nginx y SSL
# ==========================================
FROM nginx:alpine

# 1. Instalar OpenSSL para generar certificados
RUN apk add --no-cache openssl

# 2. Generar certificado auto-firmado
RUN mkdir -p /etc/nginx/ssl && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/nginx.key -out /etc/nginx/ssl/nginx.crt \
    -subj "/C=PE/ST=Lima/L=Lima/O=NutriComedor/OU=IT/CN=localhost"

# 3. Copiar tu configuración personalizada de Nginx (Proxy inverso)
# Esto sobrescribe la configuración por defecto de Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 4. Copiar los archivos compilados de React al directorio publico
COPY --from=build-stage /app/dist /usr/share/nginx/html

# Exponer los puertos HTTP (80) y HTTPS (443)
EXPOSE 80 443

# Arrancar Nginx
CMD ["nginx", "-g", "daemon off;"]