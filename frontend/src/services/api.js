/**
 * services/api.js
 * Objetivo: Capa única de acceso a la API REST del backend (FastAPI, /api/v1).
 *           Centraliza el fetch, el manejo de errores legibles (leerErrorSeguro) y
 *           expone un método por endpoint consumido desde las vistas React.
 * Historial de bloques:
 *  - Sprint 1-2: AUTH, PARAMETROS, PRESUPUESTO/PLANIFICACIONES, RECETAS, INGREDIENTES,
 *                PADRON/POS, REPORTES.
 *  - COM-19/20: login con clave provisoria y selección de comedor post-login.
 *  - COM-21: COMEDORES (multi-comedor y asociación de usuarios).
 *  - COM-22/23: GRUPOS (privilegios y roles temporales) y USUARIOS/MUNICIPALIDADES.
 *  - COM-25: VISTAS (módulos por grupo/rol).
 *  - COM-26: flujo CRUD de usuarios por perfil (contexto de creación).
 *  - COM-27: UBICACIONES (cascada departamento->provincia->distrito->municipalidad).
 *  - COM-5:  KMEANS (clustering nutricional del recetario).
 *  - COM-8:  PROPUESTAS (motor greedy de menú semanal).
 *  - COM-5 v4 / COM-8 v7: configuración de proteínas del clustering (GET/PUT
 *            /kmeans/proteinas) y bloque MODELOS_ML (panel de gráficos exclusivo del
 *            Admin de Sistemas: estado, random-forest, kmeans-scatter, greedy).
 * Uso: Importar { api } desde cualquier componente o contexto.
 */

// URL base de la API (mismo origen servido por nginx en producción)
const API_BASE = '/api/v1';

/**
 * Lee el detalle de error devuelto por FastAPI de forma segura (JSON o texto).
 */
async function leerErrorSeguro(response, mensajePorDefecto) {
    try {
        const data = await response.json();
        if (data && data.detail) {
            return typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
        }
        return mensajePorDefecto;
    } catch (e) {
        return mensajePorDefecto;
    }
}

export const api = {
    // ==========================================
    // AUTH (COM-19 / COM-20)
    // ==========================================
    login: async (documento, clave) => {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ documento, clave })
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Credenciales inválidas'));
        return response.json();
    },
    cambiarClave: async (data) => {
        const response = await fetch(`${API_BASE}/auth/cambiar-clave`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cambiar la clave'));
        return response.json();
    },
    // COM-20: opciones de comedor/municipio según membresías del usuario
    getOpcionesSeleccion: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/auth/opciones-seleccion?usuario_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cargar opciones de selección'));
        return response.json();
    },
    confirmarSeleccion: async (data) => {
        const response = await fetch(`${API_BASE}/auth/confirmar-seleccion`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al confirmar la selección'));
        return response.json();
    },

    // ==========================================
    // COMEDORES (COM-21)
    // ==========================================
    getComedores: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/comedores${qs ? `?${qs}` : ''}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comedores'));
        return response.json();
    },
    getComedoresDeUsuario: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/comedores/por-usuario/${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comedores del usuario'));
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
    getUsuariosComedor: async (comedorId) => {
        const response = await fetch(`${API_BASE}/comedores/${comedorId}/usuarios`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener usuarios del comedor'));
        return response.json();
    },
    buscarUsuarioPorDocumento: async (q) => {
        const response = await fetch(`${API_BASE}/comedores/usuarios/buscar?q=${encodeURIComponent(q)}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al buscar usuario'));
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
    buscarComedores: async (q) => {
        const response = await fetch(`${API_BASE}/comedores/buscar?q=${encodeURIComponent(q || '')}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al buscar comedores'));
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
    createGrupo: async (data) => {
        const response = await fetch(`${API_BASE}/grupos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear el grupo'));
        return response.json();
    },
    getPrivilegios: async () => {
        const response = await fetch(`${API_BASE}/grupos/privilegios`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener privilegios'));
        return response.json();
    },
    getPrivilegiosGrupo: async (grupoId) => {
        const response = await fetch(`${API_BASE}/grupos/${grupoId}/privilegios`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener privilegios del grupo'));
        return response.json();
    },
    updatePrivilegiosGrupo: async (grupoId, data) => {
        const response = await fetch(`${API_BASE}/grupos/${grupoId}/privilegios`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar privilegios'));
        return response.json();
    },
    getRolesTemporales: async (comedorId) => {
        const qs = comedorId ? `?comedor_id=${comedorId}` : '';
        const response = await fetch(`${API_BASE}/grupos/roles-temporales${qs}`);
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
    // USUARIOS (COM-23 / COM-26)
    // ==========================================
    getContextoCreacion: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/usuarios/contexto-creacion?usuario_solicitante_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cargar el contexto de creación'));
        return response.json();
    },
    crearUsuario: async (data) => {
        const response = await fetch(`${API_BASE}/usuarios`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear el usuario'));
        return response.json();
    },
    editarUsuario: async (id, data) => {
        const response = await fetch(`${API_BASE}/usuarios/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al editar el usuario'));
        return response.json();
    },
    listarUsuarios: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/usuarios${qs ? `?${qs}` : ''}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al listar usuarios'));
        return response.json();
    },
    getDetalleFlujoUsuario: async (id) => {
        const response = await fetch(`${API_BASE}/usuarios/${id}/detalle-flujo`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el detalle del usuario'));
        return response.json();
    },
    cambiarEstadoCuenta: async (id, data) => {
        const response = await fetch(`${API_BASE}/usuarios/${id}/estado-cuenta`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al cambiar el estado de la cuenta'));
        return response.json();
    },
    desbloquearReintentos: async (id, data) => {
        const response = await fetch(`${API_BASE}/usuarios/${id}/desbloqueo-reintentos`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al desbloquear reintentos'));
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
    getGruposDeUsuario: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/usuarios/${usuarioId}/grupos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener grupos del usuario'));
        return response.json();
    },

    // ==========================================
    // MUNICIPALIDADES (COM-23)
    // ==========================================
    getMunicipalidades: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/municipalidades${qs ? `?${qs}` : ''}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener municipalidades'));
        return response.json();
    },
    buscarMunicipalidades: async (q) => {
        const response = await fetch(`${API_BASE}/municipalidades/buscar?q=${encodeURIComponent(q || '')}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al buscar municipalidades'));
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
    getComedoresDeMunicipalidad: async (id) => {
        const response = await fetch(`${API_BASE}/municipalidades/${id}/comedores`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comedores de la municipalidad'));
        return response.json();
    },

    // ==========================================
    // VISTAS / MÓDULOS POR ROL (COM-25)
    // ==========================================
    getMisModulos: async (usuarioId) => {
        const response = await fetch(`${API_BASE}/vistas/mis-modulos?usuario_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener sus módulos'));
        return response.json();
    },
    getModulosSistema: async () => {
        const response = await fetch(`${API_BASE}/vistas/modulos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener módulos del sistema'));
        return response.json();
    },
    getRolesModulos: async () => {
        const response = await fetch(`${API_BASE}/vistas/roles-modulos`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener roles-modulos'));
        return response.json();
    },
    updateRolesModulos: async (data) => {
        const response = await fetch(`${API_BASE}/vistas/roles-modulos`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar roles-modulos'));
        return response.json();
    },

    // ==========================================
    // UBICACIÓN GEOGRÁFICA EN CASCADA (COM-27)
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
    entrenarKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/kmeans/entrenar?usuario_solicitante_id=${usuarioSolicitanteId}`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al entrenar el modelo'));
        return response.json();
    },
    getResumenKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/kmeans/resumen?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (response.status === 404) return null;   // sin modelo entrenado todavía
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el resumen del modelo'));
        return response.json();
    },
    getClustersKmeans: async (usuarioSolicitanteId, clusterCodigo) => {
        const qs = clusterCodigo ? `?usuario_solicitante_id=${usuarioSolicitanteId}&cluster_codigo=${clusterCodigo}`
                                 : `?usuario_solicitante_id=${usuarioSolicitanteId}`;
        const response = await fetch(`${API_BASE}/kmeans/clusters${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener recetas del cluster'));
        return response.json();
    },
    getCandidatasKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/kmeans/candidatas?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener recetas candidatas'));
        return response.json();
    },
    getDiagnosticoKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/kmeans/diagnostico?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el diagnóstico'));
        return response.json();
    },
    // COM-5 v4: configuración de proteínas permitidas / ingredientes vetados
    getProteinasKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/kmeans/proteinas?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la configuración de proteínas'));
        return response.json();
    },
    updateProteinasKmeans: async (data) => {
        const response = await fetch(`${API_BASE}/kmeans/proteinas`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al guardar la configuración de proteínas'));
        return response.json();
    },

    // ==========================================
    // PANEL DE GRÁFICOS DE MACHINE LEARNING (COM-5 v4 / COM-8 v7)
    // Exclusivo del Administrador de Sistemas (módulo 'modelos_ml')
    // ==========================================
    getEstadoModelosML: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/modelos-ml/estado?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al consultar el estado de los modelos'));
        return response.json();
    },
    // Dispersión REAL vs PREDICHO de demanda (Random Forest) + métricas + importancias
    getScatterRandomForest: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/modelos-ml/random-forest?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al generar el gráfico de Random Forest'));
        return response.json();
    },
    // Dispersión PCA-2D de recetas por cluster + centroides + cargas de variables
    getScatterKmeans: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/modelos-ml/kmeans-scatter?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al generar el gráfico de K-means'));
        return response.json();
    },
    // Serie diaria y totales por variante de la última sesión del Greedy Search
    getGreedyML: async (usuarioSolicitanteId) => {
        const response = await fetch(`${API_BASE}/modelos-ml/greedy?usuario_solicitante_id=${usuarioSolicitanteId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al generar el gráfico del Greedy Search'));
        return response.json();
    },

    // ==========================================
    // PROPUESTAS DE MENÚ SEMANAL (COM-8)
    // ==========================================
    generarPropuestas: async (data) => {
        const response = await fetch(`${API_BASE}/propuestas/generar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al generar las propuestas'));
        return response.json();
    },
    getSesionPropuestas: async (sesionId, usuarioId) => {
        const response = await fetch(`${API_BASE}/propuestas/sesion/${sesionId}?usuario_solicitante_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la sesión de propuestas'));
        return response.json();
    },
    seleccionarPropuesta: async (candidataId, data) => {
        const response = await fetch(`${API_BASE}/propuestas/${candidataId}/seleccionar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al seleccionar la propuesta'));
        return response.json();
    },
    getHistorialPropuestas: async (comedorId, usuarioId) => {
        const response = await fetch(`${API_BASE}/propuestas/historial?comedor_id=${comedorId}&usuario_solicitante_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el historial de propuestas'));
        return response.json();
    },
    getHistorialDias: async (presupuestoId, usuarioId) => {
        const response = await fetch(`${API_BASE}/propuestas/historial/${presupuestoId}/dias?usuario_solicitante_id=${usuarioId}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el detalle del menú'));
        return response.json();
    },

    // ==========================================
    // PARÁMETROS DINÁMICOS (COM-17)
    // ==========================================
    getParametros: async () => {
        const response = await fetch(`${API_BASE}/parametros`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener parámetros'));
        return response.json();
    },
    updateParametro: async (clave, data) => {
        const response = await fetch(`${API_BASE}/parametros/${clave}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar el parámetro'));
        return response.json();
    },

    // ==========================================
    // PRESUPUESTO Y PLANIFICACIÓN (Sprint 2 + compatibilidad COM-8)
    // ==========================================
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
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al calcular el presupuesto'));
        return response.json();
    },
    planificarSemana: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/planificar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al planificar la semana'));
        return response.json();
    },
    guardarPlanificacion: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/guardar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al guardar la planificación'));
        return response.json();
    },
    getPlanificaciones: async () => {
        const response = await fetch(`${API_BASE}/planificaciones`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener planificaciones'));
        return response.json();
    },
    getPlanificacionDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el detalle'));
        return response.json();
    },
    getListaCompras: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}/lista-compras`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la lista de compras'));
        return response.json();
    },
    eliminarPlanificacion: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}`, { method: 'DELETE' });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al eliminar la planificación'));
        return response.json();
    },

    // ==========================================
    // RECETAS (Sprint 1-2)
    // ==========================================
    getRecetas: async () => {
        const response = await fetch(`${API_BASE}/recetas`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener recetas'));
        return response.json();
    },
    getRecetaDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener la receta'));
        return response.json();
    },
    createReceta: async (data) => {
        const response = await fetch(`${API_BASE}/recetas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear la receta'));
        return response.json();
    },
    updateReceta: async (id, data) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar la receta'));
        return response.json();
    },
    getCostoReceta: async (id, fecha) => {
        const qs = fecha ? `?fecha=${fecha}` : '';
        const response = await fetch(`${API_BASE}/recetas/${id}/costo${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al calcular el costo'));
        return response.json();
    },

    // ==========================================
    // INGREDIENTES / CATÁLOGO (Sprint 1-2 + scraper)
    // ==========================================
    getIngredientes: async (fecha) => {
        const qs = fecha ? `?fecha=${fecha}` : '';
        const response = await fetch(`${API_BASE}/ingredientes${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener ingredientes'));
        return response.json();
    },
    getHistoricoIngrediente: async (id, rango) => {
        const qs = rango ? `?rango=${rango}` : '';
        const response = await fetch(`${API_BASE}/ingredientes/${id}/historico${qs}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el histórico'));
        return response.json();
    },
    getUnidadesMedida: async () => {
        const response = await fetch(`${API_BASE}/unidades-medida`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener unidades'));
        return response.json();
    },
    getIngredientesDisponibles: async () => {
        const response = await fetch(`${API_BASE}/ingredientes-disponibles`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener ingredientes disponibles'));
        return response.json();
    },

    // ==========================================
    // PADRON / POS (Sprint 1-2)
    // ==========================================
    getComensales: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/padron/comensales${qs ? `?${qs}` : ''}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener comensales'));
        return response.json();
    },
    createComensal: async (data) => {
        const response = await fetch(`${API_BASE}/padron/comensales`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al crear el comensal'));
        return response.json();
    },
    updateComensal: async (id, data) => {
        const response = await fetch(`${API_BASE}/padron/comensales/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al actualizar el comensal'));
        return response.json();
    },
    registrarVenta: async (data) => {
        const response = await fetch(`${API_BASE}/padron/ventas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al registrar la venta'));
        return response.json();
    },
    getVentasDia: async (fecha) => {
        const response = await fetch(`${API_BASE}/padron/ventas?fecha=${fecha}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener ventas del día'));
        return response.json();
    },

    // ==========================================
    // REPORTES (Sprint 2-3)
    // ==========================================
    getReporteConsumo: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/reportes/consumo${qs ? `?${qs}` : ''}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el reporte de consumo'));
        return response.json();
    },
    getReporteCostos: async (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/reportes/costos${qs ? `?${qs}` : ''}`);
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al obtener el reporte de costos'));
        return response.json();
    },
};