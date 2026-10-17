/**
components/layout/SidebarNav.jsx
Objetivo: COM-41: navegación lateral agrupada por CATEGORÍAS en acordeón, reutilizable
      tanto en el sidebar fijo de desktop como en el drawer móvil. Cada categoría
      despliega sus tabs con ícono + nombre (reconocimiento visual rápido, decisión
      de producto COM-41). Una sola categoría abierta a la vez (controlada por el
      padre via catAbierta/setCatAbierta) y resaltado del tab activo.
Historial:
COM-41 (este archivo): versión original.
Accesibilidad: botones con aria-expanded y foco visible de marca (COM-81):
      focus:outline-none + focus-visible:ring esmeralda (nunca outline negro).
Uso: Montado por App.jsx dentro del <aside> desktop y del drawer móvil.
Referencia: ticket COM-41 (solo trazabilidad).
*/
import React from 'react';
import { ChevronDown } from 'lucide-react';

// COM-81: foco de marca coherente con la paleta (anillo esmeralda solo con teclado)
const FOCUS_NAV = 'focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-1';

export const SidebarNav = ({ categorias, activeTab, onSelect, catAbierta, setCatAbierta }) => {
    return (
        <nav className="flex flex-col gap-1" aria-label="Navegación principal">
            {categorias.map(cat => {
                const Icon = cat.icon;
                const abierta = catAbierta === cat.clave;
                const contieneActiva = cat.tabs.some(t => t.id === activeTab);
                return (
                    <div key={cat.clave}>
                        {/* Encabezado de categoría (acordeón) */}
                        <button
                            onClick={() => setCatAbierta(abierta ? null : cat.clave)}
                            aria-expanded={abierta}
                            className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm font-semibold transition-colors ${FOCUS_NAV} ${
                                abierta || contieneActiva
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : 'text-slate-600 hover:bg-slate-100'
                            }`}
                        >
                            <Icon size={15} className={abierta || contieneActiva ? 'text-emerald-600' : 'text-slate-400'} />
                            <span className="flex-1 text-left">{cat.label}</span>
                            <ChevronDown size={14} className={`transition-transform ${abierta ? 'rotate-180' : ''}`} />
                        </button>
                        {/* Tabs de la categoría abierta */}
                        {abierta && (
                            <div className="mt-0.5 ml-3 pl-2 border-l-2 border-emerald-100 flex flex-col gap-0.5">
                                {cat.tabs.map(t => {
                                    const TIcon = t.icon;
                                    const activa = activeTab === t.id;
                                    return (
                                        <button
                                            key={t.id}
                                            onClick={() => onSelect(t.id)}
                                            className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-sm transition-colors ${FOCUS_NAV} ${
                                                activa
                                                    ? 'bg-emerald-600 text-white font-semibold shadow-sm'
                                                    : 'text-slate-600 hover:bg-slate-100'
                                            }`}
                                        >
                                            <TIcon size={15} />
                                            <span className="truncate">{t.label}</span>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                );
            })}
        </nav>
    );
};