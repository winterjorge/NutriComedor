/**
 * components/usuarios/ModalMunicipalidad.jsx
 * Objetivo: Modal de creación/edición de municipalidades. La ubicación geográfica se
 *           selecciona con la cascada departamento -> provincia -> distrito (COM-27),
 *           reemplazando los antiguos campos de texto libre. El nombre oficial, la
 *           dirección y el link de mapa se mantienen como campos de texto.
 * Uso: Abierto por GestionUsuariosSistemaView (sub-pestaña Municipalidades).
 * Dependencias COM-27: SelectorUbicacionCascada (bloque A) y api.createMunicipalidad /
 *           api.updateMunicipalidad (backend debe aceptar los FK de ubicación).
 * Referencia: tickets COM-23 (municipalidades) y COM-27 (ubicación en cascada).
 */
import React, { useState, useEffect } from 'react';
import { X, Building2, Loader2, AlertCircle, MapPin } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
// COM-27: selector de ubicación en cascada (reemplaza los campos de texto libre)
import { SelectorUbicacionCascada } from '../common/SelectorUbicacionCascada';

const FORM_INICIAL = {
    nombre: '',
    direccion: '',
    link_ubicacion: '',
};

// COM-27: estado inicial de la ubicación geográfica en cascada
const UBICACION_INICIAL = {
    departamento_id: null,
    provincia_id: null,
    distrito_id: null,
    municipalidad_id: null,
};

export const ModalMunicipalidad = ({ municipalidad, onClose, onExito }) => {
    const { usuario } = useAuth();
    const esEdicion = !!municipalidad;

    const [form, setForm] = useState(FORM_INICIAL);
    const [ubicacion, setUbicacion] = useState(UBICACION_INICIAL);
    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Precarga en modo edición
    useEffect(() => {
        if (municipalidad) {
            setForm({
                nombre: municipalidad.nombre || '',
                direccion: municipalidad.direccion || '',
                link_ubicacion: municipalidad.link_ubicacion || '',
            });
            // COM-27: precarga la ubicación desde los FK guardados
            setUbicacion({
                departamento_id: municipalidad.departamento_id || null,
                provincia_id: municipalidad.provincia_id || null,
                distrito_id: municipalidad.distrito_id || null,
                municipalidad_id: null,
            });
        }
    }, [municipalidad]);

    const validar = () => {
        if (!form.nombre.trim()) return 'El nombre de la municipalidad es obligatorio.';
        // COM-27: la ubicación debe estar completa hasta distrito
        if (!ubicacion.departamento_id || !ubicacion.provincia_id || !ubicacion.distrito_id) {
            return 'Complete la ubicación geográfica (departamento, provincia y distrito).';
        }
        return '';
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        const errValidacion = validar();
        if (errValidacion) {
            setError(errValidacion);
            return;
        }
        setGuardando(true);
        try {
            const payload = {
                nombre: form.nombre.trim(),
                direccion: form.direccion.trim() || null,
                link_ubicacion: form.link_ubicacion.trim() || null,
                usuario_solicitante_id: usuario.id,
                // COM-27: FK de ubicación geográfica (fuente de verdad)
                departamento_id: ubicacion.departamento_id,
                provincia_id: ubicacion.provincia_id,
                distrito_id: ubicacion.distrito_id,
            };
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
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden">
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

                    {/* COM-27: ubicación en cascada (reemplaza departamento/provincia/distrito de texto libre) */}
                    <div>
                        <label className="flex items-center gap-1 text-xs font-semibold text-slate-600 mb-1">
                            <MapPin size={12} className="text-emerald-600" /> Ubicación geográfica *
                        </label>
                        <SelectorUbicacionCascada
                            valores={ubicacion}
                            onCambiar={setUbicacion}
                            mostrarMunicipalidad={false}
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Nombre oficial *</label>
                        <input
                            type="text"
                            value={form.nombre}
                            onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="Ej: MUNICIPALIDAD DISTRITAL DE SAN JUAN DE LURIGANCHO"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Dirección</label>
                        <input
                            type="text"
                            value={form.direccion}
                            onChange={(e) => setForm({ ...form, direccion: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>

                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Link de ubicación (mapa)</label>
                        <input
                            type="url"
                            value={form.link_ubicacion}
                            onChange={(e) => setForm({ ...form, link_ubicacion: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            placeholder="https://maps.google.com/?q=..."
                        />
                    </div>

                    {/* Acciones */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                            Cancelar
                        </button>
                        <button type="submit" disabled={guardando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                            {guardando && <Loader2 className="animate-spin" size={15} />}
                            {esEdicion ? 'Guardar cambios' : 'Crear municipalidad'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};