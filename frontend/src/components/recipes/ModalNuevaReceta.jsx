/**
 * components/recipes/ModalNuevaReceta.jsx
 * Objetivo: Modal de creación y edición de recetas. Gestiona los datos nutricionales
 *           (hierro, proteína, energía, vitamina A, zinc, carbohidratos) y la lista
 *           dinámica de ingredientes con sus unidades de medida y cantidades requeridas.
 * Uso: Importado por RecipesView.jsx y GestionRecetas.jsx. Se controla mediante las props
 *      `isOpen`, `onClose`, `onSuccess` y `recetaEditar` (activa el modo edición).
 *
 * CORRECCIÓN DE BUG (Ticket Jira COM-16):
 *  - Causa original: el contenedor externo combinaba `items-center` con `overflow-y-auto`
 *    y la caja interna crecía sin altura máxima; con listas largas de ingredientes la parte
 *    superior (encabezado e "Información General") quedaba recortada e inaccesible.
 *  - Solución: el modal tiene altura máxima (max-h-[90vh]) con layout de columna:
 *    encabezado fijo, cuerpo con scroll interno y pie de acciones fijo.
 *  - Lista de ingredientes como cuadrícula compacta tipo tabla: encabezados de columna
 *    únicos, filas numeradas y fondos alternados para facilitar su lectura.
 *
 * MEJORA UX (Ticket Jira COM-18):
 *  - Confirmación modal antes de Guardar, Cancelar (o cerrar con X) y Eliminar ingrediente,
 *    para evitar pérdidas de trabajo por clics accidentales (reutiliza ModalConfirmacion).
 *  - El mensaje de éxito deja de ser un alert() nativo y pasa a un ModalExito con el
 *    mismo diseño de la web.
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
        hierro_mg: '',
        proteina_g: '',
        energia_kcal: '',
        vitamina_a_ug: '',
        zinc_mg: '',
        carbohidratos_g: ''
    });

    // Lista dinámica de ingredientes (siempre inicia con 1 fila)
    const [ingredientes, setIngredientes] = useState([
        { ingrediente_id: '', cantidad_requerida: '', unidad_medida_id: '' }
    ]);

    // Catálogos cargados desde la API para alimentar los selects
    const [unidadesMedida, setUnidadesMedida] = useState([]);
    const [ingredientesDisponibles, setIngredientesDisponibles] = useState([]);

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    // UX (COM-18): modal de confirmación para acciones sensibles.
    // Estructura: { tipo: 'guardar' | 'cancelar' | 'eliminar', index?: number }
    const [modalConf, setModalConf] = useState(null);

    // UX (COM-18): mensaje del modal de éxito (string vacío = cerrado)
    const [mensajeExito, setMensajeExito] = useState('');

    // Referencia al cuerpo scrolleable para subir el scroll al mostrar errores
    const cuerpoRef = useRef(null);

    // Al abrir el modal: cargar catálogos y preparar modo edición o creación
    useEffect(() => {
        if (isOpen) {
            cargarDatosIniciales();
            if (esEdicion && recetaEditar) {
                cargarRecetaParaEditar();
            } else {
                resetearFormulario();
            }
        }
    }, [isOpen, recetaEditar]);

    // Carga unidades de medida e ingredientes disponibles desde la API
    const cargarDatosIniciales = async () => {
        try {
            const [unidades, ingredientes] = await Promise.all([
                api.getUnidadesMedida(),
                api.getIngredientesDisponibles()
            ]);
            setUnidadesMedida(unidades);
            setIngredientesDisponibles(ingredientes);
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
                hierro_mg: data.receta.hierro_mg || '',
                proteina_g: data.receta.proteina_g || '',
                energia_kcal: data.receta.energia_kcal || '',
                vitamina_a_ug: data.receta.vitamina_a_ug || '',
                zinc_mg: data.receta.zinc_mg || '',
                carbohidratos_g: data.receta.carbohidratos_g || ''
            });
            if (data.ingredientes && data.ingredientes.length > 0) {
                setIngredientes(data.ingredientes.map(ing => ({
                    ingrediente_id: ing.ingrediente_id,
                    cantidad_requerida: ing.cantidad_requerida,
                    unidad_medida_id: ing.unidad_medida_id
                })));
            } else {
                setIngredientes([{ ingrediente_id: '', cantidad_requerida: '', unidad_medida_id: '' }]);
            }
        } catch (err) {
            console.error('Error cargando receta:', err);
            setError('Error al cargar la receta para editar');
        }
    };

    // Restablece el formulario a su estado inicial (modo creación)
    const resetearFormulario = () => {
        setFormData({
            nombre: '',
            descripcion: '',
            hierro_mg: '',
            proteina_g: '',
            energia_kcal: '',
            vitamina_a_ug: '',
            zinc_mg: '',
            carbohidratos_g: ''
        });
        setIngredientes([{ ingrediente_id: '', cantidad_requerida: '', unidad_medida_id: '' }]);
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

    // Actualiza un campo de una fila específica de la lista de ingredientes
    const handleIngredienteChange = (index, field, value) => {
        const nuevosIngredientes = [...ingredientes];
        nuevosIngredientes[index][field] = value;
        setIngredientes(nuevosIngredientes);
    };

    // Agrega una nueva fila vacía a la lista de ingredientes
    const agregarIngrediente = () => {
        setIngredientes([...ingredientes, { ingrediente_id: '', cantidad_requerida: '', unidad_medida_id: '' }]);
    };

    // Elimina una fila de ingredientes (mínimo 1 fila siempre)
    const eliminarIngrediente = (index) => {
        if (ingredientes.length > 1) {
            setIngredientes(ingredientes.filter((_, i) => i !== index));
        }
    };

    // Valida nombre de receta y que cada fila de ingrediente esté completa
    const validarFormulario = () => {
        if (!formData.nombre.trim()) {
            mostrarError('El nombre de la receta es obligatorio');
            return false;
        }
        for (let i = 0; i < ingredientes.length; i++) {
            const ing = ingredientes[i];
            if (!ing.ingrediente_id) {
                mostrarError(`El ingrediente ${i + 1} es obligatorio`);
                return false;
            }
            if (!ing.cantidad_requerida || parseFloat(ing.cantidad_requerida) <= 0) {
                mostrarError(`La cantidad del ingrediente ${i + 1} es obligatoria y debe ser mayor a 0`);
                return false;
            }
            if (!ing.unidad_medida_id) {
                mostrarError(`La unidad de medida del ingrediente ${i + 1} es obligatoria`);
                return false;
            }
        }
        return true;
    };

    // ===== UX (COM-18): SOLICITUDES DE CONFIRMACIÓN (no ejecutan la acción directamente) =====

    // Submit del formulario: valida y, si todo es correcto, pide confirmación de guardado
    const solicitarGuardado = (e) => {
        e.preventDefault();
        setError('');
        if (!validarFormulario()) return;
        setModalConf({ tipo: 'guardar' });
    };

    // Cancelar (botón o X del encabezado): pide confirmación antes de descartar cambios
    const solicitarCancelacion = () => {
        setModalConf({ tipo: 'cancelar' });
    };

    // Eliminar ingrediente: pide confirmación antes de quitar la fila
    const solicitarEliminacion = (index) => {
        setModalConf({ tipo: 'eliminar', index });
    };

    // Ejecuta la acción confirmada según el tipo pendiente en modalConf
    const confirmarAccion = () => {
        if (!modalConf) return;
        const { tipo, index } = modalConf;
        setModalConf(null); // cierra el modal de confirmación antes de ejecutar
        if (tipo === 'guardar') {
            ejecutarGuardado();
        } else if (tipo === 'cancelar') {
            handleClose();
        } else if (tipo === 'eliminar') {
            eliminarIngrediente(index);
        }
    };

    // Construye el mensaje del modal de confirmación según la acción pendiente
    const obtenerMensajeConfirmacion = () => {
        if (!modalConf) return '';
        if (modalConf.tipo === 'guardar') {
            return `¿Estás seguro de que deseas ${esEdicion ? 'actualizar' : 'guardar'} la receta "${formData.nombre}"?`;
        }
        if (modalConf.tipo === 'cancelar') {
            return '¿Estás seguro de que deseas cancelar? Los cambios no guardados se perderán.';
        }
        if (modalConf.tipo === 'eliminar') {
            const ing = ingredientes[modalConf.index];
            const nombreIng = ingredientesDisponibles.find(i => i.id === parseInt(ing?.ingrediente_id))?.nombre;
            return `¿Estás seguro de eliminar el ingrediente ${nombreIng ? `"${nombreIng}"` : `#${modalConf.index + 1}`}? Esta acción no se puede deshacer.`;
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
                // Sincronizar ingredientes: eliminar los actuales y registrar los nuevos
                for (const ing of ingredientes) {
                    if (ing.ingrediente_id) {
                        await api.deleteIngredienteReceta(recetaId, ing.ingrediente_id);
                    }
                }
                for (const ing of ingredientes) {
                    if (ing.ingrediente_id && ing.cantidad_requerida && ing.unidad_medida_id) {
                        await api.addIngredienteReceta(recetaId, {
                            ingrediente_id: parseInt(ing.ingrediente_id),
                            cantidad_requerida: parseFloat(ing.cantidad_requerida),
                            unidad_medida_id: parseInt(ing.unidad_medida_id)
                        });
                    }
                }
            } else {
                // Crear nueva receta y luego asociar sus ingredientes
                const response = await api.createReceta(recetaData);
                recetaId = response.id;
                for (const ing of ingredientes) {
                    if (ing.ingrediente_id && ing.cantidad_requerida && ing.unidad_medida_id) {
                        await api.addIngredienteReceta(recetaId, {
                            ingrediente_id: parseInt(ing.ingrediente_id),
                            cantidad_requerida: parseFloat(ing.cantidad_requerida),
                            unidad_medida_id: parseInt(ing.unidad_medida_id)
                        });
                    }
                }
            }
            // UX (COM-18): mostrar modal de éxito (reemplaza al alert nativo).
            // El cierre real y el refresco de la lista ocurren al aceptar el modal de éxito.
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
                        {/* UX (COM-18): la X también pide confirmación para no perder cambios por accidente */}
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
                                            placeholder="Ej: Arroz con Pollo"
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
                                            placeholder="Descripción de la receta..."
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-slate-700 mb-1">
                                            Energía (kcal)
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
                                            Proteína (g)
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
                                            Hierro (mg)
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
                                            Vitamina A (μg)
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
                                            Zinc (mg)
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
                                            Carbohidratos (g)
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

                            {/* ===== Sección: Ingredientes (cuadrícula tipo tabla) ===== */}
                            <div className="mb-2">
                                {/* Encabezado de sección con contador y botón de agregar */}
                                <div className="flex justify-between items-center mb-3">
                                    <h4 className="text-lg font-semibold text-slate-700">
                                        Ingredientes *{' '}
                                        <span className="text-sm font-normal text-slate-400">
                                            ({ingredientes.length} {ingredientes.length === 1 ? 'ítem' : 'ítems'})
                                        </span>
                                    </h4>
                                    <button
                                        type="button"
                                        onClick={agregarIngrediente}
                                        className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm"
                                    >
                                        <Plus size={16} />
                                        Agregar Ingrediente
                                    </button>
                                </div>

                                {/* Encabezados de columna ÚNICOS para toda la lista */}
                                <div className="grid grid-cols-12 gap-2 px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                                    <span className="col-span-6">Ingrediente</span>
                                    <span className="col-span-2">Cantidad *</span>
                                    <span className="col-span-3">Unidad *</span>
                                    <span className="col-span-1 text-center">Acción</span>
                                </div>

                                {/* Área de scroll propia para la lista de ingredientes */}
                                <div className="space-y-2 overflow-y-auto max-h-72 pr-1">
                                    {ingredientes.map((ing, index) => (
                                        <div
                                            key={index}
                                            className={`grid grid-cols-12 gap-2 items-center border border-slate-200 rounded-lg px-3 py-2 ${
                                                index % 2 === 1 ? 'bg-slate-50' : 'bg-white'
                                            }`}
                                        >
                                            {/* Número de fila + select de ingrediente */}
                                            <div className="col-span-6 flex items-center gap-2">
                                                <span className="text-xs font-bold text-slate-400 w-6 text-right shrink-0">
                                                    {index + 1}.
                                                </span>
                                                <select
                                                    value={ing.ingrediente_id}
                                                    onChange={(e) => handleIngredienteChange(index, 'ingrediente_id', e.target.value)}
                                                    className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm bg-white"
                                                    aria-label={`Ingrediente ${index + 1}`}
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
                                                    onChange={(e) => handleIngredienteChange(index, 'cantidad_requerida', e.target.value)}
                                                    step="0.01"
                                                    min="0.01"
                                                    className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm"
                                                    placeholder="Ej: 100"
                                                    aria-label={`Cantidad del ingrediente ${index + 1}`}
                                                    required
                                                />
                                            </div>

                                            {/* Unidad de medida */}
                                            <div className="col-span-3">
                                                <select
                                                    value={ing.unidad_medida_id}
                                                    onChange={(e) => handleIngredienteChange(index, 'unidad_medida_id', e.target.value)}
                                                    className="w-full px-3 py-1.5 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm bg-white"
                                                    aria-label={`Unidad del ingrediente ${index + 1}`}
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
                                                    onClick={() => solicitarEliminacion(index)}
                                                    className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                                                    disabled={ingredientes.length === 1}
                                                    aria-label={`Eliminar ingrediente ${index + 1}`}
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
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