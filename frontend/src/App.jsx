/**
 * App.jsx
 * Objetivo: Componente raíz de la aplicación. Orquesta la navegación por pestañas,
 *           el proveedor de parámetros dinámicos, la capa de autenticación (COM-19),
 *           la selección de comedor post-login (COM-20) y los módulos multi-comedor
 *           (COM-21) y de grupos de usuario (COM-22).
 * Uso: Montado en main.jsx mediante <React.StrictMode>. Envuelve toda la app con
 *      AuthProvider y ParametrosProvider.
 *
 * Historial de cambios:
 *  - Versión base: navegación por pestañas (Recetario, Presupuesto, Planificaciones,
 *    Catálogo, Ventas y Demanda) con ParametrosProvider.
 *  - COM-19: flujo de login (AuthContext), modal de cambio de clave obligatorio y
 *    botón de cerrar sesión en el header.
 *  - COM-21: pestaña "Comedores" con ComedoresView (gestión multi-comedor).
 *  - COM-22: pestaña "Grupos" con GruposView (grupos, roles y membresías).
 *  - COM-20: gate de selección de comedor entre login y dashboard: spinner mientras
 *            `validando` (verificación de membresía recordada), SeleccionComedorView
 *            si no hay selección, y exhibición del comedor/alcance activo en el header.
 */
import React, { useState } from 'react';
import { ChefHat, Calculator, ShoppingCart, Activity, Users, ClipboardList, LogOut, Store, UserCog, Loader2, MapPin } from 'lucide-react';
import { RecipesView } from './components/recipes/RecipesView';
import { BudgetView } from './components/budget/BudgetView';
import { PlanificacionesView } from './components/budget/PlanificacionesView';
import { CatalogView } from './components/catalog/CatalogView';
import { POSView } from './components/pos/POSView';
import { ComedoresView } from './components/comedores/ComedoresView';
import { GruposView } from './components/grupos/GruposView';
import { ParametrosProvider } from './context/ParametrosContext';
// COM-19: Autenticación y cambio de clave obligatorio
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginView } from './components/auth/LoginView';
import { ModalCambioClave } from './components/auth/ModalCambioClave';
// COM-20: pantalla de selección de comedor post-login
import { SeleccionComedorView } from './components/auth/SeleccionComedorView';

/**
 * COM-20: describe el contexto de trabajo activo para exhibirlo en el header.
 */
const descripcionContexto = (seleccion) => {
    if (!seleccion) return '';
    if (seleccion.perfil === 'SISTEMA') return 'Administración del Sistema';
    if (seleccion.perfil === 'ADMINISTRATIVO') {
        return `Alcance municipal: ${seleccion.distrito}, ${seleccion.ciudad} (${seleccion.departamento})`;
    }
    return seleccion.comedor_nombre || 'Comedor';
};

/**
 * Componente interno que consume la sesión y decide qué renderizar:
 *  - Sin sesión                -> LoginView
 *  - validando                 -> spinner (verificación de comedor recordado)
 *  - Sin selección             -> SeleccionComedorView (gate COM-20)
 *  - Con selección             -> dashboard con pestañas + contexto en header
 */
function AppContent() {
    const [activeTab, setActiveTab] = useState('pos');
    const { usuario, pendienteCambio, completarCambioClave, cerrarSesion, seleccion, validando } = useAuth();

    // COM-19: Si no hay usuario autenticado, renderizar solo la pantalla de login
    if (!usuario) {
        return <LoginView />;
    }

    // COM-20: mientras se verifica la selección recordada, mostrar spinner
    if (validando) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-emerald-700 to-emerald-900 flex flex-col items-center justify-center gap-3">
                <Loader2 className="animate-spin text-white" size={44} />
                <p className="text-emerald-100 text-sm">Verificando su comedor de trabajo...</p>
            </div>
        );
    }

    // COM-20: con sesión pero sin selección => pantalla de selección de comedor.
    // Si además hay cambio de clave pendiente, el modal bloqueante se superpone.
    if (!seleccion) {
        return (
            <>
                <SeleccionComedorView />
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

    const tabs = [
        { id: 'recipes', label: 'Recetario', icon: ChefHat, color: 'emerald' },
        { id: 'budget', label: 'Presupuesto', icon: Calculator, color: 'emerald' },
        { id: 'planificaciones', label: 'Planificaciones', icon: ClipboardList, color: 'blue' },
        { id: 'comedores', label: 'Comedores', icon: Store, color: 'emerald' },
        { id: 'grupos', label: 'Grupos', icon: UserCog, color: 'blue' },
        { id: 'catalog', label: 'Catálogo', icon: ShoppingCart, color: 'emerald' },
        { id: 'pos', label: 'Ventas y Demanda', icon: Users, color: 'blue' },
    ];

    return (
        <>
            <div className="min-h-screen bg-slate-50 text-slate-800 font-sans pb-10">
                {/* Header con identidad del sistema, contexto activo y cierre de sesión */}
                <header className="bg-emerald-700 text-white p-4 shadow-md">
                    <div className="max-w-6xl mx-auto flex items-center gap-3">
                        <Activity size={28} />
                        <div className="flex-1">
                            <h1 className="text-2xl font-bold tracking-tight">NutriComedor OSB</h1>
                            <p className="text-xs text-emerald-100">
                                {usuario.nombres} {usuario.apellido_paterno} · {usuario.tipo_documento} {usuario.documento_identidad}
                                {usuario.rol === 'Administrador Sistema' && ' · Admin Sistema'}
                            </p>
                        </div>
                        {/* COM-20: comedor o alcance de trabajo activo (recordado hasta logout) */}
                        <span
                            className="text-xs bg-emerald-800 px-3 py-1 rounded-full border border-emerald-600 shadow-inner items-center gap-1 hidden md:flex max-w-[260px]"
                            title={descripcionContexto(seleccion)}
                        >
                            <MapPin size={12} className="shrink-0" />
                            <span className="truncate">{descripcionContexto(seleccion)}</span>
                        </span>
                        <span className="text-sm bg-emerald-800 px-3 py-1 rounded-full border border-emerald-600 shadow-inner hidden lg:inline-block">
                            Módulo Predictivo Activo
                        </span>
                        {/* COM-19: botón de cerrar sesión (logout manual olvida el comedor) */}
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
                        {activeTab === 'comedores' && <ComedoresView />}
                        {activeTab === 'grupos' && <GruposView />}
                        {activeTab === 'catalog' && <CatalogView />}
                        {activeTab === 'pos' && <POSView />}
                    </div>
                </main>
            </div>

            {/* COM-19: Modal bloqueante de cambio obligatorio de clave */}
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
 * El orden es importante: AuthProvider por fuera para que el login esté
 * disponible incluso antes de cargar los parámetros dinámicos.
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