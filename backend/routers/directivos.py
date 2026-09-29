"""
routers/directivos.py
Objetivo: COM-39: gestión de la directiva de un comedor por el Administrador de
          Sistemas: búsqueda de comedores por distrito + nombre, listado de directivos
          activos (grupo Directivo: Presidente/Secretario/Tesorero) con sus roles y
          roles vacantes, y aplicación TRANSACCIONAL POR LOTES de operaciones de
          'baja' y 'reemplazo' de cargo. En un reemplazo, si la persona nueva no existe
          en la BD, se crea en el momento con clave provisoria (flujo COM-19).
Historial:
 - COM-39 (este archivo): creación del módulo. En una entrega anterior fue etiquetado
   por error como "COM-38 v2"; se corrige la trazabilidad a COM-39 sin cambios
   funcionales (mismas rutas, mismos payloads).
Permisos: Todos los endpoints exigen es_admin_sistema (el panel es exclusivo del Admin).
Modelo de datos: la fuente de verdad de membresías es usuario_grupo (COM-22); NO se
          toca usuario_comedor (legado COM-21) para no disparar migraciones de roles.
Uso: Registrado en main.py con prefijo /api/v1 (comparte prefijo /comedores).
Referencia: ticket COM-39 (solo trazabilidad; los nombres obedecen a la funcionalidad).
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from database import get_db
from permisos import es_admin_sistema
from seguridad import hashear_clave, CLAVE_INICIAL

router = APIRouter(prefix="/comedores", tags=["Directivos de Comedor (COM-39)"])

# Roles del grupo Directivo que se gestionan en este módulo
ROLES_DIRECTIVO = ('Presidente', 'Secretario', 'Tesorero')


# ==========================================
# MODELOS DE ENTRADA
# ==========================================
class NuevoUsuarioDirectivo(BaseModel):
    """Datos mínimos para registrar en el momento a una persona inexistente."""
    tipo_documento: str = 'DNI'
    documento_identidad: str
    nombres: str
    apellido_paterno: str
    apellido_materno: str = ''
    fecha_nacimiento: str          # YYYY-MM-DD


class OperacionDirectivo(BaseModel):
    """
    Una operación en cola del panel:
      - operacion='baja':      desactiva la membresía Directivo/rol del usuario origen.
      - operacion='reemplazo': desactiva al origen y activa/crea la membresía del nuevo
                               usuario (usuario_nuevo_id) o lo registra (nuevo_usuario).
    """
    operacion: str                                   # 'baja' | 'reemplazo'
    rol_nombre: str                                  # Presidente | Secretario | Tesorero
    usuario_origen_id: int
    membresia_id: Optional[int] = None               # id de usuario_grupo (preferido)
    usuario_nuevo_id: Optional[int] = None           # persona existente seleccionada
    nuevo_usuario: Optional[NuevoUsuarioDirectivo] = None  # registro en el momento


class ActualizarDirectivosInput(BaseModel):
    """Lote de operaciones aplicadas en una sola transacción."""
    usuario_solicitante_id: int
    operaciones: List[OperacionDirectivo]


# ==========================================
# HELPERS
# ==========================================
def _validar_admin(cur, usuario_id: int) -> None:
    if not usuario_id or not es_admin_sistema(cur, usuario_id):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso: la gestión de directivos es exclusiva del Administrador de Sistemas.")


def _rol_directivo_id(cur, rol_nombre: str) -> int:
    if rol_nombre not in ROLES_DIRECTIVO:
        raise HTTPException(status_code=400,
                        detail=f"Rol inválido: use uno de {ROLES_DIRECTIVO}.")
    cur.execute("""
        SELECT r.id
        FROM roles_grupo r
        JOIN grupos_usuario g ON g.id = r.grupo_id
        WHERE g.nombre = 'Directivo' AND r.nombre = %s;
    """, (rol_nombre,))
    fila = cur.fetchone()
    if not fila:
        raise HTTPException(status_code=500, detail="Catálogo de roles Directivo no inicializado.")
    return fila['id']


def _grupo_directivo_id(cur) -> int:
    cur.execute("SELECT id FROM grupos_usuario WHERE nombre = 'Directivo';")
    fila = cur.fetchone()
    if not fila:
        raise HTTPException(status_code=500, detail="Grupo 'Directivo' no inicializado.")
    return fila['id']


def _nombre_usuario(cur, usuario_id: int) -> str:
    cur.execute("""
        SELECT nombres, apellido_paterno, documento_identidad
        FROM usuarios WHERE id = %s;
    """, (usuario_id,))
    f = cur.fetchone()
    return f"{f['nombres']} {f['apellido_paterno']} (DNI {f['documento_identidad']})" if f else f"id {usuario_id}"


def _crear_usuario_en_el_momento(cur, datos: NuevoUsuarioDirectivo) -> int:
    """
    COM-39: registra a la persona con clave provisoria Nutri2026 (cambio obligatorio
    en primer login, COM-19). El rol legacy se fija en 'Operador' para que las
    migraciones de arranque NO la promuevan a Administrador de Sistemas.
    """
    try:
        fecha_nac = date.fromisoformat(datos.fecha_nacimiento)
    except Exception:
        raise HTTPException(status_code=400, detail="fecha_nacimiento inválida (use YYYY-MM-DD).")
    cur.execute("""
        INSERT INTO usuarios
            (tipo_documento, documento_identidad, nombres, apellido_paterno, apellido_materno,
             fecha_nacimiento, clave_hash, rol, estado_activo, clave_provisoria, fecha_clave)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'Operador', TRUE, TRUE,
                CURRENT_TIMESTAMP - INTERVAL '5 hours')
        RETURNING id;
    """, (
        datos.tipo_documento or 'DNI',
        datos.documento_identidad.strip(),
        datos.nombres.strip(),
        datos.apellido_paterno.strip(),
        (datos.apellido_materno or '').strip(),
        fecha_nac,
        hashear_clave(CLAVE_INICIAL),
    ))
    return cur.fetchone()['id']


def _desactivar_membresia(cur, membresia_id: int, usuario_id: int, rol_id: int,
                          comedor_id: int, solicitante_id: int) -> None:
    """Baja lógica de la membresía Directivo/rol/comedor (idempotente)."""
    if membresia_id:
        cur.execute("""
            UPDATE usuario_grupo
            SET estado_activo = FALSE,
                desactivado_por = %s,
                fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
            WHERE id = %s AND estado_activo = TRUE;
        """, (solicitante_id, membresia_id))
    else:
        cur.execute("""
            UPDATE usuario_grupo
            SET estado_activo = FALSE,
                desactivado_por = %s,
                fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
            WHERE usuario_id = %s AND rol_id = %s AND comedor_id = %s AND estado_activo = TRUE;
        """, (solicitante_id, usuario_id, rol_id, comedor_id))


def _activar_membresia(cur, usuario_id: int, grupo_id: int, rol_id: int,
                       comedor_id: int) -> None:
    """
    Alta o reactivación de la membresía Directivo/rol/comedor. Si ya existía inactiva,
    se reactiva; si existía otra persona ACTIVA en el mismo rol, se desactiva primero
    (garantiza un solo titular por cargo).
    """
    cur.execute("""
        UPDATE usuario_grupo
        SET estado_activo = FALSE,
            fecha_desactivacion = CURRENT_TIMESTAMP - INTERVAL '5 hours'
        WHERE rol_id = %s AND comedor_id = %s AND estado_activo = TRUE AND usuario_id <> %s;
    """, (rol_id, comedor_id, usuario_id))
    cur.execute("""
        INSERT INTO usuario_grupo (usuario_id, grupo_id, rol_id, comedor_id, estado_activo)
        VALUES (%s, %s, %s, %s, TRUE)
        ON CONFLICT (usuario_id, grupo_id, rol_id, comedor_id)
        DO UPDATE SET estado_activo = TRUE,
                      desactivado_por = NULL,
                      fecha_desactivacion = NULL;
    """, (usuario_id, grupo_id, rol_id, comedor_id))


# ==========================================
# BÚSQUEDA DE COMEDORES POR DISTRITO + NOMBRE
# ==========================================
@router.get("/buscar-por-distrito")
def buscar_comedores_por_distrito(
    usuario_solicitante_id: int,
    distrito: str = Query('', description="Nombre del distrito (cascade COM-27)"),
    q: str = Query('', description="Texto del nombre del comedor"),
    db=Depends(get_db),
):
    """COM-39: comedores del distrito elegido cuyo nombre coincide con el texto."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        query = """
            SELECT id, nombre, departamento, ciudad, distrito, zona, direccion
            FROM comedores
            WHERE (%s = '' OR distrito ILIKE %s)
              AND (%s = '' OR nombre ILIKE %s)
            ORDER BY nombre
            LIMIT 20;
        """
        cur.execute(query, (distrito, f"%{distrito}%", q, f"%{q}%"))
        return cur.fetchall()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al buscar comedores: {e}")
    finally:
        cur.close()


# ==========================================
# LISTADO DE DIRECTIVOS Y ROLES VACANTES
# ==========================================
@router.get("/{comedor_id}/directivos")
def listar_directivos(comedor_id: int, usuario_solicitante_id: int, db=Depends(get_db)):
    """COM-39: directivos activos del comedor + cargos sin titular."""
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, usuario_solicitante_id)
        cur.execute("SELECT id, nombre FROM comedores WHERE id = %s;", (comedor_id,))
        comedor = cur.fetchone()
        if not comedor:
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")
        cur.execute("""
            SELECT ug.id AS membresia_id, u.id AS usuario_id,
                   u.tipo_documento, u.documento_identidad,
                   u.nombres, u.apellido_paterno, u.apellido_materno,
                   r.nombre AS rol, u.estado_activo AS cuenta_activa
            FROM usuario_grupo ug
            JOIN grupos_usuario g ON g.id = ug.grupo_id
            JOIN roles_grupo r ON r.id = ug.rol_id
            JOIN usuarios u ON u.id = ug.usuario_id
            WHERE ug.comedor_id = %s AND g.nombre = 'Directivo' AND ug.estado_activo = TRUE
            ORDER BY r.nombre, u.nombres;
        """, (comedor_id,))
        directivos = cur.fetchall()
        ocupados = {d['rol'] for d in directivos}
        vacantes = [r for r in ROLES_DIRECTIVO if r not in ocupados]
        return {
            'comedor_id': comedor_id,
            'comedor_nombre': comedor['nombre'],
            'directivos': directivos,
            'roles_vacantes': vacantes,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar directivos: {e}")
    finally:
        cur.close()


# ==========================================
# APLICACIÓN POR LOTES DE BAJAS Y REEMPLAZOS
# ==========================================
@router.post("/{comedor_id}/directivos/actualizar")
def actualizar_directivos(comedor_id: int, data: ActualizarDirectivosInput, db=Depends(get_db)):
    """
    COM-39: aplica en UNA transacción todas las operaciones en cola (bajas y
    reemplazos). Si un reemplazo incluye `nuevo_usuario`, se registra a la persona en
    el momento (clave provisoria Nutri2026). Retorna el detalle para el mensaje de
    confirmación de cambios de cargo.
    """
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        _validar_admin(cur, data.usuario_solicitante_id)
        if not data.operaciones:
            raise HTTPException(status_code=400, detail="No hay operaciones que aplicar.")

        cur.execute("SELECT id FROM comedores WHERE id = %s;", (comedor_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Comedor no encontrado.")

        grupo_id = _grupo_directivo_id(cur)
        detalle = []

        for op in data.operaciones:
            rol_id = _rol_directivo_id(cur, op.rol_nombre)

            if op.operacion == 'baja':
                _desactivar_membresia(cur, op.membresia_id, op.usuario_origen_id,
                                      rol_id, comedor_id, data.usuario_solicitante_id)
                detalle.append({
                    'operacion': 'baja',
                    'rol': op.rol_nombre,
                    'origen': _nombre_usuario(cur, op.usuario_origen_id),
                    'nuevo': None,
                })

            elif op.operacion == 'reemplazo':
                if not op.usuario_nuevo_id and not op.nuevo_usuario:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Reemplazo de {op.rol_nombre}: indique usuario_nuevo_id o nuevo_usuario.")
                # 1) Baja del titular actual
                _desactivar_membresia(cur, op.membresia_id, op.usuario_origen_id,
                                      rol_id, comedor_id, data.usuario_solicitante_id)
                # 2) Resolución de la persona entrante (existente o registro en el momento)
                if op.usuario_nuevo_id:
                    nuevo_id = op.usuario_nuevo_id
                    cur.execute("SELECT id FROM usuarios WHERE id = %s;", (nuevo_id,))
                    if not cur.fetchone():
                        raise HTTPException(status_code=404, detail="El usuario nuevo no existe.")
                else:
                    nuevo_id = _crear_usuario_en_el_momento(cur, op.nuevo_usuario)
                # 3) Alta/reactivación de la membresía del nuevo titular
                _activar_membresia(cur, nuevo_id, grupo_id, rol_id, comedor_id)
                detalle.append({
                    'operacion': 'reemplazo',
                    'rol': op.rol_nombre,
                    'origen': _nombre_usuario(cur, op.usuario_origen_id),
                    'nuevo': _nombre_usuario(cur, nuevo_id),
                })
            else:
                raise HTTPException(status_code=400,
                                detail=f"Operación inválida: {op.operacion} (use 'baja' o 'reemplazo').")

        db.commit()
        lineas = [
            f"{d['rol']}: {d['origen']} → {d['nuevo']}" if d['operacion'] == 'reemplazo'
            else f"{d['rol']}: baja de {d['origen']}"
            for d in detalle
        ]
        return {
            'aplicadas': len(detalle),
            'detalle': detalle,
            'message': "Cambios de cargo aplicados: " + "; ".join(lineas),
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar directivos: {e}")
    finally:
        cur.close()