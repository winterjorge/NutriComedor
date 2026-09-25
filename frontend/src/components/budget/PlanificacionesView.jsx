/**
 * components/budget/PlanificacionesView.jsx
 * Objetivo: Vista de Planificaciones semanales (menús definitivos del comedor). Lista
 *           las planificaciones vigentes/reemplazadas y, al expandirlas, muestra:
 *           (1) tarjetas de resumen con Costo total semanal, Recolección semanal,
 *               MARGEN (ventas - compras) y Kcal promedio/día al mismo nivel visual;
 *           (2) el bloque de comensales en 3 columnas grandes separadas
 *               (Social / Afiliado / Normal) más el total;
 *           (3) el detalle POR DÍA con la RECOLECCIÓN PROYECTADA de cada jornada;
 *           (4) la lista de compras consolidada de la semana.
 * Historial:
 *  - Sprint 2: versión inicial (listado y detalle de planificaciones).
 *  - COM-8 v2: reconstruida sobre /propuestas/historial y /propuestas/historial/{id}/dias
 *              (tablas presupuesto_semanal + planificacion_dia del Sprint 2, ahora
 *              vinculadas al comedor y a la candidata elegida). Se agregan recolección
 *              por día, comensales en 3 columnas grandes y margen como tarjeta.
 *              Las kcal/día se obtienen del resumen de la candidata COM-8 (sesión);
 *              en planificaciones legacy sin candidata se muestra "—".
 * Permisos: módulo 'planificaciones' (Directivo y Operativo del comedor, COM-25/COM-8).
 * Uso: Montada por App.jsx en la pestaña "Planificaciones".
 * Referencia: tickets COM-8 / HU-09 (solo trazabilidad; los nombres obedecen a la funcionalidad).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    ClipboardList, Loader2, AlertCircle, ChevronDown, ChevronUp,
    Wallet, Coins, TrendingUp, Flame, Users, ShoppingCart, History
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const PlanificacionesView = () => {
    const { usuario, seleccion } = useAuth();
    const comedorId = seleccion?.comedor_id;

    const [planificaciones, setPlanificaciones] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');

    // Caché por planificación expandida: { id: { dias, resumen, menu } }
    const [expandidos, setExpandidos] = useState({});
    const [cache, setCache] = useState({});
    const [cargandoDetalle, setCargandoDetalle] = useState({});

    // Lista de compras: { id: filas } y { id: bool cargando }
    const [compras, setCompras] = useState({});
    const [cargandoCompras, setCargandoCompras] = useState({});
    const [mostrarCompras, setMostrarCompras] = useState({});

    // ---------- Carga del listado ----------
    const cargar = useCallback(async () => {
        if (!comedorId) return;
        setCargando(true);
        setError('');
        try {
            setPlanificaciones(await api.getHistorialPropuestas(comedorId, usuario.id));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [comedorId, usuario.id]);

    useEffect(() => { cargar(); }, [cargar]);

    // ---------- Expansión: días + resumen de la candidata ----------
    const toggleExpandir = async (plan) => {
        if (expandidos[plan.id]) {
            setExpandidos({ ...expandidos, [plan.id]: false });
            return;
        }
        setExpandidos({ ...expandidos, [plan.id]: true });
        if (cache[plan.id]) return; // ya cargado previamente
        setCargandoDetalle({ ...cargandoDetalle, [plan.id]: true });
        try {
            const dias = await api.getHistorialDias(plan.id, usuario.id);
            let resumen = null;
            let menu = null;
            if (plan.sesion_id) {
                try {
                    const sesion = await api.getSesionPropuestas(plan.sesion_id, usuario.id);
                    const prop = (sesion.propuestas || []).find(p => p.variante === plan.variante);
                    if (prop) {
                        resumen = prop.resumen;
                        menu = prop.menu;
                    }
                } catch (e) {
                    /* sesión purgada o legacy: las kcal se muestran como "—" */
                }
            }
            setCache(prev => ({ ...prev, [plan.id]: { dias, resumen, menu } }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoDetalle({ ...cargandoDetalle, [plan.id]: false });
        }
    };

    // ---------- Lista de compras ----------
    const toggleCompras = async (plan) => {
        if (mostrarCompras[plan.id]) {
            setMostrarCompras({ ...mostrarCompras, [plan.id]: false });
            return;
        }
        setMostrarCompras({ ...mostrarCompras, [plan.id]: true });
        if (compras[plan.id]) return;
        setCargandoCompras({ ...cargandoCompras, [plan.id]: true });
        try {
            const data = await api.getListaCompras(plan.id);
            const filas = Array.isArray(data) ? data : (data.items || data.grupos || []);
            setCompras(prev => ({ ...prev, [plan.id]: filas }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoCompras({ ...cargandoCompras, [plan.id]: false });
        }
    };

    // ---------- Helpers de render ----------
    const margenDe = (p) => {
        if (p.margen !== null && p.margen !== undefined) return Number(p.margen);
        return Number(p.recoleccion_total_proyectada || 0) - Number(p.costo_total_semana || 0);
    };

    const tarjeta = (icono, valor, etiqueta, colorExtra = 'text-slate-800') => (
        <div className="bg-slate-50 rounded-lg py-2 px-3 text-center">
            <p className={`flex items-center justify-center gap-1 text-sm font-bold ${colorExtra}`}>
                {icono} {valor}
            </p>
            <p className="text-[10px] text-slate-500">{etiqueta}</p>
        </div>
    );

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <ClipboardList className="text-emerald-600" size={22} /> Planificaciones Semanales
                    </h2>
                    <p className="text-sm text-slate-500">
                        Menús definitivos seleccionados del motor de propuestas, con su recolección,
                        margen y detalle por día.
                    </p>
                </div>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {cargando ? (
                <div className="p-12 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={28} /></div>
            ) : planificaciones.length === 0 ? (
                <div className="p-12 text-center bg-slate-50 border border-slate-200 rounded-2xl">
                    <History size={36} className="text-emerald-600 mx-auto mb-3" />
                    <h3 className="font-bold text-slate-800 mb-2">Aún no hay planificaciones</h3>
                    <p className="text-sm text-slate-500 max-w-md mx-auto">
                        Cuando el personal directivo seleccione una propuesta en la pestaña
                        "Propuestas de Menú", el menú semanal aparecerá aquí con todo su detalle.
                    </p>
                </div>
            ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                        <thead>
                            <tr className="bg-slate-100 text-slate-600">
                                <th className="p-3 font-semibold">Semana</th>
                                <th className="p-3 font-semibold">Propuesta</th>
                                <th className="p-3 font-semibold">Días</th>
                                <th className="p-3 font-semibold">Costo total</th>
                                <th className="p-3 font-semibold">Recolección</th>
                                <th className="p-3 font-semibold">Margen</th>
                                <th className="p-3 font-semibold">Estado</th>
                                <th className="p-3 font-semibold">Seleccionado por</th>
                                <th className="p-3 font-semibold text-right">Detalle</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                            {planificaciones.map(p => {
                                const abierto = !!expandidos[p.id];
                                const det = cache[p.id];
                                const margen = margenDe(p);
                                return (
                                    <React.Fragment key={p.id}>
                                        <tr className="hover:bg-slate-50">
                                            <td className="p-3 font-medium text-slate-800">{p.fecha_referencia}</td>
                                            <td className="p-3 text-slate-600">{p.etiqueta || p.variante || '—'}</td>
                                            <td className="p-3 text-slate-600">{p.dias_operativos}</td>
                                            <td className="p-3 text-slate-600">S/ {p.costo_total_semana}</td>
                                            <td className="p-3 text-slate-600">S/ {p.recoleccion_total_proyectada}</td>
                                            <td className={`p-3 font-semibold ${margen >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                                                S/ {margen}
                                            </td>
                                            <td className="p-3">
                                                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                                    p.estado === 'VIGENTE' ? 'bg-emerald-100 text-emerald-700'
                                                    : p.estado === 'REEMPLAZADA' ? 'bg-amber-100 text-amber-700'
                                                    : 'bg-slate-100 text-slate-600'}`}>
                                                    {p.estado}
                                                </span>
                                            </td>
                                            <td className="p-3 text-slate-600">{p.seleccionado_por || '—'}</td>
                                            <td className="p-3 text-right">
                                                <button
                                                    onClick={() => toggleExpandir(p)}
                                                    className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                                    title={abierto ? 'Ocultar detalle' : 'Ver detalle por día'}
                                                >
                                                    {abierto ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                                                </button>
                                            </td>
                                        </tr>

                                        {/* ===== Detalle expandido ===== */}
                                        {abierto && (
                                            <tr>
                                                <td colSpan="9" className="p-4 bg-slate-50 space-y-4">
                                                    {!det ? (
                                                        <div className="p-6 text-center text-emerald-600">
                                                            <Loader2 className="animate-spin mx-auto" size={22} />
                                                        </div>
                                                    ) : (
                                                        <>
                                                        {/* Tarjetas de resumen: costo, recolección, margen y kcal */}
                                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                                            {tarjeta(<Wallet size={12} className="text-slate-500" />,
                                                                `S/ ${p.costo_total_semana}`, 'Costo total semanal (compras)')}
                                                            {tarjeta(<Coins size={12} className="text-emerald-600" />,
                                                                `S/ ${p.recoleccion_total_proyectada}`, 'Recolección semanal (ventas)')}
                                                            {tarjeta(<TrendingUp size={12} />,
                                                                `S/ ${margen}`, 'Margen (ventas − compras)',
                                                                margen >= 0 ? 'text-emerald-700' : 'text-red-600')}
                                                            {tarjeta(<Flame size={12} className="text-orange-500" />,
                                                                det.resumen ? `${det.resumen.calorias_promedio_dia} kcal` : '—',
                                                                'Kcal promedio por día')}
                                                        </div>

                                                        {/* COM-8 v2: comensales en 3 columnas grandes separadas */}
                                                        {det.dias && det.dias.length > 0 && (
                                                            <div className="grid grid-cols-3 gap-3">
                                                                {[
                                                                    ['Casos Sociales', det.dias[0].comensales_social, 'bg-red-50 border-red-200 text-red-700'],
                                                                    ['Afiliados', det.dias[0].comensales_afiliado, 'bg-blue-50 border-blue-200 text-blue-700'],
                                                                    ['Normales', det.dias[0].comensales_normal, 'bg-emerald-50 border-emerald-200 text-emerald-700'],
                                                                ].map(([label, valor, estilo]) => (
                                                                    <div key={label} className={`border rounded-xl p-3 text-center ${estilo}`}>
                                                                        <p className="text-3xl font-bold">{valor}</p>
                                                                        <p className="text-xs font-semibold flex items-center justify-center gap-1">
                                                                            <Users size={12} /> {label} / día
                                                                        </p>
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        )}

                                                        {/* Tabla por día con recolección proyectada */}
                                                        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                                                            <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                                                                <thead>
                                                                    <tr className="bg-slate-100 text-slate-600">
                                                                        <th className="p-2 font-semibold">Día</th>
                                                                        <th className="p-2 font-semibold">Receta</th>
                                                                        <th className="p-2 font-semibold">Costo/ración</th>
                                                                        <th className="p-2 font-semibold">Costo del día</th>
                                                                        <th className="p-2 font-semibold">Recolección proyectada</th>
                                                                        <th className="p-2 font-semibold">Kcal/ración</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody className="divide-y divide-slate-200">
                                                                    {det.dias.map(d => {
                                                                        const diaMenu = (det.menu || []).find(m => m.dia_semana === d.dia);
                                                                        return (
                                                                            <tr key={d.id}>
                                                                                <td className="p-2 font-bold text-slate-700">{d.dia_nombre}</td>
                                                                                <td className="p-2 text-slate-600">{d.nombre_receta}</td>
                                                                                <td className="p-2 text-slate-600">S/ {d.costo_racion}</td>
                                                                                <td className="p-2 text-slate-600">S/ {d.costo_total}</td>
                                                                                <td className="p-2 font-semibold text-emerald-700">S/ {d.recoleccion_proyectada}</td>
                                                                                <td className="p-2 text-slate-600">{diaMenu ? diaMenu.energia_kcal : '—'}</td>
                                                                            </tr>
                                                                        );
                                                                    })}
                                                                </tbody>
                                                            </table>
                                                        </div>

                                                        {/* Lista de compras de la semana */}
                                                        <div>
                                                            <button
                                                                onClick={() => toggleCompras(p)}
                                                                className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-800 transition-colors"
                                                            >
                                                                <ShoppingCart size={14} />
                                                                {mostrarCompras[p.id] ? 'Ocultar lista de compras' : 'Ver lista de compras'}
                                                            </button>
                                                            {mostrarCompras[p.id] && (
                                                                <div className="mt-2 rounded-lg border border-slate-200 bg-white p-3">
                                                                    {cargandoCompras[p.id] ? (
                                                                        <Loader2 className="animate-spin mx-auto text-emerald-600" size={18} />
                                                                    ) : (compras[p.id] || []).length === 0 ? (
                                                                        <p className="text-xs text-slate-500">Sin ítems de compra registrados.</p>
                                                                    ) : (
                                                                        <table className="w-full text-left text-xs">
                                                                            <thead>
                                                                                <tr className="text-slate-500 border-b border-slate-200">
                                                                                    <th className="p-1.5 font-semibold">Insumo</th>
                                                                                    <th className="p-1.5 font-semibold">Cantidad</th>
                                                                                    <th className="p-1.5 font-semibold">Unidad</th>
                                                                                    <th className="p-1.5 font-semibold">Costo aprox.</th>
                                                                                </tr>
                                                                            </thead>
                                                                            <tbody className="divide-y divide-slate-100">
                                                                                {compras[p.id].map((row, i) => (
                                                                                    <tr key={i}>
                                                                                        <td className="p-1.5 text-slate-700">
                                                                                            {row.nombre || row.ingrediente || row.insumo || '—'}
                                                                                        </td>
                                                                                        <td className="p-1.5 text-slate-600">{row.cantidad ?? '—'}</td>
                                                                                        <td className="p-1.5 text-slate-600">{row.unidad || '—'}</td>
                                                                                        <td className="p-1.5 text-slate-600">
                                                                                            {row.costo_total ?? row.costo ?? row.costo_estimado ?? '—'}
                                                                                        </td>
                                                                                    </tr>
                                                                                ))}
                                                                            </tbody>
                                                                        </table>
                                                                    )}
                                                                </div>
                                                            )}
                                                        </div>
                                                        </>
                                                    )}
                                                </td>
                                            </tr>
                                        )}
                                    </React.Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
};