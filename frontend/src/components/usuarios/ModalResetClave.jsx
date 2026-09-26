/**
 * components/usuarios/ModalResetClave.jsx
 * Objetivo: COM-38: modal de reseteo/cambio de contraseña ejecutado por el
 *           Administrador de Sistemas sobre cualquier usuario. Dos modos:
 *           (a) aleatorio: el sistema genera una clave temporal que se muestra UNA
 *               sola vez con botón de copiado; (b) específica: el admin escribe la
 *               nueva clave (validada contra la política en backend).
 *           En ambos modos se desbloquea la cuenta y, si "forzar cambio" queda activo,
 *           el usuario deberá cambiarla en su primer login (flujo COM-19).
 * Uso: Montado por GestionUsuariosSistemaView (el cableado del botón se entrega en la
 *      Parte 3 sobre el archivo vigente). Props: isOpen, onClose, usuarioObjetivo
 *      ({id, nombres, apellido_paterno, documento_identidad, rol}).
 * Referencia: ticket COM-38 (solo trazabilidad).
 */
import React, { useState, useEffect } from 'react';
import { X, KeyRound, RefreshCw, Copy, CheckCircle2, AlertCircle, Eye, EyeOff, Lock } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const ModalResetClave = ({ isOpen, onClose, usuarioObjetivo }) => {
    const { usuario } = useAuth();

    const [modo, setModo] = useState('random');          // 'random' | 'especifica'
    const [clave, setClave] = useState('');
    const [mostrarClave, setMostrarClave] = useState(false);
    const [forzarCambio, setForzarCambio] = useState(true);
    const [cargando, setCargando] = useState(false);
    const [error, setError] = useState('');
    const [resultado, setResultado] = useState(null);    // respuesta exitosa del backend
    const [copiado, setCopiado] = useState(false);

    // Reinicio de estado al abrir/cerrar o cambiar de usuario objetivo
    useEffect(() => {
        if (isOpen) {
            setModo('random');
            setClave('');
            setMostrarClave(false);
            setForzarCambio(true);
            setCargando(false);
            setError('');
            setResultado(null);
            setCopiado(false);
        }
    }, [isOpen, usuarioObjetivo?.id]);

    if (!isOpen || !usuarioObjetivo) return null;

    const confirmar = async () => {
        setCargando(true);
        setError('');
        try {
            const res = await api.resetearClaveUsuario(usuarioObjetivo.id, {
                usuario_solicitante_id: usuario.id,
                modo,
                clave_nueva: modo === 'especifica' ? clave : undefined,
                forzar_cambio: forzarCambio,
            });
            setResultado(res);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    };

    const copiar = async () => {
        try {
            await navigator.clipboard.writeText(resultado.clave_temporal || '');
            setCopiado(true);
            setTimeout(() => setCopiado(false), 2000);
        } catch (e) {
            setError('No se pudo copiar al portapapeles; anótela manualmente.');
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden animate-in zoom-in duration-200">
                {/* Encabezado */}
                <div className="bg-emerald-700 text-white p-4 flex items-center gap-2">
                    <KeyRound size={20} />
                    <div className="flex-1">
                        <p className="font-bold text-sm">Resetear contraseña (COM-38)</p>
                        <p className="text-[11px] text-emerald-100">
                            {usuarioObjetivo.nombres} {usuarioObjetivo.apellido_paterno} ·
                            DNI {usuarioObjetivo.documento_identidad} · {usuarioObjetivo.rol}
                        </p>
                    </div>
                    <button onClick={onClose} className="p-1 hover:bg-emerald-800 rounded transition-colors">
                        <X size={18} />
                    </button>
                </div>

                <div className="p-4 space-y-4">
                    {!resultado ? (
                        <>
                            {/* Selector de modo */}
                            <div className="grid grid-cols-2 gap-2">
                                <button
                                    onClick={() => setModo('random')}
                                    className={`p-3 rounded-xl border text-left transition-colors ${
                                        modo === 'random'
                                            ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-300'
                                            : 'border-slate-200 hover:bg-slate-50'}`}
                                >
                                    <p className="flex items-center gap-1 text-xs font-bold text-slate-800">
                                        <RefreshCw size={13} /> Clave aleatoria
                                    </p>
                                    <p className="text-[10px] text-slate-500 mt-1">
                                        El sistema genera una clave temporal y se muestra una sola vez.
                                    </p>
                                </button>
                                <button
                                    onClick={() => setModo('especifica')}
                                    className={`p-3 rounded-xl border text-left transition-colors ${
                                        modo === 'especifica'
                                            ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-300'
                                            : 'border-slate-200 hover:bg-slate-50'}`}
                                >
                                    <p className="flex items-center gap-1 text-xs font-bold text-slate-800">
                                        <Lock size={13} /> Clave específica
                                    </p>
                                    <p className="text-[10px] text-slate-500 mt-1">
                                        Usted define la nueva clave (se valida la política).
                                    </p>
                                </button>
                            </div>

                            {/* Clave específica */}
                            {modo === 'especifica' && (
                                <div>
                                    <label className="text-xs font-semibold text-slate-600 mb-1 block">
                                        Nueva contraseña
                                    </label>
                                    <div className="relative">
                                        <input
                                            type={mostrarClave ? 'text' : 'password'}
                                            value={clave}
                                            onChange={(e) => setClave(e.target.value)}
                                            placeholder="Mínimo 8 caracteres, mayúscula, minúscula y dígito"
                                            className="w-full px-3 py-2 pr-10 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                        />
                                        <button
                                            onClick={() => setMostrarClave(!mostrarClave)}
                                            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                            title={mostrarClave ? 'Ocultar' : 'Mostrar'}
                                        >
                                            {mostrarClave ? <EyeOff size={16} /> : <Eye size={16} />}
                                        </button>
                                    </div>
                                </div>
                            )}

                            {/* Forzar cambio */}
                            <label className="flex items-start gap-2 text-xs text-slate-600 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={forzarCambio}
                                    onChange={(e) => setForzarCambio(e.target.checked)}
                                    className="mt-0.5 accent-emerald-600"
                                />
                                <span>
                                    <b>Forzar cambio en el primer login</b> (recomendado). Si lo desactiva,
                                    la clave quedará definitiva hasta su expiración por política.
                                </span>
                            </label>

                            {error && (
                                <div className="p-2.5 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-xs">
                                    <AlertCircle size={14} /> {error}
                                </div>
                            )}

                            {/* Acciones */}
                            <div className="flex gap-2">
                                <button
                                    onClick={onClose}
                                    className="flex-1 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-medium transition-colors"
                                >
                                    Cancelar
                                </button>
                                <button
                                    onClick={confirmar}
                                    disabled={cargando || (modo === 'especifica' && !clave)}
                                    className="flex-1 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                                >
                                    {cargando ? 'Aplicando...' : 'Confirmar reseteo'}
                                </button>
                            </div>
                        </>
                    ) : (
                        <>
                            {/* Éxito */}
                            <div className="text-center space-y-3">
                                <CheckCircle2 size={40} className="text-emerald-600 mx-auto" />
                                <p className="text-sm font-bold text-slate-800">Contraseña restablecida</p>
                                <p className="text-xs text-slate-500">
                                    La cuenta quedó desbloqueada.
                                    {resultado.debe_cambiar_al_login
                                        ? ' El usuario deberá cambiarla en su primer ingreso.'
                                        : ' La clave queda definitiva según política.'}
                                </p>

                                {resultado.clave_temporal && (
                                    <div className="bg-amber-50 border border-amber-300 rounded-xl p-3">
                                        <p className="text-[11px] font-semibold text-amber-800 mb-1">
                                            Clave temporal (se muestra UNA sola vez):
                                        </p>
                                        <div className="flex items-center gap-2">
                                            <code className="flex-1 text-lg font-mono font-bold text-amber-900 tracking-wider">
                                                {resultado.clave_temporal}
                                            </code>
                                            <button
                                                onClick={copiar}
                                                className="p-2 bg-amber-200 hover:bg-amber-300 text-amber-900 rounded-lg transition-colors"
                                                title="Copiar"
                                            >
                                                {copiado ? <CheckCircle2 size={16} /> : <Copy size={16} />}
                                            </button>
                                        </div>
                                        <p className="text-[10px] text-amber-700 mt-2">
                                            Comuníquela por un canal seguro; no volverá a mostrarse.
                                        </p>
                                    </div>
                                )}

                                <button
                                    onClick={onClose}
                                    className="w-full px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors"
                                >
                                    Cerrar
                                </button>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};