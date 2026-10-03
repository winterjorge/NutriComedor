/**
 * components/recipes/RecipesView.jsx
 * Objetivo: Listado paginado y ordenable del recetario con evaluación de costo (modal)
 *           y edición de recetas.
 * Historial:
 *  - Sprint 1/2: versión original (paginación, orden por columnas, búsqueda).
 *  - COM-47 v2: las columnas nutricionales mostraban tabla/raciones.
 *  - COM-47 v3 (este archivo): FIX del bug de doble división: los valores nutricionales
 *    de recetas_almuerzo YA SON POR RACIÓN tal como se capturan en el modal, por lo que
 *    se muestran SIN dividir (el helper porRacion queda COMENTADO por trazabilidad).
 *    Mejoras de legibilidad solicitadas:
 *      * Columna única "Contenido nutricional (por ración)" con los 6 valores
 *        etiquetados (energía, proteína, hierro, vitamina A, zinc, carbohidratos) en
 *        cuadrícula de 2 columnas para que se vea TODO el contenido sin ensanchar.
 *      * Los nombres largos de receta pasan a dos líneas: se retira whitespace-nowrap
 *        de la tabla y la celda de nombre tiene ancho máximo con wrap natural.
 *      * El ordenamiento por columnas se mueve a un selector compacto (conserva todas
 *        las claves anteriores); los encabezados ordenables quedan COMENTADOS.
 *    Nada existente se elimina; lo reemplazado se comenta.
 */
import React, { useState, useEffect } from 'react';
import { Search, Plus, BadgeDollarSign, Loader2, Edit, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, ArrowUpDown } from 'lucide-react';
import { api } from '../../services/api';
import { ModalNuevaReceta } from './ModalNuevaReceta';
import { ModalCostoReceta } from './ModalCostoReceta';

// COM-47 v3 (trazabilidad): helper de división por raciones COMENTADO. Los valores de
// la tabla ya están POR RACIÓN y no deben dividirse de nuevo (causaba 793 -> 198.25).
// const racionesDe = (r) => (r && r.raciones && r.raciones > 0 ? Number(r.raciones) : 4);
// const porRacion = (valor, r) => {
//     if (valor === null || valor === undefined || valor === '') return '-';
//     return (Number(valor) / racionesDe(r)).toFixed(2);
// };

// COM-47 v3: formato legible de un valor nutricional tal como se guardó
const fmtNut = (v) => (v === null || v === undefined || v === '' ? '—' : Number(v));

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

    // COM-47 v3 (trazabilidad): orden por clic en encabezado COMENTADO; se reemplaza
    // por el selector compacto de orden (misma lógica de estado sortBy/sortOrder).
    // const handleSort = (campo) => {
    //     if (sortBy === campo) {
    //         setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    //     } else {
    //         setSortBy(campo);
    //         setSortOrder('asc');
    //     }
    // };

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

    // COM-47 v3 (trazabilidad): ícono de orden por columna COMENTADO (ya no hay
    // encabezados ordenables; el orden vive en el selector compacto).
    // const SortIcon = ({ campo }) => {
    //     if (sortBy !== campo) return <ChevronUp size={14} className="text-slate-400" />;
    //     return sortOrder === 'asc' ? <ChevronUp size={14} className="text-emerald-600" /> : <ChevronDown size={14} className="text-emerald-600" />;
    // };

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

                <div className="mb-4 bg-slate-50 p-4 rounded-xl border border-slate-100 flex flex-wrap items-center gap-3">
                    <div className="relative flex-1 min-w-[220px] max-w-md">
                        <Search className="absolute left-3 top-2.5 text-slate-400" size={18} />
                        <input
                            type="text"
                            placeholder="Buscar Receta..."
                            value={busqueda}
                            onChange={e => setBusqueda(e.target.value)}
                            className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none shadow-sm"
                        />
                    </div>
                    {/* COM-47 v3: selector compacto de ordenamiento (reemplaza los
                        encabezados ordenables para no ensanchar la tabla) */}
                    <div className="flex items-center gap-2 ml-auto">
                        <label className="text-xs text-slate-500 flex items-center gap-1">
                            <ArrowUpDown size={13} /> Ordenar por
                        </label>
                        <select
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value)}
                            className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-white outline-none focus:ring-2 focus:ring-emerald-500"
                        >
                            <option value="nombre">Nombre</option>
                            <option value="energia_kcal">Energía (kcal/ración)</option>
                            <option value="proteina_g">Proteína (g/ración)</option>
                            <option value="hierro_mg">Hierro (mg/ración)</option>
                            <option value="vitamina_a_ug">Vitamina A (μg/ración)</option>
                            <option value="zinc_mg">Zinc (mg/ración)</option>
                            <option value="carbohidratos_g">Carbohidratos (g/ración)</option>
                            <option value="raciones">Raciones</option>
                            <option value="fecha_creacion">Fecha de creación</option>
                        </select>
                        <button
                            onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
                            title={sortOrder === 'asc' ? 'Ascendente' : 'Descendente'}
                            className="p-1.5 border border-slate-300 rounded-lg text-slate-600 hover:bg-slate-100 transition-colors"
                        >
                            {sortOrder === 'asc' ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                        </button>
                    </div>
                </div>

                {/* COM-47 v3: se retira whitespace-nowrap para que nombres y celdas
                    puedan envolver; la tabla ya no es extremadamente ancha */}
                <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            {/* COM-47 v3 (trazabilidad): encabezados ordenables anteriores
                                COMENTADOS; el orden vive ahora en el selector compacto.
                            <tr className="bg-slate-100 text-slate-600 text-sm">
                                <th ... onClick={() => handleSort('nombre')}>Receta <SortIcon campo="nombre" /></th>
                                <th ... onClick={() => handleSort('energia_kcal')}>Energía (kcal) ...</th>
                                <th ... onClick={() => handleSort('hierro_mg')}>Hierro (mg) ...</th>
                                <th ... onClick={() => handleSort('proteina_g')}>Proteína (g) ...</th>
                                <th ...>IA Evaluadora</th>
                                <th ...>Acciones</th>
                            </tr>
                            */}
                            <tr className="bg-slate-100 text-slate-600 text-sm">
                                <th className="p-4 font-semibold">Receta</th>
                                <th className="p-4 font-semibold text-center">Raciones</th>
                                <th className="p-4 font-semibold">Contenido nutricional (por ración)</th>
                                <th className="p-4 font-semibold text-center">IA Evaluadora</th>
                                <th className="p-4 font-semibold text-center">Acciones</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                            {cargando ? (
                                <tr>
                                    <td colSpan="5" className="p-8 text-center text-emerald-600">
                                        <Loader2 className="animate-spin mx-auto" size={28} />
                                    </td>
                                </tr>
                            ) : recetas.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="p-8 text-center text-slate-500">
                                        {busqueda ? 'No se encontraron recetas' : 'No hay recetas registradas'}
                                    </td>
                                </tr>
                            ) : (
                                recetas.map(r => (
                                    <tr key={r.id} className="hover:bg-slate-50 align-top">
                                        {/* COM-47 v3: nombre con wrap a dos líneas (ancho máximo) */}
                                        <td className="p-4 max-w-[240px]">
                                            <p className="font-medium text-slate-800 whitespace-normal break-words leading-snug">
                                                {r.nombre}
                                            </p>
                                            <p className="text-xs text-slate-500 whitespace-normal break-words mt-0.5">
                                                {r.descripcion}
                                            </p>
                                        </td>
                                        <td className="p-4 text-center">
                                            <span className="inline-block px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs font-bold" title="Raciones que produce la preparación">
                                                {r.raciones ?? 4}
                                            </span>
                                        </td>
                                        {/* COM-47 v3: valores TAL COMO SE GUARDARON (por ración);
                                            cuadrícula 2x3 con los 6 nutrientes etiquetados */}
                                        <td className="p-4">
                                            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] leading-4 text-slate-600 max-w-[260px]">
                                                <span><b className="text-slate-700">Energía:</b> {fmtNut(r.energia_kcal)} kcal</span>
                                                <span><b className="text-slate-700">Proteína:</b> {fmtNut(r.proteina_g)} g</span>
                                                <span><b className="text-slate-700">Hierro:</b> {fmtNut(r.hierro_mg)} mg</span>
                                                <span><b className="text-slate-700">Vit. A:</b> {fmtNut(r.vitamina_a_ug)} μg</span>
                                                <span><b className="text-slate-700">Zinc:</b> {fmtNut(r.zinc_mg)} mg</span>
                                                <span><b className="text-slate-700">Carboh.:</b> {fmtNut(r.carbohidratos_g)} g</span>
                                            </div>
                                        </td>
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