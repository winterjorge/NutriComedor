/**
 * components/budget/PlanificacionesView.jsx
 * Objetivo: Vista de Planificaciones semanales (menús definitivos del comedor). Lista
 *           las planificaciones vigentes/reemplazadas y, al expandirlas, muestra:
 *           (1) tarjetas de resumen con Costo semanal, Recolección semanal, MARGEN
 *               (ventas - compras), Kcal/día, Hierro/día y Proteína/día;
 *           (2) el detalle POR DÍA con comensales Social/Afiliado/Normal en columnas
 *               separadas, recolección proyectada y nutrición por ración;
 *           (3) la lista de compras consolidada (semanal o por día) con exportación
 *               a PDF para imprimir o llevar al mercado.
 * Historial:
 *   Sprint 2: versión original (api.getPlanificaciones / getPlanificacionDetalle /
 *             eliminarPlanificacion / getListaCompras).
 *   COM-8 v2: reconstruida sobre /propuestas/historial y /propuestas/historial/{id}/dias.
 *   COM-8 v4: comensales por día en columnas separadas; tarjetas de hierro y proteína.
 *   COM-8 v5: trazabilidad recuperada. Todo lo reemplazado se conserva COMENTADO.
 *   COM-65 (este archivo): FIX del bug "Sin ítems de compra registrados" (el frontend
 *             leía data.items/data.grupos pero el backend devuelve data.lista_compras).
 *             Se agrega filtro por día y exportación a PDF de la lista de compras.
 * Permisos: módulo 'planificaciones' (Directivo y Operativo del comedor, COM-25/COM-8).
 * Uso: Montada por App.jsx en la pestaña "Planificaciones".
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    ClipboardList, Loader2, AlertCircle, ChevronDown, ChevronUp,
    Wallet, Coins, TrendingUp, Flame, Users, ShoppingCart, History,
    Droplet, Trash2, FileDown, Calendar, Printer
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';

// COM-65: nombres de los días para el filtro
const DIAS_SEMANA = [
    { num: 1, nombre: 'Lunes' },
    { num: 2, nombre: 'Martes' },
    { num: 3, nombre: 'Miércoles' },
    { num: 4, nombre: 'Jueves' },
    { num: 5, nombre: 'Viernes' },
    { num: 6, nombre: 'Sábado' },
    { num: 7, nombre: 'Domingo' },
];

export const PlanificacionesView = () => {
    const { usuario, seleccion } = useAuth();
    const comedorId = seleccion?.comedor_id;
    const [planificaciones, setPlanificaciones] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    // Caché por planificación expandida: { id: { dias } }
    const [expandidos, setExpandidos] = useState({});
    const [cache, setCache] = useState({});
    const [cargandoDetalle, setCargandoDetalle] = useState({});
    // COM-65: lista de compras con filtro por día
    const [compras, setCompras] = useState({});
    const [cargandoCompras, setCargandoCompras] = useState({});
    const [mostrarCompras, setMostrarCompras] = useState({});
    const [diaFiltro, setDiaFiltro] = useState({}); // { planId: null | 1..7 }
    // COM-65: confirmación de eliminación
    const [confEliminar, setConfEliminar] = useState(null);

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

    // ---------- Expansión: detalle por día ----------
    const toggleExpandir = async (plan) => {
        if (expandidos[plan.id]) {
            setExpandidos({ ...expandidos, [plan.id]: false });
            return;
        }
        setExpandidos({ ...expandidos, [plan.id]: true });
        if (cache[plan.id]) return;
        setCargandoDetalle({ ...cargandoDetalle, [plan.id]: true });
        try {
            const dias = await api.getHistorialDias(plan.id, usuario.id);
            setCache(prev => ({ ...prev, [plan.id]: { dias } }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoDetalle({ ...cargandoDetalle, [plan.id]: false });
        }
    };

    // ---------- COM-65: Lista de compras (semanal o por día) ----------
    const toggleCompras = async (plan) => {
        if (mostrarCompras[plan.id]) {
            setMostrarCompras({ ...mostrarCompras, [plan.id]: false });
            return;
        }
        setMostrarCompras({ ...mostrarCompras, [plan.id]: true });
        // COM-65: si ya hay datos cargados para el día seleccionado, reutilizar
        const dia = diaFiltro[plan.id] || null;
        const cacheKey = `${plan.id}_${dia || 'all'}`;
        if (compras[cacheKey]) return;
        setCargandoCompras({ ...cargandoCompras, [cacheKey]: true });
        try {
            const data = await api.getListaCompras(plan.id, dia);
            // COM-65 FIX: el backend devuelve { lista_compras: [...] }
            const filas = Array.isArray(data.lista_compras) ? data.lista_compras : [];
            setCompras(prev => ({ ...prev, [cacheKey]: filas }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoCompras({ ...cargandoCompras, [cacheKey]: false });
        }
    };

    // COM-65: cambiar el día de filtro y recargar
    const cambiarDiaFiltro = async (planId, dia) => {
        setDiaFiltro(prev => ({ ...prev, [planId]: dia }));
        const cacheKey = `${planId}_${dia || 'all'}`;
        if (compras[cacheKey]) return;
        setCargandoCompras({ ...cargandoCompras, [cacheKey]: true });
        try {
            const data = await api.getListaCompras(planId, dia);
            const filas = Array.isArray(data.lista_compras) ? data.lista_compras : [];
            setCompras(prev => ({ ...prev, [cacheKey]: filas }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoCompras({ ...cargandoCompras, [cacheKey]: false });
        }
    };

    // COM-65: exportar a PDF (usa window.print con estilos de impresión)
    const exportarPDF = (planId) => {
        const dia = diaFiltro[planId] || null;
        const cacheKey = `${planId}_${dia || 'all'}`;
        const filas = compras[cacheKey] || [];
        if (filas.length === 0) {
            setError('No hay ítems para exportar. Cargue la lista primero.');
            return;
        }
        const plan = planificaciones.find(p => p.id === planId);
        const diaInfo = dia ? DIAS_SEMANA.find(d => d.num === dia) : null;
        const titulo = diaInfo
            ? `Lista de compras - ${diaInfo.nombre} (${plan?.fecha_referencia || ''})`
            : `Lista de compras semanal (${plan?.fecha_referencia || ''})`;

        // Abrir ventana de impresión con HTML formateado
        const ventana = window.open('', '_blank', 'width=800,height=600');
        if (!ventana) {
            setError('El navegador bloqueó la ventana de impresión. Permita popups.');
            return;
        }
        ventana.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>${titulo}</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; color: #1e293b; }
                    h1 { color: #059669; border-bottom: 2px solid #059669; padding-bottom: 8px; }
                    h2 { color: #475569; margin-top: 24px; }
                    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
                    th { background: #f1f5f9; padding: 10px; text-align: left; border: 1px solid #cbd5e1; font-size: 12px; text-transform: uppercase; }
                    td { padding: 8px 10px; border: 1px solid #e2e8f0; font-size: 13px; }
                    tr:nth-child(even) { background: #f8fafc; }
                    .total { font-weight: bold; background: #ecfdf5; }
                    .footer { margin-top: 40px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #cbd5e1; padding-top: 12px; }
                    @media print {
                        body { margin: 10mm; }
                        .no-print { display: none; }
                    }
                </style>
            </head>
            <body>
                <h1>${titulo}</h1>
                <p><strong>Comedor:</strong> ${plan?.etiqueta || 'Planificación semanal'}</p>
                <p><strong>Generado:</strong> ${new Date().toLocaleDateString('es-PE', { day: '2-digit', month: 'long', year: 'numeric' })}</p>
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Ingrediente</th>
                            <th>Cantidad</th>
                            <th>Unidad</th>
                            <th>Días de uso</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filas.map((f, i) => `
                            <tr>
                                <td>${i + 1}</td>
                                <td>${f.nombre || '—'}</td>
                                <td><strong>${f.cantidad ?? '—'}</strong></td>
                                <td>${f.unidad || '—'}</td>
                                <td>${(f.dias_uso || []).join(', ') || '—'}</td>
                            </tr>
                        `).join('')}
                        <tr class="total">
                            <td colspan="2">Total de ingredientes</td>
                            <td colspan="3">${filas.length} ítems</td>
                        </tr>
                    </tbody>
                </table>
                <div class="footer">
                    NutriComedor OSB · Lista generada automáticamente desde la planificación semanal
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

    // ---------- Eliminación ----------
    const confirmarEliminar = async () => {
        const plan = confEliminar;
        setConfEliminar(null);
        try {
            await api.eliminarPlanificacion(plan.id);
            setCache(prev => { const c = { ...prev }; delete c[plan.id]; return c; });
            setExpandidos(prev => ({ ...prev, [plan.id]: false }));
            await cargar();
        } catch (e) {
            setError(e.message);
        }
    };

    // ---------- Helpers de render ----------
    const margenDe = (p) => {
        if (p.margen !== null && p.margen !== undefined) return Number(p.margen);
        return Number(p.recoleccion_total_proyectada || 0) - Number(p.costo_total_semana || 0);
    };
    const calcularPromedios = (dias) => {
        if (!dias || dias.length === 0) return { kcal: '—', hierro: '—', proteina: '—' };
        const n = dias.length;
        const sumK = dias.reduce((a, d) => a + Number(d.energia_kcal_racion || 0), 0);
        const sumH = dias.reduce((a, d) => a + Number(d.hierro_mg_racion || 0), 0);
        const sumP = dias.reduce((a, d) => a + Number(d.proteina_g_racion || 0), 0);
        return {
            kcal: sumK > 0 ? (sumK / n).toFixed(1) : '—',
            hierro: sumH > 0 ? (sumH / n).toFixed(2) : '—',
            proteina: sumP > 0 ? (sumP / n).toFixed(1) : '—',
        };
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
                        Menús definitivos seleccionados del motor de propuestas, con recolección,
                        margen, comensales por día y detalle nutricional por ración.
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
                                <th className="p-3 font-semibold text-right">Acciones</th>
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
                                            <td className="p-3">
                                                <div className="flex justify-end gap-2">
                                                    <button
                                                        onClick={() => setConfEliminar(p)}
                                                        className="p-1.5 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors"
                                                        title="Eliminar planificación">
                                                        <Trash2 size={15} />
                                                    </button>
                                                    <button
                                                        onClick={() => toggleExpandir(p)}
                                                        className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                                        title={abierto ? 'Ocultar detalle' : 'Ver detalle por día'}>
                                                        {abierto ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                                                    </button>
                                                </div>
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
                                                        {/* Tarjetas de resumen */}
                                                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
                                                            {tarjeta(<Wallet size={12} className="text-slate-500" />,
                                                                `S/ ${p.costo_total_semana}`, 'Costo total semanal (compras)')}
                                                            {tarjeta(<Coins size={12} className="text-emerald-600" />,
                                                                `S/ ${p.recoleccion_total_proyectada}`, 'Recolección semanal (ventas)')}
                                                            {tarjeta(<TrendingUp size={12} />,
                                                                `S/ ${margen}`, 'Margen (ventas − compras)',
                                                                margen >= 0 ? 'text-emerald-700' : 'text-red-600')}
                                                            {tarjeta(<Flame size={12} className="text-orange-500" />,
                                                                `${calcularPromedios(det.dias).kcal} kcal`, 'Kcal promedio por día')}
                                                            {tarjeta(<Droplet size={12} className="text-red-500" />,
                                                                `${calcularPromedios(det.dias).hierro} mg`, 'Hierro promedio por día',
                                                                'text-red-700')}
                                                            {tarjeta(<Users size={12} className="text-blue-500" />,
                                                                `${calcularPromedios(det.dias).proteina} g`, 'Proteína promedio por día')}
                                                        </div>
                                                        {/* Tabla por día */}
                                                        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                                                            <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                                                                <thead>
                                                                    <tr className="bg-slate-100 text-slate-600">
                                                                        <th className="p-2 font-semibold">Día</th>
                                                                        <th className="p-2 font-semibold">Receta</th>
                                                                        <th className="p-2 font-semibold text-center bg-red-50 text-red-700">Social</th>
                                                                        <th className="p-2 font-semibold text-center bg-blue-50 text-blue-700">Afiliado</th>
                                                                        <th className="p-2 font-semibold text-center bg-emerald-50 text-emerald-700">Normal</th>
                                                                        <th className="p-2 font-semibold text-center">Total</th>
                                                                        <th className="p-2 font-semibold">Costo/rac.</th>
                                                                        <th className="p-2 font-semibold">Costo del día</th>
                                                                        <th className="p-2 font-semibold">Recolección proyectada</th>
                                                                        <th className="p-2 font-semibold">Kcal/rac.</th>
                                                                        <th className="p-2 font-semibold text-red-700">Fe/rac. (mg)</th>
                                                                        <th className="p-2 font-semibold">Prot/rac. (g)</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody className="divide-y divide-slate-200">
                                                                    {det.dias.map(d => (
                                                                        <tr key={d.id}>
                                                                            <td className="p-2 font-bold text-slate-700">{d.dia_nombre}</td>
                                                                            <td className="p-2 text-slate-600">{d.nombre_receta}</td>
                                                                            <td className="p-2 text-center text-lg font-bold text-red-700 bg-red-50/40">{d.comensales_social ?? 0}</td>
                                                                            <td className="p-2 text-center text-lg font-bold text-blue-700 bg-blue-50/40">{d.comensales_afiliado ?? 0}</td>
                                                                            <td className="p-2 text-center text-lg font-bold text-emerald-700 bg-emerald-50/40">{d.comensales_normal ?? 0}</td>
                                                                            <td className="p-2 text-center font-bold text-slate-800">{d.total_comensales}</td>
                                                                            <td className="p-2 text-slate-600">S/ {d.costo_racion}</td>
                                                                            <td className="p-2 text-slate-600">S/ {d.costo_total}</td>
                                                                            <td className="p-2 font-semibold text-emerald-700">S/ {d.recoleccion_proyectada}</td>
                                                                            <td className="p-2 text-slate-600">{d.energia_kcal_racion ?? '—'}</td>
                                                                            <td className="p-2 font-semibold text-red-700">{d.hierro_mg_racion ?? '—'}</td>
                                                                            <td className="p-2 text-slate-600">{d.proteina_g_racion ?? '—'}</td>
                                                                        </tr>
                                                                    ))}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                        {/* COM-65: Lista de compras con filtro por día y exportación PDF */}
                                                        <div className="bg-white rounded-lg border border-slate-200 p-4">
                                                            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                                                                <h4 className="font-bold text-slate-700 flex items-center gap-2">
                                                                    <ShoppingCart size={16} className="text-emerald-600" />
                                                                    Lista de compras
                                                                </h4>
                                                                <div className="flex flex-wrap items-center gap-2">
                                                                    {/* Filtro por día */}
                                                                    <div className="flex items-center gap-1 text-xs">
                                                                        <Calendar size={12} className="text-slate-500" />
                                                                        <span className="text-slate-600 font-medium">Ver:</span>
                                                                    </div>
                                                                    <button
                                                                        onClick={() => cambiarDiaFiltro(p.id, null)}
                                                                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                                                                            !diaFiltro[p.id] ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                                                        }`}
                                                                        title="Lista consolidada de la semana">
                                                                        Semana
                                                                    </button>
                                                                    {DIAS_SEMANA.map(d => (
                                                                        <button
                                                                            key={d.num}
                                                                            onClick={() => cambiarDiaFiltro(p.id, d.num)}
                                                                            className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                                                                                diaFiltro[p.id] === d.num ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                                                            }`}
                                                                            title={`Lista solo para ${d.nombre}`}>
                                                                            {d.nombre.slice(0, 3)}
                                                                        </button>
                                                                    ))}
                                                                    {/* Botón exportar PDF */}
                                                                    <button
                                                                        onClick={() => exportarPDF(p.id)}
                                                                        className="ml-2 flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium transition-colors"
                                                                        title="Exportar lista de compras a PDF">
                                                                        <FileDown size={12} /> PDF
                                                                    </button>
                                                                </div>
                                                            </div>
                                                            {/* Contenido de la lista */}
                                                            {(() => {
                                                                const cacheKey = `${p.id}_${diaFiltro[p.id] || 'all'}`;
                                                                const filas = compras[cacheKey] || [];
                                                                const cargando = cargandoCompras[cacheKey];
                                                                return (
                                                                    <>
                                                                        {!mostrarCompras[p.id] && (
                                                                            <button
                                                                                onClick={() => toggleCompras(p)}
                                                                                className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-800 transition-colors">
                                                                                <ShoppingCart size={14} />
                                                                                {diaFiltro[p.id]
                                                                                    ? `Ver lista para ${DIAS_SEMANA.find(d => d.num === diaFiltro[p.id])?.nombre}`
                                                                                    : 'Ver lista de compras semanal'}
                                                                            </button>
                                                                        )}
                                                                        {mostrarCompras[p.id] && (
                                                                            <div className="rounded-lg border border-slate-200 bg-white overflow-hidden">
                                                                                {cargando ? (
                                                                                    <div className="p-6 text-center text-emerald-600">
                                                                                        <Loader2 className="animate-spin mx-auto" size={18} />
                                                                                    </div>
                                                                                ) : filas.length === 0 ? (
                                                                                    <p className="p-4 text-xs text-slate-500 text-center">
                                                                                        Sin ítems de compra registrados para
                                                                                        {diaFiltro[p.id] ? ` ${DIAS_SEMANA.find(d => d.num === diaFiltro[p.id])?.nombre}` : ' esta semana'}.
                                                                                    </p>
                                                                                ) : (
                                                                                    <>
                                                                                        <div className="overflow-x-auto">
                                                                                            <table className="w-full text-left text-xs">
                                                                                                <thead>
                                                                                                    <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                                                                                                        <th className="p-2 font-semibold">#</th>
                                                                                                        <th className="p-2 font-semibold">Ingrediente</th>
                                                                                                        <th className="p-2 font-semibold text-right">Cantidad</th>
                                                                                                        <th className="p-2 font-semibold">Unidad</th>
                                                                                                        <th className="p-2 font-semibold">Días de uso</th>
                                                                                                    </tr>
                                                                                                </thead>
                                                                                                <tbody className="divide-y divide-slate-100">
                                                                                                    {filas.map((row, i) => (
                                                                                                        <tr key={i} className="hover:bg-slate-50">
                                                                                                            <td className="p-2 text-slate-500">{i + 1}</td>
                                                                                                            <td className="p-2 font-medium text-slate-800">{row.nombre || '—'}</td>
                                                                                                            <td className="p-2 text-right font-bold text-emerald-700">{row.cantidad ?? '—'}</td>
                                                                                                            <td className="p-2 text-slate-600">{row.unidad || '—'}</td>
                                                                                                            <td className="p-2 text-slate-500 text-[10px]">{(row.dias_uso || []).join(', ') || '—'}</td>
                                                                                                        </tr>
                                                                                                    ))}
                                                                                                </tbody>
                                                                                                <tfoot>
                                                                                                    <tr className="bg-emerald-50 font-bold text-emerald-800">
                                                                                                        <td colSpan="2" className="p-2">Total de ingredientes</td>
                                                                                                        <td colSpan="3" className="p-2">{filas.length} ítems</td>
                                                                                                    </tr>
                                                                                                </tfoot>
                                                                                            </table>
                                                                                        </div>
                                                                                        {/* Botón imprimir dentro del panel */}
                                                                                        <div className="p-2 bg-slate-50 border-t border-slate-200 flex justify-end">
                                                                                            <button
                                                                                                onClick={() => exportarPDF(p.id)}
                                                                                                className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs font-medium transition-colors">
                                                                                                <Printer size={12} /> Imprimir / Guardar como PDF
                                                                                            </button>
                                                                                        </div>
                                                                                    </>
                                                                                )}
                                                                            </div>
                                                                        )}
                                                                    </>
                                                                );
                                                            })()}
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
            {/* Confirmación de eliminación */}
            <ModalConfirmacion
                isOpen={!!confEliminar}
                onClose={() => setConfEliminar(null)}
                onConfirm={confirmarEliminar}
                mensaje={confEliminar
                    ? `¿Eliminar la planificación de la semana del ${confEliminar.fecha_referencia} (${confEliminar.etiqueta || confEliminar.variante || 'sin variante'})? Se eliminarán también sus días y su lista de compras asociada.`
                    : ''}
                tipo="danger"
            />
        </div>
    );
};