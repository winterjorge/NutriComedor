/**
 * components/recipes/ModalCostoReceta.jsx
 * Objetivo: Modal "Evaluar" del Recetario: desglose del costo de una receta en una
 *           fecha dada (unidad de la receta, insumo seleccionado real/predicho/manual
 *           y costo parcial) + totales por receta y por ración.
 * Historial:
 *  - Sprint 2: versión original autoconsultante (api.getCostoReceta) con filas rojas
 *    para ingredientes sin precio y aviso ámbar.
 *  - COM-37 (roto): versión que esperaba `costoData` por props; RecipesView nunca la
 *    envió y el modal no abría. Se COMENTA esa variante y se RESTAURA el auto-fetch.
 *  - COM-37 v2 (este archivo): restaura el contrato original con RecipesView
 *    ({ isOpen, onClose, receta, fecha, onChangeFecha }) y agrega:
 *      * Filas manuales: texto "Obtenido de la Base de Datos" con los colores actuales
 *        del caso sin insumos (fondo rojo), costo real incluido en totales.
 *      * Si el perfil es ADMIN DE SISTEMA y hay ingredientes sin precio: botón
 *        "Agregar precio" por fila con formulario inline (precio por unidad estándar,
 *        rango de fechas opcional) que guarda y re-evalúa al instante.
 *      * Si NO es admin: comportamiento anterior (fila roja + aviso ámbar).
 *      * Badge de costo completo/incompleto (regla: solo recetas completas entran al
 *        flujo del comedor).
 * Uso: Montado por RecipesView.jsx (props sin cambios respecto al original).
 * Referencia: tickets COM-37 / COM-37 v2 (solo trazabilidad).
 */
import React, { useState, useEffect } from 'react';
import { X, Loader2, AlertCircle, Database, TrendingUp, Plus, Save, CheckCircle2 } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

// COM-37 (trazabilidad): variante rota que esperaba datos por props, comentada:
// export const ModalCostoReceta = ({ isOpen, onClose, receta, fecha, costoData }) => {
//     if (!isOpen || !costoData) return null;   // <- RecipesView nunca envió costoData
//     ...
// };

export const ModalCostoReceta = ({ isOpen, onClose, receta, fecha, onChangeFecha }) => {
    const { usuario } = useAuth();
    const esAdminSistema = usuario?.rol === 'Administrador Sistema';

    const [datos, setDatos] = useState(null);
    const [cargando, setCargando] = useState(false);
    const [fechaLocal, setFechaLocal] = useState(fecha || new Date().toISOString().split('T')[0]);

    // COM-37 v2: catálogo de ingredientes (unidad estándar) para el formulario de precio
    const [ingPorId, setIngPorId] = useState({});
    // COM-37 v2: formulario inline de precio manual por ingrediente_id
    const [formPrecio, setFormPrecio] = useState(null);
    const [guardandoPrecio, setGuardandoPrecio] = useState(false);
    const [errorPrecio, setErrorPrecio] = useState('');
    const [exitoPrecio, setExitoPrecio] = useState('');

    const cargarCosto = async (fechaEval) => {
        if (!receta) return;
        setCargando(true);
        setDatos(null);
        try {
            const response = await api.getCostoReceta(receta.id, fechaEval);
            if (response.error) {
                // Si no hay datos para esa fecha, intentar con la fecha actual
                const hoy = new Date().toISOString().split('T')[0];
                if (fechaEval !== hoy) {
                    const responseHoy = await api.getCostoReceta(receta.id, hoy);
                    setDatos(responseHoy);
                    setFechaLocal(hoy);
                    if (onChangeFecha) onChangeFecha(hoy);
                } else {
                    setDatos(response);
                }
            } else {
                setDatos(response);
            }
        } catch (error) {
            setDatos({ error: error.message });
        } finally {
            setCargando(false);
        }
    };

    useEffect(() => {
        if (isOpen && receta) {
            setFormPrecio(null);
            setErrorPrecio('');
            setExitoPrecio('');
            cargarCosto(fechaLocal);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, receta]);

    // COM-37 v2: si es admin y hay filas sin precio, carga unidades estándar una vez
    useEffect(() => {
        if (!isOpen || !esAdminSistema) return;
        const faltantes = (datos?.detalle_insumos || []).filter(d => d.error);
        if (faltantes.length === 0) return;
        let vivo = true;
        api.getIngredientesAdmin(usuario.id)
            .then(list => {
                if (!vivo) return;
                const map = {};
                (list || []).forEach(i => { map[i.id] = i; });
                setIngPorId(map);
            })
            .catch(() => {});
        return () => { vivo = false; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, datos, esAdminSistema]);

    const handleChangeFecha = (e) => {
        const nuevaFecha = e.target.value;
        setFechaLocal(nuevaFecha);
        if (onChangeFecha) onChangeFecha(nuevaFecha);
        cargarCosto(nuevaFecha);
    };

    // COM-37 v2: guarda el precio manual y re-evalúa
    const guardarPrecioManual = async (fila) => {
        const f = formPrecio;
        if (!f || !Number(f.precio) || Number(f.precio) <= 0) {
            setErrorPrecio('Ingrese un precio mayor a cero.');
            return;
        }
        if (f.usar_rango && !f.fecha_inicio) {
            setErrorPrecio('Con el rango activado, la fecha de inicio es obligatoria.');
            return;
        }
        setGuardandoPrecio(true);
        setErrorPrecio('');
        setExitoPrecio('');
        try {
            await api.createPrecioManual(fila.ingrediente_id, {
                usuario_solicitante_id: usuario.id,
                precio_por_unidad: Number(f.precio),
                usar_rango: !!f.usar_rango,
                fecha_inicio: f.usar_rango ? f.fecha_inicio : null,
                fecha_fin: f.usar_rango ? (f.fecha_fin || null) : null,
                observacion: f.observacion || 'Cargado desde Evaluar receta (COM-37)',
            });
            setExitoPrecio(`Precio manual guardado para ${fila.ingrediente}.`);
            setFormPrecio(null);
            cargarCosto(fechaLocal);
        } catch (e) {
            setErrorPrecio(e.message);
        } finally {
            setGuardandoPrecio(false);
        }
    };

    if (!isOpen || !receta) return null;

    const detalle = datos?.detalle_insumos || [];
    const sinPrecio = datos?.ingredientes_sin_precio || 0;
    const manuales = datos?.ingredientes_manuales || 0;
    const completo = datos ? datos.precio_completo : false;
    const inputCls = "w-full px-2 py-1.5 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-emerald-500";

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
                {/* Encabezado */}
                <div className="flex justify-between items-center p-5 border-b bg-emerald-600 text-white">
                    <h3 className="font-bold text-lg">{receta.nombre}</h3>
                    <button onClick={onClose} title="Cerrar">
                        <X size={24} />
                    </button>
                </div>

                <div className="p-6 overflow-y-auto">
                    {/* Fecha + costo por ración */}
                    <div className="flex justify-between items-end mb-4 gap-3 flex-wrap">
                        <input
                            type="date"
                            value={fechaLocal}
                            onChange={handleChangeFecha}
                            className="px-4 py-2 border border-slate-300 rounded-lg outline-none"
                        />
                        {datos && !datos.error && !cargando && (
                            <p className="text-4xl font-black text-emerald-600">
                                S/ {datos.costo_total_racion?.toFixed(2) || '0.00'}
                            </p>
                        )}
                    </div>

                    {/* COM-37 v2: badge de completitud de precios (regla de negocio) */}
                    {datos && !datos.error && (
                        <div className={`mb-4 px-3 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 ${
                            completo ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                     : 'bg-amber-50 text-amber-800 border border-amber-200'}`}>
                            {completo ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                            {completo
                                ? 'Costo completo: receta apta para el flujo del comedor (propuestas y planificación).'
                                : `Costo incompleto (${sinPrecio} ingrediente(s) sin precio): la receta NO entrará a las propuestas del comedor hasta completar sus precios.`}
                        </div>
                    )}

                    {cargando ? (
                        <Loader2 className="animate-spin text-emerald-600 mx-auto" size={40} />
                    ) : detalle.length ? (
                        <div className="space-y-2">
                            <table className="w-full text-left text-sm">
                                <thead className="bg-slate-100">
                                    <tr>
                                        <th className="p-2">Ingrediente</th>
                                        <th className="p-2">Insumo Seleccionado</th>
                                        <th className="p-2 text-right">Costo</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {detalle.map((d, i) => (
                                        <React.Fragment key={i}>
                                            <tr className={d.error || d.es_manual ? 'bg-red-50' : 'hover:bg-slate-50'}>
                                                <td className="p-2 font-medium">{d.ingrediente}</td>
                                                <td className="p-2">
                                                    {d.error ? (
                                                        <span className="text-red-600 text-xs flex items-center gap-1">
                                                            <AlertCircle size={12} /> {d.error}
                                                            {/* COM-37 v2: alta rápida de precio manual solo para Admin */}
                                                            {esAdminSistema && d.ingrediente_id && (
                                                                <button
                                                                    onClick={() => {
                                                                        setFormPrecio({
                                                                            ingrediente_id: d.ingrediente_id,
                                                                            precio: '',
                                                                            usar_rango: false,
                                                                            fecha_inicio: fechaLocal,
                                                                            fecha_fin: '',
                                                                            observacion: '',
                                                                        });
                                                                        setErrorPrecio('');
                                                                        setExitoPrecio('');
                                                                    }}
                                                                    className="ml-2 inline-flex items-center gap-1 px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-[10px] font-bold transition-colors"
                                                                >
                                                                    <Plus size={11} /> Agregar precio
                                                                </button>
                                                            )}
                                                        </span>
                                                    ) : d.es_manual ? (
                                                        /* COM-37: precio manual de la BD, colores del caso sin insumos */
                                                        <span className="text-red-600 text-xs flex items-center gap-1 font-semibold">
                                                            <Database size={12} /> {d.insumo_comprado}
                                                        </span>
                                                    ) : d.es_prediccion ? (
                                                        <span className="text-amber-600 text-xs flex items-center gap-1 font-semibold">
                                                            <TrendingUp size={12} /> {d.insumo_comprado}
                                                        </span>
                                                    ) : (
                                                        <span className="text-slate-700">{d.insumo_comprado}</span>
                                                    )}
                                                </td>
                                                <td className={`p-2 text-right font-bold ${d.error ? 'text-red-600' : 'text-emerald-700'}`}>
                                                    {d.error ? (
                                                        <span>S/ 0.00</span>
                                                    ) : (
                                                        `S/${d.costo_parcial?.toFixed(2) || '0.00'}`
                                                    )}
                                                </td>
                                            </tr>

                                            {/* COM-37 v2: formulario inline de precio manual (solo Admin) */}
                                            {esAdminSistema && formPrecio && formPrecio.ingrediente_id === d.ingrediente_id && (
                                                <tr className="bg-emerald-50/60">
                                                    <td colSpan="3" className="p-3">
                                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                                            <div>
                                                                <label className="text-[10px] font-bold text-slate-600 block mb-0.5">
                                                                    Precio S/ por {ingPorId[d.ingrediente_id]
                                                                        ? `${ingPorId[d.ingrediente_id].unidad_abrev} (${ingPorId[d.ingrediente_id].unidad_nombre})`
                                                                        : 'unidad estándar'}
                                                                </label>
                                                                <input type="number" min="0.01" step="0.10" value={formPrecio.precio}
                                                                    onChange={(e) => setFormPrecio({ ...formPrecio, precio: e.target.value })}
                                                                    className={inputCls} placeholder="Ej. 18.50" />
                                                            </div>
                                                            <div className="flex items-end pb-1">
                                                                <label className="flex items-center gap-1.5 text-[11px] text-slate-700 cursor-pointer">
                                                                    <input type="checkbox" checked={formPrecio.usar_rango}
                                                                        onChange={(e) => setFormPrecio({ ...formPrecio, usar_rango: e.target.checked })}
                                                                        className="accent-emerald-600" />
                                                                    Usar rango de fechas
                                                                </label>
                                                            </div>
                                                            <div>
                                                                <label className="text-[10px] font-bold text-slate-600 block mb-0.5">Inicio</label>
                                                                <input type="date" value={formPrecio.fecha_inicio} disabled={!formPrecio.usar_rango}
                                                                    onChange={(e) => setFormPrecio({ ...formPrecio, fecha_inicio: e.target.value })}
                                                                    className={`${inputCls} disabled:bg-slate-100`} />
                                                            </div>
                                                            <div>
                                                                <label className="text-[10px] font-bold text-slate-600 block mb-0.5">Fin (opcional)</label>
                                                                <input type="date" value={formPrecio.fecha_fin} disabled={!formPrecio.usar_rango}
                                                                    onChange={(e) => setFormPrecio({ ...formPrecio, fecha_fin: e.target.value })}
                                                                    className={`${inputCls} disabled:bg-slate-100`} />
                                                            </div>
                                                        </div>
                                                        <div className="flex items-center gap-2 mt-2">
                                                            <input type="text" value={formPrecio.observacion}
                                                                onChange={(e) => setFormPrecio({ ...formPrecio, observacion: e.target.value })}
                                                                placeholder="Observación (opcional)" className={`${inputCls} flex-1`} />
                                                            <button
                                                                onClick={() => guardarPrecioManual(d)}
                                                                disabled={guardandoPrecio}
                                                                className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
                                                            >
                                                                {guardandoPrecio ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                                                                Guardar y re-evaluar
                                                            </button>
                                                            <button
                                                                onClick={() => setFormPrecio(null)}
                                                                className="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-xs font-bold transition-colors"
                                                            >
                                                                Cancelar
                                                            </button>
                                                        </div>
                                                        {errorPrecio && (
                                                            <p className="mt-1 text-[11px] text-red-600 flex items-center gap-1"><AlertCircle size={11} /> {errorPrecio}</p>
                                                        )}
                                                    </td>
                                                </tr>
                                            )}
                                        </React.Fragment>
                                    ))}
                                </tbody>
                            </table>

                            {/* Avisos inferiores */}
                            {sinPrecio > 0 && !esAdminSistema && (
                                <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-sm">
                                    <p className="font-semibold mb-1">⚠ Ingredientes sin precio:</p>
                                    <p>Algunos ingredientes no tienen insumos disponibles para la fecha seleccionada.
                                    Esto puede deberse a que el scraper aún no ha capturado precios para esos productos.</p>
                                </div>
                            )}
                            {sinPrecio > 0 && esAdminSistema && (
                                <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-sm">
                                    <p className="font-semibold mb-1">⚠ Ingredientes sin precio:</p>
                                    <p>Use el botón "Agregar precio" de cada fila para registrar un precio promedio manual
                                    (con o sin rango de fechas). Mientras falten precios, la receta queda fuera de las
                                    propuestas del comedor.</p>
                                </div>
                            )}
                            {manuales > 0 && (
                                <div className="mt-2 bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-xs flex items-center gap-2">
                                    <Database size={14} />
                                    {manuales} ingrediente(s) costeados con precio manual de la Base de Datos
                                    ("Obtenido de la Base de Datos"), incluidos en el total.
                                </div>
                            )}
                            {exitoPrecio && (
                                <div className="mt-2 bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-emerald-700 text-xs flex items-center gap-2">
                                    <CheckCircle2 size={14} /> {exitoPrecio}
                                </div>
                            )}
                        </div>
                    ) : datos?.error ? (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-amber-800">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="shrink-0 mt-0.5" size={20} />
                                <div>
                                    <p className="font-semibold mb-1">No hay datos para esta fecha</p>
                                    <p className="text-sm">{datos.error}</p>
                                </div>
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
};