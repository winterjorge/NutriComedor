/**
 * hooks/useGrupos.js
 * Objetivo: Hook del módulo de grupos de usuario (COM-22): expone el catálogo de
 *           grupos/roles, las membresías con filtros (grupo, comedor, estado) y las
 *           acciones de asignación y activación/desactivación auditadas.
 * Uso: Consumido por components/grupos/GruposView.jsx. Usa la sesión (useAuth)
 *      como solicitante para que el backend valide permisos por ámbito.
 */
import { useState, useEffect, useCallback } from 'react';
import { api } from '../services/api';
import { useAuth } from '../context/AuthContext';

export const useGrupos = () => {
    const { usuario } = useAuth();

    // Catálogos para selects y filtros
    const [grupos, setGrupos] = useState([]);       // grupos con sus roles (seed COM-22)
    const [comedores, setComedores] = useState([]); // alcances por comedor

    // Membresías según filtros activos
    const [membresias, setMembresias] = useState([]);

    // Estados de UI
    const [cargando, setCargando] = useState(true);
    const [procesando, setProcesando] = useState(false);
    const [error, setError] = useState('');

    // Filtros de la vista
    const [filtroGrupo, setFiltroGrupo] = useState('');
    const [filtroComedor, setFiltroComedor] = useState('');
    const [filtroEstado, setFiltroEstado] = useState(''); // 'activas' | 'inactivas' | ''

    // Carga del catálogo de grupos y roles
    const cargarGrupos = useCallback(async () => {
        try {
            setGrupos(await api.getGrupos());
        } catch (e) {
            console.error('Error cargando grupos:', e);
        }
    }, []);

    // Carga de comedores para filtros y alcance
    const cargarComedores = useCallback(async () => {
        try {
            setComedores(await api.getComedores());
        } catch (e) {
            console.error('Error cargando comedores:', e);
        }
    }, []);

    // Carga de membresías aplicando los filtros activos
    const cargarMembresias = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const params = {};
            if (filtroGrupo) params.grupo_id = filtroGrupo;
            if (filtroComedor) params.comedor_id = filtroComedor;
            if (filtroEstado) params.estado = filtroEstado;
            setMembresias(await api.getMembresias(params));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [filtroGrupo, filtroComedor, filtroEstado]);

    useEffect(() => { cargarGrupos(); }, [cargarGrupos]);
    useEffect(() => { cargarComedores(); }, [cargarComedores]);
    useEffect(() => { cargarMembresias(); }, [cargarMembresias]);

    /**
     * Asigna un usuario a un grupo con rol y alcance (comedor_id opcional).
     * El backend valida: rol pertenece al grupo, alcance según ámbito y permisos.
     */
    const asignarGrupo = async ({ usuario_id, grupo_id, rol_id, comedor_id }) => {
        setProcesando(true);
        setError('');
        try {
            const res = await api.asignarGrupo({
                usuario_id,
                grupo_id,
                rol_id,
                comedor_id: comedor_id || null,
                usuario_solicitante_id: usuario.id
            });
            await cargarMembresias();
            return res;
        } catch (e) {
            setError(e.message);
            throw e;
        } finally {
            setProcesando(false);
        }
    };

    /**
     * Activa/desactiva una membresía. El backend deja auditoría
     * (desactivado_por y fecha_desactivacion) y aplica candados de negocio.
     */
    const cambiarEstado = async (membresiaId, estadoActivo) => {
        setProcesando(true);
        setError('');
        try {
            const res = await api.cambiarEstadoMembresia(membresiaId, {
                estado_activo: estadoActivo,
                usuario_solicitante_id: usuario.id
            });
            await cargarMembresias();
            return res;
        } catch (e) {
            setError(e.message);
            throw e;
        } finally {
            setProcesando(false);
        }
    };

    return {
        grupos,
        comedores,
        membresias,
        cargando,
        procesando,
        error,
        filtroGrupo, setFiltroGrupo,
        filtroComedor, setFiltroComedor,
        filtroEstado, setFiltroEstado,
        asignarGrupo,
        cambiarEstado,
        recargar: cargarMembresias
    };
};