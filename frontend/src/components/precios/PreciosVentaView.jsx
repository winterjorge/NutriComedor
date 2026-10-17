/**
 * components/precios/PreciosVentaView.jsx
 * Objetivo: COM-59A: pestaña "Precios de Venta" (exclusiva del Admin de Sistemas):
 *           precios vigentes por tipo de comensal (Social/Afiliado/Normal) con política
 *           de precio único vigente hasta nuevo cambio, e historial completo de cambios
 *           para auditoría y rendición de cuentas.
 * Regla de negocio: un precio NO se edita ni se borra: se registra uno nuevo y el
 *           historial conserva la trazabilidad (estabilidad de precio para el comensal).
 * Historial:
 *  - COM-59A v1: versión original.
 *  - COM-59A v2 (este archivo): el historial se solicita con `usuario_solicitante_id`
 *    (params object) para alinearse al fix de seguridad del backend; si el api.js aún
 *    no incluye el parámetro, la vista degrada suave (banner de error) sin romper el
 *    resto del panel.
 * Uso: Montada por App.jsx en la pestaña "Precios de Venta" (módulo 'precios_venta').
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    Coins, Loader2, AlertCircle, RefreshCw, History, Users
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

const TIPOS = [
    { clave: 'Social', detalle: 'Comensal en situación de vulnerabilidad (subsidio total).' },
    { clave: 'Afiliado', detalle: 'Comensal afiliado al comedor con aporte parcial.' },
    { clave: 'Normal', detalle: 'Comensal ocasional sin afiliación.' },
];

export const PreciosVentaView = () => {
    const { usuario } = useAuth();

    const [vigentes, setVigentes] = useState(null);
    const [historial, setHistorial] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');

    // Formulario de nuevo precio
    const [tipoSel, setTipoSel] = useState('Normal');
    const [precioNuevo, setPrecioNuevo] = useState('');
    const [observacion, setObservacion] = useState('');
    const [confCambio, setConfCambio] = useState(null);   // payload pendiente de confirmación
    const [guardando, setGuardando] = useState(false);

    const cargar = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const vig = await api.getPreciosVentaVigentes();
            setVigentes(vig);
            // COM-59A v2: el historial exige identificar al solicitante (fix backend)
            try {
                const hist = await api.getHistorialPreciosVenta({ usuario_solicitante_id: usuario.id });
                setHistorial(hist || []);
            } catch (eHist) {
                // Degradación suave: sin historial el panel sigue operable
                setHistorial([]);
                setError(`Historial no disponible: ${eHist.message}`);
            }
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [usuario.id]);

    useEffect(() => { cargar(); }, [cargar]);

    const solicitarCambio = (e) => {
        e.preventDefault();
        const precio = Number(precioNuevo);
        if (precioNuevo === '' || isNaN(precio) || precio < 0) {
            setError('Ingrese un precio válido mayor o igual a cero.');
            return;
        }
        setError('');
        setConfCambio({ tipo_comensal: tipoSel, precio, observacion });
    };

    const confirmarCambio = async () => {
        const payload = confCambio;
        setConfCambio(null);
        setGuardando(true);
        setError('');
        try {
            const res = await api.registrarPrecioVenta({
                usuario_solicitante_id: usuario.id,
                tipo_comensal: payload.tipo_comensal,
                precio: payload.precio,
                observacion: payload.observacion || null,
            });
            setExito(res.message || 'Precio registrado.');
            setPrecioNuevo('');
            setObservacion('');
            cargar();
        } catch (e) {
            setError(e.message);
        } finally {
            setGuardando(false);
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
                        <Coins className="text-emerald-600" size={22} /> Precios de Venta
                    </h2>
                    <p className="text-sm text-slate-500">
                        Política de precio único vigente hasta nuevo cambio (estabilidad para el
                        comensal). Todo cambio queda en el historial.
                    </p>
                </div>
                <button onClick={cargar} className="p-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-600" title="Recargar">
                    <RefreshCw size={14} className={cargando ? 'animate-spin' : ''} />
                </button>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {cargando ? (
                <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={26} /></div>
            ) : (
                <>
                    {/* Precios vigentes */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {TIPOS.map(t => (
                            <div key={t.clave} className="bg-white border border-slate-200 rounded-xl p-4">
                                <p className="text-xs font-semibold text-slate-500 flex items-center gap-1">
                                    <Users size={12} /> {t.clave}
                                </p>
                                <p className="text-3xl font-black text-emerald-700 mt-1">
                                    S/ {Number(vigentes?.[t.clave] ?? 0).toFixed(2)}
                                </p>
                                <p className="text-[11px] text-slate-400 mt-1">{t.detalle}</p>
                            </div>
                        ))}
                    </div>

                    {/* Formulario de cambio de precio */}
                    <div className="bg-white border border-slate-200 rounded-xl p-5">
                        <h3 className="font-bold text-slate-800 text-sm mb-3">Registrar nuevo precio vigente</h3>
                        <form onSubmit={solicitarCambio} className="grid grid-cols-1 md:grid-cols-4 gap-3">
                            <div>
                                <label className={labelCls}>Tipo de comensal</label>
                                <select value={tipoSel} onChange={(e) => setTipoSel(e.target.value)} className={inputCls}>
                                    {TIPOS.map(t => <option key={t.clave} value={t.clave}>{t.clave}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className={labelCls}>Nuevo precio (S/)</label>
                                <input type="number" min="0" step="0.10" value={precioNuevo}
                                    onChange={(e) => setPrecioNuevo(e.target.value)}
                                    className={inputCls} placeholder="Ej: 5.00" required />
                            </div>
                            <div className="md:col-span-2">
                                <label className={labelCls}>Motivo / observación</label>
                                <input type="text" value={observacion}
                                    onChange={(e) => setObservacion(e.target.value)}
                                    className={inputCls} placeholder="Ej: ajuste por alza generalizada de insumos" />
                            </div>
                            <div className="md:col-span-4 flex justify-end">
                                <button type="submit"
                                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors">
                                    Proponer cambio
                                </button>
                            </div>
                        </form>
                    </div>

                    {/* Historial */}
                    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                        <div className="px-5 py-3 border-b border-slate-200 flex items-center gap-2">
                            <History size={15} className="text-slate-500" />
                            <h3 className="font-bold text-slate-800 text-sm">Historial de cambios</h3>
                        </div>
                        {historial.length === 0 ? (
                            <p className="p-6 text-center text-sm text-slate-400">Sin cambios registrados aún.</p>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                                    <thead>
                                        <tr className="bg-slate-100 text-slate-600">
                                            <th className="p-3 font-semibold">Tipo</th>
                                            <th className="p-3 font-semibold text-right">Precio</th>
                                            <th className="p-3 font-semibold">Vigente desde</th>
                                            <th className="p-3 font-semibold">Registrado por</th>
                                            <th className="p-3 font-semibold">Observación</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-200">
                                        {historial.map(h => (
                                            <tr key={h.id} className="hover:bg-slate-50">
                                                <td className="p-3 font-medium text-slate-800">{h.tipo_comensal}</td>
                                                <td className="p-3 text-right text-emerald-700 font-bold">S/ {Number(h.precio).toFixed(2)}</td>
                                                <td className="p-3 text-slate-600 text-xs">{String(h.vigente_desde || '').replace('T', ' ').slice(0, 16)}</td>
                                                <td className="p-3 text-slate-600 text-xs">{h.creado_por_nombre || '—'}</td>
                                                <td className="p-3 text-slate-500 text-xs">{h.observacion || '—'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                </>
            )}

            <ModalConfirmacion
                isOpen={!!confCambio}
                onClose={() => setConfCambio(null)}
                onConfirm={confirmarCambio}
                mensaje={confCambio
                    ? `¿Confirmar el nuevo precio ${confCambio.tipo_comensal} = S/ ${confCambio.precio.toFixed(2)}? El precio anterior quedará en el historial y el nuevo rige de inmediato para el POS, las propuestas y los reportes.`
                    : ''}
                tipo="warning"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};