import React, { useState, useEffect } from 'react';
import { Search, Plus, Edit, Trash2, ChevronLeft, ChevronRight, SortAsc, SortDesc } from 'lucide-react';
import { api } from '../../services/api';
import { ModalNuevaReceta } from './ModalNuevaReceta';

export const GestionRecetas = () => {
  const [recetas, setRecetas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('nombre');
  const [sortOrder, setSortOrder] = useState('asc');
  const [minEnergia, setMinEnergia] = useState('');
  const [maxEnergia, setMaxEnergia] = useState('');
  const [minProteina, setMinProteina] = useState('');
  const [maxProteina, setMaxProteina] = useState('');
  const [minHierro, setMinHierro] = useState('');
  const [maxHierro, setMaxHierro] = useState('');
  
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    cargarRecetas();
  }, [page, perPage, search, sortBy, sortOrder, minEnergia, maxEnergia, minProteina, maxProteina, minHierro, maxHierro]);

  const cargarRecetas = async () => {
    setLoading(true);
    try {
      const params = {
        page,
        per_page: perPage,
        search: search || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        min_energia: minEnergia || undefined,
        max_energia: maxEnergia || undefined,
        min_proteina: minProteina || undefined,
        max_proteina: maxProteina || undefined,
        min_hierro: minHierro || undefined,
        max_hierro: maxHierro || undefined
      };
      
      const data = await api.getRecetas(params);
      
      if (data && Array.isArray(data.recetas)) {
        setRecetas(data.recetas);
        setTotalPages(data.total_pages || 0);
        setTotal(data.total || 0);
      } else {
        setRecetas([]);
      }
    } catch (error) {
      console.error('Error cargando recetas:', error);
      setRecetas([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('asc');
    }
  };

  const handleRecetaCreada = () => {
    setShowModal(false);
    setPage(1);
    cargarRecetas();
  };

  const handleDelete = async (id) => {
    if (window.confirm('¿Estás seguro de eliminar esta receta?')) {
      try {
        await api.deleteReceta(id);
        cargarRecetas();
      } catch (error) {
        console.error('Error eliminando receta:', error);
        alert('Error al eliminar la receta: ' + error.message);
      }
    }
  };

  const SortIcon = ({ field }) => {
    if (sortBy !== field) return <SortAsc size={14} className="text-gray-400" />;
    return sortOrder === 'asc' ? <SortAsc size={14} className="text-emerald-600" /> : <SortDesc size={14} className="text-emerald-600" />;
  };

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Gestión de Recetas</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors"
        >
          <Plus size={20} />
          Nueva Receta
        </button>
      </div>

      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
            <input
              type="text"
              placeholder="Buscar receta..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            />
          </div>

          <div className="flex gap-2">
            <input
              type="number"
              placeholder="Min kcal"
              value={minEnergia}
              onChange={(e) => setMinEnergia(e.target.value)}
              className="w-1/2 px-3 py-2 border border-gray-300 rounded-lg"
            />
            <input
              type="number"
              placeholder="Max kcal"
              value={maxEnergia}
              onChange={(e) => setMaxEnergia(e.target.value)}
              className="w-1/2 px-3 py-2 border border-gray-300 rounded-lg"
            />
          </div>

          <div className="flex gap-2">
            <input
              type="number"
              placeholder="Min prot (g)"
              value={minProteina}
              onChange={(e) => setMinProteina(e.target.value)}
              className="w-1/2 px-3 py-2 border border-gray-300 rounded-lg"
            />
            <input
              type="number"
              placeholder="Max prot (g)"
              value={maxProteina}
              onChange={(e) => setMaxProteina(e.target.value)}
              className="w-1/2 px-3 py-2 border border-gray-300 rounded-lg"
            />
          </div>

          <div className="flex gap-2">
            <input
              type="number"
              placeholder="Min hierro (mg)"
              value={minHierro}
              onChange={(e) => setMinHierro(e.target.value)}
              className="w-1/2 px-3 py-2 border border-gray-300 rounded-lg"
            />
            <input
              type="number"
              placeholder="Max hierro (mg)"
              value={maxHierro}
              onChange={(e) => setMaxHierro(e.target.value)}
              className="w-1/2 px-3 py-2 border border-gray-300 rounded-lg"
            />
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100" onClick={() => handleSort('nombre')}>
                  <div className="flex items-center gap-2">
                    Nombre
                    <SortIcon field="nombre" />
                  </div>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100" onClick={() => handleSort('energia_kcal')}>
                  <div className="flex items-center gap-2">
                    Energía (kcal)
                    <SortIcon field="energia_kcal" />
                  </div>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100" onClick={() => handleSort('proteina_g')}>
                  <div className="flex items-center gap-2">
                    Proteína (g)
                    <SortIcon field="proteina_g" />
                  </div>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100" onClick={() => handleSort('hierro_mg')}>
                  <div className="flex items-center gap-2">
                    Hierro (mg)
                    <SortIcon field="hierro_mg" />
                  </div>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Acciones
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading ? (
                <tr>
                  <td colSpan="5" className="px-6 py-4 text-center text-gray-500">
                    Cargando...
                  </td>
                </tr>
              ) : !Array.isArray(recetas) || recetas.length === 0 ? (
                <tr>
                  <td colSpan="5" className="px-6 py-4 text-center text-gray-500">
                    No se encontraron recetas
                  </td>
                </tr>
              ) : (
                recetas.map((receta) => (
                  <tr key={receta.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">{receta.nombre}</div>
                      {receta.descripcion && (
                        <div className="text-sm text-gray-500 truncate max-w-xs">{receta.descripcion}</div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {receta.energia_kcal || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {receta.proteina_g || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                      {receta.hierro_mg || '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleDelete(receta.id)}
                          className="text-red-600 hover:text-red-900"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-700">
              Mostrando <span className="font-medium">{((page - 1) * perPage) + 1}</span> a{' '}
              <span className="font-medium">{Math.min(page * perPage, total)}</span> de{' '}
              <span className="font-medium">{total}</span> resultados
            </span>
            <select
              value={perPage}
              onChange={(e) => {
                setPerPage(Number(e.target.value));
                setPage(1);
              }}
              className="border border-gray-300 rounded-md px-3 py-1 text-sm"
            >
              <option value={10}>10 por página</option>
              <option value={20}>20 por página</option>
              <option value={50}>50 por página</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              className="relative inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={16} />
            </button>
            <span className="px-3 py-2 text-sm text-gray-700">
              Página {page} de {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page === totalPages}
              className="relative inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      <ModalNuevaReceta
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        onSuccess={handleRecetaCreada}
      />
    </div>
  );
};