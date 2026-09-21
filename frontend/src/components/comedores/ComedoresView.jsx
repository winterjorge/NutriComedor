/**
 * components/comedores/ComedoresView.jsx
 * Objetivo: Vista de gestión de comedores (COM-21) actualizada para que la ubicación
 *           geográfica se seleccione mediante la cascada departamento -> provincia ->
 *           distrito (COM-27), eliminando la captura de texto libre para esos campos.
 *           Conserva el listado, filtros, creación, edición, asociación de usuarios y
 *           cambio de estado de membresía.
 * Uso: Montado por App.jsx para usuarios con permiso de gestión de comedores.
 * Dependencias COM-27: SelectorUbicacionCascada (bloque A) y api.getDepartamentos/
 *           getProvincias/getDistritos (bloque UBICACIONES de api.js).
 * Referencia: tickets COM-21 (multi-comedor) y COM-27 (ubicación en cascada).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Store, Plus, Edit3, Search, Loader2, AlertCircle, MapPin,
    UserPlus, UserCheck, UserX, X
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';
// COM-27: selector de ubicación en cascada (reemplaza los campos de texto libre)
import { SelectorUbicacionCascada } from '../common/SelectorUbicacionCascada';

// COM-27: estado inicial de la ubicación geográfica en cascada
const UBICACION_INICIAL = {
    departamento_id: null,
    provincia_id: null,
    distrito_id: null,
    municipalidad_id: null,
};

const FORM_COMEDOR_INICIAL = {
    nombre: '',
    zona: '',
    direccion: '',
    link_ubicacion: '',
    fecha_fundacion: '',
};

export const ComedoresView = () => {
    const { usuario } = useAuth();

    // Listado y filtros
    const [comedores, setComedores] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [filtroNombre, setFiltroNombre] = useState('');
    const [filtroDepartamento, setFiltroDepartamento] = useState('');
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');

    // Modal de creación/edición de comedor
    const [modalComedorAbierto, setModalComedorAbierto] = useState(false);
    const [comedorEnEdicion, setComedorEnEdicion] = useState(null);
    const [formComedor, setFormComedor] = useState(FORM_COMEDOR_INICIAL);
    const [ubicacion, setUbicacion] = useState(UBICACION_INICIAL);
    const [guardando, setGuardando] = useState(false);

    // Modal de asociación de usuarios
    const [modalAsociarAbierto, setModalAsociarAbierto] = useState(false);
    const [comedorAsociar, setComedorAsociar] = useState(null);
    const [usuariosComedor, setUsuariosComedor] = useState([]);
    const [documentoBuscar, setDocumentoBuscar] = useState('');
    const [usuarioEncontrado, setUsuarioEncontrado] = useState(null);
    const [rolAsignar, setRolAsignar] = useState('Operador');
    const [buscandoUsuario, setBuscandoUsuario] = useState(false);

    // Confirmaciones
    const [confDesactivar, setConfDesactivar] = useState(null);

    // ---------- Carga de comedores ----------
    const cargarComedores = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const params = {};
            if (filtroNombre) params.nombre = filtroNombre;
            if (filtroDepartamento) params.departamento = filtroDepartamento;
            setComedores(await api.getComedores(params));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [filtroNombre, filtroDepartamento]);

    useEffect(() => { cargarComedores(); }, [cargarComedores]);

    // ---------- Apertura del modal de creación/edición ----------
    const abrirModalCrear = () => {
        setComedorEnEdicion(null);
        setFormComedor(FORM_COMEDOR_INICIAL);
        setUbicacion(UBICACION_INICIAL);
        setModalComedorAbierto(true);
    };

    const abrirModalEditar = (comedor) => {
        setComedorEnEdicion(comedor);
        setFormComedor({
            nombre: comedor.nombre || '',
            zona: comedor.zona || '',
            direccion: comedor.direccion || '',
            link_ubicacion: comedor.link_ubicacion || '',
            fecha_fundacion: comedor.fecha_fundacion ? String(comedor.fecha_fundacion).slice(0, 10) : '',
        });
        // COM-27: precarga la ubicación desde los FK guardados
        setUbicacion({
            departamento_id: comedor.departamento_id || null,
            provincia_id: comedor.provincia_id || null,
            distrito_id: comedor.distrito_id || null,
            municipalidad_id: null,
        });
        setModalComedorAbierto(true);
    };

    // ---------- Guardar comedor (crear o editar) ----------
    const guardarComedor = async (e) => {
        e.preventDefault();
        setError('');
        if (!formComedor.nombre.trim()) {
            setError('El nombre del comedor es obligatorio.');
            return;
        }
        // COM-27: la ubicación debe estar completa hasta distrito
        if (!ubicacion.departamento_id || !ubicacion.provincia_id || !ubicacion.distrito_id) {
            setError('Complete la ubicación geográfica (departamento, provincia y distrito).');
            return;
        }
        setGuardando(true);
        try {
            const payload = {
                nombre: formComedor.nombre.trim(),
                zona: formComedor.zona.trim() || null,
                direccion: formComedor.direccion.trim() || null,
                link_ubicacion: formComedor.link_ubicacion.trim() || null,
                fecha_fundacion: formComedor.fecha_fundacion || null,
                usuario_solicitante_id: usuario.id,
                // COM-27: FK de ubicación geográfica (fuente de verdad)
                departamento_id: ubicacion.departamento_id,
                provincia_id: ubicacion.provincia_id,
                distrito_id: ubicacion.distrito_id,
            };
            if (comedorEnEdicion) {
                await api.updateComedor(comedorEnEdicion.id, payload);
                setExito('Comedor actualizado exitosamente.');
            } else {
                await api.createComedor(payload);
                setExito('Comedor creado exitosamente.');
            }
            setModalComedorAbierto(false);
            cargarComedores();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    };

    // ---------- Asociación de usuarios a comedor ----------
    const abrirModalAsociar = async (comedor) => {
        setComedorAsociar(comedor);
        setDocumentoBuscar('');
        setUsuarioEncontrado(null);
        setRolAsignar('Operador');
        setModalAsociarAbierto(true);
        try {
            setUsuariosComedor(await api.getUsuariosComedor(comedor.id));
        } catch (e) {
            setError(e.message);
        }
    };

    const buscarUsuarioPorDocumento = async () => {
        if (!documentoBuscar.trim()) return;
        setBuscandoUsuario(true);
        setError('');
        setUsuarioEncontrado(null);
        try {
            setUsuarioEncontrado(await api.buscarUsuarioPorDocumento(documentoBuscar.trim()));
        } catch (e) {
            setError(e.message);
        } finally {
            setBuscandoUsuario(false);
        }
    };

    const asociarUsuario = async () => {
        if (!usuarioEncontrado) return;
        setError('');
        try {
            await api.asociarUsuarioComedor(comedorAsociar.id, {
                usuario_id: usuarioEncontrado.id,
                rol: rolAsignar,
                usuario_solicitante_id: usuario.id,
            });
            setExito('Usuario asociado al comedor exitosamente.');
            setUsuariosComedor(await api.getUsuariosComedor(comedorAsociar.id));
            setDocumentoBuscar('');
            setUsuarioEncontrado(null);
        } catch (e) {
            setError(e.message);
        }
    };

    const confirmarDesactivarUsuario = async () => {
        const { comedorId, usuarioId, activar } = confDesactivar;
        setConfDesactivar(null);
        try {
            await api.cambiarEstadoUsuarioComedor(comedorId, usuarioId, {
                estado_activo: activar,
                usuario_solicitante_id: usuario.id,
            });
            setExito(activar ? 'Usuario activado en el comedor.' : 'Usuario desactivado del comedor.');
            setUsuariosComedor(await api.getUsuariosComedor(comedorId));
        } catch (e) {
            setError(e.message);
        }
    };

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Store className="text-emerald-600" size={22} /> Gestión de Comedores
                    </h2>
                    <p className="text-sm text-slate-500">
                        Administre los comedores y su ubicación geográfica (selección en cascada).
                    </p>
                </div>
                <button
                    onClick={abrirModalCrear}
                    className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                >
                    <Plus size={16} /> Nuevo Comedor
                </button>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Filtros */}
            <div className="flex flex-wrap gap-3 mb-4">
                <div className="relative flex-1 min-w-[220px]">
                    <Search size={15} className="absolute left-3 top-2.5 text-slate-400" />
                    <input
                        type="text"
                        value={filtroNombre}
                        onChange={(e) => setFiltroNombre(e.target.value)}
                        placeholder="Buscar por nombre..."
                        className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                </div>
                <input
                    type="text"
                    value={filtroDepartamento}
                    onChange={(e) => setFiltroDepartamento(e.target.value)}
                    placeholder="Filtrar por departamento..."
                    className="flex-1 min-w-[220px] px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                />
            </div>

            {/* Tabla de comedores */}
            <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                    <thead>
                        <tr className="bg-slate-100 text-slate-600">
                            <th className="p-3 font-semibold">Nombre</th>
                            <th className="p-3 font-semibold">Ubicación</th>
                            <th className="p-3 font-semibold">Zona</th>
                            <th className="p-3 font-semibold">Fundación</th>
                            <th className="p-3 font-semibold text-right">Acciones</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {cargando ? (
                            <tr><td colSpan="5" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                        ) : comedores.length === 0 ? (
                            <tr><td colSpan="5" className="p-8 text-center text-slate-500">No se encontraron comedores.</td></tr>
                        ) : comedores.map(c => (
                            <tr key={c.id} className="hover:bg-slate-50">
                                <td className="p-3 font-medium text-slate-800">{c.nombre}</td>
                                <td className="p-3 text-slate-600">
                                    {/* COM-27: muestra la ubicación resuelta desde los FK */}
                                    <span className="flex items-center gap-1">
                                        <MapPin size={13} className="text-emerald-600" />
                                        {[c.distrito_nombre, c.provincia_nombre, c.departamento_nombre]
                                            .filter(Boolean).join(', ') || 'Sin ubicación'}
                                    </span>
                                </td>
                                <td className="p-3 text-slate-600">{c.zona || '—'}</td>
                                <td className="p-3 text-slate-600">{c.fecha_fundacion || '—'}</td>
                                <td className="p-3">
                                    <div className="flex justify-end gap-2">
                                        <button
                                            onClick={() => abrirModalEditar(c)}
                                            title="Editar comedor"
                                            className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                        >
                                            <Edit3 size={15} />
                                        </button>
                                        <button
                                            onClick={() => abrirModalAsociar(c)}
                                            title="Asociar usuarios"
                                            className="p-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg transition-colors"
                                        >
                                            <UserPlus size={15} />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* ===== Modal crear/editar comedor ===== */}
            {modalComedorAbierto && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden">
                        <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                            <h3 className="font-bold text-lg flex items-center gap-2">
                                <Store size={20} /> {comedorEnEdicion ? 'Editar Comedor' : 'Nuevo Comedor'}
                            </h3>
                            <button onClick={() => setModalComedorAbierto(false)} className="text-emerald-100 hover:text-white transition-colors" aria-label="Cerrar">
                                <X size={22} />
                            </button>
                        </div>

                        <form onSubmit={guardarComedor} className="p-6 space-y-4 overflow-y-auto">
                            {error && (
                                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                                    <AlertCircle size={16} /> {error}
                                </div>
                            )}

                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Nombre del comedor *</label>
                                <input
                                    type="text"
                                    value={formComedor.nombre}
                                    onChange={(e) => setFormComedor({ ...formComedor, nombre: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>

                            {/* COM-27: ubicación en cascada (reemplaza departamento/ciudad/distrito de texto libre) */}
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

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Zona</label>
                                    <input
                                        type="text"
                                        value={formComedor.zona}
                                        onChange={(e) => setFormComedor({ ...formComedor, zona: e.target.value })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                    />
                                </div>
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Fecha de fundación</label>
                                    <input
                                        type="date"
                                        value={formComedor.fecha_fundacion}
                                        onChange={(e) => setFormComedor({ ...formComedor, fecha_fundacion: e.target.value })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Dirección</label>
                                <input
                                    type="text"
                                    value={formComedor.direccion}
                                    onChange={(e) => setFormComedor({ ...formComedor, direccion: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Link de ubicación (mapa)</label>
                                <input
                                    type="url"
                                    value={formComedor.link_ubicacion}
                                    onChange={(e) => setFormComedor({ ...formComedor, link_ubicacion: e.target.value })}
                                    placeholder="https://maps.google.com/?q=..."
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>

                            <div className="flex justify-end gap-3 pt-2">
                                <button type="button" onClick={() => setModalComedorAbierto(false)}
                                    className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                                    Cancelar
                                </button>
                                <button type="submit" disabled={guardando}
                                    className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                                    {guardando && <Loader2 className="animate-spin" size={15} />}
                                    {comedorEnEdicion ? 'Guardar cambios' : 'Crear comedor'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ===== Modal asociar usuarios a comedor ===== */}
            {modalAsociarAbierto && comedorAsociar && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[92vh] flex flex-col overflow-hidden">
                        <div className="flex justify-between items-center px-6 py-4 bg-blue-700 text-white shrink-0">
                            <h3 className="font-bold text-lg flex items-center gap-2">
                                <UserPlus size={20} /> Usuarios de: {comedorAsociar.nombre}
                            </h3>
                            <button onClick={() => setModalAsociarAbierto(false)} className="text-blue-100 hover:text-white transition-colors" aria-label="Cerrar">
                                <X size={22} />
                            </button>
                        </div>

                        <div className="p-6 space-y-4 overflow-y-auto">
                            {error && (
                                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                                    <AlertCircle size={16} /> {error}
                                </div>
                            )}

                            {/* Búsqueda de usuario por documento */}
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={documentoBuscar}
                                    onChange={(e) => setDocumentoBuscar(e.target.value)}
                                    placeholder="Documento de identidad..."
                                    className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <button
                                    onClick={buscarUsuarioPorDocumento}
                                    disabled={buscandoUsuario}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 flex items-center gap-2"
                                >
                                    {buscandoUsuario ? <Loader2 className="animate-spin" size={15} /> : <Search size={15} />}
                                    Buscar
                                </button>
                            </div>

                            {usuarioEncontrado && (
                                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg flex flex-wrap items-center justify-between gap-2">
                                    <span className="text-sm text-slate-700">
                                        {usuarioEncontrado.nombres} {usuarioEncontrado.apellido_paterno} — {usuarioEncontrado.documento_identidad}
                                    </span>
                                    <div className="flex items-center gap-2">
                                        <select
                                            value={rolAsignar}
                                            onChange={(e) => setRolAsignar(e.target.value)}
                                            className="px-2 py-1 border border-slate-300 rounded-lg text-sm bg-white"
                                        >
                                            <option value="Administrador">Administrador</option>
                                            <option value="Operador">Operador</option>
                                        </select>
                                        <button
                                            onClick={asociarUsuario}
                                            className="px-3 py-1 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm"
                                        >
                                            Asociar
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Lista de usuarios del comedor */}
                            <div className="rounded-lg border border-slate-200 overflow-hidden">
                                <table className="w-full text-left text-sm">
                                    <thead>
                                        <tr className="bg-slate-100 text-slate-600">
                                            <th className="p-2 font-semibold">Usuario</th>
                                            <th className="p-2 font-semibold">Rol</th>
                                            <th className="p-2 font-semibold text-center">Estado</th>
                                            <th className="p-2 font-semibold text-right">Acción</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-200">
                                        {usuariosComedor.length === 0 ? (
                                            <tr><td colSpan="4" className="p-4 text-center text-slate-500">Sin usuarios asociados.</td></tr>
                                        ) : usuariosComedor.map(uc => (
                                            <tr key={uc.id}>
                                                <td className="p-2 text-slate-700">{uc.nombres} {uc.apellido_paterno}</td>
                                                <td className="p-2 text-slate-600">{uc.rol}</td>
                                                <td className="p-2 text-center">
                                                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${uc.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                                                        {uc.estado_activo ? 'Activo' : 'Inactivo'}
                                                    </span>
                                                </td>
                                                <td className="p-2 text-right">
                                                    <button
                                                        onClick={() => setConfDesactivar({ comedorId: comedorAsociar.id, usuarioId: uc.usuario_id, activar: !uc.estado_activo })}
                                                        className={`p-1 rounded-lg transition-colors ${uc.estado_activo ? 'bg-red-50 text-red-600 hover:bg-red-100' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
                                                        title={uc.estado_activo ? 'Desactivar' : 'Activar'}
                                                    >
                                                        {uc.estado_activo ? <UserX size={15} /> : <UserCheck size={15} />}
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Confirmaciones y éxito */}
            <ModalConfirmacion
                isOpen={!!confDesactivar}
                onClose={() => setConfDesactivar(null)}
                onConfirm={confirmarDesactivarUsuario}
                mensaje={confDesactivar
                    ? `¿${confDesactivar.activar ? 'Activar' : 'Desactivar'} al usuario en este comedor?`
                    : ''}
                tipo={confDesactivar?.activar ? 'warning' : 'danger'}
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};