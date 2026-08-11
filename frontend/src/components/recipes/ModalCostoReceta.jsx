import React, { useState, useEffect } from 'react';
import { X, Loader2, AlertCircle } from 'lucide-react';
import { api } from '../../services/api';

export const ModalCostoReceta = ({ isOpen, onClose, receta, fecha, onChangeFecha }) => {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [fechaLocal, setFechaLocal] = useState(fecha || new Date().toISOString().split('T')[0]);

  useEffect(() => {
    if (isOpen && receta) {
      cargarCosto(fechaLocal);
    }
  }, [isOpen, receta]);

  const cargarCosto = async (fechaEval) => {
    if (!receta) return;
    setCargando(true);
    setDatos(null);
    try {
      const response = await api.getCostoReceta(receta.id, fechaEval);
      if (response.error) {
        // Si no hay datos para esa fecha, intentar con la fecha actual
        const hoy = new Date().toISOString().split('T')[0];
        if (fechaEval !== hoy) {
          const responseHoy = await api.getCostoReceta(receta.id, hoy);
          setDatos(responseHoy);
          setFechaLocal(hoy);
          if (onChangeFecha) onChangeFecha(hoy);
        } else {
          setDatos(response);
        }
      } else {
        setDatos(response);
      }
    } catch (error) {
      setDatos({ error: error.message });
    } finally {
      setCargando(false);
    }
  };

  const handleChangeFecha = (e) => {
    const nuevaFecha = e.target.value;
    setFechaLocal(nuevaFecha);
    if (onChangeFecha) onChangeFecha(nuevaFecha);
    cargarCosto(nuevaFecha);
  };

  if (!isOpen || !receta) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="flex justify-between items-center p-5 border-b bg-emerald-600 text-white">
          <h3 className="font-bold text-lg">{receta.nombre}</h3>
          <button onClick={onClose}>
            <X size={24} />
          </button>
        </div>
        <div className="p-6 overflow-y-auto">
          <div className="flex justify-between items-end mb-6">
            <input 
              type="date" 
              value={fechaLocal} 
              onChange={handleChangeFecha} 
              className="px-4 py-2 border border-slate-300 rounded-lg outline-none" 
            />
            {datos && !datos.error && !cargando && (
              <p className="text-4xl font-black text-emerald-600">
                S/ {datos.costo_total_racion?.toFixed(2) || '0.00'}
              </p>
            )}
          </div>
          {cargando ? (
            <Loader2 className="animate-spin text-emerald-600 mx-auto" size={40} />
          ) : datos?.detalle_insumos ? (
            datos.error ? (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-amber-800">
                <div className="flex items-start gap-3">
                  <AlertCircle className="shrink-0 mt-0.5" size={20} />
                  <div>
                    <p className="font-semibold mb-1">No hay datos para esta fecha</p>
                    <p className="text-sm">{datos.error}</p>
                    <p className="text-sm mt-2">
                      Mostrando costos con los últimos datos disponibles (fecha actual).
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-100">
                    <tr>
                      <th className="p-2">Ingrediente</th>
                      <th className="p-2">Insumo Seleccionado</th>
                      <th className="p-2 text-right">Costo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.detalle_insumos.map((d, i) => (
                      <tr key={i} className={d.error ? 'bg-red-50' : 'hover:bg-slate-50'}>
                        <td className="p-2 font-medium">{d.ingrediente}</td>
                        <td className="p-2">
                          {d.error ? (
                            <span className="text-red-600 text-xs flex items-center gap-1">
                              <AlertCircle size={12} /> {d.error}
                            </span>
                          ) : (
                            <span className="text-slate-700">{d.insumo_comprado}</span>
                          )}
                        </td>
                        <td className="p-2 text-right font-bold text-emerald-700">
                          {d.error ? (
                            <span className="text-red-600">S/ 0.00</span>
                          ) : (
                            `S/${d.costo_parcial?.toFixed(2) || '0.00'}`
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {datos.detalle_insumos.some(d => d.error) && (
                  <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-amber-800 text-sm">
                    <p className="font-semibold mb-1">⚠ Ingredientes sin precio:</p>
                    <p>Algunos ingredientes no tienen insumos disponibles para la fecha seleccionada. 
                    Esto puede deberse a que el scraper aún no ha capturado precios para esos productos.</p>
                  </div>
                )}
              </div>
            )
          ) : null}
        </div>
      </div>
    </div>
  );
};