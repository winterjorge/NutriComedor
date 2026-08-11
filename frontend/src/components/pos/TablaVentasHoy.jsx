import React from 'react';
import { Edit } from 'lucide-react';

export const TablaVentasHoy = ({ ventas, onEditar }) => {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm flex flex-col">
      <div className="bg-slate-100 p-4 border-b"><h3 className="font-bold text-slate-800">Registros de Hoy</h3></div>
      <div className="overflow-y-auto max-h-[500px]">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500 sticky top-0"><tr><th className="p-3 font-semibold">Comensal</th><th className="p-3 font-semibold text-center">Tipo (Rac.)</th><th className="p-3 font-semibold text-right">Monto</th><th className="p-3"></th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {ventas.length === 0 ? <tr><td colSpan="4" className="p-4 text-center text-slate-500">No hay ventas hoy.</td></tr> : ventas.map(v => (
              <tr key={v.id} className="hover:bg-slate-50">
                <td className="p-3"><p className="font-medium text-slate-800 line-clamp-1">{v.nombres}</p><p className="text-xs text-slate-400">{v.documento_identidad}</p></td>
                <td className="p-3 text-center"><span className={`px-2 py-0.5 rounded text-xs font-bold ${v.tipo_comensal_venta === 'Social' ? 'bg-red-100 text-red-700' : v.tipo_comensal_venta === 'Afiliado' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'}`}>{v.tipo_comensal_venta.substring(0,3)}</span><span className="font-black text-slate-700 ml-2">x{v.raciones}</span></td>
                <td className="p-3 font-bold text-emerald-600 text-right">S/ {parseFloat(v.monto_pagado).toFixed(2)}</td>
                <td className="p-3 text-right"><button onClick={() => onEditar(v)} className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-md"><Edit size={16}/></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};