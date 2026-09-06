/**
 * components/common/ModalExito.jsx
 * Objetivo: Modal genérico de notificación de éxito con el lenguaje visual del sistema
 *           (icono esmeralda, tarjeta blanca centrada y botón "Aceptar").
 * Uso: Importar en cualquier vista o modal que necesite confirmar una operación exitosa,
 *      reemplazando los alert() nativos del navegador. Se controla con `isOpen`, `onClose` y `mensaje`.
 * Nota: Usa z-[80] para quedar por encima de modales de edición (z-[60]) y de confirmación (z-[70]).
 *       Creado en el marco del ticket Jira COM-18 (modal de recetas) y reutilizable en otros módulos.
 */
import React from 'react';
import { CheckCircle } from 'lucide-react';

export const ModalExito = ({ isOpen, onClose, mensaje }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden text-center p-6">
                {/* Icono de éxito con el color corporativo esmeralda */}
                <CheckCircle size={48} className="text-emerald-500 mx-auto mb-4" />
                <h3 className="font-bold text-xl text-slate-800 mb-2">¡Operación Exitosa!</h3>
                <p className="text-slate-600 mb-6">{mensaje}</p>
                <button
                    onClick={onClose}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 rounded-lg transition-colors"
                >
                    Aceptar
                </button>
            </div>
        </div>
    );
};