/**
 * components/pos/POSView.jsx
 * Objetivo: Vista principal del POS (Punto de Venta). Muestra el formulario de venta,
 *           la tabla de ventas del día, las estadísticas y la predicción de demanda.
 *           COM-63: agrega stats de Cocineras (fijo 20) y acceso a carga histórica.
 */
import React, { useState } from 'react';
import { Lightbulb, AlertTriangle, AlertCircle, Upload } from 'lucide-react';
import { usePOS } from '../../hooks/usePOS';
import { useParametros } from '../../context/ParametrosContext';
import { FormularioVenta } from './FormularioVenta';
import { TablaVentasHoy } from './TablaVentasHoy';
import { ModalEdicionVenta } from './ModalEdicionVenta';
import { CargaHistoricaView } from './CargaHistoricaView';

export const POSView = () => {
    const { stats, ventasHoy, prediccion, refrescarDatos } = usePOS();
    const { parametros, cargando } = useParametros();
    const [ventaEditando, setVentaEditando] = useState(null);
    const [mostrarCarga, setMostrarCarga] = useState(false);

    // Si está cargando, mostrar spinner
    if (cargando) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
            </div>
        );
    }

    const tSoc = stats.Social || 0;
    const tAfi = stats.Afiliado || 0;
    const tNor = stats.Normal || 0;
    
    // Usar parámetros dinámicos con fallback a valores por defecto (SOLO para las alertas)
    const limiteSocial = parametros?.LIMITE_SOCIAL || 20;
    const limiteAfiliado = parametros?.LIMITE_AFILIADO || 45;

    // Calcular total de predicción incluyendo cocineras (20 menús fijos diarios)
    const totalPrediccion = prediccion 
        ? prediccion.prediccion_social + prediccion.prediccion_afiliado + prediccion.prediccion_normal + 20
        : 0;

    // Formatear fecha actual
    const fechaHoy = new Date().toLocaleDateString('es-PE', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });

    return (
        <>
            <div className="animate-in fade-in duration-300">
                {/* Botón Carga Histórica */}
                <div className="flex justify-end mb-4">
                    <button
                        onClick={() => setMostrarCarga(!mostrarCarga)}
                        className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                        <Upload size={16} />
                        {mostrarCarga ? 'Ocultar Carga Histórica' : 'Carga Histórica'}
                    </button>
                </div>

                {mostrarCarga && <CargaHistoricaView />}

                {/* PREDICCIÓN - Estilo grande y resaltado */}
                {prediccion && (
                    <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-xl p-6 mb-8 text-white shadow-lg">
                        <div className="flex items-start justify-between flex-wrap gap-4">
                            <div className="flex items-center gap-4">
                                <div className="bg-white/20 p-4 rounded-xl">
                                    <Lightbulb size={40} className="text-blue-100" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-xl mb-1">Proyección de Cocina - {fechaHoy}</h3>
                                    <p className="text-blue-100 text-sm">La IA estima la demanda para planificar la olla:</p>
                                </div>
                            </div>
                            <div className="flex gap-6 bg-white/10 px-6 py-4 rounded-xl border border-white/20">
                                <div className="text-center">
                                    <p className="text-xs text-blue-200 uppercase font-semibold">Social</p>
                                    <p className="text-2xl font-bold">{prediccion.prediccion_social}</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-xs text-blue-200 uppercase font-semibold">Afiliados</p>
                                    <p className="text-2xl font-bold">{prediccion.prediccion_afiliado}</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-xs text-blue-200 uppercase font-semibold">Normales</p>
                                    <p className="text-2xl font-bold">{prediccion.prediccion_normal}</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-xs text-blue-200 uppercase font-semibold">Cocineras</p>
                                    <p className="text-2xl font-bold text-amber-300">20</p>
                                </div>
                                <div className="text-center border-l border-white/20 pl-6">
                                    <p className="text-xs text-amber-200 uppercase font-semibold">Total a Cocinar</p>
                                    <p className="text-4xl font-black text-amber-300">{totalPrediccion}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ESTADÍSTICAS DE VENTAS REALES DEL DÍA (SOLO NÚMEROS REALES, SIN LÍMITES) */}
                <h3 className="font-bold text-slate-700 mb-4 uppercase tracking-wider text-sm border-b pb-2">
                    Progreso de Ventas Real (Hoy)
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Recaudación</p>
                        <p className="text-3xl font-black text-emerald-600 mt-1">S/ {(stats.recaudacion_total||0).toFixed(2)}</p>
                    </div>
                    <div className={`p-4 rounded-xl border shadow-sm text-center ${tSoc > limiteSocial ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
                        <p className="text-xs font-semibold uppercase text-slate-500">Sociales</p>
                        <p className={`text-3xl font-black ${tSoc > limiteSocial ? 'text-red-600' : 'text-slate-700'}`}>
                            {tSoc}
                        </p>
                    </div>
                    <div className={`p-4 rounded-xl border shadow-sm text-center ${tAfi > limiteAfiliado ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
                        <p className="text-xs font-semibold uppercase text-slate-500">Afiliados</p>
                        <p className={`text-3xl font-black ${tAfi > limiteAfiliado ? 'text-amber-600' : 'text-slate-700'}`}>
                            {tAfi}
                        </p>
                    </div>
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Normales</p>
                        <p className="text-3xl font-black text-blue-600 mt-1">{tNor}</p>
                    </div>
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Cocineras</p>
                        <p className="text-3xl font-black text-purple-600 mt-1">20</p>
                    </div>
                </div>

                {/* Alertas (solo para Sociales y Afiliados) */}
                <div className="space-y-3 mb-8">
                    {tSoc > limiteSocial && (
                        <div className="bg-red-100 border border-red-300 text-red-800 px-4 py-3 rounded-lg flex items-center gap-3">
                            <AlertTriangle className="shrink-0" />
                            <p className="font-medium text-sm">¡Alerta! Límite de <b>Casos Sociales</b> sobrepasado.</p>
                        </div>
                    )}
                    {tAfi > limiteAfiliado && (
                        <div className="bg-amber-100 border border-amber-300 text-amber-800 px-4 py-3 rounded-lg flex items-center gap-3">
                            <AlertCircle className="shrink-0" />
                            <p className="font-medium text-sm">Atención: Cupo de <b>Afiliados</b> lleno. Cobrar precio normal.</p>
                        </div>
                    )}
                </div>

                {/* Formulario y Tabla */}
                <div className="grid md:grid-cols-2 gap-6">
                    <FormularioVenta onVentaRegistrada={refrescarDatos} />
                    <TablaVentasHoy ventas={ventasHoy} onEditar={setVentaEditando} />
                </div>
            </div>
            {ventaEditando && <ModalEdicionVenta venta={ventaEditando} onClose={() => setVentaEditando(null)} onActualizacion={refrescarDatos} />}
        </>
    );
};