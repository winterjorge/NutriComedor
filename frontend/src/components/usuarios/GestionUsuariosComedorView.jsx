/**
 * components/usuarios/GestionUsuariosComedorView.jsx
 * Objetivo: Panel del administrador de comedor (COM-23): gestionar a los usuarios de su
 *           comedor: activar/desactivar membresías, modificar grupos/roles, otorgar y
 *           revocar roles temporales con vigencia, y desbloquear cuentas bloqueadas por
 *           intentos fallidos de contraseña.
 * Uso: Renderizado por App.jsx en la pestaña "Usuarios" cuando el perfil tiene ámbito de
 *      comedor (Directivo con rol de gestión o Administrativo con cobertura). Usa el
 *      comedor de la sesión (COM-20); los Administrativos ven un selector de comedores.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, AlertCircle, UserCheck, UserX, ShieldCheck, History } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';
import { ModalRolTemporal } from './ModalRolTemporal';
import { ModalGruposUsuarioComedor } from './ModalGruposUsuarioComedor';

export const GestionUsuariosComedorView = () => {
    const { usuario, seleccion } = useAuth();

    // Comedores que el perfil de sesión puede gestionar
    const [opcionesComedor, setOpcionesComedor] = useState([]);
    const [comedorSel, setComedorSel] = useState(seleccion?.comedor_id || '');

    // Usuarios del comedor seleccionado (con estado de membresía y cuenta)
    const [usuarios, setUsuarios] = useState([]);
    const [cargando, setCargando] = useState(true);

    // Feedback y confirmaciones
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');
    const [confEstado, setConfEstado] = useState(null);      // { objetivo, activar }
    const [confDesbloqueo, setConfDesbloqueo] = useState(null);
    const [modalRolTemp, setModalRolTemp] = useState(null);  // usuario objetivo
    const [modalGrupos, setModalGrupos] = useState(null);    // usuario objetivo

    // Opciones de comedor según perfil (COM-20 / COM-23)
    useEffect(() => {
        const cargarOpciones = async () => {
            if (seleccion?.perfil === 'COMEDOR') {
                // Perfil de comedor: solo su comedor activo
                setOpcionesComedor([{ id: seleccion.comedor_id, nombre: seleccion.comedor_nombre }]);
                setComedorSel(seleccion.comedor_id);
            } else {
                // Administrativo municipal: selector con los comedores que cubre
                const todos = await api.getComedores();
                setOpcionesComedor(todos);
                if (todos.length && !seleccion?.comedor_id) setComedorSel(todos[0].id);
            }
        };
        cargarOpciones().catch(e => setError(e.message));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Carga los usuarios del comedor seleccionado
    const cargarUsuarios = useCallback(async () => {
        if (!comedorSel) return;
        setCargando(true);
        setError('');
        try {
            setUsuarios(await api.getUsuarios({
                comedor_id: comedorSel,
                usuario_solicitante_id: usuario.id
            }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [comedorSel, usuario.id]);

    useEffect(() => { cargarUsuarios(); }, [cargarUsuarios]);

    // Activar/desactivar membresía del usuario en el comedor
    const confirmarEstadoMembresia = async () => {
        const { objetivo, activar } = confEstado;
        setConfEstado(null);
        try {
            await api.cambiarEstadoUsuarioComedor(comedorSel, objetivo.id, {
                estado_activo: activar,
                usuario_solicitante_id: usuario.id
            });
            setExito(activar ? 'Usuario activado en el comedor' : 'Usuario desactivado en el comedor');
            cargarUsuarios();
        } catch (e) {
            setError(e.message);
        }
    };

    // Desbloqueo por intentos fallidos (regla COM-23 para admin de comedor)
    const confirmarDesbloqueo = async () => {
        const objetivo = confDesbloqueo;
        setConfDesbloqueo(null);
        try {
            await api.desbloquearReintentos(objetivo.id, { usuario_solicitante_id: usuario.id });
            setExito('Bloqueo por intentos restablecido exitosamente');
            cargarUsuarios();
        } catch (e) {
            setError(e.message);
        }
    };

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado y selector de comedor */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <UserCheck className="text-emerald-600" size={22} /> Usuarios de mi Comedor
                    </h2>
                    <p className="text-sm text-slate-500">
                        Active/desactive usuarios, modifique grupos, otorgue roles temporales y desbloquee por intentos.
                    </p>
                </div>
                {opcionesComedor.length > 1 && (
                    <select
                        value={comedorSel}
                        onChange={(e) => setComedorSel(Number(e.target.value))}
                        className="px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                    >
                        {opcionesComedor.map(c => (
                            <option key={c.id} value={c.id}>{c.nombre} — {c.distrito}</option>
                        ))}
                    </select>
                )}
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Tabla de usuarios del comedor */}
            <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                    <thead>
                        <tr className="bg-slate-100 text-slate-600">
                            <th className="p-3 font-semibold">Documento</th>
                            <th className="p-3 font-semibold">Nombres</th>
                            <th className="p-3 font-semibold">Rol en el comedor</th>
                            <th className="p-3 font-semibold text-center">Membresía</th>
                            <th className="p-3 font-semibold text-center">Cuenta</th>
                            <th className="p-3 font-semibold text-right">Acciones</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {cargando ? (
                            <tr><td colSpan="6" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                        ) : usuarios.length === 0 ? (
                            <tr><td colSpan="6" className="p-8 text-center text-slate-500">No hay usuarios asociados a este comedor.</td></tr>
                        ) : usuarios.map(u => (
                            <tr key={u.id} className="hover:bg-slate-50">
                                <td className="p-3 font-medium text-slate-800">{u.tipo_documento} {u.documento_identidad}</td>
                                <td className="p-3 text-slate-700">{u.nombres} {u.apellido_paterno} {u.apellido_materno}</td>
                                <td className="p-3 text-slate-600">{u.rol_comedor || '—'}</td>
                                <td className="p-3 text-center">
                                    <span className={`px-2 py-1 rounded-full text-xs font-bold ${u.membresia_activa ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                                        {u.membresia_activa ? 'Activo' : 'Inactivo'}
                                    </span>
                                </td>
                                <td className="p-3 text-center">
                                    <span className={`px-2 py-1 rounded-full text-xs font-bold ${u.bloqueado ? 'bg-amber-100 text-amber-700' : u.estado_activo ? 'bg-slate-100 text-slate-600' : 'bg-red-100 text-red-600'}`}>
                                        {u.bloqueado ? `Bloqueada (${u.intentos_fallidos})` : u.estado_activo ? 'Activa' : 'Bloqueada'}
                                    </span>
                                </td>
                                <td className="p-3">
                                    <div className="flex justify-end gap-2">
                                        {/* Modificar grupos/roles del usuario */}
                                        <button
                                            onClick={() => setModalGrupos(u)}
                                            title="Modificar grupos y roles"
                                            className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                        >
                                            <ShieldCheck size={15} />
                                        </button>
                                        {/* Rol temporal con vigencia */}
                                        <button
                                            onClick={() => setModalRolTemp(u)}
                                            title="Otorgar/revocar rol temporal"
                                            className="p-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg transition-colors"
                                        >
                                            <History size={15} />
                                        </button>
                                        {/* Desbloqueo por intentos (solo si está bloqueado) */}
                                        {u.bloqueado && (
                                            <button
                                                onClick={() => setConfDesbloqueo(u)}
                                                title="Desbloquear por intentos fallidos"
                                                className="p-1.5 bg-amber-50 text-amber-700 hover:bg-amber-100 rounded-lg transition-colors"
                                            >
                                                <RefreshCw size={15} />
                                            </button>
                                        )}
                                        {/* Activar/desactivar membresía en el comedor */}
                                        <button
                                            onClick={() => setConfEstado({ objetivo: u, activar: !u.membresia_activa })}
                                            title={u.membresia_activa ? 'Desactivar en el comedor' : 'Activar en el comedor'}
                                            className={`p-1.5 rounded-lg transition-colors ${u.membresia_activa ? 'bg-red-50 text-red-600 hover:bg-red-100' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
                                        >
                                            {u.membresia_activa ? <UserX size={15} /> : <UserCheck size={15} />}
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* ===== Modales y confirmaciones ===== */}
            {modalRolTemp && (
                <ModalRolTemporal
                    usuarioObjetivo={modalRolTemp}
                    comedorId={comedorSel}
                    onClose={() => setModalRolTemp(null)}
                    onExito={() => { setModalRolTemp(null); setExito('Rol temporal otorgado exitosamente'); cargarUsuarios(); }}
                />
            )}
            {modalGrupos && (
                <ModalGruposUsuarioComedor
                    usuarioObjetivo={modalGrupos}
                    comedorId={comedorSel}
                    onClose={() => setModalGrupos(null)}
                    onExito={() => { setModalGrupos(null); setExito('Membresías actualizadas exitosamente'); cargarUsuarios(); }}
                />
            )}

            <ModalConfirmacion
                isOpen={!!confEstado}
                onClose={() => setConfEstado(null)}
                onConfirm={confirmarEstadoMembresia}
                mensaje={confEstado
                    ? `¿${confEstado.activar ? 'Activar' : 'Desactivar'} a ${confEstado.objetivo.nombres} ${confEstado.objetivo.apellido_paterno} en el comedor? ${confEstado.activar ? '' : 'Perderá acceso a este comedor.'}`
                    : ''}
                tipo={confEstado?.activar ? 'warning' : 'danger'}
            />
            <ModalConfirmacion
                isOpen={!!confDesbloqueo}
                onClose={() => setConfDesbloqueo(null)}
                onConfirm={confirmarDesbloqueo}
                mensaje={confDesbloqueo
                    ? `¿Restablecer el bloqueo por intentos de ${confDesbloqueo.nombres} ${confDesbloqueo.apellido_paterno}? Se reiniciará su contador.`
                    : ''}
                tipo="warning"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};