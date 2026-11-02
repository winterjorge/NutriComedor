/**
components/ml/ModelosMLView.jsx
Objetivo: Panel de gráficos de Machine Learning con navegación por pestañas
(COM-99): Demanda (Random Forest), Recetas (K-means), Menús (Greedy Search) y
Precios (Random Forest de insumos, COM-105 v2). Incluye selector de modelo activo
oculto para GBM (COM-105 v2), MAPE (COM-91), vista de métricas crudas/limpias y
auditoría de atípicos (COM-95).
Historial:
COM-5 v4 / COM-8 v7: versión original del panel (3 gráficos SVG propios).
COM-60: scatter K-means con 6 variables nutricionales.
COM-76: precio fuera del tooltip y del rótulo del scatter K-means.
COM-91: MAPE en las métricas por tipo de comensal.
COM-92: selector de modelo (RF vs GBM) y comparación lado a lado
        (fix: TIPOS_COMENSAL local en lugar de la constante del backend).
COM-95: conmutador de métricas CRUDAS vs LIMPIAS + panel "Auditoría de atípicos".
COM-98 v2: se elimina el cuadro de comparación RF vs GBM y la segunda llamada al
        endpoint; la tabla de importancias pasa a ser consciente de la estrategia
        elegida por tipo (nota explicativa cuando no hay árboles); badge de
        estrategia activa.
COM-99: sistema de PESTAÑAS para alternar entre los gráficos de los modelos en
        lugar de apilarlos verticalmente.
COM-105 v2: nueva pestaña PRECIOS con dispersión real vs predicho en S/ por kg,
        pills por insumo con MAPE, tarjeta de métricas out-of-sample y serie
        histórica con marcadores de predicción; carga perezosa de la pestaña;
        selector GBM oculto en la UI (Random Forest como modelo visible).
COM-105 v3 (este archivo):
* PRECIOS: todas las pills son clickeables (se elimina la guarda que dejaba
  inertes a los insumos sin serie; el backend COM-105 v3 envía series para todos
  los insumos de metricas_por_insumo). El resaltado de pill activa deja de
  depender de la existencia de serie.
* MENÚS: los gráficos de barras y de líneas pasan de disposición lado a lado a
  APILADOS verticalmente, cada uno en su propia tarjeta con título, y se agrega
  un bloque de LEYENDA que explica cómo leer barras, líneas y colores.
Uso: Montada por App.jsx en la pestaña "Modelos ML" (gate por módulo 'modelos_ml').
Referencia: tickets COM-5 v4 / COM-8 v7 / COM-60 / COM-76 / COM-91 / COM-92 /
            COM-95 / COM-98 v2 / COM-99 / COM-105 v2 / COM-105 v3 (trazabilidad).
*/
import React, { useState, useEffect, useCallback } from 'react';
import {
    Activity, Loader2, AlertCircle, RefreshCw, TrendingUp, PieChart, Sparkles,
    GitCompare, ShieldAlert, BarChart3, Coins
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// ==========================================
// PALETAS Y CONSTANTES
// ==========================================
const COLOR_TIPO = { social: '#dc2626', afiliado: '#2563eb', normal: '#059669', cocinera: '#d97706' };
const COLOR_CLUSTER = { 1: '#dc2626', 2: '#2563eb', 3: '#16a34a', 4: '#d97706' };
const COLOR_VARIANTE = { NUTRI: '#dc2626', ECONO: '#d97706', BALANCE: '#059669' };
const COLOR_INDICADOR = { costo: '#64748b', recoleccion: '#059669', margen: '#2563eb' };
// COM-105 v2: paleta rotativa para colorear insumos en el scatter de precios
const PALETA_PRECIOS = ['#2563eb', '#dc2626', '#059669', '#d97706', '#7c3aed', '#0891b2', '#be185d', '#65a30d'];

const METRICAS_SERIE = [
    { clave: 'costo_total_dia', label: 'Costo del día (S/)' },
    { clave: 'recoleccion_proyectada', label: 'Recolección del día (S/)' },
    { clave: 'energia_kcal', label: 'Kcal por ración' },
    { clave: 'hierro_mg', label: 'Hierro por ración (mg)' },
];

const VARIABLES_KMEANS_DEFAULT = [
    'energia_kcal', 'hierro_mg', 'proteina_g', 'vitamina_a_ug', 'zinc_mg', 'carbohidratos_g',
];

// COM-92 (trazabilidad COM-105 v2): el catálogo de modelos de demanda sigue vivo en
// backend; la UI ya NO renderiza este selector (solo Random Forest es visible).
// const MODELOS_ML = [
//     { key: 'rf', label: 'Random Forest', descripcion: 'Ensemble de árboles, robusto a outliers' },
//     { key: 'gbm', label: 'Gradient Boosting', descripcion: 'Boosting secuencial, mejor para patrones temporales' },
// ];
const MODELO_DEMANDA_VISIBLE = 'rf';

// COM-92 fix / COM-95: tipos de comensal locales (la constante TIPOS vive en el backend)
const TIPOS_COMENSAL = ['social', 'afiliado', 'normal', 'cocinera'];

// COM-99 + COM-105 v2: pestañas del panel (4 modelos con gráfico propio)
const TABS = [
    { id: 'demanda', label: 'Demanda', icon: Activity, descripcion: 'RF de comensales' },
    { id: 'recetas', label: 'Recetas', icon: PieChart, descripcion: 'K-means nutricional' },
    { id: 'menus', label: 'Menús', icon: BarChart3, descripcion: 'Greedy Search' },
    { id: 'precios', label: 'Precios', icon: Coins, descripcion: 'RF de insumos' },
];

// ==========================================
// UTILIDADES SVG
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

// COM-95: selector de fuente de métricas (crudas vs limpias) con fallback seguro
const metricasDe = (modelo, tipo, vista) => {
    if (!modelo) return {};
    if (vista === 'limpias' && modelo.metricas_limpias?.[tipo]) return modelo.metricas_limpias[tipo];
    return modelo.metricas?.[tipo] || {};
};

// COM-98 v2: etiqueta legible de la estrategia elegida por tipo (info_split)
const etiquetaEstrategia = (estr) => {
    if (!estr) return null;
    if (estr === 'constante') return 'constante (mediana histórica)';
    if (estr.endsWith('->med3')) return 'persistencia robusta (mediana 3 días)';
    if (estr.endsWith('->rf_blend')) return 'Random Forest + mediana 3 días (blend)';
    if (estr.endsWith('->gbm_blend')) return 'Gradient Boosting + mediana 3 días (blend)';
    if (estr.endsWith('->rf')) return 'Random Forest puro';
    if (estr.endsWith('->gbm')) return 'Gradient Boosting puro';
    if (estr.endsWith('->ensemble')) return 'Ensemble RF + GBM + naive';
    return estr;
};

// COM-98 v2: true si la estrategia del tipo no usa árboles (no hay importancias reales)
const estrategiaSinArboles = (estr) =>
    !estr || estr === 'constante' || estr.endsWith('->med3');

// ==========================================
// GRÁFICO 1: DISPERSIÓN DEL MODELO ACTIVO (DEMANDA)
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
                Comensales PREDICHOS (raciones)
            </text>
        </svg>
    );
};

// ==========================================
// COM-95: PANEL DE AUDITORÍA DE ATÍPICOS
// ==========================================
const PanelAtipicos = ({ atipicos, nPorTipo }) => {
    const lista = atipicos || [];
    return (
        <div className="bg-white border border-amber-200 rounded-xl p-4">
            <h3 className="font-bold text-slate-800 text-sm mb-1 flex items-center gap-2">
                <ShieldAlert size={16} className="text-amber-600" />
                Auditoría de atípicos (COM-95)
            </h3>
            <p className="text-[11px] text-slate-500 mb-3">
                Registros detectados por z-score modificado (MAD) o fuera del rango operativo
                del comedor. El valor se <b>acota (winsoriza)</b> para entrenar y para los lags,
                pero <b>nunca se elimina</b> del libro de ventas: verifique estos días contra el
                cuaderno físico del comedor.
            </p>
            {nPorTipo && (
                <p className="text-[11px] text-slate-600 mb-2">
                    Atípicos por tipo: {Object.entries(nPorTipo).map(([t, n]) => `${t}: ${n}`).join(' · ')}
                </p>
            )}
            {lista.length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-4">
                    Sin atípicos detectados en el historial.
                </p>
            ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-left text-xs">
                        <thead>
                            <tr className="bg-slate-100 text-slate-600">
                                <th className="p-2 font-semibold">Fecha</th>
                                <th className="p-2 font-semibold">Tipo</th>
                                <th className="p-2 font-semibold text-right">Valor real</th>
                                <th className="p-2 font-semibold text-right">Acotado a</th>
                                <th className="p-2 font-semibold text-right">Límites [inf, sup]</th>
                                <th className="p-2 font-semibold">Motivo</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                            {lista.slice(0, 25).map((a, i) => (
                                <tr key={i} className="hover:bg-amber-50">
                                    <td className="p-2 text-slate-700 whitespace-nowrap">{a.fecha}</td>
                                    <td className="p-2 text-slate-700 capitalize">{a.tipo}</td>
                                    <td className="p-2 text-right font-bold text-red-600">{a.valor_real}</td>
                                    <td className="p-2 text-right text-slate-700">{a.valor_acotado}</td>
                                    <td className="p-2 text-right text-slate-500">[{a.limite_inf}, {a.limite_sup}]</td>
                                    <td className="p-2 text-slate-600">{a.motivo}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {lista.length > 25 && (
                        <p className="text-[10px] text-slate-400 p-2">
                            Mostrando 25 de {lista.length} registros atípicos.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
};

// ==========================================
// GRÁFICO 2: K-MEANS (RECETAS)
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
            {data.puntos.map(p => (
                <circle key={p.receta_id} cx={sx(p.x)} cy={sy(p.y)} r="4.5"
                    fill={COLOR_CLUSTER[p.cluster_codigo] || '#64748b'} fillOpacity="0.7">
                    <title>{`${p.nombre} · ${p.cluster_etiqueta} · Fe ${p.hierro_mg} mg · Prot ${p.proteina_g} g`}</title>
                </circle>
            ))}
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
// GRÁFICO 3: GREEDY (MENÚS)
// ==========================================
const BarrasGreedy = ({ variantes }) => {
    const W = 560, H = 320, M = { t: 24, r: 16, b: 44, l: 60 };
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
            {series.map((s, i) => (
                <g key={s.clave} transform={`translate(${M.l + i * 110}, ${M.t - 8})`}>
                    <rect width="10" height="10" fill={s.color} rx="2" />
                    <text x="14" y="9" fontSize="10" fill="#475569">{s.label} (S/)</text>
                </g>
            ))}
        </svg>
    );
};

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
// COM-105 v2: GRÁFICO 4A: DISPERSIÓN RF DE PRECIOS (S/ POR KG)
// ==========================================
const ScatterPrecios = ({ puntos }) => {
    const W = 560, H = 360, M = { t: 16, r: 16, b: 48, l: 64 };
    const vals = [...puntos.map(p => p.real_kg), ...puntos.map(p => p.predicho_kg)];
    const [d0, d1] = dominio(vals);
    const sx = (v) => M.l + ((v - d0) / (d1 - d0)) * (W - M.l - M.r);
    const sy = (v) => H - M.b - ((v - d0) / (d1 - d0)) * (H - M.t - M.b);
    const tks = ticksEntre(d0, d1, 4);
    const ids = [...new Set(puntos.map(p => p.insumo_id))];
    const colorDe = (id) => PALETA_PRECIOS[ids.indexOf(id) % PALETA_PRECIOS.length];

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {tks.map((t, i) => (
                <g key={i}>
                    <line x1={sx(t)} x2={sx(t)} y1={M.t} y2={H - M.b} stroke="#e2e8f0" />
                    <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
                    <text x={sx(t)} y={H - M.b + 16} fontSize="10" fill="#64748b" textAnchor="middle">{fmt(t, 1)}</text>
                    <text x={M.l - 8} y={sy(t) + 3} fontSize="10" fill="#64748b" textAnchor="end">{fmt(t, 1)}</text>
                </g>
            ))}
            <line x1={sx(d0)} y1={sy(d0)} x2={sx(d1)} y2={sy(d1)} stroke="#94a3b8" strokeDasharray="5 4" strokeWidth="1.5" />
            {puntos.map((p, i) => (
                <circle key={i} cx={sx(p.real_kg)} cy={sy(p.predicho_kg)} r="4"
                    fill={colorDe(p.insumo_id)} fillOpacity="0.75">
                    <title>{`${p.nombre} · ${p.fecha}: real S/ ${p.real_kg} / predicho S/ ${p.predicho_kg} por kg (error ${p.ape_pct}%)`}</title>
                </circle>
            ))}
            <text x={W / 2} y={H - 10} fontSize="11" fill="#475569" textAnchor="middle">
                Precio REAL del scraper (S/ por kg)
            </text>
            <text x={14} y={H / 2} fontSize="11" fill="#475569" textAnchor="middle"
                transform={`rotate(-90 14 ${H / 2})`}>
                Precio PREDICHO por Random Forest (S/ por kg)
            </text>
        </svg>
    );
};

// ==========================================
// COM-105 v2: GRÁFICO 4B: SERIE HISTÓRICA + PREDICCIONES EN CORTES
// ==========================================
const LineasPrecios = ({ serie }) => {
    const W = 560, H = 300, M = { t: 16, r: 16, b: 44, l: 64 };
    const hist = serie?.historia || [];
    if (!serie) {
        return <p className="text-xs text-slate-500 p-6 text-center">Seleccione un insumo para ver su serie.</p>;
    }
    if (!hist.length) {
        return <p className="text-xs text-slate-500 p-6 text-center">Sin histórico reciente para este insumo.</p>;
    }
    const idxPorFecha = {};
    hist.forEach((h, i) => { idxPorFecha[h.fecha] = i; });
    const preds = (serie.predicciones || []).filter(p => idxPorFecha[p.fecha] !== undefined);
    const vals = [...hist.map(h => h.precio_kg), ...preds.map(p => p.precio_kg)];
    const [d0, d1] = dominio(vals);
    const sx = (i) => M.l + (i / Math.max(hist.length - 1, 1)) * (W - M.l - M.r);
    const sy = (v) => H - M.b - ((v - d0) / (d1 - d0)) * (H - M.t - M.b);
    const marcas = [0, Math.floor((hist.length - 1) / 2), hist.length - 1];

    return (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
            {ticksEntre(d0, d1, 4).map((t, i) => (
                <g key={i}>
                    <line x1={M.l} x2={W - M.r} y1={sy(t)} y2={sy(t)} stroke="#e2e8f0" />
                    <text x={M.l - 8} y={sy(t) + 3} fontSize="10" fill="#64748b" textAnchor="end">{fmt(t, 2)}</text>
                </g>
            ))}
            {marcas.map(i => (
                <text key={i} x={sx(i)} y={H - M.b + 16} fontSize="10" fill="#64748b" textAnchor="middle">
                    {hist[i].fecha.slice(5)}
                </text>
            ))}
            <polyline fill="none" stroke="#2563eb" strokeWidth="2"
                points={hist.map((h, i) => `${sx(i)},${sy(h.precio_kg)}`).join(' ')} />
            {hist.map((h, i) => (
                <circle key={h.fecha} cx={sx(i)} cy={sy(h.precio_kg)} r="2.5" fill="#2563eb">
                    <title>{`${h.fecha}: S/ ${h.precio_kg} por kg (real)`}</title>
                </circle>
            ))}
            {preds.map(p => (
                <g key={p.fecha} transform={`translate(${sx(idxPorFecha[p.fecha])},${sy(p.precio_kg)})`}>
                    <rect x="-5" y="-5" width="10" height="10" transform="rotate(45)"
                        fill="#dc2626" stroke="#0f172a" strokeWidth="1">
                        <title>{`Predicho ${p.fecha}: S/ ${p.precio_kg} por kg`}</title>
                    </rect>
                </g>
            ))}
            <text x={W / 2} y={H - 8} fontSize="11" fill="#475569" textAnchor="middle">
                Histórico real del scraper, últimos 60 días
            </text>
            <text x={14} y={H / 2} fontSize="11" fill="#475569" textAnchor="middle"
                transform={`rotate(-90 14 ${H / 2})`}>
                Precio (S/ por kg)
            </text>
        </svg>
    );
};

// ==========================================
// VISTA PRINCIPAL (COM-99 + COM-105 v2 + COM-105 v3)
// ==========================================
export const ModelosMLView = () => {
    const { usuario } = useAuth();
    const [estado, setEstado] = useState(null);
    const [rf, setRf] = useState(null);
    const [km, setKm] = useState(null);
    const [greedy, setGreedy] = useState(null);
    const [precio, setPrecio] = useState(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    // COM-105 v2: estado propio de la carga perezosa de la pestaña Precios
    const [precioCargando, setPrecioCargando] = useState(false);
    const [precioError, setPrecioError] = useState('');

    // Selectores por modelo
    const [tipoRF, setTipoRF] = useState('social');
    const [metricaSerie, setMetricaSerie] = useState(METRICAS_SERIE[0]);
    // COM-105 v2: el modelo de demanda visible es SIEMPRE Random Forest; el GBM queda
    // implementado en backend y seleccionable por API, pero la UI no lo expone.
    const modeloSeleccionado = MODELO_DEMANDA_VISIBLE;
    const [vistaMetricas, setVistaMetricas] = useState('crudas');
    // COM-105 v2: insumo seleccionado para la serie histórica de la pestaña Precios
    const [precioSel, setPrecioSel] = useState(null);

    // COM-99: pestaña activa del panel
    const [tabActiva, setTabActiva] = useState('demanda');

    // COM-105 v3: el payload de precios ya NO forma parte de la carga inicial del
    // panel; se solicita al abrir la pestaña Precios (carga perezosa con caché de
    // componente). Las otras tres pestañas cargan en paralelo como antes.
    const cargarTodo = useCallback(async () => {
        setCargando(true);
        setError('');
        setPrecio(null);          // COM-105 v2: invalida también el payload de precios
        setPrecioError('');
        try {
            const est = await api.getEstadoModelosML(usuario.id);
            setEstado(est);
            const [r1, r2, r3] = await Promise.all([
                est.random_forest?.suficiente ? api.getScatterRandomForest(usuario.id, MODELO_DEMANDA_VISIBLE).catch(() => null) : Promise.resolve(null),
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

    // COM-105 v2: carga perezosa y reutilizable del gráfico de precios
    const cargarPrecios = useCallback(async () => {
        if (precioCargando) return;
        setPrecioCargando(true);
        setPrecioError('');
        try {
            const data = await api.getScatterRFPrecios(usuario.id);
            setPrecio(data);
            if (data?.series?.length) setPrecioSel(data.series[0].insumo_id);
        } catch (e) {
            setPrecioError(e.message);
        } finally {
            setPrecioCargando(false);
        }
    }, [usuario.id, precioCargando]);

    useEffect(() => { cargarTodo(); }, [cargarTodo]);

    // COM-105 v2: al entrar a la pestaña Precios sin payload, se solicita una sola vez
    useEffect(() => {
        if (tabActiva === 'precios' && !precio && !precioCargando && !cargando) {
            cargarPrecios();
        }
    }, [tabActiva, precio, precioCargando, cargando, cargarPrecios]);

    const tarjetaEstado = (icono, titulo, detalle, ok) => (
        <div className={`bg-white border rounded-xl p-3 text-center ${ok ? 'border-slate-200' : 'border-amber-300 bg-amber-50'}`}>
            <p className="flex items-center justify-center gap-1 text-sm font-bold text-slate-800">{icono} {titulo}</p>
            <p className="text-[11px] text-slate-500 mt-1">{detalle}</p>
        </div>
    );

    // COM-98 v2: estrategia activa del tipo seleccionado (viene del holdout interno)
    const estrActiva = rf?.info_split?.estrategias_usadas?.[tipoRF] || null;
    const sinArboles = estrategiaSinArboles(estrActiva);
    const importanciasTipo = rf?.importancias?.[tipoRF] || [];
    // COM-105 v2: serie seleccionada de la pestaña Precios con fallback seguro
    const serieSel = precio?.series?.find(s => s.insumo_id === precioSel) || precio?.series?.[0] || null;

    return (
        <div className="animate-in fade-in duration-300 space-y-6">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Activity className="text-emerald-600" size={22} /> Panel de Modelos de Machine Learning
                    </h2>
                    <p className="text-sm text-slate-500">
                        Validación gráfica de los cuatro motores: demanda, recetas, menús y precios.
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
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
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
                            {tarjetaEstado(<Coins size={14} className="text-amber-600" />, 'RF de Precios',
                                estado.random_forest_precios?.suficiente
                                    ? `${estado.random_forest_precios.dias_historial} días con precios · listo`
                                    : `Histórico insuficiente (${estado.random_forest_precios?.dias_historial || 0}/10 días)`,
                                estado.random_forest_precios?.suficiente)}
                        </div>
                    )}

                    {/* COM-99: sistema de pestañas */}
                    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                        <div className="flex flex-wrap border-b border-slate-200 bg-slate-50">
                            {TABS.map(tab => {
                                const Icon = tab.icon;
                                const isActive = tabActiva === tab.id;
                                return (
                                    <button
                                        key={tab.id}
                                        onClick={() => setTabActiva(tab.id)}
                                        className={`flex-1 min-w-[140px] px-4 py-3 flex items-center justify-center gap-2 transition-all ${
                                            isActive
                                                ? 'bg-white border-b-2 border-emerald-600 text-emerald-700'
                                                : 'text-slate-600 hover:bg-slate-100'
                                        }`}
                                    >
                                        <Icon size={18} />
                                        <div className="text-left">
                                            <div className="font-bold text-sm">{tab.label}</div>
                                            <div className="text-[10px] opacity-75">{tab.descripcion}</div>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>

                        <div className="p-6">
                            {/* ===== TAB: DEMANDA (Random Forest) ===== */}
                            {tabActiva === 'demanda' && (
                                <div className="space-y-4">
                                    <h3 className="font-bold text-slate-800 text-lg flex items-center gap-2">
                                        <Activity size={20} className="text-red-600" />
                                        Modelo de Demanda — Predicción de Comensales
                                    </h3>

                                    {/* COM-105 v2: sin selector RF/GBM; solo métricas crudas/limpias */}
                                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                                        <h4 className="font-bold text-slate-800 text-sm mb-2 flex items-center gap-2">
                                            <GitCompare size={16} className="text-emerald-600" />
                                            Modelo activo de demanda
                                        </h4>
                                        <p className="text-xs text-slate-600 mb-3">
                                            Modelo activo: <span className="font-bold text-slate-700">Random Forest</span>.
                                            El Gradient Boosting permanece implementado en backend como referencia
                                            comparativa y no se expone en la interfaz.
                                        </p>
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span className="text-[11px] font-semibold text-slate-600">Métricas:</span>
                                            <button
                                                onClick={() => setVistaMetricas('crudas')}
                                                className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                    vistaMetricas === 'crudas' ? 'bg-slate-700 text-white' : 'bg-white text-slate-600 hover:bg-slate-200 border border-slate-300'}`}>
                                                Crudas (todo el test)
                                            </button>
                                            <button
                                                onClick={() => setVistaMetricas('limpias')}
                                                className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                    vistaMetricas === 'limpias' ? 'bg-emerald-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-200 border border-slate-300'}`}>
                                                Limpias (sin días atípicos)
                                            </button>
                                        </div>
                                    </div>

                                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                                        <h4 className="font-bold text-slate-800 text-sm mb-1">
                                            Demanda real vs predicha
                                        </h4>
                                        <p className="text-[11px] text-slate-500 mb-3">
                                            Features por día operativo y por tipo: lags 1/2/5, medianas y medias móviles,
                                            EWMA, momentum, ventana de pago y calendario. Split temporal configurable.
                                            La línea punteada es la predicción perfecta (y = x).
                                        </p>
                                        {!rf ? (
                                            <p className="text-xs text-slate-500 p-8 text-center">
                                                Sin datos suficientes para entrenar (mínimo 30 días).
                                            </p>
                                        ) : (
                                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                                <div className="lg:col-span-2">
                                                    <ScatterRF puntos={rf.puntos} />
                                                    <div className="flex flex-wrap gap-3 justify-center mt-2">
                                                        {TIPOS_COMENSAL.map(t => {
                                                            const m = metricasDe(rf, t, vistaMetricas);
                                                            const mapeText = m.mape !== null && m.mape !== undefined ? ` · MAPE ${m.mape}%` : '';
                                                            return (
                                                                <button key={t} onClick={() => setTipoRF(t)}
                                                                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                                        tipoRF === t ? 'text-white' : 'text-slate-600 bg-slate-100 hover:bg-slate-200'
                                                                    }`}
                                                                    style={tipoRF === t ? { backgroundColor: COLOR_TIPO[t] } : {}}>
                                                                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLOR_TIPO[t] }} />
                                                                    {t} · R² {m.r2 ?? '—'} · MAE {m.mae ?? '—'}{mapeText}
                                                                </button>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                                <div className="bg-slate-50 rounded-lg p-3">
                                                    <p className="text-xs font-bold text-slate-700 mb-2 flex flex-wrap items-center gap-2">
                                                        Importancia de variables ({tipoRF})
                                                        {estrActiva && (
                                                            <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full text-[10px] font-bold">
                                                                {etiquetaEstrategia(estrActiva)}
                                                            </span>
                                                        )}
                                                    </p>
                                                    {sinArboles ? (
                                                        <p className="text-[11px] text-slate-500 leading-relaxed mt-1">
                                                            La estrategia activa para <b className="capitalize">{tipoRF}</b> es{' '}
                                                            <b>{etiquetaEstrategia(estrActiva)}</b>: la predicción sigue el nivel
                                                            reciente de la serie o su mediana histórica sin usar un modelo de
                                                            árboles, por lo que <b>no hay importancias de variables que mostrar</b>.
                                                            El motor eligió esta estrategia en su validación interna porque supera
                                                            al RF en esta serie (COM-98).
                                                        </p>
                                                    ) : (
                                                        importanciasTipo.map(iv => (
                                                            <div key={iv.variable} className="mb-2">
                                                                <div className="flex justify-between text-[11px] text-slate-600 mb-0.5">
                                                                    <span>{iv.variable}</span><span className="font-bold">{fmt(iv.importancia * 100, 1)}%</span>
                                                                </div>
                                                                <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                                                                    <div className="h-full rounded-full" style={{ width: `${iv.importancia * 100}%`, backgroundColor: COLOR_TIPO[tipoRF] }} />
                                                                </div>
                                                            </div>
                                                        ))
                                                    )}
                                                    <p className="text-[10px] text-slate-400 mt-2">
                                                        {rf.n_dias_entrenamiento} días de entrenamiento · {rf.n_dias_test} días de prueba
                                                        ({rf.rango_fechas?.[0]} → {rf.rango_fechas?.[1]})
                                                    </p>
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {rf && (rf.atipicos_detectados?.length > 0 || rf.info_split?.n_atipicos_por_tipo) && (
                                        <PanelAtipicos
                                            atipicos={rf.atipicos_detectados}
                                            nPorTipo={rf.info_split?.n_atipicos_por_tipo}
                                        />
                                    )}
                                </div>
                            )}

                            {/* ===== TAB: RECETAS (K-means) ===== */}
                            {tabActiva === 'recetas' && (
                                <div className="space-y-4">
                                    <h3 className="font-bold text-slate-800 text-lg flex items-center gap-2">
                                        <PieChart size={20} className="text-blue-600" />
                                        Modelo de Recetas — Clustering Nutricional
                                    </h3>

                                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                                        <h4 className="font-bold text-slate-800 text-sm mb-1">Recetas en espacio PCA (4 clusters)</h4>
                                        <p className="text-[11px] text-slate-500 mb-3">
                                            Variables originales: {(km?.variables || VARIABLES_KMEANS_DEFAULT).join(', ')} ·
                                            Los rombos con borde oscuro son los centroides de cada cluster.
                                            {km?.espacio_nombre ? ` Espacio de entrenamiento: ${km.espacio_nombre}.` : ''}
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
                                </div>
                            )}

                            {/* ===== TAB: MENÚS (Greedy Search) — COM-105 v3: apilado + leyenda ===== */}
                            {tabActiva === 'menus' && (
                                <div className="space-y-4">
                                    <h3 className="font-bold text-slate-800 text-lg flex items-center gap-2">
                                        <BarChart3 size={20} className="text-emerald-600" />
                                        Modelo de Menús — Optimización de Propuestas
                                    </h3>

                                    {!greedy || !greedy.variantes?.length ? (
                                        <p className="text-xs text-slate-500 p-8 text-center bg-white border border-slate-200 rounded-xl">
                                            Aún no hay sesiones del motor greedy. Genere propuestas desde "Propuestas de Menú".
                                        </p>
                                    ) : (
                                        <div className="space-y-5">
                                            {/* COM-105 v3: leyenda explicativa de los dos gráficos */}
                                            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                                                <p className="text-xs font-bold text-slate-700 mb-1">Cómo leer los gráficos de esta pestaña</p>
                                                <ul className="text-[11px] text-slate-600 space-y-1 ml-4 list-disc">
                                                    <li>
                                                        <b>Gráfico de barras:</b> totales de la semana completa por propuesta.
                                                        Gris = costo total de compras, verde = recolección proyectada por ventas,
                                                        azul = margen semanal; un margen negativo se dibuja por debajo de la línea cero.
                                                    </li>
                                                    <li>
                                                        <b>Gráfico de líneas:</b> serie diaria del indicador que elija con los botones,
                                                        para las tres propuestas; cada punto es un día de cocina de la semana evaluada.
                                                    </li>
                                                    <li>
                                                        <b>Colores de propuesta:</b> rojo NutriMax prioriza nutrición, ámbar EconoMax
                                                        prioriza costo y verde BalanceMax busca el equilibrio entre ambos.
                                                    </li>
                                                </ul>
                                            </div>

                                            {/* COM-105 v3: gráfico de barras en tarjeta propia, apilado */}
                                            <div className="bg-white border border-slate-200 rounded-xl p-4">
                                                <h4 className="font-bold text-slate-800 text-sm mb-1">
                                                    Totales semanales por propuesta
                                                </h4>
                                                <p className="text-[11px] text-slate-500 mb-3">
                                                    Indicadores: costo_total_semana, recoleccion_total_semana y margen_proyectado,
                                                    todos en soles de la semana completa.
                                                </p>
                                                <BarrasGreedy variantes={greedy.variantes} />
                                            </div>

                                            {/* COM-105 v3: gráfico de líneas en tarjeta propia, debajo del de barras */}
                                            <div className="bg-white border border-slate-200 rounded-xl p-4">
                                                <h4 className="font-bold text-slate-800 text-sm mb-1">
                                                    Serie diaria por propuesta
                                                </h4>
                                                <p className="text-[11px] text-slate-500 mb-3">
                                                    Elija el indicador a graficar; la línea de cada propuesta muestra su valor
                                                    por día de cocina.
                                                </p>
                                                <div className="flex flex-wrap gap-1.5 mb-3">
                                                    {METRICAS_SERIE.map(m => (
                                                        <button key={m.clave} onClick={() => setMetricaSerie(m)}
                                                            className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                                metricaSerie.clave === m.clave
                                                                    ? 'bg-emerald-600 text-white'
                                                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                                            }`}>
                                                            {m.label}
                                                        </button>
                                                    ))}
                                                </div>
                                                <LineasGreedy variantes={greedy.variantes} metrica={metricaSerie} />
                                                <div className="flex flex-wrap gap-3 justify-center mt-2">
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
                            )}

                            {/* ===== TAB: PRECIOS (RF de insumos, COM-105 v2 + v3) ===== */}
                            {tabActiva === 'precios' && (
                                <div className="space-y-4">
                                    <h3 className="font-bold text-slate-800 text-lg flex items-center gap-2">
                                        <Coins size={20} className="text-amber-600" />
                                        Modelo de Precios — Random Forest de Insumos
                                    </h3>

                                    {/* COM-105 v2: estados de carga perezosa y de error con reintento */}
                                    {precioCargando ? (
                                        <div className="p-10 text-center bg-white border border-slate-200 rounded-xl">
                                            <Loader2 className="animate-spin mx-auto text-amber-600" size={26} />
                                            <p className="text-xs text-slate-500 mt-2">
                                                Evaluando cortes out-of-sample del modelo de precios.
                                                La primera apertura puede tardar algunos segundos; las siguientes
                                                usan la caché de 10 minutos.
                                            </p>
                                        </div>
                                    ) : precioError ? (
                                        <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-center space-y-3">
                                            <p className="text-sm text-red-700 flex items-center justify-center gap-2">
                                                <AlertCircle size={16} /> {precioError}
                                            </p>
                                            <button onClick={cargarPrecios}
                                                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold transition-colors">
                                                Reintentar evaluación
                                            </button>
                                        </div>
                                    ) : !precio || !precio.puntos?.length ? (
                                        <p className="text-xs text-slate-500 p-8 text-center bg-white border border-slate-200 rounded-xl">
                                            Sin histórico de precios suficiente para evaluar el modelo.
                                            Espere nuevas corridas del scraper o cargue precios manuales.
                                        </p>
                                    ) : (
                                        <>
                                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                                                <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-4">
                                                    <h4 className="font-bold text-slate-800 text-sm mb-1">
                                                        Precio real vs predicho por insumo
                                                    </h4>
                                                    <p className="text-[11px] text-slate-500 mb-3">
                                                        Ambos ejes en {precio.unidad_scatter} para comparar unidades de compra
                                                        heterogéneas. La línea punteada es la predicción perfecta (y = x).
                                                        Evaluación out-of-sample sobre {precio.metricas.n_cortes} cortes temporales.
                                                    </p>
                                                    <ScatterPrecios puntos={precio.puntos} />
                                                    <div className="flex flex-wrap gap-2 justify-center mt-2">
                                                        {/* COM-105 v3: TODAS las pills son clickeables; el backend envía
                                                            serie para cada insumo de metricas_por_insumo. */}
                                                        {(precio.metricas_por_insumo || []).map(m => (
                                                            <button key={m.insumo_id}
                                                                onClick={() => setPrecioSel(m.insumo_id)}
                                                                className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                                    precioSel === m.insumo_id
                                                                        ? 'text-white bg-amber-600'
                                                                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                                                }`}
                                                                title="Ver serie histórica y predicciones de este insumo">
                                                                {m.nombre} · MAPE {m.mape_pct}% · n={m.n}
                                                            </button>
                                                        ))}
                                                    </div>
                                                </div>
                                                <div className="bg-slate-50 rounded-xl p-4 space-y-2">
                                                    <p className="text-xs font-bold text-slate-700">Métricas out-of-sample</p>
                                                    <p className="text-[11px] text-slate-600 flex justify-between">
                                                        <span>MAPE promedio</span><span className="font-bold text-slate-800">{precio.metricas.mape_pct}%</span>
                                                    </p>
                                                    <p className="text-[11px] text-slate-600 flex justify-between">
                                                        <span>MAPE mediano</span><span className="font-bold text-slate-800">{precio.metricas.mape_mediano_pct}%</span>
                                                    </p>
                                                    <p className="text-[11px] text-slate-600 flex justify-between">
                                                        <span>MAE (S/ por kg)</span><span className="font-bold text-slate-800">{precio.metricas.mae_soles_por_kg}</span>
                                                    </p>
                                                    <p className="text-[11px] text-slate-600 flex justify-between">
                                                        <span>Puntos evaluados</span><span className="font-bold text-slate-800">{precio.metricas.n_puntos}</span>
                                                    </p>
                                                    <p className="text-[11px] text-slate-600 flex justify-between">
                                                        <span>Insumos evaluados</span><span className="font-bold text-slate-800">{precio.metricas.n_insumos}</span>
                                                    </p>
                                                    <p className="text-[11px] text-slate-600 flex justify-between">
                                                        <span>Confianza promedio (in-sample)</span>
                                                        <span className="font-bold text-slate-800">{precio.metricas.confianza_promedio_insample}%</span>
                                                    </p>
                                                    {precio.universo_evaluado && (
                                                        <p className="text-[10px] text-slate-500 leading-relaxed pt-1 border-t border-slate-200">
                                                            Universo: {precio.universo_evaluado.criterio}. Se evaluaron{' '}
                                                            {precio.universo_evaluado.n_insumos_evaluados} insumos en{' '}
                                                            {precio.universo_evaluado.n_cortes} cortes separados{' '}
                                                            {precio.universo_evaluado.paso_dias} días.
                                                        </p>
                                                    )}
                                                    <p className="text-[10px] text-slate-500 leading-relaxed pt-1 border-t border-slate-200">
                                                        Cortes: {(precio.metricas.cortes || []).join(', ')}. {precio.nota}
                                                    </p>
                                                    <p className="text-[10px] text-slate-400">{precio.modelo}</p>
                                                </div>
                                            </div>

                                            <div className="bg-white border border-slate-200 rounded-xl p-4">
                                                <h4 className="font-bold text-slate-800 text-sm mb-1 flex flex-wrap items-center gap-2">
                                                    Serie histórica y predicciones en los cortes
                                                    {serieSel && (
                                                        <span className="px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded-full text-[10px] font-bold">
                                                            {serieSel.nombre} ({serieSel.unidad})
                                                        </span>
                                                    )}
                                                </h4>
                                                <p className="text-[11px] text-slate-500 mb-3">
                                                    Línea azul: precio real del scraper en S/ por kg · Rombos rojos: predicción
                                                    del modelo en cada corte evaluado.
                                                </p>
                                                <div className="flex flex-wrap gap-1.5 mb-2">
                                                    {(precio.series || []).map(s => (
                                                        <button key={s.insumo_id} onClick={() => setPrecioSel(s.insumo_id)}
                                                            className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-colors ${
                                                                serieSel?.insumo_id === s.insumo_id
                                                                    ? 'bg-amber-600 text-white'
                                                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                                            }`}>
                                                            {s.nombre}
                                                        </button>
                                                    ))}
                                                </div>
                                                <LineasPrecios serie={serieSel} />
                                            </div>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};