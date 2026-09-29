/**
 * components/ml/ModelosMLView.jsx
 * Objetivo: Panel de gráficos de Machine Learning (COM-5 v4 / COM-8 v7), exclusivo del
 *           Administrador de Sistemas (módulo 'modelos_ml'). Tres gráficos SVG propios
 *           (sin librerías externas), todos con sus VARIABLES/INDICADORES rotulados:
 *           1) Random Forest: dispersión REAL vs PREDICHO de la demanda diaria por tipo
 *              de comensal, con línea de referencia y=x, métricas R²/MAE por tipo y
 *              barras de importancia de las variables del modelo.
 *           2) K-means: dispersión PCA-2D de las recetas coloreada por cluster, con
 *              centroides proyectados, varianza explicada de PC1/PC2 y tabla de cargas
 *              de cada variable original en ambos componentes.
 *           3) Greedy Search: barras de totales por variante (costo, recolección,
 *              margen) y líneas de la serie diaria con indicador seleccionable
 *              (costo del día, recolección, kcal/ración, hierro/ración).
 * Uso: Montada por App.jsx en la pestaña "Modelos ML" (gate por módulo 'modelos_ml').
 * Referencia: tickets COM-5 v4 / COM-8 v7 (solo trazabilidad).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity, Loader2, AlertCircle, RefreshCw, TrendingUp, PieChart, Sparkles
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// ==========================================
// PALETAS Y CONSTANTES DE GRÁFICOS
// ==========================================
const COLOR_TIPO = { social: '#dc2626', afiliado: '#2563eb', normal: '#059669' };
const COLOR_CLUSTER = { 1: '#dc2626', 2: '#2563eb', 3: '#16a34a', 4: '#d97706' };
const COLOR_VARIANTE = { NUTRI: '#dc2626', ECONO: '#d97706', BALANCE: '#059669' };
const COLOR_INDICADOR = { costo: '#64748b', recoleccion: '#059669', margen: '#2563eb' };

const METRICAS_SERIE = [
    { clave: 'costo_total_dia', label: 'Costo del día (S/)' },
    { clave: 'recoleccion_proyectada', label: 'Recolección del día (S/)' },
    { clave: 'energia_kcal', label: 'Kcal por ración' },
    { clave: 'hierro_mg', label: 'Hierro por ración (mg)' },
];

// ==========================================
// UTILIDADES DE ESCALADO SVG
// ==========================================
const dominio = (vals, pad = 0.08) => {
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = (max - min) || 1;
    return [min - span * pad, max + span * pad];
};
const ticksEntre = (min, max, n = 4) => {
    const arr = [];
    for (let i = 0; i <= n; i++) arr.push(min + ((max - min) * i) / n);
    return arr;
};
const fmt = (v, d = 1) => Number(v).toFixed(d);

// ==========================================
// GRÁFICO 1: DISPERSIÓN RANDOM FOREST (REAL vs PREDICHO)
// ==========================================
const ScatterRF = ({ puntos }) => {
    const W = 560, H = 360, M = { t: 16, r: 16, b: 48, l: 56 };
    const vals = [...puntos.map(p => p.real), ...puntos.map(p => p.predicho)];
    const [d0, d1] = dominio(vals);
    const sx = (v) => M.l + ((v - d0) / (d1 - d0)) * (W - M.l - M.r);
    const sy = (v) => H - M.b - ((v - d0) / (d1 - d0)) * (H - M.t - M.b);
    const tks = ticksEntre(d0, d1, 4);
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {tks.map((t, i) => (
                <g key={i}>
                    <line x1={sx(t)} x2={sx(t)} y1={M.t} y2={H - M.b} stroke="#e2e8f0" />
                    <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
                    <text x={sx(t)} y={H - M.b + 16} fontSize="10" fill="#64748b" textAnchor="middle">{fmt(t, 0)}</text>
                    <text x={M.l - 8} y={sy(t) + 3} fontSize="10" fill="#64748b" textAnchor="end">{fmt(t, 0)}</text>
                </g>
            ))}
            {/* Línea de referencia: predicción perfecta (y = x) */}
            <line x1={sx(d0)} y1={sy(d0)} x2={sx(d1)} y2={sy(d1)} stroke="#94a3b8" strokeDasharray="5 4" strokeWidth="1.5" />
            {puntos.map((p, i) => (
                <circle key={i} cx={sx(p.real)} cy={sy(p.predicho)} r="4"
                    fill={COLOR_TIPO[p.tipo] || '#64748b'} fillOpacity="0.75">
                    <title>{`${p.fecha} · ${p.tipo}: real ${p.real} / predicho ${p.predicho}`}</title>
                </circle>
            ))}
            <text x={W / 2} y={H - 10} fontSize="11" fill="#475569" textAnchor="middle">
                Comensales REALES del día (raciones)
            </text>
            <text x={14} y={H / 2} fontSize="11" fill="#475569" textAnchor="middle"
                transform={`rotate(-90 14 ${H / 2})`}>
                Comensales PREDICHOS por Random Forest
            </text>
        </svg>
    );
};

// ==========================================
// GRÁFICO 2: DISPERSIÓN PCA-2D DEL K-MEANS
// ==========================================
const ScatterKmeans = ({ data }) => {
    const W = 560, H = 380, M = { t: 16, r: 16, b: 48, l: 56 };
    const xs = [...data.puntos.map(p => p.x), ...data.centroides.map(c => c.x)];
    const ys = [...data.puntos.map(p => p.y), ...data.centroides.map(c => c.y)];
    const [x0, x1] = dominio(xs);
    const [y0, y1] = dominio(ys);
    const sx = (v) => M.l + ((v - x0) / (x1 - x0)) * (W - M.l - M.r);
    const sy = (v) => H - M.b - ((v - y0) / (y1 - y0)) * (H - M.t - M.b);
    const tx = ticksEntre(x0, x1, 4);
    const ty = ticksEntre(y0, y1, 4);
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {tx.map((t, i) => (
                <g key={`x${i}`}>
                    <line x1={sx(t)} x2={sx(t)} y1={M.t} y2={H - M.b} stroke="#e2e8f0" />
                    <text x={sx(t)} y={H - M.b + 16} fontSize="10" fill="#64748b" textAnchor="middle">{fmt(t, 2)}</text>
                </g>
            ))}
            {ty.map((t, i) => (
                <g key={`y${i}`}>
                    <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
                    <text x={M.l - 8} y={sy(t) + 3} fontSize="10" fill="#64748b" textAnchor="end">{fmt(t, 2)}</text>
                </g>
            ))}
            {/* Recetas por cluster */}
            {data.puntos.map(p => (
                <circle key={p.receta_id} cx={sx(p.x)} cy={sy(p.y)} r="4.5"
                    fill={COLOR_CLUSTER[p.cluster_codigo] || '#64748b'} fillOpacity="0.7">
                    <title>{`${p.nombre} · ${p.cluster_etiqueta} · S/ ${p.precio_soles} · Fe ${p.hierro_mg} mg`}</title>
                </circle>
            ))}
            {/* Centroides proyectados (rombos con borde oscuro) */}
            {data.centroides.map(c => (
                <g key={c.cluster_codigo} transform={`translate(${sx(c.x)},${sy(c.y)})`}>
                    <rect x="-7" y="-7" width="14" height="14" transform="rotate(45)"
                        fill={COLOR_CLUSTER[c.cluster_codigo] || '#64748b'} stroke="#0f172a" strokeWidth="1.5">
                        <title>{`Centroide ${c.cluster_etiqueta}`}</title>
                    </rect>
                </g>
            ))}
            <text x={W / 2} y={H - 10} fontSize="11" fill="#475569" textAnchor="middle">
                PC1 ({fmt(data.varianza_explicada.pc1 * 100, 1)}% de varianza)
            </text>
            <text x={14} y={H / 2} fontSize="11" fill="#475569" textAnchor="middle"
                transform={`rotate(-90 14 ${H / 2})`}>
                PC2 ({fmt(data.varianza_explicada.pc2 * 100, 1)}% de varianza)
            </text>
        </svg>
    );
};

// ==========================================
// GRÁFICO 3a: BARRAS DE TOTALES DEL GREEDY
// ==========================================
const BarrasGreedy = ({ variantes }) => {
    const W = 560, H = 320, M = { t: 16, r: 16, b: 44, l: 60 };
    const series = [
        { clave: 'costo_total_semana', label: 'Costo', color: COLOR_INDICADOR.costo },
        { clave: 'recoleccion_total_semana', label: 'Recolección', color: COLOR_INDICADOR.recoleccion },
        { clave: 'margen_proyectado', label: 'Margen', color: COLOR_INDICADOR.margen },
    ];
    const vals = variantes.flatMap(v => series.map(s => v.totales[s.clave] || 0));
    const max = Math.max(...vals, 1);
    const min = Math.min(...vals, 0);
    const sy = (v) => H - M.b - ((v - min) / ((max - min) || 1)) * (H - M.t - M.b);
    const anchoGrupo = (W - M.l - M.r) / variantes.length;
    const anchoBarra = Math.min(34, (anchoGrupo - 24) / series.length);
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {ticksEntre(min, max, 4).map((t, i) => (
                <g key={i}>
                    <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
                    <text x={M.l - 8} y={sy(t) + 3} fontSize="10" fill="#64748b" textAnchor="end">{fmt(t, 0)}</text>
                </g>
            ))}
            {/* Línea cero (el margen puede ser negativo) */}
            <line x1={M.l} x2={W - M.r} y1={sy(0)} y2={sy(0)} stroke="#94a3b8" strokeWidth="1.5" />
            {variantes.map((v, gi) => (
                <g key={v.variante}>
                    {series.map((s, si) => {
                        const valor = v.totales[s.clave] || 0;
                        const x = M.l + gi * anchoGrupo + 12 + si * (anchoBarra + 4);
                        const y = valor >= 0 ? sy(valor) : sy(0);
                        const h = Math.abs(sy(valor) - sy(0));
                        return (
                            <rect key={s.clave} x={x} y={y} width={anchoBarra} height={Math.max(h, 1)}
                                fill={s.color} rx="2">
                                <title>{`${v.etiqueta} · ${s.label}: S/ ${valor}`}</title>
                            </rect>
                        );
                    })}
                    <text x={M.l + gi * anchoGrupo + anchoGrupo / 2} y={H - M.b + 18}
                        fontSize="11" fill="#475569" textAnchor="middle" fontWeight="bold">
                        {v.etiqueta.replace(/[^\w\s-]/g, '').trim()}
                    </text>
                </g>
            ))}
            {/* Leyenda de indicadores */}
            {series.map((s, i) => (
                <g key={s.clave} transform={`translate(${M.l + i * 110}, ${M.t - 4})`}>
                    <rect width="10" height="10" fill={s.color} rx="2" />
                    <text x="14" y="9" fontSize="10" fill="#475569">{s.label} (S/)</text>
                </g>
            ))}
        </svg>
    );
};

// ==========================================
// GRÁFICO 3b: LÍNEAS DE SERIE DIARIA DEL GREEDY
// ==========================================
const LineasGreedy = ({ variantes, metrica }) => {
    const W = 560, H = 320, M = { t: 16, r: 16, b: 44, l: 60 };
    const dias = (variantes[0]?.serie_diaria || []).map(d => d.dia_nombre);
    const vals = variantes.flatMap(v => v.serie_diaria.map(d => d[metrica.clave] || 0));
    if (!dias.length || !vals.length) {
        return <p className="text-xs text-slate-500 p-6 text-center">Sin serie diaria disponible.</p>;
    }
    const [d0, d1] = dominio(vals, 0.12);
    const sx = (i) => M.l + (i / Math.max(dias.length - 1, 1)) * (W - M.l - M.r);
    const sy = (v) => H - M.b - ((v - d0) / (d1 - d0)) * (H - M.t - M.b);
    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {ticksEntre(d0, d1, 4).map((t, i) => (
                <g key={i}>
                    <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
                    <text x={M.l - 8} y={sy(t) + 3} fontSize="10" fill="#64748b" textAnchor="end">{fmt(t, 1)}</text>
                </g>
            ))}
            {dias.map((d, i) => (
                <text key={d} x={sx(i)} y={H - M.b + 16} fontSize="10" fill="#64748b" textAnchor="middle">{d.slice(0, 3)}</text>
            ))}
            {variantes.map(v => (
                <g key={v.variante}>
                    <polyline
                        fill="none"
                        stroke={COLOR_VARIANTE[v.variante] || '#64748b'}
                        strokeWidth="2.5"
                        points={v.serie_diaria.map((d, i) => `${sx(i)},${sy(d[metrica.clave] || 0)}`).join(' ')}
                    />
                    {v.serie_diaria.map((d, i) => (
                        <circle key={i} cx={sx(i)} cy={sy(d[metrica.clave] || 0)} r="3.5"
                            fill={COLOR_VARIANTE[v.variante] || '#64748b'}>
                            <title>{`${v.etiqueta} · ${d.dia_nombre}: ${d[metrica.clave]} ${metrica.label}`}</title>
                        </circle>
                    ))}
                </g>
            ))}
            <text x={W / 2} y={H - 8} fontSize="11" fill="#475569" textAnchor="middle">Día de la semana (cocina)</text>
            <text x={14} y={H / 2} fontSize="11" fill="#475569" textAnchor="middle"
                transform={`rotate(-90 14 ${H / 2})`}>
                {metrica.label}
            </text>
        </svg>
    );
};

// ==========================================
// VISTA PRINCIPAL DEL PANEL
// ==========================================
export const ModelosMLView = () => {
    const { usuario } = useAuth();

    const [estado, setEstado] = useState(null);
    const [rf, setRf] = useState(null);
    const [km, setKm] = useState(null);
    const [greedy, setGreedy] = useState(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');

    // Selectores de indicador
    const [tipoRF, setTipoRF] = useState('social');
    const [metricaSerie, setMetricaSerie] = useState(METRICAS_SERIE[0]);

    const cargarTodo = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const est = await api.getEstadoModelosML(usuario.id);
            setEstado(est);
            const [r1, r2, r3] = await Promise.all([
                est.random_forest?.suficiente ? api.getScatterRandomForest(usuario.id).catch(() => null) : Promise.resolve(null),
                est.kmeans ? api.getScatterKmeans(usuario.id).catch(() => null) : Promise.resolve(null),
                est.greedy ? api.getGreedyML(usuario.id).catch(() => null) : Promise.resolve(null),
            ]);
            setRf(r1); setKm(r2); setGreedy(r3);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [usuario.id]);

    useEffect(() => { cargarTodo(); }, [cargarTodo]);

    const tarjetaEstado = (icono, titulo, detalle, ok) => (
        <div className={`bg-white border rounded-xl p-3 text-center ${ok ? 'border-slate-200' : 'border-amber-300 bg-amber-50'}`}>
            <p className="flex items-center justify-center gap-1 text-sm font-bold text-slate-800">{icono} {titulo}</p>
            <p className="text-[11px] text-slate-500 mt-1">{detalle}</p>
        </div>
    );

    return (
        <div className="animate-in fade-in duration-300 space-y-6">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Activity className="text-emerald-600" size={22} /> Panel de Modelos de Machine Learning
                    </h2>
                    <p className="text-sm text-slate-500">
                        Validación gráfica de Random Forest (demanda), K-means (recetas) y Greedy Search (menús).
                    </p>
                </div>
                <button onClick={cargarTodo} disabled={cargando}
                    className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                    <RefreshCw size={16} className={cargando ? 'animate-spin' : ''} /> Actualizar
                </button>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {cargando ? (
                <div className="p-16 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={30} /></div>
            ) : (
                <>
                    {/* Estado de los modelos */}
                    {estado && (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {tarjetaEstado(<Sparkles size={14} className="text-red-600" />, 'Random Forest',
                                estado.random_forest?.suficiente
                                    ? `${estado.random_forest.dias_historial} días de historial · listo`
                                    : `Historial insuficiente (${estado.random_forest?.dias_historial || 0}/30 días)`,
                                estado.random_forest?.suficiente)}
                            {tarjetaEstado(<PieChart size={14} className="text-blue-600" />, 'K-means',
                                estado.kmeans
                                    ? `k=${estado.kmeans.k} · silhouette ${estado.kmeans.silhouette} · ${estado.kmeans.n_recetas} recetas`
                                    : 'Sin modelo activo (entrene en Clusters)',
                                !!estado.kmeans)}
                            {tarjetaEstado(<TrendingUp size={14} className="text-emerald-600" />, 'Greedy Search',
                                estado.greedy
                                    ? `Última sesión ${new Date(estado.greedy.fecha).toLocaleDateString('es-PE')} · ${estado.greedy.n_propuestas} propuestas`
                                    : 'Sin sesiones generadas',
                                !!estado.greedy)}
                        </div>
                    )}

                    {/* ===== GRÁFICO 1: RANDOM FOREST ===== */}
                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                        <h3 className="font-bold text-slate-800 text-sm mb-1">1. Random Forest — Demanda real vs predicha</h3>
                        <p className="text-[11px] text-slate-500 mb-3">
                            Variables del modelo: dia_semana, mes, dia_del_mes, es_fin_de_semana · Split temporal 80/20 ·
                            La línea punteada es la predicción perfecta (y = x).
                        </p>
                        {!rf ? (
                            <p className="text-xs text-slate-500 p-8 text-center">
                            Sin datos suficientes de padrón/ventas para entrenar Random Forest (mínimo 30 días).
                            </p>
                        ) : (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                <div className="lg:col-span-2">
                                    <ScatterRF puntos={rf.puntos} />
                                    <div className="flex flex-wrap gap-3 justify-center mt-2">
                                        {rf.tipos.map(t => (
                                            <button key={t} onClick={() => setTipoRF(t)}
                                                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                    tipoRF === t ? 'text-white' : 'text-slate-600 bg-slate-100 hover:bg-slate-200'}`}
                                                style={tipoRF === t ? { backgroundColor: COLOR_TIPO[t] } : {}}>
                                                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLOR_TIPO[t] }} />
                                                {t} · R² {rf.metricas[t]?.r2 ?? '—'} · MAE {rf.metricas[t]?.mae ?? '—'}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                {/* Importancia de variables del tipo seleccionado */}
                                <div className="bg-slate-50 rounded-lg p-3">
                                    <p className="text-xs font-bold text-slate-700 mb-2">
                                        Importancia de variables ({tipoRF})
                                    </p>
                                    {(rf.importancias[tipoRF] || []).map(iv => (
                                        <div key={iv.variable} className="mb-2">
                                            <div className="flex justify-between text-[11px] text-slate-600 mb-0.5">
                                                <span>{iv.variable}</span><span className="font-bold">{fmt(iv.importancia * 100, 1)}%</span>
                                            </div>
                                            <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                                                <div className="h-full rounded-full" style={{ width: `${iv.importancia * 100}%`, backgroundColor: COLOR_TIPO[tipoRF] }} />
                                            </div>
                                        </div>
                                    ))}
                                    <p className="text-[10px] text-slate-400 mt-2">
                                        {rf.n_dias_entrenamiento} días de entrenamiento · {rf.n_dias_test} días de prueba
                                        ({rf.rango_fechas[0]} → {rf.rango_fechas[1]})
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ===== GRÁFICO 2: K-MEANS PCA ===== */}
                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                        <h3 className="font-bold text-slate-800 text-sm mb-1">2. K-means — Recetas en espacio PCA (4 clusters)</h3>
                        <p className="text-[11px] text-slate-500 mb-3">
                            Variables originales: energia_kcal, hierro_mg, proteina_g, precio_soles ·
                            Los rombos con borde oscuro son los centroides de cada cluster.
                        </p>
                        {!km ? (
                            <p className="text-xs text-slate-500 p-8 text-center">
                                Sin modelo K-means activo. Entrene desde la pestaña "Clusters K-Means".
                            </p>
                        ) : (
                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                <div className="lg:col-span-2">
                                    <ScatterKmeans data={km} />
                                    <div className="flex flex-wrap gap-3 justify-center mt-2">
                                        {km.centroides.map(c => (
                                            <span key={c.cluster_codigo} className="flex items-center gap-1.5 text-[11px] font-bold text-slate-600">
                                                <span className="w-3 h-3 rotate-45" style={{ backgroundColor: COLOR_CLUSTER[c.cluster_codigo] }} />
                                                {c.cluster_etiqueta}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                                {/* Cargas de variables en PC1/PC2 */}
                                <div className="bg-slate-50 rounded-lg p-3">
                                    <p className="text-xs font-bold text-slate-700 mb-2">Cargas de variables (PCA)</p>
                                    <table className="w-full text-[11px]">
                                        <thead>
                                            <tr className="text-slate-500 border-b border-slate-200">
                                                <th className="text-left p-1">Variable</th>
                                                <th className="text-right p-1">PC1</th>
                                                <th className="text-right p-1">PC2</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {km.cargas.map(c => (
                                                <tr key={c.variable} className="border-b border-slate-100">
                                                    <td className="p-1 text-slate-700">{c.variable}</td>
                                                    <td className={`p-1 text-right font-bold ${c.pc1 >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmt(c.pc1, 3)}</td>
                                                    <td className={`p-1 text-right font-bold ${c.pc2 >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmt(c.pc2, 3)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                    <p className="text-[10px] text-slate-400 mt-2">
                                        Silhouette {km.silhouette} · Inercia {km.inercia} ·
                                        Varianza acumulada {fmt((km.varianza_explicada.pc1 + km.varianza_explicada.pc2) * 100, 1)}%
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* ===== GRÁFICO 3: GREEDY SEARCH ===== */}
                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                        <h3 className="font-bold text-slate-800 text-sm mb-1">3. Greedy Search — Comparativa de las 3 propuestas</h3>
                        <p className="text-[11px] text-slate-500 mb-3">
                            Indicadores de barras: costo_total_semana, recoleccion_total_semana, margen_proyectado ·
                            Indicadores de línea: {METRICAS_SERIE.map(m => m.clave).join(', ')}.
                        </p>
                        {!greedy || !greedy.variantes?.length ? (
                            <p className="text-xs text-slate-500 p-8 text-center">
                                Aún no hay sesiones del motor greedy. Genere propuestas desde "Propuestas de Menú".
                            </p>
                        ) : (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                <div>
                                    <BarrasGreedy variantes={greedy.variantes} />
                                </div>
                                <div>
                                    <div className="flex flex-wrap gap-1.5 mb-2">
                                        {METRICAS_SERIE.map(m => (
                                            <button key={m.clave} onClick={() => setMetricaSerie(m)}
                                                className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                    metricaSerie.clave === m.clave
                                                        ? 'bg-emerald-600 text-white'
                                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
                                                {m.label}
                                            </button>
                                        ))}
                                    </div>
                                    <LineasGreedy variantes={greedy.variantes} metrica={metricaSerie} />
                                    <div className="flex flex-wrap gap-3 justify-center mt-1">
                                        {greedy.variantes.map(v => (
                                            <span key={v.variante} className="flex items-center gap-1.5 text-[11px] font-bold text-slate-600">
                                                <span className="w-3 h-1 rounded" style={{ backgroundColor: COLOR_VARIANTE[v.variante] }} />
                                                {v.etiqueta}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};