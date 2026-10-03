/**
 * components/reportes/ReportesView.jsx
 * Objetivo: Pestaña "Reportes" (HU-10) con dos capas:
 *   (A) KPIs operativos del sistema (contadores y ventas del día) — visibles para
 *       todos los perfiles con módulo 'reportes'.
 *   (B) Panel "Resumen ejecutivo y recomendaciones" (COM-50 v3), con alcance por
 *       perfil resuelto por /reportes-gestion/alcance:
 *         * Administrador de Sistemas  -> 403: mensaje amigable (no ve reportes de
 *                                          comedores; HU-10 y matriz COM-50 v3).
 *         * Operativo (Cocinero)       -> 403: mensaje amigable (sin reportería).
 *         * Directivo                  -> nivel 'comedor' forzado: panel de SU
 *                                          comedor, sin selector de nivel/comedor.
 *         * Municipal                  -> selector de nivel (Macro / Zona / Comedor)
 *                                          + selector condicional + tabla agregada
 *                                          `por_comedor` cuando el nivel es macro/zona.
 * Historial:
 *  - Sprint 3/4: versión original (KPIs + ventas del día).
 *  - COM-50 v1/v2: integración del panel ejecutivo (comedor único).
 *  - COM-50 v3 (este archivo): matriz de alcances completa, panel reactivo al
 *    `tipo_alcance` del backend y tabla agregada `por_comedor` en macro/zona.
 *    Lo anterior queda comentado por trazabilidad; nada se elimina.
 * Uso: Renderizado por App.jsx en la pestaña "Reportes" (módulo 'reportes').
 * Referencia: tickets COM-50 / HU-10 (solo trazabilidad).
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
    Store, Users, ChefHat, ClipboardList, Activity, Loader2, AlertCircle,
    TrendingUp, Calendar, Lightbulb, Wallet, Repeat, FileText, RefreshCw,
    MapPin, Building2, Target, Table2
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// Formatos defensivos
const fmtS = (v) => (v === null || v === undefined || v === '' ? '—' : `S/ ${Number(v).toFixed(2)}`);
const fmtN = (v) => (v === null || v === undefined || v === '' ? '—' : Number(v).toFixed(2));

const FUENTE_PLAN_LABEL = {
    propuesta_seleccionada: 'Propuesta seleccionada',
    propuesta_ultima: 'Última propuesta generada',
    propuesta_indicada: 'Propuesta indicada',
    planificacion_ultima: 'Planificación guardada',
    planificacion_indicada: 'Planificación indicada',
};

// Icono y color por tipo de sugerencia (COM-50)
const iconoSugerencia = (tipo) => {
    if (tipo === 'ahorro') return <Lightbulb size={15} className="text-emerald-600 shrink-0 mt-0.5" />;
    if (tipo === 'alerta') return <AlertCircle size={15} className="text-red-600 shrink-0 mt-0.5" />;
    return <Repeat size={15} className="text-amber-600 shrink-0 mt-0.5" />;
};

export const ReportesView = () => {
    const { usuario } = useAuth();
    const esAdminSistema = usuario?.rol === 'Administrador Sistema';

    // --- KPIs operativos (A) ---
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [kpis, setKpis] = useState({
        comedores: 0,
        usuarios: null,   // null = sin permiso (se muestra "—"); solo Admin de Sistema
        recetas: 0,
        planificaciones: 0,
        ventasHoy: null
    });

    // --- Alcance y panel ejecutivo (B) COM-50 v3 ---
    const [cargandoAlcance, setCargandoAlcance] = useState(true);
    const [alcance, setAlcance] = useState(null);          // null = aún cargando
    const [alcanceError, setAlcanceError] = useState(null); // { status, message }
    const [nivelSel, setNivelSel] = useState('macro');
    const [zonaSel, setZonaSel] = useState('');
    const [comedorSel, setComedorSel] = useState('');
    const [planSel, setPlanSel] = useState('');            // '' = vigente automático
    const [reporte, setReporte] = useState(null);
    const [cargandoReporte, setCargandoReporte] = useState(false);
    const [errorReporte, setErrorReporte] = useState('');

    // =========================================================================
    // (A) KPIs operativos: comedores, usuarios, recetas, planificaciones, ventas.
    // El contador de usuarios SOLO lo consulta el Admin de Sistema (COM-50 v2).
    // =========================================================================
    useEffect(() => {
        const cargar = async () => {
            setCargando(true);
            setError('');
            try {
                const [comedores, usuarios, recetas, planificaciones, ventasHoy] = await Promise.all([
                    api.getComedores().catch(() => []),
                    esAdminSistema
                        ? api.getUsuarios({ usuario_solicitante_id: usuario.id }).catch(() => [])
                        : Promise.resolve(null),
                    api.getRecetas().catch(() => null),
                    api.getPlanificaciones().catch(() => []),
                    api.getVentasHoy().catch(() => null),
                ]);
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
    }, [esAdminSistema, usuario?.id]);

    // =========================================================================
    // (B) Alcance de reportería (COM-50 v3). 403 -> alcanceError, alcance=null.
    // =========================================================================
    useEffect(() => {
        let vivo = true;
        const cargar = async () => {
            setCargandoAlcance(true);
            setAlcanceError(null);
            setAlcance(null);
            try {
                const data = await api.getAlcanceReportes(usuario.id);
                if (!vivo) return;
                setAlcance(data);
                // Inicializar selectores según el alcance
                const niveles = data.niveles_permitidos || [];
                if (data.tipo_alcance === 'comedor') {
                    // Directivo: nivel fijo 'comedor', comedor fijo, sin selector
                    setNivelSel('comedor');
                    setComedorSel(String(data.comedor_fijo || ''));
                } else {
                    setNivelSel(niveles.includes('macro') ? 'macro' : niveles[0] || 'macro');
                    setZonaSel((data.zonas && data.zonas[0]) || '');
                    setComedorSel((data.comedores && data.comedores[0]?.id) || '');
                }
            } catch (e) {
                if (!vivo) return;
                setAlcanceError({ status: e.status || 0, message: e.message });
            } finally {
                if (vivo) setCargandoAlcance(false);
            }
        };
        cargar();
        return () => { vivo = false; };
    }, [usuario?.id]);

    // Planes disponibles del comedor seleccionado (solo aplica en nivel 'comedor')
    const [planes, setPlanes] = useState({ propuestas: [], planificaciones: [] });
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

    // =========================================================================
    // Carga del reporte: params dependen del nivel y del alcance
    // =========================================================================
    const cargarReporte = useCallback(async () => {
        if (!alcance) return;
        // Directivo: forzar comedor fijo
        const comedorId = alcance.tipo_alcance === 'comedor' ? alcance.comedor_fijo : comedorSel;
        if (nivelSel === 'comedor' && !comedorId) return;
        if (nivelSel === 'zona' && !zonaSel) return;

        setCargandoReporte(true);
        setErrorReporte('');
        try {
            const params = {
                usuario_solicitante_id: usuario.id,
                nivel: nivelSel,
            };
            if (nivelSel === 'comedor') {
                params.comedor_id = comedorId;
                if (planSel.startsWith('candidata:')) params.candidata_id = planSel.split(':')[1];
                if (planSel.startsWith('presupuesto:')) params.presupuesto_id = planSel.split(':')[1];
            } else if (nivelSel === 'zona') {
                params.zona = zonaSel;
            }
            setReporte(await api.getReporteGestion(params));
        } catch (e) {
            setReporte(null);
            setErrorReporte(e.message);
        } finally {
            setCargandoReporte(false);
        }
    }, [alcance, nivelSel, comedorSel, zonaSel, planSel, usuario.id]);

    // Recargar cuando cambien los selectores (Directivo carga automático al entrar)
    useEffect(() => {
        if (alcance) cargarReporte();
    }, [cargarReporte, alcance]);

    // Derivados de KPIs
    const ventas = kpis.ventasHoy || {};
    const totalVentas = (ventas.social || 0) + (ventas.afiliado || 0) + (ventas.normal || 0);
    const pctVenta = (v) => totalVentas > 0 ? Math.round((v / totalVentas) * 100) : 0;
    const tarjetas = [
        { label: 'Comedores registrados', value: kpis.comedores, icon: Store, color: 'emerald' },
        { label: 'Usuarios del sistema', value: kpis.usuarios === null ? '—' : kpis.usuarios, icon: Users, color: 'blue' },
        { label: 'Recetas del recetario', value: kpis.recetas, icon: ChefHat, color: 'amber' },
        { label: 'Planificaciones guardadas', value: kpis.planificaciones, icon: ClipboardList, color: 'purple' },
    ];

    // Derivados del reporte
    const resumen = reporte?.resumen || null;
    const usoPorDia = reporte?.uso_presupuesto_por_dia || [];
    const menu = reporte?.menu || [];
    const sugerencias = reporte?.sugerencias || [];
    const porComedor = reporte?.por_comedor || [];
    const maxPct = Math.max(100, ...usoPorDia.map(u => u.pct_del_presupuesto || 0));

    // Selector de comedor (solo cuando el alcance permite varios)
    const comedoresDisponibles = useMemo(() => alcance?.comedores || [], [alcance]);

    const puedeElegirNivel = alcance && alcance.tipo_alcance !== 'comedor';
    const nivelesPermitidos = alcance?.niveles_permitidos || [];

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="text-emerald-600" size={22} /> Reportes
                    </h2>
                    <p className="text-sm text-slate-500">
                        Resumen operativo del sistema, ventas del día y rendición de cuentas.
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
                    {/* (A) KPIs operativos */}
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

                    {/* (A) Ventas del día */}
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
                                            <span className="font-semibold">{barra.value} ({pctVenta(barra.value)}%)</span>
                                        </div>
                                        <div className="w-full bg-slate-100 rounded-full h-3">
                                            <div
                                                className={`${barra.color} h-3 rounded-full transition-all`}
                                                style={{ width: `${pctVenta(barra.value)}%` }}
                                            />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* ============================================================
                        (B) RESUMEN EJECUTIVO Y RECOMENDACIONES (COM-50 v3 / HU-10)
                        ============================================================ */}
                    <div className="bg-white border border-slate-200 rounded-xl p-5 mt-6">
                        <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <FileText size={18} className="text-emerald-600" /> Resumen ejecutivo y recomendaciones
                            </h3>
                        </div>

                        {/* Estado: cargando alcance */}
                        {cargandoAlcance && (
                            <div className="p-8 text-center text-emerald-600">
                                <Loader2 className="animate-spin mx-auto" size={26} />
                                <p className="text-xs text-slate-500 mt-2">Resolviendo su alcance de reportería...</p>
                            </div>
                        )}

                        {/* (B.1) Sin acceso: Admin de Sistema u Operativo */}
                        {!cargandoAlcance && alcanceError && (
                            <div className={`p-4 rounded-lg border text-sm flex items-start gap-2 ${
                                alcanceError.status === 403 ? 'bg-slate-50 border-slate-200 text-slate-700' : 'bg-red-50 border-red-200 text-red-700'
                            }`}>
                                {alcanceError.status === 403 ? <AlertCircle size={18} className="shrink-0 mt-0.5 text-slate-500" /> : <AlertCircle size={18} className="shrink-0 mt-0.5" />}
                                <div>
                                    <p className="font-semibold">
                                        {alcanceError.status === 403
                                            ? (esAdminSistema
                                                ? 'El Administrador de Sistemas no tiene reportes relacionados a comedores.'
                                                : 'Su perfil no tiene acceso a reportería de comedores.')
                                            : 'No se pudo determinar su alcance de reportería.'}
                                    </p>
                                    <p className="text-xs mt-1 text-slate-500">
                                        {alcanceError.status === 403
                                            ? (esAdminSistema
                                                ? 'Los reportes ejecutivos están reservados a los perfiles Directivo y Municipal.'
                                                : 'Solo los perfiles Directivo y Municipal pueden consultar reportes de comedores (HU-10).')
                                            : alcanceError.message}
                                    </p>
                                </div>
                            </div>
                        )}

                        {/* (B.2) Directivo: nivel 'comedor' forzado, sin selectores de nivel/comedor */}
                        {!cargandoAlcance && alcance && alcance.tipo_alcance === 'comedor' && (
                            <div className="space-y-4">
                                <div className="flex flex-wrap items-center gap-2">
                                    <span className="px-2.5 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full text-xs font-semibold flex items-center gap-1">
                                        <Target size={12} /> Comedor asignado
                                    </span>
                                    <span className="text-sm font-bold text-slate-800">
                                        {alcance.comedor_nombre || `Comedor #${alcance.comedor_fijo}`}
                                    </span>
                                    <select
                                        value={planSel}
                                        onChange={(e) => setPlanSel(e.target.value)}
                                        className="ml-auto px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500"
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
                                        disabled={cargandoReporte}
                                        className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors"
                                        title="Recargar reporte"
                                    >
                                        {cargandoReporte ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
                                    </button>
                                </div>
                                <ContenidoReporte
                                    reporte={reporte}
                                    cargandoReporte={cargandoReporte}
                                    errorReporte={errorReporte}
                                    resumen={resumen}
                                    usoPorDia={usoPorDia}
                                    menu={menu}
                                    sugerencias={sugerencias}
                                    maxPct={maxPct}
                                    mostrarMenu={true}
                                />
                            </div>
                        )}

                        {/* (B.3) Municipal / macro_general: selector de nivel + selectores condicionales */}
                        {!cargandoAlcance && alcance && alcance.tipo_alcance !== 'comedor' && (
                            <div className="space-y-4">
                                {/* Selector de nivel */}
                                <div className="flex flex-wrap items-center gap-2">
                                    <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden">
                                        {nivelesPermitidos.includes('macro') && (
                                            <button
                                                onClick={() => { setNivelSel('macro'); setPlanSel(''); }}
                                                className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1 transition-colors ${
                                                    nivelSel === 'macro' ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                                                }`}
                                            >
                                                <Building2 size={13} /> Macro
                                            </button>
                                        )}
                                        {nivelesPermitidos.includes('zona') && (
                                            <button
                                                onClick={() => setNivelSel('zona')}
                                                className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1 transition-colors border-x border-slate-200 ${
                                                    nivelSel === 'zona' ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                                                }`}
                                            >
                                                <MapPin size={13} /> Zona
                                            </button>
                                        )}
                                        {nivelesPermitidos.includes('comedor') && (
                                            <button
                                                onClick={() => setNivelSel('comedor')}
                                                className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1 transition-colors ${
                                                    nivelSel === 'comedor' ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                                                }`}
                                            >
                                                <Store size={13} /> Comedor
                                            </button>
                                        )}
                                    </div>

                                    {/* Selector de zona (solo nivel=zona) */}
                                    {nivelSel === 'zona' && (
                                        <select
                                            value={zonaSel}
                                            onChange={(e) => setZonaSel(e.target.value)}
                                            className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500"
                                        >
                                            <option value="">Seleccionar zona...</option>
                                            {(alcance.zonas || []).map(z => (
                                                <option key={z} value={z}>{z}</option>
                                            ))}
                                        </select>
                                    )}

                                    {/* Selector de comedor (solo nivel=comedor) */}
                                    {nivelSel === 'comedor' && (
                                        <>
                                            <select
                                                value={comedorSel}
                                                onChange={(e) => { setComedorSel(e.target.value); setPlanSel(''); }}
                                                className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500"
                                            >
                                                <option value="">Seleccionar comedor...</option>
                                                {comedoresDisponibles.map(c => (
                                                    <option key={c.id} value={c.id}>
                                                        {c.nombre}{c.zona ? ` · ${c.zona}` : ''}
                                                    </option>
                                                ))}
                                            </select>
                                            {comedorSel && (
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
                                            )}
                                        </>
                                    )}

                                    <button
                                        onClick={cargarReporte}
                                        disabled={cargandoReporte || (nivelSel === 'comedor' && !comedorSel) || (nivelSel === 'zona' && !zonaSel)}
                                        className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg transition-colors disabled:opacity-50"
                                        title="Recargar reporte"
                                    >
                                        {cargandoReporte ? <Loader2 className="animate-spin" size={15} /> : <RefreshCw size={15} />}
                                    </button>
                                </div>

                                <ContenidoReporte
                                    reporte={reporte}
                                    cargandoReporte={cargandoReporte}
                                    errorReporte={errorReporte}
                                    resumen={resumen}
                                    usoPorDia={usoPorDia}
                                    menu={menu}
                                    sugerencias={sugerencias}
                                    porComedor={porComedor}
                                    maxPct={maxPct}
                                    mostrarMenu={nivelSel === 'comedor'}
                                    nivelSel={nivelSel}
                                />
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};

// ============================================================================
// Subcomponente: cuerpo del reporte (comedor único vs agregado macro/zona)
// ============================================================================
const ContenidoReporte = ({
    reporte, cargandoReporte, errorReporte, resumen, usoPorDia, menu, sugerencias,
    porComedor = [], maxPct, mostrarMenu = true, nivelSel = ''
}) => {
    if (errorReporte) {
        return (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                <AlertCircle size={16} /> {errorReporte}
            </div>
        );
    }
    if (cargandoReporte) {
        return <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={26} /></div>;
    }
    if (!reporte) {
        return <p className="text-sm text-slate-400 text-center py-8">
            Aún no hay datos para el nivel seleccionado.
        </p>;
    }

    const esNivelComedor = reporte.nivel === 'comedor';

    return (
        <div className="space-y-6">
            {/* Fuente y alcance */}
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                {esNivelComedor ? (
                    <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full font-semibold">
                        {FUENTE_PLAN_LABEL[reporte.fuente_plan] || reporte.fuente_plan}
                    </span>
                ) : (
                    <span className="px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-200 rounded-full font-semibold flex items-center gap-1">
                        <Table2 size={12} />
                        Agregado de {reporte.comedores_incluidos?.length || 0} comedor(es)
                    </span>
                )}
                <span>Generado el {reporte.generado_el}</span>
                {resumen?.dentro_de_presupuesto ? (
                    <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full font-bold">Dentro del presupuesto</span>
                ) : (
                    <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full font-bold">Fuera del presupuesto</span>
                )}
            </div>

            {reporte.nota_sugerencias && (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm flex items-center gap-2">
                    <AlertCircle size={15} /> {reporte.nota_sugerencias}
                </div>
            )}

            {/* Tarjetas de resumen ejecutivo */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="border border-slate-200 rounded-xl p-3">
                    <p className="text-[11px] text-slate-500 flex items-center gap-1"><Wallet size={12} /> Costo total</p>
                    <p className="text-lg font-bold text-slate-800">{fmtS(resumen?.costo_total_semana)}</p>
                </div>
                <div className="border border-slate-200 rounded-xl p-3">
                    <p className="text-[11px] text-slate-500 flex items-center gap-1"><ChefHat size={12} /> Costo/ración prom.</p>
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

            {/* Uso del presupuesto por día */}
            <div>
                <h4 className="text-sm font-bold text-slate-700 mb-3">
                    {esNivelComedor ? 'Uso del presupuesto por día' : 'Uso agregado del presupuesto por día'}
                </h4>
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

            {/* Menú del plan (solo cuando el reporte es de un comedor específico) */}
            {mostrarMenu && menu.length > 0 && (
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
            )}

            {/* Tabla agregada por_comedor (solo macro/zona) */}
            {!esNivelComedor && porComedor.length > 0 && (
                <div>
                    <h4 className="text-sm font-bold text-slate-700 mb-2 flex items-center gap-1">
                        <Table2 size={15} className="text-emerald-600" /> Indicadores por comedor ({porComedor.length})
                    </h4>
                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full text-left text-xs">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-2 font-semibold">Comedor</th>
                                    <th className="p-2 font-semibold">Zona</th>
                                    <th className="p-2 font-semibold">Fuente</th>
                                    <th className="p-2 font-semibold text-right">Costo semana</th>
                                    <th className="p-2 font-semibold text-right">Costo/ración</th>
                                    <th className="p-2 font-semibold text-right">Recolección</th>
                                    <th className="p-2 font-semibold text-right">Margen</th>
                                    <th className="p-2 font-semibold text-center">Presupuesto</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {porComedor.map((pc, i) => {
                                    const r = pc.resumen || {};
                                    const margen = r.margen_proyectado;
                                    return (
                                        <tr key={i} className="hover:bg-slate-50">
                                            <td className="p-2 font-medium text-slate-700 whitespace-nowrap">{pc.comedor_nombre}</td>
                                            <td className="p-2 text-slate-600">{pc.zona || '—'}</td>
                                            <td className="p-2 text-slate-500 text-[10px]">{FUENTE_PLAN_LABEL[pc.fuente_plan] || pc.fuente_plan}</td>
                                            <td className="p-2 text-right text-slate-700">{fmtS(r.costo_total_semana)}</td>
                                            <td className="p-2 text-right text-slate-700">{fmtS(r.costo_racion_promedio)}</td>
                                            <td className="p-2 text-right text-slate-700">{fmtS(r.recoleccion_total_semana)}</td>
                                            <td className={`p-2 text-right font-semibold ${(margen ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                                                {fmtS(margen)}
                                            </td>
                                            <td className="p-2 text-center">
                                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                                    r.dentro_de_presupuesto ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                                                }`}>
                                                    {r.dentro_de_presupuesto ? 'OK' : 'Excede'}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Sugerencias automáticas */}
            <div>
                <h4 className="text-sm font-bold text-slate-700 mb-2 flex items-center gap-1">
                    <Lightbulb size={15} className="text-emerald-600" /> Sugerencias y recomendaciones
                </h4>
                {sugerencias.length === 0 ? (
                    <p className="text-sm text-slate-400">
                        Sin sugerencias para el nivel seleccionado: los menús ya son económicamente
                        eficientes dentro de sus clusters y el presupuesto está equilibrado.
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
    );
};