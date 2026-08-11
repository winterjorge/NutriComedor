import React, { useState } from 'react';
import { UserCheck, Search, Loader2 } from 'lucide-react';
import { api } from '../../services/api';
import { useParametros } from '../../context/ParametrosContext'; // <-- CAMBIO
import { ModalConfirmacion } from '../common/ModalConfirmacion';

export const FormularioVenta = ({ onVentaRegistrada }) => {
    const { parametros } = useParametros(); // <-- CAMBIO
    
    // Fallbacks de seguridad
    const precioSocial = parametros.PRECIO_SOCIAL ?? 0;
    const precioAfiliado = parametros.PRECIO_AFILIADO ?? 3;
    const precioNormal = parametros.PRECIO_NORMAL ?? 5;
    const alertaRaciones = parametros.ALERTA_RACIONES_MAX || 3;

    const [docBusqueda, setDocBusqueda] = useState('');
    const [comensal, setComensal] = useState(null);
    const [cargandoDoc, setCargandoDoc] = useState(false);
    const [tipoVenta, setTipoVenta] = useState('Normal');
    const [raciones, setRaciones] = useState(1);
    const [obs, setObs] = useState('');
    const [nuevoForm, setNuevoForm] = useState({ tipo_documento: 'DNI', nombres: '', tipo_comensal: 'Normal' });
    const [modalConf, setModalConf] = useState(false);

    const buscar = async (e) => {
        e.preventDefault();
        if (!docBusqueda) return;
        setCargandoDoc(true);
        setComensal(null);
        try {
            const res = await api.buscarComensal(docBusqueda);
            if (res.ok) {
                const c = await res.json();
                setComensal(c);
                setTipoVenta(c.tipo_comensal);
            } else {
                setComensal({ isNew: true });
            }
        } catch (e) {
            console.error('Error buscando comensal:', e);
            setComensal({ isNew: true });
        } finally {
            setCargandoDoc(false);
        }
    };

    const registrarNuevo = async (e) => {
        e.preventDefault();
        const payload = {
            ...nuevoForm,
            documento_identidad: docBusqueda
        };
        const res = await api.registrarComensal(payload);
        if (res.ok) {
            const c = await res.json();
            setComensal(c);
            setTipoVenta(c.tipo_comensal);
        } else {
            const errorData = await res.json();
            alert('Error al registrar: ' + (errorData.detail || 'Error desconocido'));
        }
    };

    const confirmarVenta = async () => {
        setModalConf(false);
        // Lógica de precios dinámica
        const precio = tipoVenta === 'Social'
            ? precioSocial
            : tipoVenta === 'Afiliado'
                ? precioAfiliado
                : precioNormal;

        await api.registrarVenta({
            comensal_id: comensal.id,
            raciones,
            monto_pagado: precio * raciones,
            tipo_menu: "Almuerzo regular",
            tipo_comensal_venta: tipoVenta,
            observacion: obs
        });
        
        setDocBusqueda('');
        setComensal(null);
        setRaciones(1);
        setObs('');
        onVentaRegistrada();
    };

    const intentarVenta = () => {
        // Umbral de alerta dinámico
        if (raciones > alertaRaciones) {
            setModalConf(true);
        } else {
            confirmarVenta();
        }
    };

    const calcularTotal = () => {
        const p = tipoVenta === 'Social' ? precioSocial : tipoVenta === 'Afiliado' ? precioAfiliado : precioNormal;
        return (p * raciones).toFixed(2);
    };

    return (
        <>
            <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200 shadow-inner h-fit">
                <h3 className="font-bold text-lg text-slate-800 mb-4 flex items-center gap-2">
                    <UserCheck size={20} className="text-blue-600" />
                    Atender en Ventanilla
                </h3>

                <form onSubmit={buscar} className="flex gap-2 mb-6">
                    <div className="relative flex-1">
                        <Search className="absolute left-3 top-2.5 text-slate-400" size={20} />
                        <input
                            type="text"
                            placeholder="DNI o Carné Ext."
                            value={docBusqueda}
                            onChange={e => setDocBusqueda(e.target.value.replace(/[^a-zA-Z0-9]/g, '').slice(0, 15))}
                            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={cargandoDoc || docBusqueda.length < 8}
                        className="bg-slate-800 text-white px-6 py-2 rounded-lg font-bold disabled:opacity-50"
                    >
                        {cargandoDoc ? <Loader2 className="animate-spin" /> : 'Buscar'}
                    </button>
                </form>

                {/* Comensal encontrado */}
                {comensal && !comensal.isNew && (
                    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
                        <div className="pb-4 border-b">
                            <p className="text-xs font-bold text-slate-400 uppercase">Comensal</p>
                            <p className="text-lg font-bold">{comensal.nombres}</p>
                            <p className="text-sm text-slate-500">
                                Tipo BD: <span className="font-medium text-slate-700">{comensal.tipo_comensal}</span>
                            </p>
                        </div>
                        <div>
                            <label className="block text-sm font-semibold text-slate-600 mb-1">Aplicar Venta como:</label>
                            <select
                                value={tipoVenta}
                                onChange={e => setTipoVenta(e.target.value)}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none bg-slate-50 font-medium"
                            >
                                <option value="Social">Social (S/ {precioSocial.toFixed(2)})</option>
                                <option value="Afiliado">Afiliado (S/ {precioAfiliado.toFixed(2)})</option>
                                <option value="Normal">Normal (S/ {precioNormal.toFixed(2)})</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-semibold text-slate-600 mb-1">Observación:</label>
                            <input
                                type="text"
                                value={obs}
                                onChange={e => setObs(e.target.value)}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg outline-none text-sm"
                            />
                        </div>
                        <div className="flex items-center gap-4 bg-slate-50 p-4 rounded-lg border">
                            <div className="flex-1">
                                <label className="block text-sm font-semibold text-slate-600 mb-1">Raciones</label>
                                <div className="flex items-center gap-3">
                                    <button type="button" onClick={() => setRaciones(Math.max(1, raciones - 1))} className="w-8 h-8 rounded bg-white border font-bold">-</button>
                                    <span className="text-xl font-black w-8 text-center">{raciones}</span>
                                    <button type="button" onClick={() => setRaciones(raciones + 1)} className="w-8 h-8 rounded bg-white border font-bold">+</button>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-xs font-bold text-slate-400 uppercase">Total</p>
                                <p className="text-2xl font-black text-emerald-600">S/ {calcularTotal()}</p>
                            </div>
                        </div>
                        <button onClick={intentarVenta} className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg">
                            Confirmar Venta
                        </button>
                    </div>
                )}

                {/* Comensal no encontrado - formulario de registro */}
                {comensal?.isNew && (
                    <form onSubmit={registrarNuevo} className="bg-white p-5 rounded-xl border border-blue-200 shadow-sm space-y-3">
                        <h4 className="font-bold">Nuevo Comensal</h4>
                        <p className="text-xs text-slate-500">El documento no existe. Regístrelo.</p>
                        <div className="flex gap-3">
                            <div className="w-1/3">
                                <label className="block text-xs font-bold mb-1">Tipo</label>
                                <select value={nuevoForm.tipo_documento} onChange={e => setNuevoForm({ ...nuevoForm, tipo_documento: e.target.value })} className="w-full px-3 py-2 border rounded-md text-sm">
                                    <option value="DNI">DNI</option>
                                    <option value="CE">C.E.</option>
                                </select>
                            </div>
                            <div className="w-2/3">
                                <label className="block text-xs font-bold mb-1">Nombres</label>
                                <input type="text" required value={nuevoForm.nombres} onChange={e => setNuevoForm({ ...nuevoForm, nombres: e.target.value })} className="w-full px-3 py-2 border rounded-md text-sm" />
                            </div>
                        </div>
                        <div>
                            <label className="block text-xs font-bold mb-1">Tipo de Comensal</label>
                            <select value={nuevoForm.tipo_comensal} onChange={e => setNuevoForm({ ...nuevoForm, tipo_comensal: e.target.value })} className="w-full px-3 py-2 border rounded-md text-sm">
                                <option value="Social">Social</option>
                                <option value="Afiliado">Afiliado</option>
                                <option value="Normal">Normal</option>
                            </select>
                        </div>
                        <button type="submit" className="w-full bg-slate-800 text-white font-bold py-2.5 rounded-lg mt-2">
                            Registrar y Continuar
                        </button>
                    </form>
                )}
            </div>
            
            <ModalConfirmacion
                isOpen={modalConf}
                onClose={() => setModalConf(false)}
                onConfirm={confirmarVenta}
                mensaje={`Estás a punto de vender ${raciones} raciones a ${comensal?.nombres}. ¿Continuar?`}
            />
        </>
    );
};