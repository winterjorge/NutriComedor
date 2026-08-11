import React, { useState } from 'react';
import { X, Save, Trash2, AlertCircle, Search, Loader2, CheckCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useParametros } from '../../context/ParametrosContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';

export const ModalEdicionVenta = ({ venta, onClose, onActualizacion }) => {
    const { parametros } = useParametros();
    
    // Fallbacks de seguridad
    const precioSocial = parametros.PRECIO_SOCIAL ?? 0;
    const precioAfiliado = parametros.PRECIO_AFILIADO ?? 3;
    const precioNormal = parametros.PRECIO_NORMAL ?? 5;
    const alertaRaciones = parametros.ALERTA_RACIONES_MAX || 3;

    const [data, setData] = useState({ ...venta });
    const [motivo, setMotivo] = useState('');
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');
    const [cargando, setCargando] = useState(false);
    const [modalConf, setModalConf] = useState(null); // 'edit' | 'delete' | null

    // Estados para cambio de comensal
    const [docCambio, setDocCambio] = useState('');
    const [cargandoCambio, setCargandoCambio] = useState(false);

    const calcularMonto = () => {
        const p = data.tipo_comensal_venta === 'Social' 
            ? precioSocial 
            : data.tipo_comensal_venta === 'Afiliado' 
                ? precioAfiliado 
                : precioNormal;
        return (p * data.raciones).toFixed(2);
    };

    const cambiarComensal = async () => {
        if (docCambio.length < 8) {
            setError("El documento debe tener al menos 8 caracteres");
            return;
        }
        setError('');
        setCargandoCambio(true);
        try {
            const res = await api.buscarComensal(docCambio);
            if (res.ok) {
                const c = await res.json();
                setData({ 
                    ...data, 
                    comensal_id: c.id, 
                    nombres: c.nombres, 
                    documento_identidad: c.documento_identidad 
                });
                setDocCambio('');
                setExito(`Comensal cambiado a: ${c.nombres}`);
                setTimeout(() => setExito(''), 3000);
            } else {
                setError("Comensal no encontrado. Verifique el documento.");
            }
        } catch (e) {
            console.error("Error buscando comensal:", e);
            setError("Error de conexión al buscar comensal");
        } finally {
            setCargandoCambio(false);
        }
    };

    const guardar = async () => {
        setError('');
        setExito('');
        
        // Validar que raciones sea al menos 1
        if (data.raciones < 1) {
            return setError("Las raciones deben ser al menos 1. Use el botón Eliminar si desea remover la venta.");
        }
        
        if (!motivo.trim()) {
            return setError("El motivo es obligatorio para modificar la venta.");
        }
        
        // Confirmar si es muchas raciones
        if (data.raciones > alertaRaciones) {
            setModalConf('edit');
        } else {
            await ejecutarGuardado();
        }
    };

    const ejecutarGuardado = async () => {
        setModalConf(null);
        setCargando(true);
        
        try {
            const p = data.tipo_comensal_venta === 'Social' 
                ? precioSocial 
                : data.tipo_comensal_venta === 'Afiliado' 
                    ? precioAfiliado 
                    : precioNormal;
            
            const payload = {
                comensal_id: data.comensal_id,
                raciones: data.raciones,
                monto_pagado: p * data.raciones,
                tipo_menu: data.tipo_menu || "Almuerzo regular",
                tipo_comensal_venta: data.tipo_comensal_venta,
                observacion: data.observacion || '',
                motivo_modificacion: motivo
            };
            
            console.log("Enviando modificación:", payload);
            
            const res = await api.modificarVenta(venta.id, payload);
            
            if (res.ok) {
                setExito("Venta modificada exitosamente");
                setTimeout(() => {
                    onActualizacion();
                    onClose();
                }, 1000);
            } else {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Error al modificar');
            }
        } catch (err) {
            console.error("Error modificando venta:", err);
            setError(`Error: ${err.message}`);
        } finally {
            setCargando(false);
        }
    };

    const eliminar = async () => {
        setError('');
        setExito('');
        setModalConf('delete');
    };

    const confirmarEliminacion = async () => {
        setModalConf(null);
        setCargando(true);
        
        try {
            // Usar el endpoint DELETE real
            const res = await fetch(`/api/v1/padron/${venta.id}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (res.ok) {
                setExito("Venta eliminada exitosamente");
                setTimeout(() => {
                    onActualizacion();
                    onClose();
                }, 1000);
            } else {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Error al eliminar');
            }
        } catch (err) {
            console.error("Error eliminando venta:", err);
            setError(`Error al eliminar: ${err.message}`);
        } finally {
            setCargando(false);
        }
    };

    return (
        <>
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
                <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden max-h-[90vh] flex flex-col">
                    <div className="flex justify-between items-center p-5 border-b bg-slate-50">
                        <h3 className="font-bold text-lg">Modificar Orden #{venta.id}</h3>
                        <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
                            <X size={20} />
                        </button>
                    </div>
                    
                    <div className="p-5 space-y-4 overflow-y-auto">
                        {/* Mensajes de éxito/error */}
                        {exito && (
                            <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-3 rounded-lg flex items-center gap-2">
                                <CheckCircle size={18} />
                                <p className="text-sm font-medium">{exito}</p>
                            </div>
                        )}
                        
                        {error && (
                            <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg flex items-center gap-2">
                                <AlertCircle size={18} />
                                <p className="text-sm font-medium">{error}</p>
                            </div>
                        )}

                        {/* Cambio de comensal */}
                        <div className="bg-blue-50 p-3 rounded-lg border border-blue-200">
                            <label className="block text-sm font-semibold text-blue-800 mb-2">
                                Cambiar Comensal (si hubo error)
                            </label>
                            <div className="flex gap-2">
                                <div className="relative flex-1">
                                    <Search className="absolute left-3 top-2 text-slate-400" size={16} />
                                    <input 
                                        type="text" 
                                        placeholder="Nuevo DNI..." 
                                        value={docCambio} 
                                        onChange={e => setDocCambio(e.target.value.replace(/[^0-9]/g, ''))} 
                                        className="w-full pl-9 pr-3 py-1.5 border border-blue-300 rounded-lg text-sm outline-none focus:border-blue-500"
                                    />
                                </div>
                                <button 
                                    onClick={cambiarComensal} 
                                    disabled={cargandoCambio || docCambio.length < 8} 
                                    className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {cargandoCambio ? <Loader2 className="animate-spin" size={16} /> : 'Buscar'}
                                </button>
                            </div>
                        </div>

                        {/* Comensal actual */}
                        <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                            <p className="text-xs font-bold text-slate-400 uppercase">Comensal Actual:</p>
                            <p className="font-bold text-slate-700">{data.nombres}</p>
                            <p className="text-xs text-slate-500">Doc: {data.documento_identidad}</p>
                        </div>

                        {/* Tipo de venta */}
                        <div>
                            <label className="block text-sm font-semibold text-slate-600 mb-1">Tipo de Venta</label>
                            <select 
                                value={data.tipo_comensal_venta} 
                                onChange={e => setData({...data, tipo_comensal_venta: e.target.value})} 
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none bg-white focus:border-blue-500"
                            >
                                <option value="Social">Social (S/ {precioSocial.toFixed(2)})</option>
                                <option value="Afiliado">Afiliado (S/ {precioAfiliado.toFixed(2)})</option>
                                <option value="Normal">Normal (S/ {precioNormal.toFixed(2)})</option>
                            </select>
                        </div>

                        {/* Raciones y Total */}
                        <div className="flex gap-4">
                            <div className="w-1/2">
                                <label className="block text-sm font-semibold text-slate-600 mb-1">Raciones (mín. 1)</label>
                                <input 
                                    type="number" 
                                    min="1"
                                    value={data.raciones} 
                                    onChange={e => {
                                        const val = parseInt(e.target.value);
                                        setData({...data, raciones: isNaN(val) || val < 1 ? 1 : val});
                                    }} 
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:border-blue-500"
                                />
                            </div>
                            <div className="w-1/2">
                                <label className="block text-sm font-semibold text-slate-600 mb-1">Total a Pagar</label>
                                <div className="w-full px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-lg font-bold text-emerald-700 text-center">
                                    S/ {calcularMonto()}
                                </div>
                            </div>
                        </div>

                        {/* Observación */}
                        <div>
                            <label className="block text-sm font-semibold text-slate-600 mb-1">Observación</label>
                            <input 
                                type="text" 
                                value={data.observacion || ''} 
                                onChange={e => setData({...data, observacion: e.target.value})} 
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none focus:border-blue-500"
                                placeholder="Observaciones adicionales..."
                            />
                        </div>

                        {/* Motivo (obligatorio) */}
                        <div className="bg-amber-50 p-3 rounded-lg border border-amber-200">
                            <label className="block text-sm font-semibold text-amber-800 mb-1">
                                Motivo de la Modificación *
                            </label>
                            <textarea 
                                required 
                                value={motivo} 
                                onChange={e => setMotivo(e.target.value)} 
                                className="w-full px-3 py-2 border border-amber-200 rounded-lg outline-none text-sm resize-none focus:border-amber-500" 
                                rows="2"
                                placeholder="Ej: Error en raciones, cambio de comensal, etc."
                            ></textarea>
                        </div>

                        {/* Botones de acción */}
                        <div className="flex gap-3 mt-4 pt-4 border-t">
                            <button 
                                onClick={eliminar} 
                                disabled={cargando}
                                className="flex-1 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-bold py-3 rounded-lg flex justify-center gap-2 items-center transition-colors"
                            >
                                <Trash2 size={18} /> 
                                {cargando ? 'Eliminando...' : 'Eliminar'}
                            </button>
                            <button 
                                onClick={guardar} 
                                disabled={cargando}
                                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-bold py-3 rounded-lg flex justify-center gap-2 items-center transition-colors"
                            >
                                {cargando ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} />} 
                                {cargando ? 'Guardando...' : 'Guardar'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Modal de confirmación para edición */}
            <ModalConfirmacion 
                isOpen={modalConf === 'edit'} 
                onClose={() => setModalConf(null)} 
                onConfirm={ejecutarGuardado} 
                mensaje={`Estás modificando a ${data.raciones} raciones para ${data.nombres}. ¿Continuar?`} 
            />
            
            {/* Modal de confirmación para eliminación */}
            <ModalConfirmacion 
                isOpen={modalConf === 'delete'} 
                onClose={() => setModalConf(null)} 
                onConfirm={confirmarEliminacion} 
                mensaje={`¿Estás seguro de ELIMINAR permanentemente el registro de ${data.nombres}? Esta acción no se puede deshacer.`} 
                tipo="danger" 
            />
        </>
    );
};