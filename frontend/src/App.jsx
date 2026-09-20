/**
 * App.jsx
 * Objetivo: Componente raíz de la aplicación. Orquesta la navegación por pestañas,
 *           el proveedor de parámetros dinámicos, la capa de autenticación (COM-19),
 *           la selección de comedor post-login (COM-20), el módulo multi-comedor
 *           (COM-21), grupos de usuario (COM-22), gestión de usuarios (COM-23) y la
 *           diferenciación de vistas por grupo/rol (COM-25): cada pestaña se muestra
 *           solo si el usuario posee el módulo correspondiente en la matriz de permisos.
 * Uso: Montado en main.jsx mediante <React.StrictMode>. Envuelve toda la app con
 *      AuthProvider y ParametrosProvider.
 *
 * Historial de cambios:
 *  - Versión base: navegación por pestañas con ParametrosProvider.
 *  - COM-19: flujo de login (AuthContext), modal de cambio de clave obligatorio y
 *    botón de cerrar sesión en el header.
 *  - COM-20: gate de selección de comedor (spinner `validando`, SeleccionComedorView)
 *    y contexto activo en el header.
 *  - COM-21: pestaña "Comedores" con ComedoresView.
 *  - COM-22: pestaña "Grupos" con GruposView.
 *  - COM-23: pestaña "Usuarios" con panel global o de comedor según perfil.
 *  - COM-25: pestañas filtradas por `misModulos` (matriz rol -> módulos); nueva
 *    pestaña "Reportes" (módulo reportes); sub-pestañas del panel de administración
 *    filtradas por módulos (municipalidades / roles / bloqueos / vistas).
 */
import React, { useState, useEffect } from 'react';
import {
    ChefHat, Calculator, ShoppingCart, Activity, Users, ClipboardList,
    LogOut, Store, UserCog, Loader2, MapPin, Contact, BarChart3
} from 'lucide-react';
import { RecipesView } from './components/recipes/RecipesView';
import { BudgetView } from './components/budget/BudgetView';
import { PlanificacionesView } from './components/budget/PlanificacionesView';
import { CatalogView } from './components/catalog/CatalogView';
import { POSView } from './components/pos/POSView';
import { ComedoresView } from './components/comedores/ComedoresView';
import { GruposView } from './components/grupos/GruposView';
import { ReportesView } from './components/reportes/ReportesView';
// COM-23: paneles de gestión de usuarios (global y por comedor)
import { GestionUsuariosSistemaView } from './components/usuarios/GestionUsuariosSistemaView';
import { GestionUsuariosComedorView } from './components/usuarios/GestionUsuariosComedorView';
import { ParametrosProvider } from './context/ParametrosContext';
// COM-19/COM-20: autenticación, cambio de clave y selección de comedor
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginView } from './components/auth/LoginView';
import { ModalCambioClave } from './components/auth/ModalCambioClave';
import { SeleccionComedorView } from './components/auth/SeleccionComedorView';
import { api } from './services/api';

// COM-25: módulos de administración que abren el panel global de usuarios
const MODULOS_ADMIN = ['municipalidades', 'roles', 'bloqueos', 'vistas'];

// COM-25: catálogo de pestañas con su módulo requerido (matriz rol -> módulos)
const TABS_BASE = [
    { id: 'recipes', label: 'Recetario', icon: ChefHat, color: 'emerald', modulo: 'recetario' },
    { id: 'budget', label: 'Presupuesto', icon: Calculator, color: 'emerald', modulo: 'presupuesto' },
    { id: 'planificaciones', label: 'Planificaciones', icon: ClipboardList, color: 'blue', modulo: 'planificaciones' },
    { id: 'comedores', label: 'Comedores', icon: Store, color: 'emerald', modulo: 'comedores' },
    { id: 'grupos', label: 'Grupos', icon: UserCog, color: 'blue', modulo: 'grupos' },
    { id: 'reportes', label: 'Reportes', icon: BarChart3, color: 'blue', modulo: 'reportes' },
    { id: 'catalog', label: 'Catálogo', icon: ShoppingCart, color: 'emerald', modulo: 'catalogo' },
    { id: 'pos', label: 'Ventas y Demanda', icon: Users, color: 'blue', modulo: 'ventas' },
];

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

function AppContent() {
    const [activeTab, setActiveTab] = useState('pos');
    const { usuario, pendienteCambio, completarCambioClave, cerrarSesion, seleccion, validando } = useAuth();

    // COM-25: módulos efectivos del usuario en sesión (membresías activas + roles temporales)
    const [misModulos, setMisModulos] = useState([]);
    const [cargandoModulos, setCargandoModulos] = useState(true);

    // COM-23: perfil de gestión de comedor (fallback para el panel por comedor cuando
    // el usuario no posee módulos de administración global en la matriz COM-25).
    const [perfilGestion, setPerfilGestion] = useState(null);

    // Carga los módulos permitidos del usuario en sesión (COM-25)
    useEffect(() => {
        if (!usuario) {
            setMisModulos([]);
            return;
        }
        let vivo = true;
        const cargar = async () => {
            setCargandoModulos(true);
            try {
                const res = await api.getMisModulos(usuario.id);
                if (vivo) setMisModulos(res.modulos || []);
            } catch (e) {
                if (vivo) setMisModulos([]);
            } finally {
                if (vivo) setCargandoModulos(false);
            }
        };
        cargar();
        return () => { vivo = false; };
    }, [usuario]);

    // COM-23: determina si el usuario puede gestionar usuarios de comedor
    // (Directivo con rol de gestión o Administrativo con cobertura).
    useEffect(() => {
        if (!usuario) {
            setPerfilGestion(null);
            return;
        }
        const determinar = async () => {
            try {
                const membresias = await api.getGruposDeUsuario(usuario.id);
                const ROLES_GESTION = ['Presidente', 'Tesorero'];
                const cubreComedores = membresias.some(m =>
                    m.estado_activo && (
                        m.ambito === 'GLOBAL' ||
                        (m.ambito === 'COMEDOR' && m.grupo === 'Directivo' && ROLES_GESTION.includes(m.rol))
                    )
                );
                setPerfilGestion(cubreComedores ? 'COMEDOR_ADMIN' : null);
            } catch (e) {
                setPerfilGestion(null);
            }
        };
        determinar();
    }, [usuario]);

    // COM-19: sin sesión -> login
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

    // COM-20: con sesión pero sin selección => pantalla de selección de comedor
    if (!seleccion) {
        return (
            <>
                <SeleccionComedorView />
                {pendienteCambio && (
                    <ModalCambioClave usuario={usuario} onExito={completarCambioClave} onSalir={cerrarSesion} />
                )}
            </>
        );
    }

    // COM-25: pestañas visibles según los módulos permitidos del usuario
    const tieneModulosAdmin = MODULOS_ADMIN.some(m => misModulos.includes(m));
    const puedeVerUsuarios = tieneModulosAdmin || perfilGestion === 'COMEDOR_ADMIN';

    const tabs = TABS_BASE.filter(t => misModulos.includes(t.modulo));
    if (puedeVerUsuarios) {
        tabs.splice(3, 0, { id: 'usuarios', label: 'Usuarios', icon: Contact, color: 'blue', modulo: null });
    }

    // Mantener activa una pestaña visible (ajuste cuando cambian los permisos)
    if (tabs.length > 0 && !tabs.some(t => t.id === activeTab)) {
        // Se difiere al render para no mutar estado durante el render
        setTimeout(() => setActiveTab(tabs[0].id), 0);
    }

    // Sin módulos asignados: mensaje informativo (sin pestañas)
    if (!cargandoModulos && tabs.length === 0) {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
                <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8 max-w-md text-center">
                    <Activity size={36} className="text-emerald-600 mx-auto mb-3" />
                    <h2 className="text-lg font-bold text-slate-800 mb-2">Sin módulos asignados</h2>
                    <p className="text-sm text-slate-600">
                        Su usuario no tiene módulos permitidos en este momento. Consulte con el
                        administrador del sistema para que le asigne los accesos correspondientes.
                    </p>
                    <button
                        onClick={cerrarSesion}
                        className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                        Cerrar sesión
                    </button>
                </div>
            </div>
        );
    }

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
                        {/* COM-19: logout manual (olvida sesión y comedor recordado) */}
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
                    {cargandoModulos ? (
                        // COM-25: mientras se calculan los módulos permitidos
                        <div className="p-16 text-center text-emerald-600">
                            <Loader2 className="animate-spin mx-auto" size={32} />
                            <p className="text-sm mt-2 text-slate-500">Cargando sus módulos permitidos...</p>
                        </div>
                    ) : (
                        <>
                            {/* Barra de pestañas (solo módulos permitidos) */}
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
                                {activeTab === 'reportes' && <ReportesView />}
                                {activeTab === 'catalog' && <CatalogView />}
                                {activeTab === 'pos' && <POSView />}
                                {/* COM-23/COM-25: panel de gestión según módulos y perfil */}
                                {activeTab === 'usuarios' && tieneModulosAdmin && (
                                    <GestionUsuariosSistemaView modulosPermitidos={misModulos} />
                                )}
                                {activeTab === 'usuarios' && !tieneModulosAdmin && perfilGestion === 'COMEDOR_ADMIN' && (
                                    <GestionUsuariosComedorView />
                                )}
                            </div>
                        </>
                    )}
                </main>
            </div>

            {/* COM-19: modal bloqueante de cambio obligatorio de clave */}
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