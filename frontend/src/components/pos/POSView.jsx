/**
components/pos/POSView.jsx
Objetivo: Vista principal del POS (Punto de Venta). Muestra el formulario de venta,
          la tabla de ventas del día, las estadísticas y la predicción de demanda.
          COM-63: agrega stats de Cocineras (fijo 20) y acceso a carga histórica.
Historial:
  COM-63: tarjeta Cocineras fija en 20 + botón Carga Histórica.
  COM-64: predicción con fecha y estilo resaltado; total incluye 20 cocineras.
  COM-64 v3: FIX del NaN y del mensaje de datos insuficientes (lectura como OBJETO
             prediccion_social/afiliado/normal; bloque ámbar cuando sin_datos=true).
  COM-64 v4 (este archivo): la predicción mostrada es la PURA del modelo (el backend
             ya no aplica pisos mínimos). Se agregan:
               * Badge de CONFIANZA (%) con semáforo: ≥90 alta / 70-89 media / <70 baja,
                 con el número de muestras históricas del día de semana.
               * R² por tipo (Social/Afiliado/Normal) cuando el motor lo devuelve.
               * Leyenda explicativa de los niveles de confianza.
             Trazabilidad: bloques y cálculos anteriores quedan COMENTADOS al final.
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
    const tCoc = stats.Cocinera || 0;

    const limiteSocial = parametros?.LIMITE_SOCIAL || 20;
    const limiteAfiliado = parametros?.LIMITE_AFILIADO || 45;

    // COM-64 v3 FIX: detección explícita de "sin datos suficientes" (flag del backend)
    const sinDatos = !prediccion
        || prediccion.sin_datos === true
        || prediccion.prediccion_social == null
        || prediccion.prediccion_afiliado == null
        || prediccion.prediccion_normal == null;

    // COM-64 v3 FIX: total = social + afiliado + normal (del OBJETO) + 20 cocineras fijas
    const totalPrediccion = sinDatos
        ? 0
        : (Number(prediccion.prediccion_social || 0)
           + Number(prediccion.prediccion_afiliado || 0)
           + Number(prediccion.prediccion_normal || 0)
           + 20);

    // COM-64 v4: nivel de confianza con semáforo de color
    const confianza = sinDatos ? null : Number(prediccion.confianza_pct || 0);
    const claseConfianza = confianza == null
        ? 'bg-slate-500/30 border-slate-300'
        : confianza >= 90
            ? 'bg-emerald-500/30 border-emerald-300'
            : confianza >= 70
                ? 'bg-yellow-500/30 border-yellow-300'
                : 'bg-orange-500/30 border-orange-300';
    const etiquetaConfianza = confianza == null
        ? ''
        : confianza >= 90 ? 'Alta' : confianza >= 70 ? 'Media' : 'Baja';

    // COM-64 v4: helper para mostrar R² por tipo solo si el motor lo devolvió
    const r2De = (tipo) => {
        if (sinDatos || !prediccion.r2 || prediccion.r2[tipo] == null) return null;
        return Number(prediccion.r2[tipo]).toFixed(2);
    };

    const fechaHoy = new Date().toLocaleDateString('es-PE', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });

    return (
        <>
            <div className="animate-in fade-in duration-300">
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

                {/* ===== ZONA DE PREDICCIÓN (COM-64 v4: predicción pura + confianza) ===== */}
                {sinDatos ? (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 mb-8 text-amber-800 shadow-sm flex items-center gap-4">
                        <AlertCircle size={32} className="text-amber-600 shrink-0" />
                        <div>
                            <h3 className="font-bold text-lg">Datos insuficientes</h3>
                            <p className="text-amber-700 text-sm">
                                Te faltan datos para poder generar una predicción precisa para este día de la semana.
                                A medida que registres ventas reales, el modelo aprenderá y podrá predecir este día.
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-xl p-6 mb-8 text-white shadow-lg">
                        <div className="flex items-start justify-between flex-wrap gap-4 mb-4">
                            <div className="flex items-center gap-4">
                                <div className="bg-white/20 p-4 rounded-xl">
                                    <Lightbulb size={40} className="text-blue-100" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-xl mb-1">Proyección de Cocina - {fechaHoy}</h3>
                                    <p className="text-blue-100 text-sm">La IA estima la demanda para planificar la olla:</p>
                                </div>
                            </div>
                            {/* COM-64 v4: badge de confianza con semáforo */}
                            <div className={`px-4 py-2 rounded-xl border text-center ${claseConfianza}`}>
                                <p className="text-xs font-semibold uppercase text-white/80">Confianza {etiquetaConfianza}</p>
                                <p className="text-2xl font-black">{confianza}%</p>
                                <p className="text-[10px] text-white/70">{prediccion.n_muestras} muestras del día</p>
                            </div>
                        </div>

                        <div className="flex gap-6 bg-white/10 px-6 py-4 rounded-xl border border-white/20 flex-wrap">
                            <div className="text-center">
                                <p className="text-xs text-blue-200 uppercase font-semibold">Social</p>
                                <p className="text-2xl font-bold">{prediccion.prediccion_social}</p>
                                {r2De('Social') && <p className="text-[10px] text-blue-200/70">R²={r2De('Social')}</p>}
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-blue-200 uppercase font-semibold">Afiliados</p>
                                <p className="text-2xl font-bold">{prediccion.prediccion_afiliado}</p>
                                {r2De('Afiliado') && <p className="text-[10px] text-blue-200/70">R²={r2De('Afiliado')}</p>}
                            </div>
                            <div className="text-center">
                                <p className="text-xs text-blue-200 uppercase font-semibold">Normales</p>
                                <p className="text-2xl font-bold">{prediccion.prediccion_normal}</p>
                                {r2De('Normal') && <p className="text-[10px] text-blue-200/70">R²={r2De('Normal')}</p>}
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

                        {/* COM-64 v4: leyenda de niveles de confianza */}
                        <div className="mt-3 text-[11px] text-blue-100/80 flex items-center gap-4 flex-wrap">
                            <span>🟢 Alta (≥90%): 3+ meses de datos del día</span>
                            <span>🟡 Media (70-89%): 2-3 meses</span>
                            <span>🟠 Baja (50-69%): 1-2 meses</span>
                        </div>
                    </div>
                )}

                {/* ===== VENTAS REALES DE HOY (solo CURRENT_DATE) ===== */}
                <h3 className="font-bold text-slate-700 mb-4 uppercase tracking-wider text-sm border-b pb-2">
                    Progreso de Ventas Real (Hoy)
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Recaudación</p>
                        <p className="text-3xl font-black text-emerald-600 mt-1">S/ {(stats.recaudacion_total || 0).toFixed(2)}</p>
                    </div>
                    <div className={`p-4 rounded-xl border shadow-sm text-center ${tSoc > limiteSocial ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
                        <p className="text-xs font-semibold uppercase text-slate-500">Sociales</p>
                        <p className={`text-3xl font-black ${tSoc > limiteSocial ? 'text-red-600' : 'text-slate-700'}`}>{tSoc}</p>
                    </div>
                    <div className={`p-4 rounded-xl border shadow-sm text-center ${tAfi > limiteAfiliado ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
                        <p className="text-xs font-semibold uppercase text-slate-500">Afiliados</p>
                        <p className={`text-3xl font-black ${tAfi > limiteAfiliado ? 'text-amber-600' : 'text-slate-700'}`}>{tAfi}</p>
                    </div>
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Normales</p>
                        <p className="text-3xl font-black text-blue-600 mt-1">{tNor}</p>
                    </div>
                    <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm text-center">
                        <p className="text-xs font-semibold text-slate-500 uppercase">Cocineras</p>
                        <p className="text-3xl font-black text-purple-600 mt-1">{tCoc}</p>
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

/*
COM-64 v4 (trazabilidad): versiones anteriores COMENTADAS.
1) COM-64 v3 leía la predicción como OBJETO pero el backend aplicaba pisos mínimos
   (max(IA_MIN_*, predicción)), mostrando 15/35/80 aunque el modelo predijera menos:
       social = max(limites_minimos['SOCIAL'], int(round(prediccion[0])))  # backend v3
   Desde COM-64 v4 el backend devuelve la predicción PURA + confianza_pct + r2.
2) COM-64 v2 indexaba como array (prediccion[0]) causando NaN con respuesta objeto:
       const totalPrediccion = prediccion ? prediccion[0] + prediccion[1] + prediccion[2] + 20 : 0;
3) El bloque ámbar de "datos insuficientes" (COM-64 v3) se mantiene SIN cambios:
   se muestra cuando el backend responde sin_datos=true.
*/