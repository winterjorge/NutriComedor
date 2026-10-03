/**
 * components/recipes/ModalNuevaReceta.jsx
 * Objetivo: Modal de creación y edición de recetas. Gestiona los datos nutricionales
 *           (6 valores POR RACIÓN), las raciones (COM-45) y la lista dinámica de
 *           ingredientes CON COMPONENTE (COM-48): Ensalada, Plato de fondo, Refresco,
 *           Fruta (catálogo extensible desde /recetas/componentes).
 * Historial:
 *  - COM-16: fix de scroll/recorte del modal (max-h-[90vh], cuerpo scrolleable, pie fijo).
 *  - COM-18: confirmación modal antes de Guardar/Cancelar/Eliminar y ModalExito.
 *  - COM-45: campo "Raciones *" obligatorio (entero > 0, default 4).
 *  - COM-48 (este archivo): esquema multi-componente:
 *      * Cada fila de ingrediente pertenece a un componente (selector implícito por
 *        sección: las filas se agrupan visualmente bajo su componente y se agregan con
 *        el botón de cada sección). El mismo ingrediente puede repetirse en componentes
 *        distintos con cantidades INDEPENDIENTES.
 *      * Catálogo de componentes cargado de api.getComponentesReceta() (extensible: si
 *        mañana existe 'Sopa', aparece solo).
 *      * Edición: sincronización mediante api.limpiarIngredientesReceta(recetaId) +
 *        re-grabado de todas las filas con su componente (el borrado por ingrediente
 *        del esquema anterior perdería filas duplicadas en varios componentes); el
 *        bucle anterior queda COMENTADO por trazabilidad.
 *      * Validación: componente obligatorio por fila (garantizado por la sección),
 *        ingrediente/cantidad/unidad obligatorios por fila, al menos 1 fila en total.
 * Uso: Importado por RecipesView.jsx. Props: isOpen, onClose, onSuccess, recetaEditar.
 */
import React, { useState, useEffect, useRef } from 'react';
import { X, Plus, Trash2 } from 'lucide-react';
import { api } from '../../services/api';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

export const ModalNuevaReceta = ({ isOpen, onClose, onSuccess, recetaEditar }) => {
    // Indica si el modal opera en modo edición (true) o creación (false)
    const esEdicion = !!recetaEditar;

    // Datos generales y nutricionales de la receta
    const [formData, setFormData] = useState({
        nombre: '',
        descripcion: '',
        raciones: '4',          // COM-45: default 4 raciones (entero > 0, obligatorio en UI)
        hierro_mg: '',
        proteina_g: '',
        energia_kcal: '',
        vitamina_a_ug: '',
        zinc_mg: '',
        carbohidratos_g: ''
    });
    // COM-48: filas de ingredientes, cada una con su componente_id y uid local
    const [ingredientes, setIngredientes] = useState([]);
    // COM-48: catálogo de componentes (Ensalada, Plato de fondo, Refresco, Fruta...)
    const [componentes, setComponentes] = useState([]);
    // Catálogos cargados desde la API para alimentar los selects
    const [unidadesMedida, setUnidadesMedida] = useState([]);
    const [ingredientesDisponibles, setIngredientesDisponibles] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    // UX (COM-18): modal de confirmación para acciones sensibles.
    // Estructura: { tipo: 'guardar' | 'cancelar' | 'eliminar', uid?: number }
    const [modalConf, setModalConf] = useState(null);
    // UX (COM-18): mensaje del modal de éxito (string vacío = cerrado)
    const [mensajeExito, setMensajeExito] = useState('');
    // Referencia al cuerpo scrolleable para subir el scroll al mostrar errores
    const cuerpoRef = useRef(null);
    // COM-48: contador de uids locales para las filas de ingredientes
    const uidRef = useRef(1);
    const nuevoUid = () => uidRef.current++;

    // COM-48: fila vacía de un componente dado
    const filaVacia = (componenteId) => ({
        uid: nuevoUid(),
        componente_id: componenteId,
        ingrediente_id: '',
        cantidad_requerida: '',
        unidad_medida_id: ''
    });

    // Al abrir el modal: cargar catálogos y preparar modo edición o creación
    useEffect(() => {
        if (isOpen) {
            cargarDatosIniciales();
        }
    }, [isOpen, recetaEditar]);

    // Carga unidades, ingredientes disponibles y componentes; prepara filas iniciales
    const cargarDatosIniciales = async () => {
        try {
            const [unidades, ingredientesDisp, comps] = await Promise.all([
                api.getUnidadesMedida(),
                api.getIngredientesDisponibles(),
                api.getComponentesReceta()   // COM-48
            ]);
            setUnidadesMedida(unidades);
            setIngredientesDisponibles(ingredientesDisp);
            setComponentes(comps || []);
            if (esEdicion && recetaEditar) {
                await cargarRecetaParaEditar();
            } else {
                resetearFormulario(comps || []);
            }
        } catch (err) {
            console.error('Error cargando datos:', err);
            setError('Error al cargar datos iniciales');
        }
    };

    // Rellena el formulario con los datos de la receta seleccionada para editar
    const cargarRecetaParaEditar = async () => {
        try {
            const data = await api.getRecetaDetalle(recetaEditar.id);
            setFormData({
                nombre: data.receta.nombre || '',
                descripcion: data.receta.descripcion || '',
                // COM-45: precarga raciones; si la receta antigua no tuviera valor, default 4
                raciones: data.receta.raciones != null ? String(data.receta.raciones) : '4',
                hierro_mg: data.receta.hierro_mg || '',
                proteina_g: data.receta.proteina_g || '',
                energia_kcal: data.receta.energia_kcal || '',
                vitamina_a_ug: data.receta.vitamina_a_ug || '',
                zinc_mg: data.receta.zinc_mg || '',
                carbohidratos_g: data.receta.carbohidratos_g || ''
            });
            // COM-48: cada línea trae componente_id/componente_nombre desde el backend
            if (data.ingredientes && data.ingredientes.length > 0) {
                setIngredientes(data.ingredientes.map(ing => ({
                    uid: nuevoUid(),
                    componente_id: ing.componente_id,
                    ingrediente_id: ing.ingrediente_id,
                    cantidad_requerida: ing.cantidad_requerida,
                    unidad_medida_id: ing.unidad_medida_id
                })));
            } else {
                // Receta sin líneas: una fila vacía en el primer componente (o Plato de fondo)
                const inicial = (componentes.find(c => c.nombre === 'Plato de fondo') || componentes[0]);
                setIngredientes(inicial ? [filaVacia(inicial.id)] : []);
            }
        } catch (err) {
            console.error('Error cargando receta:', err);
            setError('Error al cargar la receta para editar');
        }
    };

    // COM-48: restablece el formulario (modo creación) con 1 fila en Plato de fondo
    const resetearFormulario = (comps = componentes) => {
        setFormData({
            nombre: '',
            descripcion: '',
            raciones: '4',   // COM-45: default 4 raciones al crear
            hierro_mg: '',
            proteina_g: '',
            energia_kcal: '',
            vitamina_a_ug: '',
            zinc_mg: '',
            carbohidratos_g: ''
        });
        const inicial = (comps.find(c => c.nombre === 'Plato de fondo') || comps[0]);
        setIngredientes(inicial ? [filaVacia(inicial.id)] : []);
        setError('');
    };

    // Fija el error y sube el scroll del cuerpo para que el mensaje sea visible
    const mostrarError = (mensaje) => {
        setError(mensaje);
        if (cuerpoRef.current) {
            cuerpoRef.current.scrollTop = 0;
        }
    };

    // Actualiza un campo del formulario de datos generales
    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    // COM-48: actualiza un campo de una fila identificada por uid
    const handleIngredienteChange = (uid, field, value) => {
        setIngredientes(prev => prev.map(row => (row.uid === uid ? { ...row, [field]: value } : row)));
    };

    // COM-48: agrega una fila vacía al componente indicado
    const agregarIngrediente = (componenteId) => {
        setIngredientes(prev => [...prev, filaVacia(componenteId)]);
    };

    // COM-48: elimina una fila por uid (pide confirmación COM-18)
    const eliminarIngrediente = (uid) => {
        setIngredientes(prev => prev.filter(row => row.uid !== uid));
    };

    // Valida nombre, raciones (COM-45), y cada fila de ingrediente con su componente (COM-48)
    const validarFormulario = () => {
        if (!formData.nombre.trim()) {
            mostrarError('El nombre de la receta es obligatorio');
            return false;
        }
        // COM-45: raciones obligatorias en la interfaz: entero mayor a cero, no vacío
        const racionesNum = Number(formData.raciones);
        if (formData.raciones === '' || formData.raciones === null || formData.raciones === undefined
            || !Number.isInteger(racionesNum) || racionesNum <= 0) {
            mostrarError('La cantidad de raciones es obligatoria y debe ser un número entero mayor a 0');
            return false;
        }
        // COM-48: al menos una fila de ingrediente en toda la receta
        if (ingredientes.length === 0) {
            mostrarError('Agregue al menos un ingrediente a la receta');
            return false;
        }
        // COM-48: validación por componente y fila (el componente siempre viene de la sección)
        for (const comp of componentes) {
            const filas = ingredientes.filter(i => i.componente_id === comp.id);
            filas.forEach((ing, idx) => {
                // se recorre completo para reportar el primer error con contexto
            });
            for (let i = 0; i < filas.length; i++) {
                const ing = filas[i];
                const etiqueta = `${comp.nombre} · fila ${i + 1}`;
                if (!ing.componente_id) {
                    mostrarError(`El componente de ${etiqueta} es obligatorio`);
                    return false;
                }
                if (!ing.ingrediente_id) {
                    mostrarError(`El ingrediente de ${etiqueta} es obligatorio`);
                    return false;
                }
                if (!ing.cantidad_requerida || parseFloat(ing.cantidad_requerida) <= 0) {
                    mostrarError(`La cantidad de ${etiqueta} es obligatoria y debe ser mayor a 0`);
                    return false;
                }
                if (!ing.unidad_medida_id) {
                    mostrarError(`La unidad de medida de ${etiqueta} es obligatoria`);
                    return false;
                }
            }
        }
        return true;
    };

    // ===== UX (COM-18): SOLICITUDES DE CONFIRMACIÓN =====
    const solicitarGuardado = (e) => {
        e.preventDefault();
        setError('');
        if (!validarFormulario()) return;
        setModalConf({ tipo: 'guardar' });
    };

    const solicitarCancelacion = () => {
        setModalConf({ tipo: 'cancelar' });
    };

    const solicitarEliminacion = (uid) => {
        setModalConf({ tipo: 'eliminar', uid });
    };

    const confirmarAccion = () => {
        if (!modalConf) return;
        const { tipo, uid } = modalConf;
        setModalConf(null);
        if (tipo === 'guardar') {
            ejecutarGuardado();
        } else if (tipo === 'cancelar') {
            handleClose();
        } else if (tipo === 'eliminar') {
            eliminarIngrediente(uid);
        }
    };

    const obtenerMensajeConfirmacion = () => {
        if (!modalConf) return '';
        if (modalConf.tipo === 'guardar') {
            return `¿Estás seguro de que deseas ${esEdicion ? 'actualizar' : 'guardar'} la receta "${formData.nombre}"? Se grabarán ${ingredientes.length} línea(s) de ingredientes en sus componentes.`;
        }
        if (modalConf.tipo === 'cancelar') {
            return '¿Estás seguro de que deseas cancelar? Los cambios no guardados se perderán.';
        }
        if (modalConf.tipo === 'eliminar') {
            const row = ingredientes.find(i => i.uid === modalConf.uid);
            const nombreIng = ingredientesDisponibles.find(i => i.id === parseInt(row?.ingrediente_id))?.nombre;
            const nombreComp = componentes.find(c => c.id === row?.componente_id)?.nombre;
            return `¿Estás seguro de eliminar la fila ${nombreIng ? `"${nombreIng}"` : 'sin ingrediente'} del componente ${nombreComp || ''}? Esta acción no se puede deshacer.`;
        }
        return '';
    };

    // ===== GUARDADO REAL (se ejecuta solo tras confirmación) =====
    const ejecutarGuardado = async () => {
        setLoading(true);
        try {
            const recetaData = {
                nombre: formData.nombre,
                descripcion: formData.descripcion,
                // COM-45: se envían las raciones validadas (entero > 0) al backend
                raciones: parseInt(formData.raciones, 10),
                hierro_mg: parseFloat(formData.hierro_mg) || null,
                proteina_g: parseFloat(formData.proteina_g) || null,
                energia_kcal: parseFloat(formData.energia_kcal) || null,
                vitamina_a_ug: parseFloat(formData.vitamina_a_ug) || null,
                zinc_mg: parseFloat(formData.zinc_mg) || null,
                carbohidratos_g: parseFloat(formData.carbohidratos_g) || null
            };
            let recetaId;
            if (esEdicion) {
                // Actualizar receta existente
                await api.updateReceta(recetaEditar.id, recetaData);
                recetaId = recetaEditar.id;
                // COM-48 (trazabilidad): sincronización anterior por ingrediente comentada
                // (con componentes, un ingrediente puede tener varias filas y borrarlo
                // por id las perdería todas):
                // for (const ing of ingredientes) {
                //     if (ing.ingrediente_id) {
                //         await api.deleteIngredienteReceta(recetaId, ing.ingrediente_id);
                //     }
                // }
                // COM-48: limpiar TODAS las líneas y re-grabar con componente explícito
                await api.limpiarIngredientesReceta(recetaId);
                for (const ing of ingredientes) {
                    if (ing.ingrediente_id && ing.cantidad_requerida && ing.unidad_medida_id && ing.componente_id) {
                        await api.addIngredienteReceta(recetaId, {
                            ingrediente_id: parseInt(ing.ingrediente_id),
                            cantidad_requerida: parseFloat(ing.cantidad_requerida),
                            unidad_medida_id: parseInt(ing.unidad_medida_id),
                            componente_id: parseInt(ing.componente_id)
                        });
                    }
                }
            } else {
                // Crear nueva receta y luego asociar sus ingredientes por componente
                const response = await api.createReceta(recetaData);
                recetaId = response.id;
                for (const ing of ingredientes) {
                    if (ing.ingrediente_id && ing.cantidad_requerida && ing.unidad_medida_id && ing.componente_id) {
                        await api.addIngredienteReceta(recetaId, {
                            ingrediente_id: parseInt(ing.ingrediente_id),
                            cantidad_requerida: parseFloat(ing.cantidad_requerida),
                            unidad_medida_id: parseInt(ing.unidad_medida_id),
                            componente_id: parseInt(ing.componente_id)
                        });
                    }
                }
            }
            // UX (COM-18): mostrar modal de éxito (reemplaza al alert nativo).
            setMensajeExito(esEdicion ? 'Receta actualizada exitosamente' : 'Receta creada exitosamente');
        } catch (err) {
            console.error('Error guardando receta:', err);
            mostrarError('Error al guardar la receta: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    // Cierra el modal dejando el formulario limpio
    const handleClose = () => {
        resetearFormulario();
        onClose();
    };

    // Al aceptar el modal de éxito: cierra todo, limpia y notifica al padre para refrescar
    const cerrarExito = () => {
        setMensajeExito('');
        resetearFormulario();
        onClose();
        if (onSuccess) {
            onSuccess();
        }
    };

    if (!isOpen) return null;

    return (
        <>
            {/* Contenedor externo SIN overflow propio; el scroll vive dentro del modal */}
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                {/* Altura máxima 90vh + layout de columna => encabezado y pie fijos, cuerpo scrolleable */}
                <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
                    {/* ===== Encabezado fijo (siempre visible) ===== */}
                    <div className="flex justify-between items-center px-6 py-4 border-b border-slate-200 bg-white shrink-0">
                        <h3 className="font-bold text-xl text-slate-800">
                            {esEdicion ? 'Editar Receta' : 'Nueva Receta'}
                        </h3>
                        {/* UX (COM-18): la X también pide confirmación para no perder cambios */}
                        <button
                            onClick={solicitarCancelacion}
                            className="text-slate-400 hover:text-slate-600 transition-colors"
                            aria-label="Cerrar modal"
                        >
                            <X size={24} />
                        </button>
                    </div>
                    {/* El form envuelve cuerpo scrolleable + pie fijo para que el submit funcione desde el pie */}
                    <form onSubmit={solicitarGuardado} className="flex flex-col flex-1 min-h-0">
                        {/* ===== Cuerpo con scroll interno ===== */}
                        <div ref={cuerpoRef} className="flex-1 overflow-y-auto p-6">
                            {/* Mensaje de error de validación */}
                            {error && (
                                <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg">
                                    {error}
                                </div>
                            )}
                            {/* ===== Sección: Información General ===== */}
                            <div className="mb-6">
                                <h4 className="text-lg font-semibold text-slate-700 mb-4">Información General</h4>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="md:col-span-2">
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Nombre de la Receta *
                                        </label>
                                        <input
                                            type="text"
                                            name="nombre"
                                            value={formData.nombre}
                                            onChange={handleInputChange}
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
                                            placeholder="Ej: Menú del día: chaufa + ensalada + refresco + fruta"
                                            required
                                        />
                                    </div>
                                    <div className="md:col-span-2">
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Descripción
                                        </label>
                                        <textarea
                                            name="descripcion"
                                            value={formData.descripcion}
                                            onChange={handleInputChange}
                                            rows="2"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                            placeholder="Descripción de la receta (composición de componentes)..."
                                        />
                                    </div>
                                    {/* COM-45: cantidad de raciones para las que está pensada la receta */}
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Raciones *
                                        </label>
                                        <input
                                            type="number"
                                            name="raciones"
                                            value={formData.raciones}
                                            onChange={handleInputChange}
                                            step="1"
                                            min="1"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                            placeholder="Ej: 4"
                                            title="Número de raciones que produce la preparación (entero mayor a 0)"
                                            required
                                        />
                                        <p className="text-[11px] text-slate-400 mt-1">
                                            La nutrición y el costo se analizan por ración (COM-47 v2).
                                        </p>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Energía (kcal/ración)
                                        </label>
                                        <input
                                            type="number"
                                            name="energia_kcal"
                                            value={formData.energia_kcal}
                                            onChange={handleInputChange}
                                            step="0.01"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Proteína (g/ración)
                                        </label>
                                        <input
                                            type="number"
                                            name="proteina_g"
                                            value={formData.proteina_g}
                                            onChange={handleInputChange}
                                            step="0.01"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Hierro (mg/ración)
                                        </label>
                                        <input
                                            type="number"
                                            name="hierro_mg"
                                            value={formData.hierro_mg}
                                            onChange={handleInputChange}
                                            step="0.01"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Vitamina A (μg/ración)
                                        </label>
                                        <input
                                            type="number"
                                            name="vitamina_a_ug"
                                            value={formData.vitamina_a_ug}
                                            onChange={handleInputChange}
                                            step="0.01"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Zinc (mg/ración)
                                        </label>
                                        <input
                                            type="number"
                                            name="zinc_mg"
                                            value={formData.zinc_mg}
                                            onChange={handleInputChange}
                                            step="0.01"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Carbohidratos (g/ración)
                                        </label>
                                        <input
                                            type="number"
                                            name="carbohidratos_g"
                                            value={formData.carbohidratos_g}
                                            onChange={handleInputChange}
                                            step="0.01"
                                            className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500"
                                        />
                                    </div>
                                </div>
                            </div>

                            {/* ===== COM-48: Ingredientes agrupados por componente ===== */}
                            <div className="mb-2">
                                <div className="flex justify-between items-center mb-3">
                                    <h4 className="text-lg font-semibold text-slate-700">
                                        Ingredientes por componente *{' '}
                                        <span className="text-sm font-normal text-slate-400">
                                            ({ingredientes.length} {ingredientes.length === 1 ? 'línea' : 'líneas'})
                                        </span>
                                    </h4>
                                </div>
                                <p className="text-[11px] text-slate-500 mb-4">
                                    Cada receta se compone de componentes (Ensalada, Plato de fondo, Refresco, Fruta).
                                    Un mismo ingrediente puede usarse en varios componentes con cantidades independientes
                                    (ej. limón en la ensalada y en el refresco).
                                </p>
                                {componentes.length === 0 ? (
                                    <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-amber-800 text-sm">
                                        No se pudo cargar el catálogo de componentes. Verifique la conexión o recargue.
                                    </div>
                                ) : (
                                    componentes.map(comp => {
                                        const filas = ingredientes.filter(i => i.componente_id === comp.id);
                                        return (
                                            <div key={comp.id} className="mb-5 border border-slate-200 rounded-xl overflow-hidden">
                                                {/* Encabezado del componente */}
                                                <div className="flex justify-between items-center px-4 py-2 bg-slate-100 border-b border-slate-200">
                                                    <div>
                                                        <p className="text-sm font-bold text-slate-700">{comp.nombre}</p>
                                                        {comp.descripcion && (
                                                            <p className="text-[10px] text-slate-500">{comp.descripcion}</p>
                                                        )}
                                                    </div>
                                                    <button
                                                        type="button"
                                                        onClick={() => agregarIngrediente(comp.id)}
                                                        className="flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-xs font-medium"
                                                    >
                                                        <Plus size={14} />
                                                        Agregar ingrediente
                                                    </button>
                                                </div>
                                                {/* Filas del componente */}
                                                <div className="p-3 space-y-2 bg-white">
                            {/* Encabezados de columna ÚNICOS por componente */}
                            <div className="grid grid-cols-12 gap-2 px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                                <span className="col-span-6">Ingrediente</span>
                                <span className="col-span-2">Cantidad *</span>
                                <span className="col-span-3">Unidad *</span>
                                <span className="col-span-1 text-center">Acción</span>
                            </div>
                            {filas.length === 0 ? (
                                <p className="text-[11px] text-slate-400 px-2 py-2">
                                    Sin ingredientes en este componente. Use "Agregar ingrediente".
                                </p>
                            ) : (
                                filas.map((ing) => (
                                    <div
                                        key={ing.uid}
                                        className="grid grid-cols-12 gap-2 items-center border border-slate-200 rounded-lg px-2 py-2 bg-white"
                                    >
                                        {/* Select de ingrediente */}
                                        <div className="col-span-6">
                                            <select
                                                value={ing.ingrediente_id}
                                                onChange={(e) => handleIngredienteChange(ing.uid, 'ingrediente_id', e.target.value)}
                                                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm bg-white"
                                                aria-label={`Ingrediente en ${comp.nombre}`}
                                                required
                                            >
                                                <option value="">Seleccionar...</option>
                                                {ingredientesDisponibles.map(item => (
                                                    <option key={item.id} value={item.id}>
                                                        {item.nombre}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                        {/* Cantidad requerida */}
                                        <div className="col-span-2">
                                            <input
                                                type="number"
                                                value={ing.cantidad_requerida}
                                                onChange={(e) => handleIngredienteChange(ing.uid, 'cantidad_requerida', e.target.value)}
                                                step="0.01"
                                                min="0.01"
                                                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm"
                                                placeholder="Ej: 100"
                                                aria-label={`Cantidad en ${comp.nombre}`}
                                                required
                                            />
                                        </div>
                                        {/* Unidad de medida */}
                                        <div className="col-span-3">
                                            <select
                                                value={ing.unidad_medida_id}
                                                onChange={(e) => handleIngredienteChange(ing.uid, 'unidad_medida_id', e.target.value)}
                                                className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm bg-white"
                                                aria-label={`Unidad en ${comp.nombre}`}
                                                required
                                            >
                                                <option value="">Seleccionar...</option>
                                                {unidadesMedida.map(um => (
                                                    <option key={um.id} value={um.id}>
                                                        {um.nombre}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                        {/* Botón eliminar fila (pide confirmación COM-18) */}
                                        <div className="col-span-1 flex justify-center">
                                            <button
                                                type="button"
                                                onClick={() => solicitarEliminacion(ing.uid)}
                                                className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                                aria-label={`Eliminar fila de ${comp.nombre}`}
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                    </div>
                                ))
                            )}
                                                </div>
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                        {/* ===== Pie fijo con acciones (siempre visible) ===== */}
                        <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200 bg-slate-50 shrink-0">
                            {/* UX (COM-18): Cancelar pide confirmación antes de descartar cambios */}
                            <button
                                type="button"
                                onClick={solicitarCancelacion}
                                className="px-6 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
                            >
                                Cancelar
                            </button>
                            {/* UX (COM-18): Guardar valida y pide confirmación antes de ejecutar */}
                            <button
                                type="submit"
                                disabled={loading}
                                className="px-6 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? 'Guardando...' : (esEdicion ? 'Actualizar Receta' : 'Guardar Receta')}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
            {/* Modal de confirmación para acciones sensibles (guardar/cancelar/eliminar) */}
            <ModalConfirmacion
                isOpen={!!modalConf}
                onClose={() => setModalConf(null)}
                onConfirm={confirmarAccion}
                mensaje={obtenerMensajeConfirmacion()}
                tipo={modalConf?.tipo === 'eliminar' ? 'danger' : 'warning'}
            />
            {/* Modal de éxito con el diseño de la web (reemplaza al alert nativo) */}
            <ModalExito
                isOpen={!!mensajeExito}
                onClose={cerrarExito}
                mensaje={mensajeExito}
            />
        </>
    );
};