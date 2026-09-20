"""
esquema_flujo_usuario.py
Objetivo: Concentrar el DDL del flujo de creación/edición de usuarios según perfil
          (corrección COM-26): tabla de asociación de usuarios Administrativos a
          municipalidades, que completa el modelo de alcance iniciado en COM-21/COM-23
          (comedores para Directivo/Operativo, municipalidades para Administrativo).
Uso: Importado por db_bootstrap.py, que ejecuta `aplicar_esquema_flujo_usuario(cur)`.
Nota: Todas las sentencias son idempotentes (IF NOT EXISTS), por lo que pueden
      ejecutarse en cada arranque sin efectos secundarios.
Referencia: ticket COM-26 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""

# =========================================================================
# DDL: Asociación usuario -> municipalidad (alcance del perfil Administrativo).
# Espejo conceptual de usuario_comedor, pero para el ámbito municipal.
# =========================================================================
DDL_USUARIO_MUNICIPALIDAD = """
CREATE TABLE IF NOT EXISTS usuario_municipalidad (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    municipalidad_id INT NOT NULL REFERENCES municipalidades(id) ON DELETE CASCADE,
    estado_activo BOOLEAN NOT NULL DEFAULT TRUE,
    desactivado_por INT REFERENCES usuarios(id),
    fecha_desactivacion TIMESTAMP,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP - INTERVAL '5 hours',
    UNIQUE NULLS NOT DISTINCT (usuario_id, municipalidad_id)
);
CREATE INDEX IF NOT EXISTS idx_usuario_municipalidad_usuario ON usuario_municipalidad(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_municipalidad_municipalidad ON usuario_municipalidad(municipalidad_id);
"""


def aplicar_esquema_flujo_usuario(cur):
    """
    Ejecuta el esquema del flujo de usuarios por perfil sobre un cursor abierto.
    El caller (db_bootstrap) es responsable del commit.
    """
    cur.execute(DDL_USUARIO_MUNICIPALIDAD)