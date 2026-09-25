/**
 * components/budget/GenerarPropuestasView.jsx
 * Objetivo: Vista COM-8 "Propuestas de Menú": genera y muestra 3 propuestas de menú
 *           semanal (NutriMax, EconoMax, BalanceMax) del motor greedy, cada una con
 *           costo total, calorías promedio/día, RECOLECCIÓN PROYECTADA y MARGEN
 *           (ventas - compras), top 3 de ingredientes (solo vegetales/frutas/proteínas)
 *           y el listado de platos por día. El personal Directivo fija una propuesta
 *           ("Seleccionar esta opción"); "Regenerar" pide 3 opciones nuevas (jitter).
 *           Incluye historial de menús seleccionados con detalle expandible por día.
 * Historial:
 *  - COM-8 v1: 3 tarjetas, selección solo Directivo, regenerar e historial.
 *  - COM-8 v2: (a) selector de DÍAS DE COCINA en chips (Lun-Dom, por defecto Lun-Vie)
 *              enviado al motor como dias_semana, para excluir feriados o incluir
 *              sábados según la operativa real; (b) tarjetas de recolección proyectada
 *              y margen al mismo nivel visual que costo total y kcal/día.
 * Permisos: vista para Directivo y Operativo (módulo 'propuestas', COM-25). El botón
 *           de selección solo aparece si el backend responde puede_seleccionar=true.
 * Uso: Montada por App.jsx en la pestaña "Propuestas de Menú".
 * Referencia: ticket COM-8 / HU-08 (solo trazabilidad; los nombres obedecen a la funcionalidad).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Sparkles, RefreshCw, Loader2, AlertCircle, Wallet, Flame,
    ShoppingBasket, CalendarDays, History, ChevronDown, ChevronUp, Lock,
    CheckCircle2, TrendingUp, Coins
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

// Estilos por variante (clases literales para Tailwind)
const COLORES_VARIANTE = {
    NUTRI: { chip: 'bg-red-100 text-red-700', borde: 'border-red-300' },
    ECONO: { chip: 'bg-amber-100 text-amber-700', borde: 'border-amber-300' },
    BALANCE: { chip: 'bg-emerald-100 text-emerald-700', borde: 'border-emerald-300' },
};

// COM-8 v2: días de cocina seleccionables (1=Lunes .. 7=Domingo)
const DIAS_OPCIONES = [
    { id: 1, label: 'Lun' },
    { id: 2, label: 'Mar' },
    { id: 3, label: 'Mié' },
    { id: 4, label: 'Jue' },
    { id: 5, label: 'Vie' },
    { id: 6, label: 'Sáb' },
    { id: 7, label: 'Dom' },
];

// COM-8 v2: por defecto se cocina de lunes a viernes
const DIAS_DEFAULT = [1, 2, 3, 4, 5];

export const GenerarPropuestasView = () => {
    const { usuario, seleccion } = useAuth();
    const comedorId = seleccion?.comedor_id;

    // Parámetros de generación
    const [presupuesto, setPresupuesto] = useState('2500');
    const [fechaRef, setFechaRef] = useState('');
    const [seed, setSeed] = useState(0);
    // COM-8 v2: días de cocina seleccionados
    const [diasSel, setDiasSel] = useState(DIAS_DEFAULT);

    // Estado de la sesión de propuestas
    const [sesion, setSesion] = useState(null);
    const [seleccionadaId, setSeleccionadaId] = useState(null);
    const [cargando, setCargando] = useState(false);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');
    const [confSeleccion, setConfSeleccion] = useState(null);

    // Historial de menús definitivos
    const [historial, setHistorial] = useState([]);
    const [mostrarHistorial, setMostrarHistorial] = useState(false);
    const [expandidos, setExpandidos] = useState({});
    const [diasHistorial, setDiasHistorial] = useState({});

    const puedeSeleccionar = !!sesion?.puede_seleccionar;

    const cargarHistorial = useCallback(async () => {
        if (!comedorId) return;
        try {
            setHistorial(await api.getHistorialPropuestas(comedorId, usuario.id));
        } catch (e) {
            /* sección opcional: no bloquea la vista */
        }
    }, [comedorId, usuario.id]);

    useEffect(() => { cargarHistorial(); }, [cargarHistorial]);

    // COM-8 v2: alterna un día de cocina (mínimo 1 día activo)
    const toggleDia = (id) => {
        setDiasSel(prev => {
            if (prev.includes(id)) {
                if (prev.length === 1) return prev;   // no permitir cero días
                return prev.filter(d => d !== id);
            }
            return [...prev, id].sort((a, b) => a - b);
        });
    };

    // ---------- Generación / regeneración ----------
    const generar = async (nuevoSeed) => {
        if (!comedorId) {
            setError('No hay un comedor seleccionado en su sesión.');
            return;
        }
        const pres = Number(presupuesto);
        if (!pres || pres <= 0) {
            setError('Ingrese un presupuesto semanal válido (mayor a 0).');
            return;
        }
        if (diasSel.length === 0) {
            setError('Seleccione al menos un día de cocina.');
            return;
        }
        setCargando(true);
        setError('');
        setSeleccionadaId(null);
        try {
            const res = await api.generarPropuestas({
                comedor_id: comedorId,
                presupuesto_semanal: pres,
                fecha_referencia: fechaRef || null,
                seed: nuevoSeed,
                dias_semana: diasSel,          // COM-8 v2: días de cocina elegidos
                usuario_solicitante_id: usuario.id,
            });
            setSesion(res);
            setSeed(nuevoSeed);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    };

    const regenerar = () => generar(seed + 1);

    // ---------- Selección del menú definitivo ----------
    const confirmarSeleccion = async () => {
        const propuesta = confSeleccion;
        setConfSeleccion(null);
        setCargando(true);
        setError('');
        try {
            const res = await api.seleccionarPropuesta(propuesta.candidata_id, {
                usuario_solicitante_id: usuario.id,
            });
            setSeleccionadaId(propuesta.candidata_id);
            setExito(res.message || `Menú ${res.etiqueta} fijado para la semana del ${res.semana_inicio}.`);
            await cargarHistorial();
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    };

    // ---------- Historial expandible ----------
    const toggleDias = async (id) => {
        if (expandidos[id]) {
            setExpandidos({ ...expandidos, [id]: false });
            return;
        }
        setExpandidos({ ...expandidos, [id]: true });
        if (!diasHistorial[id]) {
            try {
                const dias = await api.getHistorialDias(id, usuario.id);
                setDiasHistorial(prev => ({ ...prev, [id]: dias }));
            } catch (e) {
                setError(e.message);
            }
        }
    };

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Sparkles className="text-emerald-600" size={22} /> Propuestas de Menú Semanal
                    </h2>
                    <p className="text-sm text-slate-500">
                        El motor genera 3 opciones con distintos criterios (nutrición, costo y balance).
                        Elija la que mejor se adapte a su experiencia.
                    </p>
                </div>
                {sesion && (
                    <button
                        onClick={regenerar}
                        disabled={cargando}
                        className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        <RefreshCw size={16} /> Regenerar
                    </button>
                )}
            </div>

            {/* Formulario de generación */}
            <div className="flex flex-wrap gap-3 mb-4 items-end">
                <div>
                    <label className="flex items-center gap-1 text-xs font-semibold text-slate-600 mb-1">
                        <Wallet size={12} /> Presupuesto semanal (S/)
                    </label>
                    <input
                        type="number" min="1" step="50"
                        value={presupuesto}
                        onChange={(e) => setPresupuesto(e.target.value)}
                        className="w-40 px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                </div>
                <div>
                    <label className="flex items-center gap-1 text-xs font-semibold text-slate-600 mb-1">
                        <CalendarDays size={12} /> Semana de referencia
                    </label>
                    <input
                        type="date"
                        value={fechaRef}
                        onChange={(e) => setFechaRef(e.target.value)}
                        className="px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                </div>
                <button
                    onClick={() => generar(seed)}
                    disabled={cargando}
                    className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                >
                    {cargando ? <Loader2 className="animate-spin" size={16} /> : <Sparkles size={16} />}
                    Generar 3 propuestas
                </button>
            </div>

            {/* COM-8 v2: selector de días de cocina (chips) */}
            <div className="mb-5">
                <label className="flex items-center gap-1 text-xs font-semibold text-slate-600 mb-1">
                    <CalendarDays size={12} /> Días de cocina de la semana
                    <span className="font-normal text-slate-400">
                        (desmarque feriados o marque sábados según abra el comedor)
                    </span>
                </label>
                <div className="flex flex-wrap gap-1.5">
                    {DIAS_OPCIONES.map(d => {
                        const activo = diasSel.includes(d.id);
                        return (
                            <button
                                key={d.id}
                                type="button"
                                onClick={() => toggleDia(d.id)}
                                className={`px-3 py-2 rounded-lg text-xs font-bold transition-colors border ${
                                    activo
                                        ? 'bg-emerald-600 text-white border-emerald-600'
                                        : 'bg-white text-slate-500 border-slate-300 hover:bg-slate-100'
                                }`}
                            >
                                {d.label}
                            </button>
                        );
                    })}
                </div>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Tarjetas de propuestas */}
            {cargando && !sesion ? (
                <div className="p-12 text-center text-emerald-600">
                    <Loader2 className="animate-spin mx-auto" size={28} />
                    <p className="text-sm mt-2 text-slate-500">Calculando menús con el motor de optimización...</p>
                </div>
            ) : sesion ? (
                <>
                    <p className="text-xs text-slate-500 mb-3">
                        Semana del <b>{sesion.semana_inicio}</b> · {sesion.propuestas.length} propuestas ·
                        Días de cocina:{' '}
                        <b>
                            {(sesion.dias_seleccionados || []).map(d => DIAS_OPCIONES[d - 1]?.label).join(', ')}
                        </b>
                        {!puedeSeleccionar && (
                            <span className="ml-2 inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full font-semibold">
                                <Lock size={11} /> Solo el personal directivo puede fijar el menú
                            </span>
                        )}
                    </p>
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
                        {sesion.propuestas.map(p => {
                            const col = COLORES_VARIANTE[p.variante] || COLORES_VARIANTE.BALANCE;
                            const r = p.resumen;
                            const elegida = seleccionadaId === p.candidata_id;
                            return (
                                <div key={p.candidata_id}
                                    className={`bg-white border rounded-xl p-4 flex flex-col ${col.borde} ${elegida ? 'ring-2 ring-emerald-400' : ''}`}>
                                    {/* Encabezado de la tarjeta */}
                                    <div className="flex items-center gap-2 mb-2">
                                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${col.chip}`}>{p.etiqueta}</span>
                                        {elegida && (
                                            <span className="ml-auto flex items-center gap-1 text-emerald-700 text-xs font-bold">
                                                <CheckCircle2 size={14} /> Seleccionada
                                            </span>
                                        )}
                                    </div>
                                    <p className="text-xs text-slate-500 mb-3">{p.descripcion}</p>

                                    {/* COM-8 v2: resumen en 4 tarjetas: compras, kcal, ventas y margen */}
                                    <div className="grid grid-cols-2 gap-2 mb-3 text-center">
                                        <div className="bg-slate-50 rounded-lg py-2">
                                            <p className="flex items-center justify-center gap-1 text-sm font-bold text-slate-800">
                                                <Wallet size={12} className="text-slate-500" /> S/ {r.costo_total_semana}
                                            </p>
                                            <p className="text-[10px] text-slate-500">Costo total (compras)</p>
                                        </div>
                                        <div className="bg-slate-50 rounded-lg py-2">
                                            <p className="flex items-center justify-center gap-1 text-sm font-bold text-slate-800">
                                                <Flame size={12} className="text-orange-500" /> {r.calorias_promedio_dia} kcal
                                            </p>
                                            <p className="text-[10px] text-slate-500">Promedio por día</p>
                                        </div>
                                        <div className="bg-slate-50 rounded-lg py-2">
                                            <p className="flex items-center justify-center gap-1 text-sm font-bold text-slate-800">
                                                <Coins size={12} className="text-emerald-600" /> S/ {r.recoleccion_total_semana}
                                            </p>
                                            <p className="text-[10px] text-slate-500">Recolección proyectada (ventas)</p>
                                        </div>
                                        <div className="bg-slate-50 rounded-lg py-2">
                                            <p className={`flex items-center justify-center gap-1 text-sm font-bold ${
                                                r.margen_proyectado >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                                                <TrendingUp size={12} /> S/ {r.margen_proyectado}
                                            </p>
                                            <p className="text-[10px] text-slate-500">Margen (ventas − compras)</p>
                                        </div>
                                    </div>

                                    <div className="mb-3">
                                        <p className="flex items-center gap-1 text-[11px] font-semibold text-slate-600 mb-1">
                                            <ShoppingBasket size={11} /> Top 3 ingredientes
                                        </p>
                                        <div className="flex flex-wrap gap-1">
                                            {(r.top_ingredientes || []).map(ing => (
                                                <span key={ing} className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-[10px] font-medium">
                                                    {ing}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                    <p className={`text-[11px] font-semibold mb-3 ${r.dentro_de_presupuesto ? 'text-emerald-700' : 'text-red-600'}`}>
                                        {r.dentro_de_presupuesto
                                            ? `Dentro del presupuesto de S/ ${r.presupuesto_semanal}`
                                            : `Excede el presupuesto de S/ ${r.presupuesto_semanal}`}
                                    </p>

                                    {/* Menú resumido por día (solo días de cocina) */}
                                    <div className="space-y-1 mb-4 flex-1">
                                        {(p.menu || []).map(d => (
                                            <div key={d.dia_semana} className="flex justify-between items-start gap-2 text-xs border-b border-slate-100 pb-1">
                                                <div>
                                                    <span className="font-bold text-slate-700">{d.dia_nombre}: </span>
                                                    <span className="text-slate-600">{d.receta_nombre}</span>
                                                    <span className="block text-[10px] text-slate-400">{d.cluster_etiqueta}</span>
                                                </div>
                                                <span className="text-slate-600 font-semibold shrink-0">S/ {d.costo_racion}</span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Acción de selección (solo Directivo) */}
                                    {puedeSeleccionar && !elegida && seleccionadaId === null && (
                                        <button
                                            onClick={() => setConfSeleccion(p)}
                                            disabled={cargando}
                                            className="w-full px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                                        >
                                            Seleccionar esta opción
                                        </button>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </>
            ) : (
                <div className="p-12 text-center bg-slate-50 border border-slate-200 rounded-2xl mb-6">
                    <Sparkles size={36} className="text-emerald-600 mx-auto mb-3" />
                    <h3 className="font-bold text-slate-800 mb-2">Genere sus 3 propuestas de menú</h3>
                    <p className="text-sm text-slate-500 max-w-md mx-auto">
                        Configure el presupuesto, marque los días que abrirá el comedor y pulse
                        "Generar 3 propuestas". El motor combinará nutrición y precio con tres
                        criterios distintos para que elija el menú que mejor se adapte.
                    </p>
                </div>
            )}

            {/* Historial de menús seleccionados */}
            <button
                onClick={() => setMostrarHistorial(!mostrarHistorial)}
                className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-800 transition-colors mb-2"
            >
                <History size={14} />
                {mostrarHistorial ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                Historial de menús semanales ({historial.length})
            </button>
            {mostrarHistorial && (
                <div className="overflow-x-auto rounded-lg border border-slate-200 mb-4">
                    <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                        <thead>
                            <tr className="bg-slate-100 text-slate-600">
                                <th className="p-3 font-semibold">Semana</th>
                                <th className="p-3 font-semibold">Propuesta</th>
                                <th className="p-3 font-semibold">Costo</th>
                                <th className="p-3 font-semibold">Recolección</th>
                                <th className="p-3 font-semibold">Margen</th>
                                <th className="p-3 font-semibold">Estado</th>
                                <th className="p-3 font-semibold">Seleccionado por</th>
                                <th className="p-3 font-semibold text-right">Detalle</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                            {historial.length === 0 ? (
                                <tr><td colSpan="8" className="p-6 text-center text-slate-500">Aún no hay menús seleccionados.</td></tr>
                            ) : historial.map(h => (
                                <React.Fragment key={h.id}>
                                    <tr className="hover:bg-slate-50">
                                        <td className="p-3 font-medium text-slate-800">{h.fecha_referencia}</td>
                                        <td className="p-3 text-slate-600">{h.etiqueta || h.variante || '—'}</td>
                                        <td className="p-3 text-slate-600">S/ {h.costo_total_semana}</td>
                                        <td className="p-3 text-slate-600">S/ {h.recoleccion_total_proyectada}</td>
                                        <td className={`p-3 font-semibold ${h.margen >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                                            S/ {h.margen}
                                        </td>
                                        <td className="p-3">
                                            <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                                h.estado === 'VIGENTE' ? 'bg-emerald-100 text-emerald-700'
                                                : h.estado === 'REEMPLAZADA' ? 'bg-amber-100 text-amber-700'
                                                : 'bg-slate-100 text-slate-600'}`}>
                                                {h.estado}
                                            </span>
                                        </td>
                                        <td className="p-3 text-slate-600">{h.seleccionado_por || '—'}</td>
                                        <td className="p-3 text-right">
                                            <button
                                                onClick={() => toggleDias(h.id)}
                                                className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                                title="Ver menú por día"
                                            >
                                                {expandidos[h.id] ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                                            </button>
                                        </td>
                                    </tr>
                                    {expandidos[h.id] && (
                                        <tr>
                                            <td colSpan="8" className="p-3 bg-slate-50">
                                                {!diasHistorial[h.id] ? (
                                                    <Loader2 className="animate-spin mx-auto text-emerald-600" size={18} />
                                                ) : (
                                                    <ul className="space-y-1 text-xs text-slate-600">
                                                        {diasHistorial[h.id].map(d => (
                                                            <li key={d.id} className="flex justify-between gap-4">
                                                                <span><b>{d.dia_nombre}:</b> {d.nombre_receta}</span>
                                                                <span>
                                                                    costo S/ {d.costo_total} · recolección S/ {d.recoleccion_proyectada}
                                                                </span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                )}
                                            </td>
                                        </tr>
                                    )}
                                </React.Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Confirmación y éxito */}
            <ModalConfirmacion
                isOpen={!!confSeleccion}
                onClose={() => setConfSeleccion(null)}
                onConfirm={confirmarSeleccion}
                mensaje={confSeleccion
                    ? `¿Fijar el menú "${confSeleccion.etiqueta}" (costo S/ ${confSeleccion.resumen.costo_total_semana}, margen S/ ${confSeleccion.resumen.margen_proyectado}) como definitivo para la semana del ${sesion?.semana_inicio}? Solo el personal directivo podrá cambiarlo después.`
                    : ''}
                tipo="warning"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};