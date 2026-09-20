/**
 * components/grupos/GruposView.jsx
 * Objetivo: Vista principal del módulo de grupos de usuario (COM-22): listar membresías
 *           con filtros (grupo, comedor y estado), activar/desactivar membresías con
 *           confirmación y auditoría, y abrir el flujo de asignación de usuarios a
 *           grupos con rol y alcance (global o por comedor).
 * Uso: Renderizado por App.jsx en la pestaña "Grupos". Consume el hook useGrupos.
 */
import React, { useState } from 'react';
import { Users, UserPlus, ShieldCheck, ShieldOff, Loader2, AlertCircle } from 'lucide-react';
import { useGrupos } from '../../hooks/useGrupos';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';
import { ModalAsignarGrupo } from './ModalAsignarGrupo';

export const GruposView = () => {
    const {
        grupos, comedores, membresias, cargando, procesando, error,
        filtroGrupo, setFiltroGrupo,
        filtroComedor, setFiltroComedor,
        filtroEstado, setFiltroEstado,
        cambiarEstado, recargar
    } = useGrupos();

    // Estados de UI: modal de asignación, confirmación de cambio de estado y éxito
    const [modalAsignar, setModalAsignar] = useState(false);
    const [confEstado, setConfEstado] = useState(null);
    const [exito, setExito] = useState('');

    // Ejecuta el cambio de estado confirmado (dejando auditoría en el backend)
    const confirmarCambioEstado = async () => {
        const m = confEstado;
        setConfEstado(null);
        try {
            await cambiarEstado(m.id, !m.estado_activo);
            setExito(m.estado_activo
                ? 'Membresía desactivada correctamente'
                : 'Membresía activada correctamente');
        } catch (e) {
            // El mensaje de error ya queda visible vía hook (error)
        }
    };

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado del módulo */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-6">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Users className="text-emerald-600" size={22} /> Grupos de Usuario
                    </h2>
                    <p className="text-sm text-slate-500">
                        Membresías por grupo, rol y alcance (sistema, municipalidad o comedor).
                    </p>
                </div>
                <button
                    onClick={() => setModalAsignar(true)}
                    className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
                >
                    <UserPlus size={18} /> Asignar Usuario
                </button>
            </div>

            {/* Barra de filtros */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4 bg-slate-50 p-4 rounded-xl border border-slate-100">
                <select
                    value={filtroGrupo}
                    onChange={(e) => setFiltroGrupo(e.target.value)}
                    className="px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                >
                    <option value="">Todos los grupos</option>
                    {grupos.map(g => (
                        <option key={g.id} value={g.id}>{g.nombre} ({g.ambito})</option>
                    ))}
                </select>
                <select
                    value={filtroComedor}
                    onChange={(e) => setFiltroComedor(e.target.value)}
                    className="px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                >
                    <option value="">Todos los comedores / global</option>
                    {comedores.map(c => (
                        <option key={c.id} value={c.id}>{c.nombre}</option>
                    ))}
                </select>
                <select
                    value={filtroEstado}
                    onChange={(e) => setFiltroEstado(e.target.value)}
                    className="px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                >
                    <option value="">Todos los estados</option>
                    <option value="activas">Activas</option>
                    <option value="inactivas">Inactivas</option>
                </select>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={18} /> {error}
                </div>
            )}

            {/* Tabla de membresías */}
            <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
                <table className="w-full text-left border-collapse whitespace-nowrap">
                    <thead>
                        <tr className="bg-slate-100 text-slate-600 text-sm">
                            <th className="p-4 font-semibold">Usuario</th>
                            <th className="p-4 font-semibold">Grupo</th>
                            <th className="p-4 font-semibold">Rol</th>
                            <th className="p-4 font-semibold">Alcance</th>
                            <th className="p-4 font-semibold text-center">Estado</th>
                            <th className="p-4 font-semibold text-center">Acción</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {cargando ? (
                            <tr>
                                <td colSpan="6" className="p-8 text-center text-emerald-600">
                                    <Loader2 className="animate-spin mx-auto" size={28} />
                                </td>
                            </tr>
                        ) : membresias.length === 0 ? (
                            <tr>
                                <td colSpan="6" className="p-8 text-center text-slate-500">
                                    No se encontraron membresías con los filtros aplicados.
                                </td>
                            </tr>
                        ) : (
                            membresias.map(m => (
                                <tr key={m.id} className="hover:bg-slate-50">
                                    <td className="p-4">
                                        <p className="font-medium text-slate-800">
                                            {m.nombres} {m.apellido_paterno}
                                        </p>
                                        <p className="text-xs text-slate-500">{m.documento_identidad}</p>
                                    </td>
                                    <td className="p-4">
                                        <span className="text-sm font-medium text-slate-700">{m.grupo}</span>
                                        <span className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                            m.ambito === 'SISTEMA' ? 'bg-purple-100 text-purple-700'
                                            : m.ambito === 'GLOBAL' ? 'bg-blue-100 text-blue-700'
                                            : 'bg-emerald-100 text-emerald-700'
                                        }`}>
                                            {m.ambito}
                                        </span>
                                    </td>
                                    <td className="p-4 text-sm text-slate-700">{m.rol}</td>
                                    <td className="p-4 text-sm text-slate-600">{m.comedor || 'Global'}</td>
                                    <td className="p-4 text-center">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${
                                            m.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'
                                        }`}>
                                            {m.estado_activo ? 'Activo' : 'Inactivo'}
                                        </span>
                                    </td>
                                    <td className="p-4 text-center">
                                        <button
                                            onClick={() => setConfEstado(m)}
                                            disabled={procesando}
                                            className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 ${
                                                m.estado_activo
                                                    ? 'bg-red-50 text-red-600 hover:bg-red-100'
                                                    : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                                            }`}
                                        >
                                            {m.estado_activo ? <ShieldOff size={14} /> : <ShieldCheck size={14} />}
                                            {m.estado_activo ? 'Desactivar' : 'Activar'}
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Modal de asignación de usuario a grupo (COM-22) */}
            {modalAsignar && (
                <ModalAsignarGrupo
                    grupos={grupos}
                    comedores={comedores}
                    onClose={() => setModalAsignar(false)}
                    onExito={() => { setModalAsignar(false); setExito('Membresía asignada correctamente'); recargar(); }}
                />
            )}

            {/* Confirmación de activación/desactivación con auditoría */}
            <ModalConfirmacion
                isOpen={!!confEstado}
                onClose={() => setConfEstado(null)}
                onConfirm={confirmarCambioEstado}
                mensaje={confEstado
                    ? `¿${confEstado.estado_activo ? 'Desactivar' : 'Activar'} la membresía de ${confEstado.nombres} (${confEstado.documento_identidad}) en el grupo ${confEstado.grupo} - rol ${confEstado.rol}${confEstado.comedor ? ` del comedor ${confEstado.comedor}` : ' (alcance global)'}?`
                    : ''}
                tipo={confEstado?.estado_activo ? 'danger' : 'warning'}
            />

            {/* Aviso de éxito reutilizable (COM-18) */}
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};