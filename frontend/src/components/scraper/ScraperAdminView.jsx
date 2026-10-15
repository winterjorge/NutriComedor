/**
components/scraper/ScraperAdminView.jsx
Objetivo: COM-43: panel del Administrador de Sistemas para ejecutar el scraper SISAP
      desde la web (un día o un rango), ver el progreso en vivo, el hueco de fechas
      faltantes y el historial auditado de corridas (scraper_corridas).
      El botón reutiliza el scraper existente del backend (sin código de scraping nuevo).
Historial:
COM-43 (este archivo): versión original.
Permisos: pestaña gateada por el módulo 'modelos_ml' (solo Admin de Sistemas) y el
      backend valida es_admin_sistema en los 3 endpoints (403 para el resto).
Uso: Montada por App.jsx en la pestaña "Scraper SISAP".
Referencia: ticket COM-43 (solo trazabilidad).
*/
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
    Database, Loader2, AlertCircle, Play, CalendarRange, History,
    CheckCircle2, XCircle, RefreshCw, Download
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalExito } from '../common/ModalExito';

const ESTADO_BADGE = {
    EN_PROCESO: 'bg-blue-100 text-blue-700',
    COMPLETADA: 'bg-emerald-100 text-emerald-700',
    COMPLETADA_CON_ERRORES: 'bg-amber-100 text-amber-700',
    FALLIDA: 'bg-red-100 text-red-700',
};

export const ScraperAdminView = () => {
    const { usuario } = useAuth();
    const [estado, setEstado] = useState(null);
    const [historial, setHistorial] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');
    const [lanzando, setLanzando] = useState(false);
    const [fechaInicio, setFechaInicio] = useState('');
    const [fechaFin, setFechaFin] = useState('');
    const timerRef = useRef(null);

    const cargar = useCallback(async () => {
        try {
            const [est, hist] = await Promise.all([
                api.getEstadoScraper(usuario.id),
                api.getHistorialScraper(usuario.id, 20),
            ]);
            setEstado(est);
            setHistorial(hist || []);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, [usuario.id]);

    useEffect(() => { cargar(); }, [cargar]);

    // COM-43: polling de progreso mientras haya job activo
    useEffect(() => {
        if (estado?.job?.activo || estado?.job) {
            timerRef.current = setInterval(cargar, 3000);
        }
        return () => { if (timerRef.current) clearInterval(timerRef.current); };
    }, [estado?.job, cargar]);

    const lanzar = async () => {
        setLanzando(true);
        setError(''); setExito('');
        try {
            const res = await api.ejecutarScraper({
                usuario_solicitante_id: usuario.id,
                fecha_inicio: fechaInicio || null,
                fecha_fin: fechaFin || null,
            });
            setExito(res.message || 'Corrida lanzada.');
            await cargar();
        } catch (e) {
            setError(e.message);
        } finally {
            setLanzando(false);
        }
    };

    const rellenarHuecos = () => {
        if (!estado?.ultima_fecha_bd) return;
        const ult = new Date(estado.ultima_fecha_bd + 'T00:00:00');
        ult.setDate(ult.getDate() + 1);
        const ayer = new Date();
        ayer.setDate(ayer.getDate() - 1);
        const fmt = (d) => d.toISOString().slice(0, 10);
        setFechaInicio(fmt(ult));
        setFechaFin(fmt(ayer));
    };

    const job = estado?.job || null;
    const pct = job && job.dias_totales > 0
        ? Math.round((job.dias_procesados / job.dias_totales) * 100) : 0;

    return (
        <div className="animate-in fade-in duration-300 space-y-5">
            {/* Encabezado */}
            <div className="flex flex-wrap justify-between items-center gap-3">
                <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                        <Database className="text-emerald-600" size={22} /> Scraper SISAP — Precios de insumos
                    </h2>
                    <p className="text-sm text-slate-500">
                        Ejecuta el extractor de precios del portal SISAP (MIDAGRI) para un día o un
                        rango histórico. El cron del host sigue corriendo a las 05:00 y el sistema
                        rellena huecos automáticamente al arrancar el servidor.
                    </p>
                </div>
                <button onClick={cargar} disabled={cargando}
                    className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                    <RefreshCw size={16} className={cargando ? 'animate-spin' : ''} /> Actualizar
                </button>
            </div>

            {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {/* Estado de la base de precios */}
            {estado && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
                        <p className="text-lg font-bold text-slate-800">
                            {estado.ultima_fecha_bd ? estado.ultima_fecha_bd : '—'}
                        </p>
                        <p className="text-[11px] text-slate-500">Última fecha con precios en BD</p>
                    </div>
                    <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
                        <p className={`text-lg font-bold ${estado.dias_faltantes_hasta_ayer > 0 ? 'text-amber-600' : 'text-emerald-700'}`}>
                            {estado.dias_faltantes_hasta_ayer ?? '—'}
                        </p>
                        <p className="text-[11px] text-slate-500">Días faltantes hasta ayer</p>
                    </div>
                    <div className="bg-white border border-slate-200 rounded-xl p-4 text-center">
                        <p className="text-lg font-bold text-slate-800">
                            {estado.ultima_corrida ? `#${estado.ultima_corrida.id} · ${estado.ultima_corrida.origen}` : '—'}
                        </p>
                        <p className="text-[11px] text-slate-500">
                            Última corrida: {estado.ultima_corrida?.estado || 'sin registros'}
                        </p>
                    </div>
                </div>
            )}

            {/* Progreso del job activo */}
            {job && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                    <p className="text-sm font-bold text-blue-800 flex items-center gap-2 mb-2">
                        <Loader2 size={16} className="animate-spin" />
                        Corrida {job.origen} #{job.corrida_id} en proceso: {job.fecha_inicio} → {job.fecha_fin}
                    </p>
                    <div className="h-3 bg-blue-100 rounded-full overflow-hidden mb-2">
                        <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                    <p className="text-xs text-blue-700">
                        {job.dias_procesados}/{job.dias_totales} días ({pct}%) ·
                        actuales: {job.fecha_actual || '—'} ·
                        ok: {job.dias_exitosos} · fallos: {job.dias_fallidos} · {job.ultimo_evento}
                    </p>
                </div>
            )}

            {/* Lanzamiento manual por rango */}
            <div className="bg-white border border-slate-200 rounded-xl p-4">
                <p className="text-sm font-bold text-slate-700 flex items-center gap-1 mb-3">
                    <CalendarRange size={15} className="text-emerald-600" /> Ejecución manual por rango
                </p>
                <div className="flex flex-wrap items-end gap-3">
                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Desde</label>
                        <input type="date" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)}
                            className="px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                    </div>
                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Hasta</label>
                        <input type="date" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)}
                            className="px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                    </div>
                    <button onClick={rellenarHuecos}
                        className="flex items-center gap-1 px-3 py-2 bg-amber-100 hover:bg-amber-200 text-amber-800 rounded-lg text-sm font-medium transition-colors">
                        <Download size={14} /> Rellenar huecos
                    </button>
                    <button onClick={lanzar} disabled={lanzando || !!job}
                        className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
                        {lanzando ? <Loader2 className="animate-spin" size={16} /> : <Play size={16} />}
                        Ejecutar scraper
                    </button>
                </div>
                <p className="text-[11px] text-slate-400 mt-2">
                    Sin fechas ⇒ corre el día de hoy. El proceso corre en segundo plano: puede
                    cerrar esta pestaña y volver para ver el progreso.
                </p>
            </div>

            {/* Historial de corridas */}
            <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
                <p className="text-sm font-bold text-slate-700 flex items-center gap-1 p-4 pb-2">
                    <History size={15} className="text-emerald-600" /> Historial de corridas
                </p>
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse whitespace-nowrap text-sm">
                        <thead>
                            <tr className="bg-slate-100 text-slate-600">
                                <th className="p-3 font-semibold">#</th>
                                <th className="p-3 font-semibold">Origen</th>
                                <th className="p-3 font-semibold">Rango</th>
                                <th className="p-3 font-semibold">Días ok/fallo</th>
                                <th className="p-3 font-semibold">Estado</th>
                                <th className="p-3 font-semibold">Iniciado</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200">
                            {cargando ? (
                                <tr><td colSpan="6" className="p-6 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={22} /></td></tr>
                            ) : historial.length === 0 ? (
                                <tr><td colSpan="6" className="p-6 text-center text-slate-500">Aún no hay corridas registradas.</td></tr>
                            ) : historial.map(h => (
                                <tr key={h.id} className="hover:bg-slate-50">
                                    <td className="p-3 font-medium text-slate-800">{h.id}</td>
                                    <td className="p-3 text-slate-600">{h.origen}</td>
                                    <td className="p-3 text-slate-600">{h.fecha_inicio} → {h.fecha_fin}</td>
                                    <td className="p-3 text-slate-600">
                                        <span className="text-emerald-700 font-bold">{h.dias_exitosos}</span>
                                        {' / '}
                                        <span className={h.dias_fallidos > 0 ? 'text-red-600 font-bold' : 'text-slate-400'}>{h.dias_fallidos}</span>
                                    </td>
                                    <td className="p-3">
                                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${ESTADO_BADGE[h.estado] || 'bg-slate-100 text-slate-600'}`}>
                                            {h.estado}
                                        </span>
                                    </td>
                                    <td className="p-3 text-slate-500 text-xs">
                                        {h.iniciado_en ? new Date(h.iniciado_en).toLocaleString('es-PE') : '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};