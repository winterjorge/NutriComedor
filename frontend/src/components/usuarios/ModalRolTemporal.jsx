/**
 * components/usuarios/ModalRolTemporal.jsx
 * Objetivo: COM-23: otorgar un rol de comedor por tiempo definido a un usuario con
 *           membresía activa (ej. el tesorero asume al presidente durante un viaje)
 *           y revocar otorgamientos temporales vigentes del mismo usuario.
 * Uso: Abierto por GestionUsuariosComedorView pasando el usuario objetivo y el comedor.
 */
import React, { useState, useEffect } from 'react';
import { X, History, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const ModalRolTemporal = ({ usuarioObjetivo, comedorId, onClose, onExito }) => {
    const { usuario } = useAuth();

    // Roles de grupos de ámbito COMEDOR (Directivo/Operativo) para el select
    const [rolesComedor, setRolesComedor] = useState([]);
    const [rolSel, setRolSel] = useState('');
    const [fechaInicio, setFechaInicio] = useState('');
    const [fechaFin, setFechaFin] = useState('');
    const [motivo, setMotivo] = useState('');

    // Otorgamientos temporales VIGENTES del usuario en este comedor
    const [vigentes, setVigentes] = useState([]);
    const [error, setError] = useState('');
    const [avisoInterno, setAvisoInterno] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Carga roles disponibles y roles temporales vigentes del usuario
    useEffect(() => {
        const cargar = async () => {
            const [grupos, temps] = await Promise.all([
                api.getGrupos(),
                api.getRolesTemporales({ comedor_id: comedorId, estado: 'VIGENTE' })
            ]);
            const opciones = [];
            grupos.filter(g => g.ambito === 'COMEDOR').forEach(g => {
                (g.roles || []).forEach(r => {
                    opciones.push({ rol_id: r.id, etiqueta: `${g.nombre} — ${r.nombre}` });
                });
            });
            setRolesComedor(opciones);
            setVigentes(temps.filter(t => t.usuario_id === usuarioObjetivo.id));
        };
        cargar().catch(e => setError(e.message));
    }, [comedorId, usuarioObjetivo.id]);

    const recargarVigentes = async () => {
        const temps = await api.getRolesTemporales({ comedor_id: comedorId, estado: 'VIGENTE' });
        setVigentes(temps.filter(t => t.usuario_id === usuarioObjetivo.id));
    };

    // Otorgar rol temporal con vigencia
    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        if (!rolSel || !fechaInicio || !fechaFin) {
            setError('Seleccione rol y rango de fechas.');
            return;
        }
        setGuardando(true);
        try {
            await api.otorgarRolTemporal({
                usuario_id: usuarioObjetivo.id,
                comedor_id: comedorId,
                rol_id: Number(rolSel),
                motivo: motivo || null,
                fecha_inicio: fechaInicio,
                fecha_fin: fechaFin,
                usuario_solicitante_id: usuario.id
            });
            onExito();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    };

    // Revocar anticipadamente un rol temporal vigente
    const revocar = async (rolTemporalId) => {
        setError('');
        try {
            await api.revocarRolTemporal(rolTemporalId, { usuario_solicitante_id: usuario.id });
            setAvisoInterno('Rol temporal revocado exitosamente.');
            recargarVigentes();
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
                        <History size={20} /> Rol Temporal
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
                    {avisoInterno && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 flex items-center gap-2 text-sm">
                            <CheckCircle size={16} /> {avisoInterno}
                        </div>
                    )}

                    {/* Otorgamientos vigentes con revocación */}
                    <div>
                        <h4 className="text-xs font-bold text-slate-600 uppercase mb-2">Otorgamientos vigentes</h4>
                        {vigentes.length === 0 ? (
                            <p className="text-xs text-slate-400">Sin roles temporales vigentes.</p>
                        ) : (
                            <div className="space-y-2">
                                {vigentes.map(t => (
                                    <div key={t.id} className="flex items-center justify-between gap-2 p-2 bg-blue-50 border border-blue-200 rounded-lg">
                                        <div className="text-xs text-slate-700">
                                            <b>{t.grupo} — {t.rol}</b>
                                            <span className="block text-slate-500">
                                                {String(t.fecha_inicio).slice(0, 10)} → {String(t.fecha_fin).slice(0, 10)}
                                                {t.motivo ? ` · ${t.motivo}` : ''}
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => revocar(t.id)}
                                            className="px-2 py-1 bg-red-50 text-red-600 hover:bg-red-100 rounded text-xs font-medium transition-colors"
                                        >
                                            Revocar
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Formulario de otorgamiento */}
                    <form onSubmit={handleSubmit} className="space-y-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Rol a otorgar *</label>
                            <select
                                value={rolSel}
                                onChange={(e) => setRolSel(e.target.value)}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            >
                                <option value="">Seleccionar rol...</option>
                                {rolesComedor.map(op => (
                                    <option key={op.rol_id} value={op.rol_id}>{op.etiqueta}</option>
                                ))}
                            </select>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Desde *</label>
                                <input type="date" value={fechaInicio}
                                    onChange={(e) => setFechaInicio(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Hasta *</label>
                                <input type="date" value={fechaFin}
                                    onChange={(e) => setFechaFin(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Motivo</label>
                            <input type="text" value={motivo}
                                onChange={(e) => setMotivo(e.target.value)}
                                placeholder="Ej: viaje del presidente"
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div className="flex justify-end gap-3 pt-2">
                            <button type="button" onClick={onClose}
                                className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                                Cerrar
                            </button>
                            <button type="submit" disabled={guardando}
                                className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                                {guardando && <Loader2 className="animate-spin" size={15} />} Otorgar rol temporal
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    );
};