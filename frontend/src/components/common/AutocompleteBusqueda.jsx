/**
 * components/common/AutocompleteBusqueda.jsx
 * Objetivo: Campo de texto reutilizable con búsqueda (autocompletado con debounce) y
 *           selección múltiple mediante chips. Se usa en el flujo de creación/edición
 *           de usuarios (COM-26) para seleccionar municipalidades y comedores dentro
 *           del alcance permitido del creador.
 * Uso: Importar y pasar `buscarFn` (async que recibe la consulta), `seleccionados`,
 *      `onSeleccionar`/`onQuitar`, `getLabel`/`getSubLabel` y opcionalmente
 *      `permitidos` (array de ids del alcance del creador para filtrar resultados).
 * Nota: Los nombres describen funcionalidad (no referencian tickets).
 */
import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Loader2 } from 'lucide-react';

export const AutocompleteBusqueda = ({
    placeholder = 'Buscar...',
    buscarFn,               // async (query) => [ {id, ...}, ... ]
    seleccionados = [],     // [{id, ...}] ya seleccionados
    onSeleccionar,          // (item) => void
    onQuitar,               // (item) => void
    getLabel,               // (item) => string (texto principal)
    getSubLabel,            // (item) => string (texto secundario, opcional)
    permitidos = null,      // array de ids permitidos (alcance) o null = sin filtro
    deshabilitado = false,
}) => {
    const [query, setQuery] = useState('');
    const [resultados, setResultados] = useState([]);
    const [cargando, setCargando] = useState(false);
    const [abierto, setAbierto] = useState(false);
    const contRef = useRef(null);
    const debounceRef = useRef(null);

    // Búsqueda con debounce de 300 ms, filtrada al alcance y a los no seleccionados
    useEffect(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        if (!query.trim()) {
            setResultados([]);
            setAbierto(false);
            return;
        }
        debounceRef.current = setTimeout(async () => {
            setCargando(true);
            try {
                let res = await buscarFn(query.trim());
                if (permitidos) res = res.filter(r => permitidos.includes(r.id));
                const yaSeleccionados = new Set(seleccionados.map(s => s.id));
                res = res.filter(r => !yaSeleccionados.has(r.id));
                setResultados(res);
                setAbierto(true);
            } catch (e) {
                setResultados([]);
            } finally {
                setCargando(false);
            }
        }, 300);
        return () => clearTimeout(debounceRef.current);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query, permitidos]);

    // Cerrar el dropdown al hacer clic fuera del componente
    useEffect(() => {
        const onClickFuera = (e) => {
            if (contRef.current && !contRef.current.contains(e.target)) setAbierto(false);
        };
        document.addEventListener('mousedown', onClickFuera);
        return () => document.removeEventListener('mousedown', onClickFuera);
    }, []);

    const seleccionar = (item) => {
        onSeleccionar(item);
        setQuery('');
        setResultados([]);
        setAbierto(false);
    };

    return (
        <div ref={contRef} className="relative">
            {/* Chips de elementos ya seleccionados */}
            {seleccionados.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                    {seleccionados.map(item => (
                        <span key={item.id}
                            className="flex items-center gap-1 bg-emerald-100 text-emerald-800 px-2 py-1 rounded-full text-xs font-medium">
                            {getLabel(item)}
                            {!deshabilitado && (
                                <button type="button" onClick={() => onQuitar(item)}
                                    className="hover:text-red-600 transition-colors" aria-label="Quitar">
                                    <X size={12} />
                                </button>
                            )}
                        </span>
                    ))}
                </div>
            )}

            {/* Input de búsqueda */}
            <div className="relative">
                <Search size={15} className="absolute left-3 top-2.5 text-slate-400" />
                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => { if (resultados.length) setAbierto(true); }}
                    placeholder={placeholder}
                    disabled={deshabilitado}
                    className="w-full pl-9 pr-9 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50"
                />
                {cargando && <Loader2 size={15} className="animate-spin absolute right-3 top-2.5 text-slate-400" />}
            </div>

            {/* Dropdown de resultados */}
            {abierto && resultados.length > 0 && (
                <div className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                    {resultados.map(item => (
                        <button key={item.id} type="button" onClick={() => seleccionar(item)}
                            className="w-full text-left px-3 py-2 hover:bg-emerald-50 transition-colors">
                            <span className="block text-sm text-slate-800">{getLabel(item)}</span>
                            {getSubLabel && <span className="block text-xs text-slate-500">{getSubLabel(item)}</span>}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};