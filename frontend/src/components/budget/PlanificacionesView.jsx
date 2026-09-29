/**
 * components/budget/PlanificacionesView.jsx
 * Objetivo: Vista de Planificaciones semanales (menús definitivos del comedor). Lista
 *           las planificaciones vigentes/reemplazadas y, al expandirlas, muestra:
 *           (1) tarjetas de resumen con Costo semanal, Recolección semanal, MARGEN
 *               (ventas - compras), Kcal/día, Hierro/día y Proteína/día;
 *           (2) el detalle POR DÍA con comensales Social/Afiliado/Normal en columnas
 *               separadas (anticipación diaria solicitada en COM-8 v4), recolección
 *               proyectada y nutrición por ración;
 *           (3) la lista de compras consolidada y la acción de eliminar planificación
 *               (funcionalidad original de Sprint 2, conservada activa).
 * Historial:
 *  - Sprint 2: versión original (api.getPlanificaciones / getPlanificacionDetalle /
 *    eliminarPlanificacion / getListaCompras).
 *  - COM-8 v2: reconstruida sobre /propuestas/historial y /propuestas/historial/{id}/dias
 *              (maestro presupuesto_semanal + detalle planificacion_dia vinculados al
 *              comedor y a la candidata COM-8).
 *  - COM-8 v4: comensales por día en columnas separadas; tarjetas de hierro y proteína;
 *              nutrición por ración en el detalle diario.
 *  - COM-8 v5 (este archivo): trazabilidad recuperada. Todo lo reemplazado se conserva
 *              COMENTADO (carga original, detalle original y bloque de comensales
 *              semanal); eliminar planificación se mantiene ACTIVO.
 * Permisos: módulo 'planificaciones' (Directivo y Operativo del comedor, COM-25/COM-8).
 * Uso: Montada por App.jsx en la pestaña "Planificaciones".
 * Referencia: tickets COM-8 / HU-06 / HU-07 (solo trazabilidad).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    ClipboardList, Loader2, AlertCircle, ChevronDown, ChevronUp,
    Wallet, Coins, TrendingUp, Flame, Users, ShoppingCart, History,
    Droplet, Trash2
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';

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

    // Lista de compras: { id: filas } y { id: bool cargando }
    const [compras, setCompras] = useState({});
    const [cargandoCompras, setCargandoCompras] = useState({});
    const [mostrarCompras, setMostrarCompras] = useState({});

    // COM-8 v5: confirmación de eliminación (funcionalidad original de Sprint 2, conservada)
    const [confEliminar, setConfEliminar] = useState(null);

    // ---------- Carga del listado ----------
    const cargar = useCallback(async () => {
        if (!comedorId) return;
        setCargando(true);
        setError('');
        try {
            // COM-8 v2: lectura filtrada por comedor y con variante/estado/selector.
            setPlanificaciones(await api.getHistorialPropuestas(comedorId, usuario.id));
            // COM-8 v5 (trazabilidad): carga original de Sprint 2, comentada:
            // setPlanificaciones(await api.getPlanificaciones());
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
        if (cache[plan.id]) return; // ya cargado previamente
        setCargandoDetalle({ ...cargandoDetalle, [plan.id]: true });
        try {
            // COM-8 v2/v4: detalle con comensales por día, recolección y nutrición por ración.
            const dias = await api.getHistorialDias(plan.id, usuario.id);
            // COM-8 v5 (trazabilidad): detalle original de Sprint 2, comentado:
            // const dias = await api.getPlanificacionDetalle(plan.id);
            setCache(prev => ({ ...prev, [plan.id]: { dias } }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoDetalle({ ...cargandoDetalle, [plan.id]: false });
        }
    };

    // ---------- Lista de compras (Sprint 2, conservada activa) ----------
    const toggleCompras = async (plan) => {
        if (mostrarCompras[plan.id]) {
            setMostrarCompras({ ...mostrarCompras, [plan.id]: false });
            return;
        }
        setMostrarCompras({ ...mostrarCompras, [plan.id]: true });
        if (compras[plan.id]) return;
        setCargandoCompras({ ...cargandoCompras, [plan.id]: true });
        try {
            const data = await api.getListaCompras(plan.id);
            const filas = Array.isArray(data) ? data : (data.items || data.grupos || []);
            setCompras(prev => ({ ...prev, [plan.id]: filas }));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoCompras({ ...cargandoCompras, [plan.id]: false });
        }
    };

    // ---------- Eliminación (Sprint 2, conservada activa sobre el mismo maestro) ----------
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

    // COM-8 v4: promedios nutricionales calculados desde los días persistidos
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
                                                    {/* COM-8 v5: eliminar planificación (Sprint 2), conservado activo */}
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
                                                        {/* COM-8 v4: tarjetas de resumen (margen = ventas - compras,
                                                            al mismo nivel visual que costo y kcal; hierro y proteína
                                                            agregados por ser factor crítico) */}
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

                                                        {/* COM-8 v5 (trazabilidad): bloque de comensales de COM-8 v2,
                                                            COMENTADO. Mostraba un único número por categoría para toda
                                                            la semana (tomado del día 1), lo cual era erróneo para
                                                            anticipar la atención diaria. Reemplazado por las columnas
                                                            Social/Afiliado/Normal POR DÍA en la tabla siguiente.
                                                        <div className="grid grid-cols-3 gap-3">
                                                            <div className="border rounded-xl p-3 text-center bg-red-50 border-red-200 text-red-700">
                                                                <p className="text-3xl font-bold">{det.dias[0].comensales_social}</p>
                                                                <p className="text-xs font-semibold">Casos Sociales / día</p>
                                                            </div>
                                                            <div className="border rounded-xl p-3 text-center bg-blue-50 border-blue-200 text-blue-700">
                                                                <p className="text-3xl font-bold">{det.dias[0].comensales_afiliado}</p>
                                                                <p className="text-xs font-semibold">Afiliados / día</p>
                                                            </div>
                                                            <div className="border rounded-xl p-3 text-center bg-emerald-50 border-emerald-200 text-emerald-700">
                                                                <p className="text-3xl font-bold">{det.dias[0].comensales_normal}</p>
                                                                <p className="text-xs font-semibold">Normales / día</p>
                                                            </div>
                                                        </div>
                                                        */}

                                                        {/* COM-8 v4: tabla por día con comensales en columnas
                                                            separadas, recolección proyectada y nutrición por ración */}
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

                                                        {/* Lista de compras de la semana (Sprint 2, conservada) */}
                                                        <div>
                                                            <button onClick={() => toggleCompras(p)}
                                                                className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-800 transition-colors">
                                                                <ShoppingCart size={14} />
                                                                {mostrarCompras[p.id] ? 'Ocultar lista de compras' : 'Ver lista de compras'}
                                                            </button>
                                                            {mostrarCompras[p.id] && (
                                                                <div className="mt-2 rounded-lg border border-slate-200 bg-white p-3">
                                                                    {cargandoCompras[p.id] ? (
                                                                        <Loader2 className="animate-spin mx-auto text-emerald-600" size={18} />
                                                                    ) : (compras[p.id] || []).length === 0 ? (
                                                                        <p className="text-xs text-slate-500">Sin ítems de compra registrados.</p>
                                                                    ) : (
                                                                        <table className="w-full text-left text-xs">
                                                                            <thead>
                                                                                <tr className="text-slate-500 border-b border-slate-200">
                                                                                    <th className="p-1.5 font-semibold">Insumo</th>
                                                                                    <th className="p-1.5 font-semibold">Cantidad</th>
                                                                                    <th className="p-1.5 font-semibold">Unidad</th>
                                                                                    <th className="p-1.5 font-semibold">Costo aprox.</th>
                                                                                </tr>
                                                                            </thead>
                                                                            <tbody className="divide-y divide-slate-100">
                                                                                {compras[p.id].map((row, i) => (
                                                                                    <tr key={i}>
                                                                                        <td className="p-1.5 text-slate-700">
                                                                                            {row.nombre || row.ingrediente || row.insumo || '—'}
                                                                                        </td>
                                                                                        <td className="p-1.5 text-slate-600">{row.cantidad ?? '—'}</td>
                                                                                        <td className="p-1.5 text-slate-600">{row.unidad || '—'}</td>
                                                                                        <td className="p-1.5 text-slate-600">
                                                                                            {row.costo_total ?? row.costo ?? row.costo_estimado ?? '—'}
                                                                                        </td>
                                                                                    </tr>
                                                                                ))}
                                                                            </tbody>
                                                                        </table>
                                                                    )}
                                                                </div>
                                                            )}
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

            {/* COM-8 v5: confirmación de eliminación (Sprint 2, conservada) */}
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