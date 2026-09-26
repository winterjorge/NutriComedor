/**
 * App.jsx
 * Objetivo: Componente raíz de la aplicación. Orquesta la navegación por pestañas,
 *           el proveedor de parámetros dinámicos, la capa de autenticación (COM-19),
 *           la selección de comedor post-login (COM-20), el módulo multi-comedor
 *           (COM-21), grupos de usuario (COM-22), gestión de usuarios (COM-23), la
 *           diferenciación de vistas por grupo/rol (COM-25), la pestaña de clusters
 *           K-means del recetario (COM-5), la pestaña de propuestas de menú semanal
 *           del motor greedy (COM-8) y el panel de gráficos de ML (COM-5 v4),
 *           todas filtradas por los módulos permitidos del usuario.
 * Uso: Montado en main.jsx mediante <React.StrictMode>. Envuelve toda la app con
 *      AuthProvider y ParametrosProvider.
 *
 * Historial de cambios:
 *  - COM-19/20/21/22/23/25: flujo de login, selección de comedor, pestañas y permisos.
 *  - COM-27: pestañas filtradas por módulos y formularios con cascada de ubicación.
 *  - COM-5: nueva pestaña "Clusters K-Means" ligada al módulo 'recetario'.
 *  - COM-8: nueva pestaña "Propuestas de Menú" ligada al módulo 'propuestas'.
 *  - COM-8 v2: la pestaña "Presupuesto" (generación aleatoria) se RETIRA y se comenta;
 *              su función es reemplazada por "Propuestas de Menú" (motor greedy).
 *  - COM-5 v4 / COM-8 v7 (este archivo): "Clusters K-Means" pasa del módulo 'recetario'
 *              al módulo 'clusters' (EXCLUSIVO del Admin de Sistemas; la línea anterior
 *              queda comentada por trazabilidad) y se agrega la pestaña "Modelos ML"
 *              (módulo 'modelos_ml', también exclusiva del Admin), montando ModelosMLView.
 */
import React, { useState, useEffect } from 'react';
import {
    ChefHat, Calculator, ShoppingCart, Activity, Users, ClipboardList,
    LogOut, Store, UserCog, Loader2, MapPin, Contact, BarChart3, PieChart,
    Sparkles,  // COM-8: ícono de la pestaña "Propuestas de Menú"
    LineChart  // COM-5 v4: ícono de la pestaña "Modelos ML"
} from 'lucide-react';
import { RecipesView } from './components/recipes/RecipesView';
import { ClusterRecetasView } from './components/recipes/ClusterRecetasView';
// COM-5 v4: panel de gráficos de Machine Learning (exclusivo Admin de Sistemas)
import { ModelosMLView } from './components/ml/ModelosMLView';
// COM-8 v2: import COMENTADO. La vista de Presupuesto (generación aleatoria de menús)
// fue reemplazada por GenerarPropuestasView (motor greedy search). Se conserva la
// línea comentada para trazabilidad; el archivo BudgetView.jsx NO se elimina.
// import { BudgetView } from './components/budget/BudgetView';
import { PlanificacionesView } from './components/budget/PlanificacionesView';
// COM-8: vista de propuestas de menú semanal (motor greedy search)
import { GenerarPropuestasView } from './components/budget/GenerarPropuestasView';
import { CatalogView } from './components/catalog/CatalogView';
import { POSView } from './components/pos/POSView';
import { ComedoresView } from './components/comedores/ComedoresView';
import { GruposView } from './components/grupos/GruposView';
import { ReportesView } from './components/reportes/ReportesView';
import { GestionUsuariosSistemaView } from './components/usuarios/GestionUsuariosSistemaView';
import { GestionUsuariosComedorView } from './components/usuarios/GestionUsuariosComedorView';
import { ParametrosProvider } from './context/ParametrosContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginView } from './components/auth/LoginView';
import { ModalCambioClave } from './components/auth/ModalCambioClave';
import { SeleccionComedorView } from './components/auth/SeleccionComedorView';
import { api } from './services/api';

// COM-25: módulos de administración que abren el panel global de usuarios
const MODULOS_ADMIN = ['municipalidades', 'roles', 'bloqueos', 'vistas'];

// COM-25 + COM-5 + COM-8 + COM-5 v4: catálogo de pestañas con su módulo requerido
const TABS_BASE = [
    { id: 'recipes', label: 'Recetario', icon: ChefHat, color: 'emerald', modulo: 'recetario' },
    // COM-5 v4 (trazabilidad): línea ANTERIOR comentada. Hasta COM-5 v3 la pestaña de
    // clusters se gateaba por el módulo 'recetario' (visible para Directivo/Operativo);
    // desde COM-5 v4 es exclusiva del Admin de Sistemas vía módulo 'clusters'.
    // { id: 'clusters', label: 'Clusters K-Means', icon: PieChart, color: 'emerald', modulo: 'recetario' }, // COM-5 v1
    { id: 'clusters', label: 'Clusters K-Means', icon: PieChart, color: 'emerald', modulo: 'clusters' }, // COM-5 v4: solo Admin
    // COM-5 v4: panel de gráficos de validación de los modelos ML (solo Admin)
    { id: 'modelos_ml', label: 'Modelos ML', icon: LineChart, color: 'blue', modulo: 'modelos_ml' },
    // COM-8 v2: pestaña RETIRADA (se comenta, no se borra): su esquema de generación
    // aleatoria de menús fue reemplazado por el motor greedy de "Propuestas de Menú".
    // { id: 'budget', label: 'Presupuesto', icon: Calculator, color: 'emerald', modulo: 'presupuesto' },
    { id: 'planificaciones', label: 'Planificaciones', icon: ClipboardList, color: 'blue', modulo: 'planificaciones' },
    // COM-8: propuestas del motor greedy; módulo 'propuestas' sembrado para
    // Directivo (Presidente/Tesorero/Secretario) y Operativo (Cocinero)
    { id: 'propuestas', label: 'Propuestas de Menú', icon: Sparkles, color: 'emerald', modulo: 'propuestas' },
    { id: 'comedores', label: 'Comedores', icon: Store, color: 'emerald', modulo: 'comedores' },
    { id: 'grupos', label: 'Grupos', icon: UserCog, color: 'blue', modulo: 'grupos' },
    { id: 'reportes', label: 'Reportes', icon: BarChart3, color: 'blue', modulo: 'reportes' },
    { id: 'catalog', label: 'Catálogo', icon: ShoppingCart, color: 'emerald', modulo: 'catalogo' },
    { id: 'pos', label: 'Ventas y Demanda', icon: Users, color: 'blue', modulo: 'ventas' },
];

// COM-25: pestaña de gestión de usuarios (panel global o de comedor)
const TAB_USUARIOS = { id: 'usuarios', label: 'Usuarios', icon: Contact, color: 'blue', modulo: null };

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

    // COM-25: módulos efectivos del usuario en sesión
    const [misModulos, setMisModulos] = useState([]);
    const [cargandoModulos, setCargandoModulos] = useState(true);
    // COM-23: perfil de gestión de comedor (panel de usuarios por comedor)
    const [perfilGestion, setPerfilGestion] = useState(null);

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

    // COM-20: verificando comedor recordado
    if (validando) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-emerald-700 to-emerald-900 flex flex-col items-center justify-center gap-3">
                <Loader2 className="animate-spin text-white" size={44} />
                <p className="text-emerald-100 text-sm">Verificando su comedor de trabajo...</p>
            </div>
        );
    }

    // COM-20: con sesión pero sin selección => pantalla de selección
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

    // COM-25: pestañas visibles según módulos permitidos
    const tieneModulosAdmin = MODULOS_ADMIN.some(m => misModulos.includes(m));
    const puedeVerUsuarios = tieneModulosAdmin || perfilGestion === 'COMEDOR_ADMIN';

    // COM-8 v2: compatibilidad de módulos. La pestaña "Presupuesto" fue retirada y
    // reemplazada por "Propuestas de Menú"; quien conservaba el módulo 'presupuesto'
    // mantiene visibilidad de propuestas aunque el seed 'propuestas' no se le aplicara.
    const modulosEfectivos = (misModulos.includes('presupuesto') && !misModulos.includes('propuestas'))
        ? [...misModulos, 'propuestas']
        : misModulos;

    // COM-8 v2: el filtro usa modulosEfectivos (línea anterior comentada abajo).
    // const tabs = TABS_BASE.filter(t => misModulos.includes(t.modulo));  // COM-8 v2: reemplazada
    const tabs = TABS_BASE.filter(t => modulosEfectivos.includes(t.modulo));
    if (puedeVerUsuarios) {
        const idx = tabs.findIndex(t => t.id === 'comedores');
        tabs.splice(idx === -1 ? tabs.length : idx, 0, TAB_USUARIOS);
    }

    // Mantiene activa una pestaña visible
    if (tabs.length > 0 && !tabs.some(t => t.id === activeTab)) {
        setTimeout(() => setActiveTab(tabs[0].id), 0);
    }

    // Sin módulos asignados
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
                {/* Header */}
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
                        <div className="p-16 text-center text-emerald-600">
                            <Loader2 className="animate-spin mx-auto" size={32} />
                            <p className="text-sm mt-2 text-slate-500">Cargando sus módulos permitidos...</p>
                        </div>
                    ) : (
                        <>
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

                            {/* Contenedor de vistas */}
                            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 min-h-[500px]">
                                {activeTab === 'recipes' && <RecipesView />}
                                {activeTab === 'clusters' && <ClusterRecetasView />} {/* COM-5 / COM-5 v4: módulo 'clusters' */}
                                {activeTab === 'modelos_ml' && <ModelosMLView />} {/* COM-5 v4: panel ML solo Admin */}
                                {/* COM-8 v2: render COMENTADO de la vista Presupuesto retirada.
                                    Su esquema de generación aleatoria fue reemplazado por el
                                    motor greedy de Propuestas de Menú. */}
                                {/* {activeTab === 'budget' && <BudgetView />} */}
                                {activeTab === 'planificaciones' && <PlanificacionesView />}
                                {activeTab === 'propuestas' && <GenerarPropuestasView />} {/* COM-8 */}
                                {activeTab === 'comedores' && <ComedoresView />}
                                {activeTab === 'grupos' && <GruposView />}
                                {activeTab === 'reportes' && <ReportesView />}
                                {activeTab === 'catalog' && <CatalogView />}
                                {activeTab === 'pos' && <POSView />}
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

            {/* COM-19: cambio obligatorio de clave */}
            {pendienteCambio && (
                <ModalCambioClave usuario={usuario} onExito={completarCambioClave} onSalir={cerrarSesion} />
            )}
        </>
    );
}

export default function App() {
    return (
        <AuthProvider>
            <ParametrosProvider>
                <AppContent />
            </ParametrosProvider>
        </AuthProvider>
    );
}