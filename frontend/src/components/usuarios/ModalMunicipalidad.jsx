/**
 * components/usuarios/ModalMunicipalidad.jsx
 * Objetivo: COM-23: modal de creación/edición de municipalidades del registro nacional
 *           (departamento, provincia, distrito, nombre, dirección y link de mapa).
 * Uso: Abierto por GestionUsuariosSistemaView con `municipalidad` null (crear) o un
 *      objeto (editar); al guardar con éxito invoca onExito.
 */
import React, { useState, useEffect } from 'react';
import { X, Building2, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const FORM_INICIAL = {
    departamento: '',
    provincia: '',
    distrito: '',
    nombre: '',
    direccion: '',
    link_ubicacion: ''
};

export const ModalMunicipalidad = ({ municipalidad, onClose, onExito }) => {
    const { usuario } = useAuth();
    const esEdicion = !!municipalidad;
    const [form, setForm] = useState(FORM_INICIAL);
    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Precarga en modo edición
    useEffect(() => {
        if (municipalidad) {
            setForm({
                departamento: municipalidad.departamento || '',
                provincia: municipalidad.provincia || '',
                distrito: municipalidad.distrito || '',
                nombre: municipalidad.nombre || '',
                direccion: municipalidad.direccion || '',
                link_ubicacion: municipalidad.link_ubicacion || ''
            });
        }
    }, [municipalidad]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        if (!form.departamento.trim() || !form.provincia.trim() || !form.distrito.trim() || !form.nombre.trim()) {
            setError('Departamento, provincia, distrito y nombre son obligatorios.');
            return;
        }
        setGuardando(true);
        try {
            const payload = { ...form, usuario_solicitante_id: usuario.id };
            if (esEdicion) {
                await api.updateMunicipalidad(municipalidad.id, payload);
            } else {
                await api.createMunicipalidad(payload);
            }
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
                    <h3 className="font-bold text-lg flex items-center gap-2">
                        <Building2 size={20} /> {esEdicion ? 'Editar Municipalidad' : 'Nueva Municipalidad'}
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

                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Departamento *</label>
                            <input type="text" value={form.departamento}
                                onChange={(e) => setForm({ ...form, departamento: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Provincia *</label>
                            <input type="text" value={form.provincia}
                                onChange={(e) => setForm({ ...form, provincia: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Distrito *</label>
                            <input type="text" value={form.distrito}
                                onChange={(e) => setForm({ ...form, distrito: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Nombre *</label>
                        <input type="text" value={form.nombre}
                            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="Ej: Municipalidad Distrital de San Juan de Lurigancho" />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Dirección</label>
                        <input type="text" value={form.direccion}
                            onChange={(e) => setForm({ ...form, direccion: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Link de ubicación (mapa)</label>
                        <input type="url" value={form.link_ubicacion}
                            onChange={(e) => setForm({ ...form, link_ubicacion: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="https://maps.google.com/?q=..." />
                    </div>

                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                            Cancelar
                        </button>
                        <button type="submit" disabled={guardando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                            {guardando && <Loader2 className="animate-spin" size={15} />} {esEdicion ? 'Guardar cambios' : 'Crear municipalidad'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};