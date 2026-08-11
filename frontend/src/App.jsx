import React, { useState } from 'react';
import { ChefHat, Calculator, ShoppingCart, Activity, Users, ClipboardList } from 'lucide-react';
import { RecipesView } from './components/recipes/RecipesView';
import { BudgetView } from './components/budget/BudgetView';
import { PlanificacionesView } from './components/budget/PlanificacionesView';
import { CatalogView } from './components/catalog/CatalogView';
import { POSView } from './components/pos/POSView';
import { ParametrosProvider } from './context/ParametrosContext';

export default function App() {
    const [activeTab, setActiveTab] = useState('pos');

    const tabs = [
        { id: 'recipes', label: 'Recetario', icon: ChefHat, color: 'emerald' },
        { id: 'budget', label: 'Presupuesto', icon: Calculator, color: 'emerald' },
        { id: 'planificaciones', label: 'Planificaciones', icon: ClipboardList, color: 'blue' },
        { id: 'catalog', label: 'Catálogo', icon: ShoppingCart, color: 'emerald' },
        { id: 'pos', label: 'Ventas y Demanda', icon: Users, color: 'blue' },
    ];

    return (
        <ParametrosProvider>
            <div className="min-h-screen bg-slate-50 text-slate-800 font-sans pb-10">
                <header className="bg-emerald-700 text-white p-4 shadow-md">
                    <div className="max-w-6xl mx-auto flex items-center gap-3">
                        <Activity size={28} />
                        <h1 className="text-2xl font-bold tracking-tight">NutriComedor OSB</h1>
                        <span className="ml-auto text-sm bg-emerald-800 px-3 py-1 rounded-full border border-emerald-600 shadow-inner hidden md:inline-block">Módulo Predictivo Activo</span>
                    </div>
                </header>

                <main className="max-w-6xl mx-auto mt-8 p-4">
                    <div className="flex gap-2 mb-6 border-b border-slate-200 pb-2 overflow-x-auto">
                        {tabs.map(tab => {
                            const Icon = tab.icon;
                            const isActive = activeTab === tab.id;
                            return (
                                <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`flex shrink-0 items-center gap-2 px-4 py-2 font-medium rounded-t-lg transition-colors ${isActive ? `bg-white text-${tab.color}-700 shadow-sm border-t border-x border-slate-200` : 'text-slate-500 hover:bg-slate-100'}`}>
                                    <Icon size={18} /> {tab.label}
                                </button>
                            );
                        })}
                    </div>
                    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 min-h-[500px]">
                        {activeTab === 'recipes' && <RecipesView />}
                        {activeTab === 'budget' && <BudgetView />}
                        {activeTab === 'planificaciones' && <PlanificacionesView />}
                        {activeTab === 'catalog' && <CatalogView />}
                        {activeTab === 'pos' && <POSView />}
                    </div>
                </main>
            </div>
        </ParametrosProvider>
    );
}