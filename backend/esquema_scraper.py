"""
esquema_scraper.py
Objetivo: COM-43: tabla de auditoría de corridas del scraper SISAP
(`scraper_corridas`): cada ejecución (WEB manual por rango, CRON del host o
CATCH-UP de arranque) deja una fila con origen, rango de fechas, contadores de
días procesados/exitosos/fallidos, estado y detalle JSON de fallos.
Historial:
COM-43 (este archivo): versión original. DDL idempotente (IF NOT EXISTS); el
    bootstrap la aplica en cada arranque sin efectos secundarios.
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_scraper(cur)`.
Referencia: ticket COM-43 (solo trazabilidad).
"""

DDL_SCRAPER_CORRIDAS = """
CREATE TABLE IF NOT EXISTS scraper_corridas (
    id SERIAL PRIMARY KEY,
    origen VARCHAR(20) NOT NULL DEFAULT 'WEB',
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    dias_procesados INT NOT NULL DEFAULT 0,
    dias_exitosos INT NOT NULL DEFAULT 0,
    dias_fallidos INT NOT NULL DEFAULT 0,
    estado VARCHAR(30) NOT NULL DEFAULT 'EN_PROCESO',
    detalle TEXT,
    usuario_solicitante_id INT,
    iniciado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    terminado_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scraper_corridas_estado ON scraper_corridas(estado);
CREATE INDEX IF NOT EXISTS idx_scraper_corridas_inicio ON scraper_corridas(iniciado_en DESC);
"""


def aplicar_esquema_scraper(cur):
    """COM-43: crea la tabla de auditoría de corridas. Idempotente."""
    cur.execute(DDL_SCRAPER_CORRIDAS)