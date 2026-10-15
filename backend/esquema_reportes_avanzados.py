"""
esquema_reportes_avanzados.py
Objetivo: COM-77/78: seed idempotente de los parámetros de metas y umbrales de los
reportes avanzados (sin DDL de tablas; todo viaja en payloads JSON):
  * META_HIERRO_RACION_MG / META_PROTEINA_RACION_G / META_KCAL_RACION: metas del
    semáforo nutricional por ración de ALMUERZO (referencia NTS 127-MINSA: el
    almuerzo cubre ~30-35% del requerimiento diario; editables por Admin).
  * ALERTA_VOLATILIDAD_PCT y CANASTA_CRITICA_OBSERVATORIO: reservados para el
    Observatorio de Precios de COM-78 (se siembran ahora para no requerir otro
    bootstrap después).
Uso: Importado por db_bootstrap.py (paso COM-77). Idempotente (ON CONFLICT DO NOTHING).
Referencia: tickets COM-77 / COM-78 (solo trazabilidad).
"""

SEED_PARAMETROS_REPORTES_AVANZADOS = """
INSERT INTO parametros_sistema (clave, valor, descripcion, categoria, tipo_dato) VALUES
('META_HIERRO_RACION_MG', '4.5',
 'COM-77: meta de hierro por ración de almuerzo (mg) para el semáforo nutricional', 'REPORTES', 'FLOAT'),
('META_PROTEINA_RACION_G', '22',
 'COM-77: meta de proteína por ración de almuerzo (g) para el semáforo nutricional', 'REPORTES', 'FLOAT'),
('META_KCAL_RACION', '750',
 'COM-77: meta de energía por ración de almuerzo (kcal) para el semáforo nutricional', 'REPORTES', 'FLOAT'),
('ALERTA_VOLATILIDAD_PCT', '8.0',
 'COM-78: umbral de variación 7d (%) que dispara alerta temprana en el Observatorio de Precios', 'REPORTES', 'FLOAT'),
('CANASTA_CRITICA_OBSERVATORIO', '["pollo", "huevo", "arroz", "frijol", "aceite", "papa", "cebolla"]',
 'COM-78: JSON con los nombres-normalizados de la canasta crítica del Observatorio de Precios', 'REPORTES', 'JSON')
ON CONFLICT (clave) DO NOTHING;
"""


def aplicar_esquema_reportes_avanzados(cur):
    """COM-77: siembra los parámetros de metas/umbrales de reportes. Idempotente."""
    cur.execute(SEED_PARAMETROS_REPORTES_AVANZADOS)