/**
 * components/comedores/ModalGestionUsuariosComedor.jsx
 * Objetivo: COM-21: gestionar los usuarios de un comedor específico: buscar por documento
 *          y asociar con rol (Administrador/Operador), activar/desactivar por comedor con
 *          confirmación y auditoría (quién y cuándo desactivó). El backend aplica las
 *          reglas: solo admin del comedor o del sistema, nadie se desactiva a sí mismo y
 *          el comedor no queda sin su último admin activo.
 * Uso: Abierto por ComedoresView pasando el `comedor` seleccionado y `onClose`.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { X, UserSearch, UserPlus, Loader2, ShieldCheck, ShieldOff } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

export const ModalGestionUsuariosComedor = ({ comedor, onClose }) => {
    const { usuario } = useAuth();

    // Usuarios asociados al comedor
    const [usuarios, setUsuarios] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    // Flujo de asociación: búsqueda por documento + rol
    const [documento, setDocumento] = useState('');
    const [buscando, setBuscando] = useState(false);
    const [candidato, setCandidato] = useState(null);
    const [rolNuevo, setRolNuevo] = useState('Operador');
    const [errorAdd, setErrorAdd] = useState('');
    const [procesando, setProcesando] = useState(false);

    // Confirmación de desactivación y aviso de éxito
    const [confDesactivar, setConfDesactivar] = useState(null);
    const [exito, setExito] = useState('');

    const cargarUsuarios = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            setUsuarios(await api.getUsuariosComedor(comedor.id));
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, [comedor.id]);

    useEffect(() => { cargarUsuarios(); }, [cargarUsuarios]);

    // Búsqueda del usuario por documento antes de asociarlo
    const buscarUsuario = async () => {
        setErrorAdd('');
        setCandidato(null);
        if (!documento.trim()) {
            setErrorAdd('Ingrese un documento para buscar.');
            return;
        }
        setBuscando(true);
        try {
            setCandidato(await api.buscarUsuarioPorDocumento(documento.trim()));
        } catch (e) {
            setErrorAdd(e.message);
        } finally {
            setBuscando(false);
        }
    };

    // Asociación del usuario encontrado con el rol elegido
    const asociar = async () => {
        setProcesando(true);
        setErrorAdd('');
        try {
            await api.asociarUsuarioComedor(comedor.id, {
                usuario_id: candidato.id,
                rol: rolNuevo,
                usuario_solicitante_id: usuario.id
            });
            setExito('Usuario asociado al comedor exitosamente');
            setCandidato(null);
            setDocumento('');
            setRolNuevo('Operador');
            cargarUsuarios();
        } catch (e) {
            setErrorAdd(e.message);
        } finally {
            setProcesando(false);
        }
    };

    // Activación/desactivación del usuario DENTRO del comedor (estado por comedor)
    const cambiarEstado = async (u, activo) => {
        setProcesando(true);
        setError('');
        try {
            await api.cambiarEstadoUsuarioComedor(comedor.id, u.usuario_id, {
                estado_activo: activo,
                usuario_solicitante_id: usuario.id
            });
            setExito(activo ? 'Usuario activado en el comedor' : 'Usuario desactivado en el comedor');
            setConfDesactivar(null);
            cargarUsuarios();
        } catch (e) {
            // El backend devuelve reglas de negocio (último admin, auto-desactivación, permisos)
            setError(e.message);
            setConfDesactivar(null);
        } finally {
            setProcesando(false);
        }
    };

    return (
        <>
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">

                    {/* Encabezado con el comedor en gestión */}
                    <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                        <div>
                            <h3 className="font-bold text-lg">Usuarios del Comedor</h3>
                            <p className="text-emerald-100 text-sm">{comedor.nombre} — {comedor.distrito}, {comedor.departamento}</p>
                        </div>
                        <button onClick={onClose} className="text-emerald-100 hover:text-white transition-colors" aria-label="Cerrar">
                            <X size={24} />
                        </button>
                    </div>

                    <div className="p-6 overflow-y-auto space-y-5">
                        {/* ===== Sección: asociar nuevo usuario ===== */}
                        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4">
                            <h4 className="text-sm font-bold text-slate-700 mb-3 flex items-center gap-2">
                                <UserPlus size={16} className="text-emerald-600" /> Asociar usuario al comedor
                            </h4>
                            <div className="flex flex-wrap gap-2">
                                <input
                                    type="text"
                                    value={documento}
                                    onChange={(e) => setDocumento(e.target.value.replace(/[^0-9A-Za-z]/g, ''))}
                                    placeholder="Documento (DNI/CE) del usuario"
                                    className="flex-1 min-w-[200px] px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                                />
                                <button onClick={buscarUsuario} disabled={buscando}
                                    className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-800 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                    {buscando ? <Loader2 className="animate-spin" size={16} /> : <UserSearch size={16} />}
                                    Buscar
                                </button>
                            </div>

                            {/* Resultado de búsqueda con selección de rol */}
                            {candidato && (
                                <div className="mt-3 flex flex-wrap items-center gap-3 bg-white border border-emerald-200 rounded-lg p-3">
                                    <div className="flex-1 min-w-[200px]">
                                        <p className="text-sm font-semibold text-slate-800">
                                            {candidato.nombres} {candidato.apellido_paterno} {candidato.apellido_materno}
                                        </p>
                                        <p className="text-xs text-slate-500">{candidato.tipo_documento} {candidato.documento_identidad}</p>
                                    </div>
                                    <select value={rolNuevo} onChange={(e) => setRolNuevo(e.target.value)}
                                        className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white">
                                        <option value="Operador">Operador</option>
                                        <option value="Administrador">Administrador</option>
                                    </select>
                                    <button onClick={asociar} disabled={procesando}
                                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                        Asociar
                                    </button>
                                </div>
                            )}
                            {errorAdd && (
                                <p className="mt-2 text-sm text-red-600">{errorAdd}</p>
                            )}
                        </div>

                        {/* ===== Sección: usuarios asociados ===== */}
                        {error && (
                            <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-sm">{error}</div>
                        )}

                        {loading ? (
                            <div className="flex items-center justify-center py-10 text-slate-400">
                                <Loader2 className="animate-spin mr-2" size={20} /> Cargando usuarios...
                            </div>
                        ) : (
                            <div className="overflow-x-auto border border-slate-200 rounded-lg">
                                <table className="w-full text-sm text-left">
                                    <thead className="bg-slate-100 text-slate-600 uppercase text-xs">
                                        <tr>
                                            <th className="px-4 py-3">Usuario</th>
                                            <th className="px-4 py-3">Rol en el comedor</th>
                                            <th className="px-4 py-3">Estado</th>
                                            <th className="px-4 py-3 text-right">Acción</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {usuarios.length === 0 && (
                                            <tr><td colSpan="4" className="px-4 py-8 text-center text-slate-400">Sin usuarios asociados.</td></tr>
                                        )}
                                        {usuarios.map(u => (
                                            <tr key={u.id} className="border-t border-slate-200 hover:bg-slate-50">
                                                <td className="px-4 py-3">
                                                    <p className="font-semibold text-slate-800">
                                                        {u.nombres} {u.apellido_paterno} {u.apellido_materno}
                                                    </p>
                                                    <p className="text-xs text-slate-500">{u.tipo_documento} {u.documento_identidad}</p>
                                                    {!u.estado_activo && u.fecha_desactivacion && (
                                                        <p className="text-xs text-red-500">Desactivado: {String(u.fecha_desactivacion).slice(0, 10)}</p>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${u.rol === 'Administrador' ? 'bg-purple-100 text-purple-700' : 'bg-slate-100 text-slate-600'}`}>
                                                        {u.rol}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${u.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                                                        {u.estado_activo ? 'Activo' : 'Inactivo'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="flex justify-end">
                                                        {u.estado_activo ? (
                                                            <button onClick={() => setConfDesactivar(u)} disabled={procesando}
                                                                className="flex items-center gap-1 px-3 py-1.5 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg text-xs font-medium transition-colors disabled:opacity-50">
                                                                <ShieldOff size={14} /> Desactivar
                                                            </button>
                                                        ) : (
                                                            <button onClick={() => cambiarEstado(u, true)} disabled={procesando}
                                                                className="flex items-center gap-1 px-3 py-1.5 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded-lg text-xs font-medium transition-colors disabled:opacity-50">
                                                                <ShieldCheck size={14} /> Activar
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Confirmación de desactivación (regla COM-21: acción sensible) */}
            <ModalConfirmacion
                isOpen={!!confDesactivar}
                onClose={() => setConfDesactivar(null)}
                onConfirm={() => cambiarEstado(confDesactivar, false)}
                mensaje={confDesactivar
                    ? `¿Desactivar a ${confDesactivar.nombres} ${confDesactivar.apellido_paterno} del comedor "${comedor.nombre}"? El usuario perderá acceso a este comedor (podrá reactivarse después).`
                    : ''}
                tipo="danger"
            />

            {/* Aviso de éxito reutilizable (COM-18) */}
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </>
    );
};