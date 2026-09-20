/**
 * components/usuarios/ModalCrearUsuario.jsx
 * Objetivo: COM-23: modal de creación de usuarios del sistema: datos personales,
 *           documento y clave inicial que debe cumplir la política vigente. Muestra
 *           como ayuda la política actual (longitudes) leída del backend.
 * Uso: Abierto por GestionUsuariosSistemaView; al crear con éxito invoca onExito.
 */
import React, { useState, useEffect } from 'react';
import { X, UserPlus, Loader2, AlertCircle, KeyRound } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// Formulario en blanco para un usuario nuevo
const FORM_INICIAL = {
    tipo_documento: 'DNI',
    documento_identidad: '',
    nombres: '',
    apellido_paterno: '',
    apellido_materno: '',
    fecha_nacimiento: '',
    clave_inicial: '',
    confirmar_clave: ''
};

export const ModalCrearUsuario = ({ onClose, onExito }) => {
    const { usuario } = useAuth();
    const [form, setForm] = useState(FORM_INICIAL);
    const [politica, setPolitica] = useState(null);
    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Carga la política vigente para mostrarla como ayuda al definir la clave
    useEffect(() => {
        api.getPoliticaClave().then(setPolitica).catch(() => setPolitica(null));
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        if (!form.documento_identidad.trim() || !form.nombres.trim()) {
            setError('El documento y los nombres son obligatorios.');
            return;
        }
        if (!form.clave_inicial || form.clave_inicial !== form.confirmar_clave) {
            setError('Las contraseñas no coinciden o están vacías.');
            return;
        }
        setGuardando(true);
        try {
            await api.crearUsuario({
                tipo_documento: form.tipo_documento,
                documento_identidad: form.documento_identidad.trim(),
                nombres: form.nombres.trim(),
                apellido_paterno: form.apellido_paterno.trim() || null,
                apellido_materno: form.apellido_materno.trim() || null,
                fecha_nacimiento: form.fecha_nacimiento || null,
                clave_inicial: form.clave_inicial,
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
                    <h3 className="font-bold text-lg flex items-center gap-2"><UserPlus size={20} /> Nuevo Usuario</h3>
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

                    {/* Ayuda de política de claves vigente */}
                    {politica && (
                        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 flex items-center gap-2 text-xs">
                            <KeyRound size={14} className="shrink-0" />
                            Política vigente: {politica.longitud_min}–{politica.longitud_max} caracteres, letras y números,
                            sin contener el documento. El usuario deberá cambiarla en su primer ingreso.
                        </div>
                    )}

                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Tipo doc.</label>
                            <select
                                value={form.tipo_documento}
                                onChange={(e) => setForm({ ...form, tipo_documento: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            >
                                <option value="DNI">DNI</option>
                                <option value="CE">C.E.</option>
                            </select>
                        </div>
                        <div className="col-span-2">
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Documento *</label>
                            <input
                                type="text"
                                value={form.documento_identidad}
                                onChange={(e) => setForm({ ...form, documento_identidad: e.target.value.replace(/[^0-9A-Za-z]/g, '').slice(0, 15) })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                placeholder="Ej: 70000001"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Nombres *</label>
                        <input
                            type="text"
                            value={form.nombres}
                            onChange={(e) => setForm({ ...form, nombres: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Apellido paterno</label>
                            <input
                                type="text"
                                value={form.apellido_paterno}
                                onChange={(e) => setForm({ ...form, apellido_paterno: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Apellido materno</label>
                            <input
                                type="text"
                                value={form.apellido_materno}
                                onChange={(e) => setForm({ ...form, apellido_materno: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Fecha de nacimiento</label>
                        <input
                            type="date"
                            value={form.fecha_nacimiento}
                            onChange={(e) => setForm({ ...form, fecha_nacimiento: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Clave inicial *</label>
                            <input
                                type="password"
                                value={form.clave_inicial}
                                onChange={(e) => setForm({ ...form, clave_inicial: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Confirmar clave *</label>
                            <input
                                type="password"
                                value={form.confirmar_clave}
                                onChange={(e) => setForm({ ...form, confirmar_clave: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            />
                        </div>
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                            Cancelar
                        </button>
                        <button type="submit" disabled={guardando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                            {guardando && <Loader2 className="animate-spin" size={15} />} Crear usuario
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};