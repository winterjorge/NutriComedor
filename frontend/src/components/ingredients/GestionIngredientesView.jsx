/**
 * components/ingredients/GestionIngredientesView.jsx
 * Objetivo: COM-37: pestaña "Gestión de Ingredientes" (exclusiva del Administrador de
 *           Sistemas, módulo 'gestion_ingredientes'):
 *           - Tabla de ingredientes con estado de emparejamiento: insumos ligados,
 *             insumos con precio del scraper y períodos manuales activos (guía visual
 *             para cargar precios "en duro" donde SISAP no llega).
 *           - Crear y editar/renombrar ingredientes SIN borrado físico; toda edición
 *             abre un modal de ADVERTENCIA de inconsistencias históricas antes de
 *             confirmarse (decisión de ticket).
 *           - Panel de períodos de precio manual por ingrediente (unidad estándar),
 *             con toggle "Aplicar rango de vigencia" (si está apagado el precio rige
 *             siempre), validación de solapes (la responde el backend) y desactivación
 *             lógica de períodos.
 *           - Botón "Re-emparejar insumos" que relanza el algoritmo de reconocimiento
 *             (heuristics + nombres vigentes) sobre insumos huérfanos.
 * Uso: Montada por App.jsx en la pestaña "Gestión de Ingredientes".
 * Referencia: ticket COM-37 (solo trazabilidad).
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
    Plus, Edit3, Database, RefreshCw, Loader2, AlertCircle, Coins, Power, Sprout
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

const FORM_PER_VACIO = {
    precio_por_unidad: '',
    usar_rango: false,
    fecha_inicio: '',
    fecha_fin: '',
    observacion: '',
};

export const GestionIngredientesView = () => {
    const { usuario } = useAuth();

    // ===== Listado principal =====
    const [ingredientes, setIngredientes] = useState([]);
    const [unidades, setUnidades] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');
    const [reemparejando, setReemparejando] = useState(false);

    // ===== Modal crear/editar ingrediente =====
    const [modalIng, setModalIng] = useState(null);          // {modo:'crear'} | {modo:'editar', ing}
    const [formIng, setFormIng] = useState({ nombre: '', categoria_id: '', unidad_medida_id: '', peso_estimado_g: 100 });
    const [guardandoIng, setGuardandoIng] = useState(false);
    const [confEdicion, setConfEdicion] = useState(null);    // payload pendiente tras advertencia

    // ===== Modal períodos de precio manual =====
    const [modalPrecios, setModalPrecios] = useState(null);  // ingrediente seleccionado
    const [periodos, setPeriodos] = useState([]);
    const [cargandoPeriodos, setCargandoPeriodos] = useState(false);
    const [formPer, setFormPer] = useState(FORM_PER_VACIO);
    const [periodoEditId, setPeriodoEditId] = useState(null);
    const [guardandoPer, setGuardandoPer] = useState(false);
    const [errorPer, setErrorPer] = useState('');

    // ---------- Cargadores ----------
    const cargar = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const [ings, ums] = await Promise.all([
                api.getIngredientesAdmin(usuario.id),
                api.getUnidadesMedida(),
            ]);
            setIngredientes(ings);
            setUnidades(ums);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [usuario.id]);

    useEffect(() => { cargar(); }, [cargar]);

    // Categorías disponibles derivadas del catálogo en uso (sin endpoint nuevo)
    const categorias = useMemo(() => {
        const map = new Map();
        ingredientes.forEach(i => {
            if (i.categoria_id) map.set(i.categoria_id, i.categoria_nombre || `Categoría ${i.categoria_id}`);
        });
        return [...map.entries()].map(([id, nombre]) => ({ id, nombre })).sort((a, b) => a.nombre.localeCompare(b.nombre));
    }, [ingredientes]);

    // ---------- Crear / editar ingrediente ----------
    const abrirCrear = () => {
        setFormIng({ nombre: '', categoria_id: '', unidad_medida_id: '', peso_estimado_g: 100 });
        setModalIng({ modo: 'crear' });
    };

    const abrirEditar = (ing) => {
        setFormIng({
            nombre: ing.nombre,
            categoria_id: ing.categoria_id || '',
            unidad_medida_id: ing.unidad_medida_id,
            peso_estimado_g: ing.peso_estimado_g,
        });
        setModalIng({ modo: 'editar', ing });
    };

    const submitIngrediente = async (e) => {
        e.preventDefault();
        if (!formIng.nombre.trim() || !formIng.unidad_medida_id) {
            setError('Nombre y unidad de medida son obligatorios.');
            return;
        }
        const payload = {
            usuario_solicitante_id: usuario.id,
            nombre: formIng.nombre.trim(),
            categoria_id: formIng.categoria_id === '' ? null : Number(formIng.categoria_id),
            unidad_medida_id: Number(formIng.unidad_medida_id),
            peso_estimado_g: Number(formIng.peso_estimado_g) || 100,
        };
        if (modalIng.modo === 'crear') {
            setGuardandoIng(true);
            setError('');
            try {
                const res = await api.createIngredienteAdmin(payload);
                setExito(res.message || 'Ingrediente creado.');
                setModalIng(null);
                cargar();
            } catch (e2) {
                setError(e2.message);
            } finally {
                setGuardandoIng(false);
            }
        } else {
            // COM-37: toda edición pasa por advertencia de inconsistencias
            setConfEdicion(payload);
        }
    };

    const confirmarEdicion = async () => {
        const payload = confEdicion;
        setConfEdicion(null);
        setGuardandoIng(true);
        setError('');
        try {
            const res = await api.updateIngredienteAdmin(modalIng.ing.id, payload);
            setExito(res.message || 'Ingrediente actualizado.');
            setModalIng(null);
            cargar();
        } catch (e) {
            setError(e.message);
        } finally {
            setGuardandoIng(false);
        }
    };

    // ---------- Períodos de precio manual ----------
    const abrirPrecios = async (ing) => {
        setModalPrecios(ing);
        setFormPer(FORM_PER_VACIO);
        setPeriodoEditId(null);
        setErrorPer('');
        setCargandoPeriodos(true);
        try {
            setPeriodos(await api.getPreciosManuales(ing.id, usuario.id));
        } catch (e) {
            setErrorPer(e.message);
        } finally {
            setCargandoPeriodos(false);
        }
    };

    const editarPeriodo = (p) => {
        setPeriodoEditId(p.id);
        setFormPer({
            precio_por_unidad: String(p.precio_por_unidad),
            usar_rango: !!p.fecha_inicio,
            fecha_inicio: p.fecha_inicio || '',
            fecha_fin: p.fecha_fin || '',
            observacion: p.observacion || '',
        });
    };

    const submitPeriodo = async (e) => {
        e.preventDefault();
        setErrorPer('');
        const payload = {
            usuario_solicitante_id: usuario.id,
            precio_por_unidad: Number(formPer.precio_por_unidad),
            usar_rango: formPer.usar_rango,
            fecha_inicio: formPer.usar_rango ? formPer.fecha_inicio : null,
            fecha_fin: formPer.usar_rango ? (formPer.fecha_fin || null) : null,
            observacion: formPer.observacion || null,
        };
        setGuardandoPer(true);
        try {
            if (periodoEditId) {
                const res = await api.updatePrecioManual(periodoEditId, payload);
                setExito(res.message || 'Período actualizado.');
            } else {
                const res = await api.createPrecioManual(modalPrecios.id, payload);
                setExito(res.message || 'Precio manual registrado.');
            }
            setFormPer(FORM_PER_VACIO);
            setPeriodoEditId(null);
            setPeriodos(await api.getPreciosManuales(modalPrecios.id, usuario.id));
            cargar();
        } catch (e) {
            setErrorPer(e.message);   // incluye mensajes de solape del backend
        } finally {
            setGuardandoPer(false);
        }
    };

    const desactivarPeriodo = async (p) => {
        setErrorPer('');
        try {
            const res = await api.desactivarPrecioManual(p.id, usuario.id);
            setExito(res.message || 'Período desactivado.');
            setPeriodos(await api.getPreciosManuales(modalPrecios.id, usuario.id));
            cargar();
        } catch (e) {
            setErrorPer(e.message);
        }
    };

    // ---------- Re-emparejado de insumos huérfanos ----------
    const reemparejar = async () => {
        setReemparejando(true);
        setError('');
        try {
            const res = await api.reemparejarInsumos(usuario.id);
            setExito(res.message || 'Re-emparejado completado.');
            cargar();
        } catch (e) {
            setError(e.message);
        } finally {
            setReemparejando(false);
        }
    };

    const inputCls = "w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500";

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Sprout className="text-emerald-600" size={22} /> Gestión de Ingredientes
                    </h2>
                    <p className="text-sm text-slate-500">
                        Catálogo de ingredientes, precios promedio manuales con vigencia y
                        re-emparejado del reconocimiento insumo→ingrediente. Exclusivo Admin de Sistemas.
                    </p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={reemparejar}
                        disabled={reemparejando}
                        className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        {reemparejando ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                        Re-emparejar insumos
                    </button>
                    <button
                        onClick={abrirCrear}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
                    >
                        <Plus size={16} /> Nuevo ingrediente
                    </button>
                </div>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Tabla de ingredientes */}
            <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                    <thead>
                        <tr className="bg-slate-100 text-slate-600">
                            <th className="p-3 font-semibold">Ingrediente</th>
                            <th className="p-3 font-semibold">Categoría</th>
                            <th className="p-3 font-semibold">Unidad</th>
                            <th className="p-3 font-semibold text-right">Peso est. (g)</th>
                            <th className="p-3 font-semibold text-center">Insumos</th>
                            <th className="p-3 font-semibold text-center">Con precio scraper</th>
                            <th className="p-3 font-semibold text-center">Precios manuales</th>
                            <th className="p-3 font-semibold text-right">Acciones</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {cargando ? (
                            <tr><td colSpan="8" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                        ) : ingredientes.length === 0 ? (
                            <tr><td colSpan="8" className="p-8 text-center text-slate-500">No hay ingredientes registrados.</td></tr>
                        ) : ingredientes.map(i => (
                            <tr key={i.id} className={`hover:bg-slate-50 ${i.n_insumos_con_precio === 0 ? 'bg-amber-50/60' : ''}`}>
                                <td className="p-3 font-medium text-slate-800">{i.nombre}</td>
                                <td className="p-3 text-slate-600">{i.categoria_nombre || '—'}</td>
                                <td className="p-3 text-slate-600">{i.unidad_nombre} ({i.unidad_abrev})</td>
                                <td className="p-3 text-right text-slate-600">{i.peso_estimado_g}</td>
                                <td className="p-3 text-center text-slate-600">{i.n_insumos}</td>
                                <td className="p-3 text-center">
                                    {i.n_insumos_con_precio > 0 ? (
                                        <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full text-xs font-bold">{i.n_insumos_con_precio}</span>
                                    ) : (
                                        <span className="px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full text-xs font-bold" title="Sin precios del scraper: requiere precio manual">0</span>
                                    )}
                                </td>
                                <td className="p-3 text-center">
                                    {i.n_precios_manuales > 0 ? (
                                        <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-bold">{i.n_precios_manuales}</span>
                                    ) : (
                                        <span className="text-slate-400 text-xs">—</span>
                                    )}
                                </td>
                                <td className="p-3">
                                    <div className="flex justify-end gap-2">
                                        <button
                                            onClick={() => abrirPrecios(i)}
                                            title="Precios manuales con vigencia"
                                            className="p-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg transition-colors"
                                        >
                                            <Coins size={15} />
                                        </button>
                                        <button
                                            onClick={() => abrirEditar(i)}
                                            title="Editar / renombrar (advertencia de inconsistencias)"
                                            className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors"
                                        >
                                            <Edit3 size={15} />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* ===== Modal crear/editar ingrediente ===== */}
            {modalIng && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
                        <div className="bg-emerald-700 text-white p-4">
                            <p className="font-bold text-sm">
                                {modalIng.modo === 'crear' ? 'Nuevo ingrediente' : `Editar: ${modalIng.ing.nombre}`}
                            </p>
                        </div>
                        <form onSubmit={submitIngrediente} className="p-4 space-y-3">
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">Nombre</label>
                                <input type="text" value={formIng.nombre}
                                    onChange={(e) => setFormIng({ ...formIng, nombre: e.target.value })}
                                    className={inputCls} required />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs font-semibold text-slate-600 block mb-1">Categoría</label>
                                    <select value={formIng.categoria_id}
                                        onChange={(e) => setFormIng({ ...formIng, categoria_id: e.target.value })}
                                        className={inputCls}>
                                        <option value="">Sin categoría</option>
                                        {categorias.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className="text-xs font-semibold text-slate-600 block mb-1">Unidad estándar</label>
                                    <select value={formIng.unidad_medida_id}
                                        onChange={(e) => setFormIng({ ...formIng, unidad_medida_id: e.target.value })}
                                        className={inputCls} required>
                                        <option value="">Seleccionar...</option>
                                        {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className="text-xs font-semibold text-slate-600 block mb-1">Peso estimado (g, para unidades discretas)</label>
                                <input type="number" min="1" step="1" value={formIng.peso_estimado_g}
                                    onChange={(e) => setFormIng({ ...formIng, peso_estimado_g: e.target.value })}
                                    className={inputCls} required />
                            </div>
                            <div className="flex gap-2 pt-1">
                                <button type="button" onClick={() => setModalIng(null)}
                                    className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors">
                                    Cancelar
                                </button>
                                <button type="submit" disabled={guardandoIng}
                                    className="flex-1 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                    {guardandoIng ? 'Guardando...' : 'Guardar'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ===== Modal períodos de precio manual ===== */}
            {modalPrecios && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden">
                        <div className="bg-blue-700 text-white p-4 flex items-center gap-2">
                            <Database size={18} />
                            <div className="flex-1">
                                <p className="font-bold text-sm">Precios manuales: {modalPrecios.nombre}</p>
                                <p className="text-[11px] text-blue-100">
                                    Unidad estándar: {modalPrecios.unidad_nombre} ({modalPrecios.unidad_abrev}) ·
                                    se usan solo cuando el scraper/RF no predicen.
                                </p>
                            </div>
                            <button onClick={() => setModalPrecios(null)} className="p-1 hover:bg-blue-800 rounded transition-colors">
                                <AlertCircle size={0} />✕
                            </button>
                        </div>

                        <div className="p-4 overflow-y-auto space-y-4">
                            {errorPer && (
                                <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-xs">
                                    <AlertCircle size={14} /> {errorPer}
                                </div>
                            )}

                            {/* Listado de períodos */}
                            {cargandoPeriodos ? (
                                <div className="p-6 text-center text-blue-600"><Loader2 className="animate-spin mx-auto" size={22} /></div>
                            ) : periodos.length === 0 ? (
                                <p className="text-xs text-slate-500 text-center p-4">Sin períodos registrados.</p>
                            ) : (
                                <div className="space-y-2">
                                    {periodos.map(p => (
                                        <div key={p.id} className={`border rounded-xl p-3 flex flex-wrap items-center gap-3 ${
                                            p.estado_activo ? 'border-slate-200 bg-white' : 'border-slate-100 bg-slate-50 opacity-60'}`}>
                                            <div className="flex-1 min-w-[180px]">
                                                <p className="text-sm font-bold text-slate-800">
                                                    S/ {Number(p.precio_por_unidad).toFixed(2)} / {p.unidad_abrev}
                                                </p>
                                                <p className="text-[11px] text-slate-500">
                                                    {p.fecha_inicio
                                                        ? `Vigencia: ${p.fecha_inicio} → ${p.fecha_fin || 'abierto'}`
                                                        : 'Vigencia permanente (sin rango)'}
                                                    {p.observacion ? ` · ${p.observacion}` : ''}
                                                </p>
                                            </div>
                                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                                p.estado_activo ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-500'}`}>
                                                {p.estado_activo ? 'ACTIVO' : 'INACTIVO'}
                                            </span>
                                            {p.estado_activo && (
                                                <div className="flex gap-2">
                                                    <button onClick={() => editarPeriodo(p)}
                                                        className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors" title="Editar período">
                                                        <Edit3 size={14} />
                                                    </button>
                                                    <button onClick={() => desactivarPeriodo(p)}
                                                        className="p-1.5 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors" title="Desactivar período">
                                                        <Power size={14} />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {/* Formulario crear/editar período */}
                            <form onSubmit={submitPeriodo} className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                                <p className="text-xs font-bold text-slate-700">
                                    {periodoEditId ? `Editando período #${periodoEditId}` : 'Nuevo período de precio manual'}
                                </p>
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="text-xs font-semibold text-slate-600 block mb-1">
                                            Precio por {modalPrecios.unidad_abrev} (S/)
                                        </label>
                                        <input type="number" min="0.01" step="0.10" value={formPer.precio_por_unidad}
                                            onChange={(e) => setFormPer({ ...formPer, precio_por_unidad: e.target.value })}
                                            className={inputCls} required />
                                    </div>
                                    <div className="flex items-end pb-1">
                                        <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
                                            <input type="checkbox" checked={formPer.usar_rango}
                                                onChange={(e) => setFormPer({ ...formPer, usar_rango: e.target.checked })}
                                                className="accent-blue-600" />
                                            Aplicar rango de vigencia
                                        </label>
                                    </div>
                                    <div>
                                        <label className="text-xs font-semibold text-slate-600 block mb-1">Fecha inicio</label>
                                        <input type="date" value={formPer.fecha_inicio} disabled={!formPer.usar_rango}
                                            onChange={(e) => setFormPer({ ...formPer, fecha_inicio: e.target.value })}
                                            className={`${inputCls} disabled:bg-slate-100`} />
                                    </div>
                                    <div>
                                        <label className="text-xs font-semibold text-slate-600 block mb-1">Fecha fin (opcional)</label>
                                        <input type="date" value={formPer.fecha_fin} disabled={!formPer.usar_rango}
                                            onChange={(e) => setFormPer({ ...formPer, fecha_fin: e.target.value })}
                                            className={`${inputCls} disabled:bg-slate-100`} />
                                    </div>
                                </div>
                                <div>
                                    <label className="text-xs font-semibold text-slate-600 block mb-1">Observación</label>
                                    <input type="text" value={formPer.observacion}
                                        onChange={(e) => setFormPer({ ...formPer, observacion: e.target.value })}
                                        placeholder="Ej. precio referencial mercado mayorista"
                                        className={inputCls} />
                                </div>
                                <div className="flex gap-2">
                                    {periodoEditId && (
                                        <button type="button"
                                            onClick={() => { setPeriodoEditId(null); setFormPer(FORM_PER_VACIO); }}
                                            className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors">
                                            Cancelar edición
                                        </button>
                                    )}
                                    <button type="submit" disabled={guardandoPer}
                                        className="flex-1 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                        {guardandoPer ? 'Guardando...' : (periodoEditId ? 'Actualizar período' : 'Registrar período')}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            )}

            {/* Advertencia COM-37 ante edición de ingrediente */}
            <ModalConfirmacion
                isOpen={!!confEdicion}
                onClose={() => setConfEdicion(null)}
                onConfirm={confirmarEdicion}
                mensaje="ATENCIÓN: editar un ingrediente (nombre, categoría, unidad o peso) puede generar inconsistencias en costos históricos, emparejamientos con insumos y modelos ya entrenados. ¿Confirma que desea continuar?"
                tipo="warning"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};