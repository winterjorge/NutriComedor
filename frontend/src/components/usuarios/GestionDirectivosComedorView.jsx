/**
 * components/usuarios/GestionDirectivosComedorView.jsx
 * Objetivo: COM-39: panel del Administrador de Sistemas para gestionar la directiva de
 *           un comedor: cascada Departamento -> Provincia -> Distrito (con reset
 *           jerárquico: al cambiar un nivel superior se vacían los inferiores),
 *           búsqueda de comedores del distrito por nombre, tabla de directivos activos
 *           (documento, nombres y cargo) con COLA de cambios simultáneos (cambio de
 *           cargo con búsqueda/registro inmediato de persona vía ModalBuscarPersona,
 *           y baja de cargo), y aplicación transaccional del lote con mensaje de
 *           confirmación de los cambios de cargo al guardar.
 * Permisos: heredados del panel (solo Admin de Sistemas); el backend re-valida (403).
 * Uso: Montado en la sub-pestaña "Directivos de Comedor" de GestionUsuariosSistemaView.
 * Referencia: ticket COM-39 (solo trazabilidad).
 */
import React, { useState, useEffect } from 'react';
import {
    Store, Search, Loader2, AlertCircle, Save, Undo2,
    UserCog, UserMinus, MapPin
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalExito } from '../common/ModalExito';
import { ModalBuscarPersona } from './ModalBuscarPersona';

export const GestionDirectivosComedorView = () => {
    const { usuario } = useAuth();

    // ===== Cascada geográfica (COM-27) =====
    const [departamentos, setDepartamentos] = useState([]);
    const [provincias, setProvincias] = useState([]);
    const [distritos, setDistritos] = useState([]);
    const [selDep, setSelDep] = useState('');
    const [selProv, setSelProv] = useState('');
    const [selDist, setSelDist] = useState('');
    const [distNombre, setDistNombre] = useState('');

    // ===== Búsqueda de comedores del distrito =====
    const [qComedor, setQComedor] = useState('');
    const [resultadosComedores, setResultadosComedores] = useState([]);
    const [buscandoComedores, setBuscandoComedores] = useState(false);
    const [comedorSel, setComedorSel] = useState(null);

    // ===== Directivos y cola de cambios simultáneos =====
    const [directivos, setDirectivos] = useState([]);
    const [rolesVacantes, setRolesVacantes] = useState([]);
    const [cargandoDirectivos, setCargandoDirectivos] = useState(false);
    const [cola, setCola] = useState([]);              // operaciones pendientes
    const [modalBuscar, setModalBuscar] = useState(null); // { rol, origen }
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');

    // Carga inicial de departamentos
    useEffect(() => {
        api.getDepartamentos().then(setDepartamentos).catch(e => setError(e.message));
    }, []);

    // ---------- COM-39: reset jerárquico de la cascada ----------
    const onChangeDep = async (e) => {
        const id = e.target.value;
        setSelDep(id); setSelProv(''); setSelDist(''); setDistNombre('');
        setProvincias([]); setDistritos([]);
        setResultadosComedores([]); setComedorSel(null);
        setDirectivos([]); setRolesVacantes([]); setCola([]);
        if (id) {
            try { setProvincias(await api.getProvincias(id)); } catch (e) { setError(e.message); }
        }
    };
    const onChangeProv = async (e) => {
        const id = e.target.value;
        setSelProv(id); setSelDist(''); setDistNombre('');
        setDistritos([]);
        setResultadosComedores([]); setComedorSel(null);
        setDirectivos([]); setRolesVacantes([]); setCola([]);
        if (id) {
            try { setDistritos(await api.getDistritos(id)); } catch (e) { setError(e.message); }
        }
    };
    const onChangeDist = (e) => {
        const opt = e.target.selectedOptions[0];
        setSelDist(e.target.value);
        setDistNombre(opt ? opt.textContent.trim() : '');
        setResultadosComedores([]); setComedorSel(null);
        setDirectivos([]); setRolesVacantes([]); setCola([]);
    };

    // ---------- Búsqueda de comedores del distrito (debounce 400ms) ----------
    useEffect(() => {
        if (!distNombre) { setResultadosComedores([]); return; }
        const t = setTimeout(async () => {
            setBuscandoComedores(true);
            try {
                setResultadosComedores(await api.buscarComedoresPorDistrito(distNombre, qComedor, usuario.id));
            } catch (e) { setError(e.message); }
            finally { setBuscandoComedores(false); }
        }, 400);
        return () => clearTimeout(t);
    }, [qComedor, distNombre, usuario.id]);

    const seleccionarComedor = async (c) => {
        setComedorSel(c);
        setResultadosComedores([]);
        setQComedor('');
        setCola([]);
        setCargandoDirectivos(true);
        setError('');
        try {
            const data = await api.getDirectivosComedor(c.id, usuario.id);
            setDirectivos(data.directivos || []);
            setRolesVacantes(data.roles_vacantes || []);
        } catch (e) { setError(e.message); }
        finally { setCargandoDirectivos(false); }
    };

    // ---------- Cola de cambios ----------
    const abrirModalCambio = (d) => setModalBuscar({ rol: d.rol, origen: d });

    const stageBaja = (d) => {
        setCola(prev => [...prev.filter(op => op.rol_nombre !== d.rol), {
            operacion: 'baja',
            rol_nombre: d.rol,
            usuario_origen_id: d.usuario_id,
            membresia_id: d.membresia_id,
            origen_nombre: `${d.nombres} ${d.apellido_paterno}`,
            nuevo: null,
        }]);
    };

    const onPersonaSeleccionada = (payload) => {
        if (!modalBuscar) return;
        const d = modalBuscar.origen;
        setCola(prev => [...prev.filter(op => op.rol_nombre !== d.rol), {
            operacion: 'reemplazo',
            rol_nombre: d.rol,
            usuario_origen_id: d.usuario_id,
            membresia_id: d.membresia_id,
            origen_nombre: `${d.nombres} ${d.apellido_paterno}`,
            nuevo: payload,
        }]);
        setModalBuscar(null);
    };

    const quitarDeCola = (rol) => setCola(prev => prev.filter(op => op.rol_nombre !== rol));
    const opDeRol = (rol) => cola.find(op => op.rol_nombre === rol);

    const nombreDeNuevo = (op) => {
        if (!op.nuevo) return '';
        if (op.nuevo.tipo === 'existente') return op.nuevo.nombres;
        const nu = op.nuevo.nuevo_usuario || {};
        return `${nu.nombres || ''} ${nu.apellido_paterno || ''}`.trim() + ' (nuevo)';
    };

    // ---------- Guardado transaccional del lote ----------
    const guardarCambios = async () => {
        if (!comedorSel || cola.length === 0) return;
        setGuardando(true);
        setError('');
        try {
            const operaciones = cola.map(op => (op.operacion === 'baja' ? {
                operacion: 'baja',
                rol_nombre: op.rol_nombre,
                usuario_origen_id: op.usuario_origen_id,
                membresia_id: op.membresia_id,
            } : {
                operacion: 'reemplazo',
                rol_nombre: op.rol_nombre,
                usuario_origen_id: op.usuario_origen_id,
                membresia_id: op.membresia_id,
                usuario_nuevo_id: op.nuevo && op.nuevo.tipo === 'existente' ? op.nuevo.usuario_id : undefined,
                nuevo_usuario: op.nuevo && op.nuevo.tipo === 'nuevo' ? op.nuevo.nuevo_usuario : undefined,
            }));
            const res = await api.actualizarDirectivos(comedorSel.id, {
                usuario_solicitante_id: usuario.id,
                operaciones,
            });
            setExito(res.message);   // COM-39: confirmación de los cambios de cargo
            setCola([]);
            const data = await api.getDirectivosComedor(comedorSel.id, usuario.id);
            setDirectivos(data.directivos || []);
            setRolesVacantes(data.roles_vacantes || []);
        } catch (e) {
            setError(e.message);
        } finally {
            setGuardando(false);
        }
    };

    const selectCls = "px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500";

    return (
        <div className="space-y-5">
            {/* ===== Cascada geográfica + buscador de comedores ===== */}
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                <p className="flex items-center gap-1 text-xs font-bold text-slate-600 mb-3">
                    <MapPin size={13} /> Ubicación del comedor (cascada COM-27)
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                    <div>
                        <label className="text-[11px] font-semibold text-slate-600 block mb-1">Departamento</label>
                        <select value={selDep} onChange={onChangeDep} className={`${selectCls} w-full`}>
                            <option value="">Seleccionar...</option>
                            {departamentos.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="text-[11px] font-semibold text-slate-600 block mb-1">Provincia</label>
                        <select value={selProv} onChange={onChangeProv} disabled={!selDep} className={`${selectCls} w-full disabled:bg-slate-100`}>
                            <option value="">{selDep ? 'Seleccionar...' : 'Seleccione departamento'}</option>
                            {provincias.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="text-[11px] font-semibold text-slate-600 block mb-1">Distrito</label>
                        <select value={selDist} onChange={onChangeDist} disabled={!selProv} className={`${selectCls} w-full disabled:bg-slate-100`}>
                            <option value="">{selProv ? 'Seleccionar...' : 'Seleccione provincia'}</option>
                            {distritos.map(d => <option key={d.id} value={d.id}>{d.nombre}</option>)}
                        </select>
                    </div>
                </div>

                {/* Buscador de comedores del distrito */}
                <div className="relative">
                    <label className="text-[11px] font-semibold text-slate-600 block mb-1">
                        Nombre del comedor (busca dentro del distrito seleccionado)
                    </label>
                    <div className="relative">
                        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input
                            type="text"
                            value={qComedor}
                            onChange={(e) => setQComedor(e.target.value)}
                            disabled={!selDist}
                            placeholder={selDist ? 'Escriba el nombre del comedor...' : 'Seleccione primero el distrito'}
                            className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500 disabled:bg-slate-100"
                        />
                    </div>
                    {buscandoComedores && (
                        <div className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-lg p-3 text-center text-emerald-600">
                            <Loader2 className="animate-spin mx-auto" size={18} />
                        </div>
                    )}
                    {!buscandoComedores && resultadosComedores.length > 0 && (
                        <div className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                            {resultadosComedores.map(c => (
                                <button
                                    key={c.id}
                                    onClick={() => seleccionarComedor(c)}
                                    className="w-full text-left px-3 py-2 hover:bg-emerald-50 transition-colors flex items-center gap-2"
                                >
                                    <Store size={14} className="text-emerald-600 shrink-0" />
                                    <span className="text-sm text-slate-700 font-medium">{c.nombre}</span>
                                    <span className="ml-auto text-[10px] text-slate-400">{c.distrito}</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* ===== Comedor seleccionado: directivos y cola ===== */}
            {comedorSel && (
                <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2">
                        <Store size={16} className="text-emerald-600" />
                        <p className="font-bold text-slate-800 text-sm">{comedorSel.nombre}</p>
                        {rolesVacantes.length > 0 && (
                            <span className="ml-2 flex flex-wrap gap-1">
                                {rolesVacantes.map(r => (
                                    <span key={r} className="px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full text-[10px] font-bold">
                                        {r} vacante
                                    </span>
                                ))}
                            </span>
                        )}
                    </div>

                    {/* Tabla de directivos */}
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-3 font-semibold">Documento</th>
                                    <th className="p-3 font-semibold">Nombres</th>
                                    <th className="p-3 font-semibold">Cargo</th>
                                    <th className="p-3 font-semibold">Cambio en cola</th>
                                    <th className="p-3 font-semibold text-right">Acciones</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {cargandoDirectivos ? (
                                    <tr><td colSpan="5" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                                ) : directivos.length === 0 ? (
                                    <tr><td colSpan="5" className="p-8 text-center text-slate-500">El comedor no tiene directivos activos.</td></tr>
                                ) : directivos.map(d => {
                                    const op = opDeRol(d.rol);
                                    return (
                                        <tr key={d.membresia_id} className="hover:bg-slate-50">
                                            <td className="p-3 font-medium text-slate-800">{d.tipo_documento} {d.documento_identidad}</td>
                                            <td className="p-3 text-slate-700">{d.nombres} {d.apellido_paterno} {d.apellido_materno || ''}</td>
                                            <td className="p-3">
                                                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-bold">{d.rol}</span>
                                            </td>
                                            <td className="p-3">
                                                {op ? (
                                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                                        op.operacion === 'baja' ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'}`}>
                                                        {op.operacion === 'baja' ? 'Baja pendiente' : `→ ${nombreDeNuevo(op)}`}
                                                    </span>
                                                ) : (
                                                    <span className="text-[11px] text-slate-400">—</span>
                                                )}
                                            </td>
                                            <td className="p-3">
                                                <div className="flex justify-end gap-2">
                                                    {op ? (
                                                        <button
                                                            onClick={() => quitarDeCola(d.rol)}
                                                            title="Deshacer cambio en cola"
                                                            className="p-1.5 bg-slate-100 text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
                                                        >
                                                            <Undo2 size={15} />
                                                        </button>
                                                    ) : (
                                                        <>
                                                            <button
                                                                onClick={() => abrirModalCambio(d)}
                                                                title="Cambio de cargo (buscar o registrar persona)"
                                                                className="p-1.5 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 rounded-lg transition-colors"
                                                            >
                                                                <UserCog size={15} />
                                                            </button>
                                                            <button
                                                                onClick={() => stageBaja(d)}
                                                                title="Baja de cargo"
                                                                className="p-1.5 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors"
                                                            >
                                                                <UserMinus size={15} />
                                                            </button>
                                                        </>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* Barra de guardado del lote */}
                    <div className="flex flex-wrap items-center gap-3">
                        <p className="text-xs text-slate-600">
                            Cambios en cola: <b>{cola.length}</b>
                            {cola.length > 0 && ` (${cola.map(op => `${op.rol_nombre}: ${op.operacion}`).join(', ')})`}
                        </p>
                        <div className="ml-auto flex gap-2">
                            {cola.length > 0 && (
                                <button
                                    onClick={() => setCola([])}
                                    className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors"
                                >
                                    Descartar todo
                                </button>
                            )}
                            <button
                                onClick={guardarCambios}
                                disabled={cola.length === 0 || guardando}
                                className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                            >
                                {guardando ? <Loader2 className="animate-spin" size={16} /> : <Save size={16} />}
                                Guardar cambios ({cola.length})
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ===== Modales ===== */}
            <ModalBuscarPersona
                isOpen={!!modalBuscar}
                onClose={() => setModalBuscar(null)}
                onSeleccionar={onPersonaSeleccionada}
                titulo={modalBuscar ? `Nuevo titular de ${modalBuscar.rol}` : ''}
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};