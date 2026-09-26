/**
 * components/usuarios/ModalBuscarPersona.jsx
 * Objetivo: COM-39: modal de búsqueda de persona por documento para asignar/reemplazar
 *           un cargo directivo. Si la persona NO existe en la BD, muestra un formulario
 *           de registro inmediato (datos mínimos) que se entrega al padre como
 *           `nuevo_usuario` para que el backend la cree dentro de la misma transacción
 *           del lote (clave provisoria Nutri2026, flujo COM-19).
 * Contrato con el padre (onSeleccionar):
 *   - Persona existente: { tipo: 'existente', usuario_id, documento, nombres, apellidos }
 *   - Persona nueva:     { tipo: 'nuevo', nuevo_usuario: { tipo_documento,
 *                         documento_identidad, nombres, apellido_paterno,
 *                         apellido_materno, fecha_nacimiento } }
 * Uso: Montado por GestionDirectivosComedorView (COM-39). El modal NO crea usuarios:
 *      solo busca o recolecta datos; la creación es atómica en el backend.
 * Referencia: ticket COM-39 (solo trazabilidad).
 */
import React, { useState, useEffect } from 'react';
import { X, UserSearch, UserPlus, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import { api } from '../../services/api';

export const ModalBuscarPersona = ({ isOpen, onClose, onSeleccionar, titulo }) => {
    // ----- Estado de búsqueda -----
    const [documento, setDocumento] = useState('');
    const [buscando, setBuscando] = useState(false);
    const [encontrado, setEncontrado] = useState(null);   // usuario existente
    const [noEncontrado, setNoEncontrado] = useState(false);
    const [error, setError] = useState('');

    // ----- Estado del registro inmediato -----
    const [formNuevo, setFormNuevo] = useState({
        tipo_documento: 'DNI',
        documento_identidad: '',
        nombres: '',
        apellido_paterno: '',
        apellido_materno: '',
        fecha_nacimiento: '',
    });

    // Reinicio total al abrir/cerrar
    useEffect(() => {
        if (isOpen) {
            setDocumento('');
            setBuscando(false);
            setEncontrado(null);
            setNoEncontrado(false);
            setError('');
            setFormNuevo({
                tipo_documento: 'DNI',
                documento_identidad: '',
                nombres: '',
                apellido_paterno: '',
                apellido_materno: '',
                fecha_nacimiento: '',
            });
        }
    }, [isOpen]);

    if (!isOpen) return null;

    // ---------- Búsqueda por documento ----------
    const buscar = async () => {
        const doc = documento.trim();
        if (!doc) {
            setError('Ingrese el número de documento a buscar.');
            return;
        }
        setBuscando(true);
        setError('');
        setEncontrado(null);
        setNoEncontrado(false);
        try {
            const u = await api.buscarUsuarioPorDocumento(doc);
            setEncontrado(u);
            // Precarga el formulario por si se decide registrar a otra persona después
            setFormNuevo(prev => ({ ...prev, documento_identidad: doc }));
        } catch (e) {
            // 404 u otro: se ofrece el registro inmediato
            setNoEncontrado(true);
            setFormNuevo(prev => ({ ...prev, documento_identidad: doc }));
        } finally {
            setBuscando(false);
        }
    };

    // ---------- Selección de persona existente ----------
    const seleccionarExistente = () => {
        onSeleccionar({
            tipo: 'existente',
            usuario_id: encontrado.id,
            documento: encontrado.documento_identidad,
            nombres: `${encontrado.nombres} ${encontrado.apellido_paterno || ''} ${encontrado.apellido_materno || ''}`.trim(),
        });
        onClose();
    };

    // ---------- Registro inmediato (no se crea aquí: el backend lo hace en el lote) ----------
    const seleccionarNueva = () => {
        if (!formNuevo.nombres.trim() || !formNuevo.apellido_paterno.trim() || !formNuevo.fecha_nacimiento) {
            setError('Complete nombres, apellido paterno y fecha de nacimiento para registrar a la persona.');
            return;
        }
        onSeleccionar({
            tipo: 'nuevo',
            nuevo_usuario: {
                tipo_documento: formNuevo.tipo_documento,
                documento_identidad: formNuevo.documento_identidad.trim(),
                nombres: formNuevo.nombres.trim(),
                apellido_paterno: formNuevo.apellido_paterno.trim(),
                apellido_materno: (formNuevo.apellido_materno || '').trim(),
                fecha_nacimiento: formNuevo.fecha_nacimiento,
            },
        });
        onClose();
    };

    const inputCls = "w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500";

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden animate-in zoom-in duration-200">
                {/* Encabezado */}
                <div className="bg-emerald-700 text-white p-4 flex items-center gap-2">
                    <UserSearch size={20} />
                    <p className="font-bold text-sm flex-1">{titulo || 'Buscar persona para el cargo'}</p>
                    <button onClick={onClose} className="p-1 hover:bg-emerald-800 rounded transition-colors">
                        <X size={18} />
                    </button>
                </div>

                <div className="p-4 space-y-4">
                    {/* Buscador por documento */}
                    <div>
                        <label className="text-xs font-semibold text-slate-600 mb-1 block">
                            Número de documento
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={documento}
                                onChange={(e) => setDocumento(e.target.value)}
                                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); buscar(); } }}
                                placeholder="Ej. 43604221"
                                className={inputCls}
                            />
                            <button
                                onClick={buscar}
                                disabled={buscando}
                                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
                            >
                                {buscando ? <Loader2 className="animate-spin" size={15} /> : <UserSearch size={15} />}
                                Buscar
                            </button>
                        </div>
                    </div>

                    {error && (
                        <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-xs">
                            <AlertCircle size={14} /> {error}
                        </div>
                    )}

                    {/* Persona encontrada */}
                    {encontrado && (
                        <div className="bg-emerald-50 border border-emerald-300 rounded-xl p-3 flex items-center gap-3">
                            <CheckCircle2 size={22} className="text-emerald-600 shrink-0" />
                            <div className="flex-1">
                                <p className="text-sm font-bold text-slate-800">
                                    {encontrado.nombres} {encontrado.apellido_paterno} {encontrado.apellido_materno || ''}
                                </p>
                                <p className="text-xs text-slate-500">
                                    {encontrado.tipo_documento} {encontrado.documento_identidad}
                                    {encontrado.rol ? ` · Rol actual: ${encontrado.rol}` : ''}
                                </p>
                            </div>
                            <button
                                onClick={seleccionarExistente}
                                className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-colors"
                            >
                                Seleccionar
                            </button>
                        </div>
                    )}

                    {/* No encontrada: registro inmediato */}
                    {noEncontrado && (
                        <div className="bg-amber-50 border border-amber-300 rounded-xl p-3 space-y-3">
                            <p className="flex items-center gap-2 text-xs font-bold text-amber-800">
                                <UserPlus size={14} />
                                La persona no existe en la BD. Regístrela ahora (se creará al guardar los cambios).
                            </p>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className="text-[11px] font-semibold text-slate-600 block mb-0.5">Tipo doc.</label>
                                    <select
                                        value={formNuevo.tipo_documento}
                                        onChange={(e) => setFormNuevo({ ...formNuevo, tipo_documento: e.target.value })}
                                        className={inputCls}
                                    >
                                        <option value="DNI">DNI</option>
                                        <option value="CE">CE</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="text-[11px] font-semibold text-slate-600 block mb-0.5">Documento</label>
                                    <input
                                        type="text"
                                        value={formNuevo.documento_identidad}
                                        onChange={(e) => setFormNuevo({ ...formNuevo, documento_identidad: e.target.value })}
                                        className={inputCls}
                                    />
                                </div>
                                <div>
                                    <label className="text-[11px] font-semibold text-slate-600 block mb-0.5">Nombres</label>
                                    <input
                                        type="text"
                                        value={formNuevo.nombres}
                                        onChange={(e) => setFormNuevo({ ...formNuevo, nombres: e.target.value })}
                                        className={inputCls}
                                    />
                                </div>
                                <div>
                                    <label className="text-[11px] font-semibold text-slate-600 block mb-0.5">Apellido paterno</label>
                                    <input
                                        type="text"
                                        value={formNuevo.apellido_paterno}
                                        onChange={(e) => setFormNuevo({ ...formNuevo, apellido_paterno: e.target.value })}
                                        className={inputCls}
                                    />
                                </div>
                                <div>
                                    <label className="text-[11px] font-semibold text-slate-600 block mb-0.5">Apellido materno</label>
                                    <input
                                        type="text"
                                        value={formNuevo.apellido_materno}
                                        onChange={(e) => setFormNuevo({ ...formNuevo, apellido_materno: e.target.value })}
                                        className={inputCls}
                                    />
                                </div>
                                <div>
                                    <label className="text-[11px] font-semibold text-slate-600 block mb-0.5">Fecha nacimiento</label>
                                    <input
                                        type="date"
                                        value={formNuevo.fecha_nacimiento}
                                        onChange={(e) => setFormNuevo({ ...formNuevo, fecha_nacimiento: e.target.value })}
                                        className={inputCls}
                                    />
                                </div>
                            </div>
                            <button
                                onClick={seleccionarNueva}
                                className="w-full px-3 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-xs font-bold transition-colors flex items-center justify-center gap-2"
                            >
                                <UserPlus size={14} /> Registrar y seleccionar para el cargo
                            </button>
                            <p className="text-[10px] text-amber-700">
                                La cuenta se creará con clave provisoria Nutri2026 y cambio obligatorio en el primer ingreso.
                            </p>
                        </div>
                    )}

                    {/* Cierre */}
                    <button
                        onClick={onClose}
                        className="w-full px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors"
                    >
                        Cancelar
                    </button>
                </div>
            </div>
        </div>
    );
};