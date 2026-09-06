/**
 * components/auth/LoginView.jsx
 * Objetivo: Pantalla de inicio de sesión (COM-19) por tipo de documento (DNI por defecto)
 *           + contraseña. Valida campos en blanco, muestra errores (rojo) y avisos de
 *           bloqueo inminente (ámbar).
 * Uso: Renderizado por App.jsx cuando no existe sesión activa (useAuth).
 */
import React, { useState } from 'react';
import { Activity, User, Lock, Eye, EyeOff, AlertCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export const LoginView = () => {
    const { iniciarSesion } = useAuth();

    // Datos del formulario de acceso
    const [tipoDocumento, setTipoDocumento] = useState('DNI');
    const [documento, setDocumento] = useState('');
    const [clave, setClave] = useState('');
    const [verClave, setVerClave] = useState(false);

    // Mensajes de feedback: error (caja roja) y aviso (caja ámbar)
    const [error, setError] = useState('');
    const [aviso, setAviso] = useState('');
    const [cargando, setCargando] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setAviso('');

        // Validación de campos en blanco (requisito COM-19)
        if (!documento.trim()) {
            setError('Debe ingresar el usuario, no puede enviarse en blanco.');
            return;
        }
        if (!clave.trim()) {
            setError('Debe ingresar la contraseña, no puede enviarse en blanco.');
            return;
        }

        setCargando(true);
        try {
            const { ok, data } = await api.login({
                tipo_documento: tipoDocumento,
                documento_identidad: documento.trim(),
                clave
            });
            if (ok) {
                // Login exitoso (si requiere_cambio_clave, App mostrará el modal de cambio)
                iniciarSesion(data);
            } else {
                // El backend devuelve detail como {mensaje, tipo} o como string
                const detail = data.detail;
                const mensaje = (typeof detail === 'object' && detail !== null) ? detail.mensaje : (detail || 'Error al iniciar sesión.');
                const tipo = (typeof detail === 'object' && detail !== null) ? detail.tipo : 'error';
                if (tipo === 'aviso') {
                    setAviso(mensaje);
                } else {
                    setError(mensaje);
                }
            }
        } catch (err) {
            console.error('Error de conexión en login:', err);
            setError('Error de conexión con el servidor.');
        } finally {
            setCargando(false);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-emerald-700 to-emerald-900 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
                {/* Encabezado con identidad del sistema */}
                <div className="bg-emerald-700 p-6 text-center">
                    <Activity size={40} className="text-emerald-200 mx-auto mb-2" />
                    <h1 className="text-2xl font-bold text-white tracking-tight">NutriComedor OSB</h1>
                    <p className="text-emerald-200 text-sm mt-1">Inicie sesión para continuar</p>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    {/* Mensaje de error (caja roja) */}
                    {error && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-start gap-2">
                            <AlertCircle size={18} className="shrink-0 mt-0.5" />
                            <p className="text-sm font-medium">{error}</p>
                        </div>
                    )}
                    {/* Mensaje de aviso de bloqueo inminente (caja ámbar) */}
                    {aviso && (
                        <div className="p-3 bg-amber-50 border border-amber-300 rounded-lg text-amber-800 flex items-start gap-2">
                            <AlertTriangle size={18} className="shrink-0 mt-0.5" />
                            <p className="text-sm font-medium">{aviso}</p>
                        </div>
                    )}

                    {/* Tipo de documento + número */}
                    <div className="flex gap-3">
                        <div className="w-1/3">
                            <label className="block text-sm font-semibold text-slate-600 mb-1">Tipo</label>
                            <div className="relative">
                                <User className="absolute left-3 top-2.5 text-slate-400" size={16} />
                                <select
                                    value={tipoDocumento}
                                    onChange={(e) => setTipoDocumento(e.target.value)}
                                    className="w-full pl-9 pr-2 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 bg-white text-sm"
                                >
                                    <option value="DNI">DNI</option>
                                    <option value="CE">C.E.</option>
                                </select>
                            </div>
                        </div>
                        <div className="flex-1">
                            <label className="block text-sm font-semibold text-slate-600 mb-1">Documento</label>
                            <input
                                type="text"
                                value={documento}
                                onChange={(e) => setDocumento(e.target.value.replace(/[^a-zA-Z0-9]/g, '').slice(0, 15))}
                                placeholder="Ej: 43604221"
                                className="w-full px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                            />
                        </div>
                    </div>

                    {/* Contraseña con mostrar/ocultar */}
                    <div>
                        <label className="block text-sm font-semibold text-slate-600 mb-1">Contraseña</label>
                        <div className="relative">
                            <Lock className="absolute left-3 top-2.5 text-slate-400" size={16} />
                            <input
                                type={verClave ? 'text' : 'password'}
                                value={clave}
                                onChange={(e) => setClave(e.target.value)}
                                placeholder="Ingrese su contraseña"
                                className="w-full pl-9 pr-10 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500 text-sm"
                            />
                            <button
                                type="button"
                                onClick={() => setVerClave(!verClave)}
                                className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                                aria-label={verClave ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                            >
                                {verClave ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                        </div>
                    </div>

                    {/* Botón de ingreso */}
                    <button
                        type="submit"
                        disabled={cargando}
                        className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-3 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                        {cargando ? <Loader2 className="animate-spin" size={18} /> : 'Ingresar'}
                    </button>

                    <p className="text-xs text-slate-400 text-center">
                        La contraseña expira cada 6 meses. Tras 3 intentos fallidos el usuario se bloquea.
                    </p>
                </form>
            </div>
        </div>
    );
};