/**
 * components/reportes/ReportesView.jsx
 * Objetivo: Pestaña "Reportes": resumen operativo del sistema (contadores y ventas del
 *           día) + COM-50 "Resumen ejecutivo y recomendaciones" (menú del plan vigente,
 *           costo total, costo por comensal, barras de % de presupuesto por día y
 *           sugerencias automáticas de ahorro/alertas/variedad, HU-10).
 * Historial:
 *  - Sprint 3/4: versión original (KPIs agregados + ventas del día).
 *  - COM-50 v1: panel de reporte de gestión integrado en esta pestaña.
 *  - COM-50 v2 (este archivo): fix de los errores de consola con perfil no admin:
 *      * El KPI "Usuarios del sistema" SOLO se consulta si el perfil es Admin de
 *        Sistemas (antes se pedía con usuario_solicitante_id=0 => 403 siempre, y 403
 *        por permiso para Presidente/Tesorero); para el resto se muestra "—" sin llamada.
 *      * El KPI "Recetas" usa el total del listado paginado (antes contaba solo la
 *        primera página, mostrando 0 o un número parcial).
 *      * Se muestra la nota de degradación de sugerencias si el backend la incluye.
 *    Nada existente se elimina; lo ajustado queda comentado por trazabilidad.
 * Uso: Renderizado por App.jsx en la pestaña "Reportes" (módulo 'reportes').
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Store, Users, ChefHat, ClipboardList, Activity, Loader2, AlertCircle,
    TrendingUp, Calendar, Lightbulb, Wallet, Repeat, FileText, RefreshCw
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// COM-50: formato de montos para las tarjetas del reporte
const fmtS = (v) => (v === null || v === undefined || v === '' ? '—' : `S/ ${Number(v).toFixed(2)}`);

// COM-50: etiquetas legibles de la fuente del plan reportado
const FUENTE_PLAN_LABEL = {
    propuesta_seleccionada: 'Propuesta seleccionada',
    propuesta_ultima: 'Última propuesta generada',
    propuesta_indicada: 'Propuesta indicada',
    planificacion_ultima: 'Planificación guardada',
    planificacion_indicada: 'Planificación indicada',
};

export const ReportesView = () => {
    const { usuario, seleccion } = useAuth();
    // COM-50 v2: solo el Admin de Sistemas puede ver el contador global de usuarios
    const esAdminSistema = usuario?.rol === 'Administrador Sistema';

    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');

    // KPIs agregados
    const [kpis, setKpis] = useState({
        comedores: 0,
        usuarios: null,   // COM-50 v2: null = sin permiso (se muestra "—")
        recetas: 0,
        planificaciones: 0,
        ventasHoy: null
    });

    // ===== COM-50: estado del panel de reporte de gestión =====
    const [comedoresLista, setComedoresLista] = useState([]);
    const [comedorSel, setComedorSel] = useState(seleccion?.comedor_id || '');
    const [planes, setPlanes] = useState({ propuestas: [], planificaciones: [] });
    const [planSel, setPlanSel] = useState('');   // '' = plan vigente automático
    const [reporte, setReporte] = useState(null);
    const [cargandoReporte, setCargandoReporte] = useState(false);
    const [errorReporte, setErrorReporte] = useState('');

    // Carga agregada de los contadores y el resumen de ventas del día
    useEffect(() => {
        const cargar = async () => {
            setCargando(true);
            setError('');
            try {
                const [comedores, usuarios, recetas, planificaciones, ventasHoy] = await Promise.all([
                    api.getComedores().catch(() => []),
                    // COM-50 v2 (trazabilidad): llamada anterior sin gate, comentada:
                    // api.getUsuarios({ usuario_solicitante_id: 0 }).catch(() => []),
                    // COM-50 v2: solo Admin de Sistemas consulta el padrón de usuarios
                    esAdminSistema
                        ? api.getUsuarios({ usuario_solicitante_id: usuario.id }).catch(() => [])
                        : Promise.resolve(null),
                    api.getRecetas().catch(() => null),
                    api.getPlanificaciones().catch(() => []),
                    api.getVentasHoy().catch(() => null),
                ]);
                // COM-50 v2 (trazabilidad): conteo anterior de recetas por longitud de
                // la primera página, comentado:
                // recetas: Array.isArray(recetas) ? recetas.length : 0,
                const totalRecetas = recetas
                    ? (recetas.total ?? (Array.isArray(recetas.recetas) ? recetas.recetas.length : 0))
                    : 0;
                setKpis({
                    comedores: Array.isArray(comedores) ? comedores.length : 0,
                    usuarios: Array.isArray(usuarios) ? usuarios.length : null,
                    recetas: totalRecetas,
                    planificaciones: Array.isArray(planificaciones) ? planificaciones.length : 0,
                    ventasHoy
                });
            } catch (e) {
                setError(e.message);
            } finally {
                setCargando(false);
            }
        };
        cargar();
    }, [esAdminSistema, usuario.id]);

    // COM-50: si la sesión no fija comedor (perfil SISTEMA), ofrecer selector
    useEffect(() => {
        if (seleccion?.comedor_id) {
            setComedorSel(seleccion.comedor_id);
            return;
        }
        api.getComedores()
            .then(list => setComedoresLista(Array.isArray(list) ? list : []))
            .catch(() => setComedoresLista([]));
    }, [seleccion]);

    // COM-50: planes disponibles del comedor seleccionado
    useEffect(() => {
        if (!comedorSel) {
            setPlanes({ propuestas: [], planificaciones: [] });
            return;
        }
        let vivo = true;
        api.getPlanesGestion(comedorSel, usuario.id)
            .then(r => { if (vivo) setPlanes(r || { propuestas: [], planificaciones: [] }); })
            .catch(() => { if (vivo) setPlanes({ propuestas: [], planificaciones: [] }); });
        return () => { vivo = false; };
    }, [comedorSel, usuario.id]);

    // COM-50: carga del reporte (plan indicado o vigente automático)
    const cargarReporte = useCallback(async () => {
        if (!comedorSel) return;
        setCargandoReporte(true);
        setErrorReporte('');
        try {
            const params = { comedor_id: comedorSel, usuario_solicitante_id: usuario.id };
            if (planSel.startsWith('candidata:')) params.candidata_id = planSel.split(':')[1];
            if (planSel.startsWith('presupuesto:')) params.presupuesto_id = planSel.split(':')[1];
            setReporte(await api.getReporteGestion(params));
        } catch (e) {
            setReporte(null);
            setErrorReporte(e.message);
        } finally {
            setCargandoReporte(false);
        }
    }, [comedorSel, planSel, usuario.id]);

    useEffect(() => { cargarReporte(); }, [cargarReporte]);

    // Agrupación de ventas por tipo de comensal (para el gráfico CSS)
    const ventas = kpis.ventasHoy || {};
    const totalVentas = (ventas.social || 0) + (ventas.afiliado || 0) + (ventas.normal || 0);
    const pct = (v) => totalVentas > 0 ? Math.round((v / totalVentas) * 100) : 0;
    const tarjetas = [
        { label: 'Comedores registrados', value: kpis.comedores, icon: Store, color: 'emerald' },
        // COM-50 v2: null => "—" (perfil sin permiso sobre el padrón de usuarios)
        { label: 'Usuarios del sistema', value: kpis.usuarios === null ? '—' : kpis.usuarios, icon: Users, color: 'blue' },
        { label: 'Recetas del recetario', value: kpis.recetas, icon: ChefHat, color: 'amber' },
        { label: 'Planificaciones guardadas', value: kpis.planificaciones, icon: ClipboardList, color: 'purple' },
    ];

    // ===== COM-50: datos derivados del reporte =====
    const resumen = reporte?.resumen || null;
    const usoPorDia = reporte?.uso_presupuesto_por_dia || [];
    const menu = reporte?.menu || [];
    const sugerencias = reporte?.sugerencias || [];
    const maxPct = Math.max(100, ...usoPorDia.map(u => u.pct_del_presupuesto || 0));

    const iconoSugerencia = (tipo) => {
        if (tipo === 'ahorro') return <Lightbulb size={15} className="text-emerald-600 shrink-0 mt-0.5" />;
        if (tipo === 'alerta') return <AlertCircle size={15} className="text-red-600 shrink-0 mt-0.5" />;
        return <Repeat size={15} className="text-amber-600 shrink-0 mt-0.5" />;
    };

    return (
        <div className="animate-in fade-in duration-300">
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="text-emerald-600" size={22} /> Reportes
                    </h2>
                    <p className="text-sm text-slate-500">
                        Resumen operativo del sistema y de las ventas del día.
                    </p>
                </div>
                <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1 rounded-full flex items-center gap-1">
                    <Calendar size={12} /> {new Date().toLocaleDateString('es-PE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </span>
            </div>
            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}
            {cargando ? (
                <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={28} /></div>
            ) : (
                <>
                    {/* Tarjetas de KPIs */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        {tarjetas.map(t => {
                            const Icon = t.icon;
                            return (
                                <div key={t.label} className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
                                    <div className={`p-3 rounded-lg bg-${t.color}-100 text-${t.color}-700`}>
                                        <Icon size={22} />
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold text-slate-800">{t.value}</p>
                                        <p className="text-xs text-slate-500">{t.label}</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {/* Panel de ventas del día */}
                    <div className="bg-white border border-slate-200 rounded-xl p-5">
                        <div className="flex flex-wrap justify-between items-center gap-2 mb-4">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <Activity size={18} className="text-emerald-600" /> Ventas del día
                            </h3>
                            <span className="text-sm font-semibold text-slate-700">
                                Total: {totalVentas} raciones
                            </span>
                        </div>
                        {totalVentas === 0 ? (
                            <p className="text-sm text-slate-400 text-center py-8">
                                Aún no hay ventas registradas el día de hoy.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {[
                                    { label: 'Social', value: ventas.social || 0, color: 'bg-red-500' },
                                    { label: 'Afiliado', value: ventas.afiliado || 0, color: 'bg-blue-500' },
                                    { label: 'Normal', value: ventas.normal || 0, color: 'bg-emerald-500' },
                                ].map(barra => (
                                    <div key={barra.label}>
                                        <div className="flex justify-between text-xs text-slate-600 mb-1">
                                            <span>{barra.label}</span>
                                            <span className="font-semibold">{barra.value} ({pct(barra.value)}%)</span>
                                        </div>
                                        <div className="w-full bg-slate-100 rounded-full h-3">
                                            <div
                                                className={`${barra.color} h-3 rounded-full transition-all`}
                                                style={{ width: `${pct(barra.value)}%` }}
                                            />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* ============================================================
                        COM-50: RESUMEN EJECUTIVO Y RECOMENDACIONES (HU-10)
                        ============================================================ */}
                    <div className="bg-white border border-slate-200 rounded-xl p-5 mt-6">
                        <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <FileText size={18} className="text-emerald-600" /> Resumen ejecutivo y recomendaciones
                            </h3>
                            <div className="flex flex-wrap items-center gap-2">
                                {/* Selector de comedor solo si la sesión no fija uno (perfil SISTEMA) */}
                                {!seleccion?.comedor_id && (
                                    <select
                                        value={comedorSel}
                                        onChange={(e) => { setComedorSel(e.target.value); setPlanSel(''); }}
                                        className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500"
                                    >
                                        <option value="">Seleccionar comedor...</option>
                                        {comedoresLista.map(c => (
                                            <option key={c.id} value={c.id}>{c.nombre}</option>
                                        ))}
                                    </select>
                                )}
                                <select
                                    value={planSel}
                                    onChange={(e) => setPlanSel(e.target.value)}
                                    className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500"
                                >
                                    <option value="">Plan vigente (automático)</option>
                                    <optgroup label="Propuestas de menú">
                                        {planes.propuestas.map(p => (
                                            <option key={`c-${p.id}`} value={`candidata:${p.id}`}>
                                                #{p.id} · {p.etiqueta || p.variante} · {p.estado || '—'} · {String(p.fecha || '').slice(0, 10)}
                                            </option>
                                        ))}
                                    </optgroup>
                                    <optgroup label="Planificaciones guardadas">
                                        {planes.planificaciones.map(p => (
                                            <option key={`p-${p.id}`} value={`presupuesto:${p.id}`}>
                                                #{p.id} · semana {p.fecha_referencia || '—'} · {fmtS(p.costo_total_semana)}
                                            </option>
                                        ))}
                                    </optgroup>
                                </select>
                                <button
                                    onClick={cargarReporte}
                                    disabled={cargandoReporte || !comedorSel}
                                    className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors disabled:opacity-50"
                                    title="Recargar reporte"
                                >
                                    {cargandoReporte ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
                                </button>
                            </div>
                        </div>

                        {errorReporte && (
                            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm mb-4">
                                <AlertCircle size={16} /> {errorReporte}
                            </div>
                        )}

                        {!comedorSel ? (
                            <p className="text-sm text-slate-400 text-center py-8">
                                Seleccione un comedor para generar el reporte de gestión.
                            </p>
                        ) : cargandoReporte ? (
                            <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={26} /></div>
                        ) : !reporte ? (
                            <p className="text-sm text-slate-400 text-center py-8">
                                Este comedor aún no tiene propuestas seleccionadas ni planificaciones guardadas.
                            </p>
                        ) : (
                            <div className="space-y-6">
                                {/* Fuente del plan */}
                                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                                    <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full font-semibold">
                                        {FUENTE_PLAN_LABEL[reporte.fuente_plan] || reporte.fuente_plan}
                                    </span>
                                    <span>Generado el {reporte.generado_el}</span>
                                    {resumen?.dentro_de_presupuesto ? (
                                        <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-bold">Dentro del presupuesto</span>
                                    ) : (
                                        <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full font-bold">Fuera del presupuesto</span>
                                    )}
                                </div>

                                {/* COM-50 v2: nota de degradación de sugerencias si aplica */}
                                {reporte.nota_sugerencias && (
                                    <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm flex items-center gap-2">
                                        <AlertCircle size={15} /> {reporte.nota_sugerencias}
                                    </div>
                                )}

                                {/* Tarjetas de resumen ejecutivo */}
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                                    <div className="border border-slate-200 rounded-xl p-3">
                                        <p className="text-[11px] text-slate-500 flex items-center gap-1"><Wallet size={12} /> Costo total semana</p>
                                        <p className="text-lg font-bold text-slate-800">{fmtS(resumen?.costo_total_semana)}</p>
                                    </div>
                                    <div className="border border-slate-200 rounded-xl p-3">
                                        <p className="text-[11px] text-slate-500 flex items-center gap-1"><ChefHat size={12} /> Costo por ración</p>
                                        <p className="text-lg font-bold text-slate-800">{fmtS(resumen?.costo_racion_promedio)}</p>
                                    </div>
                                    <div className="border border-slate-200 rounded-xl p-3">
                                        <p className="text-[11px] text-slate-500 flex items-center gap-1"><TrendingUp size={12} /> Recolección proy.</p>
                                        <p className="text-lg font-bold text-slate-800">{fmtS(resumen?.recoleccion_total_semana)}</p>
                                    </div>
                                    <div className="border border-slate-200 rounded-xl p-3">
                                        <p className="text-[11px] text-slate-500 flex items-center gap-1"><Activity size={12} /> Margen proy.</p>
                                        <p className={`text-lg font-bold ${(resumen?.margen_proyectado ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                                            {fmtS(resumen?.margen_proyectado)}
                                        </p>
                                    </div>
                                    <div className="border border-slate-200 rounded-xl p-3">
                                        <p className="text-[11px] text-slate-500 flex items-center gap-1"><ClipboardList size={12} /> Presupuesto</p>
                                        <p className="text-lg font-bold text-slate-800">{fmtS(resumen?.presupuesto_semanal)}</p>
                                    </div>
                                </div>

                                {/* Gráfico de barras: % del presupuesto usado por día */}
                                <div>
                                    <h4 className="text-sm font-bold text-slate-700 mb-3">Uso del presupuesto por día</h4>
                                    {usoPorDia.length === 0 ? (
                                        <p className="text-sm text-slate-400">Sin datos diarios para graficar.</p>
                                    ) : (
                                        <div className="space-y-3">
                                            {usoPorDia.map((u, i) => (
                                                <div key={i}>
                                                    <div className="flex justify-between text-xs text-slate-600 mb-1">
                                                        <span className="font-semibold">{u.dia_nombre}{u.fecha ? ` · ${u.fecha}` : ''}</span>
                                                        <span>
                                                            {fmtS(u.costo_total_dia)}
                                                            {u.pct_del_presupuesto != null && ` (${u.pct_del_presupuesto}% del presupuesto)`}
                                                        </span>
                                                    </div>
                                                    <div className="w-full bg-slate-100 rounded-full h-3">
                                                        <div
                                                            className={`h-3 rounded-full transition-all ${
                                                                (u.pct_del_presupuesto || 0) > (100 / Math.max(usoPorDia.length, 1)) * 1.35
                                                                    ? 'bg-amber-500'
                                                                    : 'bg-emerald-500'
                                                            }`}
                                                            style={{ width: `${Math.min(100, ((u.pct_del_presupuesto || 0) / maxPct) * 100)}%` }}
                                                        />
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>

                                {/* Menú del plan reportado */}
                                <div>
                                    <h4 className="text-sm font-bold text-slate-700 mb-2">Menú del plan reportado</h4>
                                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                                        <table className="w-full text-left text-sm">
                                            <thead>
                                                <tr className="bg-slate-100 text-slate-600">
                                                    <th className="p-2 font-semibold">Día</th>
                                                    <th className="p-2 font-semibold">Receta</th>
                                                    <th className="p-2 font-semibold">Cluster</th>
                                                    <th className="p-2 font-semibold text-right">Costo/ración</th>
                                                    <th className="p-2 font-semibold text-right">Costo del día</th>
                                                    <th className="p-2 font-semibold text-right">Recolección proy.</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-200">
                                                {menu.map((d, i) => (
                                                    <tr key={i} className="hover:bg-slate-50">
                                                        <td className="p-2 font-medium text-slate-700">{d.dia_nombre}</td>
                                                        <td className="p-2 text-slate-700">{d.receta_nombre}</td>
                                                        <td className="p-2 text-xs text-slate-500">{d.cluster_etiqueta || '—'}</td>
                                                        <td className="p-2 text-right text-slate-700">{fmtS(d.costo_racion)}</td>
                                                        <td className="p-2 text-right text-slate-700">{fmtS(d.costo_total_dia)}</td>
                                                        <td className="p-2 text-right text-slate-700">{fmtS(d.recoleccion_proyectada)}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Sugerencias automáticas */}
                                <div>
                                    <h4 className="text-sm font-bold text-slate-700 mb-2 flex items-center gap-1">
                                        <Lightbulb size={15} className="text-emerald-600" /> Sugerencias y recomendaciones
                                    </h4>
                                    {sugerencias.length === 0 ? (
                                        <p className="text-sm text-slate-400">
                                            Sin sugerencias para este plan: el menú ya es económicamente eficiente
                                            dentro de sus clusters y el presupuesto está equilibrado.
                                        </p>
                                    ) : (
                                        <div className="space-y-2">
                                            {sugerencias.map((s, i) => (
                                                <div
                                                    key={i}
                                                    className={`p-3 rounded-lg border text-sm flex items-start gap-2 ${
                                                        s.tipo === 'alerta'
                                                            ? 'bg-red-50 border-red-200 text-red-700'
                                                            : s.tipo === 'variedad'
                                                                ? 'bg-amber-50 border-amber-200 text-amber-800'
                                                                : 'bg-emerald-50 border-emerald-200 text-emerald-800'
                                                    }`}
                                                >
                                                    {iconoSugerencia(s.tipo)}
                                                    <span>
                                                        {s.texto}
                                                        {s.ahorro_pct != null && (
                                                            <b className="ml-1">(ahorro {s.ahorro_pct}% · {fmtS(s.ahorro_soles_por_racion)}/ración)</b>
                                                        )}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};