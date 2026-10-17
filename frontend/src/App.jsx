/**
App.jsx
Objetivo: Componente raíz de la aplicación. Orquesta la navegación por pestañas,
el proveedor de parámetros dinámicos, la capa de autenticación (COM-19),
la selección de comedor post-login (COM-20), el módulo multi-comedor
(COM-21), grupos de usuario (COM-22), gestión de usuarios (COM-23), la
diferenciación de vistas por grupo/rol (COM-25), la pestaña de clusters
K-means del recetario (COM-5), la pestaña de propuestas de menú semanal
del motor greedy (COM-8) y el panel de gráficos de ML (COM-5 v4),
todas filtradas por los módulos permitidos del usuario.
Uso: Montado en main.jsx mediante <React.StrictMode>. Envuelve toda la app con
AuthProvider y ParametrosProvider.
Historial de cambios:
COM-19/20/21/22/23/25: flujo de login, selección de comedor, pestañas y permisos.
COM-27: pestañas filtradas por módulos y formularios con cascada de ubicación.
COM-5: nueva pestaña "Clusters K-Means" ligada al módulo 'recetario'.
COM-8: nueva pestaña "Propuestas de Menú" ligada al módulo 'propuestas'.
COM-8 v2: la pestaña "Presupuesto" (generación aleatoria) se RETIRA y se comenta;
su función es reemplazada por "Propuestas de Menú" (motor greedy).
COM-5 v4 / COM-8 v7: "Clusters K-Means" pasa al módulo 'clusters' (solo Admin) y
se agrega "Modelos ML" (módulo 'modelos_ml', solo Admin).
COM-37: se AGREGA la pestaña "Gestión de Ingredientes" (módulo 'gestion_ingredientes').
COM-59A: se AGREGAN dos pestañas del modelo de autogestión:
* "Subsidio de Víveres" (módulo 'subsidio'): Admin de Sistemas y Directivos
gestionan; perfiles municipales/auditoría solo lectura (gate backend).
* "Precios de Venta" (módulo 'precios_venta'): exclusivo Admin de Sistemas.
Solo hay 4 adiciones marcadas COM-59A (2 íconos, 2 imports, 2 entradas en
TABS_BASE y 2 líneas de render); ninguna línea existente se elimina.
COM-69: se AGREGA la pestaña "Reporte Subsidio" (módulo 'subsidio'):
vista de rendición mensual de uso del subsidio por comedor para el
administrativo municipal (3 adiciones: import del ícono ClipboardCheck,
import de ReporteSubsidioView, entrada en TABS_BASE y línea de render).
Ninguna línea existente se elimina.
COM-43: se AGREGA la pestaña "Scraper SISAP" (módulo 'modelos_ml'):
ejecución web y auditoría del scraper (import Database + ScraperAdminView).
COM-78: header mejorado: nombre de la municipalidad visible para el perfil
Administrativo y "Módulo Predictivo Activo" SOLO para Admin de Sistemas.
COM-81: foco visible de marca (anillo esmeralda focus-visible) en botones del
shell en lugar del outline negro del navegador.
COM-41 (este archivo): la barra horizontal de pestañas se REEMPLAZA por un
SIDEBAR lateral con 6 categorías en acordeón (Cocina, Operación, Gestión,
Inteligencia, Configuración y Sistema), fijo en desktop (>=lg) y drawer
deslizante con hamburguesa + backdrop en móvil/tablet. El catálogo TABS_BASE
y todos los gates de módulos/permisos se conservan EXACTOS; solo cambia el
contenedor de navegación. La categoría del tab activo se abre automáticamente
y la elección del acordeón se persiste en localStorage ('nutri_sidebar_cat').
La barra horizontal anterior queda COMENTADA por trazabilidad.
*/
import React, { useState, useEffect } from 'react';
import {
  ChefHat, Calculator, ShoppingCart, Activity, Users, ClipboardList,
  LogOut, Store, UserCog, Loader2, MapPin, Contact, BarChart3, PieChart,
  Sparkles,   // COM-8: ícono de la pestaña "Propuestas de Menú"
  LineChart,  // COM-5 v4: ícono de la pestaña "Modelos ML"
  Package,    // COM-37: ícono de la pestaña "Gestión de Ingredientes"
  Gift,       // COM-59A: ícono de la pestaña "Subsidio de Víveres"
  Coins,      // COM-59A: ícono de la pestaña "Precios de Venta"
  ClipboardCheck, // COM-69: ícono de la pestaña "Reporte Subsidio"
  Database,   // COM-43: ícono de la pestaña "Scraper SISAP"
  Menu, X,    // COM-41: hamburguesa del drawer móvil y botón de cierre
  Settings,   // COM-41: ícono de la categoría "Configuración"
  Shield      // COM-41: ícono de la categoría "Sistema" (solo Admin)
} from 'lucide-react';
import { RecipesView } from './components/recipes/RecipesView';
import { ClusterRecetasView } from './components/recipes/ClusterRecetasView';
// COM-5 v4: panel de gráficos de validación de los modelos ML (exclusivo Admin de Sistemas)
import { ModelosMLView } from './components/ml/ModelosMLView';
// COM-37: gestión de ingredientes y precios manuales con vigencia (exclusivo Admin)
import { GestionIngredientesView } from './components/ingredients/GestionIngredientesView';
// COM-59A: subsidio mensual de víveres por comedor (Admin + Directivos gestionan)
import { SubsidioView } from './components/subsidio/SubsidioView';
// COM-69: reporte de uso del subsidio por comedor y mes (lectura municipal/directiva)
import { ReporteSubsidioView } from './components/subsidio/ReporteSubsidioView';
// COM-59A: precios de venta con historial (exclusivo Admin de Sistemas)
import { PreciosVentaView } from './components/precios/PreciosVentaView';
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
// COM-43: panel de ejecución/auditoría del scraper SISAP (solo Admin de Sistemas)
import { ScraperAdminView } from './components/scraper/ScraperAdminView';
// COM-41: navegación lateral agrupada por categorías (desktop + drawer móvil)
import { SidebarNav } from './components/layout/SidebarNav';

// COM-25: módulos de administración que abren el panel global de usuarios
const MODULOS_ADMIN = ['municipalidades', 'roles', 'bloqueos', 'vistas'];

// COM-25 + COM-5 + COM-8 + COM-5 v4 + COM-37 + COM-59A + COM-69 + COM-43: catálogo de pestañas
const TABS_BASE = [
  { id: 'recipes', label: 'Recetario', icon: ChefHat, color: 'emerald', modulo: 'recetario' },
  // COM-5 v4 (trazabilidad): línea ANTERIOR comentada. Hasta COM-5 v3 la pestaña de
  // clusters se gateaba por el módulo 'recetario' (visible para Directivo/Operativo);
  // desde COM-5 v4 es exclusiva del Admin de Sistemas vía módulo 'clusters'.
  // { id: 'clusters', label: 'Clusters K-Means', icon: PieChart, color: 'emerald', modulo: 'recetario' }, // COM-5 v1
  { id: 'clusters', label: 'Clusters K-Means', icon: PieChart, color: 'emerald', modulo: 'clusters' }, // COM-5 v4: solo Admin
  // COM-5 v4: panel de gráficos de validación de los modelos ML (solo Admin)
  { id: 'modelos_ml', label: 'Modelos ML', icon: LineChart, color: 'blue', modulo: 'modelos_ml' },
  // COM-43: ejecución web y auditoría del scraper SISAP. Gateada por el módulo
  // 'modelos_ml' (sembrado solo para el Admin de Sistemas); el backend re-valida.
  { id: 'scraper', label: 'Scraper SISAP', icon: Database, color: 'blue', modulo: 'modelos_ml' },
  // COM-37: gestión de ingredientes y precios manuales con vigencia (solo Admin)
  { id: 'gestion_ingredientes', label: 'Gestión de Ingredientes', icon: Package, color: 'amber', modulo: 'gestion_ingredientes' },
  // COM-59A: subsidio mensual de víveres (módulo 'subsidio': Admin gestiona todo;
  // Directivos gestionan su comedor; municipales/auditoría solo lectura vía backend)
  { id: 'subsidio', label: 'Subsidio de Víveres', icon: Gift, color: 'emerald', modulo: 'subsidio' },
  // COM-69: reporte de uso del subsidio por comedor y mes (misma puerta 'subsidio';
  // el backend filtra comedores visibles según alcance del usuario)
  { id: 'reporte_subsidio', label: 'Reporte Subsidio', icon: ClipboardCheck, color: 'blue', modulo: 'subsidio' },
  // COM-59A: precios de venta con historial (módulo 'precios_venta': solo Admin)
  { id: 'precios_venta', label: 'Precios de Venta', icon: Coins, color: 'amber', modulo: 'precios_venta' },
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

// =========================================================================
// COM-41: CATEGORÍAS DEL SIDEBAR (agrupación de negocio validada con producto)
// =========================================================================
const CATEGORIAS = [
  { clave: 'cocina', label: 'Cocina', icon: ChefHat },
  { clave: 'operacion', label: 'Operación', icon: Activity },
  { clave: 'gestion', label: 'Gestión', icon: Gift },
  { clave: 'inteligencia', label: 'Inteligencia', icon: BarChart3 },
  { clave: 'configuracion', label: 'Configuración', icon: Settings },
  // COM-41: categoría técnica exclusiva del Admin de Sistemas (decisión de producto)
  { clave: 'sistema', label: 'Sistema', icon: Shield },
];
// COM-41: mapa tab -> categoría. Todo tab nuevo DEBE registrarse aquí o quedará
// sin contenedor de navegación (fail-safe: se ignora en el agrupado).
const MAPA_CATEGORIAS = {
  recipes: 'cocina', propuestas: 'cocina', planificaciones: 'cocina', catalog: 'cocina',
  pos: 'operacion',
  subsidio: 'gestion', reporte_subsidio: 'gestion', precios_venta: 'gestion',
  reportes: 'inteligencia',
  comedores: 'configuracion', grupos: 'configuracion', usuarios: 'configuracion',
  clusters: 'sistema', modelos_ml: 'sistema', scraper: 'sistema', gestion_ingredientes: 'sistema',
};
// COM-41: clave de persistencia del acordeón
const LS_CATEGORIA = 'nutri_sidebar_cat';

/**
COM-20: describe el contexto de trabajo activo para exhibirlo en el header.
COM-78: para el perfil Administrativo se complementa con la municipalidad resuelta
en AppContent (infoMunicipal), no solo con el contexto de selección.
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
  // COM-78: municipalidad del perfil Administrativo para el header
  const [infoMunicipal, setInfoMunicipal] = useState(null);
  // COM-41: categoría abierta del acordeón (persistida) y drawer móvil
  const [catAbierta, setCatAbierta] = useState(() => {
    try {
      return localStorage.getItem(LS_CATEGORIA) || MAPA_CATEGORIAS['pos'];
    } catch (e) {
      return MAPA_CATEGORIAS['pos'];
    }
  });
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  // COM-78: resolver nombre y distrito de la municipalidad del usuario Administrativo
  useEffect(() => {
    if (!usuario || usuario.rol === 'Administrador Sistema') {
      setInfoMunicipal(null);
      return;
    }
    let vivo = true;
    const cargar = async () => {
      try {
        const membresias = await api.getGruposDeUsuario(usuario.id);
        const mun = membresias.find(m => m.grupo === 'Administrativo' && m.estado_activo);
        if (!vivo) return;
        if (mun && (mun.municipalidad_nombre || mun.nombre)) {
          setInfoMunicipal({
            nombre: mun.municipalidad_nombre || mun.nombre || 'Municipalidad',
            distrito: mun.distrito || mun.municipalidad_distrito || '',
          });
        } else {
          setInfoMunicipal(null);
        }
      } catch (e) {
        if (vivo) setInfoMunicipal(null);
      }
    };
    cargar();
    return () => { vivo = false; };
  }, [usuario]);

  // COM-41: persistencia del acordeón
  useEffect(() => {
    try {
      if (catAbierta) localStorage.setItem(LS_CATEGORIA, catAbierta);
    } catch (e) { /* almacenamiento no disponible: se ignora */ }
  }, [catAbierta]);

  // COM-41: la categoría del tab activo se abre automáticamente (sigue a la selección)
  useEffect(() => {
    const cat = MAPA_CATEGORIAS[activeTab];
    if (cat) setCatAbierta(cat);
  }, [activeTab]);

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

  // COM-41: agrupado de tabs visibles por categoría; se omiten categorías vacías
  const categoriasVisibles = CATEGORIAS
    .map(cat => ({ ...cat, tabs: tabs.filter(t => MAPA_CATEGORIAS[t.id] === cat.clave) }))
    .filter(cat => cat.tabs.length > 0);

  // COM-41: selección desde el sidebar (desktop o drawer)
  const seleccionarTab = (id) => {
    setActiveTab(id);
    setCatAbierta(MAPA_CATEGORIAS[id] || null);
    setDrawerOpen(false);
  };

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
            className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
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
            {/* COM-41: hamburguesa del drawer móvil/tablet */}
            <button
              onClick={() => setDrawerOpen(true)}
              className="lg:hidden p-2 bg-emerald-800 hover:bg-emerald-900 rounded-lg border border-emerald-600 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
              title="Abrir menú de navegación"
              aria-label="Abrir menú de navegación"
            >
              <Menu size={18} />
            </button>
            <Activity size={28} className="hidden lg:block" />
            <div className="flex-1">
              <h1 className="text-2xl font-bold tracking-tight">NutriComedor OSB</h1>
              <p className="text-xs text-emerald-100">
                {usuario.nombres} {usuario.apellido_paterno} · {usuario.tipo_documento} {usuario.documento_identidad}
                {usuario.rol === 'Administrador Sistema' && ' · Admin Sistema'}
                {infoMunicipal && ` · ${infoMunicipal.nombre}${infoMunicipal.distrito ? ` (${infoMunicipal.distrito})` : ''}`}
              </p>
            </div>
            <span
              className="text-xs bg-emerald-800 px-3 py-1 rounded-full border border-emerald-600 shadow-inner items-center gap-1 hidden md:flex max-w-[260px]"
              title={descripcionContexto(seleccion)}
            >
              <MapPin size={12} className="shrink-0" />
              <span className="truncate">{descripcionContexto(seleccion)}</span>
            </span>
            {/* COM-78: solo el Admin de Sistemas ve el distintivo del módulo predictivo */}
            {usuario.rol === 'Administrador Sistema' && (
              <span className="text-sm bg-emerald-800 px-3 py-1 rounded-full border border-emerald-600 shadow-inner hidden lg:inline-block">
                Módulo Predictivo Activo
              </span>
            )}
            <button
              onClick={cerrarSesion}
              className="flex items-center gap-2 bg-emerald-800 hover:bg-emerald-900 px-3 py-2 rounded-lg text-sm font-medium transition-colors border border-emerald-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300"
              title="Cerrar sesión"
            >
              <LogOut size={16} />
              <span className="hidden sm:inline">Salir</span>
            </button>
          </div>
        </header>

        {/* COM-41: drawer móvil/tablet del sidebar (backdrop + panel deslizante) */}
        {drawerOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setDrawerOpen(false)} />
            <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-white shadow-xl p-4 overflow-y-auto">
              <div className="flex items-center justify-between mb-3">
                <p className="font-bold text-slate-800 flex items-center gap-2">
                  <Activity size={16} className="text-emerald-600" /> Menú
                </p>
                <button
                  onClick={() => setDrawerOpen(false)}
                  className="p-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-slate-600 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                  title="Cerrar menú"
                  aria-label="Cerrar menú"
                >
                  <X size={16} />
                </button>
              </div>
              <SidebarNav
                categorias={categoriasVisibles}
                activeTab={activeTab}
                onSelect={seleccionarTab}
                catAbierta={catAbierta}
                setCatAbierta={setCatAbierta}
              />
            </div>
          </div>
        )}

        <main className="max-w-6xl mx-auto mt-8 p-4">
          {cargandoModulos ? (
            <div className="p-16 text-center text-emerald-600">
              <Loader2 className="animate-spin mx-auto" size={32} />
              <p className="text-sm mt-2 text-slate-500">Cargando sus módulos permitidos...</p>
            </div>
          ) : (
            /* COM-41: layout de dos columnas: sidebar desktop + contenido */
            <div className="flex gap-6 items-start">
              {/* Sidebar fijo desktop */}
              <aside className="hidden lg:block w-60 shrink-0 sticky top-4">
                <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm">
                  <SidebarNav
                    categorias={categoriasVisibles}
                    activeTab={activeTab}
                    onSelect={seleccionarTab}
                    catAbierta={catAbierta}
                    setCatAbierta={setCatAbierta}
                  />
                </div>
              </aside>
              {/* Contenedor de vistas */}
              <div className="flex-1 min-w-0 bg-white p-6 rounded-xl shadow-sm border border-slate-200 min-h-[500px]">
                {/* COM-41 (trazabilidad): barra horizontal de pestañas RETIRADA y
                    comentada; la navegación vive ahora en SidebarNav (desktop/drawer).
                <div className="flex gap-2 mb-6 border-b border-slate-200 pb-2 overflow-x-auto">
                    {tabs.map(tab => { ... })}
                </div>
                */}
                {activeTab === 'recipes' && <RecipesView />}
                {activeTab === 'clusters' && <ClusterRecetasView />} {/* COM-5 / COM-5 v4: módulo 'clusters' */}
                {activeTab === 'modelos_ml' && <ModelosMLView />} {/* COM-5 v4: panel ML solo Admin */}
                {activeTab === 'scraper' && <ScraperAdminView />} {/* COM-43 */}
                {/* COM-37: gestión de ingredientes y precios manuales (solo Admin) */}
                {activeTab === 'gestion_ingredientes' && <GestionIngredientesView />}
                {/* COM-59A: subsidio mensual de víveres por comedor */}
                {activeTab === 'subsidio' && <SubsidioView />}
                {/* COM-69: reporte de uso del subsidio por comedor y mes */}
                {activeTab === 'reporte_subsidio' && <ReporteSubsidioView />}
                {/* COM-59A: precios de venta con historial (solo Admin) */}
                {activeTab === 'precios_venta' && <PreciosVentaView />}
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
            </div>
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