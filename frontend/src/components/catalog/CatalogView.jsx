import React, { useState } from 'react';
import { Search, Calendar, BarChart2, Loader2 } from 'lucide-react';
import { useCatalog } from '../../hooks/useCatalog';
import { ModalHistoricoPrecios } from './ModalHistoricoPrecios';

export const CatalogView = () => {
  // INICIALIZACIÓN CORRECTA: Siempre tendrá un valor desde el primer render
  const [fecha, setFecha] = useState(new Date().toISOString().split('T')[0]);
  const [busqueda, setBusqueda] = useState('');
  
  const { 
    catalogo, 
    cargando, 
    ingredienteSel, 
    setIngredienteSel 
  } = useCatalog(fecha, busqueda);

  return (
    <>
      <div className="animate-in fade-in duration-300">
        <div className="flex flex-col md:flex-row justify-between items-center gap-4 mb-6 bg-slate-50 p-4 rounded-xl border border-slate-100">
          <div className="w-full md:w-1/2 relative">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
            <input 
              type="text" 
              placeholder="Buscar Insumo..." 
              value={busqueda} 
              onChange={e => setBusqueda(e.target.value)} 
              className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none bg-white shadow-sm" 
            />
          </div>
          <div className="relative">
            <Calendar className="absolute left-3 top-2.5 text-slate-400" size={18} />
            <input 
              type="date" 
              value={fecha} 
              onChange={e => setFecha(e.target.value)} 
              className="pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none bg-white shadow-sm" 
            />
          </div>
        </div>
        
        <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-100 text-slate-600 text-sm">
                <th className="p-4 font-semibold">Insumo</th>
                <th className="p-4 font-semibold">Categoría</th>
                <th className="p-4 font-semibold text-right">Precio</th>
                <th className="p-4 font-semibold text-center">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {cargando ? (
                <tr>
                  <td colSpan="4" className="p-8 text-center text-emerald-600">
                    <Loader2 className="animate-spin mx-auto" size={28} />
                  </td>
                </tr>
              ) : catalogo.length > 0 ? (
                catalogo.map(item => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="p-4 font-medium text-slate-800">{item.nombre}</td>
                    <td className="p-4 text-sm text-slate-600">
                      <span className="bg-slate-200 px-2 py-1 rounded-md text-xs font-semibold">{item.categoria}</span>
                    </td>
                    <td className="p-4 font-bold text-emerald-600 text-right">
                      S/ {parseFloat(item.precio).toFixed(2)}
                    </td>
                    <td className="p-4 text-center">
                      <button 
                        onClick={() => setIngredienteSel(item)} 
                        className="inline-flex items-center gap-1 bg-white border border-slate-300 hover:bg-emerald-50 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-600"
                      >
                        <BarChart2 size={16} /> Histórico
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="4" className="p-8 text-center text-slate-500">No hay insumos.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      
      <ModalHistoricoPrecios 
        ingrediente={ingredienteSel} 
        onClose={() => setIngredienteSel(null)} 
      />
    </>
  );
};