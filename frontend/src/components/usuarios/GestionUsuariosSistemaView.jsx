/**
 * components/usuarios/GestionUsuariosSistemaView.jsx
 * Objetivo: Panel global de administración (COM-25) para perfiles con módulos
 *           administrativos: usuarios y bloqueos, municipalidades, grupos y
 *           privilegios, política de claves y permisos por vistas.
 * Historial:
 *  - COM-23/COM-25: sub-pestañas y CRUD de municipalidades/grupos/política/vistas.
 *  - COM-26: creación y edición de usuarios con precarga de membresías y alcance.
 *  - COM-38 (este archivo): botón "Resetear contraseña" por fila de usuario y montaje
 *    del ModalResetClave (reset aleatorio o clave específica, exclusivo Admin de
 *    Sistemas). Nada existente se elimina: solo se agregan líneas marcadas COM-38
 *    (import del modal, estado resetUsuario, botón en acciones y montaje al final).
 * Uso: Montada por App.jsx cuando el usuario posee módulos administrativos
 *      (modulosPermitidos prop).
 * Referencia: tickets COM-23/25/26 y COM-38 (solo trazabilidad).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Users, Building2, ShieldCheck, KeyRound, Plus, Lock, Unlock,
    RefreshCw, Loader2, AlertCircle, Edit3, Eye
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';
import { ModalCrearUsuario } from './ModalCrearUsuario';
import { ModalEditarUsuario } from './ModalEditarUsuario';
import { ModalMunicipalidad } from './ModalMunicipalidad';
import { ModalGrupoPrivilegios } from './ModalGrupoPrivilegios';
import { VistaPermisosView } from './VistaPermisosView';
// COM-38: modal de reseteo/cambio de contraseña por Admin de Sistemas
import { ModalResetClave } from './ModalResetClave';

// Catálogo de sub-pestañas con su módulo requerido (COM-25)
const SUBTABS = [
    { id: 'usuarios', label: 'Usuarios y bloqueos', modulo: 'bloqueos', icon: Users },
    { id: 'municipalidades', label: 'Municipalidades', modulo: 'municipalidades', icon: Building2 },
    { id: 'grupos', label: 'Grupos y privilegios', modulo: 'roles', icon: ShieldCheck },
    { id: 'politica', label: 'Política de claves', modulo: 'bloqueos', icon: KeyRound },
    { id: 'vistas', label: 'Permisos por vistas', modulo: 'vistas', icon: Eye },
];

export const GestionUsuariosSistemaView = ({ modulosPermitidos = [] }) => {
    const { usuario } = useAuth();

    // ===== Estado: sub-pestaña activa =====
    const [subtab, setSubtab] = useState('usuarios');

    // ===== Estado: Usuarios =====
    const [usuarios, setUsuarios] = useState([]);
    const [q, setQ] = useState('');
    const [estado, setEstado] = useState('');
    const [cargandoUsuarios, setCargandoUsuarios] = useState(true);
    const [modalCrearUsuario, setModalCrearUsuario] = useState(false);
    const [editarUsuarioId, setEditarUsuarioId] = useState(null); // COM-26: edición con precarga
    const [confCuenta, setConfCuenta] = useState(null); // { objetivo, activar }
    const [confDesbloqueo, setConfDesbloqueo] = useState(null); // objetivo
    // COM-38: usuario objetivo del modal de reseteo de contraseña
    const [resetUsuario, setResetUsuario] = useState(null);

    // ===== Estado: Municipalidades =====
    const [municipalidades, setMunicipalidades] = useState([]);
    const [cargandoMunicipalidades, setCargandoMunicipalidades] = useState(false);
    const [modalMuni, setModalMuni] = useState(null); // { crear: true } | { editar: objeto }

    // ===== Estado: Grupos y privilegios =====
    const [grupos, setGrupos] = useState([]);
    const [cargandoGrupos, setCargandoGrupos] = useState(false);
    const [modalPrivilegios, setModalPrivilegios] = useState(null); // grupo seleccionado
    const [nuevoGrupo, setNuevoGrupo] = useState({ nombre: '', ambito: 'COMEDOR', descripcion: '' });
    const [creandoGrupo, setCreandoGrupo] = useState(false);

    // ===== Estado: Política de claves =====
    const [politica, setPolitica] = useState(null);
    const [guardandoPolitica, setGuardandoPolitica] = useState(false);

    // ===== Feedback global =====
    const [exito, setExito] = useState('');
    const [error, setError] = useState('');

    // ---------- Cargadores ----------
    const cargarUsuarios = useCallback(async () => {
        setCargandoUsuarios(true);
        try {
            const params = {};
            if (q) params.q = q;
            if (estado) params.estado = estado;
            setUsuarios(await api.getUsuarios(params));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoUsuarios(false);
        }
    }, [q, estado]);

    const cargarMunicipalidades = useCallback(async () => {
        setCargandoMunicipalidades(true);
        try {
            setMunicipalidades(await api.getMunicipalidades());
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoMunicipalidades(false);
        }
    }, []);

    const cargarGrupos = useCallback(async () => {
        setCargandoGrupos(true);
        try {
            setGrupos(await api.getGrupos());
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoGrupos(false);
        }
    }, []);

    const cargarPolitica = useCallback(async () => {
        try {
            setPolitica(await api.getPoliticaClave());
        } catch (e) {
            setError(e.message);
        }
    }, []);

    useEffect(() => { cargarUsuarios(); }, [cargarUsuarios]);
    useEffect(() => {
        if (subtab === 'municipalidades') cargarMunicipalidades();
        if (subtab === 'grupos') cargarGrupos();
        if (subtab === 'politica') cargarPolitica();
    }, [subtab, cargarMunicipalidades, cargarGrupos, cargarPolitica]);

    // Sub-pestañas visibles según módulos permitidos (COM-25)
    const subtabsVisibles = SUBTABS.filter(t => modulosPermitidos.includes(t.modulo));
    const idsVisibles = subtabsVisibles.map(t => t.id).join(',');
    useEffect(() => {
        if (subtabsVisibles.length > 0 && !idsVisibles.split(',').includes(subtab)) {
            setSubtab(idsVisibles.split(',')[0]);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [idsVisibles]);

    // ---------- Handlers ----------
    const guardarPolitica = async (e) => {
        e.preventDefault();
        setGuardandoPolitica(true);
        try {
            await api.updatePoliticaClave({ ...politica, usuario_solicitante_id: usuario.id });
            setExito('Política de claves actualizada exitosamente');
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardandoPolitica(false);
        }
    };

    const crearGrupo = async (e) => {
        e.preventDefault();
        setCreandoGrupo(true);
        try {
            await api.createGrupo({ ...nuevoGrupo, usuario_solicitante_id: usuario.id });
            setExito('Grupo creado exitosamente');
            setNuevoGrupo({ nombre: '', ambito: 'COMEDOR', descripcion: '' });
            cargarGrupos();
        } catch (err) {
            setError(err.message);
        } finally {
            setCreandoGrupo(false);
        }
    };

    const confirmarCuenta = async () => {
        const { objetivo, activar } = confCuenta;
        setConfCuenta(null);
        try {
            await api.cambiarEstadoCuenta(objetivo.id, {
                activar,
                usuario_solicitante_id: usuario.id,
            });
            setExito(activar ? 'Cuenta desbloqueada exitosamente' : 'Cuenta bloqueada exitosamente');
            cargarUsuarios();
        } catch (e) {
            setError(e.message);
        }
    };

    const confirmarDesbloqueoReintentos = async () => {
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
            {/* Encabezado y sub-pestañas */}
            <div className="mb-5">
                <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2 mb-3">
                    <ShieldCheck className="text-emerald-600" size={22} /> Administración del Sistema
                </h2>
                <div className="flex gap-2 border-b border-slate-200 pb-2 overflow-x-auto">
                    {subtabsVisibles.map(t => {
                        const Icon = t.icon;
                        const activa = subtab === t.id;
                        return (
                            <button
                                key={t.id}
                                onClick={() => setSubtab(t.id)}
                                className={`flex shrink-0 items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                                    activa ? 'bg-white text-emerald-700 shadow-sm border-t border-x border-slate-200'
                                           : 'text-slate-500 hover:bg-slate-100'}`}
                            >
                                <Icon size={16} /> {t.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* ============ SUB-PESTAÑA: USUARIOS Y BLOQUEOS (bloqueos) ============ */}
            {subtab === 'usuarios' && (
                <div>
                    <div className="flex flex-wrap gap-3 mb-4 items-center">
                        <input
                            type="text"
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            placeholder="Buscar por documento o nombre..."
                            className="flex-1 min-w-[200px] px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                        />
                        <select
                            value={estado}
                            onChange={(e) => setEstado(e.target.value)}
                            className="px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        >
                            <option value="">Todos los estados</option>
                            <option value="activos">Activos</option>
                            <option value="inactivos">Inactivos</option>
                            <option value="bloqueados">Bloqueados</option>
                        </select>
                        <button
                            onClick={() => setModalCrearUsuario(true)}
                            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Plus size={16} /> Nuevo usuario
                        </button>
                    </div>

                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-3 font-semibold">Documento</th>
                                    <th className="p-3 font-semibold">Nombres</th>
                                    <th className="p-3 font-semibold">Rol</th>
                                    <th className="p-3 font-semibold">Estado</th>
                                    <th className="p-3 font-semibold">Bloqueos</th>
                                    <th className="p-3 font-semibold text-right">Acciones</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {cargandoUsuarios ? (
                                    <tr><td colSpan="6" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                                ) : usuarios.length === 0 ? (
                                    <tr><td colSpan="6" className="p-8 text-center text-slate-500">No se encontraron usuarios.</td></tr>
                                ) : usuarios.map(u => (
                                    <tr key={u.id} className="hover:bg-slate-50">
                                        <td className="p-3 font-medium text-slate-800">{u.tipo_documento} {u.documento_identidad}</td>
                                        <td className="p-3 text-slate-600">{u.nombres} {u.apellido_paterno} {u.apellido_materno || ''}</td>
                                        <td className="p-3 text-slate-600">{u.rol}</td>
                                        <td className="p-3">
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                                u.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                                {u.estado_activo ? 'Activo' : 'Inactivo'}
                                            </span>
                                        </td>
                                        <td className="p-3">
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                                u.bloqueado ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
                                                {u.bloqueado ? `Bloqueado (${u.intentos_fallidos})` : 'Libre'}
                                            </span>
                                        </td>
                                        <td className="p-3">
                                            <div className="flex justify-end gap-2">
                                                {/* COM-26: edición con precarga de membresías y alcance */}
                                                <button
                                                    onClick={() => setEditarUsuarioId(u.id)}
                                                    title="Editar usuario (datos, perfil y alcance)"
                                                    className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                                >
                                                    <Edit3 size={15} />
                                                </button>
                                                {/* COM-38: reseteo de contraseña por Admin de Sistemas */}
                                                <button
                                                    onClick={() => setResetUsuario(u)}
                                                    title="Resetear contraseña (COM-38)"
                                                    className="p-1.5 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded-lg transition-colors"
                                                >
                                                    <KeyRound size={15} />
                                                </button>
                                                {u.bloqueado && (
                                                    <button
                                                        onClick={() => setConfDesbloqueo(u)}
                                                        title="Desbloquear por intentos fallidos"
                                                        className="p-1.5 bg-amber-50 text-amber-700 hover:bg-amber-100 rounded-lg transition-colors"
                                                    >
                                                        <RefreshCw size={15} />
                                                    </button>
                                                )}
                                                <button
                                                    onClick={() => setConfCuenta({ objetivo: u, activar: !u.estado_activo })}
                                                    title={u.estado_activo ? 'Bloquear cuenta' : 'Desbloquear cuenta'}
                                                    className={`p-1.5 rounded-lg transition-colors ${
                                                        u.estado_activo ? 'bg-red-50 text-red-600 hover:bg-red-100'
                                                                        : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
                                                >
                                                    {u.estado_activo ? <Lock size={15} /> : <Unlock size={15} />}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ============ SUB-PESTAÑA: MUNICIPALIDADES ============ */}
            {subtab === 'municipalidades' && (
                <div>
                    <div className="flex justify-end mb-4">
                        <button
                            onClick={() => setModalMuni({ crear: true })}
                            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Plus size={16} /> Nueva municipalidad
                        </button>
                    </div>
                    {cargandoMunicipalidades ? (
                        <div className="p-10 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={26} /></div>
                    ) : municipalidades.length === 0 ? (
                        <p className="text-sm text-slate-500 text-center p-8">No hay municipalidades registradas.</p>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {municipalidades.map(m => (
                                <div key={m.id} className="bg-white border border-slate-200 rounded-xl p-4 flex items-start gap-3">
                                    <Building2 size={18} className="text-emerald-600 mt-0.5" />
                                    <div className="flex-1">
                                        <p className="font-bold text-slate-800 text-sm">{m.nombre}</p>
                                        <p className="text-xs text-slate-500">
                                            {m.distrito || ''}{m.provincia ? `, ${m.provincia}` : ''}{m.departamento ? ` - ${m.departamento}` : ''}
                                        </p>
                                        <div className="flex flex-wrap gap-1 mt-2">
                                            {(m.comedores || []).map(c => (
                                                <span key={c.id} className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-[10px] font-medium">
                                                    {c.nombre}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => setModalMuni({ editar: m })}
                                        className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                        title="Editar municipalidad"
                                    >
                                        <Edit3 size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* ============ SUB-PESTAÑA: GRUPOS Y PRIVILEGIOS (roles) ============ */}
            {subtab === 'grupos' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div>
                        <h3 className="font-bold text-slate-700 flex items-center gap-2 mb-3">
                            <ShieldCheck size={16} /> Grupos existentes
                        </h3>
                        {cargandoGrupos ? (
                            <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={22} /></div>
                        ) : (
                            <div className="space-y-2">
                                {grupos.map(g => (
                                    <div key={g.id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3">
                                        <div className="flex-1">
                                            <p className="text-sm font-bold text-slate-800">{g.nombre}</p>
                                            <p className="text-[11px] text-slate-500">{g.descripcion}</p>
                                        </div>
                                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                            g.ambito === 'SISTEMA' ? 'bg-red-100 text-red-700'
                                            : g.ambito === 'GLOBAL' ? 'bg-blue-100 text-blue-700'
                                            : 'bg-emerald-100 text-emerald-700'}`}>
                                            {g.ambito}
                                        </span>
                                        <button
                                            onClick={() => setModalPrivilegios(g)}
                                            className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                                        >
                                            Privilegios
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                    <div>
                        <h3 className="font-bold text-slate-700 flex items-center gap-2 mb-3">
                            <Plus size={16} /> Nuevo grupo
                        </h3>
                        <form onSubmit={crearGrupo} className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                            <div>
                                <label className="text-xs font-semibold text-slate-600 mb-1 block">Nombre</label>
                                <input
                                    type="text"
                                    value={nuevoGrupo.nombre}
                                    onChange={(e) => setNuevoGrupo({ ...nuevoGrupo, nombre: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                    required
                                />
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 mb-1 block">Ámbito</label>
                                <select
                                    value={nuevoGrupo.ambito}
                                    onChange={(e) => setNuevoGrupo({ ...nuevoGrupo, ambito: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                >
                                    <option value="COMEDOR">COMEDOR</option>
                                    <option value="GLOBAL">GLOBAL</option>
                                </select>
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 mb-1 block">Descripción</label>
                                <textarea
                                    value={nuevoGrupo.descripcion}
                                    onChange={(e) => setNuevoGrupo({ ...nuevoGrupo, descripcion: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                    rows="2"
                                />
                            </div>
                            <button
                                type="submit"
                                disabled={creandoGrupo}
                                className="w-full px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                            >
                                {creandoGrupo ? 'Creando...' : 'Crear grupo'}
                            </button>
                        </form>
                    </div>
                </div>
            )}

            {/* ============ SUB-PESTAÑA: POLÍTICA DE CLAVES (bloqueos) ============ */}
            {subtab === 'politica' && politica && (
                <form onSubmit={guardarPolitica} className="max-w-md bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
                    <h3 className="font-bold text-slate-700 flex items-center gap-2">
                        <KeyRound size={16} /> Política de contraseñas
                    </h3>
                    <div>
                        <label className="text-xs font-semibold text-slate-600 mb-1 block">Longitud mínima</label>
                        <input
                            type="number" min="6" max="32"
                            value={politica.longitud_minima ?? 8}
                            onChange={(e) => setPolitica({ ...politica, longitud_minima: Number(e.target.value) })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-slate-600 mb-1 block">Expiración (días)</label>
                        <input
                            type="number" min="30" max="730"
                            value={politica.expiracion_dias ?? 180}
                            onChange={(e) => setPolitica({ ...politica, expiracion_dias: Number(e.target.value) })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>
                    <div>
                        <label className="text-xs font-semibold text-slate-600 mb-1 block">Máximo de intentos fallidos</label>
                        <input
                            type="number" min="1" max="10"
                            value={politica.max_intentos_bloqueo ?? 3}
                            onChange={(e) => setPolitica({ ...politica, max_intentos_bloqueo: Number(e.target.value) })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                    </div>
                    {[
                        ['requiere_mayuscula', 'Exigir mayúscula'],
                        ['requiere_minuscula', 'Exigir minúscula'],
                        ['requiere_digito', 'Exigir dígito'],
                        ['requiere_simbolo', 'Exigir símbolo'],
                    ].map(([clave, label]) => (
                        <label key={clave} className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={!!politica[clave]}
                                onChange={(e) => setPolitica({ ...politica, [clave]: e.target.checked })}
                                className="accent-emerald-600"
                            />
                            {label}
                        </label>
                    ))}
                    <button
                        type="submit"
                        disabled={guardandoPolitica}
                        className="w-full px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        {guardandoPolitica ? 'Guardando...' : 'Guardar política'}
                    </button>
                </form>
            )}

            {/* ============ SUB-PESTAÑA: PERMISOS POR VISTAS (vistas) ============ */}
            {subtab === 'vistas' && (
                <VistaPermisosView />
            )}

            {/* ============ MODALES ============ */}
            {modalCrearUsuario && (
                <ModalCrearUsuario
                    onClose={() => setModalCrearUsuario(false)}
                    onExito={() => { setModalCrearUsuario(false); setExito('Usuario creado exitosamente'); cargarUsuarios(); }}
                />
            )}
            {/* COM-26: edición de usuario con precarga de membresías y alcance */}
            {editarUsuarioId && (
                <ModalEditarUsuario
                    usuarioId={editarUsuarioId}
                    onClose={() => setEditarUsuarioId(null)}
                    onExito={() => { setEditarUsuarioId(null); setExito('Usuario actualizado exitosamente'); cargarUsuarios(); }}
                />
            )}
            {modalMuni && (
                <ModalMunicipalidad
                    municipalidad={modalMuni.editar || null}
                    onClose={() => setModalMuni(null)}
                    onExito={() => { setModalMuni(null); setExito('Municipalidad guardada exitosamente'); cargarMunicipalidades(); }}
                />
            )}
            {modalPrivilegios && (
                <ModalGrupoPrivilegios
                    grupo={modalPrivilegios}
                    privilegios={[]}
                    onClose={() => setModalPrivilegios(null)}
                    onExito={() => { setModalPrivilegios(null); setExito('Privilegios actualizados exitosamente'); }}
                />
            )}
            <ModalConfirmacion
                isOpen={!!confCuenta}
                onClose={() => setConfCuenta(null)}
                onConfirm={confirmarCuenta}
                mensaje={confCuenta
                    ? `¿${confCuenta.activar ? 'Desbloquear' : 'Bloquear'} la cuenta de ${confCuenta.objetivo.nombres} ${confCuenta.objetivo.apellido_paterno}?`
                    : ''}
                tipo="warning"
            />
            <ModalConfirmacion
                isOpen={!!confDesbloqueo}
                onClose={() => setConfDesbloqueo(null)}
                onConfirm={confirmarDesbloqueoReintentos}
                mensaje={confDesbloqueo
                    ? `¿Restablecer el bloqueo por intentos fallidos de ${confDesbloqueo.nombres} ${confDesbloqueo.apellido_paterno}? Se reiniciará su contador de intentos.`
                    : ''}
                tipo="warning"
            />
            {/* COM-38: modal de reseteo/cambio de contraseña (Admin de Sistemas) */}
            <ModalResetClave
                isOpen={!!resetUsuario}
                onClose={() => { setResetUsuario(null); cargarUsuarios(); }}
                usuarioObjetivo={resetUsuario}
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};