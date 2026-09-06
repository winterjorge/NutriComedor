/**
 * App.jsx
 * Objetivo: Componente raíz de la aplicación. Orquesta la navegación por pestañas,
 *           el proveedor de parámetros dinámicos y, desde el ticket COM-19,
 *           la capa de autenticación: renderiza LoginView si no hay sesión activa
 *           y ModalCambioClave bloqueante cuando la contraseña está expirada o es provisoria.
 * Uso: Montado en main.jsx mediante <React.StrictMode>. Envuelve toda la app con
 *      AuthProvider y ParametrosProvider.
 *
 * Historial de cambios:
 *  - Versión base: navegación por pestañas (Recetario, Presupuesto, Planificaciones,
 *    Catálogo, Ventas y Demanda) con ParametrosProvider.
 *  - COM-19: integración del flujo de login (AuthContext) y modal de cambio de clave
 *    obligatorio. Se añade botón de cerrar sesión en el header.
 */
import React, { useState } from 'react';
import { ChefHat, Calculator, ShoppingCart, Activity, Users, ClipboardList, LogOut } from 'lucide-react';
import { RecipesView } from './components/recipes/RecipesView';
import { BudgetView } from './components/budget/BudgetView';
import { PlanificacionesView } from './components/budget/PlanificacionesView';
import { CatalogView } from './components/catalog/CatalogView';
import { POSView } from './components/pos/POSView';
import { ParametrosProvider } from './context/ParametrosContext';
// COM-19: Autenticación y cambio de clave obligatorio
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginView } from './components/auth/LoginView';
import { ModalCambioClave } from './components/auth/ModalCambioClave';

/**
 * Componente interno que consume la sesión y decide qué renderizar:
 *  - Sin sesión -> LoginView
 *  - Con sesión y pendienteCambio -> ModalCambioClave (bloqueante)
 *  - Con sesión y clave vigente -> App principal con pestañas
 */
function AppContent() {
    const [activeTab, setActiveTab] = useState('pos');
    const { usuario, pendienteCambio, completarCambioClave, cerrarSesion } = useAuth();

    // COM-19: Si no hay usuario autenticado, renderizar solo la pantalla de login
    if (!usuario) {
        return <LoginView />;
    }

    const tabs = [
        { id: 'recipes', label: 'Recetario', icon: ChefHat, color: 'emerald' },
        { id: 'budget', label: 'Presupuesto', icon: Calculator, color: 'emerald' },
        { id: 'planificaciones', label: 'Planificaciones', icon: ClipboardList, color: 'blue' },
        { id: 'catalog', label: 'Catálogo', icon: ShoppingCart, color: 'emerald' },
        { id: 'pos', label: 'Ventas y Demanda', icon: Users, color: 'blue' },
    ];

    return (
        <>
            <div className="min-h-screen bg-slate-50 text-slate-800 font-sans pb-10">
                {/* Header con identidad del sistema y botón de cerrar sesión (COM-19) */}
                <header className="bg-emerald-700 text-white p-4 shadow-md">
                    <div className="max-w-6xl mx-auto flex items-center gap-3">
                        <Activity size={28} />
                        <div className="flex-1">
                            <h1 className="text-2xl font-bold tracking-tight">NutriComedor OSB</h1>
                            <p className="text-xs text-emerald-100">
                                {usuario.nombres} {usuario.apellido_paterno} · {usuario.tipo_documento} {usuario.documento_identidad}
                            </p>
                        </div>
                        <span className="text-sm bg-emerald-800 px-3 py-1 rounded-full border border-emerald-600 shadow-inner hidden md:inline-block">
                            Módulo Predictivo Activo
                        </span>
                        {/* COM-19: Botón de cerrar sesión */}
                        <button
                            onClick={cerrarSesion}
                            className="flex items-center gap-2 bg-emerald-800 hover:bg-emerald-900 px-3 py-2 rounded-lg text-sm font-medium transition-colors border border-emerald-600"
                            title="Cerrar sesión"
                        >
                            <LogOut size={16} />
                            <span className="hidden sm:inline">Salir</span>
                        </button>
                    </div>
                </header>

                <main className="max-w-6xl mx-auto mt-8 p-4">
                    {/* Barra de pestañas */}
                    <div className="flex gap-2 mb-6 border-b border-slate-200 pb-2 overflow-x-auto">
                        {tabs.map(tab => {
                            const Icon = tab.icon;
                            const isActive = activeTab === tab.id;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`flex shrink-0 items-center gap-2 px-4 py-2 font-medium rounded-t-lg transition-colors ${
                                        isActive
                                            ? `bg-white text-${tab.color}-700 shadow-sm border-t border-x border-slate-200`
                                            : 'text-slate-500 hover:bg-slate-100'
                                    }`}
                                >
                                    <Icon size={18} /> {tab.label}
                                </button>
                            );
                        })}
                    </div>

                    {/* Contenedor de vistas por pestaña */}
                    <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 min-h-[500px]">
                        {activeTab === 'recipes' && <RecipesView />}
                        {activeTab === 'budget' && <BudgetView />}
                        {activeTab === 'planificaciones' && <PlanificacionesView />}
                        {activeTab === 'catalog' && <CatalogView />}
                        {activeTab === 'pos' && <POSView />}
                    </div>
                </main>
            </div>

            {/* COM-19: Modal bloqueante de cambio obligatorio de clave.
                Se muestra cuando el backend indica que la clave está expirada (6 meses)
                o es provisoria (primer login). Bloquea el uso del sistema hasta
                completarse el cambio o cerrarse la sesión. */}
            {pendienteCambio && (
                <ModalCambioClave
                    usuario={usuario}
                    onExito={completarCambioClave}
                    onSalir={cerrarSesion}
                />
            )}
        </>
    );
}

/**
 * Componente raíz exportado: envuelve AppContent con los providers globales.
 * El orden es importante: AuthProvider debe estar por fuera para que el login
 * esté disponible incluso antes de cargar los parámetros dinámicos.
 */
export default function App() {
    return (
        <AuthProvider>
            <ParametrosProvider>
                <AppContent />
            </ParametrosProvider>
        </AuthProvider>
    );
}