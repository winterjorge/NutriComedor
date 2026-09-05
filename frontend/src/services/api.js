/**
 * services/api.js
 * Objetivo: Servicio centralizado de comunicación HTTP con la API del backend.
 * Uso: Importar `api` en hooks y componentes para consumir los endpoints del sistema.
 * FIX: Se agrega `leerErrorSeguro` para parsear errores del servidor de forma segura.
 *      Antes, una respuesta 500 en texto plano ("Internal Server Error") rompía el
 *      JSON.parse del frontend con "Unexpected token 'I'".
 */
const API_BASE = '/api/v1';

// Parser defensivo de errores: si el cuerpo no es JSON, devuelve un mensaje legible
const leerErrorSeguro = async (response, mensajePorDefecto) => {
    try {
        const data = await response.json();
        return data.detail || mensajePorDefecto;
    } catch (e) {
        // El servidor respondió con texto plano o cuerpo vacío
        return `${mensajePorDefecto} (HTTP ${response.status})`;
    }
};

export const api = {
    // ==========================================
    // PARÁMETROS DINÁMICOS
    // ==========================================
    getParametros: async () => {
        const response = await fetch(`${API_BASE}/parametros`);
        if (!response.ok) throw new Error('Error al obtener parámetros');
        return response.json();
    },

    // ==========================================
    // RECETAS
    // ==========================================
    getRecetas: async (params = {}) => {
        const queryString = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE}/recetas?${queryString}`);
        if (!response.ok) throw new Error('Error al obtener recetas');
        return response.json();
    },
    getRecetaDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`);
        if (!response.ok) throw new Error('Error al obtener detalle');
        return response.json();
    },
    createReceta: async (data) => {
        const response = await fetch(`${API_BASE}/recetas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(await leerErrorSeguro(response, 'Error al crear receta'));
        }
        return response.json();
    },
    updateReceta: async (id, data) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(await leerErrorSeguro(response, 'Error al actualizar receta'));
        }
        return response.json();
    },
    deleteReceta: async (id) => {
        const response = await fetch(`${API_BASE}/recetas/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Error al eliminar receta');
        return response.json();
    },
    getUnidadesMedida: async () => {
        const response = await fetch(`${API_BASE}/unidades-medida`);
        if (!response.ok) throw new Error('Error al obtener unidades');
        return response.json();
    },
    getIngredientesDisponibles: async () => {
        const response = await fetch(`${API_BASE}/ingredientes-disponibles`);
        if (!response.ok) throw new Error('Error al obtener ingredientes');
        return response.json();
    },
    addIngredienteReceta: async (recetaId, data) => {
        const response = await fetch(`${API_BASE}/recetas/${recetaId}/ingredientes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error('Error al agregar ingrediente');
        return response.json();
    },
    deleteIngredienteReceta: async (recetaId, ingredienteId) => {
        const response = await fetch(`${API_BASE}/recetas/${recetaId}/ingredientes/${ingredienteId}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Error al eliminar ingrediente');
        return response.json();
    },

    // ==========================================
    // COSTOS Y CATÁLOGO
    // ==========================================
    getCostoReceta: async (id, fecha) => (await fetch(`${API_BASE}/recetas/${id}/costo?fecha=${fecha}`)).json(),
    getIngredientes: async (fecha) => (await fetch(`${API_BASE}/ingredientes?fecha=${fecha}`)).json(),
    getHistoricoPrecios: async (id, rango) => (await fetch(`${API_BASE}/ingredientes/${id}/historico?rango=${rango}`)).json(),

    // ==========================================
    // PADRÓN Y ESTADÍSTICAS
    // ==========================================
    getPadronStats: async () => (await fetch(`${API_BASE}/padron/stats`)).json(),
    getVentasHoy: async () => (await fetch(`${API_BASE}/padron/hoy`)).json(),
    getPrediccionDemanda: async (fecha) => (await fetch(`${API_BASE}/padron/prediccion_demanda?fecha_str=${fecha}`)).json(),

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
        if (!response.ok) {
            throw new Error(await leerErrorSeguro(response, 'Error al planificar semana'));
        }
        return response.json();
    },
    guardarPlanificacion: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/guardar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(await leerErrorSeguro(response, 'Error al guardar planificación'));
        }
        return response.json();
    },
    getTiposPlatos: async () => {
        const response = await fetch(`${API_BASE}/presupuesto/tipos-platos`);
        if (!response.ok) throw new Error('Error al obtener tipos de platos');
        return response.json();
    },
    calcularPresupuesto: async (data) => {
        const response = await fetch(`${API_BASE}/presupuesto/calcular`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!response.ok) throw new Error('Error al calcular presupuesto');
        return response.json();
    },

    // ==========================================
    // PLANIFICACIONES GUARDADAS
    // ==========================================
    getPlanificaciones: async () => {
        const response = await fetch(`${API_BASE}/planificaciones`);
        if (!response.ok) throw new Error('Error al obtener planificaciones');
        return response.json();
    },
    getPlanificacionDetalle: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}`);
        if (!response.ok) throw new Error('Error al obtener detalle de planificación');
        return response.json();
    },
    getListaCompras: async (planificacionId, dia = null) => {
        const url = dia
            ? `${API_BASE}/planificaciones/${planificacionId}/lista-compras?dia=${dia}`
            : `${API_BASE}/planificaciones/${planificacionId}/lista-compras`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('Error al generar lista de compras');
        return response.json();
    },
    eliminarPlanificacion: async (id) => {
        const response = await fetch(`${API_BASE}/planificaciones/${id}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error('Error al eliminar planificación');
        return response.json();
    }
};