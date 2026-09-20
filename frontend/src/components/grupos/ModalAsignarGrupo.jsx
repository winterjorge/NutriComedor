/**
 * components/grupos/ModalAsignarGrupo.jsx
 * Objetivo: COM-22: flujo de asignación de un usuario a un grupo: búsqueda por documento,
 *           selección de grupo y rol (dependiente del grupo) y definición del alcance
 *           (comedor) según el ámbito: COMEDOR lo exige, GLOBAL es opcional, SISTEMA ninguno.
 * Uso: Abierto por GruposView. Al asignar con éxito invoca onExito para refrescar membresías.
 */
import React, { useState } from 'react';
import { X, UserSearch, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const ModalAsignarGrupo = ({ grupos, comedores, onClose, onExito }) => {
    const { usuario } = useAuth();

    // Búsqueda del usuario por documento
    const [documento, setDocumento] = useState('');
    const [candidato, setCandidato] = useState(null);
    const [buscando, setBuscando] = useState(false);

    // Selección de grupo, rol y alcance
    const [grupoId, setGrupoId] = useState('');
    const [rolId, setRolId] = useState('');
    const [comedorId, setComedorId] = useState('');

    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Grupo seleccionado y sus roles (catálogo COM-22)
    const grupoSel = grupos.find(g => String(g.id) === String(grupoId)) || null;
    const rolesDelGrupo = grupoSel ? grupoSel.roles : [];

    // Reglas de alcance según ámbito del grupo (COM-22)
    const requiereComedor = grupoSel?.ambito === 'COMEDOR';
    const comedorOpcional = grupoSel?.ambito === 'GLOBAL';

    const buscarUsuario = async () => {
        setError('');
        setCandidato(null);
        if (!documento.trim()) {
            setError('Ingrese un documento para buscar.');
            return;
        }
        setBuscando(true);
        try {
            setCandidato(await api.buscarUsuarioPorDocumento(documento.trim()));
        } catch (e) {
            setError(e.message);
        } finally {
            setBuscando(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        if (!candidato) { setError('Busque y seleccione un usuario.'); return; }
        if (!grupoId || !rolId) { setError('Seleccione grupo y rol.'); return; }
        if (requiereComedor && !comedorId) { setError('El grupo elegido exige indicar un comedor.'); return; }
        setGuardando(true);
        try {
            await api.asignarGrupo({
                usuario_id: candidato.id,
                grupo_id: parseInt(grupoId),
                rol_id: parseInt(rolId),
                comedor_id: comedorId ? parseInt(comedorId) : null,
                usuario_solicitante_id: usuario.id
            });
            onExito();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden">
                {/* Encabezado */}
                <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                    <h3 className="font-bold text-lg">Asignar Usuario a Grupo</h3>
                    <button onClick={onClose} className="text-emerald-100 hover:text-white transition-colors" aria-label="Cerrar">
                        <X size={22} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto">
                    {error && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                            <AlertCircle size={16} /> {error}
                        </div>
                    )}

                    {/* Búsqueda de usuario por documento */}
                    <div>
                        <label className="block text-sm font-semibold text-slate-700 mb-1">Usuario (por documento)</label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={documento}
                                onChange={(e) => setDocumento(e.target.value.replace(/[^0-9A-Za-z]/g, ''))}
                                placeholder="DNI o C.E."
                                className="flex-1 px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                            />
                            <button
                                type="button"
                                onClick={buscarUsuario}
                                disabled={buscando}
                                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                            >
                                {buscando ? <Loader2 className="animate-spin" size={16} /> : <UserSearch size={16} />}
                                Buscar
                            </button>
                        </div>
                        {candidato && (
                            <div className="mt-2 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm">
                                <p className="font-semibold text-slate-800">
                                    {candidato.nombres} {candidato.apellido_paterno} {candidato.apellido_materno}
                                </p>
                                <p className="text-xs text-slate-500">
                                    {candidato.tipo_documento} {candidato.documento_identidad}
                                </p>
                            </div>
                        )}
                    </div>

                    {/* Grupo y rol (rol dependiente del grupo) */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-1">Grupo *</label>
                            <select
                                value={grupoId}
                                onChange={(e) => { setGrupoId(e.target.value); setRolId(''); }}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                            >
                                <option value="">Seleccionar...</option>
                                {grupos.map(g => (
                                    <option key={g.id} value={g.id}>{g.nombre} ({g.ambito})</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-1">Rol *</label>
                            <select
                                value={rolId}
                                onChange={(e) => setRolId(e.target.value)}
                                disabled={!grupoSel}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm disabled:opacity-50"
                            >
                                <option value="">Seleccionar...</option>
                                {rolesDelGrupo.map(r => (
                                    <option key={r.id} value={r.id}>{r.nombre}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* Alcance: comedor según ámbito del grupo */}
                    {(requiereComedor || comedorOpcional) && (
                        <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-1">
                                Comedor {requiereComedor ? '*' : '(opcional: alcance específico)'}
                            </label>
                            <select
                                value={comedorId}
                                onChange={(e) => setComedorId(e.target.value)}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                            >
                                <option value="">
                                    {comedorOpcional ? 'Global (todos los comedores)' : 'Seleccionar...'}
                                </option>
                                {comedores.map(c => (
                                    <option key={c.id} value={c.id}>{c.nombre} — {c.distrito}</option>
                                ))}
                            </select>
                            {comedorOpcional && (
                                <p className="text-xs text-slate-500 mt-1">
                                    Si deja "Global", la membresía aplicará a todos los comedores.
                                </p>
                            )}
                        </div>
                    )}

                    {/* Acciones */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
                        >
                            Cancelar
                        </button>
                        <button
                            type="submit"
                            disabled={guardando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50"
                        >
                            {guardando ? 'Asignando...' : 'Asignar Membresía'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};