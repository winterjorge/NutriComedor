/**
components/budget/PlanificacionesView.jsx
Objetivo: Vista de Planificaciones semanales (menús definitivos del comedor). Lista
      las planificaciones vigentes/reemplazadas y, al expandirlas, muestra:
      (1) tarjetas de resumen con Costo semanal, Recolección semanal, MARGEN
          (ventas - compras), Kcal/día, Hierro/día y Proteína/día;
      (2) el detalle POR DÍA con comensales Social/Afiliado/Normal en columnas
          separadas, recolección proyectada y nutrición por ración;
      (3) la lista de compras consolidada (semanal o por día) con exportación
          a PDF para imprimir o llevar al mercado.
Historial:
  Sprint 2: versión original (api.getPlanificaciones / getPlanificacionDetalle /
            eliminarPlanificacion / getListaCompras).
  COM-8 v2: reconstruida sobre /propuestas/historial y /propuestas/historial/{id}/dias.
  COM-8 v4: comensales por día en columnas separadas; tarjetas de hierro y proteína.
  COM-8 v5: trazabilidad recuperada. Todo lo reemplazado se conserva COMENTADO.
  COM-65: FIX del bug "Sin ítems de compra registrados" (el frontend
            leía data.items/data.grupos pero el backend devuelve data.lista_compras).
            Se agrega filtro por día y exportación a PDF de la lista de compras.
  COM-66: Rediseño responsive para móviles/tablets (tooltips, modal de detalles,
            scroll horizontal controlado).
  COM-69 (este archivo): la lista de compras se solicita CON comedor_id para que el
            backend aplique la cobertura del subsidio del mes (Solución B):
            * Nuevas columnas "Subsidio cubre" y "Costo": cuando el ítem queda 100%
              cubierto por el subsidio, el costo se reemplaza por el badge ROJO
              "SUBSIDIADO"; cobertura parcial muestra "SUBS. PARCIAL" + el costo del
              restante que sí se compra.
            * Franja resumen del subsidio del mes (ítems subsidiados, ahorro
              estimado y costo de compra estimado).
            * El PDF incluye las mismas columnas y el texto SUBSIDIADO en rojo.
            Trazabilidad: la tabla anterior de 5 columnas queda comentada al final.
Permisos: módulo 'planificaciones' (Directivo y Operativo del comedor, COM-25/COM-8).
Uso: Montada por App.jsx en la pestaña "Planificaciones".
*/
import React, { useState, useEffect, useCallback } from 'react';
import {
    ClipboardList, Loader2, AlertCircle, ChevronDown, ChevronUp,
    Wallet, Coins, TrendingUp, Flame, Users, ShoppingCart, History,
    Droplet, Trash2, FileDown, Calendar, Printer, Info, X, Gift
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

// COM-69: nombres de meses para la franja resumen del subsidio
const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

// COM-66: Tooltip component
const Tooltip = ({ children, content }) => {
    const [show, setShow] = useState(false);
    return (
        <div className="relative inline-block" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
            {children}
            {show && (
                <div className="absolute z-50 bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-slate-800 text-white text-xs rounded-lg shadow-lg whitespace-nowrap">
                    {content}
                    <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-slate-800"></div>
                </div>
            )}
        </div>
    );
};

// COM-66: Modal para detalles nutricionales
const ModalDetallesReceta = ({ receta, onClose }) => {
    if (!receta) return null;
    return (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
                <div className="bg-emerald-700 text-white p-4 flex justify-between items-center sticky top-0 z-10">
                    <h3 className="font-bold text-lg">Detalles de la Receta</h3>
                    <button onClick={onClose} className="text-white hover:bg-emerald-600 p-1 rounded">
                        <X size={20} />
                    </button>
                </div>
                <div className="p-6 space-y-4">
                    <div>
                        <h4 className="font-bold text-slate-800 text-lg">{receta.nombre_receta}</h4>
                        <p className="text-sm text-slate-500">{receta.dia_nombre}</p>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div className="bg-orange-50 p-3 rounded-lg border border-orange-200">
                            <p className="text-xs text-orange-600 font-semibold">Energía</p>
                            <p className="text-xl font-bold text-orange-700">{receta.energia_kcal_racion} kcal</p>
                            <p className="text-[10px] text-orange-500">por ración</p>
                        </div>
                        <div className="bg-red-50 p-3 rounded-lg border border-red-200">
                            <p className="text-xs text-red-600 font-semibold">Hierro</p>
                            <p className="text-xl font-bold text-red-700">{receta.hierro_mg_racion} mg</p>
                            <p className="text-[10px] text-red-500">por ración</p>
                        </div>
                        <div className="bg-blue-50 p-3 rounded-lg border border-blue-200">
                            <p className="text-xs text-blue-600 font-semibold">Proteína</p>
                            <p className="text-xl font-bold text-blue-700">{receta.proteina_g_racion} g</p>
                            <p className="text-[10px] text-blue-500">por ración</p>
                        </div>
                        <div className="bg-emerald-50 p-3 rounded-lg border border-emerald-200">
                            <p className="text-xs text-emerald-600 font-semibold">Costo</p>
                            <p className="text-xl font-bold text-emerald-700">S/ {receta.costo_racion}</p>
                            <p className="text-[10px] text-emerald-500">por ración</p>
                        </div>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-lg">
                        <h5 className="font-bold text-slate-700 mb-2">Proyección de Atenciones</h5>
                        <div className="grid grid-cols-3 gap-3">
                            <div className="text-center">
                                <p className="text-xs text-red-600 font-semibold">Social</p>
                                <p className="text-2xl font-bold text-red-700">{receta.comensales_social}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-blue-600 font-semibold">Afiliado</p>
                                <p className="text-2xl font-bold text-blue-700">{receta.comensales_afiliado}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-emerald-600 font-semibold">Normal</p>
                                <p className="text-2xl font-bold text-emerald-700">{receta.comensales_normal}</p>
                            </div>
                        </div>
                        <div className="mt-3 pt-3 border-t border-slate-200 text-center">
                            <p className="text-xs text-slate-600 font-semibold">Total Comensales</p>
                            <p className="text-2xl font-bold text-slate-800">{receta.total_comensales}</p>
                        </div>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-lg">
                        <h5 className="font-bold text-slate-700 mb-2">Resumen Financiero del Día</h5>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <p className="text-xs text-slate-600">Costo Total</p>
                                <p className="text-lg font-bold text-slate-800">S/ {receta.costo_total}</p>
                            </div>
                            <div>
                                <p className="text-xs text-slate-600">Recolección Proyectada</p>
                                <p className="text-lg font-bold text-emerald-700">S/ {receta.recoleccion_proyectada}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

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
    // COM-69: resumen de subsidio por cacheKey de lista
    const [subsidios, setSubsidios] = useState({});
    // COM-65: confirmación de eliminación
    const [confEliminar, setConfEliminar] = useState(null);
    // COM-66: modal de detalles de receta
    const [recetaSeleccionada, setRecetaSeleccionada] = useState(null);

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

    // ---------- COM-65 + COM-69: Lista de compras (semanal o por día, con subsidio) ----------
    const toggleCompras = async (plan) => {
        if (mostrarCompras[plan.id]) {
            setMostrarCompras({ ...mostrarCompras, [plan.id]: false });
            return;
        }
        setMostrarCompras({ ...mostrarCompras, [plan.id]: true });
        const dia = diaFiltro[plan.id] || null;
        const cacheKey = `${plan.id}_${dia || 'all'}`;
        if (compras[cacheKey]) return;
        setCargandoCompras({ ...cargandoCompras, [cacheKey]: true });
        try {
            // COM-69: se envía comedorId para aplicar la cobertura del subsidio del mes
            const data = await api.getListaCompras(plan.id, dia, comedorId);
            const filas = Array.isArray(data.lista_compras) ? data.lista_compras : [];
            setCompras(prev => ({ ...prev, [cacheKey]: filas }));
            setSubsidios(prev => ({ ...prev, [cacheKey]: data.subsidio || null }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoCompras({ ...cargandoCompras, [cacheKey]: false });
        }
    };

    // COM-65 + COM-69: cambiar el día de filtro y recargar (con comedor_id)
    const cambiarDiaFiltro = async (planId, dia) => {
        setDiaFiltro(prev => ({ ...prev, [planId]: dia }));
        const cacheKey = `${planId}_${dia || 'all'}`;
        if (compras[cacheKey]) return;
        setCargandoCompras({ ...cargandoCompras, [cacheKey]: true });
        try {
            const data = await api.getListaCompras(planId, dia, comedorId);
            const filas = Array.isArray(data.lista_compras) ? data.lista_compras : [];
            setCompras(prev => ({ ...prev, [cacheKey]: filas }));
            setSubsidios(prev => ({ ...prev, [cacheKey]: data.subsidio || null }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoCompras({ ...cargandoCompras, [cacheKey]: false });
        }
    };

    // COM-65 + COM-69: exportar a PDF con columnas de subsidio y costo
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
        const sub = subsidios[cacheKey] || null;
        const titulo = diaInfo
            ? `Lista de compras - ${diaInfo.nombre} (${plan?.fecha_referencia || ''})`
            : `Lista de compras semanal (${plan?.fecha_referencia || ''})`;

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
                    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
                    th { background: #f1f5f9; padding: 10px; text-align: left; border: 1px solid #cbd5e1; font-size: 12px; text-transform: uppercase; }
                    td { padding: 8px 10px; border: 1px solid #e2e8f0; font-size: 13px; }
                    tr:nth-child(even) { background: #f8fafc; }
                    .total { font-weight: bold; background: #ecfdf5; }
                    .subsidiado { color: #dc2626; font-weight: bold; }
                    .footer { margin-top: 40px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #cbd5e1; padding-top: 12px; }
                    .subsidio-box { margin-top: 12px; padding: 10px; border: 1px solid #fca5a5; background: #fef2f2; font-size: 12px; color: #b91c1c; }
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
                            <th>Comprar</th>
                            <th>Unidad</th>
                            <th>Subsidio cubre</th>
                            <th>Días de uso</th>
                            <th>Costo</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filas.map((f, i) => `
                            <tr>
                                <td>${i + 1}</td>
                                <td>${f.nombre || '—'}</td>
                                <td><strong>${f.cantidad ?? '—'}</strong></td>
                                <td>${f.unidad || '—'}</td>
                                <td>${f.cantidad_subsidio > 0 ? `${f.cantidad_subsidio} ${f.unidad}` : '—'}</td>
                                <td>${(f.dias_uso || []).join(', ') || '—'}</td>
                                <td>${f.subsidio_completo
                                    ? '<span class="subsidiado">SUBSIDIADO</span>'
                                    : f.subsidio_parcial
                                        ? `<span class="subsidiado">SUBS. PARCIAL</span> + S/ ${(f.costo_estimado ?? 0).toFixed(2)}`
                                        : (f.costo_estimado != null ? `S/ ${f.costo_estimado.toFixed(2)}` : '—')}</td>
                            </tr>
                        `).join('')}
                        <tr class="total">
                            <td colspan="2">Total de ingredientes</td>
                            <td colspan="5">${filas.length} ítems</td>
                        </tr>
                    </tbody>
                </table>
                ${sub && sub.stock_registrado ? `
                <div class="subsidio-box">
                    <strong>Subsidio de víveres ${MESES[sub.mes - 1]} ${sub.anio}:</strong>
                    ${sub.items_subsididados} ítem(s) cubierto(s) total o parcialmente por el subsidio municipal ·
                    Ahorro estimado S/ ${sub.ahorro_total_estimado} ·
                    Costo de compra estimado S/ ${sub.costo_total_compra_estimado}
                </div>` : ''}
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

    // COM-69: celda de costo con badge SUBSIDIADO en rojo
    const celdaCosto = (row) => {
        if (row.subsidio_completo) {
            return (
                <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full text-[10px] font-black whitespace-nowrap">
                    SUBSIDIADO
                </span>
            );
        }
        if (row.subsidio_parcial) {
            return (
                <span className="flex flex-col items-end gap-0.5">
                    <span className="px-2 py-0.5 bg-red-100 text-red-700 rounded-full text-[10px] font-black whitespace-nowrap">
                        SUBS. PARCIAL
                    </span>
                    <span className="text-slate-700 font-bold">
                        {row.costo_estimado != null ? `S/ ${Number(row.costo_estimado).toFixed(2)}` : '—'}
                    </span>
                </span>
            );
        }
        return (
            <span className="text-slate-700 font-bold">
                {row.costo_estimado != null ? `S/ ${Number(row.costo_estimado).toFixed(2)}` : '—'}
            </span>
        );
    };

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
                <div className="space-y-4">
                    {planificaciones.map(p => {
                        const abierto = !!expandidos[p.id];
                        const det = cache[p.id];
                        const margen = margenDe(p);
                        return (
                            <div key={p.id} className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                                {/* Fila principal de la planificación */}
                                <div className="p-4 border-b border-slate-200">
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                        <div className="flex items-center gap-3">
                                            <div>
                                                <p className="font-bold text-slate-800">{p.fecha_referencia}</p>
                                                <p className="text-xs text-slate-500">{p.etiqueta || p.variante || '—'}</p>
                                            </div>
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${p.estado === 'VIGENTE' ? 'bg-emerald-100 text-emerald-700'
                                                : p.estado === 'REEMPLAZADA' ? 'bg-amber-100 text-amber-700'
                                                    : 'bg-slate-100 text-slate-600'}`}>
                                                {p.estado}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-2">
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
                                    </div>
                                    {/* Resumen rápido */}
                                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
                                        <div className="text-center">
                                            <p className="text-xs text-slate-500">Costo total</p>
                                            <p className="font-bold text-slate-800">S/ {p.costo_total_semana}</p>
                                        </div>
                                        <div className="text-center">
                                            <p className="text-xs text-slate-500">Recolección</p>
                                            <p className="font-bold text-slate-800">S/ {p.recoleccion_total_proyectada}</p>
                                        </div>
                                        <div className="text-center">
                                            <p className="text-xs text-slate-500">Margen</p>
                                            <p className={`font-bold ${margen >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                                                S/ {margen}
                                            </p>
                                        </div>
                                        <div className="text-center">
                                            <p className="text-xs text-slate-500">Días</p>
                                            <p className="font-bold text-slate-800">{p.dias_operativos}</p>
                                        </div>
                                    </div>
                                </div>
                                {/* Detalle expandido */}
                                {abierto && (
                                    <div className="p-4 space-y-4">
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
                                                {/* COM-66: Tabla responsive de días */}
                                                <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                                                    <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                                                        <thead>
                                                            <tr className="bg-slate-100 text-slate-600">
                                                                <th className="p-2 font-semibold">Día</th>
                                                                <th className="p-2 font-semibold">Receta</th>
                                                                <th className="p-2 font-semibold text-center">
                                                                    <Tooltip content="Social / Afiliado / Normal">
                                                                        <span className="cursor-help">Comensales</span>
                                                                    </Tooltip>
                                                                </th>
                                                                <th className="p-2 font-semibold text-center">Total</th>
                                                                <th className="p-2 font-semibold">Costo/rac.</th>
                                                                <th className="p-2 font-semibold">Kcal</th>
                                                                <th className="p-2 font-semibold text-red-700">Fe</th>
                                                                <th className="p-2 font-semibold">Prot</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="divide-y divide-slate-200">
                                                            {det.dias.map(d => (
                                                                <tr key={d.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => setRecetaSeleccionada(d)}>
                                                                    <td className="p-2 font-bold text-slate-700">{d.dia_nombre}</td>
                                                                    <td className="p-2 text-slate-600 max-w-[200px] truncate" title={d.nombre_receta}>{d.nombre_receta}</td>
                                                                    <td className="p-2 text-center">
                                                                        <Tooltip content={`Social: ${d.comensales_social} | Afiliado: ${d.comensales_afiliado} | Normal: ${d.comensales_normal}`}>
                                                                            <span className="inline-flex items-center gap-1 text-slate-700 font-medium">
                                                                                {d.total_comensales}
                                                                                <Info size={10} className="text-slate-400" />
                                                                            </span>
                                                                        </Tooltip>
                                                                    </td>
                                                                    <td className="p-2 text-center font-bold text-slate-800">{d.total_comensales}</td>
                                                                    <td className="p-2 text-slate-600">S/ {d.costo_racion}</td>
                                                                    <td className="p-2 text-slate-600">{d.energia_kcal_racion ?? '—'}</td>
                                                                    <td className="p-2 font-semibold text-red-700">{d.hierro_mg_racion ?? '—'}</td>
                                                                    <td className="p-2 text-slate-600">{d.proteina_g_racion ?? '—'}</td>
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                                <p className="text-xs text-slate-500 text-center">
                                                    💡 Haz clic en cualquier fila para ver los detalles completos de la receta
                                                </p>
                                                {/* COM-65 + COM-69: Lista de compras con filtro por día, subsidio y PDF */}
                                                <div className="bg-white rounded-lg border border-slate-200 p-4">
                                                    <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                                                        <h4 className="font-bold text-slate-700 flex items-center gap-2">
                                                            <ShoppingCart size={16} className="text-emerald-600" />
                                                            Lista de compras
                                                        </h4>
                                                        <div className="flex flex-wrap items-center gap-2">
                                                            <div className="flex items-center gap-1 text-xs">
                                                                <Calendar size={12} className="text-slate-500" />
                                                                <span className="text-slate-600 font-medium">Ver:</span>
                                                            </div>
                                                            <button
                                                                onClick={() => cambiarDiaFiltro(p.id, null)}
                                                                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${!diaFiltro[p.id] ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                                                                title="Lista consolidada de la semana">
                                                                Semana
                                                            </button>
                                                            {DIAS_SEMANA.map(d => (
                                                                <button
                                                                    key={d.num}
                                                                    onClick={() => cambiarDiaFiltro(p.id, d.num)}
                                                                    className={`px-2 py-1 rounded text-xs font-medium transition-colors ${diaFiltro[p.id] === d.num ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                                                                    title={`Lista solo para ${d.nombre}`}>
                                                                    {d.nombre.slice(0, 3)}
                                                                </button>
                                                            ))}
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
                                                        const sub = subsidios[cacheKey] || null;
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
                                                                                {/* COM-69: franja resumen del subsidio del mes */}
                                                                                {sub && sub.stock_registrado && (
                                                                                    <div className="m-2 p-2.5 bg-red-50 border border-red-200 rounded-lg text-[11px] text-red-700 flex flex-wrap gap-x-4 gap-y-1 items-center">
                                                                                        <span className="font-bold flex items-center gap-1">
                                                                                            <Gift size={12} /> Subsidio {MESES[sub.mes - 1]} {sub.anio}
                                                                                        </span>
                                                                                        <span>Ítems subsidiados: <b>{sub.items_subsididados}</b></span>
                                                                                        <span>Ahorro estimado: <b>S/ {sub.ahorro_total_estimado}</b></span>
                                                                                        <span>Costo de compra estimado: <b>S/ {sub.costo_total_compra_estimado}</b></span>
                                                                                    </div>
                                                                                )}
                                                                                <div className="overflow-x-auto">
                                                                                    <table className="w-full text-left text-xs">
                                                                                        <thead>
                                                                                            <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                                                                                                <th className="p-2 font-semibold">#</th>
                                                                                                <th className="p-2 font-semibold">Ingrediente</th>
                                                                                                <th className="p-2 font-semibold text-right">Comprar</th>
                                                                                                <th className="p-2 font-semibold">Unidad</th>
                                                                                                <th className="p-2 font-semibold text-right">Subsidio cubre</th>
                                                                                                <th className="p-2 font-semibold">Días de uso</th>
                                                                                                <th className="p-2 font-semibold text-right">Costo</th>
                                                                                            </tr>
                                                                                        </thead>
                                                                                        <tbody className="divide-y divide-slate-100">
                                                                                            {filas.map((row, i) => (
                                                                                                <tr key={i} className="hover:bg-slate-50">
                                                                                                    <td className="p-2 text-slate-500">{i + 1}</td>
                                                                                                    <td className="p-2 font-medium text-slate-800">{row.nombre || '—'}</td>
                                                                                                    <td className="p-2 text-right font-bold text-emerald-700">{row.cantidad ?? '—'}</td>
                                                                                                    <td className="p-2 text-slate-600">{row.unidad || '—'}</td>
                                                                                                    <td className="p-2 text-right text-red-700 font-semibold">
                                                                                                        {row.cantidad_subsidio > 0 ? `${row.cantidad_subsidio} ${row.unidad}` : '—'}
                                                                                                    </td>
                                                                                                    <td className="p-2 text-slate-500 text-[10px]">{(row.dias_uso || []).join(', ') || '—'}</td>
                                                                                                    <td className="p-2 text-right">{celdaCosto(row)}</td>
                                                                                                </tr>
                                                                                            ))}
                                                                                        </tbody>
                                                                                        <tfoot>
                                                                                            <tr className="bg-emerald-50 font-bold text-emerald-800">
                                                                                                <td colSpan="2" className="p-2">Total de ingredientes</td>
                                                                                                <td colSpan="5" className="p-2">{filas.length} ítems</td>
                                                                                            </tr>
                                                                                        </tfoot>
                                                                                    </table>
                                                                                </div>
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
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
            {/* COM-66: Modal de detalles de receta */}
            <ModalDetallesReceta receta={recetaSeleccionada} onClose={() => setRecetaSeleccionada(null)} />
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

/*
COM-69 (trazabilidad): tabla de lista de compras ANTERIOR (5 columnas, sin subsidio),
COMENTADA. Las columnas "Cantidad/Unidad" mostraban el requerimiento total sin
distinguir lo cubierto por el subsidio municipal:
    <th>#</th><th>Ingrediente</th><th>Cantidad</th><th>Unidad</th><th>Días de uso</th>
    ...
    <td>{row.cantidad}</td><td>{row.unidad}</td>
Desde COM-69 la lista solicita comedor_id y muestra "Comprar" (solo lo que se
compra), "Subsidio cubre" y "Costo" con badge SUBSIDIADO en rojo cuando el ítem
queda 100% cubierto por el subsidio del mes.
*/