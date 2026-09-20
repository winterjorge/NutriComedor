/**
 * components/usuarios/ModalGrupoPrivilegios.jsx
 * Objetivo: COM-23: modal de asignación de privilegios a un grupo: checklist con el
 *           catálogo completo de privilegios del sistema; al guardar se REEMPLAZA el
 *           conjunto de privilegios del grupo por los seleccionados.
 * Uso: Abierto por GestionUsuariosSistemaView pasando el `grupo` y el catálogo de
 *      `privilegios` (con la lista de grupos que poseen cada privilegio).
 */
import React, { useState, useEffect } from 'react';
import { X, ShieldCheck, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const ModalGrupoPrivilegios = ({ grupo, privilegios, onClose, onExito }) => {
    const { usuario } = useAuth();
    const [seleccionados, setSeleccionados] = useState([]);
    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Precarga: privilegios que el grupo ya posee (según catálogo recibido)
    useEffect(() => {
        if (grupo && privilegios) {
            setSeleccionados(
                privilegios.filter(p => (p.grupos || []).includes(grupo.nombre)).map(p => p.id)
            );
        }
    }, [grupo, privilegios]);

    const toggle = (privilegioId) => {
        setSeleccionados(prev =>
            prev.includes(privilegioId)
                ? prev.filter(id => id !== privilegioId)
                : [...prev, privilegioId]
        );
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setGuardando(true);
        try {
            await api.asignarPrivilegiosGrupo(grupo.id, {
                privilegio_ids: seleccionados,
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
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[90vh] flex flex-col overflow-hidden">
                {/* Encabezado */}
                <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                    <h3 className="font-bold text-lg flex items-center gap-2">
                        <ShieldCheck size={20} /> Privilegios: {grupo?.nombre}
                    </h3>
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

                    <p className="text-xs text-slate-500">
                        Marque los privilegios que tendrá el grupo. Al guardar, se reemplazará
                        el conjunto actual por el seleccionado.
                    </p>

                    <div className="space-y-2">
                        {privilegios.map(p => (
                            <label
                                key={p.id}
                                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                                    seleccionados.includes(p.id)
                                        ? 'bg-emerald-50 border-emerald-300'
                                        : 'bg-white border-slate-200 hover:bg-slate-50'
                                }`}
                            >
                                <input
                                    type="checkbox"
                                    checked={seleccionados.includes(p.id)}
                                    onChange={() => toggle(p.id)}
                                    className="mt-1 accent-emerald-600"
                                />
                                <span>
                                    <span className="block text-sm font-semibold text-slate-800">{p.nombre}</span>
                                    <span className="block text-xs text-slate-500">{p.descripcion}</span>
                                </span>
                            </label>
                        ))}
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                            Cancelar
                        </button>
                        <button type="submit" disabled={guardando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                            {guardando && <Loader2 className="animate-spin" size={15} />} Guardar privilegios
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};