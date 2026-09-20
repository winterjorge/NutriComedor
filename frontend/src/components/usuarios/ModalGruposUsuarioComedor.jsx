/**
 * components/usuarios/ModalGruposUsuarioComedor.jsx
 * Objetivo: COM-23: modificar las membresías de grupos/roles de un usuario dentro de un
 *           comedor: listar sus membresías en ese comedor (con estado), activarlas o
 *           desactivarlas y asignarle nuevas membresías de grupos de ámbito COMEDOR o
 *           GLOBAL con el rol elegido (alcance fijado al comedor en gestión).
 * Uso: Abierto por GestionUsuariosComedorView pasando el usuario objetivo y el comedor.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { X, ShieldCheck, Loader2, AlertCircle, CheckCircle, UserPlus } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const ModalGruposUsuarioComedor = ({ usuarioObjetivo, comedorId, onClose, onExito }) => {
    const { usuario } = useAuth();

    // Membresías del usuario en este comedor y catálogo de grupos COMEDOR/GLOBAL
    const [membresias, setMembresias] = useState([]);
    const [grupos, setGrupos] = useState([]);
    const [grupoSel, setGrupoSel] = useState('');
    const [rolSel, setRolSel] = useState('');

    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [aviso, setAviso] = useState('');
    const [asignando, setAsignando] = useState(false);

    // Carga membresías del usuario (filtradas al comedor) y catálogo de grupos
    const cargar = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const [delUsuario, catalogo] = await Promise.all([
                api.getGruposDeUsuario(usuarioObjetivo.id),
                api.getGrupos()
            ]);
            setMembresias(delUsuario.filter(m => m.comedor_id === comedorId));
            setGrupos(catalogo.filter(g => g.ambito === 'COMEDOR' || g.ambito === 'GLOBAL'));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [usuarioObjetivo.id, comedorId]);

    useEffect(() => { cargar(); }, [cargar]);

    // Grupo seleccionado para derivar sus roles
    const grupoSelObj = grupos.find(g => String(g.id) === String(grupoSel)) || null;

    // Asignar nueva membresía (grupo + rol) con alcance al comedor en gestión
    const asignar = async (e) => {
        e.preventDefault();
        setError('');
        setAviso('');
        if (!grupoSel || !rolSel) {
            setError('Seleccione grupo y rol.');
            return;
        }
        setAsignando(true);
        try {
            await api.asignarGrupo({
                usuario_id: usuarioObjetivo.id,
                grupo_id: Number(grupoSel),
                rol_id: Number(rolSel),
                comedor_id: comedorId,
                usuario_solicitante_id: usuario.id
            });
            setAviso('Membresía asignada exitosamente.');
            setGrupoSel('');
            setRolSel('');
            cargar();
        } catch (err) {
            setError(err.message);
        } finally {
            setAsignando(false);
        }
    };

    // Activar/desactivar una membresía existente (con auditoría en el backend)
    const cambiarEstado = async (membresia) => {
        setError('');
        setAviso('');
        try {
            await api.cambiarEstadoMembresia(membresia.id, {
                estado_activo: !membresia.estado_activo,
                usuario_solicitante_id: usuario.id
            });
            setAviso(membresia.estado_activo ? 'Membresía desactivada.' : 'Membresía activada.');
            cargar();
        } catch (err) {
            setError(err.message);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden">
                {/* Encabezado */}
                <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                    <h3 className="font-bold text-lg flex items-center gap-2">
                        <ShieldCheck size={20} /> Grupos y Roles del Usuario
                    </h3>
                    <button onClick={onClose} className="text-emerald-100 hover:text-white transition-colors" aria-label="Cerrar">
                        <X size={22} />
                    </button>
                </div>

                <div className="p-6 space-y-4 overflow-y-auto">
                    <p className="text-sm text-slate-600">
                        Usuario: <b>{usuarioObjetivo.nombres} {usuarioObjetivo.apellido_paterno}</b> ({usuarioObjetivo.documento_identidad})
                    </p>

                    {error && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                            <AlertCircle size={16} /> {error}
                        </div>
                    )}
                    {aviso && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 flex items-center gap-2 text-sm">
                            <CheckCircle size={16} /> {aviso}
                        </div>
                    )}

                    {/* Membresías actuales en el comedor */}
                    <div>
                        <h4 className="text-xs font-bold text-slate-600 uppercase mb-2">Membresías en este comedor</h4>
                        {cargando ? (
                            <div className="p-4 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={20} /></div>
                        ) : membresias.length === 0 ? (
                            <p className="text-xs text-slate-400">El usuario no tiene membresías en este comedor.</p>
                        ) : (
                            <div className="space-y-2">
                                {membresias.map(m => (
                                    <div key={m.id} className="flex items-center justify-between gap-2 p-2 bg-slate-50 border border-slate-200 rounded-lg">
                                        <div className="text-xs text-slate-700">
                                            <b>{m.grupo} — {m.rol}</b>
                                            <span className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold ${m.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                                                {m.estado_activo ? 'Activa' : 'Inactiva'}
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => cambiarEstado(m)}
                                            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${m.estado_activo ? 'bg-red-50 text-red-600 hover:bg-red-100' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
                                        >
                                            {m.estado_activo ? 'Desactivar' : 'Activar'}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Formulario de nueva membresía */}
                    <form onSubmit={asignar} className="space-y-3 border-t border-slate-200 pt-4">
                        <h4 className="text-xs font-bold text-slate-600 uppercase flex items-center gap-1">
                            <UserPlus size={14} /> Asignar nueva membresía
                        </h4>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Grupo</label>
                            <select
                                value={grupoSel}
                                onChange={(e) => { setGrupoSel(e.target.value); setRolSel(''); }}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            >
                                <option value="">Seleccionar grupo...</option>
                                {grupos.map(g => (
                                    <option key={g.id} value={g.id}>{g.nombre} ({g.ambito})</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Rol</label>
                            <select
                                value={rolSel}
                                onChange={(e) => setRolSel(e.target.value)}
                                disabled={!grupoSelObj}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50"
                            >
                                <option value="">Seleccionar rol...</option>
                                {(grupoSelObj?.roles || []).map(r => (
                                    <option key={r.id} value={r.id}>{r.nombre}</option>
                                ))}
                            </select>
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <button type="button" onClick={onClose}
                                className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                                Cerrar
                            </button>
                            <button type="submit" disabled={asignando}
                                className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                                {asignando && <Loader2 className="animate-spin" size={15} />} Asignar
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};