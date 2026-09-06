/**
 * services/api.js
 * Objetivo: Servicio centralizado de comunicación HTTP con la API del backend.
 *           Todos los componentes consumen este módulo en lugar de hacer fetch directo,
 *           lo que garantiza un manejo uniforme de errores, cabeceras y endpoints.
 * Uso: Importar `api` en hooks y componentes para consumir los endpoints del sistema.
 *
 * Historial de cambios:
 *  - Versión base: endpoints de recetas, catálogo, padron, presupuesto y planificaciones.
 *  - COM-17: parser defensivo `leerErrorSeguro` para evitar el fallo
 *    "Unexpected token 'I', 'Internal S'... is not valid JSON" cuando el backend
 *    devuelve respuestas 500 en texto plano.
 *  - COM-19: nuevos endpoints de autenticación (login, cambiar-clave) con retorno
 *    uniforme {ok, data} para facilitar el manejo en LoginView y ModalCambioClave.
 */
const API_BASE = '/api/v1';

/**
 * COM-17: Parser defensivo de errores. Si el cuerpo de la respuesta no es JSON válido
 * (por ejemplo, un "Internal Server Error" en texto plano), devuelve un mensaje legible
 * en lugar de romper el JSON.parse del frontend.
 * @param {Response} response - Respuesta fetch no exitosa.
 * @param {string} mensajePorDefecto - Mensaje genérico si no se puede parsear.
 * @returns {Promise<string>} Mensaje de error listo para mostrar al usuario.
 */
const leerErrorSeguro = async (response, mensajePorDefecto) => {
    try {
        const data = await response.json();
        // El backend puede devolver {detail: "..."} o {detail: {mensaje, tipo}}
        if (typeof data.detail === 'object' && data.detail !== null) {
            return data.detail.mensaje || mensajePorDefecto;
        }
        return data.detail || data.message || mensajePorDefecto;
    } catch (e) {
        // El servidor respondió con texto plano o cuerpo vacío
        return `${mensajePorDefecto} (HTTP ${response.status})`;
    }
};

export const api = {
    // ==========================================
    // AUTENTICACIÓN (COM-19)
    // ==========================================
    /**
     * Inicia sesión con tipo+documento y contraseña.
     * Retorna {ok: boolean, data: ...} para facilitar el manejo en LoginView.
     * En caso de error, data.detail contiene {mensaje, tipo} (error/aviso).
     */
    login: async (data) => {
        try {
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const payload = await response.json();
            return { ok: response.ok, data: response.ok ? payload : { detail: payload.detail } };
        } catch (err) {
            return { ok: false, data: { detail: 'Error de conexión con el servidor.' } };
        }
    },

    /**
     * Cambia la contraseña validando la política COM-19 (8-12 caracteres,
     * letras+números, sin contener el DNI). Reinicia la vigencia de 6 meses.
     */
    cambiarClave: async (data) => {
        try {
            const response = await fetch(`${API_BASE}/auth/cambiar-clave`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const payload = await response.json();
            return { ok: response.ok, data: response.ok ? payload : { detail: payload.detail } };
        } catch (err) {
            return { ok: false, data: { detail: 'Error de conexión con el servidor.' } };
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
        const response = await fetch(`${API_BASE}/recetas/${id}`, {
            method: 'DELETE'
        });
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
        const response = await fetch(`${API_BASE}/recetas/${recetaId}/ingredientes/${ingredienteId}`, {
            method: 'DELETE'
        });
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
    eliminarVenta: async (id) => fetch(`${API_BASE}/padron/${id}`, {
        method: 'DELETE'
    }),

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
        const response = await fetch(`${API_BASE}/planificaciones/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(await leerErrorSeguro(response, 'Error al eliminar planificación'));
        return response.json();
    }
};