/**
 * components/recipes/ModalCostoReceta.jsx
 * Objetivo: Modal "Evaluar" del Recetario: desglose del costo de una receta en una
 *           fecha dada (unidad de USO, insumo seleccionado real/predicho/manual y costo
 *           parcial) + totales por receta y por ración.
 * Historial:
 *  - Sprint 2: versión original autoconsultante con filas rojas sin precio y aviso ámbar.
 *  - COM-37 (roto): variante que esperaba `costoData` por props; comentada.
 *  - COM-37 v2: auto-fetch + filas manuales ("Obtenido de la Base de Datos") + badge de
 *    costo completo + formulario inline de precio manual (solo Admin).
 *  - COM-37 v5/v6: botón "Asignar insumo/precio" por fila sin precio (solo Admin) que
 *    abre el modal simplificado de un solo ingrediente (vincular insumo del scraper o
 *    registrar insumo manual con unidad+precio+vigencia+equivalencia) y re-evalúa.
 *  - COM-37 v8 (este archivo): FIX del reporte "vinculé y solo una receta quedó completa":
 *    al vincular un insumo que PERTENECE A OTRO INGREDIENTE, el modal muestra la
 *    confirmación "Vincular y fusionar", que envía fusionar_ingrediente_origen=true para
 *    que el ingrediente sinónimo se fusione en el actual y TODAS sus recetas hereden el
 *    precio (el sinónimo queda como [OBSOLETO]). Sin ese aviso, la reasignación dejaba
 *    huérfano al ingrediente origen.
 * Uso: Montado por RecipesView.jsx con props { isOpen, onClose, receta, fecha, onChangeFecha }.
 * Referencia: tickets COM-37 v2/v5/v6/v8 (solo trazabilidad).
 */
import React, { useState, useEffect } from 'react';
import {
    X, Loader2, AlertCircle, Database, TrendingUp, CheckCircle2,
    Search, Package, Scale, Save, GitMerge
} from 'lucide-react';
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

    // COM-37 v5: catálogo de ingredientes (unidad de uso por defecto) y unidades
    const [ingPorId, setIngPorId] = useState({});
    const [unidades, setUnidades] = useState([]);

    // COM-37 v5/v6: modal simplificado "Asignar insumo/precio" (una fila sin precio)
    const [modalAsignar, setModalAsignar] = useState(null);
    const [tabAsignar, setTabAsignar] = useState('scraper');
    const [qAsignar, setQAsignar] = useState('');
    const [resultadosAsignar, setResultadosAsignar] = useState([]);
    const [buscandoAsignar, setBuscandoAsignar] = useState(false);
    const [formManual, setFormManual] = useState({
        nombre: '', unidad_medida_id: '', precio_por_unidad: '', usar_rango: false,
        fecha_inicio: '', fecha_fin: '', observacion: '',
        eq_unidad_uso_id: '', eq_gramos: '',
    });
    const [guardandoAsignar, setGuardandoAsignar] = useState(false);
    const [errorAsignar, setErrorAsignar] = useState('');
    const [exitoPrecio, setExitoPrecio] = useState('');
    // COM-37 v8: confirmación de fusión cuando el insumo pertenece a otro ingrediente
    const [confirmFusion, setConfirmFusion] = useState(null);

    const cargarCosto = async (fechaEval) => {
        if (!receta) return;
        setCargando(true);
        setDatos(null);
        try {
            const response = await api.getCostoReceta(receta.id, fechaEval);
            if (response.error) {
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
            setModalAsignar(null);
            setConfirmFusion(null);
            setErrorAsignar('');
            setExitoPrecio('');
            cargarCosto(fechaLocal);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isOpen, receta]);

    // COM-37 v5: si es admin y hay filas sin precio, carga catálogo y unidades
    useEffect(() => {
        if (!isOpen || !esAdminSistema) return;
        const faltantes = (datos?.detalle_insumos || []).filter(d => d.error);
        if (faltantes.length === 0) return;
        let vivo = true;
        Promise.all([api.getIngredientesAdmin(usuario.id), api.getUnidadesMedida()])
            .then(([ings, ums]) => {
                if (!vivo) return;
                const map = {};
                (ings || []).forEach(i => { map[i.id] = i; });
                setIngPorId(map);
                setUnidades(ums || []);
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

    // ---------- COM-37 v5/v6/v8: modal simplificado ----------
    const abrirAsignar = (fila) => {
        const ing = ingPorId[fila.ingrediente_id];
        setModalAsignar(fila);
        setTabAsignar('scraper');
        setQAsignar(fila.ingrediente || '');
        setErrorAsignar('');
        setConfirmFusion(null);
        setResultadosAsignar([]);
        setFormManual({
            nombre: `${fila.ingrediente} (manual)`,
            unidad_medida_id: '',
            precio_por_unidad: '',
            usar_rango: false,
            fecha_inicio: fechaLocal,
            fecha_fin: '',
            observacion: 'Cargado desde Evaluar receta (COM-37)',
            eq_unidad_uso_id: ing ? String(ing.unidad_medida_id) : '',
            eq_gramos: '',
        });
        buscarScraper(fila.ingrediente || '');
    };

    const buscarScraper = async (q) => {
        setBuscandoAsignar(true);
        setErrorAsignar('');
        try {
            setResultadosAsignar(await api.buscarInsumosAdmin(q || '', false, usuario.id));
        } catch (e) {
            setErrorAsignar(e.message);
        } finally {
            setBuscandoAsignar(false);
        }
    };

    // COM-37 v8: si el insumo pertenece a OTRO ingrediente, pedir confirmación de fusión
    const pedirVincular = (ins) => {
        if (ins.ingrediente_id && ins.ingrediente_id !== modalAsignar.ingrediente_id) {
            setConfirmFusion(ins);
        } else {
            vincularScraper(ins, false);
        }
    };

    const vincularScraper = async (ins, fusionar) => {
        setGuardandoAsignar(true);
        setErrorAsignar('');
        try {
            const res = await api.vincularInsumo(modalAsignar.ingrediente_id, {
                usuario_solicitante_id: usuario.id,
                insumo_id: ins.id,
                reasignar: true,
                fusionar_ingrediente_origen: !!fusionar,
                equivalencias: [],
            });
            setExitoPrecio(res.message || `Insumo '${ins.nombre}' vinculado.`);
            setConfirmFusion(null);
            setModalAsignar(null);
            cargarCosto(fechaLocal);
        } catch (e) {
            setErrorAsignar(e.message);
        } finally {
            setGuardandoAsignar(false);
        }
    };

    const crearManual = async () => {
        if (!formManual.nombre.trim() || !formManual.unidad_medida_id || !Number(formManual.precio_por_unidad)) {
            setErrorAsignar('Complete nombre, unidad de compra y precio mayor a cero.');
            return;
        }
        if (formManual.usar_rango && !formManual.fecha_inicio) {
            setErrorAsignar('Con el rango activado, la fecha de inicio es obligatoria.');
            return;
        }
        setGuardandoAsignar(true);
        setErrorAsignar('');
        try {
            const equivalencias = [];
            if (formManual.eq_unidad_uso_id && Number(formManual.eq_gramos) > 0) {
                equivalencias.push({
                    unidad_uso_id: Number(formManual.eq_unidad_uso_id),
                    gramos_por_unidad_uso: Number(formManual.eq_gramos),
                    observacion: 'Equivalencia inicial desde Evaluar receta',
                });
            }
            const res = await api.crearInsumoManual(modalAsignar.ingrediente_id, {
                usuario_solicitante_id: usuario.id,
                nombre: formManual.nombre.trim(),
                unidad_medida_id: Number(formManual.unidad_medida_id),
                precio_por_unidad: Number(formManual.precio_por_unidad),
                usar_rango: formManual.usar_rango,
                fecha_inicio: formManual.usar_rango ? formManual.fecha_inicio : null,
                fecha_fin: formManual.usar_rango ? (formManual.fecha_fin || null) : null,
                observacion: formManual.observacion || null,
                equivalencias,
            });
            setExitoPrecio(res.message || 'Insumo manual creado y vinculado.');
            setModalAsignar(null);
            cargarCosto(fechaLocal);
        } catch (e) {
            setErrorAsignar(e.message);
        } finally {
            setGuardandoAsignar(false);
        }
    };

    // COM-37 v2 (trazabilidad): guardado del formulario inline legacy de precio manual
    // por ingrediente, COMENTADO. Reemplazado por el modal simplificado v5/v8:
    // const guardarPrecioManual = async (fila) => { ... api.createPrecioManual(...) ... };

    if (!isOpen || !receta) return null;

    const detalle = datos?.detalle_insumos || [];
    const sinPrecio = datos?.ingredientes_sin_precio || 0;
    const manuales = datos?.ingredientes_manuales || 0;
    const completo = datos ? datos.precio_completo : false;
    const inputCls = "w-full px-2 py-1.5 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-emerald-500";
    const labelCls = "text-[10px] font-bold text-slate-600 block mb-0.5";

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

                    {/* Badge de completitud de precios (regla del flujo del comedor) */}
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
                                        <tr key={i} className={d.error || d.es_manual ? 'bg-red-50' : 'hover:bg-slate-50'}>
                                            <td className="p-2 font-medium">{d.ingrediente}</td>
                                            <td className="p-2">
                                                {d.error ? (
                                                    <span className="text-red-600 text-xs flex items-center gap-1 flex-wrap">
                                                        <AlertCircle size={12} /> {d.error}
                                                        {esAdminSistema && d.ingrediente_id && (
                                                            <button
                                                                onClick={() => abrirAsignar(d)}
                                                                className="ml-2 inline-flex items-center gap-1 px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-[10px] font-bold transition-colors"
                                                            >
                                                                <Package size={11} /> Asignar insumo/precio
                                                            </button>
                                                        )}
                                                    </span>
                                                ) : d.es_manual ? (
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
                                                {d.error ? <span>S/ 0.00</span> : `S/${d.costo_parcial?.toFixed(2) || '0.00'}`}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>

                            {/* COM-37 v2 (trazabilidad): formulario inline legacy COMENTADO
                                (reemplazado por el modal simplificado v5/v8):
                            {esAdminSistema && formPrecio && formPrecio.ingrediente_id === d.ingrediente_id && (
                                <tr className="bg-emerald-50/60"> ... inputs precio/rango ... </tr>
                            )}
                            */}

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
                                    <p>Use "Asignar insumo/precio" en cada fila: vincule un insumo del scraper o
                                    registre un insumo manual. Si el insumo pertenece a un ingrediente sinónimo,
                                    elija "Vincular y fusionar" para que TODAS las recetas del sinónimo hereden el
                                    precio. Mientras falten precios, la receta queda fuera de las propuestas.</p>
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

            {/* ===== COM-37 v5/v6/v8: modal simplificado de asignación ===== */}
            {modalAsignar && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[88vh] flex flex-col overflow-hidden">
                        <div className="bg-emerald-700 text-white p-4 flex items-center gap-2">
                            <Package size={18} />
                            <div className="flex-1">
                                <p className="font-bold text-sm">Asignar insumo/precio: {modalAsignar.ingrediente}</p>
                                <p className="text-[11px] text-emerald-100">
                                    Unidad de uso en esta receta: {modalAsignar.cantidad_usada}
                                </p>
                            </div>
                            <button onClick={() => { setModalAsignar(null); setConfirmFusion(null); }} className="p-1 hover:bg-emerald-800 rounded">
                                <X size={18} />
                            </button>
                        </div>

                        <div className="p-4 overflow-y-auto space-y-4">
                            {/* Pestañas */}
                            <div className="grid grid-cols-2 gap-2">
                                <button
                                    onClick={() => setTabAsignar('scraper')}
                                    className={`p-2 rounded-lg text-xs font-bold transition-colors flex items-center justify-center gap-1 ${
                                        tabAsignar === 'scraper' ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
                                    <Search size={13} /> Insumo del scraper
                                </button>
                                <button
                                    onClick={() => setTabAsignar('manual')}
                                    className={`p-2 rounded-lg text-xs font-bold transition-colors flex items-center justify-center gap-1 ${
                                        tabAsignar === 'manual' ? 'bg-purple-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
                                    <Package size={13} /> Registrar insumo manual
                                </button>
                            </div>

                            {errorAsignar && (
                                <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-xs">
                                    <AlertCircle size={14} /> {errorAsignar}
                                </div>
                            )}

                            {/* COM-37 v8: confirmación de fusión de sinónimos */}
                            {confirmFusion && (
                                <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 text-xs space-y-2">
                                    <p className="font-bold flex items-center gap-1"><GitMerge size={13} /> El insumo pertenece a otro ingrediente</p>
                                    <p>
                                        "{confirmFusion.nombre}" está vinculado actualmente a <b>{confirmFusion.ingrediente_actual}</b>.
                                        Si "{confirmFusion.ingrediente_actual}" es un sinónimo de "{modalAsignar.ingrediente}",
                                        fusiónelos para que <b>todas</b> sus recetas hereden este precio (el sinónimo quedará
                                        marcado como [OBSOLETO] y sus líneas de receta se moverán aquí).
                                    </p>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => vincularScraper(confirmFusion, true)}
                                            disabled={guardandoAsignar}
                                            className="flex-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-[11px] font-bold transition-colors disabled:opacity-50">
                                            Vincular y fusionar (recomendado)
                                        </button>
                                        <button
                                            onClick={() => vincularScraper(confirmFusion, false)}
                                            disabled={guardandoAsignar}
                                            className="flex-1 px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-[11px] font-bold transition-colors disabled:opacity-50">
                                            Solo vincular
                                        </button>
                                    </div>
                                    <button onClick={() => setConfirmFusion(null)}
                                        className="text-[10px] underline text-slate-600">Cancelar</button>
                                </div>
                            )}

                            {/* Vía 1: buscar y vincular insumo del scraper */}
                            {tabAsignar === 'scraper' && !confirmFusion && (
                                <div className="space-y-2">
                                    <div className="flex gap-2">
                                        <input
                                            type="text"
                                            value={qAsignar}
                                            onChange={(e) => setQAsignar(e.target.value)}
                                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); buscarScraper(qAsignar); } }}
                                            placeholder="Nombre del insumo..."
                                            className={inputCls}
                                        />
                                        <button
                                            onClick={() => buscarScraper(qAsignar)}
                                            disabled={buscandoAsignar}
                                            className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition-colors disabled:opacity-50">
                                            {buscandoAsignar ? <Loader2 className="animate-spin" size={13} /> : 'Buscar'}
                                        </button>
                                    </div>
                                    <div className="space-y-1.5 max-h-52 overflow-y-auto">
                                        {resultadosAsignar.map(ins => (
                                            <div key={ins.id} className="border border-slate-200 rounded-lg p-2 flex items-center gap-2 text-xs">
                                                <div className="flex-1">
                                                    <p className="font-bold text-slate-800">{ins.nombre}</p>
                                                    <p className="text-[10px] text-slate-500">
                                                        {ins.origen} · {ins.unidad_nombre}
                                                        {ins.ingrediente_id ? ` · vinculado a: ${ins.ingrediente_actual}` : ' · sin vincular'}
                                                    </p>
                                                </div>
                                                <button
                                                    onClick={() => pedirVincular(ins)}
                                                    disabled={guardandoAsignar}
                                                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-[11px] font-bold transition-colors disabled:opacity-50">
                                                    Vincular
                                                </button>
                                            </div>
                                        ))}
                                        {resultadosAsignar.length === 0 && !buscandoAsignar && (
                                            <p className="text-[11px] text-slate-500 text-center p-3">
                                                Sin resultados. Pruebe otro texto o registre un insumo manual.
                                            </p>
                                        )}
                                    </div>
                                </div>
                            )}

                            {/* Vía 2: registrar insumo manual con precio y equivalencia */}
                            {tabAsignar === 'manual' && (
                                <div className="space-y-3">
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <label className={labelCls}>Nombre del insumo</label>
                                            <input type="text" value={formManual.nombre}
                                                onChange={(e) => setFormManual({ ...formManual, nombre: e.target.value })}
                                                className={inputCls} />
                                        </div>
                                        <div>
                                            <label className={labelCls}>Unidad de COMPRA</label>
                                            <select value={formManual.unidad_medida_id}
                                                onChange={(e) => setFormManual({ ...formManual, unidad_medida_id: e.target.value })}
                                                className={inputCls}>
                                                <option value="">Seleccionar...</option>
                                                {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className={labelCls}>Precio por unidad (S/)</label>
                                            <input type="number" min="0.01" step="0.10" value={formManual.precio_por_unidad}
                                                onChange={(e) => setFormManual({ ...formManual, precio_por_unidad: e.target.value })}
                                                className={inputCls} />
                                        </div>
                                        <div className="flex items-end pb-1">
                                            <label className="flex items-center gap-1.5 text-[11px] text-slate-700 cursor-pointer">
                                                <input type="checkbox" checked={formManual.usar_rango}
                                                    onChange={(e) => setFormManual({ ...formManual, usar_rango: e.target.checked })}
                                                    className="accent-purple-600" />
                                                Rango de vigencia
                                            </label>
                                        </div>
                                        <div>
                                            <label className={labelCls}>Inicio</label>
                                            <input type="date" value={formManual.fecha_inicio} disabled={!formManual.usar_rango}
                                                onChange={(e) => setFormManual({ ...formManual, fecha_inicio: e.target.value })}
                                                className={`${inputCls} disabled:bg-slate-100`} />
                                        </div>
                                        <div>
                                            <label className={labelCls}>Fin (opcional)</label>
                                            <input type="date" value={formManual.fecha_fin} disabled={!formManual.usar_rango}
                                                onChange={(e) => setFormManual({ ...formManual, fecha_fin: e.target.value })}
                                                className={`${inputCls} disabled:bg-slate-100`} />
                                        </div>
                                    </div>

                                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                                        <p className="text-[11px] font-bold text-slate-700 mb-2 flex items-center gap-1">
                                            <Scale size={12} /> Equivalencia unidad de USO → gramos (opcional)
                                        </p>
                                        <div className="grid grid-cols-2 gap-2">
                                            <div>
                                                <label className={labelCls}>Unidad de uso</label>
                                                <select value={formManual.eq_unidad_uso_id}
                                                    onChange={(e) => setFormManual({ ...formManual, eq_unidad_uso_id: e.target.value })}
                                                    className={inputCls}>
                                                    <option value="">Sin equivalencia</option>
                                                    {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className={labelCls}>Gramos por unidad</label>
                                                <input type="number" min="0.0001" step="0.0001" value={formManual.eq_gramos}
                                                    onChange={(e) => setFormManual({ ...formManual, eq_gramos: e.target.value })}
                                                    className={inputCls} placeholder="Ej. 0.5" />
                                            </div>
                                        </div>
                                        <p className="text-[10px] text-slate-500 mt-1">
                                            Si la deja vacía, se usará la conversión estándar de la unidad de uso.
                                        </p>
                                    </div>

                                    <button
                                        onClick={crearManual}
                                        disabled={guardandoAsignar}
                                        className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-bold transition-colors disabled:opacity-50">
                                        {guardandoAsignar ? <Loader2 className="animate-spin" size={15} /> : <Save size={15} />}
                                        Crear insumo manual y re-evaluar
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};