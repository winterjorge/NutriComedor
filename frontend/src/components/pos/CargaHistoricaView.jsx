/**
 * components/pos/CargaHistoricaView.jsx
 * Objetivo: COM-63: interfaz para cargar atenciones históricas desde CSV.
 * Estructura del CSV: fecha;afiliados;publico;sociales;cocineras
 * Uso: Montado por POSView.jsx en una pestaña "Carga Histórica".
 */
import React, { useState } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { api } from '../../services/api';

export const CargaHistoricaView = () => {
    const [archivo, setArchivo] = useState(null);
    const [cargando, setCargando] = useState(false);
    const [resultado, setResultado] = useState(null);
    const [error, setError] = useState('');

    const handleArchivoChange = (e) => {
        const file = e.target.files[0];
        if (file && !file.name.endsWith('.csv')) {
            setError('El archivo debe ser CSV');
            setArchivo(null);
            return;
        }
        setArchivo(file);
        setError('');
        setResultado(null);
    };

    const handleCargar = async () => {
        if (!archivo) return;
        
        setCargando(true);
        setError('');
        setResultado(null);
        
        try {
            const formData = new FormData();
            formData.append('file', archivo);
            
            const res = await api.cargaMasivaHistorica(formData);
            setResultado(res);
        } catch (err) {
            setError(err.message || 'Error al cargar el archivo');
        } finally {
            setCargando(false);
        }
    };

    return (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
            <h3 className="font-bold text-lg text-slate-800 mb-4 flex items-center gap-2">
                <Upload size={20} className="text-emerald-600" />
                Carga Histórica de Atenciones
            </h3>
            
            <div className="space-y-4">
                {/* Instrucciones */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                    <p className="text-sm font-semibold text-blue-800 mb-2">Estructura del CSV:</p>
                    <code className="text-xs bg-white px-2 py-1 rounded block">
                        fecha;afiliados;publico;sociales;cocineras
                    </code>
                    <p className="text-xs text-blue-600 mt-2">
                        • Fecha: YYYY-MM-DD o DD/MM/YYYY<br/>
                        • Números enteros >= 0<br/>
                        • Separador: punto y coma (;)
                    </p>
                </div>

                {/* Input file */}
                <div className="flex items-center gap-3">
                    <label className="flex-1">
                        <div className="border-2 border-dashed border-slate-300 rounded-lg p-4 text-center cursor-pointer hover:border-emerald-500 transition-colors">
                            {archivo ? (
                                <div className="flex items-center justify-center gap-2">
                                    <FileText size={20} className="text-emerald-600" />
                                    <span className="text-sm font-medium text-slate-700">{archivo.name}</span>
                                </div>
                            ) : (
                                <div>
                                    <Upload size={24} className="mx-auto text-slate-400 mb-2" />
                                    <p className="text-sm text-slate-500">Haz clic para seleccionar CSV</p>
                                </div>
                            )}
                        </div>
                        <input
                            type="file"
                            accept=".csv"
                            onChange={handleArchivoChange}
                            className="hidden"
                        />
                    </label>
                </div>

                {/* Botón cargar */}
                <button
                    onClick={handleCargar}
                    disabled={!archivo || cargando}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white font-bold py-3 rounded-lg flex items-center justify-center gap-2"
                >
                    {cargando ? (
                        <>
                            <Loader2 className="animate-spin" size={18} />
                            Procesando...
                        </>
                    ) : (
                        <>
                            <Upload size={18} />
                            Cargar Atenciones Históricas
                        </>
                    )}
                </button>

                {/* Error */}
                {error && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
                        <AlertCircle size={16} className="text-red-600" />
                        <p className="text-sm text-red-700">{error}</p>
                    </div>
                )}

                {/* Resultado */}
                {resultado && (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-3">
                            <CheckCircle size={20} className="text-emerald-600" />
                            <p className="font-bold text-emerald-800">Carga completada</p>
                        </div>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                            <div>
                                <p className="text-slate-600">Filas procesadas:</p>
                                <p className="font-bold text-emerald-700">{resultado.filas_procesadas}</p>
                            </div>
                            <div>
                                <p className="text-slate-600">Ventas creadas:</p>
                                <p className="font-bold text-emerald-700">{resultado.ventas_creadas}</p>
                            </div>
                            <div>
                                <p className="text-slate-600">Filas omitidas:</p>
                                <p className="font-bold text-amber-700">{resultado.filas_omitidas}</p>
                            </div>
                            <div>
                                <p className="text-slate-600">Rango de fechas:</p>
                                <p className="font-bold text-slate-700">
                                    {resultado.rango_fechas?.desde} → {resultado.rango_fechas?.hasta}
                                </p>
                            </div>
                        </div>
                        {resultado.detalle_omitidas?.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-emerald-200">
                                <p className="text-xs font-semibold text-amber-800 mb-1">Detalle de omitidas:</p>
                                <ul className="text-xs text-amber-700 space-y-1">
                                    {resultado.detalle_omitidas.map((d, i) => (
                                        <li key={i}>• Fila {d.fila}: {d.razon}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};