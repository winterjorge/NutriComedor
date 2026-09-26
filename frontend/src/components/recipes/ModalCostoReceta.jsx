/**
 * components/recipes/ModalCostoReceta.jsx
 * Objetivo: Modal de "Evaluar" del Recetario: desglose del costo de una receta en una
 *           fecha dada, por ingrediente, con la unidad de la receta, el insumo
 *           seleccionado (real del día o predicho por Random Forest) y el costo parcial;
 *           totales por receta y por ración en el pie.
 * Historial:
 *  - Sprint 2: versión original (filas rojas para ingredientes sin insumo/precio,
 *    ámbar para predicciones RF, alerta ámbar de subestimación).
 *  - COM-37 (este archivo): filas de precio MANUAL (fallback cuando el scraper/RF no
 *    pueden predecir). La columna "Insumo Seleccionado" muestra el texto
 *    "Obtenido de la Base de Datos" y la fila CONSERVA los colores actuales del caso
 *    "sin insumos disponibles" (fondo rojo y texto rojo), según requerimiento del
 *    ticket; el costo parcial se muestra con el valor real costeo manual. La alerta
 *    ámbar inferior se extiende para informar cuántos ingredientes se costearon con
 *    precio manual (incluidos en el total). Nada existente se elimina.
 * Uso: Montado por RecipesView.jsx con props { isOpen, onClose, receta, fecha, costoData }.
 * Referencia: tickets COM-37 / HU-05 (solo trazabilidad).
 */
import React from 'react';
import { X, AlertCircle, TrendingUp, Database, Utensils, CalendarDays } from 'lucide-react';

export const ModalCostoReceta = ({ isOpen, onClose, receta, fecha, costoData }) => {
    if (!isOpen || !costoData) return null;

    const detalle = costoData.detalle_insumos || [];
    const sinPrecio = costoData.ingredientes_sin_precio || 0;
    const manuales = costoData.ingredientes_manuales || 0;   // COM-37
    const predichos = costoData.ingredientes_predichos || 0;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-[88vh] flex flex-col overflow-hidden animate-in zoom-in duration-200">
                {/* Encabezado */}
                <div className="bg-emerald-700 text-white p-4 flex items-center gap-2">
                    <Utensils size={18} />
                    <div className="flex-1">
                        <p className="font-bold text-sm">Costo de receta: {receta?.nombre || `#${costoData.receta_id}`}</p>
                        <p className="text-[11px] text-emerald-100 flex items-center gap-1">
                            <CalendarDays size={12} /> Evaluado al {fecha}
                        </p>
                    </div>
                    <button onClick={onClose} className="p-1 hover:bg-emerald-800 rounded transition-colors" title="Cerrar">
                        <X size={18} />
                    </button>
                </div>

                {/* Cuerpo: tabla de desglose */}
                <div className="p-4 overflow-y-auto">
                    <table className="w-full text-left text-sm border-collapse">
                        <thead>
                            <tr className="text-slate-500 border-b border-slate-200">
                                <th className="p-2 font-semibold">Ingrediente</th>
                                <th className="p-2 font-semibold">Cantidad (receta)</th>
                                <th className="p-2 font-semibold">Insumo Seleccionado</th>
                                <th className="p-2 font-semibold text-right">Costo</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {detalle.map((d, i) => (
                                <tr
                                    key={i}
                                    /* COM-37: las filas manuales conservan el fondo rojo
                                       del caso "sin insumos disponibles" (requerimiento). */
                                    className={d.error || d.es_manual ? 'bg-red-50' : 'hover:bg-slate-50'}
                                >
                                    <td className="p-2 text-slate-700 font-medium">{d.ingrediente}</td>
                                    <td className="p-2 text-slate-500">{d.cantidad_usada}</td>
                                    <td className="p-2">
                                        {d.error ? (
                                            /* Caso original: sin insumo / sin precios */
                                            <span className="flex items-center gap-1 text-red-600 text-xs font-semibold">
                                                <AlertCircle size={13} /> {d.insumo_comprado}
                                            </span>
                                        ) : d.es_manual ? (
                                            /* COM-37: precio manual de la BD; mismo estilo
                                               rojo del caso sin insumos, texto requerido. */
                                            <span className="flex items-center gap-1 text-red-600 text-xs font-semibold">
                                                <Database size={13} /> {d.insumo_comprado}
                                            </span>
                                        ) : d.es_prediccion ? (
                                            /* Predicción Random Forest */
                                            <span className="flex items-center gap-1 text-amber-600 text-xs font-semibold">
                                                <TrendingUp size={13} /> {d.insumo_comprado}
                                            </span>
                                        ) : (
                                            /* Precio real del día */
                                            <span className="text-slate-600 text-xs">{d.insumo_comprado}</span>
                                        )}
                                    </td>
                                    <td className={`p-2 text-right font-bold ${
                                        /* COM-37: el costo manual se muestra en rojo como el
                                           caso sin insumos (colores actuales conservados). */
                                        d.error || d.es_manual ? 'text-red-600' : 'text-emerald-700'
                                    }`}>
                                        S/ {Number(d.costo_parcial || 0).toFixed(2)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {/* Alertas de calidad del costeo (paleta ámbar existente) */}
                    {(sinPrecio > 0 || manuales > 0) && (
                        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-xs space-y-1">
                            {sinPrecio > 0 && (
                                <p className="flex items-center gap-2">
                                    <AlertCircle size={14} />
                                    {sinPrecio} ingrediente(s) sin precio para esta fecha: el costo total está subestimado.
                                </p>
                            )}
                            {manuales > 0 && (
                                /* COM-37: informa que hay costos manuales incluidos en el total */
                                <p className="flex items-center gap-2">
                                    <Database size={14} />
                                    {manuales} ingrediente(s) costeados con precio manual de la Base de Datos
                                    ("Obtenido de la Base de Datos"): incluidos en el total, sujetos a edición en
                                    Gestión de Ingredientes.
                                </p>
                            )}
                        </div>
                    )}

                    {/* Leyenda de fuentes de precio */}
                    <div className="mt-3 flex flex-wrap gap-3 text-[10px] text-slate-500">
                        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-slate-400" /> Precio real del día</span>
                        <span className="flex items-center gap-1"><TrendingUp size={11} className="text-amber-600" /> Predicho (Random Forest){predichos > 0 ? ` (${predichos})` : ''}</span>
                        <span className="flex items-center gap-1"><Database size={11} className="text-red-600" /> Manual BD (COM-37){manuales > 0 ? ` (${manuales})` : ''}</span>
                        <span className="flex items-center gap-1"><AlertCircle size={11} className="text-red-600" /> Sin precio{sinPrecio > 0 ? ` (${sinPrecio})` : ''}</span>
                    </div>
                </div>

                {/* Pie: totales */}
                <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
                    <div>
                        <p className="text-xs text-slate-500">Costo total receta ({costoData.raciones_receta} raciones)</p>
                        <p className="text-lg font-bold text-slate-800">S/ {Number(costoData.costo_total_receta || 0).toFixed(2)}</p>
                    </div>
                    <div className="text-right">
                        <p className="text-xs text-slate-500">Costo por ración</p>
                        <p className="text-lg font-bold text-emerald-700">S/ {Number(costoData.costo_total_racion || 0).toFixed(2)}</p>
                    </div>
                </div>
            </div>
        </div>
    );
};