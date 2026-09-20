/**
 * components/auth/SeleccionComedorView.jsx
 * Objetivo: COM-20: pantalla de selección de comedor post-login (antes del dashboard).
 *           Dropdowns cascada departamento → ciudad → distrito → nombre del comedor,
 *           mostrando SOLO opciones activas del usuario; si un dropdown tiene una sola
 *           opción se muestra bloqueada; perfiles SISTEMA (sin selección) y
 *           ADMINISTRATIVO (solo 3 dropdowns, sin nombre de comedor).
 * Uso: Renderizado por App.jsx cuando hay sesión pero aún no hay selección de comedor.
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { MapPin, Building2, Loader2, AlertCircle, ArrowRight, LogOut } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// Mensaje exacto requerido por COM-20 cuando el usuario no tiene comedores activos
const MSG_SIN_COMEDOR = 'No perteneces a ningún comedor, consulta con las personas encargadas para que seas asignado a tu comedor.';

export const SeleccionComedorView = () => {
    const { usuario, establecerSeleccion, cerrarSesion } = useAuth();

    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [contexto, setContexto] = useState(null);   // { perfil, membresias_activas, alcance_global }
    const [fuente, setFuente] = useState([]);         // filas que alimentan los dropdowns
    const [sinComedores, setSinComedores] = useState(false);

    // Selecciones cascada
    const [selDep, setSelDep] = useState('');
    const [selCiu, setSelCiu] = useState('');
    const [selDis, setSelDis] = useState('');
    const [selCom, setSelCom] = useState('');

    const autoAplicado = useRef(false); // evita re-ejecuciones del auto-continuar

    const esComedor = contexto?.perfil === 'COMEDOR';
    const esAdmin = contexto?.perfil === 'ADMINISTRATIVO';

    // Carga el contexto de selección al montar
    useEffect(() => {
        const cargar = async () => {
            setCargando(true);
            setError('');
            try {
                const ctx = await api.getContextoSeleccion(usuario.id);
                setContexto(ctx);

                // COM-20: administradores de sistema no seleccionan comedor
                if (ctx.perfil === 'SISTEMA') {
                    establecerSeleccion({
                        perfil: 'SISTEMA',
                        comedor_id: null,
                        comedor_nombre: 'Administración del Sistema',
                        departamento: null, ciudad: null, distrito: null,
                        rol_comedor: null
                    });
                    return;
                }

                let filas = ctx.membresias_activas || [];
                // Administrativo con alcance global: todos los comedores son opciones
                if (ctx.perfil === 'ADMINISTRATIVO' && ctx.alcance_global) {
                    filas = await api.getComedores();
                }
                if (!filas || filas.length === 0) {
                    setSinComedores(true);
                    setFuente([]);
                    return;
                }
                setFuente(filas);
            } catch (e) {
                setError(e.message || 'Error al cargar sus comedores disponibles.');
            } finally {
                setCargando(false);
            }
        };
        cargar();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Opciones únicas por nivel (cascada)
    const departamentos = useMemo(() => [...new Set(fuente.map(f => f.departamento))].sort(), [fuente]);
    const ciudades = useMemo(() => [...new Set(fuente.filter(f => f.departamento === selDep).map(f => f.ciudad))].sort(), [fuente, selDep]);
    const distritos = useMemo(() => [...new Set(fuente.filter(f => f.departamento === selDep && f.ciudad === selCiu).map(f => f.distrito))].sort(), [fuente, selDep, selCiu]);
    const comedores = useMemo(() => {
        const filas = fuente.filter(f => f.departamento === selDep && f.ciudad === selCiu && f.distrito === selDis);
        const mapa = new Map(filas.map(f => [f.nombre, f]));
        return [...mapa.values()].sort((a, b) => a.nombre.localeCompare(b.nombre));
    }, [fuente, selDep, selCiu, selDis]);

    // Auto-ajuste de selecciones cuando cambian las opciones (opción única => bloqueada)
    useEffect(() => {
        if (!fuente.length) return;
        if (!departamentos.includes(selDep)) setSelDep(departamentos.length === 1 ? departamentos[0] : '');
    }, [departamentos, fuente, selDep]);
    useEffect(() => {
        if (!selDep) { setSelCiu(''); return; }
        if (!ciudades.includes(selCiu)) setSelCiu(ciudades.length === 1 ? ciudades[0] : '');
    }, [ciudades, selDep, selCiu]);
    useEffect(() => {
        if (!selCiu) { setSelDis(''); return; }
        if (!distritos.includes(selDis)) setSelDis(distritos.length === 1 ? distritos[0] : '');
    }, [distritos, selCiu, selDis]);
    useEffect(() => {
        if (!selDis) { setSelCom(''); return; }
        if (!comedores.some(c => c.nombre === selCom)) setSelCom(comedores.length === 1 ? comedores[0].nombre : '');
    }, [comedores, selDis, selCom]);

    // COM-20: un solo comedor (o una sola ubicación) => continuar automáticamente
    useEffect(() => {
        if (autoAplicado.current || cargando || sinComedores || !contexto) return;
        if (esComedor && fuente.length === 1) {
            autoAplicado.current = true;
            const f = fuente[0];
            establecerSeleccion({
                perfil: 'COMEDOR',
                comedor_id: f.comedor_id,
                comedor_nombre: f.nombre,
                departamento: f.departamento,
                ciudad: f.ciudad,
                distrito: f.distrito,
                rol_comedor: f.rol_comedor || null
            });
        } else if (esAdmin) {
            const combos = [...new Set(fuente.map(f => `${f.departamento}|${f.ciudad}|${f.distrito}`))];
            if (combos.length === 1) {
                autoAplicado.current = true;
                const f = fuente[0];
                establecerSeleccion({
                    perfil: 'ADMINISTRATIVO',
                    comedor_id: null,
                    comedor_nombre: null,
                    departamento: f.departamento,
                    ciudad: f.ciudad,
                    distrito: f.distrito,
                    rol_comedor: null
                });
            }
        }
    }, [cargando, sinComedores, contexto, fuente, esComedor, esAdmin, establecerSeleccion]);

    // Persiste la selección elegida y entra al dashboard
    const continuar = () => {
        if (esComedor) {
            const f = comedores.find(c => c.nombre === selCom);
            if (!f) return;
            establecerSeleccion({
                perfil: 'COMEDOR',
                comedor_id: f.comedor_id,
                comedor_nombre: f.nombre,
                departamento: f.departamento,
                ciudad: f.ciudad,
                distrito: f.distrito,
                rol_comedor: f.rol_comedor || null
            });
        } else if (esAdmin) {
            establecerSeleccion({
                perfil: 'ADMINISTRATIVO',
                comedor_id: null,
                comedor_nombre: null,
                departamento: selDep,
                ciudad: selCiu,
                distrito: selDis,
                rol_comedor: null
            });
        }
    };

    const puedeContinuar = esComedor ? !!selCom : (esAdmin ? !!selDis : false);

    // Select reutilizable con bloqueo automático cuando hay opción única (COM-20)
    const renderSelect = (valor, setValor, opciones, placeholder, bloqueado) => (
        <select
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            disabled={bloqueado}
            className={`w-full px-4 py-2.5 border rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm ${
                bloqueado ? 'bg-slate-100 text-slate-500 cursor-not-allowed border-slate-200' : 'bg-white border-slate-300'
            }`}
        >
            <option value="">{placeholder}</option>
            {opciones.map(op => (
                <option key={op} value={op}>{op}</option>
            ))}
        </select>
    );

    if (cargando) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-emerald-700 to-emerald-900 flex items-center justify-center">
                <Loader2 className="animate-spin text-white" size={40} />
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-emerald-700 to-emerald-900 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
                {/* Encabezado */}
                <div className="bg-emerald-700 p-6 text-white text-center">
                    <Building2 size={36} className="mx-auto mb-2 text-emerald-200" />
                    <h2 className="text-xl font-bold">Selección de Comedor</h2>
                    <p className="text-emerald-100 text-sm mt-1">
                        Hola {usuario?.nombres}, indica a qué comedor ingresarás.
                    </p>
                </div>

                <div className="p-6 space-y-4">
                    {error && (
                        <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg flex items-center gap-2 text-sm">
                            <AlertCircle size={16} /> {error}
                        </div>
                    )}

                    {sinComedores ? (
                        /* COM-20: mensaje exacto cuando no hay membresías activas */
                        <div className="p-4 bg-amber-50 border border-amber-200 text-amber-800 rounded-lg text-sm text-center">
                            {MSG_SIN_COMEDOR}
                        </div>
                    ) : (
                        <>
                            <div>
                                <label className="block text-sm font-semibold text-slate-700 mb-1">Departamento</label>
                                {renderSelect(selDep, setSelDep, departamentos, 'Seleccionar...', departamentos.length === 1)}
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-slate-700 mb-1">Ciudad</label>
                                {renderSelect(selCiu, setSelCiu, ciudades, selDep ? 'Seleccionar...' : 'Seleccione departamento', ciudades.length === 1 && !!selDep)}
                            </div>
                            <div>
                                <label className="block text-sm font-semibold text-slate-700 mb-1">Distrito</label>
                                {renderSelect(selDis, setSelDis, distritos, selCiu ? 'Seleccionar...' : 'Seleccione ciudad', distritos.length === 1 && !!selCiu)}
                            </div>

                            {/* Nombre del comedor: solo perfil COMEDOR */}
                            {esComedor && (
                                <div>
                                    <label className="block text-sm font-semibold text-slate-700 mb-1">Nombre del Comedor</label>
                                    <select
                                        value={selCom}
                                        onChange={(e) => setSelCom(e.target.value)}
                                        disabled={comedores.length === 1 && !!selDis}
                                        className={`w-full px-4 py-2.5 border rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm ${
                                            comedores.length === 1 && !!selDis ? 'bg-slate-100 text-slate-500 cursor-not-allowed border-slate-200' : 'bg-white border-slate-300'
                                        }`}
                                    >
                                        <option value="">{selDis ? 'Seleccionar...' : 'Seleccione distrito'}</option>
                                        {comedores.map(c => (
                                            <option key={c.comedor_id} value={c.nombre}>{c.nombre}</option>
                                        ))}
                                    </select>
                                </div>
                            )}

                            {/* Nota de alcance para perfil municipal */}
                            {esAdmin && (
                                <p className="text-xs text-slate-500 flex items-center gap-1">
                                    <MapPin size={12} /> Perfil municipal: su alcance queda definido por departamento, ciudad y distrito.
                                </p>
                            )}
                        </>
                    )}

                    {/* Botones Cancelar / Siguiente (COM-20) */}
                    <div className="flex gap-3 pt-2">
                        <button
                            onClick={() => cerrarSesion()}
                            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm font-medium"
                        >
                            <LogOut size={16} /> Cancelar
                        </button>
                        {!sinComedores && (
                            <button
                                onClick={continuar}
                                disabled={!puedeContinuar}
                                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                Siguiente <ArrowRight size={16} />
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};