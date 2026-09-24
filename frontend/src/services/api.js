/**
 * services/api.js
 * Objetivo: Servicio centralizado de comunicación HTTP con la API del backend.
 *           Todos los componentes consumen este módulo en lugar de hacer fetch directo,
 *           lo que garantiza un manejo uniforme de errores, cabeceras y endpoints.
 * Uso: Importar `api` en hooks y componentes para consumir los endpoints del sistema.
 *
 * Historial:
 *  - COM-17: parser defensivo `leerErrorSeguro` (evita "Unexpected token 'I'" con 500 en texto plano).
 *  - COM-19: endpoints de autenticación (login, cambiar-clave).
 *  - COM-20: getContextoSeleccion y verificarMembresia (selección de comedor post-login).
 *  - COM-21: bloque COMEDORES (CRUD, usuarios por comedor, asociación, estado, búsqueda).
 *  - COM-22: bloque GRUPOS (catálogo, membresías, asignación y estado).
 *  - COM-23: bloque USUARIOS (creación, bloqueo/desbloqueo, política de claves),
 *            bloque MUNICIPALIDADES (CRUD) y extensiones de GRUPOS (privilegios,
 *            creación de grupos y roles temporales con vigencia/revocación).
 *  - COM-25: bloque VISTAS (catálogo de módulos del sistema, matriz de permisos por rol,
 *            edición de permisos por rol y módulos efectivos del usuario en sesión).
 *  - COM-26: flujo CRUD de usuarios por perfil: contextoCreacion, crearUsuario y
 *            editarUsuario con perfil objetivo y alcance, más los métodos de búsqueda
 *            buscarMunicipalidades y buscarComedores para el autocompletado.
 */
const API_BASE = '/api/v1';

/**
 * Parser defensivo de errores: si el cuerpo no es JSON, devuelve un mensaje legible.
 */
const leerErrorSeguro = async (response, mensajePorDefecto) => {
    try {
        const data = await response.json();
        if (typeof data.detail === 'object' && data.detail !== null) {
            return data.detail.mensaje || mensajePorDefecto;
        }
        return data.detail || data.message || mensajePorDefecto;
    } catch (e) {
        return `${mensajePorDefecto} (HTTP ${response.status})`;
    }
};

export const api = {
    // ==========================================
    // AUTENTICACIÓN (COM-19)
    // ==========================================
    login: async (data) => {
        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const body = await response.json().catch(() => ({}));
            return { ok: response.ok, status: response.status, data: body };
        } catch (err) {
            return { ok: false, status: 0, data: { detail: 'Error de conexión con el servidor.' } };
        }
    },
    cambiarClave: async (data) => {
        try {
            const response = await fetch(`${API_BASE}/auth/cambiar-clave`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const body = await response.json().catch(() => ({}));
            return { ok: response.ok, status: response.status, data: body };
        } catch (err) {
            return { ok: false, status: 0, data: { detail: 'Error de conexión con el servidor.' } };
        }
    },

    // ==========================================
    // PARÁMETROS DINÁMICOS
    // ==========================================
    getParametros: async () => {
        const response = await fetch(`${API_BASE}/parametros`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener parámetros'));
        return response.json();
    },

    // ==========================================
    // COMEDORES (COM-21) Y CONTEXTO DE SELECCIÓN (COM-20)
    // ==========================================
    getComedores: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/comedores?${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comedores'));
        return response.json();
    },
    getComedorDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/comedores/${id}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el comedor'));
        return response.json();
    },
    createComedor: async (data) => {
        const response = await fetch(`${API_BASE}/comedores`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear el comedor'));
        return response.json();
    },
    updateComedor: async (id, data) => {
        const response = await fetch(`${API_BASE}/comedores/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar el comedor'));
        return response.json();
    },
    // COM-26: búsqueda de comedores para el autocompletado del formulario de usuarios
    buscarComedores: async (q) => {
        const response = await fetch(`${API_BASE}/comedores/buscar?q=${encodeURIComponent(q || '')}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al buscar comedores'));
        return response.json();
    },
    getComedoresDeUsuario: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/comedores/por-usuario/${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comedores del usuario'));
        return response.json();
    },
    buscarUsuarioPorDocumento: async (documento) => {
        const response = await fetch(`${API_BASE}/comedores/usuarios/buscar?documento=${encodeURIComponent(documento)}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Usuario no encontrado'));
        return response.json();
    },
    getUsuariosComedor: async (comedorId) => {
        const response = await fetch(`${API_BASE}/comedores/${comedorId}/usuarios`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener usuarios del comedor'));
        return response.json();
    },
    asociarUsuarioComedor: async (comedorId, data) => {
        const response = await fetch(`${API_BASE}/comedores/${comedorId}/usuarios`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al asociar el usuario'));
        return response.json();
    },
    cambiarEstadoUsuarioComedor: async (comedorId, usuarioId, data) => {
        const response = await fetch(`${API_BASE}/comedores/${comedorId}/usuarios/${usuarioId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cambiar el estado'));
        return response.json();
    },
    getContextoSeleccion: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/comedores/contexto-seleccion?usuario_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el contexto de selección'));
        return response.json();
    },
    verificarMembresia: async (usuarioId, comedorId, perfil) => {
        const params = new URLSearchParams({ usuario_id: String(usuarioId), perfil: perfil || 'COMEDOR' });
        if (comedorId !== null && comedorId !== undefined) {
            params.append('comedor_id', String(comedorId));
        }
        const response = await fetch(`${API_BASE}/comedores/verificar-membresia?${params.toString()}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al verificar la membresía'));
        return response.json();
    },

    // ==========================================
    // GRUPOS, PRIVILEGIOS Y ROLES TEMPORALES (COM-22 / COM-23)
    // ==========================================
    getGrupos: async () => {
        const response = await fetch(`${API_BASE}/grupos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener grupos'));
        return response.json();
    },
    getGruposDeUsuario: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/grupos/por-usuario/${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener grupos del usuario'));
        return response.json();
    },
    getMembresias: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/grupos/membresias?${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener membresías'));
        return response.json();
    },
    asignarGrupo: async (data) => {
        const response = await fetch(`${API_BASE}/grupos/membresias`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al asignar el grupo'));
        return response.json();
    },
    cambiarEstadoMembresia: async (membresiaId, data) => {
        const response = await fetch(`${API_BASE}/grupos/membresias/${membresiaId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cambiar el estado de la membresía'));
        return response.json();
    },
    getPrivilegios: async () => {
        const response = await fetch(`${API_BASE}/grupos/privilegios`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener privilegios'));
        return response.json();
    },
    createGrupo: async (data) => {
        const response = await fetch(`${API_BASE}/grupos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear el grupo'));
        return response.json();
    },
    asignarPrivilegiosGrupo: async (grupoId, data) => {
        const response = await fetch(`${API_BASE}/grupos/${grupoId}/privilegios`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al asignar privilegios'));
        return response.json();
    },
    getRolesTemporales: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/grupos/roles-temporales?${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener roles temporales'));
        return response.json();
    },
    otorgarRolTemporal: async (data) => {
        const response = await fetch(`${API_BASE}/grupos/roles-temporales`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al otorgar el rol temporal'));
        return response.json();
    },
    revocarRolTemporal: async (rolTemporalId, data) => {
        const response = await fetch(`${API_BASE}/grupos/roles-temporales/${rolTemporalId}/revocar`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al revocar el rol temporal'));
        return response.json();
    },

    // ==========================================
    // PERMISOS POR VISTAS (COM-25)
    // ==========================================
    getModulosSistema: async () => {
        const response = await fetch(`${API_BASE}/vistas/modulos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener los módulos del sistema'));
        return response.json();
    },
    getMatrizPermisos: async () => {
        const response = await fetch(`${API_BASE}/vistas/permisos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la matriz de permisos'));
        return response.json();
    },
    updatePermisosRol: async (rolId, data) => {
        const response = await fetch(`${API_BASE}/vistas/permisos/${rolId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar los permisos del rol'));
        return response.json();
    },
    getMisModulos: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/vistas/mis-modulos?usuario_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener sus módulos permitidos'));
        return response.json();
    },

    // ==========================================
    // USUARIOS: FLUJO CRUD POR PERFIL (COM-23 / COM-26)
    // ==========================================
    getUsuarios: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/usuarios?${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener usuarios'));
        return response.json();
    },
    /**
     * COM-26: contexto de creación/edición según el perfil del creador:
     * perfil del solicitante, perfiles que puede crear, grupos/roles por perfil
     * y alcance permitido (municipalidades y/o comedores).
     */
    getContextoCreacion: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/usuarios/contexto-creacion?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el contexto de creación'));
        return response.json();
    },
    /**
     * COM-26: creación de usuario con perfil objetivo y alcance
     * (municipalidad_ids para Administrativo, comedor_ids para Directivo/Operativo).
     */
    crearUsuario: async (data) => {
        const response = await fetch(`${API_BASE}/usuarios`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear el usuario'));
        return response.json();
    },
    /**
     * COM-26: edición de usuario (datos personales + membresías del grupo del perfil objetivo).
     */
    editarUsuario: async (usuarioId, data) => {
        const response = await fetch(`${API_BASE}/usuarios/${usuarioId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al editar el usuario'));
        return response.json();
    },
    /**
     * COM-26: detalle del usuario para precargar la edición (datos personales,
     * perfil, grupo/rol actual y alcance vigente: municipalidades/comedores).
     */
    getDetalleFlujoUsuario: async (usuarioId, solicitanteId) => {
        const response = await fetch(`${API_BASE}/usuarios/${usuarioId}/detalle-flujo?usuario_solicitante_id=${solicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el detalle del usuario'));
        return response.json();
    },
    cambiarEstadoCuenta: async (usuarioId, data) => {
        const response = await fetch(`${API_BASE}/usuarios/${usuarioId}/estado-cuenta`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cambiar el estado de la cuenta'));
        return response.json();
    },
    desbloquearReintentos: async (usuarioId, data) => {
        const response = await fetch(`${API_BASE}/usuarios/${usuarioId}/desbloqueo-reintentos`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al desbloquear por intentos'));
        return response.json();
    },
    getPoliticaClave: async () => {
        const response = await fetch(`${API_BASE}/usuarios/politica-clave`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la política de claves'));
        return response.json();
    },
    updatePoliticaClave: async (data) => {
        const response = await fetch(`${API_BASE}/usuarios/politica-clave`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar la política'));
        return response.json();
    },

    // ==========================================
    // MUNICIPALIDADES (COM-23)
    // ==========================================
    getMunicipalidades: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/municipalidades?${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener municipalidades'));
        return response.json();
    },
    getMunicipalidadDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/municipalidades/${id}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la municipalidad'));
        return response.json();
    },
    getComedoresDeMunicipalidad: async (id) => {
        const response = await fetch(`${API_BASE}/municipalidades/${id}/comedores`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comedores de la municipalidad'));
        return response.json();
    },
    createMunicipalidad: async (data) => {
        const response = await fetch(`${API_BASE}/municipalidades`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear la municipalidad'));
        return response.json();
    },
    updateMunicipalidad: async (id, data) => {
        const response = await fetch(`${API_BASE}/municipalidades/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar la municipalidad'));
        return response.json();
    },
    // COM-26: búsqueda de municipalidades para el autocompletado del formulario de usuarios
    buscarMunicipalidades: async (q) => {
        const response = await fetch(`${API_BASE}/municipalidades/buscar?q=${encodeURIComponent(q || '')}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al buscar municipalidades'));
        return response.json();
    },

    // ==========================================
    // UBICACIÓN GEOGRÁFICA (COM-27)
    // ==========================================
    getDepartamentos: async () => {
        const response = await fetch(`${API_BASE}/ubicaciones/departamentos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener departamentos'));
        return response.json();
    },
    getProvincias: async (departamentoId) => {
        const response = await fetch(`${API_BASE}/ubicaciones/provincias?departamento_id=${departamentoId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener provincias'));
        return response.json();
    },
    getDistritos: async (provinciaId) => {
        const response = await fetch(`${API_BASE}/ubicaciones/distritos?provincia_id=${provinciaId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener distritos'));
        return response.json();
    },
    getMunicipalidadesPorDistrito: async (distritoId) => {
        const response = await fetch(`${API_BASE}/ubicaciones/municipalidades?distrito_id=${distritoId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener municipalidades'));
        return response.json();
    },
        
    // ==========================================
    // CLUSTERING K-MEANS DEL RECETARIO (COM-5)
    // ==========================================
    // Entrena el modelo k=4 sobre recetas aptas (reglas R1-R3) y lo deja activo
    entrenarKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/kmeans/entrenar?usuario_solicitante_id=${usuarioSolicitanteId}`, {
            method: 'POST',
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al entrenar el modelo'));
        return response.json();
    },
    // Resumen del modelo activo; retorna null si aún no existe modelo (404)
    getResumenKmeans: async () => {
        const response = await fetch(`${API_BASE}/kmeans/resumen`);
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el resumen del modelo'));
        return response.json();
    },
    // Recetas asignadas al modelo activo (opcionalmente por cluster 1-4)
    getClustersKmeans: async (clusterCodigo) => {
        const qs = clusterCodigo ? `?cluster_codigo=${clusterCodigo}` : '';
        const response = await fetch(`${API_BASE}/kmeans/clusters${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener recetas del cluster'));
        return response.json();
    },
    // Auditoría de reglas R1-R3: recetas aptas y excluidas con su motivo
    getCandidatasKmeans: async () => {
        const response = await fetch(`${API_BASE}/kmeans/candidatas`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener recetas candidatas'));
        return response.json();
    },

    // ==========================================
    // RECETAS
    // ==========================================
    getRecetas: async (params = {}) => {
        const queryString = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/recetas?${queryString}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener recetas'));
        return response.json();
    },
    getRecetaDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener detalle'));
        return response.json();
    },
    createReceta: async (data) => {
        const response = await fetch(`${API_BASE}/recetas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear receta'));
        return response.json();
    },
    updateReceta: async (id, data) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar receta'));
        return response.json();
    },
    deleteReceta: async (id) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al eliminar receta'));
        return response.json();
    },
    getUnidadesMedida: async () => {
        const response = await fetch(`${API_BASE}/unidades-medida`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener unidades'));
        return response.json();
    },
    getIngredientesDisponibles: async () => {
        const response = await fetch(`${API_BASE}/ingredientes-disponibles`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener ingredientes'));
        return response.json();
    },
    addIngredienteReceta: async (recetaId, data) => {
        const response = await fetch(`${API_BASE}/recetas/${recetaId}/ingredientes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al agregar ingrediente'));
        return response.json();
    },
    deleteIngredienteReceta: async (recetaId, ingredienteId) => {
        const response = await fetch(`${API_BASE}/recetas/${recetaId}/ingredientes/${ingredienteId}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al eliminar ingrediente'));
        return response.json();
    },

    // ==========================================
    // COSTOS Y CATÁLOGO
    // ==========================================
    getCostoReceta: async (id, fecha) => {
        const response = await fetch(`${API_BASE}/recetas/${id}/costo?fecha=${fecha}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener costo'));
        return response.json();
    },
    getIngredientes: async (fecha) => {
        const response = await fetch(`${API_BASE}/ingredientes?fecha=${fecha}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener ingredientes'));
        return response.json();
    },
    getHistoricoPrecios: async (id, rango) => {
        const response = await fetch(`${API_BASE}/ingredientes/${id}/historico?rango=${rango}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener histórico'));
        return response.json();
    },

    // ==========================================
    // PADRÓN Y ESTADÍSTICAS
    // ==========================================
    getPadronStats: async () => {
        const response = await fetch(`${API_BASE}/padron/stats`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener estadísticas'));
        return response.json();
    },
    getVentasHoy: async () => {
        const response = await fetch(`${API_BASE}/padron/hoy`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener ventas'));
        return response.json();
    },
    getPrediccionDemanda: async (fecha) => {
        const response = await fetch(`${API_BASE}/padron/prediccion_demanda?fecha_str=${fecha}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener predicción'));
        return response.json();
    },

    // ==========================================
    // COMENSALES Y VENTAS (POS)
    // ==========================================
    buscarComensal: async (doc) => fetch(`${API_BASE}/comensales/${doc}`),
    registrarComensal: async (data) => fetch(`${API_BASE}/comensales/registrar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }),
    registrarVenta: async (data) => fetch(`${API_BASE}/padron`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }),
    modificarVenta: async (id, data) => fetch(`${API_BASE}/padron/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    }),
    eliminarVenta: async (id) => fetch(`${API_BASE}/padron/${id}`, { method: 'DELETE' }),

    // ==========================================
    // PRESUPUESTO
    // ==========================================
    planificarSemana: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/planificar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al planificar semana'));
        return response.json();
    },
    guardarPlanificacion: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/guardar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al guardar planificación'));
        return response.json();
    },
    getTiposPlatos: async () => {
        const response = await fetch(`${API_BASE}/presupuesto/tipos-platos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener tipos de platos'));
        return response.json();
    },
    calcularPresupuesto: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/calcular`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al calcular presupuesto'));
        return response.json();
    },

    // ==========================================
    // PLANIFICACIONES GUARDADAS
    // ==========================================
    getPlanificaciones: async () => {
        const response = await fetch(`${API_BASE}/planificaciones`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener planificaciones'));
        return response.json();
    },
    getPlanificacionDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener detalle de planificación'));
        return response.json();
    },
    getListaCompras: async (planificacionId, dia = null) => {
        const url = dia
            ? `${API_BASE}/planificaciones/${planificacionId}/lista-compras?dia=${dia}`
            : `${API_BASE}/planificaciones/${planificacionId}/lista-compras`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al generar lista de compras'));
        return response.json();
    },
    eliminarPlanificacion: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al eliminar planificación'));
        return response.json();
    }
};