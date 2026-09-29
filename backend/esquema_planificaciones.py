"""
esquema_planificaciones.py
Objetivo: DDL y seeds del módulo de propuestas de menú semanal (COM-8). Crea la tabla
          de propuestas candidatas (las 3 tarjetas del motor greedy), agrega columnas
          aditivas al maestro presupuesto_semanal (vínculo con comedor, candidata y
          selector) y a planificacion_dia (nutrición por ración), siembra los parámetros
          de ponderación/rotación/comensales y registra el módulo 'propuestas' en la
          matriz de permisos por vistas (COM-25).
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_planificaciones(cur)`.
Nota: Idempotente (IF NOT EXISTS / ON CONFLICT DO NOTHING). NO modifica ni elimina las
      tablas existentes presupuesto_semanal ni planificacion_dia: solo les AGREGA
      columnas nullable/defaults para el flujo multi-comedor y nutricional de COM-8.
Historial:
 - COM-8 Parte 1: tabla planificaciones_candidatas + parámetros del motor + módulo.
 - COM-8 Parte 3: vínculo de presupuesto_semanal (comedor_id, candidata_id,
   seleccionado_por_id, fecha_seleccion, estado) para historial por comedor.
 - COM-8 v4: columnas nutricionales por día en planificacion_dia
   (energia_kcal_racion, hierro_mg_racion, proteina_g_racion).
Referencia: ticket COM-8 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""

# =========================================================================
# DDL: Propuestas candidatas del motor greedy (COM-8).
# Viven entre el "Generar 3 propuestas" y el "Seleccionar esta opción".
# Al seleccionar, la propuesta se copia a presupuesto_semanal + planificacion_dia
# (tablas existentes) y queda marcada como SELECCIONADA (historial auditable).
# =========================================================================
DDL_PLANIFICACIONES_CANDIDATAS = """
CREATE TABLE IF NOT EXISTS planificaciones_candidatas (
    id SERIAL PRIMARY KEY,
    comedor_id INT NOT NULL REFERENCES comedores(id) ON DELETE CASCADE,
    sesion_id VARCHAR(64) NOT NULL,
    variante VARCHAR(30) NOT NULL,
    etiqueta VARCHAR(60) NOT NULL,
    descripcion VARCHAR(200),
    ponderacion JSONB NOT NULL,
    resumen JSONB NOT NULL,
    menu JSONB NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    creado_por_id INT REFERENCES usuarios(id),
    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours'
);
CREATE INDEX IF NOT EXISTS idx_candidatas_sesion ON planificaciones_candidatas(sesion_id);
CREATE INDEX IF NOT EXISTS idx_candidatas_comedor ON planificaciones_candidatas(comedor_id, fecha DESC);
"""

# =========================================================================
# COM-8 (Parte 3): Vínculo del maestro presupuesto_semanal (init.sql) con el comedor,
# la candidata origen y el usuario que seleccionó. Columnas ADITIVAS: las
# planificaciones históricas del Sprint 1-2 (sin comedor) siguen funcionando.
# `estado` permite auditar reemplazos: VIGENTE / REEMPLAZADA.
# =========================================================================
DDL_PRESUPUESTO_VINCULO_COMEDOR = """
ALTER TABLE presupuesto_semanal
ADD COLUMN IF NOT EXISTS comedor_id INT REFERENCES comedores(id),
ADD COLUMN IF NOT EXISTS candidata_id INT REFERENCES planificaciones_candidatas(id),
ADD COLUMN IF NOT EXISTS seleccionado_por_id INT REFERENCES usuarios(id),
ADD COLUMN IF NOT EXISTS fecha_seleccion TIMESTAMP,
ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'VIGENTE';
CREATE INDEX IF NOT EXISTS idx_presupuesto_semanal_comedor
ON presupuesto_semanal(comedor_id, fecha_referencia DESC);
"""

# =========================================================================
# COM-8 v4: Columnas nutricionales POR DÍA en planificacion_dia (Kcal, Hierro y
# Proteína por ración). Se agregan como ADD COLUMN IF NOT EXISTS para no tocar los
# datos existentes; el motor greedy las llena al insertar y PlanificacionesView las
# muestra aunque la sesión candidata ya se haya purgado.
# =========================================================================
DDL_PLANIFICACION_DIA_NUTRICIONAL = """
ALTER TABLE planificacion_dia
ADD COLUMN IF NOT EXISTS energia_kcal_racion NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS hierro_mg_racion    NUMERIC(8,2),
ADD COLUMN IF NOT EXISTS proteina_g_racion   NUMERIC(8,2);
"""

# =========================================================================
# SEED: Parámetros del motor (ponderaciones por variante, rotación de clusters
# por día y comensales proyectados por tipo para el detalle diario).
# =========================================================================
SEED_PARAMETROS_PLANIFICACION = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('PLANIFICACION_DIAS_SEMANA', '7', 'Número de días que abarca una planificación semanal', 'PLANIFICACION', 'INTEGER'),
('PLANIFICACION_VARIANTE_NUTRI_W', '{"hierro":0.40,"proteina":0.30,"energia":0.10,"precio":0.10,"variedad":0.10}',
    'Ponderación variante NutriMax: prioriza hierro y proteína', 'PLANIFICACION', 'JSON'),
('PLANIFICACION_VARIANTE_ECONO_W', '{"hierro":0.10,"proteina":0.10,"energia":0.10,"precio":0.60,"variedad":0.10}',
    'Ponderación variante EconoMax: prioriza menor costo', 'PLANIFICACION', 'JSON'),
('PLANIFICACION_VARIANTE_BALANCE_W', '{"hierro":0.25,"proteina":0.25,"energia":0.20,"precio":0.20,"variedad":0.10}',
    'Ponderación variante BalanceMax: balance nutrición/costo', 'PLANIFICACION', 'JSON'),
('PLANIFICACION_ROTACION_CLUSTERS', '[1,2,4,1,3,2,4]',
    'Código de cluster objetivo por día (lun=1..dom=7). 1=AntiAnemia 2=Fortalecimiento 3=Ligero 4=AllRounder',
    'PLANIFICACION', 'JSON'),
('PLANIFICACION_COMENSALES_SOCIAL', '22', 'Comensales sociales proyectados por día (rango operativo 20-25)', 'PLANIFICACION', 'INTEGER'),
('PLANIFICACION_COMENSALES_AFILIADO', '48', 'Comensales afiliados proyectados por día (rango operativo 45-50)', 'PLANIFICACION', 'INTEGER'),
('PLANIFICACION_COMENSALES_NORMAL', '50', 'Comensales normales proyectados por día (completa ~120 raciones)', 'PLANIFICACION', 'INTEGER')
ON CONFLICT (clave) DO NOTHING;
"""

# =========================================================================
# SEED: Módulo 'propuestas' en la matriz de permisos por vistas (COM-25).
# Visibilidad de la vista: Directivo (Presidente/Tesorero/Secretario) y Operativo
# (Cocinero). La acción de SELECCIONAR se valida aparte en el backend (solo Directivo).
# =========================================================================
SEED_MODULO_PROPUESTAS = """
INSERT INTO modulos_sistema (clave, nombre, descripcion)
VALUES ('propuestas', 'Propuestas de Menú',
        'Generación y selección de 3 propuestas de menú semanal (COM-8)')
ON CONFLICT (clave) DO NOTHING;

INSERT INTO roles_modulos (rol_id, modulo_id)
SELECT r.id, m.id
FROM roles_grupo r
JOIN modulos_sistema m ON m.clave = 'propuestas'
WHERE r.nombre IN ('Presidente', 'Tesorero', 'Secretario', 'Cocinero')
ON CONFLICT (rol_id, modulo_id) DO NOTHING;
"""


def aplicar_esquema_planificaciones(cur):
    """
    COM-8: crea la tabla de propuestas candidatas, agrega el vínculo comedor/candidata/
    selector al maestro presupuesto_semanal, agrega las columnas nutricionales por día
    a planificacion_dia, siembra parámetros del motor y registra el módulo 'propuestas'
    en la matriz de vistas. Idempotente. El caller (db_bootstrap) hace el commit.
    """
    # 1) Tabla de candidatas (debe existir antes del FK candidata_id del paso 2)
    cur.execute(DDL_PLANIFICACIONES_CANDIDATAS)
    # 2) COM-8 Parte 3: vínculo del maestro existente con comedor/candidata/selector
    cur.execute(DDL_PRESUPUESTO_VINCULO_COMEDOR)
    # 3) COM-8 v4: columnas nutricionales por día (Kcal/Hierro/Proteína por ración)
    cur.execute(DDL_PLANIFICACION_DIA_NUTRICIONAL)
    # 4) Parámetros del motor greedy
    cur.execute(SEED_PARAMETROS_PLANIFICACION)
    # 5) Módulo de vistas y su asignación a roles Directivo/Operativo
    cur.execute(SEED_MODULO_PROPUESTAS)