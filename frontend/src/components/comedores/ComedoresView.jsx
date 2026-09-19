/**
 * components/comedores/ComedoresView.jsx
 * Objetivo: Vista principal del módulo multi-comedor (COM-21): listar comedores a nivel
 *           nacional con filtros, crear/editar comedor (atributos: departamento, ciudad,
 *           distrito, zona, nombre, dirección, link de mapa y fecha de fundación) y
 *           acceder a la gestión de usuarios por comedor.
 * Uso: Renderizado por App.jsx en la pestaña "Comedores". Usa la sesión (useAuth) como
 *      solicitante para los permisos; el backend valida y devuelve 403 si no aplica.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Store, Plus, Users, Edit3, MapPin, ExternalLink, Loader2 } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalExito } from '../common/ModalExito';
import { ModalGestionUsuariosComedor } from './ModalGestionUsuariosComedor';

// Formulario en blanco para creación de comedores
const FORM_INICIAL = {
    nombre: '', departamento: '', ciudad: '', distrito: '',
    zona: '', direccion: '', link_ubicacion: '', fecha_fundacion: ''
};

export const ComedoresView = () => {
    const { usuario } = useAuth();

    // Listado y estados de carga/error
    const [comedores, setComedores] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [filtro, setFiltro] = useState('');

    // Modal de creación/edición
    const [modalAbierto, setModalAbierto] = useState(false);
    const [comedorEdit, setComedorEdit] = useState(null);
    const [form, setForm] = useState(FORM_INICIAL);
    const [guardando, setGuardando] = useState(false);
    const [errorForm, setErrorForm] = useState('');

    // Modal de gestión de usuarios por comedor
    const [comedorUsuarios, setComedorUsuarios] = useState(null);
    const [exito, setExito] = useState('');

    // Solo el Administrador del Sistema ve el botón de creación (regla COM-21)
    const esAdminSistema = usuario?.rol === 'Administrador Sistema';

    const cargarComedores = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            setComedores(await api.getComedores());
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { cargarComedores(); }, [cargarComedores]);

    // Apertura del modal en modo creación
    const abrirNuevo = () => {
        setComedorEdit(null);
        setForm(FORM_INICIAL);
        setErrorForm('');
        setModalAbierto(true);
    };

    // Apertura del modal en modo edición con los datos del comedor
    const abrirEdicion = (c) => {
        setComedorEdit(c);
        setForm({
            nombre: c.nombre || '', departamento: c.departamento || '',
            ciudad: c.ciudad || '', distrito: c.distrito || '',
            zona: c.zona || '', direccion: c.direccion || '',
            link_ubicacion: c.link_ubicacion || '', fecha_fundacion: c.fecha_fundacion || ''
        });
        setErrorForm('');
        setModalAbierto(true);
    };

    // Guardado (creación o edición) enviando al solicitante de la sesión
    const handleSubmit = async (e) => {
        e.preventDefault();
        setErrorForm('');
        if (!form.nombre.trim() || !form.departamento.trim() || !form.ciudad.trim() || !form.distrito.trim()) {
            setErrorForm('Nombre, departamento, ciudad y distrito son obligatorios.');
            return;
        }
        setGuardando(true);
        try {
            const payload = { ...form, usuario_solicitante_id: usuario.id };
            if (comedorEdit) {
                await api.updateComedor(comedorEdit.id, payload);
                setExito('Comedor actualizado exitosamente');
            } else {
                await api.createComedor(payload);
                setExito('Comedor creado exitosamente');
            }
            setModalAbierto(false);
            cargarComedores();
        } catch (err) {
            setErrorForm(err.message);
        } finally {
            setGuardando(false);
        }
    };

    // Filtro local por nombre o distrito
    const filtrados = comedores.filter(c =>
        c.nombre.toLowerCase().includes(filtro.toLowerCase()) ||
        (c.distrito || '').toLowerCase().includes(filtro.toLowerCase())
    );

    return (
        <div>
            {/* Encabezado del módulo */}
            <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Store className="text-emerald-600" size={22} /> Comedores Populares
                    </h2>
                    <p className="text-sm text-slate-500">Gestión nacional de comedores y sus usuarios asociados (COM-21).</p>
                </div>
                {esAdminSistema && (
                    <button onClick={abrirNuevo}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-medium transition-colors">
                        <Plus size={18} /> Nuevo Comedor
                    </button>
                )}
            </div>

            {/* Filtro de búsqueda */}
            <input
                type="text"
                value={filtro}
                onChange={(e) => setFiltro(e.target.value)}
                placeholder="Filtrar por nombre o distrito..."
                className="w-full md:w-80 px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 mb-4"
            />

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{error}</div>
            )}

            {loading ? (
                <div className="flex items-center justify-center py-16 text-slate-400">
                    <Loader2 className="animate-spin mr-2" size={20} /> Cargando comedores...
                </div>
            ) : (
                <div className="overflow-x-auto border border-slate-200 rounded-lg">
                    <table className="w-full text-sm text-left">
                        <thead className="bg-slate-100 text-slate-600 uppercase text-xs">
                            <tr>
                                <th className="px-4 py-3">Comedor</th>
                                <th className="px-4 py-3">Ubicación</th>
                                <th className="px-4 py-3">Dirección</th>
                                <th className="px-4 py-3">Fundación</th>
                                <th className="px-4 py-3 text-right">Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtrados.length === 0 && (
                                <tr><td colSpan="5" className="px-4 py-8 text-center text-slate-400">No se encontraron comedores.</td></tr>
                            )}
                            {filtrados.map(c => (
                                <tr key={c.id} className="border-t border-slate-200 hover:bg-slate-50">
                                    <td className="px-4 py-3">
                                        <p className="font-semibold text-slate-800">{c.nombre}</p>
                                        {c.zona && <p className="text-xs text-slate-500">Zona: {c.zona}</p>}
                                    </td>
                                    <td className="px-4 py-3 text-slate-600">
                                        <span className="flex items-center gap-1"><MapPin size={14} className="text-emerald-600" />
                                            {c.distrito}, {c.ciudad} — {c.departamento}
                                        </span>
                                        {c.link_ubicacion && (
                                            <a href={c.link_ubicacion} target="_blank" rel="noreferrer"
                                                className="text-xs text-blue-600 hover:underline flex items-center gap-1 mt-1">
                                                <ExternalLink size={12} /> Ver mapa
                                            </a>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-slate-600 max-w-[220px] truncate">{c.direccion || '—'}</td>
                                    <td className="px-4 py-3 text-slate-600">{c.fecha_fundacion || '—'}</td>
                                    <td className="px-4 py-3">
                                        <div className="flex justify-end gap-2">
                                            <button onClick={() => setComedorUsuarios(c)}
                                                className="flex items-center gap-1 px-3 py-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg text-xs font-medium transition-colors">
                                                <Users size={14} /> Usuarios
                                            </button>
                                            <button onClick={() => abrirEdicion(c)}
                                                className="flex items-center gap-1 px-3 py-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg text-xs font-medium transition-colors">
                                                <Edit3 size={14} /> Editar
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ===== Modal de creación/edición de comedor ===== */}
            {modalAbierto && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
                        <div className="px-6 py-4 border-b border-slate-200 bg-emerald-700 text-white">
                            <h3 className="font-bold text-lg">{comedorEdit ? 'Editar Comedor' : 'Nuevo Comedor'}</h3>
                        </div>
                        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto space-y-4">
                            {errorForm && (
                                <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{errorForm}</div>
                            )}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="md:col-span-2">
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Nombre del Comedor *</label>
                                    <input type="text" value={form.nombre}
                                        onChange={(e) => setForm({ ...form, nombre: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        placeholder="Ej: Comedor Popular Cruz de Motupe - Grupo 2" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Departamento *</label>
                                    <input type="text" value={form.departamento}
                                        onChange={(e) => setForm({ ...form, departamento: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Ciudad *</label>
                                    <input type="text" value={form.ciudad}
                                        onChange={(e) => setForm({ ...form, ciudad: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Distrito *</label>
                                    <input type="text" value={form.distrito}
                                        onChange={(e) => setForm({ ...form, distrito: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500" />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Zona</label>
                                    <input type="text" value={form.zona}
                                        onChange={(e) => setForm({ ...form, zona: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        placeholder="Ej: A.H. Cruz de Motupe" />
                                </div>
                                <div className="md:col-span-2">
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Dirección</label>
                                    <input type="text" value={form.direccion}
                                        onChange={(e) => setForm({ ...form, direccion: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500" />
                                </div>
                                <div className="md:col-span-2">
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Link de ubicación (mapa)</label>
                                    <input type="url" value={form.link_ubicacion}
                                        onChange={(e) => setForm({ ...form, link_ubicacion: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        placeholder="https://maps.google.com/?q=..." />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-slate-700 mb-1">Fecha de fundación</label>
                                    <input type="date" value={form.fecha_fundacion}
                                        onChange={(e) => setForm({ ...form, fecha_fundacion: e.target.value })}
                                        className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500" />
                                </div>
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                                <button type="button" onClick={() => setModalAbierto(false)}
                                    className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors">
                                    Cancelar
                                </button>
                                <button type="submit" disabled={guardando}
                                    className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50">
                                    {guardando ? 'Guardando...' : (comedorEdit ? 'Actualizar' : 'Crear Comedor')}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ===== Modal de gestión de usuarios del comedor seleccionado ===== */}
            {comedorUsuarios && (
                <ModalGestionUsuariosComedor
                    comedor={comedorUsuarios}
                    onClose={() => setComedorUsuarios(null)}
                />
            )}

            {/* Modal de éxito reutilizable (COM-18) */}
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};