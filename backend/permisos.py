"""
permisos.py
Objetivo: Centralizar la lógica de permisos del modelo multi-grupo/multi-comedor
          (COM-21/COM-22), del módulo de gestión de usuarios (COM-23) y del flujo
          de creación/edición de usuarios por perfil (COM-26): privilegios heredados
          por grupo, membresías efectivas que incluyen roles temporales vigentes,
          detección del perfil del creador, matriz de perfiles creables y alcance
          (municipalidades/comedores) del solicitante.
Uso: Importar desde routers (comedores.py, grupos.py, usuarios.py, municipalidades.py,
     vistas.py). Todas las funciones reciben un cursor psycopg2 activo (RealDictCursor).

Historial:
 - COM-22: permisos por grupos/roles/alcances y puede_gestionar_grupos.
 - COM-23: catálogo de claves de privilegios, tiene_privilegio(), sweep de roles
   temporales expirados y membresías efectivas con roles_temporales vigentes.
 - COM-26: perfiles de usuario (obtener_perfil_usuario), matriz de creación por perfil
   (puede_crear_perfil), alcance municipal/comedor (alcance_municipalidades,
   alcance_comedores) y validación de cargos permanentes no repetibles.
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

# ==========================================
# Claves de privilegios (COM-23) - catálogo sembrado en la tabla privilegios
# ==========================================
PRIV_GESTION_MUNICIPALIDADES = "GESTION_MUNICIPALIDADES"
PRIV_GESTION_COMEDORES = "GESTION_COMEDORES"
PRIV_GESTION_GRUPOS = "GESTION_GRUPOS"
PRIV_GESTION_USUARIOS = "GESTION_USUARIOS"
PRIV_GESTION_POLITICAS_CLAVE = "GESTION_POLITICAS_CLAVE"
PRIV_GESTION_USUARIOS_COMEDOR = "GESTION_USUARIOS_COMEDOR"
PRIV_REPORTES = "REPORTES"
PRIV_AUDITORIA = "AUDITORIA"

# ==========================================
# COM-26: PERFILES DE USUARIO Y MATRIZ DE CREACIÓN
# ==========================================
PERFIL_ADMIN_SISTEMA = "ADMINISTRADOR_SISTEMA"
PERFIL_ADMINISTRATIVO = "ADMINISTRATIVO"
PERFIL_DIRECTIVO = "DIRECTIVO"
PERFIL_OPERATIVO = "OPERATIVO"

# Matriz de perfiles que cada creador puede crear/editar (regla de negocio COM-26):
#   - Admin de Sistemas: Sistema, Administrativo y Directivo (NO Operativo).
#   - Administrativo: solo Administrativo (limitado a sus municipalidades).
#   - Directivo: Directivo y Operativo (limitado a sus comedores).
#   - Operativo: no crea ni edita usuarios.
MATRIZ_CREACION_PERFILES = {
    PERFIL_ADMIN_SISTEMA: {PERFIL_ADMIN_SISTEMA, PERFIL_ADMINISTRATIVO, PERFIL_DIRECTIVO},
    PERFIL_ADMINISTRATIVO: {PERFIL_ADMINISTRATIVO},
    PERFIL_DIRECTIVO: {PERFIL_DIRECTIVO, PERFIL_OPERATIVO},
    PERFIL_OPERATIVO: set(),
}

# Cargos permanentes que NO pueden repetirse por comedor (COM-26). El único cargo
# permanente repetible es Cocinero; las asignaciones temporales (roles_temporales)
# no cuentan como cargos permanentes.
CARGOS_NO_REPETIBLES = ("Presidente", "Tesorero", "Secretario")


# ==========================================
# ROLES TEMPORALES (COM-23)
# ==========================================
def expirar_roles_temporales(cur):
    """
    Sweep perezoso: marca como EXPIRADO los roles temporales cuya vigencia terminó.
    Retorna el número de filas actualizadas. El caller es responsable del commit.
    """
    cur.execute("""
        UPDATE roles_temporales
        SET estado = 'EXPIRADO'
        WHERE estado = 'VIGENTE' AND fecha_fin < CURRENT_TIMESTAMP;
    """)
    return cur.rowcount


# ==========================================
# MEMBRESÍAS EFECTIVAS (COM-22 + COM-23)
# ==========================================
def _membresias(cur, usuario_id, grupo_nombre, comedor_id=None, roles=None, cobertura=False):
    """
    Consulta membresías ACTIVAS de un usuario en un grupo, incluyendo roles
    temporales vigentes (COM-23): un otorgamiento temporal dentro de su ventana
    fecha_inicio/fecha_fin con estado VIGENTE equivale a membresía efectiva.
    Si se indica comedor_id:
      - cobertura=True : acepta alcance global (NULL) o el comedor (grupos GLOBAL).
      - cobertura=False: exige el comedor exacto (grupos COMEDOR).
    """
    query = """
        SELECT m.id, m.comedor_id, m.grupo, m.ambito, m.rol
        FROM (
            SELECT ug.id, ug.comedor_id, g.nombre AS grupo, g.ambito, r.nombre AS rol
            FROM usuario_grupo ug
            JOIN grupos_usuario g ON g.id = ug.grupo_id
            JOIN roles_grupo r ON r.id = ug.rol_id
            WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE
            UNION
            SELECT rt.id, rt.comedor_id, g.nombre AS grupo, g.ambito, r.nombre AS rol
            FROM roles_temporales rt
            JOIN roles_grupo r ON r.id = rt.rol_id
            JOIN grupos_usuario g ON g.id = r.grupo_id
            WHERE rt.usuario_id = %s AND rt.estado = 'VIGENTE'
              AND CURRENT_TIMESTAMP BETWEEN rt.fecha_inicio AND rt.fecha_fin
        ) m
        WHERE m.grupo = %s
    """
    params = [usuario_id, usuario_id, grupo_nombre]
    if comedor_id is not None:
        if cobertura:
            query += " AND (m.comedor_id IS NULL OR m.comedor_id = %s)"
        else:
            query += " AND m.comedor_id = %s"
        params.append(comedor_id)
    if roles:
        query += f" AND m.rol IN ({', '.join(['%s'] * len(roles))})"
        params.extend(list(roles))
    cur.execute(query, params)
    return cur.fetchall()


# ==========================================
# PERFILES Y ROLES EFECTIVOS
# ==========================================
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
    COM-21 + COM-22 + COM-23: puede gestionar el comedor quien cumpla cualquiera de:
      - Legacy usuario_comedor rol 'Administrador' activo.
      - Directivo Presidente/Tesorero del comedor (incluye roles temporales vigentes).
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


# ==========================================
# PRIVILEGIOS (COM-23)
# ==========================================
def tiene_privilegio(cur, usuario_id, clave_privilegio, comedor_id=None) -> bool:
    """
    True si el usuario posee el privilegio mediante una membresía activa cuyo grupo
    lo tenga asignado en grupos_privilegios:
      - Administrador de Sistemas: posee todos los privilegios.
      - Con comedor_id: acepta membresías de alcance global (NULL) o de ese comedor.
      - Sin comedor_id: cualquier membresía activa cuyo grupo tenga el privilegio.
    """
    if es_admin_sistema(cur, usuario_id):
        return True
    query = """
        SELECT 1
        FROM usuario_grupo ug
        JOIN grupos_privilegios gp ON gp.grupo_id = ug.grupo_id
        JOIN privilegios p ON p.id = gp.privilegio_id
        WHERE ug.usuario_id = %s AND ug.estado_activo = TRUE AND p.clave = %s
    """
    params = [usuario_id, clave_privilegio]
    if comedor_id is not None:
        query += " AND (ug.comedor_id IS NULL OR ug.comedor_id = %s)"
        params.append(comedor_id)
    query += " LIMIT 1;"
    cur.execute(query, params)
    return cur.fetchone() is not None


def puede_gestionar_usuarios_comedor(cur, usuario_id: int, comedor_id: int) -> bool:
    """COM-23: activar/desactivar usuarios, grupos, roles temporales y desbloqueo por
    intentos DENTRO de un comedor: admin de sistemas o privilegio con cobertura."""
    if es_admin_sistema(cur, usuario_id):
        return True
    return tiene_privilegio(cur, usuario_id, PRIV_GESTION_USUARIOS_COMEDOR, comedor_id)


def puede_gestionar_usuarios_global(cur, usuario_id: int) -> bool:
    """COM-23: crear usuarios y bloquear/desbloquear cuentas (ámbito global)."""
    if es_admin_sistema(cur, usuario_id):
        return True
    return tiene_privilegio(cur, usuario_id, PRIV_GESTION_USUARIOS)


def puede_gestionar_politicas_clave(cur, usuario_id: int) -> bool:
    """COM-23: modificar la política de contraseñas (longitud, expiración, intentos)."""
    if es_admin_sistema(cur, usuario_id):
        return True
    return tiene_privilegio(cur, usuario_id, PRIV_GESTION_POLITICAS_CLAVE)


def puede_gestionar_municipalidades(cur, usuario_id: int) -> bool:
    """COM-23: crear/editar municipalidades del registro nacional."""
    if es_admin_sistema(cur, usuario_id):
        return True
    return tiene_privilegio(cur, usuario_id, PRIV_GESTION_MUNICIPALIDADES)


def puede_gestionar_comedores_nacional(cur, usuario_id: int) -> bool:
    """COM-23: crear/editar comedores a nivel nacional."""
    if es_admin_sistema(cur, usuario_id):
        return True
    return tiene_privilegio(cur, usuario_id, PRIV_GESTION_COMEDORES)


def puede_gestionar_grupos_y_privilegios(cur, usuario_id: int) -> bool:
    """COM-23: crear grupos y asignarles privilegios."""
    if es_admin_sistema(cur, usuario_id):
        return True
    return tiene_privilegio(cur, usuario_id, PRIV_GESTION_GRUPOS)


def puede_gestionar_grupos(cur, usuario_id: int, ambito: str, comedor_id=None) -> bool:
    """
    COM-22: quién puede asignar/desactivar membresías según el ámbito del grupo:
      - SISTEMA : solo Administrador de Sistemas.
      - GLOBAL  : Admin de Sistemas o Administrativo global.
      - COMEDOR : Admin de Sistemas, Administrativo que cubra el comedor,
                  o Directivo Presidente del comedor (incluye rol temporal vigente).
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


# ==========================================
# COM-26: PERFIL DEL CREADOR Y MATRIZ DE CREACIÓN
# ==========================================
def obtener_perfil_usuario(cur, usuario_id: int):
    """
    COM-26: Determina el perfil primario del usuario según sus membresías activas
    (incluye roles temporales vigentes), con prioridad:
      Administrador de Sistemas > Administrativo > Directivo > Operativo.
    Retorna None si el usuario no tiene membresías activas.
    """
    if es_admin_sistema(cur, usuario_id):
        return PERFIL_ADMIN_SISTEMA
    if len(_membresias(cur, usuario_id, GRUPO_ADMINISTRATIVO)) > 0:
        return PERFIL_ADMINISTRATIVO
    if len(_membresias(cur, usuario_id, GRUPO_DIRECTIVO)) > 0:
        return PERFIL_DIRECTIVO
    if len(_membresias(cur, usuario_id, GRUPO_OPERATIVO)) > 0:
        return PERFIL_OPERATIVO
    return None


def puede_crear_perfil(cur, solicitante_id: int, perfil_objetivo: str) -> bool:
    """
    COM-26: aplica la matriz de creación/edición de usuarios según el perfil del
    creador. El alcance (municipalidades o comedores permitidos) se valida aparte
    con alcance_municipalidades / alcance_comedores.
    """
    perfil_creador = obtener_perfil_usuario(cur, solicitante_id)
    if not perfil_creador:
        return False
    return perfil_objetivo in MATRIZ_CREACION_PERFILES.get(perfil_creador, set())


def alcance_municipalidades(cur, usuario_id: int):
    """
    COM-26: municipalidades que el usuario puede asignar al crear/editar personal
    Administrativo. El administrador de sistemas no tiene restricción (todas); el
    personal Administrativo solo las municipalidades a las que pertenece (activas).
    """
    if es_admin_sistema(cur, usuario_id):
        cur.execute("""
            SELECT id, nombre, departamento, provincia, distrito
            FROM municipalidades
            ORDER BY nombre;
        """)
        return cur.fetchall()
    cur.execute("""
        SELECT m.id, m.nombre, m.departamento, m.provincia, m.distrito
        FROM usuario_municipalidad um
        JOIN municipalidades m ON m.id = um.municipalidad_id
        WHERE um.usuario_id = %s AND um.estado_activo = TRUE
        ORDER BY m.nombre;
    """, (usuario_id,))
    return cur.fetchall()


def alcance_comedores(cur, usuario_id: int):
    """
    COM-26: comedores que el usuario puede asignar al crear/editar personal
    Directivo/Operativo. El administrador de sistemas no tiene restricción (todos);
    el personal Directivo solo los comedores donde tiene membresía activa.
    """
    if es_admin_sistema(cur, usuario_id):
        cur.execute("""
            SELECT id, nombre, departamento, ciudad, distrito
            FROM comedores
            ORDER BY nombre;
        """)
        return cur.fetchall()
    cur.execute("""
        SELECT DISTINCT c.id, c.nombre, c.departamento, c.ciudad, c.distrito
        FROM usuario_comedor uc
        JOIN comedores c ON c.id = uc.comedor_id
        WHERE uc.usuario_id = %s AND uc.estado_activo = TRUE
        ORDER BY c.nombre;
    """, (usuario_id,))
    return cur.fetchall()


def es_cargo_no_repetible(cur, rol_id: int) -> bool:
    """COM-26: True si el rol corresponde a un cargo permanente no repetible
    (Presidente, Tesorero o Secretario). Cocinero es el único repetible."""
    cur.execute("SELECT nombre FROM roles_grupo WHERE id = %s;", (rol_id,))
    row = cur.fetchone()
    return bool(row) and row["nombre"] in CARGOS_NO_REPETIBLES


def hay_cargo_permanente_ocupado(cur, comedor_id: int, rol_id: int,
                                 excluir_usuario_id: int = None) -> bool:
    """
    COM-26: True si el cargo permanente del comedor ya está ocupado por otro usuario
    con membresía activa. Los roles temporales (roles_temporales) NO cuentan como
    cargos permanentes, por lo que no bloquean la asignación.
    `excluir_usuario_id` permite la edición del propio usuario sin auto-bloquearse.
    """
    query = """
        SELECT 1
        FROM usuario_grupo ug
        WHERE ug.comedor_id = %s AND ug.rol_id = %s AND ug.estado_activo = TRUE
    """
    params = [comedor_id, rol_id]
    if excluir_usuario_id is not None:
        query += " AND ug.usuario_id <> %s"
        params.append(excluir_usuario_id)
    query += " LIMIT 1;"
    cur.execute(query, params)
    return cur.fetchone() is not None