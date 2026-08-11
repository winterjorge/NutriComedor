import React, { useState, useEffect } from 'react';
import { Search, Plus, BadgeDollarSign, Loader2, Edit, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { api } from '../../services/api';
import { ModalNuevaReceta } from './ModalNuevaReceta';
import { ModalCostoReceta } from './ModalCostoReceta';

export const RecipesView = () => {
  const [recetas, setRecetas] = useState([]);
  const [cargando, setCargando] = useState(true);
  const [busqueda, setBusqueda] = useState('');
  const [modalNueva, setModalNueva] = useState(false);
  const [modalCosto, setModalCosto] = useState(false);
  const [recetaSel, setRecetaSel] = useState(null);
  const [recetaEditar, setRecetaEditar] = useState(null);
  const [fecha, setFecha] = useState(new Date().toISOString().split('T')[0]);
  
  // Paginación y Ordenamiento
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [sortBy, setSortBy] = useState('nombre');
  const [sortOrder, setSortOrder] = useState('asc');

  const cargarRecetas = async () => {
    setCargando(true);
    try {
      // CORRECCIÓN: Solo incluir search si busqueda tiene valor
      const params = {
        page,
        per_page: perPage,
        sort_by: sortBy,
        sort_order: sortOrder
      };
      
      // Solo agregar search si hay un valor
      if (busqueda && busqueda.trim() !== '') {
        params.search = busqueda;
      }
      
      const data = await api.getRecetas(params);
      setRecetas(data.recetas || []);
      setTotalPages(data.total_pages || 0);
      setTotal(data.total || 0);
    } catch (e) {
      console.error('Error cargando recetas:', e);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargarRecetas();
  }, [page, perPage, sortBy, sortOrder]);

  // Resetear a página 1 cuando cambia la búsqueda
  useEffect(() => {
    setPage(1);
  }, [busqueda]);
  
  // Recargar cuando cambia la búsqueda (con debounce simple)
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      cargarRecetas();
    }, 300);
    
    return () => clearTimeout(timeoutId);
  }, [busqueda]);

  const handleSort = (campo) => {
    if (sortBy === campo) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(campo);
      setSortOrder('asc');
    }
  };

  const abrirEditar = (receta) => {
    setRecetaEditar(receta);
    // Forzar un pequeño delay para asegurar que el estado se actualice
    setTimeout(() => {
      setModalNueva(true);
    }, 0);
  };

  const abrirCosto = (r) => {
    setRecetaSel(r);
    setModalCosto(true);
  };

  const handleModalClose = () => {
    setModalNueva(false);
    setRecetaEditar(null);
  };

  const SortIcon = ({ campo }) => {
    if (sortBy !== campo) return <ChevronUp size={14} className="text-slate-400" />;
    return sortOrder === 'asc' ? <ChevronUp size={14} className="text-emerald-600" /> : <ChevronDown size={14} className="text-emerald-600" />;
  };

  return (
    <>
      <div className="animate-in fade-in duration-300">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-800">Gestión de Recetas</h2>
            <p className="text-sm text-slate-500">{total} recetas registradas</p>
          </div>
          <button
            onClick={() => { setRecetaEditar(null); setModalNueva(true); }}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-medium"
          >
            <Plus size={18} /> Nueva Receta
          </button>
        </div>

        <div className="mb-4 bg-slate-50 p-4 rounded-xl border border-slate-100">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
            <input 
              type="text" 
              placeholder="Buscar Receta..." 
              value={busqueda} 
              onChange={e => setBusqueda(e.target.value)} 
              className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none shadow-sm" 
            />
          </div>
        </div>
    
        <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
          <table className="w-full text-left border-collapse whitespace-nowrap">
            <thead>
              <tr className="bg-slate-100 text-slate-600 text-sm">
                <th className="p-4 font-semibold cursor-pointer hover:bg-slate-200" onClick={() => handleSort('nombre')}>
                  <div className="flex items-center gap-2">
                    Receta
                    <SortIcon campo="nombre" />
                  </div>
                </th>
                <th className="p-4 font-semibold text-center cursor-pointer hover:bg-slate-200" onClick={() => handleSort('energia_kcal')}>
                  <div className="flex items-center justify-center gap-2">
                    Energía (kcal)
                    <SortIcon campo="energia_kcal" />
                  </div>
                </th>
                <th className="p-4 font-semibold text-center cursor-pointer hover:bg-slate-200" onClick={() => handleSort('hierro_mg')}>
                  <div className="flex items-center justify-center gap-2">
                    Hierro (mg)
                    <SortIcon campo="hierro_mg" />
                  </div>
                </th>
                <th className="p-4 font-semibold text-center cursor-pointer hover:bg-slate-200" onClick={() => handleSort('proteina_g')}>
                  <div className="flex items-center justify-center gap-2">
                    Proteína (g)
                    <SortIcon campo="proteina_g" />
                  </div>
                </th>
                <th className="p-4 font-semibold text-center">IA Evaluadora</th>
                <th className="p-4 font-semibold text-center">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {cargando ? (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-emerald-600">
                    <Loader2 className="animate-spin mx-auto" size={28} />
                  </td>
                </tr>
              ) : recetas.length === 0 ? (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-slate-500">
                    {busqueda ? 'No se encontraron recetas' : 'No hay recetas registradas'}
                  </td>
                </tr>
              ) : (
                recetas.map(r => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="p-4">
                      <p className="font-medium text-slate-800">{r.nombre}</p>
                      <p className="text-xs text-slate-500 truncate max-w-xs">{r.descripcion}</p>
                    </td>
                    <td className="p-4 text-center text-sm text-slate-700">{r.energia_kcal || '-'}</td>
                    <td className="p-4 text-center text-sm text-slate-700">{r.hierro_mg || '-'}</td>
                    <td className="p-4 text-center text-sm text-slate-700">{r.proteina_g || '-'}</td>
                    <td className="p-4 text-center">
                      <button 
                        onClick={() => abrirCosto(r)} 
                        className="inline-flex items-center gap-1.5 bg-white border border-emerald-300 text-emerald-700 hover:bg-emerald-50 px-3 py-1.5 rounded-lg text-sm font-semibold"
                      >
                        <BadgeDollarSign size={16} /> Evaluar
                      </button>
                    </td>
                    <td className="p-4 text-center">
                      <button
                        onClick={() => abrirEditar(r)}
                        className="inline-flex items-center gap-1.5 bg-white border border-blue-300 text-blue-700 hover:bg-blue-50 px-3 py-1.5 rounded-lg text-sm font-semibold"
                      >
                        <Edit size={16} /> Editar
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Controles de Paginación */}
        {total > 0 && (
          <div className="mt-4 flex flex-col sm:flex-row justify-between items-center gap-4 bg-white p-4 rounded-lg border border-slate-200">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <span>Mostrar</span>
              <select
                value={perPage}
                onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1); }}
                className="px-3 py-1 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>
              <span>por página</span>
            </div>

            <div className="text-sm text-slate-600">
              Página {page} de {totalPages} ({total} total)
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="inline-flex items-center gap-1 px-3 py-1.5 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                <ChevronLeft size={16} /> Anterior
              </button>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page === totalPages}
                className="inline-flex items-center gap-1 px-3 py-1.5 border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                Siguiente <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
  
      <ModalNuevaReceta 
        isOpen={modalNueva} 
        onClose={handleModalClose}
        onSuccess={() => { handleModalClose(); cargarRecetas(); }}
        recetaEditar={recetaEditar}
      />
      <ModalCostoReceta 
        isOpen={modalCosto} 
        onClose={() => { setModalCosto(false); setRecetaSel(null); }} 
        receta={recetaSel} 
        fecha={fecha}
        onChangeFecha={setFecha}
      />
    </>
  );
};