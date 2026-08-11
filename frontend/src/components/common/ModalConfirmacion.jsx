import React from 'react';
import { AlertTriangle } from 'lucide-react';

export const ModalConfirmacion = ({ isOpen, onClose, onConfirm, mensaje, tipo = 'warning' }) => {
  if (!isOpen) return null;
  const color = tipo === 'danger' ? 'text-red-500' : 'text-amber-500';
  const btn = tipo === 'danger' ? 'bg-red-600 hover:bg-red-700' : 'bg-amber-500 hover:bg-amber-600';
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden text-center p-6">
        <AlertTriangle size={48} className={`${color} mx-auto mb-4`} />
        <h3 className="font-bold text-xl text-slate-800 mb-2">¡Atención!</h3>
        <p className="text-slate-600 mb-6">{mensaje}</p>
        <div className="flex gap-3">
          <button onClick={onClose} className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold py-2 rounded-lg">Cancelar</button>
          <button onClick={onConfirm} className={`flex-1 ${btn} text-white font-bold py-2 rounded-lg`}>Sí, Confirmar</button>
        </div>
      </div>
    </div>
  );
};