/**
components/subsidio/ReporteSubsidioView.jsx
Objetivo: COM-69: REPORTE DE USO DEL SUBSIDIO de víveres por comedor y mes, dirigido
      al administrativo de la municipalidad (y visible también para la directiva y
      el Admin de Sistemas según permisos de lectura de subsidio):
        * Stock recibido por ingrediente (unidad original y gramos/ml base).
        * Consumo proyectado ACUMULADO de todas las planificaciones del mes.
        * Restante, % de uso con barra de progreso y estado:
          OK / POR AGOTAR (≥90%) / AGOTADO (consumo > stock) / SIN CONSUMO.
        * Detalle por planificación (semana) para auditoría.
        * Exportación a PDF para la rendición de cuentas municipal.
Historial:
  COM-69 (este archivo): vista nueva. El backend expone GET /subsidio/reporte-uso
      y GET /subsidio/comedores-visibles (gate _validar_lectura de COM-59A).
Permisos: módulo 'subsidio' con alcance (Admin Sistema: todos; Directivo: su comedor;
      municipal: comedores de su distrito, COM-27).
Uso: Montada por App.jsx en la pestaña "Reporte Subsidio" (módulo 'subsidio').
*/
import React, { useState, useEffect, useCallback } from 'react';
import {
    Gift, Loader2, AlertCircle, FileDown, Printer, Package,
    AlertTriangle, CheckCircle2, Clock3, Ban
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

// COM-69: estilos de badge por estado del stock
const badgeEstado = (estado) => {
    switch (estado) {
        case 'AGOTADO':
            return { cls: 'bg-red-100 text-red-700', icon: <Ban size={11} />, txt: 'AGOTADO (comprar excedente)' };
        case 'POR_AGOTAR':
            return { cls: 'bg-amber-100 text-amber-700', icon: <AlertTriangle size={11} />, txt: 'POR AGOTAR' };
        case 'SIN_CONSUMO':
            return { cls: 'bg-slate-100 text-slate-600', icon: <Clock3 size={11} />, txt: 'SIN CONSUMO' };
        default:
            return { cls: 'bg-emerald-100 text-emerald-700', icon: <CheckCircle2 size={11} />, txt: 'OK' };
    }
};

// COM-69: formato de gramos base a kg/L legibles
const fmtGramos = (g) => {
    const v = Number(g || 0);
    return v >= 1000 ? `${(v / 1000).toFixed(2)} kg/L` : `${v.toFixed(0)} g/ml`;
};

export const ReporteSubsidioView = () => {
    const { usuario } = useAuth();
    const [comedores, setComedores] = useState([]);
    const [cargandoComedores, setCargandoComedores] = useState(true);
    const [comedorId, setComedorId] = useState('');
    const ahora = new Date();
    const [anio, setAnio] = useState(ahora.getFullYear());
    const [mes, setMes] = useState(ahora.getMonth() + 1);
    const [reporte, setReporte] = useState(null);
    const [cargando, setCargando] = useState(false);
    const [error, setError] = useState('');

    // ---------- Carga del selector de comedores visibles ----------
    const cargarComedores = useCallback(async () => {
        setCargandoComedores(true);
        try {
            const lista = await api.getComedoresVisiblesSubsidio(usuario.id);
            setComedores(lista || []);
            if (lista && lista.length === 1) setComedorId(String(lista[0].id));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoComedores(false);
        }
    }, [usuario.id]);

    useEffect(() => { cargarComedores(); }, [cargarComedores]);

    // ---------- Generar reporte ----------
    const generar = async () => {
        if (!comedorId) {
            setError('Seleccione un comedor para generar el reporte.');
            return;
        }
        setCargando(true);
        setError('');
        setReporte(null);
        try {
            const data = await api.getReporteSubsidio({
                usuario_solicitante_id: usuario.id,
                comedor_id: Number(comedorId),
                anio: Number(anio),
                mes: Number(mes),
            });
            setReporte(data);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    };

    // ---------- Exportar a PDF ----------
    const exportarPDF = () => {
        if (!reporte) return;
        const ventana = window.open('', '_blank', 'width=800,height=600');
        if (!ventana) {
            setError('El navegador bloqueó la ventana de impresión. Permita popups.');
            return;
        }
        const nombres = {};
        (reporte.lineas || []).forEach(l => { nombres[l.ingrediente_id] = l.ingrediente; });
        ventana.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Reporte de uso del subsidio - ${reporte.comedor_nombre}</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; color: #1e293b; }
                    h1 { color: #059669; border-bottom: 2px solid #059669; padding-bottom: 8px; font-size: 20px; }
                    h2 { font-size: 14px; color: #475569; margin-top: 24px; }
                    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
                    th { background: #f1f5f9; padding: 8px; text-align: left; border: 1px solid #cbd5e1; font-size: 11px; text-transform: uppercase; }
                    td { padding: 7px 8px; border: 1px solid #e2e8f0; font-size: 12px; }
                    .agotado { color: #dc2626; font-weight: bold; }
                    .por-agotar { color: #d97706; font-weight: bold; }
                    .ok { color: #059669; font-weight: bold; }
                    .sin-consumo { color: #64748b; }
                    .footer { margin-top: 40px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #cbd5e1; padding-top: 12px; }
                    @media print { body { margin: 10mm; } .no-print { display: none; } }
                </style>
            </head>
            <body>
                <h1>Reporte de Uso del Subsidio de Víveres</h1>
                <p><strong>Comedor:</strong> ${reporte.comedor_nombre}</p>
                <p><strong>Período:</strong> ${MESES[reporte.mes - 1]} ${reporte.anio}</p>
                <p><strong>Generado:</strong> ${new Date().toLocaleDateString('es-PE', { day: '2-digit', month: 'long', year: 'numeric' })}</p>
                <p><strong>Planificaciones del mes consideradas:</strong> ${reporte.n_planes_del_mes}</p>
                <table>
                    <thead>
                        <tr>
                            <th>Ingrediente</th>
                            <th>Recibido</th>
                            <th>Stock (base)</th>
                            <th>Consumo proyectado</th>
                            <th>Restante</th>
                            <th>% uso</th>
                            <th>Estado</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(reporte.lineas || []).map(l => `
                            <tr>
                                <td>${l.ingrediente}</td>
                                <td>${l.cantidad_recibida} ${l.unidad_abrev || l.unidad_recibida}</td>
                                <td>${fmtGramos(l.gramos_stock)}</td>
                                <td>${fmtGramos(l.gramos_consumo)}</td>
                                <td>${fmtGramos(l.gramos_restante)}</td>
                                <td>${l.pct_uso != null ? l.pct_uso + '%' : '—'}</td>
                                <td class="${l.estado === 'AGOTADO' ? 'agotado' : l.estado === 'POR_AGOTAR' ? 'por-agotar' : l.estado === 'SIN_CONSUMO' ? 'sin-consumo' : 'ok'}">${l.estado}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
                <h2>Detalle por planificación (semana)</h2>
                <table>
                    <thead>
                        <tr><th>Semana (fecha ref.)</th><th>Ingrediente subsidiado</th><th>Consumo (base)</th></tr>
                    </thead>
                    <tbody>
                        ${(reporte.planes || []).map(pl =>
            Object.entries(pl.consumo_gramos || {})
                .filter(([ingId]) => nombres[ingId])
                .map(([ingId, g]) => `
                                <tr>
                                    <td>${pl.fecha_referencia}</td>
                                    <td>${nombres[ingId]}</td>
                                    <td>${fmtGramos(g)}</td>
                                </tr>
                            `).join('')
        ).join('') || '<tr><td colspan="3">Sin planificaciones en el mes.</td></tr>'}
                    </tbody>
                </table>
                <div class="footer">
                    NutriComedor OSB · Reporte COM-69 para rendición de cuentas municipal ·
                    Consumo proyectado desde menús planificados (no incluye mermas reales)
                </div>
                <div class="no-print" style="margin-top: 20px; text-align: center;">
                    <button onclick="window.print()" style="padding: 10px 24px; background: #059669; color: white; border: none; border-radius: 6px; font-size: 14px; cursor: pointer;">
                        🖨️ Imprimir / Guardar como PDF
                    </button>
                </div>
            </body>
            </html>
        `);
        ventana.document.close();
    };

    const nombresPorId = {};
    (reporte?.lineas || []).forEach(l => { nombresPorId[l.ingrediente_id] = l.ingrediente; });

    return (
        <div className="animate-in fade-in duration-300 space-y-5">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Gift className="text-emerald-600" size={22} /> Reporte de Uso del Subsidio
                    </h2>
                    <p className="text-sm text-slate-500">
                        Rendición mensual por comedor: víveres recibidos del municipio vs consumo
                        proyectado de las planificaciones. Exclusivo para lectura autorizada
                        (municipalidad, directiva y Admin de Sistemas).
                    </p>
                </div>
                <button
                    onClick={exportarPDF}
                    disabled={!reporte}
                    className="flex items-center gap-1 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    title="Exportar reporte a PDF">
                    <FileDown size={15} /> PDF
                </button>
            </div>

            {/* Selectores */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
                <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">Comedor</label>
                    <select
                        value={comedorId}
                        onChange={(e) => { setComedorId(e.target.value); setReporte(null); }}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500"
                        disabled={cargandoComedores}>
                        <option value="">{cargandoComedores ? 'Cargando…' : 'Seleccionar…'}</option>
                        {comedores.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                    </select>
                </div>
                <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">Mes</label>
                    <select
                        value={mes}
                        onChange={(e) => { setMes(Number(e.target.value)); setReporte(null); }}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500">
                        {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                    </select>
                </div>
                <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">Año</label>
                    <input
                        type="number" min="2020" max="2100" value={anio}
                        onChange={(e) => { setAnio(Number(e.target.value)); setReporte(null); }}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                </div>
                <button
                    onClick={generar}
                    disabled={cargando || !comedorId}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
                    {cargando ? <Loader2 className="animate-spin" size={15} /> : <Package size={15} />}
                    Generar reporte
                </button>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Resultado */}
            {reporte && (
                <>
                    {reporte.aviso_enlace && (
                        <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-xs flex items-center gap-2">
                            <AlertTriangle size={14} /> {reporte.aviso_enlace}
                        </div>
                    )}
                    {/* Tarjetas de resumen */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 uppercase font-semibold">Ingredientes con subsidio</p>
                            <p className="text-3xl font-black text-slate-800 mt-1">{reporte.totales.ingredientes_con_subsidio}</p>
                        </div>
                        <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
                            <p className="text-xs text-slate-500 uppercase font-semibold">Planificaciones del mes</p>
                            <p className="text-3xl font-black text-slate-800 mt-1">{reporte.n_planes_del_mes}</p>
                        </div>
                        <div className="bg-white border border-amber-200 rounded-xl p-4 text-center">
                            <p className="text-xs text-amber-600 uppercase font-semibold">Por agotar</p>
                            <p className="text-3xl font-black text-amber-600 mt-1">{reporte.totales.ingredientes_por_agotar}</p>
                        </div>
                        <div className="bg-white border border-red-200 rounded-xl p-4 text-center">
                            <p className="text-xs text-red-600 uppercase font-semibold">Agotados</p>
                            <p className="text-3xl font-black text-red-600 mt-1">{reporte.totales.ingredientes_agotados}</p>
                        </div>
                    </div>

                    {/* Tabla principal */}
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                        <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-3 font-semibold">Ingrediente</th>
                                    <th className="p-3 font-semibold">Recibido</th>
                                    <th className="p-3 font-semibold">Stock (base)</th>
                                    <th className="p-3 font-semibold">Consumo proyectado</th>
                                    <th className="p-3 font-semibold">Restante</th>
                                    <th className="p-3 font-semibold">% uso</th>
                                    <th className="p-3 font-semibold">Estado</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {reporte.lineas.length === 0 ? (
                                    <tr><td colSpan="7" className="p-8 text-center text-slate-500">
                                        No hay subsidio registrado para {MESES[mes - 1]} {anio} en este comedor.
                                        Regístrelo en la pestaña "Subsidio de Víveres".
                                    </td></tr>
                                ) : reporte.lineas.map(l => {
                                    const b = badgeEstado(l.estado);
                                    const pct = Math.min(100, Number(l.pct_uso || 0));
                                    return (
                                        <tr key={l.ingrediente_id} className="hover:bg-slate-50">
                                            <td className="p-3 font-medium text-slate-800">{l.ingrediente}</td>
                                            <td className="p-3 text-slate-600">{l.cantidad_recibida} {l.unidad_abrev || l.unidad_recibida}</td>
                                            <td className="p-3 text-slate-600">{fmtGramos(l.gramos_stock)}</td>
                                            <td className="p-3 text-slate-600">{fmtGramos(l.gramos_consumo)}</td>
                                            <td className={`p-3 font-bold ${l.gramos_restante < 0 ? 'text-red-600' : 'text-slate-700'}`}>
                                                {fmtGramos(l.gramos_restante)}
                                            </td>
                                            <td className="p-3 min-w-[140px]">
                                                <div className="flex items-center gap-2">
                                                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                                                        <div
                                                            className={`h-full ${l.estado === 'AGOTADO' ? 'bg-red-500' : l.estado === 'POR_AGOTAR' ? 'bg-amber-500' : 'bg-emerald-500'}`}
                                                            style={{ width: `${pct}%` }}></div>
                                                    </div>
                                                    <span className="text-xs font-bold text-slate-600">{l.pct_uso != null ? `${l.pct_uso}%` : '—'}</span>
                                                </div>
                                            </td>
                                            <td className="p-3">
                                                <span className={`px-2 py-0.5 rounded-full text-[10px] font-black inline-flex items-center gap-1 ${b.cls}`}>
                                                    {b.icon} {b.txt}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>

                    {/* Detalle por planificación */}
                    <div className="bg-white border border-slate-200 rounded-xl p-4">
                        <h3 className="font-bold text-slate-700 text-sm mb-3 flex items-center gap-2">
                            <Printer size={14} className="text-slate-500" /> Detalle por planificación del mes
                        </h3>
                        {reporte.planes.length === 0 ? (
                            <p className="text-xs text-slate-500">Sin planificaciones registradas en el mes.</p>
                        ) : (
                            <div className="space-y-3">
                                {reporte.planes.map(pl => (
                                    <div key={pl.plan_id} className="border border-slate-200 rounded-lg p-3">
                                        <p className="text-xs font-bold text-slate-700 mb-1">
                                            Semana del {pl.fecha_referencia} (planificación #{pl.plan_id})
                                        </p>
                                        <div className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-600">
                                            {Object.entries(pl.consumo_gramos || {})
                                                .filter(([ingId]) => nombresPorId[ingId])
                                                .map(([ingId, g]) => (
                                                    <span key={ingId}>
                                                        <b>{nombresPorId[ingId]}:</b> {fmtGramos(g)}
                                                    </span>
                                                ))}
                                            {Object.entries(pl.consumo_gramos || {}).filter(([ingId]) => nombresPorId[ingId]).length === 0 && (
                                                <span className="text-slate-400">Sin ingredientes subsidiados en esta semana.</span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};