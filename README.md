# 🍲 NutriComedor OSB

**Sistema web para la generación de dietas balanceadas de bajo costo en comedores populares**
Distrito de San Juan de Lurigancho — Lima, Perú 🇵
*Proyecto de Tesis de Ingeniería de Sistemas*
*Autores: Jorge Winter y Jean Wong*

---

## 📋 Descripción del proyecto

NutriComedor OSB es una plataforma web para comedores populares autogestionados que reciben un
subsidio mensual del Estado de **S/ 625** más víveres (6 sacos de arroz, 50 kg de menestra,
22 botellas de aceite de 1 L y 80 kg de pollo o huevo).

El sistema ayuda a la administradora a:

- **Planificar menús semanales** que cumplan requerimientos nutricionales (hierro, proteína, energía) respetando el presupuesto real.
- **Predecir precios** de insumos con Machine Learning (Random Forest) usando el histórico de precios mayoristas del **SISAP (MIDAGRI)**, permitiendo compras semanales en lugar de diarias.
- **Predecir la demanda** de comensales por tipo (Social, Afiliado, Normal) para dimensionar la cocina.
- **Gestionar el punto de venta (POS)** con precios diferenciados: Normal S/ 5.00, Afiliado S/ 3.00, Social S/ 0.00.
- **Proyectar ~120 menús diarios** (20–25 sociales, 45–50 afiliados, resto normales).

---

## 🏗️ Arquitectura

Tres contenedores orquestados con **Docker Compose**:

| Contenedor | Tecnología | Rol |
|---|---|---|
| `db` | PostgreSQL 16 | Base de datos persistente |
| `api` | Python 3.10 + FastAPI + scikit-learn | API REST, motor de costos y modelos ML |
| `web` | React (Vite) + Nginx | SPA servida por HTTPS (443) con proxy inverso a `/api/` |

Además, un **módulo scraper** (cron diario 5:00 a. m.) consulta el portal SISAP del MIDAGRI,
normaliza y clasifica insumos y alimenta el `historial_precios`.

```
SISAP MIDAGRI ──▶ Scraper diario ──▶ historial_precios ──▶ Random Forest (precios)
                                                              │
POS (padrón_diario) ──▶ Random Forest (demanda) ──▶ Planificador semanal ──▶ Lista de compras
```

---

## 📁 Estructura del proyecto

```
.
├── docker-compose.yml          # Orquestación de contenedores
├── backfill.py                 # Backfill del scraper por rango de fechas
├── README.md
├── backend/
│   ├── main.py                 # Entrada FastAPI + lifespan (bootstrap de esquema)
│   ├── config.py               # Variables de entorno globales
│   ├── database.py             # Conexiones y helper de parámetros
│   ├── seguridad.py            # Hash PBKDF2 y política de contraseñas (COM-19)
│   ├── optimizador.py          # Cálculo de costo por ración con precios reales/predichos
│   ├── ai_engine.py            # Predicción de demanda (Random Forest)
│   ├── db_bootstrap.py         # Auto-reparación idempotente del esquema en cada arranque
│   ├── validacion_modelos.py   # Métricas MAE/MAPE de los modelos ML
│   ├── Dockerfile
│   ├── routers/                # auth, health, parametros, recetas, ingredientes,
│   │                           # padron, presupuesto, planificacion
│   ├── schemas/                # Modelos Pydantic (receta, comensal, presupuesto)
│   └── scraper/                # extractors/, classifiers/, database/, utils/
├── database/
│   ├── init.sql                # DDL del esquema (se auto-ejecuta al crear el volumen)
│   ├── seed.sql                # Datos maestros (categorías, unidades, ingredientes…)
│   ├── parametros.sql          # Parámetros dinámicos (POS, precios, umbrales IA)
│   ├── poblar_recetas.sql      # 20 recetas de almuerzo con nutrición e ingredientes
│   └── datos_ficticios.sql     # 1 año de atenciones simuladas para entrenar la IA
└── frontend/
    ├── Dockerfile              # Build multi-etapa Node 20 → Nginx + SSL
    ├── nginx.conf              # Servidor estático + proxy inverso + HTTPS
    └── src/
        ├── App.jsx             # Navegación por pestañas + control de sesión
        ├── components/         # auth/, recipes/, budget/, catalog/, pos/, common/
        ├── context/            # AuthContext, ParametrosContext
        ├── hooks/              # useBudget, useCatalog, usePOS, useRecipes
        ├── services/api.js     # Cliente HTTP centralizado
        └── utils/constants.js  # Fallbacks locales
```

---

## 🛠️ Stack tecnológico

- **Backend:** Python 3.10, FastAPI, Uvicorn, psycopg2, scikit-learn (Random Forest), pandas.
- **Frontend:** React 18, Vite, Tailwind CSS, Lucide Icons.
- **Base de datos:** PostgreSQL 16.
- **Infraestructura:** Docker, Docker Compose, Nginx (SSL autofirmado), cron.

---

## ⚙️ Requisitos

- Ubuntu 24.04 (o similar) con Docker y Docker Compose instalados.
- Acceso a internet para consultar la API del SISAP (scraper).
- Puertos 80 y 443 libres.

---

## 🚀 Instalación y despliegue

```bash
# 1. Clonar el repositorio
git clone https://github.com/TU_USUARIO/nutricomedor.git
cd nutricomedor

# 2. Levantar los contenedores (primera vez: inicializa la BD con init.sql)
docker compose up -d --build

# 3. Verificar que el bootstrap de esquema corrió
docker compose logs api | grep BOOTSTRAP

# 4. Acceder a la aplicación
https://TU_SERVIDOR/   (aceptar el certificado autofirmado)
```

> ⚠️ Los scripts de `/docker-entrypoint-initdb.d/` solo se ejecutan en la **primera**
> inicialización del volumen. El archivo `db_bootstrap.py` garantiza idempotentemente,
> en cada arranque de la API, que existan las tablas/columnas dinámicas
> (`parametros_sistema`, `planificacion_dia`, `raciones`, columnas de seguridad, etc.),
> incluso en volúmenes creados con versiones antiguas del esquema.

### Scripts SQL adicionales (volúmenes nuevos, opcional)

Si deseas poblar datos completos en un volumen nuevo, ejecuta en orden:

```bash
docker compose exec -T db psql -U nutricomedor -d nutricomedor < database/parametros.sql
docker compose exec -T db psql -U nutricomedor -d nutricomedor < database/poblar_recetas.sql
docker compose exec -T db psql -U nutricomedor -d nutricomedor < database/datos_ficticios.sql
```

---

## 🔐 Acceso y seguridad (COM-19)

**Credenciales iniciales (usuario del seed):**

| Campo | Valor |
|---|---|
| Tipo de documento | DNI |
| Documento | `43604221` |
| Contraseña provisoria | `Nutri2026` *(cambio obligatorio en el primer login)* |

**Política de contraseñas:**

- Longitud de **8 a 12 caracteres**.
- Debe contener **letras y números**.
- **No puede contener el DNI** del usuario.
- **Expira cada 6 meses** (cambio obligatorio al vencer).
- **3 intentos fallidos bloquean** al usuario.
- Aviso ámbar de bloqueo inminente al quedar 1 intento restante.

**Desbloqueo manual (solo administrador de BD):**

```sql
UPDATE usuarios SET bloqueado = FALSE, intentos_fallidos = 0
WHERE documento_identidad = '43604221';
```

Las contraseñas se almacenan con hash **PBKDF2-SHA256** (200 000 iteraciones, sal aleatoria).

---

## 🕷️ Scraper de precios (SISAP)

- Ejecución diaria automática vía **cron (5:00 a. m.)** o manual:

```bash
cd backend/scraper
source venv/bin/activate
python main.py                      # fecha de hoy
python main.py --fecha 2026-04-01   # fecha específica
```

- **Backfill histórico** (una sola vez, para entrenar los modelos):

```bash
python backfill.py   # itera el rango de fechas con pausas anti-bloqueo
```

- Flujo: extrae precios del SISAP → normaliza nombres → clasifica heurísticamente
  (`classifiers/heuristics.py`) → guarda con UPSERT en `historial_precios`.

---

## 🤖 Modelos de IA

| Modelo | Algoritmo | Entrada | Salida |
|---|---|---|---|
| Demanda | Random Forest | Histórico de `padron_diario` | Comensales Social/Afiliado/Normal por día |
| Precios | Random Forest | `historial_precios` | Precio proyectado por insumo y fecha |

Validación de métricas (MAE/MAPE): `python validacion_modelos.py`.

---

## 📦 Módulos de la aplicación

| Pestaña | Función |
|---|---|
| **Recetario** | CRUD de recetas, evaluación de costos por ración (precios reales o predichos) |
| **Presupuesto** | Planificación semanal viable según presupuesto y predicción de demanda |
| **Planificaciones** | Historial de planificaciones guardadas y listas de compras (kg/L/und) |
| **Catálogo** | Consulta de precios por fecha e histórico gráfico por insumo |
| **Ventas y Demanda** | POS con límites/alertas por tipo de comensal y proyección de cocina |

---

## 🧾 Historial de tickets (Jira)

| Ticket | Descripción |
|---|---|
| COM-16 | Fix de scroll/accesibilidad del modal Editar Receta + rediseño de lista de ingredientes |
| COM-17 | Columna `raciones` en `recetas_almuerzo` para el motor de costos |
| COM-18 | Confirmaciones modales (guardar/cancelar/eliminar) + `ModalExito` reutilizable |
| COM-19 | Módulo de login: política de contraseñas, expiración 6 meses, bloqueo por intentos |

---

## 📌 Checkpoints

- **`Estable PI1`**: estado de referencia del sistema (configuración de archivos
  documentada en el inventario del proyecto). Si se solicita "regresar a Estable PI1",
  se restaura dicha configuración.

---

## 👥 Autores
Jorge Winter y Jean Wong
Proyecto de Tesis — Ingeniería de Sistemas y Computación.
*Universidad Peruana de Ciencias Aplicadas — Lima, Perú.*
