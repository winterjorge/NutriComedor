import React, { useState, useEffect } from 'react';
import { X, Plus, Trash2 } from 'lucide-react';
import { api } from '../../services/api';

export const ModalNuevaReceta = ({ isOpen, onClose, onSuccess, recetaEditar }) => {
  const esEdicion = !!recetaEditar;
  
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
  
  const [ingredientes, setIngredientes] = useState([
    { ingrediente_id: '', cantidad_requerida: '', unidad_medida_id: '' }
  ]);
  
  const [unidadesMedida, setUnidadesMedida] = useState([]);
  const [ingredientesDisponibles, setIngredientesDisponibles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleIngredienteChange = (index, field, value) => {
    const nuevosIngredientes = [...ingredientes];
    nuevosIngredientes[index][field] = value;
    setIngredientes(nuevosIngredientes);
  };

  const agregarIngrediente = () => {
    setIngredientes([...ingredientes, { ingrediente_id: '', cantidad_requerida: '', unidad_medida_id: '' }]);
  };

  const eliminarIngrediente = (index) => {
    if (ingredientes.length > 1) {
      setIngredientes(ingredientes.filter((_, i) => i !== index));
    }
  };

  const validarFormulario = () => {
    if (!formData.nombre.trim()) {
      setError('El nombre de la receta es obligatorio');
      return false;
    }
    for (let i = 0; i < ingredientes.length; i++) {
      const ing = ingredientes[i];
      if (!ing.ingrediente_id) {
        setError(`El ingrediente ${i + 1} es obligatorio`);
        return false;
      }
      if (!ing.cantidad_requerida || parseFloat(ing.cantidad_requerida) <= 0) {
        setError(`La cantidad del ingrediente ${i + 1} es obligatoria y debe ser mayor a 0`);
        return false;
      }
      if (!ing.unidad_medida_id) {
        setError(`La unidad de medida del ingrediente ${i + 1} es obligatoria`);
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!validarFormulario()) {
      return;
    }

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
        
        // CORRECCIÓN: Actualizar ingredientes en edición
        // 1. Eliminar todos los ingredientes existentes
        for (const ing of ingredientes) {
          if (ing.ingrediente_id) {
            await api.deleteIngredienteReceta(recetaId, ing.ingrediente_id);
          }
        }
        
        // 2. Agregar los nuevos ingredientes
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
        // Crear nueva receta
        const response = await api.createReceta(recetaData);
        recetaId = response.id;
        
        // Agregar ingredientes
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

      handleClose();
      if (onSuccess) {
        onSuccess();
      }
      alert(esEdicion ? 'Receta actualizada exitosamente' : 'Receta creada exitosamente');
    } catch (err) {
      console.error('Error guardando receta:', err);
      setError('Error al guardar la receta: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    resetearFormulario();
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl my-8">
        <div className="flex justify-between items-center p-6 border-b">
          <h3 className="font-bold text-2xl text-slate-800">
            {esEdicion ? 'Editar Receta' : 'Nueva Receta'}
          </h3>
          <button onClick={handleClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X size={24} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6">
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg">
              {error}
            </div>
          )}

          {/* Datos básicos */}
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
                  rows="3"
                  className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
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

          {/* Ingredientes */}
          <div className="mb-6">
            <div className="flex justify-between items-center mb-4">
              <h4 className="text-lg font-semibold text-slate-700">Ingredientes *</h4>
              <button
                type="button"
                onClick={agregarIngrediente}
                className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm"
              >
                <Plus size={16} />
                Agregar Ingrediente
              </button>
            </div>

            <div className="space-y-3">
              {ingredientes.map((ing, index) => (
                <div key={index} className="flex gap-3 items-start p-3 bg-slate-50 rounded-lg">
                  <div className="flex-1">
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Ingrediente
                    </label>
                    <select
                      value={ing.ingrediente_id}
                      onChange={(e) => handleIngredienteChange(index, 'ingrediente_id', e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm"
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

                  <div className="w-32">
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Cantidad *
                    </label>
                    <input
                      type="number"
                      value={ing.cantidad_requerida}
                      onChange={(e) => handleIngredienteChange(index, 'cantidad_requerida', e.target.value)}
                      step="0.01"
                      min="0.01"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm"
                      placeholder="Ej: 100"
                      required
                    />
                  </div>

                  <div className="w-40">
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Unidad *
                    </label>
                    <select
                      value={ing.unidad_medida_id}
                      onChange={(e) => handleIngredienteChange(index, 'unidad_medida_id', e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-emerald-500 text-sm"
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

                  <button
                    type="button"
                    onClick={() => eliminarIngrediente(index)}
                    className="mt-6 p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    disabled={ingredientes.length === 1}
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Botones */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <button
              type="button"
              onClick={handleClose}
              className="px-6 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
            >
              Cancelar
            </button>
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
  );
};