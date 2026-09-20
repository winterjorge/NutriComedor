/**
 * components/reportes/ReportesView.jsx
 * Objetivo: Pestaña "Reportes" con resumen operativo del sistema: contadores de
 *           comedores, usuarios, recetas y planificaciones guardadas, y el estado
 *           agregado del padrón de ventas del día. Diseñado para Auditor, Presidente
 *           y Tesorero (según matriz de permisos del módulo).
 * Uso: Renderizado por App.jsx en la pestaña "Reportes" cuando el usuario tiene
 *      permiso sobre el módulo 'reportes'.
 * Nota: Los nombres describen funcionalidad (no referencian tickets).
 */
import React, { useState, useEffect } from 'react';
import {
    Store, Users, ChefHat, ClipboardList, Activity, Loader2, AlertCircle,
    TrendingUp, Calendar
} from 'lucide-react';
import { api } from '../../services/api';

export const ReportesView = () => {
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');

    // KPIs agregados
    const [kpis, setKpis] = useState({
        comedores: 0,
        usuarios: 0,
        recetas: 0,
        planificaciones: 0,
        ventasHoy: null
    });

    // Carga agregada de los contadores y el resumen de ventas del día
    useEffect(() => {
        const cargar = async () => {
            setCargando(true);
            setError('');
            try {
                const [comedores, usuarios, recetas, planificaciones, ventasHoy] = await Promise.all([
                    api.getComedores().catch(() => []),
                    api.getUsuarios({ usuario_solicitante_id: 0 }).catch(() => []),
                    api.getRecetas().catch(() => []),
                    api.getPlanificaciones().catch(() => []),
                    api.getVentasHoy().catch(() => null),
                ]);
                setKpis({
                    comedores: Array.isArray(comedores) ? comedores.length : 0,
                    usuarios: Array.isArray(usuarios) ? usuarios.length : 0,
                    recetas: Array.isArray(recetas) ? recetas.length : 0,
                    planificaciones: Array.isArray(planificaciones) ? planificaciones.length : 0,
                    ventasHoy
                });
            } catch (e) {
                setError(e.message);
            } finally {
                setCargando(false);
            }
        };
        cargar();
    }, []);

    // Agrupación de ventas por tipo de comensal (para el gráfico CSS)
    const ventas = kpis.ventasHoy || {};
    const totalVentas = (ventas.social || 0) + (ventas.afiliado || 0) + (ventas.normal || 0);
    const pct = (v) => totalVentas > 0 ? Math.round((v / totalVentas) * 100) : 0;

    const tarjetas = [
        { label: 'Comedores registrados', value: kpis.comedores, icon: Store, color: 'emerald' },
        { label: 'Usuarios del sistema', value: kpis.usuarios, icon: Users, color: 'blue' },
        { label: 'Recetas del recetario', value: kpis.recetas, icon: ChefHat, color: 'amber' },
        { label: 'Planificaciones guardadas', value: kpis.planificaciones, icon: ClipboardList, color: 'purple' },
    ];

    return (
        <div className="animate-in fade-in duration-300">
            <div className="flex flex-wrap justify-between items-center gap-3 mb-5">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <TrendingUp className="text-emerald-600" size={22} /> Reportes
                    </h2>
                    <p className="text-sm text-slate-500">
                        Resumen operativo del sistema y de las ventas del día.
                    </p>
                </div>
                <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1 rounded-full flex items-center gap-1">
                    <Calendar size={12} /> {new Date().toLocaleDateString('es-PE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </span>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {cargando ? (
                <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={28} /></div>
            ) : (
                <>
                    {/* Tarjetas de KPIs */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        {tarjetas.map(t => {
                            const Icon = t.icon;
                            return (
                                <div key={t.label} className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
                                    <div className={`p-3 rounded-lg bg-${t.color}-100 text-${t.color}-700`}>
                                        <Icon size={22} />
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold text-slate-800">{t.value}</p>
                                        <p className="text-xs text-slate-500">{t.label}</p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Panel de ventas del día */}
                    <div className="bg-white border border-slate-200 rounded-xl p-5">
                        <div className="flex flex-wrap justify-between items-center gap-2 mb-4">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <Activity size={18} className="text-emerald-600" /> Ventas del día
                            </h3>
                            <span className="text-sm font-semibold text-slate-700">
                                Total: {totalVentas} raciones
                            </span>
                        </div>

                        {totalVentas === 0 ? (
                            <p className="text-sm text-slate-400 text-center py-8">
                                Aún no hay ventas registradas el día de hoy.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {[
                                    { label: 'Social', value: ventas.social || 0, color: 'bg-red-500' },
                                    { label: 'Afiliado', value: ventas.afiliado || 0, color: 'bg-blue-500' },
                                    { label: 'Normal', value: ventas.normal || 0, color: 'bg-emerald-500' },
                                ].map(barra => (
                                    <div key={barra.label}>
                                        <div className="flex justify-between text-xs text-slate-600 mb-1">
                                            <span>{barra.label}</span>
                                            <span className="font-semibold">{barra.value} ({pct(barra.value)}%)</span>
                                        </div>
                                        <div className="w-full bg-slate-100 rounded-full h-3">
                                            <div
                                                className={`${barra.color} h-3 rounded-full transition-all`}
                                                style={{ width: `${pct(barra.value)}%` }}
                                            />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
};