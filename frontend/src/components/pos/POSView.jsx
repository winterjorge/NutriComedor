import React, { useState } from 'react';
import { Lightbulb, AlertTriangle, AlertCircle } from 'lucide-react';
import { usePOS } from '../../hooks/usePOS';
import { useParametros } from '../../context/ParametrosContext';
import { FormularioVenta } from './FormularioVenta';
import { TablaVentasHoy } from './TablaVentasHoy';
import { ModalEdicionVenta } from './ModalEdicionVenta';

export const POSView = () => {
    const { stats, ventasHoy, prediccion, refrescarDatos } = usePOS();
    const { parametros, cargando } = useParametros(); // <-- CAMBIO: Usar useParametros
    const [ventaEditando, setVentaEditando] = useState(null);

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

    // Usar parámetros dinámicos con fallback a valores por defecto
    const limiteSocial = parametros?.LIMITE_SOCIAL || 20;
    const limiteAfiliado = parametros?.LIMITE_AFILIADO || 45;

    return (
        <>
            <div className="animate-in fade-in duration-300">
                {prediccion && (
                    <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-xl p-5 mb-8 text-white shadow-md flex items-center justify-between flex-wrap gap-4">
                        <div className="flex items-center gap-4">
                            <div className="bg-white/20 p-3 rounded-lg">
                                <Lightbulb size={32} className="text-blue-100" />
                            </div>
                            <div>
                                <h3 className="font-bold text-lg">Proyección de Cocina (Random Forest)</h3>
                                <p className="text-blue-100 text-sm">La IA estima la demanda para planificar la olla de hoy:</p>
                            </div>
                        </div>
                        <div className="flex gap-6 bg-white/10 px-5 py-3 rounded-xl border border-white/20">
                            <div className="text-center">
                                <p className="text-xs text-blue-200 uppercase">Social</p>
                                <p className="text-xl font-bold">{prediccion.prediccion_social}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-blue-200 uppercase">Afiliados</p>
                                <p className="text-xl font-bold">{prediccion.prediccion_afiliado}</p>
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-blue-200 uppercase">Normales</p>
                                <p className="text-xl font-bold">{prediccion.prediccion_normal}</p>
                            </div>
                            <div className="text-center border-l border-white/20 pl-6">
                                <p className="text-xs text-amber-200 uppercase">Cocinar</p>
                                <p className="text-3xl font-black text-amber-300">{prediccion.total_raciones_sugeridas}</p>
                            </div>
                        </div>
                    </div>
                )}

                <h3 className="font-bold text-slate-700 mb-4 uppercase tracking-wider text-sm border-b pb-2">Progreso de Ventas Real (Hoy)</h3>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Recaudación</p>
                        <p className="text-3xl font-black text-emerald-600 mt-1">S/ {(stats.recaudacion_total||0).toFixed(2)}</p>
                    </div>
                    
                    <div className={`p-4 rounded-xl border shadow-sm text-center ${tSoc > limiteSocial ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
                        <p className="text-xs font-semibold uppercase text-slate-500">Sociales</p>
                        <p className={`text-3xl font-black ${tSoc > limiteSocial ? 'text-red-600' : 'text-slate-700'}`}>
                            {tSoc} <span className="text-sm font-medium text-slate-400">/ {limiteSocial}</span>
                        </p>
                    </div>
                    
                    <div className={`p-4 rounded-xl border shadow-sm text-center ${tAfi > limiteAfiliado ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
                        <p className="text-xs font-semibold uppercase text-slate-500">Afiliados</p>
                        <p className={`text-3xl font-black ${tAfi > limiteAfiliado ? 'text-amber-600' : 'text-slate-700'}`}>
                            {tAfi} <span className="text-sm font-medium text-slate-400">/ {limiteAfiliado}</span>
                        </p>
                    </div>
                    
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Normales</p>
                        <p className="text-3xl font-black text-blue-600 mt-1">{stats.Normal || 0}</p>
                    </div>
                </div>

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

                <div className="grid md:grid-cols-2 gap-6">
                    <FormularioVenta onVentaRegistrada={refrescarDatos} />
                    <TablaVentasHoy ventas={ventasHoy} onEditar={setVentaEditando} />
                </div>
            </div>
            {ventaEditando && <ModalEdicionVenta venta={ventaEditando} onClose={() => setVentaEditando(null)} onActualizacion={refrescarDatos} />}
        </>
    );
};