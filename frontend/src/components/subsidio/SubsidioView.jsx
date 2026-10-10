/**
 * components/subsidio/SubsidioView.jsx
 * Objetivo: COM-59A: pestaña "Subsidio de Víveres": gestión del subsidio mensual de
 *           víveres que el comedor recibe del municipio (mes calendario), con
 *           equivalencia en gramos para auditoría del motor de costos.
 * Permisos (reflejando al backend): gestión (crear/editar/borrar) para Admin de
 *           Sistemas (cualquier comedor) y Directivos del comedor de la sesión;
 *           perfiles municipales/auditoría ven solo lectura (el backend re-valida).
 * Historial:
 *  - COM-59A: versión original.
 * Uso: Montada por App.jsx en la pestaña "Subsidio" (módulo 'subsidio').
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Package, Plus, Edit3, Trash2, Loader2, AlertCircle, RefreshCw, Scale, CheckCircle2
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

const FORM_VACIO = {
    subsidio_id: null,
    ingrediente_id: '',
    cantidad_recibida: '',
    unidad_medida_id: '',
    observacion: '',
};

export const SubsidioView = () => {
    const { usuario, seleccion } = useAuth();
    const esAdminSistema = usuario?.rol === 'Administrador Sistema';

    // Comedor objetivo: el de la sesión (Directivo) o selector (Admin de Sistemas)
    const [comedoresLista, setComedoresLista] = useState([]);
    const [comedorSel, setComedorSel] = useState(seleccion?.comedor_id || '');
    // Período (mes calendario)
    const hoy = new Date();
    const [anio, setAnio] = useState(hoy.getFullYear());
    const [mes, setMes] = useState(hoy.getMonth() + 1);

    const [lineas, setLineas] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');

    // Catálogos para el formulario
    const [ingredientes, setIngredientes] = useState([]);
    const [unidades, setUnidades] = useState([]);

    // Formulario de línea (alta/edición)
    const [form, setForm] = useState(FORM_VACIO);
    const [mostrarForm, setMostrarForm] = useState(false);
    const [guardando, setGuardando] = useState(false);
    const [confBorrado, setConfBorrado] = useState(null);

    // Gestión permitida: Admin de Sistemas o Directivo con comedor de sesión
    const puedeGestionar = esAdminSistema || !!seleccion?.comedor_id;

    // ---------- Cargadores ----------
    const cargarLineas = useCallback(async () => {
        if (!comedorSel) { setLineas([]); setCargando(false); return; }
        setCargando(true);
        setError('');
        try {
            const data = await api.getSubsidioMes({
                comedor_id: comedorSel, anio, mes, usuario_solicitante_id: usuario.id,
            });
            setLineas(data.lineas || []);
        } catch (e) {
            setLineas([]);
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [comedorSel, anio, mes, usuario.id]);

    useEffect(() => {
        // Selector de comedor solo para Admin de Sistemas (perfil SISTEMA sin comedor fijo)
        if (!seleccion?.comedor_id) {
            api.getComedores().then(list => setComedoresLista(Array.isArray(list) ? list : [])).catch(() => setComedoresLista([]));
        }
        // Catálogos del formulario
        Promise.all([api.getIngredientesDisponibles(), api.getUnidadesMedida()])
            .then(([ings, ums]) => { setIngredientes(ings || []); setUnidades(ums || []); })
            .catch(() => { setIngredientes([]); setUnidades([]); });
    }, [seleccion]);

    useEffect(() => { cargarLineas(); }, [cargarLineas]);

    // ---------- Acciones ----------
    const abrirAlta = () => { setForm(FORM_VACIO); setMostrarForm(true); };
    const abrirEdicion = (l) => {
        setForm({
            subsidio_id: l.id,
            ingrediente_id: String(l.ingrediente_id),
            cantidad_recibida: String(l.cantidad_recibida),
            unidad_medida_id: String(l.unidad_medida_id),
            observacion: l.observacion || '',
        });
        setMostrarForm(true);
    };

    const guardar = async (e) => {
        e.preventDefault();
        if (!form.ingrediente_id || !form.cantidad_recibida || !form.unidad_medida_id) {
            setError('Ingrediente, cantidad y unidad son obligatorios.');
            return;
        }
        setGuardando(true);
        setError('');
        try {
            if (form.subsidio_id) {
                const res = await api.editarSubsidio(form.subsidio_id, {
                    usuario_solicitante_id: usuario.id,
                    cantidad_recibida: Number(form.cantidad_recibida),
                    unidad_medida_id: Number(form.unidad_medida_id),
                    observacion: form.observacion || null,
                });
                setExito(res.message || 'Línea de subsidio actualizada.');
            } else {
                const res = await api.registrarSubsidio({
                    usuario_solicitante_id: usuario.id,
                    comedor_id: Number(comedorSel),
                    anio: Number(anio),
                    mes: Number(mes),
                    ingrediente_id: Number(form.ingrediente_id),
                    cantidad_recibida: Number(form.cantidad_recibida),
                    unidad_medida_id: Number(form.unidad_medida_id),
                    observacion: form.observacion || null,
                });
                setExito(res.message || 'Subsidio registrado.');
            }
            setMostrarForm(false);
            setForm(FORM_VACIO);
            cargarLineas();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    };

    const confirmarBorrado = async () => {
        const id = confBorrado;
        setConfBorrado(null);
        setError('');
        try {
            const res = await api.eliminarSubsidio(id, usuario.id);
            setExito(res.message || 'Línea de subsidio eliminada.');
            cargarLineas();
        } catch (err) {
            setError(err.message);
        }
    };

    const inputCls = "w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500";
    const labelCls = "text-xs font-semibold text-slate-600 block mb-1";

    return (
        <div className="animate-in fade-in duration-300 space-y-5">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Package className="text-emerald-600" size={22} /> Subsidio de Víveres
                    </h2>
                    <p className="text-sm text-slate-500">
                        Víveres recibidos del municipio por mes calendario. Se descuentan del
                        costo real de las recetas al planificar (COM-59A).
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    {/* Selector de comedor solo para Admin de Sistemas */}
                    {!seleccion?.comedor_id && (
                        <select value={comedorSel} onChange={(e) => setComedorSel(e.target.value)}
                            className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500">
                            <option value="">Seleccionar comedor...</option>
                            {comedoresLista.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                        </select>
                    )}
                    <select value={mes} onChange={(e) => setMes(Number(e.target.value))}
                        className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500">
                        {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                    </select>
                    <input type="number" value={anio} min="2020" max="2100"
                        onChange={(e) => setAnio(Number(e.target.value))}
                        className="w-24 px-3 py-1.5 border border-slate-300 rounded-lg text-xs outline-none focus:ring-2 focus:ring-emerald-500" />
                    <button onClick={cargarLineas} className="p-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-600" title="Recargar">
                        <RefreshCw size={14} className={cargando ? 'animate-spin' : ''} />
                    </button>
                    {puedeGestionar && comedorSel && (
                        <button onClick={abrirAlta}
                            className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium transition-colors">
                            <Plus size={14} /> Registrar víver
                        </button>
                    )}
                </div>
            </div>

            {!puedeGestionar && (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-xs flex items-center gap-2">
                    <AlertCircle size={14} /> Modo solo lectura: la configuración del subsidio corresponde al
                    Admin de Sistemas o a la directiva del comedor.
                </div>
            )}
            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Tabla del mes */}
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                {cargando ? (
                    <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></div>
                ) : !comedorSel ? (
                    <p className="p-8 text-center text-sm text-slate-400">Seleccione un comedor para ver su subsidio.</p>
                ) : lineas.length === 0 ? (
                    <p className="p-8 text-center text-sm text-slate-400">
                        Sin víveres registrados para {MESES[mes - 1]} {anio}.
                        {puedeGestionar && ' Use "Registrar víver" para cargar el subsidio del mes.'}
                    </p>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                            <thead>
                                <tr className="bg-slate-100 text-slate-600">
                                    <th className="p-3 font-semibold">Ingrediente</th>
                                    <th className="p-3 font-semibold text-right">Cantidad recibida</th>
                                    <th className="p-3 font-semibold text-right">Equivalencia</th>
                                    <th className="p-3 font-semibold">Observación</th>
                                    {puedeGestionar && <th className="p-3 font-semibold text-right">Acciones</th>}
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-200">
                                {lineas.map(l => (
                                    <tr key={l.id} className="hover:bg-slate-50">
                                        <td className="p-3 font-medium text-slate-800">{l.ingrediente_nombre}</td>
                                        <td className="p-3 text-right text-slate-700">
                                            {Number(l.cantidad_recibida).toLocaleString('es-PE')} {l.unidad_abrev}
                                        </td>
                                        <td className="p-3 text-right text-slate-600 flex items-center justify-end gap-1">
                                            <Scale size={12} className="text-slate-400" />
                                            {Number(l.gramos_equivalentes || 0).toLocaleString('es-PE')} g
                                        </td>
                                        <td className="p-3 text-slate-500 text-xs">{l.observacion || '—'}</td>
                                        {puedeGestionar && (
                                            <td className="p-3">
                                                <div className="flex justify-end gap-1">
                                                    <button onClick={() => abrirEdicion(l)} title="Editar"
                                                        className="p-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-700 transition-colors">
                                                        <Edit3 size={14} />
                                                    </button>
                                                    <button onClick={() => setConfBorrado(l.id)} title="Eliminar"
                                                        className="p-1.5 bg-red-50 hover:bg-red-100 rounded-lg text-red-600 transition-colors">
                                                        <Trash2 size={14} />
                                                    </button>
                                                </div>
                                            </td>
                                        )}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Formulario alta/edición */}
            {mostrarForm && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
                        <div className="bg-emerald-700 text-white p-4">
                            <p className="font-bold text-sm">
                                {form.subsidio_id ? 'Editar línea de subsidio' : `Registrar víver · ${MESES[mes - 1]} ${anio}`}
                            </p>
                        </div>
                        <form onSubmit={guardar} className="p-4 space-y-3">
                            <div>
                                <label className={labelCls}>Ingrediente *</label>
                                <select value={form.ingrediente_id} disabled={!!form.subsidio_id}
                                    onChange={(e) => setForm({ ...form, ingrediente_id: e.target.value })}
                                    className={`${inputCls} disabled:bg-slate-100`} required>
                                    <option value="">Seleccionar...</option>
                                    {ingredientes.map(i => <option key={i.id} value={i.id}>{i.nombre}</option>)}
                                </select>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className={labelCls}>Cantidad recibida *</label>
                                    <input type="number" min="0" step="0.01" value={form.cantidad_recibida}
                                        onChange={(e) => setForm({ ...form, cantidad_recibida: e.target.value })}
                                        className={inputCls} required placeholder="Ej: 300" />
                                </div>
                                <div>
                                    <label className={labelCls}>Unidad de entrega *</label>
                                    <select value={form.unidad_medida_id}
                                        onChange={(e) => setForm({ ...form, unidad_medida_id: e.target.value })}
                                        className={inputCls} required>
                                        <option value="">Seleccionar...</option>
                                        {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className={labelCls}>Observación</label>
                                <input type="text" value={form.observacion}
                                    onChange={(e) => setForm({ ...form, observacion: e.target.value })}
                                    className={inputCls} placeholder="Ej: 6 sacos de 50 kg de la municipalidad" />
                            </div>
                            <div className="flex gap-2 pt-1">
                                <button type="button" onClick={() => { setMostrarForm(false); setForm(FORM_VACIO); }}
                                    className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors">
                                    Cancelar
                                </button>
                                <button type="submit" disabled={guardando}
                                    className="flex-1 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                    {guardando ? 'Guardando...' : 'Guardar'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            <ModalConfirmacion
                isOpen={!!confBorrado}
                onClose={() => setConfBorrado(null)}
                onConfirm={confirmarBorrado}
                mensaje="¿Eliminar esta línea del subsidio del mes? El costo de las recetas volverá a considerar ese ingrediente como comprado."
                tipo="danger"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};