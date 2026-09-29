/**
 * components/auth/ModalCambioClave.jsx
 * Objetivo: Modal de cambio de contraseña obligatorio (COM-19) cuando la clave está
 *           expirada (6 meses) o es provisoria. Muestra checklist en vivo de la política:
 *           8-12 caracteres, letras+números, sin contener el DNI y confirmación coincidente.
 * Uso: Renderizado por App.jsx cuando pendienteCambio es TRUE. Bloquea el uso del
 *      sistema hasta cambiar la clave o cerrar sesión.
 */
import React, { useState } from 'react';
import { KeyRound, CheckCircle, XCircle, Loader2, LogOut, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';
import { ModalExito } from '../common/ModalExito';

export const ModalCambioClave = ({ usuario, onExito, onSalir }) => {
    // Campos del formulario de cambio
    const [claveActual, setClaveActual] = useState('');
    const [claveNueva, setClaveNueva] = useState('');
    const [confirmar, setConfirmar] = useState('');

    // Estados de feedback y carga
    const [error, setError] = useState('');
    const [cargando, setCargando] = useState(false);
    const [exito, setExito] = useState(false);

    // Documento del usuario en sesión (para la regla "no contener el DNI")
    const doc = usuario?.documento_identidad || '';

    // Checklist en vivo de la política de contraseñas (COM-19)
    const reglas = [
        { ok: claveNueva.length >= 8 && claveNueva.length <= 12, texto: 'Entre 8 y 12 caracteres' },
        { ok: /[A-Za-z]/.test(claveNueva) && /\d/.test(claveNueva), texto: 'Contiene letras y números' },
        { ok: claveNueva.length > 0 && doc !== '' && !claveNueva.includes(doc), texto: 'No contiene su documento' },
        { ok: confirmar !== '' && confirmar === claveNueva, texto: 'Las contraseñas coinciden' }
    ];
    const todasOk = reglas.every(r => r.ok);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        // Validación de campos en blanco (requisito COM-19)
        if (!claveActual.trim() || !claveNueva.trim() || !confirmar.trim()) {
            setError('Debe ingresar todos los campos, no pueden enviarse en blanco.');
            return;
        }
        // Validación de política en cliente (el backend re-valida como fuente de verdad)
        if (!todasOk) {
            setError('La contraseña nueva no cumple la política de seguridad.');
            return;
        }

        setCargando(true);
        try {
            const { ok, data } = await api.cambiarClave({
                tipo_documento: usuario.tipo_documento,
                documento_identidad: usuario.documento_identidad,
                clave_actual: claveActual,
                clave_nueva: claveNueva
            });
            if (ok) {
                // Mostrar modal de éxito con el diseño de la web
                setExito(true);
            } else {
                // El backend devuelve detail como {mensaje, tipo} o como string
                const detail = data.detail;
                setError((typeof detail === 'object' && detail !== null) ? detail.mensaje : (detail || 'Error al cambiar la contraseña.'));
            }
        } catch (err) {
            console.error('Error cambiando contraseña:', err);
            setError('Error de conexión con el servidor.');
        } finally {
            setCargando(false);
        }
    };

    // Al aceptar el modal de éxito, notificar al padre para desbloquear el sistema
    const cerrarExito = () => {
        setExito(false);
        onExito();
    };

    return (
        <>
            {/* Modal bloqueante: sin botón X, sin cierre por click fuera (COM-19) */}
            <div className="fixed inset-0 z-[75] flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-sm">
                <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden max-h-[90vh] flex flex-col">
                    
                    {/* Encabezado con identidad del sistema */}
                    <div className="bg-gradient-to-r from-emerald-700 to-emerald-800 p-5 text-white">
                        <div className="flex items-center gap-3">
                            <div className="bg-white/20 p-2 rounded-lg">
                                <KeyRound size={24} />
                            </div>
                            <div>
                                <h3 className="font-bold text-lg">Cambio de Contraseña Obligatorio</h3>
                                <p className="text-emerald-100 text-xs">
                                    Su contraseña ha expirado o es provisoria. Debe actualizarla para continuar.
                                </p>
                            </div>
                        </div>
                        <p className="text-emerald-100 text-xs mt-2 bg-white/10 px-3 py-2 rounded-lg">
                            Usuario: <span className="font-semibold">{usuario?.nombres} {usuario?.apellido_paterno}</span> · {usuario?.tipo_documento} {usuario?.documento_identidad}
                        </p>
                    </div>

                    {/* Cuerpo scrolleable */}
                    <form onSubmit={handleSubmit} className="p-5 space-y-4 overflow-y-auto">
                        
                        {/* Mensaje de error */}
                        {error && (
                            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-start gap-2">
                                <AlertCircle size={18} className="shrink-0 mt-0.5" />
                                <p className="text-sm font-medium">{error}</p>
                            </div>
                        )}

                        {/* Clave actual */}
                        <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-1">
                                Contraseña Actual *
                            </label>
                            <input
                                type="password"
                                value={claveActual}
                                onChange={(e) => setClaveActual(e.target.value)}
                                placeholder="Ingrese su contraseña actual"
                                className="w-full px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                                autoComplete="current-password"
                            />
                        </div>

                        {/* Clave nueva */}
                        <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-1">
                                Nueva Contraseña *
                            </label>
                            <input
                                type="password"
                                value={claveNueva}
                                onChange={(e) => setClaveNueva(e.target.value)}
                                placeholder="Entre 8 y 12 caracteres, letras y números"
                                className="w-full px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                                autoComplete="new-password"
                            />
                        </div>

                        {/* Confirmación de clave nueva */}
                        <div>
                            <label className="block text-sm font-semibold text-slate-700 mb-1">
                                Confirmar Nueva Contraseña *
                            </label>
                            <input
                                type="password"
                                value={confirmar}
                                onChange={(e) => setConfirmar(e.target.value)}
                                placeholder="Repita la nueva contraseña"
                                className="w-full px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                                autoComplete="new-password"
                            />
                        </div>

                        {/* Checklist en vivo de la política de contraseñas (COM-19) */}
                        <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                            <p className="text-xs font-bold text-slate-500 uppercase mb-2">
                                Política de Seguridad
                            </p>
                            <ul className="space-y-1.5">
                                {reglas.map((regla, idx) => (
                                    <li key={idx} className="flex items-center gap-2 text-sm">
                                        {regla.ok ? (
                                            <CheckCircle size={16} className="text-emerald-600 shrink-0" />
                                        ) : (
                                            <XCircle size={16} className="text-slate-400 shrink-0" />
                                        )}
                                        <span className={regla.ok ? 'text-slate-700' : 'text-slate-500'}>
                                            {regla.texto}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </div>

                        {/* Botones de acción */}
                        <div className="flex gap-2 pt-2">
                            <button
                                type="button"
                                onClick={onSalir}
                                disabled={cargando}
                                className="flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-lg transition-colors disabled:opacity-50 text-sm"
                            >
                                <LogOut size={16} />
                                Cerrar Sesión
                            </button>
                            <button
                                type="submit"
                                disabled={cargando || !todasOk}
                                className="flex-1 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                            >
                                {cargando ? (
                                    <>
                                        <Loader2 className="animate-spin" size={16} />
                                        Actualizando...
                                    </>
                                ) : (
                                    'Actualizar Contraseña'
                                )}
                            </button>
                        </div>
                    </form>
                </div>
            </div>

            {/* Modal de éxito (reutiliza ModalExito creado en COM-18) */}
            <ModalExito
                isOpen={exito}
                onClose={cerrarExito}
                mensaje="Su contraseña ha sido actualizada exitosamente. Ya puede continuar usando el sistema."
            />
        </>
    );
};