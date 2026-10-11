/**
 * components/pos/POSView.jsx
 * Objetivo: Vista principal del POS (Punto de Venta). Muestra el formulario de venta,
 *           la tabla de ventas del día, las estadísticas y la predicción de demanda.
 *           COM-63: agrega stats de Cocineras y acceso a carga histórica.
 * Historial:
 *  - Sprint 1/2: versión original.
 *  - COM-62 v2: integración con FormularioVenta COM-62 (autocompletado por nombre).
 *  - COM-63: stats de Cocineras + botón de carga histórica.
 */
import React, { useState, useEffect } from 'react';
import { Activity, TrendingUp, AlertTriangle, Upload } from 'lucide-react';
import { api } from '../../services/api';
import { useParametros } from '../../context/ParametrosContext';
import { FormularioVenta } from './FormularioVenta';
import { TablaVentasHoy } from './TablaVentasHoy';
import { ModalEdicionVenta } from './ModalEdicionVenta';
import { CargaHistoricaView } from './CargaHistoricaView';

export const POSView = () => {
    const { parametros } = useParametros();
    const limiteSocial = parametros?.LIMITE_SOCIAL || 20;
    const limiteAfiliado = parametros?.LIMITE_AFILIADO || 45;
    const limiteCocinera = parametros?.LIMITE_COCINERA || 10;

    const [stats, setStats] = useState({ Social: 0, Afiliado: 0, Normal: 0, Cocinera: 0, recaudacion_total: 0 });
    const [ventas, setVentas] = useState([]);
    const [prediccion, setPrediccion] = useState(null);
    const [modalEditar, setModalEditar] = useState(null);
    const [mostrarCarga, setMostrarCarga] = useState(false);

    const cargarDatos = async () => {
        try {
            const [statsData, ventasData, predData] = await Promise.all([
                api.getPadronStats(),
                api.getVentasHoy(),
                api.getPrediccionDemanda(new Date().toISOString().split('T')[0])
            ]);
            setStats(statsData);
            setVentas(ventasData);
            setPrediccion(predData);
        } catch (e) {
            console.error("Error cargando datos del POS:", e);
        }
    };

    useEffect(() => {
        cargarDatos();
    }, []);

    const tSoc = stats.Social || 0;
    const tAfi = stats.Afiliado || 0;
    const tNor = stats.Normal || 0;
    const tCoc = stats.Cocinera || 0;

    return (
        <div className="animate-in fade-in duration-300 space-y-6">
            <div className="flex justify-between items-center">
                <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                    <Activity className="text-emerald-600" size={28} />
                    Punto de Venta
                </h2>
                <button
                    onClick={() => setMostrarCarga(!mostrarCarga)}
                    className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                    <Upload size={16} />
                    {mostrarCarga ? 'Ocultar Carga Histórica' : 'Carga Histórica'}
                </button>
            </div>

            {mostrarCarga && <CargaHistoricaView />}

            {/* Stats */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                <div className={`p-4 rounded-xl border shadow-sm text-center ${tSoc > limiteSocial ? 'bg-red-50 border-red-200' : 'bg-white border-slate-200'}`}>
                    <p className="text-xs font-semibold uppercase text-slate-500">Social</p>
                    <p className={`text-3xl font-black ${tSoc > limiteSocial ? 'text-red-600' : 'text-slate-700'}`}>
                        {tSoc} <span className="text-sm font-medium text-slate-400">/ {limiteSocial}</span>
                    </p>
                    {tSoc > limiteSocial && <AlertTriangle size={16} className="text-red-600 mx-auto mt-1" />}
                </div>
                <div className={`p-4 rounded-xl border shadow-sm text-center ${tAfi > limiteAfiliado ? 'bg-amber-50 border-amber-200' : 'bg-white border-slate-200'}`}>
                    <p className="text-xs font-semibold uppercase text-slate-500">Afiliado</p>
                    <p className={`text-3xl font-black ${tAfi > limiteAfiliado ? 'text-amber-600' : 'text-slate-700'}`}>
                        {tAfi} <span className="text-sm font-medium text-slate-400">/ {limiteAfiliado}</span>
                    </p>
                    {tAfi > limiteAfiliado && <AlertTriangle size={16} className="text-amber-600 mx-auto mt-1" />}
                </div>
                <div className="p-4 rounded-xl border border-slate-200 bg-white shadow-sm text-center">
                    <p className="text-xs font-semibold uppercase text-slate-500">Normal</p>
                    <p className="text-3xl font-black text-slate-700">{tNor}</p>
                </div>
                <div className={`p-4 rounded-xl border shadow-sm text-center ${tCoc > limiteCocinera ? 'bg-purple-50 border-purple-200' : 'bg-white border-slate-200'}`}>
                    <p className="text-xs font-semibold uppercase text-slate-500">Cocineras</p>
                    <p className={`text-3xl font-black ${tCoc > limiteCocinera ? 'text-purple-600' : 'text-slate-700'}`}>
                        {tCoc} <span className="text-sm font-medium text-slate-400">/ {limiteCocinera}</span>
                    </p>
                    {tCoc > limiteCocinera && <AlertTriangle size={16} className="text-purple-600 mx-auto mt-1" />}
                </div>
                <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50 shadow-sm text-center">
                    <p className="text-xs font-semibold uppercase text-emerald-600">Recaudación</p>
                    <p className="text-3xl font-black text-emerald-700">S/ {stats.recaudacion_total?.toFixed(2) || '0.00'}</p>
                </div>
            </div>

            {/* Predicción */}
            {prediccion && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex items-center gap-3">
                    <TrendingUp size={24} className="text-blue-600" />
                    <div>
                        <p className="text-sm font-bold text-blue-800">Predicción para hoy:</p>
                        <p className="text-xs text-blue-600">
                            Social: {prediccion.prediccion_social} | Afiliado: {prediccion.prediccion_afiliado} | Normal: {prediccion.prediccion_normal} | Total: {prediccion.total_raciones_sugeridas}
                        </p>
                    </div>
                </div>
            )}

            {/* Formulario y Tabla */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <FormularioVenta onVentaRegistrada={cargarDatos} />
                <TablaVentasHoy ventas={ventas} onEditar={setModalEditar} />
            </div>

            {modalEditar && (
                <ModalEdicionVenta
                    venta={modalEditar}
                    onClose={() => setModalEditar(null)}
                    onActualizacion={cargarDatos}
                />
            )}
        </div>
    );
};