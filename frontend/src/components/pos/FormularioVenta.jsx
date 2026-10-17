/**
 * components/pos/FormularioVenta.jsx
 * Objetivo: COM-62 v2 + COM-63: atención ágil en ventanilla con tipo "Cocinera".
 * Flujo:
 *   1) Caja de NOMBRE con autocompletado (busca por nombre, excluye al Cliente Genérico).
 *   2) Al seleccionar una ficha: se usa para la venta. Si NO tiene DNI real, se muestra
 *      badge "Sin DNI" + botón "Completar DNI" (mini-modal para editar la ficha).
 *   3) Si no hay coincidencia: "Registrar sin DNI" (crea ficha con DNI 00000000 y ese
 *      nombre, reutilizable la próxima vez) o "Registrar con DNI" (formulario completo).
 *   4) El Cliente Genérico (es_generico=TRUE) NO aparece en el autocompletado: es reserva
 *      para cargas masivas históricas (no se usa en el POS diario).
 *   5) COM-63: tipo "Cocinera" con precio 0.00.
 * Historial:
 *  - Sprint 1/2: versión original (búsqueda por DNI obligatorio).
 *  - COM-62 v2: identidad por nombre, DNI opcional, completado posterior.
 *  - COM-63: tipo "Cocinera" agregado.
 * Uso: Montado por POSView.jsx en la columna izquierda del POS.
 */
import React, { useState, useEffect, useRef } from 'react';
import { UserCheck, Search, Loader2, Edit3, UserPlus, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { useParametros } from '../../context/ParametrosContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';

const DNI_SIN_DATO = '00000000';
const TIPOS_COMENSAL = ['Social', 'Afiliado', 'Normal', 'Cocinera'];

export const FormularioVenta = ({ onVentaRegistrada }) => {
    const { parametros } = useParametros();
    const precioSocial = parametros?.PRECIO_SOCIAL ?? 0;
    const precioAfiliado = parametros?.PRECIO_AFILIADO ?? 3;
    const precioNormal = parametros?.PRECIO_NORMAL ?? 5;
    const precioCocinera = parametros?.PRECIO_COCINERA ?? 0;
    const alertaRaciones = parametros?.ALERTA_RACIONES_MAX || 3;

    // Autocompletado por nombre
    const [nombreBusqueda, setNombreBusqueda] = useState('');
    const [sugerencias, setSugerencias] = useState([]);
    const [cargandoNombre, setCargandoNombre] = useState(false);
    const [mostrarSugerencias, setMostrarSugerencias] = useState(false);
    const debounceRef = useRef(null);

    // Comensal seleccionado para la venta
    const [comensal, setComensal] = useState(null);

    // Formulario de venta
    const [tipoVenta, setTipoVenta] = useState('Normal');
    const [raciones, setRaciones] = useState(1);
    const [obs, setObs] = useState('');

    // Mini-modal: completar DNI de una ficha "sin DNI"
    const [modalDni, setModalDni] = useState(null);   // { comensal }
    const [nuevoDni, setNuevoDni] = useState('');
    const [guardandoDni, setGuardandoDni] = useState(false);
    const [errorDni, setErrorDni] = useState('');

    // Formulario de registro completo (con DNI)
    const [modalRegistro, setModalRegistro] = useState(false);
    const [formRegistro, setFormRegistro] = useState({
        tipo_documento: 'DNI', documento_identidad: '', nombres: '', tipo_comensal: 'Normal'
    });
    const [registrando, setRegistrando] = useState(false);
    const [errorRegistro, setErrorRegistro] = useState('');

    // Error de venta (banner visible)
    const [errorVenta, setErrorVenta] = useState('');

    // Confirmación de venta con muchas raciones
    const [modalConf, setModalConf] = useState(false);

    // ---------- Autocompletado por nombre ----------
    useEffect(() => {
        clearTimeout(debounceRef.current);
        const q = nombreBusqueda.trim();
        if (q.length < 2) { setSugerencias([]); setMostrarSugerencias(false); return; }
        debounceRef.current = setTimeout(async () => {
            setCargandoNombre(true);
            try {
                const lista = await api.buscarComensalesPorNombre(q, 8);
                setSugerencias(lista || []);
                setMostrarSugerencias(true);
            } catch (e) {
                setSugerencias([]);
            } finally {
                setCargandoNombre(false);
            }
        }, 250);
        return () => clearTimeout(debounceRef.current);
    }, [nombreBusqueda]);

    const seleccionarSugerencia = (c) => {
        setComensal(c);
        setTipoVenta(c.tipo_comensal || 'Normal');
        setNombreBusqueda(c.nombres);
        setSugerencias([]);
        setMostrarSugerencias(false);
        setErrorVenta('');
    };

    // ---------- Registro sin DNI (crea ficha con DNI 00000000, reutilizable) ----------
    const registrarSinDni = async () => {
        const nombres = nombreBusqueda.trim();
        if (nombres.length < 2) return;
        setRegistrando(true);
        setErrorRegistro('');
        setErrorVenta('');
        try {
            const res = await api.registrarComensal({
                tipo_documento: 'DNI',
                documento_identidad: '',   // backend lo normaliza a '00000000'
                nombres,
                tipo_comensal: 'Normal',
            });
            setComensal(res);
            setTipoVenta(res.tipo_comensal || 'Normal');
            setSugerencias([]);
            setMostrarSugerencias(false);
        } catch (e) {
            setErrorRegistro(e.message);
        } finally {
            setRegistrando(false);
        }
    };

    // ---------- Registro con DNI (formulario completo) ----------
    const registrarConDni = async (e) => {
        e.preventDefault();
        setErrorRegistro('');
        setErrorVenta('');
        if (!formRegistro.documento_identidad.trim() || !formRegistro.nombres.trim()) {
            setErrorRegistro('Documento y nombres son obligatorios.');
            return;
        }
        setRegistrando(true);
        try {
            const res = await api.registrarComensal({
                tipo_documento: formRegistro.tipo_documento,
                documento_identidad: formRegistro.documento_identidad.trim(),
                nombres: formRegistro.nombres.trim(),
                tipo_comensal: formRegistro.tipo_comensal,
            });
            setComensal(res);
            setTipoVenta(res.tipo_comensal || 'Normal');
            setModalRegistro(false);
            setFormRegistro({ tipo_documento: 'DNI', documento_identidad: '', nombres: '', tipo_comensal: 'Normal' });
            setNombreBusqueda(res.nombres);
        } catch (e) {
            setErrorRegistro(e.message);
        } finally {
            setRegistrando(false);
        }
    };

    // ---------- Completar DNI de una ficha "sin DNI" ----------
    const abrirModalDni = () => {
        setNuevoDni('');
        setErrorDni('');
        setModalDni({ comensal });
    };
    const guardarDni = async () => {
        const dni = nuevoDni.trim();
        if (!/^\d{8}$/.test(dni)) {
            setErrorDni('El DNI debe tener exactamente 8 dígitos.');
            return;
        }
        setGuardandoDni(true);
        setErrorDni('');
        try {
            const actualizado = await api.editarComensal(modalDni.comensal.id, {
                documento_identidad: dni,
            });
            setComensal(actualizado);
            setModalDni(null);
        } catch (e) {
            setErrorDni(e.message);
        } finally {
            setGuardandoDni(false);
        }
    };

    // ---------- Venta ----------
    const confirmarVenta = async () => {
        setModalConf(false);
        setErrorVenta('');
        // Validación defensiva: comensal.id debe existir
        if (!comensal || !comensal.id) {
            setErrorVenta('No hay comensal seleccionado. Busque o registre un comensal primero.');
            return;
        }
        const precio = tipoVenta === 'Social' ? precioSocial 
            : tipoVenta === 'Afiliado' ? precioAfiliado 
            : tipoVenta === 'Cocinera' ? precioCocinera
            : precioNormal;
        try {
            await api.registrarVenta({
                comensal_id: comensal.id,
                raciones,
                monto_pagado: precio * raciones,
                tipo_menu: 'Almuerzo regular',
                tipo_comensal_venta: tipoVenta,
                observacion: obs,
            });
            setNombreBusqueda('');
            setComensal(null);
            setRaciones(1);
            setObs('');
            setSugerencias([]);
            onVentaRegistrada();
        } catch (e) {
            setErrorVenta(e.message);
        }
    };

    const intentarVenta = () => {
        if (!comensal) return;
        if (raciones > alertaRaciones) setModalConf(true);
        else confirmarVenta();
    };

    const calcularTotal = () => {
        const p = tipoVenta === 'Social' ? precioSocial 
            : tipoVenta === 'Afiliado' ? precioAfiliado 
            : tipoVenta === 'Cocinera' ? precioCocinera
            : precioNormal;
        return (p * raciones).toFixed(2);
    };

    const tieneDniReal = comensal && comensal.documento_identidad && comensal.documento_identidad !== DNI_SIN_DATO;
    const esSinDni = comensal && comensal.documento_identidad === DNI_SIN_DATO && !comensal.es_generico;

    const inputCls = "w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500";

    return (
        <>
            <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200 shadow-inner h-fit">
                <h3 className="font-bold text-lg text-slate-800 mb-4 flex items-center gap-2">
                    <UserCheck size={20} className="text-blue-600" />
                    Atender en Ventanilla
                </h3>

                {/* Banner de error de venta (fix COM-62 v2) */}
                {errorVenta && (
                    <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                        <AlertCircle size={16} /> {errorVenta}
                    </div>
                )}

                {/* Caja de nombre con autocompletado */}
                <div className="relative mb-6">
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                        Nombre del comensal (escribe para buscar)
                    </label>
                    <div className="relative">
                        <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
                        <input
                            type="text"
                            value={nombreBusqueda}
                            onChange={(e) => setNombreBusqueda(e.target.value)}
                            onFocus={() => sugerencias.length > 0 && setMostrarSugerencias(true)}
                            onBlur={() => setTimeout(() => setMostrarSugerencias(false), 150)}
                            placeholder="Ej: María Quispe"
                            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500"
                        />
                        {cargandoNombre && <Loader2 className="absolute right-3 top-2.5 animate-spin text-slate-400" size={18} />}
                    </div>

                    {/* Lista de sugerencias */}
                    {mostrarSugerencias && sugerencias.length > 0 && (
                        <div className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                            {sugerencias.map(s => (
                                <button
                                    key={s.id}
                                    type="button"
                                    onMouseDown={(e) => { e.preventDefault(); seleccionarSugerencia(s); }}
                                    className="w-full text-left px-3 py-2 hover:bg-emerald-50 border-b border-slate-100 last:border-0"
                                >
                                    <p className="text-sm font-medium text-slate-800">{s.nombres}</p>
                                    <p className="text-[11px] text-slate-500">
                                        {s.tipo_comensal}
                                        {s.tiene_dni ? ` · DNI ${s.documento_identidad}` : ' · Sin DNI'}
                                    </p>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                {/* Acciones rápidas cuando NO hay comensal seleccionado */}
                {!comensal && (
                    <div className="space-y-2 mb-4">
                        <button
                            onClick={registrarSinDni}
                            disabled={nombreBusqueda.trim().length < 2 || registrando}
                            className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
                        >
                            <UserPlus size={16} />
                            {registrando ? 'Registrando...' : 'Registrar sin DNI (atender rápido)'}
                        </button>
                        <button
                            onClick={() => { setModalRegistro(true); setErrorRegistro(''); }}
                            className="w-full flex items-center justify-center gap-2 bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 py-2 rounded-lg text-sm font-medium transition-colors"
                        >
                            <UserPlus size={16} /> Registrar con DNI
                        </button>
                        {errorRegistro && (
                            <p className="text-xs text-red-600 flex items-center gap-1">
                                <AlertCircle size={12} /> {errorRegistro}
                            </p>
                        )}
                    </div>
                )}

                {/* Ficha de comensal seleccionada */}
                {comensal && (
                    <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
                        <div className="pb-4 border-b">
                            <p className="text-xs font-bold text-slate-400 uppercase">Comensal</p>
                            <p className="text-lg font-bold">{comensal.nombres}</p>
                            <div className="flex items-center gap-2 mt-1 flex-wrap">
                                <span className="text-sm text-slate-500">
                                    Tipo: <span className="font-medium text-slate-700">{comensal.tipo_comensal}</span>
                                </span>
                                {tieneDniReal && (
                                    <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">
                                        DNI {comensal.documento_identidad}
                                    </span>
                                )}
                                {esSinDni && (
                                    <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-bold flex items-center gap-1">
                                        Sin DNI
                                        <button onClick={abrirModalDni} className="underline hover:text-amber-900" title="Completar DNI">
                                            <Edit3 size={11} />
                                        </button>
                                    </span>
                                )}
                                {comensal.es_generico && (
                                    <span className="text-xs bg-slate-200 text-slate-600 px-2 py-0.5 rounded-full font-bold">
                                        Cliente Genérico
                                    </span>
                                )}
                            </div>
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
                                <option value="Cocinera">Cocinera (S/ {precioCocinera.toFixed(2)})</option>
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

                        <div className="flex gap-2">
                            <button
                                onClick={() => { setComensal(null); setNombreBusqueda(''); setSugerencias([]); setErrorVenta(''); }}
                                className="flex-1 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold py-3 rounded-lg text-sm"
                            >
                                Cambiar comensal
                            </button>
                            <button onClick={intentarVenta} className="flex-[2] bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-lg">
                                Confirmar Venta
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {/* Mini-modal: completar DNI */}
            {modalDni && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm overflow-hidden">
                        <div className="bg-amber-600 text-white p-4">
                            <p className="font-bold text-sm flex items-center gap-2">
                                <Edit3 size={16} /> Completar DNI de {modalDni.comensal.nombres}
                            </p>
                        </div>
                        <div className="p-4 space-y-3">
                            {errorDni && (
                                <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs flex items-center gap-1">
                                    <AlertCircle size={12} /> {errorDni}
                                </div>
                            )}
                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">DNI (8 dígitos)</label>
                                <input
                                    type="text"
                                    value={nuevoDni}
                                    onChange={(e) => setNuevoDni(e.target.value.replace(/\D/g, '').slice(0, 8))}
                                    className={inputCls}
                                    placeholder="Ej: 70000001"
                                    autoFocus
                                />
                                <p className="text-[11px] text-slate-500 mt-1">
                                    Si algún día el comedor decide pedir DNI, puedes completarlo ahora. La ficha se actualizará y las ventas históricas quedan vinculadas.
                                </p>
                            </div>
                            <div className="flex gap-2">
                                <button onClick={() => setModalDni(null)} className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium">
                                    Cancelar
                                </button>
                                <button onClick={guardarDni} disabled={guardandoDni} className="flex-1 px-3 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                                    {guardandoDni ? 'Guardando...' : 'Guardar DNI'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Modal: registro completo con DNI */}
            {modalRegistro && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden">
                        <div className="bg-emerald-700 text-white p-4">
                            <p className="font-bold text-sm flex items-center gap-2">
                                <UserPlus size={16} /> Registrar comensal con DNI
                            </p>
                        </div>
                        <form onSubmit={registrarConDni} className="p-4 space-y-3">
                            {errorRegistro && (
                                <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs flex items-center gap-1">
                                    <AlertCircle size={12} /> {errorRegistro}
                                </div>
                            )}
                            <div className="grid grid-cols-3 gap-2">
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Tipo</label>
                                    <select value={formRegistro.tipo_documento} onChange={(e) => setFormRegistro({ ...formRegistro, tipo_documento: e.target.value })} className={inputCls}>
                                        <option value="DNI">DNI</option>
                                        <option value="CE">C.E.</option>
                                    </select>
                                </div>
                                <div className="col-span-2">
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Documento *</label>
                                    <input type="text" value={formRegistro.documento_identidad} onChange={(e) => setFormRegistro({ ...formRegistro, documento_identidad: e.target.value.replace(/[^0-9A-Za-z]/g, '').slice(0, 15) })} className={inputCls} required />
                                </div>
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Nombres *</label>
                                <input type="text" value={formRegistro.nombres} onChange={(e) => setFormRegistro({ ...formRegistro, nombres: e.target.value })} className={inputCls} required />
                            </div>
                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Tipo de comensal</label>
                                <select value={formRegistro.tipo_comensal} onChange={(e) => setFormRegistro({ ...formRegistro, tipo_comensal: e.target.value })} className={inputCls}>
                                    {TIPOS_COMENSAL.map(t => <option key={t} value={t}>{t}</option>)}
                                </select>
                            </div>
                            <div className="flex gap-2 pt-1">
                                <button type="button" onClick={() => setModalRegistro(false)} className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium">
                                    Cancelar
                                </button>
                                <button type="submit" disabled={registrando} className="flex-1 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium disabled:opacity-50">
                                    {registrando ? 'Registrando...' : 'Registrar y atender'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            <ModalConfirmacion
                isOpen={modalConf}
                onClose={() => setModalConf(false)}
                onConfirm={confirmarVenta}
                mensaje={`Estás a punto de vender ${raciones} raciones a ${comensal?.nombres}. ¿Continuar?`}
            />
        </>
    );
};