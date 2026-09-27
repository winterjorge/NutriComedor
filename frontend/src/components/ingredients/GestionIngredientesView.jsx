/**
 * components/ingredients/GestionIngredientesView.jsx
 * Objetivo: COM-37 v5: pestaña "Gestión de Ingredientes" (exclusiva Admin de Sistemas,
 *           módulo 'gestion_ingredientes') sobre el modelo de DOS CONCEPTOS:
 *             - INGREDIENTE (unidad de USO: pizca, cucharadita, taza, und...).
 *             - INSUMO (unidad de COMPRA: Kg, L, atado, und...; origen SCRAPER|MANUAL).
 *           DOS SECCIONES en la misma vista, más el catálogo de ingredientes:
 *             A) Catálogo de ingredientes: tabla con indicadores de emparejamiento,
 *                crear y editar/renombrar SIN borrado (advertencia de inconsistencias).
 *             B) Emparejamiento ingrediente<->insumo: insumos vinculados con precio de
 *                hoy y fuente; búsqueda de insumos del scraper para vincular (con
 *                equivalencias opcionales); creación de insumo MANUAL con unidad de
 *                compra + precio con vigencia + equivalencias; edición/desvinculación.
 *             C) Equivalencias unidad de USO -> gramos por insumo (CRUD + desactivar).
 *             D) Precios manuales POR INSUMO (períodos con vigencia opcional, solapes
 *                validados en backend, desactivación lógica).
 *           El botón "Re-emparejar insumos" relanza el reconocimiento (heuristics) sobre
 *           insumos huérfanos para alimentar el algoritmo tras crear/renombrar.
 * Uso: Montada por App.jsx en la pestaña "Gestión de Ingredientes".
 * Referencia: ticket COM-37 v5 (solo trazabilidad).
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
    Plus, Edit3, Database, RefreshCw, Loader2, AlertCircle, Coins, Power,
    Sprout, Search, Link2, Package, Scale
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

    // ===== Sección A: catálogo =====
    const [ingredientes, setIngredientes] = useState([]);
    const [unidades, setUnidades] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');
    const [reemparejando, setReemparejando] = useState(false);

    // Modal crear/editar ingrediente
    const [modalIng, setModalIng] = useState(null);
    const [formIng, setFormIng] = useState({ nombre: '', categoria_id: '', unidad_medida_id: '', peso_estimado_g: 100 });
    const [guardandoIng, setGuardandoIng] = useState(false);
    const [confEdicion, setConfEdicion] = useState(null);

    // ===== Ingrediente seleccionado para secciones B/C/D =====
    const [ingSel, setIngSel] = useState(null);

    // ===== Sección B: insumos del ingrediente =====
    const [insumos, setInsumos] = useState([]);
    const [cargandoInsumos, setCargandoInsumos] = useState(false);
    const [modalBuscarInsumo, setModalBuscarInsumo] = useState(false);
    const [qInsumo, setQInsumo] = useState('');
    const [resultadosInsumo, setResultadosInsumo] = useState([]);
    const [buscandoInsumo, setBuscandoInsumo] = useState(false);
    const [modalInsumoManual, setModalInsumoManual] = useState(false);
    const [formInsumoManual, setFormInsumoManual] = useState({
        nombre: '', unidad_medida_id: '', precio_por_unidad: '', usar_rango: false,
        fecha_inicio: '', fecha_fin: '', observacion: '', equivalencias: [],
    });
    const [guardandoInsumo, setGuardandoInsumo] = useState(false);

    // ===== Sección C: equivalencias =====
    const [equivalencias, setEquivalencias] = useState([]);
    const [cargandoEq, setCargandoEq] = useState(false);
    const [formEq, setFormEq] = useState({ insumo_id: '', unidad_uso_id: '', gramos_por_unidad_uso: '', observacion: '' });
    const [eqEditId, setEqEditId] = useState(null);
    const [guardandoEq, setGuardandoEq] = useState(false);

    // ===== Sección D: precios manuales por insumo =====
    const [insumoPreciosSel, setInsumoPreciosSel] = useState('');
    const [periodos, setPeriodos] = useState([]);
    const [cargandoPer, setCargandoPer] = useState(false);
    const [formPer, setFormPer] = useState(FORM_PER_VACIO);
    const [perEditId, setPerEditId] = useState(null);
    const [guardandoPer, setGuardandoPer] = useState(false);
    const [errorSeccion, setErrorSeccion] = useState('');

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

    const categorias = useMemo(() => {
        const map = new Map();
        ingredientes.forEach(i => {
            if (i.categoria_id) map.set(i.categoria_id, i.categoria_nombre || `Categoría ${i.categoria_id}`);
        });
        return [...map.entries()].map(([id, nombre]) => ({ id, nombre })).sort((a, b) => a.nombre.localeCompare(b.nombre));
    }, [ingredientes]);

    const cargarInsumos = useCallback(async (ing) => {
        setCargandoInsumos(true);
        setErrorSeccion('');
        try {
            setInsumos(await api.getInsumosDelIngrediente(ing.id, usuario.id));
        } catch (e) {
            setErrorSeccion(e.message);
        } finally {
            setCargandoInsumos(false);
        }
    }, [usuario.id]);

    const cargarEquivalencias = useCallback(async (ing) => {
        setCargandoEq(true);
        try {
            setEquivalencias(await api.getEquivalencias(ing.id, usuario.id));
        } catch (e) {
            setErrorSeccion(e.message);
        } finally {
            setCargandoEq(false);
        }
    }, [usuario.id]);

    const cargarPeriodos = useCallback(async (insumoId) => {
        if (!insumoId) { setPeriodos([]); return; }
        setCargandoPer(true);
        try {
            setPeriodos(await api.getPreciosManualesInsumo(insumoId, usuario.id));
        } catch (e) {
            setErrorSeccion(e.message);
        } finally {
            setCargandoPer(false);
        }
    }, [usuario.id]);

    const seleccionarIngrediente = (ing) => {
        setIngSel(ing);
        setInsumoPreciosSel('');
        setPeriodos([]);
        setFormEq({ insumo_id: '', unidad_uso_id: '', gramos_por_unidad_uso: '', observacion: '' });
        setEqEditId(null);
        setFormPer(FORM_PER_VACIO);
        setPerEditId(null);
        cargarInsumos(ing);
        cargarEquivalencias(ing);
    };

    // ---------- Sección A: crear/editar ingrediente ----------
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
            setError('Nombre y unidad de uso son obligatorios.');
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
            setConfEdicion(payload); // advertencia de inconsistencias antes de confirmar
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
            if (ingSel && ingSel.id === modalIng.ing.id) seleccionarIngrediente({ ...ingSel, ...payload });
        } catch (e) {
            setError(e.message);
        } finally {
            setGuardandoIng(false);
        }
    };

    // ---------- Sección B: buscar y vincular insumos ----------
    const buscarInsumos = async () => {
        setBuscandoInsumo(true);
        setErrorSeccion('');
        try {
            setResultadosInsumo(await api.buscarInsumosAdmin(qInsumo, false, usuario.id));
        } catch (e) {
            setErrorSeccion(e.message);
        } finally {
            setBuscandoInsumo(false);
        }
    };
    const vincular = async (ins) => {
        setErrorSeccion('');
        try {
            const res = await api.vincularInsumo(ingSel.id, {
                usuario_solicitante_id: usuario.id,
                insumo_id: ins.id,
                reasignar: ins.ingrediente_id !== null && ins.ingrediente_id !== ingSel.id,
                equivalencias: [],
            });
            setExito(res.message || 'Insumo vinculado.');
            setModalBuscarInsumo(false);
            setQInsumo('');
            setResultadosInsumo([]);
            cargarInsumos(ingSel);
            cargar();
        } catch (e) {
            setErrorSeccion(e.message);
        }
    };
    const agregarFilaEq = () => setFormInsumoManual(f => ({
        ...f,
        equivalencias: [...f.equivalencias, { unidad_uso_id: '', gramos_por_unidad_uso: '' }],
    }));
    const submitInsumoManual = async (e) => {
        e.preventDefault();
        setGuardandoInsumo(true);
        setErrorSeccion('');
        try {
            const res = await api.crearInsumoManual(ingSel.id, {
                usuario_solicitante_id: usuario.id,
                nombre: formInsumoManual.nombre.trim(),
                unidad_medida_id: Number(formInsumoManual.unidad_medida_id),
                precio_por_unidad: Number(formInsumoManual.precio_por_unidad),
                usar_rango: formInsumoManual.usar_rango,
                fecha_inicio: formInsumoManual.usar_rango ? formInsumoManual.fecha_inicio : null,
                fecha_fin: formInsumoManual.usar_rango ? (formInsumoManual.fecha_fin || null) : null,
                observacion: formInsumoManual.observacion || null,
                equivalencias: formInsumoManual.equivalencias
                    .filter(eq => eq.unidad_uso_id && Number(eq.gramos_por_unidad_uso) > 0)
                    .map(eq => ({
                        unidad_uso_id: Number(eq.unidad_uso_id),
                        gramos_por_unidad_uso: Number(eq.gramos_por_unidad_uso),
                    })),
            });
            setExito(res.message || 'Insumo manual creado.');
            setModalInsumoManual(false);
            setFormInsumoManual({
                nombre: '', unidad_medida_id: '', precio_por_unidad: '', usar_rango: false,
                fecha_inicio: '', fecha_fin: '', observacion: '', equivalencias: [],
            });
            cargarInsumos(ingSel);
            cargarEquivalencias(ingSel);
            cargar();
        } catch (e2) {
            setErrorSeccion(e2.message);
        } finally {
            setGuardandoInsumo(false);
        }
    };
    const desvincular = async (ins) => {
        setErrorSeccion('');
        try {
            const res = await api.desvincularInsumo(ins.id, usuario.id);
            setExito(res.message || 'Insumo desvinculado.');
            cargarInsumos(ingSel);
            cargar();
        } catch (e) {
            setErrorSeccion(e.message);
        }
    };

    // ---------- Sección C: equivalencias ----------
    const submitEq = async (e) => {
        e.preventDefault();
        setGuardandoEq(true);
        setErrorSeccion('');
        try {
            if (eqEditId) {
                const res = await api.updateEquivalencia(eqEditId, {
                    usuario_solicitante_id: usuario.id,
                    gramos_por_unidad_uso: Number(formEq.gramos_por_unidad_uso),
                    observacion: formEq.observacion || null,
                });
                setExito(res.message || 'Equivalencia actualizada.');
            } else {
                const res = await api.createEquivalencia(ingSel.id, {
                    usuario_solicitante_id: usuario.id,
                    insumo_id: Number(formEq.insumo_id),
                    unidad_uso_id: Number(formEq.unidad_uso_id),
                    gramos_por_unidad_uso: Number(formEq.gramos_por_unidad_uso),
                    observacion: formEq.observacion || null,
                });
                setExito(res.message || 'Equivalencia registrada.');
            }
            setFormEq({ insumo_id: '', unidad_uso_id: '', gramos_por_unidad_uso: '', observacion: '' });
            setEqEditId(null);
            cargarEquivalencias(ingSel);
        } catch (e2) {
            setErrorSeccion(e2.message);
        } finally {
            setGuardandoEq(false);
        }
    };
    const desactivarEq = async (eq) => {
        setErrorSeccion('');
        try {
            const res = await api.desactivarEquivalencia(eq.id, usuario.id);
            setExito(res.message || 'Equivalencia desactivada.');
            cargarEquivalencias(ingSel);
        } catch (e) {
            setErrorSeccion(e.message);
        }
    };

    // ---------- Sección D: precios manuales por insumo ----------
    const submitPer = async (e) => {
        e.preventDefault();
        setGuardandoPer(true);
        setErrorSeccion('');
        try {
            const payload = {
                usuario_solicitante_id: usuario.id,
                precio_por_unidad: Number(formPer.precio_por_unidad),
                usar_rango: formPer.usar_rango,
                fecha_inicio: formPer.usar_rango ? formPer.fecha_inicio : null,
                fecha_fin: formPer.usar_rango ? (formPer.fecha_fin || null) : null,
                observacion: formPer.observacion || null,
            };
            if (perEditId) {
                const res = await api.updatePrecioManualInsumo(perEditId, payload);
                setExito(res.message || 'Período actualizado.');
            } else {
                const res = await api.createPrecioManualInsumo(Number(insumoPreciosSel), payload);
                setExito(res.message || 'Precio manual registrado.');
            }
            setFormPer(FORM_PER_VACIO);
            setPerEditId(null);
            cargarPeriodos(insumoPreciosSel);
            cargarInsumos(ingSel);
        } catch (e2) {
            setErrorSeccion(e2.message);
        } finally {
            setGuardandoPer(false);
        }
    };
    const desactivarPer = async (p) => {
        setErrorSeccion('');
        try {
            const res = await api.desactivarPrecioManualInsumo(p.id, usuario.id);
            setExito(res.message || 'Período desactivado.');
            cargarPeriodos(insumoPreciosSel);
            cargarInsumos(ingSel);
        } catch (e) {
            setErrorSeccion(e.message);
        }
    };

    // ---------- Re-emparejado ----------
    const reemparejar = async () => {
        setReemparejando(true);
        setError('');
        try {
            const res = await api.reemparejarInsumos(usuario.id);
            setExito(res.message || 'Re-emparejado completado.');
            cargar();
            if (ingSel) cargarInsumos(ingSel);
        } catch (e) {
            setError(e.message);
        } finally {
            setReemparejando(false);
        }
    };

    const inputCls = "w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500";
    const labelCls = "text-xs font-semibold text-slate-600 block mb-1";

    return (
        <div className="animate-in fade-in duration-300 space-y-6">
            {/* ===== Encabezado ===== */}
            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Sprout className="text-emerald-600" size={22} /> Gestión de Ingredientes
                    </h2>
                    <p className="text-sm text-slate-500">
                        Ingrediente (unidad de uso) ↔ Insumo (unidad de compra), equivalencias y
                        precios manuales con vigencia. Exclusivo Admin de Sistemas.
                    </p>
                </div>
                <div className="flex gap-2">
                    <button onClick={reemparejar} disabled={reemparejando}
                        className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                        {reemparejando ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                        Re-emparejar insumos
                    </button>
                    <button onClick={abrirCrear}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                        <Plus size={16} /> Nuevo ingrediente
                    </button>
                </div>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* ===== Sección A: catálogo de ingredientes ===== */}
            <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                    <thead>
                        <tr className="bg-slate-100 text-slate-600">
                            <th className="p-3 font-semibold">Ingrediente (uso)</th>
                            <th className="p-3 font-semibold">Categoría</th>
                            <th className="p-3 font-semibold">Unidad uso</th>
                            <th className="p-3 text-center">Insumos</th>
                            <th className="p-3 text-center">Manuales</th>
                            <th className="p-3 text-center">Con precio scraper</th>
                            <th className="p-3 text-center">Equivalencias</th>
                            <th className="p-3 text-right">Acciones</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                        {cargando ? (
                            <tr><td colSpan="8" className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={24} /></td></tr>
                        ) : ingredientes.length === 0 ? (
                            <tr><td colSpan="8" className="p-8 text-center text-slate-500">No hay ingredientes registrados.</td></tr>
                        ) : ingredientes.map(i => (
                            <tr key={i.id} className={`hover:bg-slate-50 cursor-pointer ${ingSel?.id === i.id ? 'bg-emerald-50' : ''} ${i.n_insumos_con_precio_scraper === 0 && i.n_insumos_manuales === 0 ? 'bg-amber-50/60' : ''}`}
                                onClick={() => seleccionarIngrediente(i)}>
                                <td className="p-3 font-medium text-slate-800">{i.nombre}</td>
                                <td className="p-3 text-slate-600">{i.categoria_nombre || '—'}</td>
                                <td className="p-3 text-slate-600">{i.unidad_nombre} ({i.unidad_abrev})</td>
                                <td className="p-3 text-center text-slate-600">{i.n_insumos}</td>
                                <td className="p-3 text-center text-slate-600">{i.n_insumos_manuales}</td>
                                <td className="p-3 text-center">
                                    {i.n_insumos_con_precio_scraper > 0 ? (
                                        <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded-full text-xs font-bold">{i.n_insumos_con_precio_scraper}</span>
                                    ) : (
                                        <span className="px-2 py-0.5 bg-amber-100 text-amber-700 rounded-full text-xs font-bold" title="Sin precios del scraper">0</span>
                                    )}
                                </td>
                                <td className="p-3 text-center text-slate-600">{i.n_equivalencias}</td>
                                <td className="p-3" onClick={(e) => e.stopPropagation()}>
                                    <div className="flex justify-end gap-2">
                                        <button onClick={() => seleccionarIngrediente(i)} title="Gestionar insumos, equivalencias y precios"
                                            className="p-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg transition-colors">
                                            <Package size={15} />
                                        </button>
                                        <button onClick={() => abrirEditar(i)} title="Editar / renombrar (advertencia de inconsistencias)"
                                            className="p-1.5 bg-slate-100 text-slate-700 hover:bg-slate-200 rounded-lg transition-colors">
                                            <Edit3 size={15} />
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* ===== Panel del ingrediente seleccionado: secciones B, C y D ===== */}
            {ingSel && (
                <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-6">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <h3 className="font-bold text-slate-800 flex items-center gap-2">
                            <Package className="text-blue-600" size={18} /> {ingSel.nombre}
                            <span className="text-xs font-normal text-slate-500">
                                (unidad de uso: {ingSel.unidad_nombre})
                            </span>
                        </h3>
                        <div className="flex gap-2">
                            <button onClick={() => { setModalBuscarInsumo(true); setResultadosInsumo([]); setQInsumo(''); }}
                                className="flex items-center gap-1 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors">
                                <Search size={13} /> Vincular insumo del scraper
                            </button>
                            <button onClick={() => setModalInsumoManual(true)}
                                className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-medium transition-colors">
                                <Plus size={13} /> Nuevo insumo manual
                            </button>
                            <button onClick={() => setIngSel(null)}
                                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg text-xs font-medium transition-colors">
                                Cerrar panel
                            </button>
                        </div>
                    </div>

                    {errorSeccion && (
                        <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-xs">
                            <AlertCircle size={14} /> {errorSeccion}
                        </div>
                    )}

                    {/* ----- Sección B: insumos vinculados ----- */}
                    <div>
                        <p className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1"><Link2 size={13} /> Insumos vinculados (compra)</p>
                        {cargandoInsumos ? (
                            <div className="p-6 text-center text-blue-600"><Loader2 className="animate-spin mx-auto" size={20} /></div>
                        ) : insumos.length === 0 ? (
                            <p className="text-xs text-slate-500">Sin insumos vinculados. Vincule uno del scraper o cree un insumo manual.</p>
                        ) : (
                            <div className="overflow-x-auto rounded-lg border border-slate-200">
                                <table className="w-full text-left border-collapse whitespace-nowrap text-xs">
                                    <thead>
                                        <tr className="bg-slate-100 text-slate-600">
                                            <th className="p-2 font-semibold">Insumo</th>
                                            <th className="p-2 font-semibold">Origen</th>
                                            <th className="p-2 font-semibold">Unidad compra</th>
                                            <th className="p-2 font-semibold">Último precio scraper</th>
                                            <th className="p-2 font-semibold">Precio hoy (por g)</th>
                                            <th className="p-2 font-semibold">Fuente</th>
                                            <th className="p-2 text-center">Períodos man.</th>
                                            <th className="p-2 text-center">Equiv.</th>
                                            <th className="p-2 text-right">Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-200">
                                        {insumos.map(ins => (
                                            <tr key={ins.id} className="hover:bg-slate-50">
                                                <td className="p-2 font-medium text-slate-800">{ins.nombre}</td>
                                                <td className="p-2">
                                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${ins.origen === 'MANUAL' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>
                                                        {ins.origen}
                                                    </span>
                                                </td>
                                                <td className="p-2 text-slate-600">{ins.unidad_nombre} ({ins.unidad_abrev})</td>
                                                <td className="p-2 text-slate-600">
                                                    {ins.ultimo_precio_scraper ? `S/ ${Number(ins.ultimo_precio_scraper).toFixed(2)} (${ins.fecha_ultimo_precio})` : '—'}
                                                </td>
                                                <td className="p-2 text-slate-600">{ins.precio_por_gramo_hoy ? ins.precio_por_gramo_hoy.toFixed(5) : '—'}</td>
                                                <td className="p-2 text-slate-600">{ins.fuente_precio_hoy || '—'}</td>
                                                <td className="p-2 text-center text-slate-600">{ins.n_precios_manuales}</td>
                                                <td className="p-2 text-center text-slate-600">{ins.n_equivalencias}</td>
                                                <td className="p-2">
                                                    <div className="flex justify-end gap-1">
                                                        <button onClick={() => { setInsumoPreciosSel(String(ins.id)); cargarPeriodos(ins.id); }}
                                                            title="Precios manuales del insumo"
                                                            className="p-1 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded transition-colors">
                                                            <Coins size={13} />
                                                        </button>
                                                        {ins.origen === 'MANUAL' && (
                                                            <button onClick={() => desvincular(ins)} title="Desvincular (queda huérfano)"
                                                                className="p-1 bg-red-50 text-red-600 hover:bg-red-100 rounded transition-colors">
                                                                <Power size={13} />
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>

                    {/* ----- Sección C: equivalencias ----- */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                        <div>
                            <p className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1"><Scale size={13} /> Equivalencias unidad de uso → gramos</p>
                            {cargandoEq ? (
                                <div className="p-6 text-center text-blue-600"><Loader2 className="animate-spin mx-auto" size={20} /></div>
                            ) : equivalencias.length === 0 ? (
                                <p className="text-xs text-slate-500">Sin equivalencias: se usará la conversión estándar de la unidad de uso.</p>
                            ) : (
                                <div className="space-y-1.5 max-h-56 overflow-y-auto">
                                    {equivalencias.map(eq => (
                                        <div key={eq.id} className={`border rounded-lg p-2 flex items-center gap-2 text-xs ${eq.estado_activo ? 'border-slate-200 bg-white' : 'border-slate-100 bg-slate-50 opacity-60'}`}>
                                            <div className="flex-1">
                                                <p className="font-bold text-slate-800">
                                                    {eq.insumo_nombre}: 1 {eq.unidad_uso_nombre} ({eq.unidad_uso_abrev}) = {eq.gramos_por_unidad_uso} g
                                                </p>
                                                {eq.observacion && <p className="text-[10px] text-slate-500">{eq.observacion}</p>}
                                            </div>
                                            {eq.estado_activo && (
                                                <div className="flex gap-1">
                                                    <button onClick={() => { setEqEditId(eq.id); setFormEq({ insumo_id: String(eq.insumo_id), unidad_uso_id: String(eq.unidad_uso_id), gramos_por_unidad_uso: String(eq.gramos_por_unidad_uso), observacion: eq.observacion || '' }); }}
                                                        className="p-1 bg-slate-100 hover:bg-slate-200 rounded transition-colors" title="Editar">
                                                        <Edit3 size={12} />
                                                    </button>
                                                    <button onClick={() => desactivarEq(eq)}
                                                        className="p-1 bg-red-50 text-red-600 hover:bg-red-100 rounded transition-colors" title="Desactivar">
                                                        <Power size={12} />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <form onSubmit={submitEq} className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2 h-fit">
                            <p className="text-xs font-bold text-slate-700">{eqEditId ? `Editando equivalencia #${eqEditId}` : 'Nueva equivalencia'}</p>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <label className={labelCls}>Insumo</label>
                                    <select value={formEq.insumo_id} disabled={!!eqEditId}
                                        onChange={(e) => setFormEq({ ...formEq, insumo_id: e.target.value })}
                                        className={`${inputCls} disabled:bg-slate-100`} required={!eqEditId}>
                                        <option value="">Seleccionar...</option>
                                        {insumos.map(ins => <option key={ins.id} value={ins.id}>{ins.nombre}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className={labelCls}>Unidad de uso</label>
                                    <select value={formEq.unidad_uso_id} disabled={!!eqEditId}
                                        onChange={(e) => setFormEq({ ...formEq, unidad_uso_id: e.target.value })}
                                        className={`${inputCls} disabled:bg-slate-100`} required={!eqEditId}>
                                        <option value="">Seleccionar...</option>
                                        {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className={labelCls}>Gramos por unidad de uso</label>
                                <input type="number" min="0.0001" step="0.0001" value={formEq.gramos_por_unidad_uso}
                                    onChange={(e) => setFormEq({ ...formEq, gramos_por_unidad_uso: e.target.value })}
                                    className={inputCls} required placeholder="Ej. 0.5 para pizca de sal" />
                            </div>
                            <div>
                                <label className={labelCls}>Observación</label>
                                <input type="text" value={formEq.observacion}
                                    onChange={(e) => setFormEq({ ...formEq, observacion: e.target.value })}
                                    className={inputCls} />
                            </div>
                            <div className="flex gap-2">
                                {eqEditId && (
                                    <button type="button" onClick={() => { setEqEditId(null); setFormEq({ insumo_id: '', unidad_uso_id: '', gramos_por_unidad_uso: '', observacion: '' }); }}
                                        className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors">
                                        Cancelar
                                    </button>
                                )}
                                <button type="submit" disabled={guardandoEq}
                                    className="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50">
                                    {guardandoEq ? 'Guardando...' : (eqEditId ? 'Actualizar' : 'Registrar equivalencia')}
                                </button>
                            </div>
                        </form>
                    </div>

                    {/* ----- Sección D: precios manuales por insumo ----- */}
                    <div>
                        <p className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1"><Coins size={13} /> Precios manuales por insumo (unidad de compra)</p>
                        <div className="flex gap-2 mb-3">
                            <select value={insumoPreciosSel} onChange={(e) => { setInsumoPreciosSel(e.target.value); setPerEditId(null); setFormPer(FORM_PER_VACIO); cargarPeriodos(e.target.value); }}
                                className={`${inputCls} max-w-xs`}>
                                <option value="">Seleccionar insumo...</option>
                                {insumos.map(ins => <option key={ins.id} value={ins.id}>{ins.nombre} ({ins.unidad_abrev})</option>)}
                            </select>
                        </div>
                        {insumoPreciosSel && (
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                <div className="space-y-1.5 max-h-56 overflow-y-auto">
                                    {cargandoPer ? (
                                        <div className="p-6 text-center text-blue-600"><Loader2 className="animate-spin mx-auto" size={20} /></div>
                                    ) : periodos.length === 0 ? (
                                        <p className="text-xs text-slate-500">Sin períodos manuales para este insumo.</p>
                                    ) : periodos.map(p => (
                                        <div key={p.id} className={`border rounded-lg p-2 flex items-center gap-2 text-xs ${p.estado_activo ? 'border-slate-200 bg-white' : 'border-slate-100 bg-slate-50 opacity-60'}`}>
                                            <div className="flex-1">
                                                <p className="font-bold text-slate-800">S/ {Number(p.precio_por_unidad).toFixed(2)} / {p.unidad_abrev}</p>
                                                <p className="text-[10px] text-slate-500">
                                                    {p.fecha_inicio ? `Vigencia ${p.fecha_inicio} → ${p.fecha_fin || 'abierto'}` : 'Vigencia permanente'}
                                                    {p.observacion ? ` · ${p.observacion}` : ''}
                                                </p>
                                            </div>
                                            {p.estado_activo && (
                                                <div className="flex gap-1">
                                                    <button onClick={() => { setPerEditId(p.id); setFormPer({ precio_por_unidad: String(p.precio_por_unidad), usar_rango: !!p.fecha_inicio, fecha_inicio: p.fecha_inicio || '', fecha_fin: p.fecha_fin || '', observacion: p.observacion || '' }); }}
                                                        className="p-1 bg-slate-100 hover:bg-slate-200 rounded transition-colors" title="Editar">
                                                        <Edit3 size={12} />
                                                    </button>
                                                    <button onClick={() => desactivarPer(p)}
                                                        className="p-1 bg-red-50 text-red-600 hover:bg-red-100 rounded transition-colors" title="Desactivar">
                                                        <Power size={12} />
                                                    </button>
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                                <form onSubmit={submitPer} className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2 h-fit">
                                    <p className="text-xs font-bold text-slate-700">{perEditId ? `Editando período #${perEditId}` : 'Nuevo período'}</p>
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <label className={labelCls}>Precio por unidad de compra</label>
                                            <input type="number" min="0.01" step="0.10" value={formPer.precio_por_unidad}
                                                onChange={(e) => setFormPer({ ...formPer, precio_por_unidad: e.target.value })}
                                                className={inputCls} required />
                                        </div>
                                        <div className="flex items-end pb-1">
                                            <label className="flex items-center gap-1.5 text-[11px] text-slate-700 cursor-pointer">
                                                <input type="checkbox" checked={formPer.usar_rango}
                                                    onChange={(e) => setFormPer({ ...formPer, usar_rango: e.target.checked })}
                                                    className="accent-blue-600" />
                                                Usar rango de vigencia
                                            </label>
                                        </div>
                                        <div>
                                            <label className={labelCls}>Inicio</label>
                                            <input type="date" value={formPer.fecha_inicio} disabled={!formPer.usar_rango}
                                                onChange={(e) => setFormPer({ ...formPer, fecha_inicio: e.target.value })}
                                                className={`${inputCls} disabled:bg-slate-100`} />
                                        </div>
                                        <div>
                                            <label className={labelCls}>Fin (opcional)</label>
                                            <input type="date" value={formPer.fecha_fin} disabled={!formPer.usar_rango}
                                                onChange={(e) => setFormPer({ ...formPer, fecha_fin: e.target.value })}
                                                className={`${inputCls} disabled:bg-slate-100`} />
                                        </div>
                                    </div>
                                    <div>
                                        <label className={labelCls}>Observación</label>
                                        <input type="text" value={formPer.observacion}
                                            onChange={(e) => setFormPer({ ...formPer, observacion: e.target.value })}
                                            className={inputCls} />
                                    </div>
                                    <div className="flex gap-2">
                                        {perEditId && (
                                            <button type="button" onClick={() => { setPerEditId(null); setFormPer(FORM_PER_VACIO); }}
                                                className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors">
                                                Cancelar
                                            </button>
                                        )}
                                        <button type="submit" disabled={guardandoPer}
                                            className="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50">
                                            {guardandoPer ? 'Guardando...' : (perEditId ? 'Actualizar' : 'Registrar período')}
                                        </button>
                                    </div>
                                </form>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ===== Modal crear/editar ingrediente ===== */}
            {modalIng && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
                        <div className="bg-emerald-700 text-white p-4">
                            <p className="font-bold text-sm">{modalIng.modo === 'crear' ? 'Nuevo ingrediente' : `Editar: ${modalIng.ing.nombre}`}</p>
                        </div>
                        <form onSubmit={submitIngrediente} className="p-4 space-y-3">
                            <div>
                                <label className={labelCls}>Nombre</label>
                                <input type="text" value={formIng.nombre}
                                    onChange={(e) => setFormIng({ ...formIng, nombre: e.target.value })}
                                    className={inputCls} required />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className={labelCls}>Categoría</label>
                                    <select value={formIng.categoria_id}
                                        onChange={(e) => setFormIng({ ...formIng, categoria_id: e.target.value })}
                                        className={inputCls}>
                                        <option value="">Sin categoría</option>
                                        {categorias.map(c => <option key={c.id} value={c.id}>{c.nombre}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className={labelCls}>Unidad de USO</label>
                                    <select value={formIng.unidad_medida_id}
                                        onChange={(e) => setFormIng({ ...formIng, unidad_medida_id: e.target.value })}
                                        className={inputCls} required>
                                        <option value="">Seleccionar...</option>
                                        {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label className={labelCls}>Peso estimado (g, para unidades discretas)</label>
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

            {/* ===== Modal buscar insumo del scraper ===== */}
            {modalBuscarInsumo && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col overflow-hidden">
                        <div className="bg-blue-700 text-white p-4 flex items-center gap-2">
                            <Search size={18} />
                            <p className="font-bold text-sm flex-1">Vincular insumo del scraper a {ingSel.nombre}</p>
                            <button onClick={() => setModalBuscarInsumo(false)} className="p-1 hover:bg-blue-800 rounded"><AlertCircle size={0} />✕</button>
                        </div>
                        <div className="p-4 space-y-3 overflow-y-auto">
                            <div className="flex gap-2">
                                <input type="text" value={qInsumo} onChange={(e) => setQInsumo(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); buscarInsumos(); } }}
                                    placeholder="Nombre del insumo (ej. sal, arroz...)" className={inputCls} />
                                <button onClick={buscarInsumos} disabled={buscandoInsumo}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                    {buscandoInsumo ? <Loader2 className="animate-spin" size={15} /> : 'Buscar'}
                                </button>
                            </div>
                            {resultadosInsumo.length > 0 && (
                                <div className="space-y-1.5">
                                    {resultadosInsumo.map(ins => (
                                        <div key={ins.id} className="border border-slate-200 rounded-lg p-2 flex items-center gap-2 text-xs">
                                            <div className="flex-1">
                                                <p className="font-bold text-slate-800">{ins.nombre}</p>
                                                <p className="text-[10px] text-slate-500">
                                                    {ins.origen} · {ins.unidad_nombre}
                                                    {ins.ingrediente_id ? ` · ya vinculado a: ${ins.ingrediente_actual}` : ' · sin vincular'}
                                                </p>
                                            </div>
                                            <button onClick={() => vincular(ins)}
                                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-[11px] font-bold transition-colors">
                                                Vincular
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                            <p className="text-[11px] text-slate-500">
                                Si ningún insumo del scraper satisface, ciérrelo y use "Nuevo insumo manual".
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* ===== Modal crear insumo manual ===== */}
            {modalInsumoManual && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-xl max-h-[88vh] flex flex-col overflow-hidden">
                        <div className="bg-purple-700 text-white p-4">
                            <p className="font-bold text-sm">Nuevo insumo manual para {ingSel.nombre}</p>
                            <p className="text-[11px] text-purple-100">Unidad de COMPRA + primer precio con vigencia + equivalencias opcionales.</p>
                        </div>
                        <form onSubmit={submitInsumoManual} className="p-4 space-y-3 overflow-y-auto">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className={labelCls}>Nombre del insumo</label>
                                    <input type="text" value={formInsumoManual.nombre}
                                        onChange={(e) => setFormInsumoManual({ ...formInsumoManual, nombre: e.target.value })}
                                        className={inputCls} required placeholder="Ej. Sal yodada mercado local" />
                                </div>
                                <div>
                                    <label className={labelCls}>Unidad de COMPRA</label>
                                    <select value={formInsumoManual.unidad_medida_id}
                                        onChange={(e) => setFormInsumoManual({ ...formInsumoManual, unidad_medida_id: e.target.value })}
                                        className={inputCls} required>
                                        <option value="">Seleccionar...</option>
                                        {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className={labelCls}>Precio por unidad de compra (S/)</label>
                                    <input type="number" min="0.01" step="0.10" value={formInsumoManual.precio_por_unidad}
                                        onChange={(e) => setFormInsumoManual({ ...formInsumoManual, precio_por_unidad: e.target.value })}
                                        className={inputCls} required />
                                </div>
                                <div className="flex items-end pb-1">
                                    <label className="flex items-center gap-1.5 text-[11px] text-slate-700 cursor-pointer">
                                        <input type="checkbox" checked={formInsumoManual.usar_rango}
                                            onChange={(e) => setFormInsumoManual({ ...formInsumoManual, usar_rango: e.target.checked })}
                                            className="accent-purple-600" />
                                        Usar rango de vigencia
                                    </label>
                                </div>
                                <div>
                                    <label className={labelCls}>Inicio</label>
                                    <input type="date" value={formInsumoManual.fecha_inicio} disabled={!formInsumoManual.usar_rango}
                                        onChange={(e) => setFormInsumoManual({ ...formInsumoManual, fecha_inicio: e.target.value })}
                                        className={`${inputCls} disabled:bg-slate-100`} />
                                </div>
                                <div>
                                    <label className={labelCls}>Fin (opcional)</label>
                                    <input type="date" value={formInsumoManual.fecha_fin} disabled={!formInsumoManual.usar_rango}
                                        onChange={(e) => setFormInsumoManual({ ...formInsumoManual, fecha_fin: e.target.value })}
                                        className={`${inputCls} disabled:bg-slate-100`} />
                                </div>
                            </div>
                            <div>
                                <label className={labelCls}>Observación</label>
                                <input type="text" value={formInsumoManual.observacion}
                                    onChange={(e) => setFormInsumoManual({ ...formInsumoManual, observacion: e.target.value })}
                                    className={inputCls} />
                            </div>

                            {/* Equivalencias opcionales */}
                            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2">
                                <div className="flex items-center justify-between">
                                    <p className="text-xs font-bold text-slate-700">Equivalencias unidad de uso → gramos (opcional)</p>
                                    <button type="button" onClick={agregarFilaEq}
                                        className="flex items-center gap-1 px-2 py-1 bg-slate-200 hover:bg-slate-300 rounded text-[11px] font-bold text-slate-700 transition-colors">
                                        <Plus size={11} /> Agregar
                                    </button>
                                </div>
                                {formInsumoManual.equivalencias.length === 0 ? (
                                    <p className="text-[11px] text-slate-500">Sin equivalencias: se usará la conversión estándar de cada unidad de uso.</p>
                                ) : formInsumoManual.equivalencias.map((eq, idx) => (
                                    <div key={idx} className="grid grid-cols-[1fr_1fr_auto] gap-2 items-end">
                                        <div>
                                            <label className={labelCls}>Unidad de uso</label>
                                            <select value={eq.unidad_uso_id}
                                                onChange={(e) => {
                                                    const eqs = [...formInsumoManual.equivalencias];
                                                    eqs[idx] = { ...eqs[idx], unidad_uso_id: e.target.value };
                                                    setFormInsumoManual({ ...formInsumoManual, equivalencias: eqs });
                                                }}
                                                className={inputCls}>
                                                <option value="">Seleccionar...</option>
                                                {unidades.map(u => <option key={u.id} value={u.id}>{u.nombre} ({u.abreviatura})</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className={labelCls}>Gramos</label>
                                            <input type="number" min="0.0001" step="0.0001" value={eq.gramos_por_unidad_uso}
                                                onChange={(e) => {
                                                    const eqs = [...formInsumoManual.equivalencias];
                                                    eqs[idx] = { ...eqs[idx], gramos_por_unidad_uso: e.target.value };
                                                    setFormInsumoManual({ ...formInsumoManual, equivalencias: eqs });
                                                }}
                                                className={inputCls} />
                                        </div>
                                        <button type="button"
                                            onClick={() => setFormInsumoManual({ ...formInsumoManual, equivalencias: formInsumoManual.equivalencias.filter((_, i) => i !== idx) })}
                                            className="p-2 bg-red-50 text-red-600 hover:bg-red-100 rounded-lg transition-colors" title="Quitar fila">
                                            <Power size={13} />
                                        </button>
                                    </div>
                                ))}
                            </div>

                            <div className="flex gap-2 pt-1">
                                <button type="button" onClick={() => setModalInsumoManual(false)}
                                    className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors">
                                    Cancelar
                                </button>
                                <button type="submit" disabled={guardandoInsumo}
                                    className="flex-1 px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                                    {guardandoInsumo ? 'Creando...' : 'Crear insumo manual'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Advertencia COM-37 ante edición de ingrediente */}
            <ModalConfirmacion
                isOpen={!!confEdicion}
                onClose={() => setConfEdicion(null)}
                onConfirm={confirmarEdicion}
                mensaje="ATENCIÓN: editar un ingrediente (nombre, categoría, unidad de uso o peso) puede generar inconsistencias en costos históricos, emparejamientos con insumos, equivalencias y modelos ya entrenados. ¿Confirma que desea continuar?"
                tipo="warning"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};