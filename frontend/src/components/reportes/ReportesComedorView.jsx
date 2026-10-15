/**
components/reportes/ReportesComedorView.jsx
Objetivo: COM-77: vista de los 5 REPORTES OPERATIVOS del comedor (Directiva/Tesorero/
      Operativo) y del drill-down municipal (solo lectura):
        A) Estado de Resultados y Margen Real (semanal/mensual).
        B) Tablero de Consumo de Subsidio con fecha estimada de quiebre.
        C) Inteligencia de Compras (ahorro por IA/scraper vs promedio histórico).
        D) Merma y Precisión de Demanda (proyectado IA vs atendido POS).
        E) Semáforo Nutricional y Anemia Cero (metas parametrizables).
Historial:
COM-77 (este archivo): versión original.
Permisos: el backend valida el alcance (403); la vista recibe `alcance` ya resuelto.
Uso: Montada por ReportesView.jsx en el segmento "Reportes operativos (COM-77)".
Referencia: ticket COM-77 (solo trazabilidad).
*/
import React, { useState, useCallback } from 'react';
import {
    Loader2, AlertCircle, Wallet, Gift, Lightbulb, Scale, Heart,
    TrendingDown, TrendingUp, Calendar, RefreshCw
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

const SUBREPORTES = [
    { clave: 'estado', label: 'Estado de Resultados', icon: Wallet },
    { clave: 'subsidio', label: 'Consumo de Subsidio', icon: Gift },
    { clave: 'compras', label: 'Inteligencia de Compras', icon: Lightbulb },
    { clave: 'merma', label: 'Merma y Demanda', icon: Scale },
    { clave: 'nutricional', label: 'Semáforo Nutricional', icon: Heart },
];

const fmtS = (v) => (v === null || v === undefined ? '—' : `S/ ${Number(v).toFixed(2)}`);
const fmtN = (v, d = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

const badgeSemaforo = (estado) => {
    const map = {
        OK: 'bg-emerald-100 text-emerald-700',
        POR_AGOTAR: 'bg-amber-100 text-amber-700',
        AGOTADO: 'bg-red-100 text-red-700',
        SIN_CONSUMO: 'bg-slate-100 text-slate-600',
        SIN_REGISTRO_POS: 'bg-slate-100 text-slate-600',
        EN_RIESGO: 'bg-amber-100 text-amber-700',
        CRITICO: 'bg-red-100 text-red-700',
        SIN_DATOS: 'bg-slate-100 text-slate-600',
    };
    return <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${map[estado] || map.SIN_DATOS}`}>{estado}</span>;
};

const Tarjeta = ({ label, valor, sub, tono = 'text-slate-800' }) => (
    <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
        <p className="text-[11px] text-slate-500 uppercase font-semibold">{label}</p>
        <p className={`text-lg font-bold ${tono}`}>{valor}</p>
        {sub && <p className="text-[10px] text-slate-400">{sub}</p>}
    </div>
);

export const ReportesComedorView = ({ alcance, comedorForzado = null }) => {
    const { usuario } = useAuth();
    const ahora = new Date();
    const [comedorId, setComedorId] = useState(comedorForzado || alcance?.comedor_fijo || alcance?.comedores?.[0]?.id || '');
    const [anio, setAnio] = useState(ahora.getFullYear());
    const [mes, setMes] = useState(ahora.getMonth() + 1);
    const [sub, setSub] = useState('estado');
    const [data, setData] = useState(null);
    const [cargando, setCargando] = useState(false);
    const [error, setError] = useState('');

    React.useEffect(() => { if (comedorForzado) setComedorId(comedorForzado); }, [comedorForzado]);

    const generar = useCallback(async () => {
        if (!comedorId) { setError('Seleccione un comedor.'); return; }
        setCargando(true); setError(''); setData(null);
        const params = { usuario_solicitante_id: usuario.id, comedor_id: Number(comedorId), anio, mes };
        try {
            const fn = {
                estado: api.getReporteEstadoResultados,
                subsidio: api.getReporteConsumoSubsidio,
                compras: api.getReporteInteligenciaCompras,
                merma: api.getReporteMermaDemanda,
                nutricional: api.getReporteSemaforoNutricional,
            }[sub];
            setData(await fn(params));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [comedorId, anio, mes, sub, usuario.id]);

    return (
        <div className="space-y-4">
            {/* Selectores */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
                <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">Comedor</label>
                    <select value={comedorId} disabled={!!comedorForzado}
                        onChange={(e) => { setComedorId(e.target.value); setData(null); }}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500 disabled:bg-slate-50">
                        {(alcance?.comedores || []).map(c => <option key={c.id} value={c.id}>{c.nombre}{c.zona ? ` · ${c.zona}` : ''}</option>)}
                    </select>
                </div>
                <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">Mes</label>
                    <select value={mes} onChange={(e) => { setMes(Number(e.target.value)); setData(null); }}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500">
                        {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                    </select>
                </div>
                <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">Año</label>
                    <input type="number" min="2020" max="2100" value={anio}
                        onChange={(e) => { setAnio(Number(e.target.value)); setData(null); }}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                </div>
                <div className="md:col-span-2 flex items-end gap-2">
                    <button onClick={generar} disabled={cargando}
                        className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                        {cargando ? <Loader2 className="animate-spin" size={15} /> : <Calendar size={15} />}
                        Generar reporte
                    </button>
                </div>
            </div>

            {/* Sub-reportes */}
            <div className="flex flex-wrap gap-1.5">
                {SUBREPORTES.map(s => {
                    const Icon = s.icon;
                    return (
                        <button key={s.clave} onClick={() => { setSub(s.clave); setData(null); }}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${sub === s.clave ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'}`}>
                            <Icon size={13} /> {s.label}
                        </button>
                    );
                })}
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}
            {cargando && <div className="p-10 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={26} /></div>}

            {!cargando && data && sub === 'estado' && (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Tarjeta label="Ingreso real (tarifa)" valor={fmtS(data.totales.ingreso_real_tarifa)} sub={`caja: ${fmtS(data.totales.ingreso_real_caja)}`} />
                        <Tarjeta label="Ingreso proyectado" valor={fmtS(data.totales.ingreso_proyectado)} />
                        <Tarjeta label="Costo ejecutado" valor={fmtS(data.totales.costo_ejecutado)} sub={`sin subsidio: ${fmtS(data.totales.costo_sin_subsidio)}`} />
                        <Tarjeta label="Subsidio consumido" valor={fmtS(data.totales.valor_subsidio_consumido)} tono="text-red-600" />
                        <Tarjeta label="Margen ejecutado" valor={fmtS(data.totales.margen_ejecutado)} tono={data.totales.margen_ejecutado >= 0 ? 'text-emerald-700' : 'text-red-600'} sub={`${fmtN(data.totales.margen_pct_ejecutado)}%`} />
                        <Tarjeta label="Margen proyectado" valor={fmtS(data.totales.margen_proyectado)} />
                        <Tarjeta label="Objetivo semanal" valor={`${fmtN(data.totales.margen_objetivo_pct)}%`} />
                        <Tarjeta label="¿Cumple objetivo?" valor={data.totales.cumple_objetivo ? 'SÍ' : 'NO'} tono={data.totales.cumple_objetivo ? 'text-emerald-700' : 'text-red-600'} />
                    </div>
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                        <table className="w-full text-left text-xs">
                            <thead><tr className="bg-slate-100 text-slate-600">
                                <th className="p-2">Semana</th><th className="p-2">Estado</th>
                                <th className="p-2 text-right">Ingreso proy.</th><th className="p-2 text-right">Ingreso real</th>
                                <th className="p-2 text-right">Costo</th><th className="p-2 text-right">Margen ejec.</th>
                                <th className="p-2 text-right">Margen %</th><th className="p-2 text-center">Objetivo</th>
                            </tr></thead>
                            <tbody className="divide-y divide-slate-100">
                                {data.semanas.map(s => (
                                    <tr key={s.plan_id} className="hover:bg-slate-50">
                                        <td className="p-2 font-medium">{s.semana}</td>
                                        <td className="p-2">{s.estado}</td>
                                        <td className="p-2 text-right">{fmtS(s.ingreso_proyectado)}</td>
                                        <td className="p-2 text-right">{fmtS(s.ingreso_real_tarifa)}</td>
                                        <td className="p-2 text-right">{fmtS(s.costo_ejecutado)}</td>
                                        <td className={`p-2 text-right font-bold ${s.margen_ejecutado >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmtS(s.margen_ejecutado)}</td>
                                        <td className="p-2 text-right">{fmtN(s.margen_pct_ejecutado)}%</td>
                                        <td className="p-2 text-center">{s.cumple_objetivo ? '✅' : '⚠️'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="text-[11px] text-slate-400">{data.nota_padron}</p>
                </div>
            )}

            {!cargando && data && sub === 'subsidio' && (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Tarjeta label="Con subsidio" valor={data.totales.ingredientes_con_subsidio} />
                        <Tarjeta label="OK" valor={data.totales.ok} tono="text-emerald-700" />
                        <Tarjeta label="Por agotar" valor={data.totales.por_agotar} tono="text-amber-600" />
                        <Tarjeta label="Agotados" valor={data.totales.agotados} tono="text-red-600" />
                    </div>
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                        <table className="w-full text-left text-xs">
                            <thead><tr className="bg-slate-100 text-slate-600">
                                <th className="p-2">Ingrediente</th><th className="p-2 text-right">Stock</th>
                                <th className="p-2 text-right">Consumo real</th><th className="p-2 text-right">Comprometido</th>
                                <th className="p-2 text-right">Restante</th><th className="p-2 text-right">% uso</th>
                                <th className="p-2 text-right">Consumo/día</th><th className="p-2">Quiebre est.</th>
                                <th className="p-2 text-center">Estado</th>
                            </tr></thead>
                            <tbody className="divide-y divide-slate-100">
                                {data.lineas.map(l => (
                                    <tr key={l.ingrediente_id} className="hover:bg-slate-50">
                                        <td className="p-2 font-medium">{l.ingrediente}</td>
                                        <td className="p-2 text-right">{fmtN(l.gramos_stock / 1000, 2)} kg/L</td>
                                        <td className="p-2 text-right">{fmtN(l.gramos_consumo_real / 1000, 2)}</td>
                                        <td className="p-2 text-right">{fmtN(l.gramos_comprometido_futuro / 1000, 2)}</td>
                                        <td className={`p-2 text-right font-bold ${l.gramos_restante < 0 ? 'text-red-600' : 'text-slate-700'}`}>{fmtN(l.gramos_restante / 1000, 2)}</td>
                                        <td className="p-2 text-right">{fmtN(l.pct_uso)}%</td>
                                        <td className="p-2 text-right">{fmtN(l.consumo_diario_planificado / 1000, 2)}</td>
                                        <td className="p-2">{l.fecha_estimada_quiebre || '—'}</td>
                                        <td className="p-2 text-center">{badgeSemaforo(l.estado)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {!cargando && data && sub === 'compras' && (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Tarjeta label="Ahorro por IA/Scraper" valor={fmtS(data.totales.ahorro_ia)} tono="text-emerald-700" />
                        <Tarjeta label="Costo a precio usado" valor={fmtS(data.totales.costo_usado)} />
                        <Tarjeta label="Costo a promedio mes" valor={fmtS(data.totales.costo_a_promedio_mes)} />
                        <Tarjeta label="Diferencia" valor={fmtS(data.totales.diferencia_usado_vs_prommes)} tono={data.totales.diferencia_usado_vs_prommes <= 0 ? 'text-emerald-700' : 'text-amber-600'} />
                    </div>
                    <p className="text-[11px] text-slate-500">{data.criterio}</p>
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                        <table className="w-full text-left text-xs">
                            <thead><tr className="bg-slate-100 text-slate-600">
                                <th className="p-2">Semana</th><th className="p-2">Fecha compra</th>
                                <th className="p-2 text-right">Costo usado</th><th className="p-2 text-right">Ahorro IA</th>
                                <th className="p-2">Fuentes</th><th className="p-2">Top ahorros</th>
                            </tr></thead>
                            <tbody className="divide-y divide-slate-100">
                                {data.planes.map(p => (
                                    <tr key={p.plan_id} className="hover:bg-slate-50">
                                        <td className="p-2 font-medium">{p.semana}</td>
                                        <td className="p-2">{p.fecha_compra}</td>
                                        <td className="p-2 text-right">{fmtS(p.costo_usado)}</td>
                                        <td className={`p-2 text-right font-bold ${(p.ahorro_ia || 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmtS(p.ahorro_ia)}</td>
                                        <td className="p-2">{Object.entries(p.items_por_fuente).map(([f, n]) => `${f}(${n})`).join(' · ')}</td>
                                        <td className="p-2 text-[10px] text-slate-500">{p.top_ahorros.map(t => `${t.insumo}: ${fmtS(t.ahorro)}`).join(' · ') || '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {!cargando && data && sub === 'merma' && (
                <div className="space-y-4">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <Tarjeta label="Raciones proyectadas" valor={data.totales.raciones_proyectadas} />
                        <Tarjeta label="Raciones reales" valor={data.totales.raciones_reales} />
                        <Tarjeta label="Merma total" valor={data.totales.merma_total} tono={data.totales.merma_total > 0 ? 'text-amber-600' : 'text-emerald-700'} />
                        <Tarjeta label="Precisión promedio" valor={`${fmtN(data.totales.precision_promedio_pct)}%`} tono="text-emerald-700" />
                        <Tarjeta label="Sesgo acumulado" valor={data.totales.sesgo_acumulado} sub={data.totales.interpretacion_sesgo} />
                        <Tarjeta label="Días con IA" valor={data.totales.dias_con_prediccion_ia} />
                        <Tarjeta label="Días sin POS" valor={data.totales.dias_sin_registro_pos} tono="text-amber-600" />
                        <Tarjeta label="Días planificados" valor={data.totales.dias_planificados} />
                    </div>
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                        <table className="w-full text-left text-xs">
                            <thead><tr className="bg-slate-100 text-slate-600">
                                <th className="p-2">Fecha</th><th className="p-2">Día</th>
                                <th className="p-2 text-right">Proyectado</th><th className="p-2 text-right">Atendido</th>
                                <th className="p-2 text-right">Merma</th><th className="p-2 text-right">Precisión</th>
                                <th className="p-2">Fuente</th><th className="p-2 text-center">Estado</th>
                            </tr></thead>
                            <tbody className="divide-y divide-slate-100">
                                {data.dias.map((d, i) => (
                                    <tr key={i} className="hover:bg-slate-50">
                                        <td className="p-2 font-medium">{d.fecha}</td>
                                        <td className="p-2">{d.dia_nombre}</td>
                                        <td className="p-2 text-right">{d.proyectado}</td>
                                        <td className="p-2 text-right">{d.atendido_real ?? '—'}</td>
                                        <td className={`p-2 text-right font-bold ${(d.merma || 0) > 0 ? 'text-amber-600' : 'text-emerald-700'}`}>{d.merma ?? '—'}</td>
                                        <td className="p-2 text-right">{d.precision != null ? `${d.precision}%` : '—'}</td>
                                        <td className="p-2">{d.fuente === 'prediccion_ia' ? 'IA' : 'Parámetro'}</td>
                                        <td className="p-2 text-center">{badgeSemaforo(d.estado)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="text-[11px] text-slate-400">{data.nota_padron}</p>
                </div>
            )}

            {!cargando && data && sub === 'nutricional' && (
                <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                        {data.nutrientes.map(n => (
                            <div key={n.nutriente} className="bg-white border border-slate-200 rounded-xl p-3 text-center">
                                <p className="text-[11px] text-slate-500 uppercase font-semibold">{n.nutriente}</p>
                                <p className="text-lg font-bold text-slate-800">{fmtN(n.valor, 2)} / meta {fmtN(n.meta, 1)}</p>
                                <div className="mt-1">{badgeSemaforo(n.semaforo)}</div>
                            </div>
                        ))}
                        <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
                            <p className="text-[11px] text-slate-500 uppercase font-semibold">Días Anti-Anemia</p>
                            <p className="text-lg font-bold text-red-700">{data.anemia_cero.dias_con_receta_anti_anemia} ({fmtN(data.anemia_cero.pct_dias_anti_anemia)}%)</p>
                            <p className="text-[10px] text-slate-400">cuota mensual: {data.anemia_cero.cuota_mensual_esperada}</p>
                            <div className="mt-1">{badgeSemaforo(data.anemia_cero.semaforo)}</div>
                        </div>
                    </div>
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                        <table className="w-full text-left text-xs">
                            <thead><tr className="bg-slate-100 text-slate-600">
                                <th className="p-2">Fecha</th><th className="p-2">Receta</th>
                                <th className="p-2 text-right">Fe (mg)</th><th className="p-2 text-right">Prot (g)</th>
                                <th className="p-2 text-right">Kcal</th><th className="p-2 text-center">Anti-Anemia</th>
                            </tr></thead>
                            <tbody className="divide-y divide-slate-100">
                                {data.dias.map((d, i) => (
                                    <tr key={i} className="hover:bg-slate-50">
                                        <td className="p-2 font-medium">{d.fecha}</td>
                                        <td className="p-2">{d.receta}</td>
                                        <td className={`p-2 text-right font-bold ${d.hierro_mg_racion >= data.nutrientes[0].meta ? 'text-emerald-700' : 'text-amber-600'}`}>{fmtN(d.hierro_mg_racion, 2)}</td>
                                        <td className="p-2 text-right">{fmtN(d.proteina_g_racion, 2)}</td>
                                        <td className="p-2 text-right">{fmtN(d.energia_kcal_racion, 0)}</td>
                                        <td className="p-2 text-center">{d.es_anti_anemia ? '🩸' : '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {!cargando && !data && !error && (
                <div className="p-10 text-center bg-slate-50 border border-slate-200 rounded-xl">
                    <RefreshCw size={28} className="text-emerald-600 mx-auto mb-2" />
                    <p className="text-sm text-slate-500">Configure el período y pulse "Generar reporte".</p>
                </div>
            )}
        </div>
    );
};