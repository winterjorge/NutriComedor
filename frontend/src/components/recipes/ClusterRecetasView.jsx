/**
 * components/recipes/ClusterRecetasView.jsx
 * Objetivo: Vista COM-5 del modelo K-means del recetario: métricas del modelo activo
 *           (silhouette, inercia, recetas aptas/excluidas), tarjetas de los 4 clusters
 *           (Anti-Anemia Premium, Fortalecimiento Balanceado, Ligero y Saludable y
 *           All-Rounder Económico) con su centroide por ración, listado de recetas por
 *           cluster, auditoría de exclusiones (reglas R1-R3) y re-entrenamiento.
 * Uso: Montada por App.jsx como pestaña "Clusters K-Means" (módulo Recetario).
 * Referencia: ticket COM-5 (solo trazabilidad; los nombres obedecen a la funcionalidad).
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
    PieChart, Droplets, Dumbbell, Leaf, Coins, RefreshCw, Loader2,
    AlertCircle, Sparkles, ChevronDown, ChevronUp, Utensils
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalConfirmacion } from '../common/ModalConfirmacion';
import { ModalExito } from '../common/ModalExito';

// Configuración visual de cada cluster (clases literales para Tailwind)
const CONFIG_CLUSTER = {
    1: { icon: Droplets, chip: 'bg-red-100 text-red-700', borde: 'border-red-200', desc: 'Prioritario por salud: máximo aporte de hierro.' },
    2: { icon: Dumbbell, chip: 'bg-blue-100 text-blue-700', borde: 'border-blue-200', desc: 'Proteína y energía para trabajo físico.' },
    3: { icon: Leaf, chip: 'bg-green-100 text-green-700', borde: 'border-green-200', desc: 'Digestión ligera: baja densidad calórica.' },
    4: { icon: Coins, chip: 'bg-amber-100 text-amber-700', borde: 'border-amber-200', desc: 'Máxima nutrición por sol: amortigua el presupuesto.' },
};

// Motivos de exclusión legibles (reglas de negocio COM-5)
const MOTIVOS = {
    contiene_res_o_cerdo: 'Contiene res o cerdo (R2)',
    sin_proteina_permitida: 'Sin proteína permitida (R1)',
    sin_datos_nutricion: 'Sin datos nutricionales',
    sin_precio: 'Sin precio en el scraper',
    precio_alto: 'Precio alto (R3)',
    sin_ingredientes: 'Sin ingredientes registrados',
};

export const ClusterRecetasView = () => {
    const { usuario } = useAuth();

    const [resumen, setResumen] = useState(null);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');

    const [clusterSel, setClusterSel] = useState(null);
    const [recetasCluster, setRecetasCluster] = useState([]);
    const [cargandoRecetas, setCargandoRecetas] = useState(false);

    const [confEntrenar, setConfEntrenar] = useState(false);
    const [entrenando, setEntrenando] = useState(false);

    const [mostrarExcluidas, setMostrarExcluidas] = useState(false);
    const [excluidas, setExcluidas] = useState(null);

    // Carga el resumen del modelo activo (null si aún no se entrena)
    const cargarResumen = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            setResumen(await api.getResumenKmeans());
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, []);

    useEffect(() => { cargarResumen(); }, [cargarResumen]);

    // Recetas del cluster seleccionado
    const verRecetas = async (codigo) => {
        if (clusterSel === codigo) {
            setClusterSel(null);
            return;
        }
        setClusterSel(codigo);
        setCargandoRecetas(true);
        try {
            setRecetasCluster(await api.getClustersKmeans(codigo));
        } catch (e) {
            setError(e.message);
        } finally {
            setCargandoRecetas(false);
        }
    };

    // Re-entrenamiento con confirmación
    const confirmarEntrenar = async () => {
        setConfEntrenar(false);
        setEntrenando(true);
        setError('');
        try {
            const r = await api.entrenarKmeans(usuario.id);
            setExito(`Modelo re-entrenado: ${r.n_recetas} recetas en ${r.k} clusters (silhouette ${r.silhouette}).`);
            setClusterSel(null);
            setExcluidas(null);
            setMostrarExcluidas(false);
            await cargarResumen();
        } catch (e) {
            setError(e.message);
        } finally {
            setEntrenando(false);
        }
    };

    // Auditoría perezosa de recetas excluidas
    const toggleExcluidas = async () => {
        if (!mostrarExcluidas && excluidas === null) {
            try {
                const data = await api.getCandidatasKmeans();
                setExcluidas(data.excluidas || []);
            } catch (e) {
                setError(e.message);
                return;
            }
        }
        setMostrarExcluidas(!mostrarExcluidas);
    };

    const badgeNivel = (nivel) => (
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${nivel === 'bajo' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
            {nivel}
        </span>
    );

    return (
        <div className="animate-in fade-in duration-300">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <PieChart className="text-emerald-600" size={22} /> Clusters K-Means del Recetario
                    </h2>
                    <p className="text-sm text-slate-500">
                        Clasificación nutricional-económica de recetas (energía, hierro, proteína y precio por ración).
                    </p>
                </div>
                {resumen && (
                    <button
                        onClick={() => setConfEntrenar(true)}
                        disabled={entrenando}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                    >
                        {entrenando ? <Loader2 className="animate-spin" size={16} /> : <RefreshCw size={16} />}
                        Re-entrenar modelo
                    </button>
                )}
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {cargando ? (
                <div className="p-12 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={28} /></div>
            ) : !resumen ? (
                /* Sin modelo entrenado */
                <div className="p-12 text-center bg-slate-50 border border-slate-200 rounded-2xl">
                    <Sparkles size={36} className="text-emerald-600 mx-auto mb-3" />
                    <h3 className="font-bold text-slate-800 mb-2">Aún no hay un modelo entrenado</h3>
                    <p className="text-sm text-slate-500 mb-4">
                        Entrene el modelo K-means (k=4) para clasificar el recetario en los perfiles
                        Anti-Anemia, Fortalecimiento, Ligero y All-Rounder Económico.
                    </p>
                    <button
                        onClick={() => setConfEntrenar(true)}
                        disabled={entrenando}
                        className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                    >
                        {entrenando ? 'Entrenando...' : 'Entrenar modelo ahora'}
                    </button>
                </div>
            ) : (
                <>
                    {/* Métricas del modelo */}
                    <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-5">
                        {[
                            ['Silhouette', resumen.silhouette],
                            ['Inercia', resumen.inercia],
                            ['Recetas aptas', resumen.n_recetas],
                            ['Excluidas', resumen.n_excluidas],
                            ['Clusters (k)', resumen.k],
                            ['Entrenado', new Date(resumen.fecha_entrenamiento).toLocaleDateString('es-PE')],
                        ].map(([label, valor]) => (
                            <div key={label} className="bg-white border border-slate-200 rounded-xl p-3 text-center">
                                <p className="text-lg font-bold text-slate-800">{valor}</p>
                                <p className="text-[11px] text-slate-500">{label}</p>
                            </div>
                        ))}
                    </div>

                    {/* Tarjetas de clusters */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
                        {(resumen.clusters || []).map(c => {
                            const cfg = CONFIG_CLUSTER[c.cluster_codigo] || CONFIG_CLUSTER[4];
                            const Icon = cfg.icon;
                            const centroide = resumen.centroides?.[String(c.cluster_codigo)] || {};
                            const activo = clusterSel === c.cluster_codigo;
                            return (
                                <div key={c.cluster_codigo}
                                    className={`bg-white border rounded-xl p-4 ${activo ? cfg.borde + ' ring-2 ring-emerald-300' : 'border-slate-200'}`}>
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className={`p-2 rounded-lg ${cfg.chip}`}><Icon size={16} /></span>
                                        <div>
                                            <p className="font-bold text-slate-800 text-sm">{c.cluster_etiqueta}</p>
                                            <p className="text-[11px] text-slate-500">{cfg.desc}</p>
                                        </div>
                                        <span className="ml-auto text-xs font-bold text-slate-600">{c.n_recetas} recetas</span>
                                    </div>
                                    <div className="grid grid-cols-4 gap-2 my-3 text-center">
                                        {[
                                            ['kcal', centroide.energia_kcal ?? c.energia_prom],
                                            ['Fe mg', centroide.hierro_mg ?? c.hierro_prom],
                                            ['Prot g', centroide.proteina_g ?? c.proteina_prom],
                                            ['S/', centroide.precio_soles ?? c.precio_prom],
                                        ].map(([label, v]) => (
                                            <div key={label} className="bg-slate-50 rounded-lg py-1.5">
                                                <p className="text-sm font-bold text-slate-700">{v}</p>
                                                <p className="text-[10px] text-slate-500">{label}</p>
                                            </div>
                                        ))}
                                    </div>
                                    <p className="text-[11px] text-slate-500 mb-2">
                                        Rango de precio: S/ {c.precio_min} – S/ {c.precio_max} por ración (centroide del modelo).
                                    </p>
                                    <button
                                        onClick={() => verRecetas(c.cluster_codigo)}
                                        className="w-full flex items-center justify-center gap-1 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-medium transition-colors"
                                    >
                                        <Utensils size={12} />
                                        {activo ? 'Ocultar recetas' : 'Ver recetas'}
                                        {activo ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                                    </button>
                                </div>
                            );
                        })}
                    </div>

                    {/* Listado de recetas del cluster seleccionado */}
                    {clusterSel && (
                        <div className="overflow-x-auto rounded-lg border border-slate-200 mb-5">
                            <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                                <thead>
                                    <tr className="bg-slate-100 text-slate-600">
                                        <th className="p-3 font-semibold">Receta</th>
                                        <th className="p-3 font-semibold">Cluster</th>
                                        <th className="p-3 font-semibold">kcal</th>
                                        <th className="p-3 font-semibold">Prot (g)</th>
                                        <th className="p-3 font-semibold">Fe (mg)</th>
                                        <th className="p-3 font-semibold">Fibra (g)</th>
                                        <th className="p-3 font-semibold">Precio</th>
                                        <th className="p-3 font-semibold">Nivel</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200">
                                    {cargandoRecetas ? (
                                        <tr><td colSpan="8" className="p-6 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={22} /></td></tr>
                                    ) : recetasCluster.length === 0 ? (
                                        <tr><td colSpan="8" className="p-6 text-center text-slate-500">Sin recetas en este cluster.</td></tr>
                                    ) : recetasCluster.map(r => (
                                        <tr key={r.receta_id} className="hover:bg-slate-50">
                                            <td className="p-3 font-medium text-slate-800">{r.nombre}</td>
                                            <td className="p-3 text-slate-600">{r.cluster_etiqueta}</td>
                                            <td className="p-3 text-slate-600">{r.energia_kcal}</td>
                                            <td className="p-3 text-slate-600">{r.proteina_g}</td>
                                            <td className="p-3 text-slate-600">{r.hierro_mg}</td>
                                            <td className="p-3 text-slate-600">{r.fibra_g}</td>
                                            <td className="p-3 text-slate-600">S/ {r.precio_soles}</td>
                                            <td className="p-3">{badgeNivel(r.nivel_precio)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}

                    {/* Auditoría de exclusiones (reglas R1-R3) */}
                    <button
                        onClick={toggleExcluidas}
                        className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-800 transition-colors mb-2"
                    >
                        {mostrarExcluidas ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        Ver recetas excluidas del modelo ({resumen.n_excluidas})
                    </button>
                    {mostrarExcluidas && excluidas !== null && (
                        <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1 max-h-56 overflow-y-auto">
                            {excluidas.length === 0 ? (
                                <p className="text-xs text-slate-500">No hay recetas excluidas.</p>
                            ) : excluidas.map(e => (
                                <div key={e.receta_id} className="flex justify-between items-center text-xs">
                                    <span className="text-slate-700">{e.nombre}</span>
                                    <span className="px-2 py-0.5 bg-red-100 text-red-600 rounded-full font-bold">
                                        {MOTIVOS[e.motivo] || e.motivo}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}

            <ModalConfirmacion
                isOpen={confEntrenar}
                onClose={() => setConfEntrenar(false)}
                onConfirm={confirmarEntrenar}
                mensaje="¿Re-entrenar el modelo K-means con los precios y recetas actuales? El modelo activo será reemplazado."
                tipo="warning"
            />
            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};