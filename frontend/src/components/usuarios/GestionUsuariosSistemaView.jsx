/**
 * components/usuarios/GestionUsuariosSistemaView.jsx
 * Objetivo: Panel del administrador de sistemas: usuarios y bloqueos (creación con
 *           formulario dinámico por perfil y edición con precarga de membresías según
 *           la corrección COM-26), municipalidades, grupos y privilegios, política de
 *           contraseñas, editor de permisos por vistas y, desde COM-39, gestión de
 *           directivos por comedor. Las sub-pestañas visibles se filtran según los
 *           módulos permitidos del usuario en sesión.
 * Uso: Renderizado por App.jsx en la pestaña "Usuarios" cuando el usuario posee al
 *      menos uno de los módulos de administración; recibe `modulosPermitidos`.
 * Historial:
 *  - COM-23/COM-25/COM-26: versión original (sub-pestañas, payloads con
 *    usuario_solicitante_id, estado_activo y claves de política).
 *  - COM-38: botón "Resetear contraseña" por fila de usuario y montaje de ModalResetClave.
 *  - COM-39 (este archivo): se AGREGA la sub-pestaña "Directivos de Comedor"
 *    (módulo 'comedores') que monta GestionDirectivosComedorView. Nada existente se
 *    elimina: solo adiciones marcadas COM-39 (import del icono Store, import de la
 *    vista, entrada en SUBTABS y bloque de render).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Users, Building2, ShieldCheck, KeyRound, Plus, Lock, Unlock,
    RefreshCw, Loader2, AlertCircle, Edit3, Eye,
    Store // COM-39: ícono de la sub-pestaña "Directivos de Comedor"
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
// COM-39: panel de gestión de directivos por comedor
import { GestionDirectivosComedorView } from './GestionDirectivosComedorView';

// Sub-pestañas con su módulo requerido (matriz de permisos por rol)
const SUBTABS = [
    { id: 'usuarios', label: 'Usuarios y Bloqueos', icon: Users, modulo: 'bloqueos' },
    // COM-39: gestión de directivos por comedor (exclusiva del Admin de Sistemas)
    { id: 'directivos', label: 'Directivos de Comedor', icon: Store, modulo: 'comedores' },
    { id: 'municipalidades', label: 'Municipalidades', icon: Building2, modulo: 'municipalidades' },
    { id: 'grupos', label: 'Grupos y Privilegios', icon: ShieldCheck, modulo: 'roles' },
    { id: 'politica', label: 'Política de Claves', icon: KeyRound, modulo: 'bloqueos' },
    { id: 'vistas', label: 'Vistas', icon: Eye, modulo: 'vistas' },
];

export const GestionUsuariosSistemaView = ({ modulosPermitidos = [] }) => {
    const { usuario } = useAuth();

    // Sub-pestañas visibles según los módulos permitidos del usuario en sesión
    const subtabsVisibles = SUBTABS.filter(s => modulosPermitidos.includes(s.modulo));
    const [subtab, setSubtab] = useState(subtabsVisibles[0]?.id || '');

    // Ajusta la sub-pestaña activa si cambian los permisos del usuario
    useEffect(() => {
        if (!subtabsVisibles.some(s => s.id === subtab)) {
            setSubtab(subtabsVisibles[0]?.id || '');
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [modulosPermitidos]);

    // ===== Estado: Usuarios =====
    const [usuarios, setUsuarios] = useState([]);
    const [q, setQ] = useState('');
    const [estado, setEstado] = useState('');
    const [cargandoUsuarios, setCargandoUsuarios] = useState(true);
    const [modalCrearUsuario, setModalCrearUsuario] = useState(false);
    const [editarUsuarioId, setEditarUsuarioId] = useState(null); // COM-26: edición con precarga
    const [confCuenta, setConfCuenta] = useState(null);        // { objetivo, activar }
    const [confDesbloqueo, setConfDesbloqueo] = useState(null); // objetivo
    // COM-38: usuario objetivo del modal de reseteo de contraseña
    const [resetUsuario, setResetUsuario] = useState(null);

    // ===== Estado: Municipalidades =====
    const [municipalidades, setMunicipalidades] = useState([]);
    const [cargandoMunis, setCargandoMunis] = useState(false);
    const [modalMuni, setModalMuni] = useState(null); // null | { crear: true } | { editar: muni }

    // ===== Estado: Grupos y privilegios =====
    const [grupos, setGrupos] = useState([]);
    const [privilegios, setPrivilegios] = useState([]);
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
        setError('');
        try {
            const params = { usuario_solicitante_id: usuario.id };
            if (q) params.q = q;
            if (estado) params.estado = estado;
            setUsuarios(await api.getUsuarios(params));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoUsuarios(false);
        }
    }, [q, estado, usuario.id]);

    const cargarMunicipalidades = useCallback(async () => {
        setCargandoMunis(true);
        setError('');
        try {
            setMunicipalidades(await api.getMunicipalidades());
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoMunis(false);
        }
    }, []);

    const cargarGrupos = useCallback(async () => {
        setCargandoGrupos(true);
        setError('');
        try {
            const [g, p] = await Promise.all([api.getGrupos(), api.getPrivilegios()]);
            setGrupos(g);
            setPrivilegios(p);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoGrupos(false);
        }
    }, []);

    const cargarPolitica = useCallback(async () => {
        setError('');
        try {
            setPolitica(await api.getPoliticaClave());
        } catch (e) {
            setError(e.message);
        }
    }, []);

    // Carga según sub-pestaña activa
    useEffect(() => {
        if (subtab === 'usuarios') cargarUsuarios();
        if (subtab === 'municipalidades') cargarMunicipalidades();
        if (subtab === 'grupos') cargarGrupos();
        if (subtab === 'politica') cargarPolitica();
    }, [subtab, cargarUsuarios, cargarMunicipalidades, cargarGrupos, cargarPolitica]);

    // ---------- Acciones: Usuarios ----------
    const confirmarEstadoCuenta = async () => {
        const { objetivo, activar } = confCuenta;
        setConfCuenta(null);
        try {
            await api.cambiarEstadoCuenta(objetivo.id, {
                estado_activo: activar,
                usuario_solicitante_id: usuario.id
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

    // ---------- Acciones: Grupos ----------
    const crearGrupo = async (e) => {
        e.preventDefault();
        setCreandoGrupo(true);
        setError('');
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

    // ---------- Acciones: Política ----------
    const guardarPolitica = async (e) => {
        e.preventDefault();
        setGuardandoPolitica(true);
        setError('');
        try {
            await api.updatePoliticaClave({
                longitud_min: Number(politica.longitud_min),
                longitud_max: Number(politica.longitud_max),
                meses_expiracion: Number(politica.meses_expiracion),
                max_intentos: Number(politica.max_intentos),
                usuario_solicitante_id: usuario.id
            });
            setExito('Política de contraseñas actualizada exitosamente');
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardandoPolitica(false);
        }
    };

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado y sub-pestañas (solo las permitidas por la matriz de módulos) */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <ShieldCheck className="text-emerald-600" size={22} /> Gestión de Usuarios y Configuración
                    </h2>
                    <p className="text-sm text-slate-500">Administración global: usuarios, directivos, municipalidades, grupos y política de claves.</p>
                </div>
            </div>

            <div className="flex gap-2 mb-5 border-b border-slate-200 pb-2 overflow-x-auto">
                {subtabsVisibles.map(t => {
                    const Icon = t.icon;
                    const activa = subtab === t.id;
                    return (
                        <button
                            key={t.id}
                            onClick={() => setSubtab(t.id)}
                            className={`flex shrink-0 items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
                                activa ? 'bg-emerald-600 text-white' : 'text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            <Icon size={16} /> {t.label}
                        </button>
                    );
                })}
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
                            className="px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm"
                        >
                            <option value="">Todos los estados</option>
                            <option value="activos">Cuentas activas</option>
                            <option value="inactivos">Cuentas bloqueadas</option>
                        </select>
                        <button
                            onClick={() => setModalCrearUsuario(true)}
                            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Plus size={16} /> Nuevo Usuario
                        </button>
                    </div>

                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-3 font-semibold">Documento</th>
                                    <th className="p-3 font-semibold">Nombres</th>
                                    <th className="p-3 font-semibold">Rol global</th>
                                    <th className="p-3 font-semibold text-center">Cuenta</th>
                                    <th className="p-3 font-semibold text-center">Bloqueo intentos</th>
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
                                        <td className="p-3 text-slate-700">{u.nombres} {u.apellido_paterno} {u.apellido_materno}</td>
                                        <td className="p-3 text-slate-600">{u.rol}</td>
                                        <td className="p-3 text-center">
                                            <span className={`px-2 py-1 rounded-full text-xs font-bold ${u.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
                                                {u.estado_activo ? 'Activa' : 'Bloqueada'}
                                            </span>
                                        </td>
                                        <td className="p-3 text-center">
                                            <span className={`px-2 py-1 rounded-full text-xs font-bold ${u.bloqueado ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
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
                                                    className={`p-1.5 rounded-lg transition-colors ${u.estado_activo ? 'bg-red-50 text-red-600 hover:bg-red-100' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'}`}
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

            {/* ============ SUB-PESTAÑA: DIRECTIVOS DE COMEDOR (COM-39) ============ */}
            {subtab === 'directivos' && (
                <GestionDirectivosComedorView />
            )}

            {/* ============ SUB-PESTAÑA: MUNICIPALIDADES ============ */}
            {subtab === 'municipalidades' && (
                <div>
                    <div className="flex justify-end mb-4">
                        <button
                            onClick={() => setModalMuni({ crear: true })}
                            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                        >
                            <Plus size={16} /> Nueva Municipalidad
                        </button>
                    </div>
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-3 font-semibold">Nombre</th>
                                    <th className="p-3 font-semibold">Ubicación</th>
                                    <th className="p-3 font-semibold">Dirección</th>
                                    <th className="p-3 font-semibold text-right">Acciones</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {cargandoMunis ? (
                                    <tr><td colSpan="4" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                                ) : municipalidades.length === 0 ? (
                                    <tr><td colSpan="4" className="p-8 text-center text-slate-500">Aún no hay municipalidades registradas.</td></tr>
                                ) : municipalidades.map(m => (
                                    <tr key={m.id} className="hover:bg-slate-50">
                                        <td className="p-3 font-medium text-slate-800">{m.nombre}</td>
                                        <td className="p-3 text-slate-600">{m.distrito}, {m.provincia} — {m.departamento}</td>
                                        <td className="p-3 text-slate-600 max-w-[240px] truncate">{m.direccion || '—'}</td>
                                        <td className="p-3 text-right">
                                            <button
                                                onClick={() => setModalMuni({ editar: m })}
                                                className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                                title="Editar municipalidad"
                                            >
                                                <Edit3 size={15} />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ============ SUB-PESTAÑA: GRUPOS Y PRIVILEGIOS (roles) ============ */}
            {subtab === 'grupos' && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                    {/* Formulario de creación de grupo */}
                    <form onSubmit={crearGrupo} className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3 h-fit">
                        <h3 className="font-bold text-slate-700 flex items-center gap-2"><Plus size={16} /> Crear grupo</h3>
                        <input
                            type="text"
                            value={nuevoGrupo.nombre}
                            onChange={(e) => setNuevoGrupo({ ...nuevoGrupo, nombre: e.target.value })}
                            placeholder="Nombre del grupo"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                            required
                        />
                        <select
                            value={nuevoGrupo.ambito}
                            onChange={(e) => setNuevoGrupo({ ...nuevoGrupo, ambito: e.target.value })}
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm"
                        >
                            <option value="SISTEMA">Ámbito SISTEMA</option>
                            <option value="GLOBAL">Ámbito GLOBAL (municipal)</option>
                            <option value="COMEDOR">Ámbito COMEDOR</option>
                        </select>
                        <textarea
                            value={nuevoGrupo.descripcion}
                            onChange={(e) => setNuevoGrupo({ ...nuevoGrupo, descripcion: e.target.value })}
                            placeholder="Descripción"
                            rows="2"
                            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                        <button
                            type="submit"
                            disabled={creandoGrupo}
                            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                            {creandoGrupo ? 'Creando...' : 'Crear grupo'}
                        </button>
                    </form>
                    {/* Listado de grupos con privilegios */}
                    <div className="lg:col-span-2 space-y-3">
                        {cargandoGrupos ? (
                            <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></div>
                        ) : grupos.map(g => (
                            <div key={g.id} className="border border-slate-200 rounded-xl p-4 bg-white">
                                <div className="flex flex-wrap justify-between items-center gap-2 mb-2">
                                    <div>
                                        <p className="font-bold text-slate-800">{g.nombre}</p>
                                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                            g.ambito === 'SISTEMA' ? 'bg-purple-100 text-purple-700'
                                            : g.ambito === 'GLOBAL' ? 'bg-blue-100 text-blue-700'
                                            : 'bg-emerald-100 text-emerald-700'
                                        }`}>{g.ambito}</span>
                                    </div>
                                    <button
                                        onClick={() => setModalPrivilegios(g)}
                                        className="flex items-center gap-1 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                                    >
                                        <ShieldCheck size={14} /> Privilegios
                                    </button>
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                    {privilegios.filter(p => (p.grupos || []).includes(g.nombre)).length === 0 ? (
                                        <span className="text-xs text-slate-400">Sin privilegios asignados.</span>
                                    ) : privilegios.filter(p => (p.grupos || []).includes(g.nombre)).map(p => (
                                        <span key={p.id} className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-[10px] font-medium">
                                            {p.nombre}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ============ SUB-PESTAÑA: POLÍTICA DE CLAVES (bloqueos) ============ */}
            {subtab === 'politica' && politica && (
                <form onSubmit={guardarPolitica} className="max-w-md bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
                    <h3 className="font-bold text-slate-700 flex items-center gap-2"><KeyRound size={16} /> Política de contraseñas</h3>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Longitud mínima</label>
                            <input type="number" min="6" max="32" value={politica.longitud_min}
                                onChange={(e) => setPolitica({ ...politica, longitud_min: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Longitud máxima</label>
                            <input type="number" min="8" max="64" value={politica.longitud_max}
                                onChange={(e) => setPolitica({ ...politica, longitud_max: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Meses de expiración</label>
                            <input type="number" min="1" max="60" value={politica.meses_expiracion}
                                onChange={(e) => setPolitica({ ...politica, meses_expiracion: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Intentos máximos</label>
                            <input type="number" min="1" max="10" value={politica.max_intentos}
                                onChange={(e) => setPolitica({ ...politica, max_intentos: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                    </div>
                    <button
                        type="submit"
                        disabled={guardandoPolitica}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        {guardandoPolitica ? 'Guardando...' : 'Guardar política'}
                    </button>
                </form>
            )}

            {/* ============ SUB-PESTAÑA: VISTAS (editor de permisos por rol) ============ */}
            {subtab === 'vistas' && <VistaPermisosView />}

            {/* ===== Modales y confirmaciones ===== */}
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
                    privilegios={privilegios}
                    onClose={() => setModalPrivilegios(null)}
                    onExito={() => { setModalPrivilegios(null); setExito('Privilegios actualizados exitosamente'); cargarGrupos(); }}
                />
            )}
            <ModalConfirmacion
                isOpen={!!confCuenta}
                onClose={() => setConfCuenta(null)}
                onConfirm={confirmarEstadoCuenta}
                mensaje={confCuenta
                    ? `¿${confCuenta.activar ? 'Desbloquear' : 'Bloquear'} la cuenta de ${confCuenta.objetivo.nombres} ${confCuenta.objetivo.apellido_paterno} (${confCuenta.objetivo.documento_identidad})? ${confCuenta.activar ? '' : 'El usuario no podrá iniciar sesión.'}`
                    : ''}
                tipo={confCuenta?.activar ? 'warning' : 'danger'}
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