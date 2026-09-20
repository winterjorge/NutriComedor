"""
permisos.py
Objetivo: Centralizar la lógica de permisos del modelo multi-grupo/multi-comedor
          (COM-22), manteniendo compatibilidad hacia atrás con el modelo legacy de
          COM-21 (usuarios.rol y usuario_comedor).
Uso: Importar desde los routers (comedores.py, grupos.py, etc.). Todas las funciones
     reciben un cursor psycopg2 activo (RealDictCursor) y consultan la BD.
"""

# ==========================================
# Nombres de grupos sembrados por db_bootstrap (COM-22)
# ==========================================
GRUPO_SISTEMA = "Administrador de Sistemas"
GRUPO_ADMINISTRATIVO = "Administrativo"
GRUPO_DIRECTIVO = "Directivo"
GRUPO_OPERATIVO = "Operativo"

# Roles del grupo Directivo que gestionan el comedor (parte administrativa)
ROLES_DIRECTIVO_GESTION = ("Presidente", "Tesorero")


def _membresias(cur, usuario_id, grupo_nombre, comedor_id=None, roles=None, cobertura=False):
    """
    Consulta membresías ACTIVAS de un usuario en un grupo.
    Si se indica comedor_id:
      - cobertura=True : acepta alcance global (NULL) o el comedor (grupos GLOBAL).
      - cobertura=False: exige el comedor exacto (grupos COMEDOR).
    """
    query = """
        SELECT ug.id, ug.comedor_id, g.nombre AS grupo, g.ambito, r.nombre AS rol
        FROM usuario_grupo ug
        JOIN grupos_usuario g ON g.id = ug.grupo_id
        JOIN roles_grupo r ON r.id = ug.rol_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND g.nombre = %s
    """
    params = [usuario_id, grupo_nombre]
    if comedor_id is not None:
        if cobertura:
            query += " AND (ug.comedor_id IS NULL OR ug.comedor_id = %s)"
        else:
            query += " AND ug.comedor_id = %s"
        params.append(comedor_id)
    if roles:
        query += f" AND r.nombre IN ({', '.join(['%s'] * len(roles))})"
        params.extend(list(roles))
    cur.execute(query, params)
    return cur.fetchall()


def es_admin_sistema(cur, usuario_id: int) -> bool:
    """Admin de sistemas: rol legacy COM-21 o membresía activa al grupo de sistema."""
    cur.execute("SELECT rol FROM usuarios WHERE id = %s;", (usuario_id,))
    row = cur.fetchone()
    if row and row["rol"] == "Administrador Sistema":
        return True
    return len(_membresias(cur, usuario_id, GRUPO_SISTEMA)) > 0


def es_administrativo_global(cur, usuario_id: int) -> bool:
    """Administrativo municipal con alcance GLOBAL (comedor_id NULL)."""
    membresias = _membresias(cur, usuario_id, GRUPO_ADMINISTRATIVO)
    return any(m["comedor_id"] is None for m in membresias)


def es_administrativo_de_comedor(cur, usuario_id: int, comedor_id: int) -> bool:
    """Administrativo que CUBRE el comedor (alcance global o específico)."""
    return len(_membresias(cur, usuario_id, GRUPO_ADMINISTRATIVO,
                           comedor_id=comedor_id, cobertura=True)) > 0


def es_directivo_de_comedor(cur, usuario_id: int, comedor_id: int, roles=None) -> bool:
    """Directivo del comedor exacto (roles por defecto: todos)."""
    return len(_membresias(cur, usuario_id, GRUPO_DIRECTIVO,
                           comedor_id=comedor_id, roles=roles)) > 0


def es_operativo_de_comedor(cur, usuario_id: int, comedor_id: int) -> bool:
    """Operativo (Cocinero) del comedor exacto."""
    return len(_membresias(cur, usuario_id, GRUPO_OPERATIVO, comedor_id=comedor_id)) > 0


def es_admin_comedor(cur, usuario_id: int, comedor_id: int) -> bool:
    """
    COM-21 + COM-22: puede gestionar el comedor quien cumpla cualquiera de:
      - Legacy usuario_comedor rol 'Administrador' activo.
      - Directivo Presidente/Tesorero del comedor.
      - Administrativo con cobertura sobre el comedor.
    """
    cur.execute("""
        SELECT 1 FROM usuario_comedor
        WHERE usuario_id = %s AND comedor_id = %s
          AND rol = 'Administrador' AND estado_activo = TRUE;
    """, (usuario_id, comedor_id))
    if cur.fetchone():
        return True
    if es_directivo_de_comedor(cur, usuario_id, comedor_id, roles=ROLES_DIRECTIVO_GESTION):
        return True
    return es_administrativo_de_comedor(cur, usuario_id, comedor_id)


def puede_gestionar_grupos(cur, usuario_id: int, ambito: str, comedor_id=None) -> bool:
    """
    COM-22: quién puede asignar/desactivar membresías según el ámbito del grupo:
      - SISTEMA : solo Administrador de Sistemas.
      - GLOBAL  : Admin de Sistemas o Administrativo global.
      - COMEDOR : Admin de Sistemas, Administrativo que cubra el comedor,
                  o Directivo Presidente del comedor.
    """
    if es_admin_sistema(cur, usuario_id):
        return True
    if ambito == "SISTEMA":
        return False
    if ambito == "GLOBAL":
        return es_administrativo_global(cur, usuario_id)
    if ambito == "COMEDOR" and comedor_id is not None:
        return (es_administrativo_de_comedor(cur, usuario_id, comedor_id)
                or es_directivo_de_comedor(cur, usuario_id, comedor_id, roles=("Presidente",)))
    return False