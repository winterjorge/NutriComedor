import React, { useState, useEffect } from 'react';
import { Calculator, CheckCircle, AlertCircle, RefreshCw, DollarSign, Save, Loader2 } from 'lucide-react';
import { api } from '../../services/api';
import { usePOS } from '../../hooks/usePOS';

export const BudgetView = () => {
  const { prediccion } = usePOS();
  
  const [presupuesto, setPresupuesto] = useState('');
  const [diasOperativos, setDiasOperativos] = useState('5');
  const [fechaReferencia, setFechaReferencia] = useState(new Date().toISOString().split('T')[0]);
  const [prediccionPorDia, setPrediccionPorDia] = useState([]);
  const [planificacion, setPlanificacion] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState(null);
  const [mensajeExito, setMensajeExito] = useState(null);

  // Generar predicción por día basada en la proyección de cocina
  useEffect(() => {
    if (prediccion && prediccion.total_raciones_sugeridas) {
      const dias = parseInt(diasOperativos) || 5;
      
      // Obtener la predicción base por tipo
      const socialBase = prediccion.prediccion_social || 0;
      const afiliadoBase = prediccion.prediccion_afiliado || 0;
      const normalBase = prediccion.prediccion_normal || 0;
      
      // Distribuir entre los días operativos con variación realista
      const prediccionDias = Array(dias).fill(0).map((_, index) => {
        // Variación según el día de la semana (lunes y viernes suelen tener más demanda)
        const diaSemana = (new Date(fechaReferencia).getDay() + index) % 7;
        let factorVariacion = 1.0;
        
        if (diaSemana === 1 || diaSemana === 5) { // Lunes o Viernes
          factorVariacion = 1.1; // 10% más
        } else if (diaSemana === 3) { // Miércoles
          factorVariacion = 0.95; // 5% menos
        }
        
        // Añadir pequeña variación aleatoria pero consistente
        const seed = index * 17 + 13;
        const variacionAleatoria = 0.95 + ((seed % 10) / 100); // Variación entre 0.95 y 1.05
        
        const factorTotal = factorVariacion * variacionAleatoria;
        
        return {
          social: Math.round(socialBase * factorTotal),
          afiliado: Math.round(afiliadoBase * factorTotal),
          normal: Math.round(normalBase * factorTotal)
        };
      });
      
      setPrediccionPorDia(prediccionDias);
    }
  }, [prediccion, diasOperativos, fechaReferencia]);

  const generarPlanificacion = async (e) => {
    if (e) e.preventDefault();
    
    if (!presupuesto || !diasOperativos) {
      setError('Complete presupuesto y dias operativos');
      return;
    }

    const presupuestoNum = parseFloat(presupuesto);
    const diasNum = parseInt(diasOperativos);

    if (presupuestoNum <= 0 || diasNum <= 0) {
      setError('Ingrese valores validos mayores a 0');
      return;
    }

    setCargando(true);
    setError(null);
    setMensajeExito(null);

    try {
      const data = await api.planificarSemana({
        presupuesto: presupuestoNum,
        dias_operativos: diasNum,
        prediccion_comensales: prediccionPorDia,
        fecha_referencia: fechaReferencia || null
      });
      setPlanificacion(data);
    } catch (err) {
      console.error('Error generando planificacion:', err);
      setError('Error al generar la planificacion: ' + err.message);
    } finally {
      setCargando(false);
    }
  };

  const handleRegenerar = () => {
    generarPlanificacion();
  };

  const guardarPlanificacion = async () => {
    if (!planificacion) return;
    
    setGuardando(true);
    setError(null);
    setMensajeExito(null);

    try {
      const data = await api.guardarPlanificacion({
        presupuesto: planificacion.presupuesto,
        dias_operativos: planificacion.dias.length,
        fecha_referencia: fechaReferencia,
        costo_total_semana: planificacion.costo_total_semana,
        recoleccion_total_proyectada: planificacion.recoleccion_total_proyectada,
        margen: planificacion.margen,
        viable: planificacion.viable,
        dias: planificacion.dias
      });
      
      setMensajeExito(`Planificación guardada exitosamente (ID: ${data.id})`);
    } catch (err) {
      console.error('Error guardando planificación:', err);
      setError('Error al guardar la planificación: ' + err.message);
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="animate-in fade-in duration-300">
      <div className="mb-6">
        <h2 className="text-xl font-bold text-slate-800">Planificacion Semanal de Menu</h2>
        <p className="text-sm text-slate-500">
          Configure su presupuesto y dias operativos para generar recomendaciones de platos
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 p-6 mb-6">
        <form onSubmit={generarPlanificacion} className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Presupuesto Semanal (S/)
            </label>
            <div className="relative">
              <DollarSign className="absolute left-3 top-2.5 text-slate-400" size={18} />
              <input
                type="number"
                value={presupuesto}
                onChange={(e) => setPresupuesto(e.target.value)}
                placeholder="1500"
                className="w-full pl-10 pr-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500"
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Dias Operativos
            </label>
            <select
              value={diasOperativos}
              onChange={(e) => setDiasOperativos(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="5">5 dias (Lun-Vie)</option>
              <option value="6">6 dias (Lun-Sab)</option>
              <option value="7">7 dias (Lun-Dom)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Fecha de Referencia
            </label>
            <input
              type="date"
              value={fechaReferencia}
              onChange={(e) => setFechaReferencia(e.target.value)}
              className="w-full px-4 py-2 border border-slate-300 rounded-lg outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div className="flex items-end gap-2">
            <button
              type="submit"
              disabled={cargando}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {cargando ? 'Generando...' : 'Generar Planificacion'}
            </button>
          </div>
        </form>

        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
          </div>
        )}

        {mensajeExito && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-700 text-sm flex items-center gap-2">
            <CheckCircle size={16} />
            {mensajeExito}
          </div>
        )}
      </div>

      {planificacion && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className={`p-6 ${planificacion.viable ? 'bg-emerald-50' : 'bg-amber-50'}`}>
            <div className="flex items-start gap-3">
              {planificacion.viable ? (
                <CheckCircle className="text-emerald-600 shrink-0" size={24} />
              ) : (
                <AlertCircle className="text-amber-600 shrink-0" size={24} />
              )}
              <div className="flex-1">
                <h3 className={`font-bold text-lg ${planificacion.viable ? 'text-emerald-800' : 'text-amber-800'}`}>
                  {planificacion.viable ? '¡Planificacion Viable!' : 'Planificacion No Viable'}
                </h3>
                <p className={`text-sm mt-1 ${planificacion.viable ? 'text-emerald-700' : 'text-amber-700'}`}>
                  {planificacion.viable
                    ? `El presupuesto es suficiente. Margen disponible: S/ ${planificacion.margen.toFixed(2)}`
                    : `El presupuesto no es suficiente. Deficit: S/ ${Math.abs(planificacion.margen).toFixed(2)}`
                  }
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleRegenerar}
                  disabled={cargando}
                  className="flex items-center gap-2 px-4 py-2 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 disabled:opacity-50"
                >
                  <RefreshCw size={16} className={cargando ? 'animate-spin' : ''} />
                  Regenerar
                </button>
                <button
                  onClick={guardarPlanificacion}
                  disabled={guardando}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white border border-blue-700 rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {guardando ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Guardando...
                    </>
                  ) : (
                    <>
                      <Save size={16} />
                      Guardar Planificacion
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-4 border-b border-slate-200">
            <div className="p-4 text-center border-r border-slate-200">
              <p className="text-xs text-slate-500 uppercase">Presupuesto</p>
              <p className="text-xl font-bold text-slate-800">S/ {planificacion.presupuesto.toFixed(2)}</p>
            </div>
            <div className="p-4 text-center border-r border-slate-200">
              <p className="text-xs text-slate-500 uppercase">Costo Total</p>
              <p className="text-xl font-bold text-slate-800">S/ {planificacion.costo_total_semana.toFixed(2)}</p>
            </div>
            <div className="p-4 text-center border-r border-slate-200">
              <p className="text-xs text-slate-500 uppercase">Recolección Proyectada</p>
              <p className="text-xl font-bold text-emerald-600">S/ {planificacion.recoleccion_total_proyectada.toFixed(2)}</p>
            </div>
            <div className="p-4 text-center">
              <p className="text-xs text-slate-500 uppercase">Margen</p>
              <p className={`text-xl font-bold ${planificacion.margen >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                S/ {planificacion.margen.toFixed(2)}
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase">Dia</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase">Menu</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-slate-600 uppercase">Comensales</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase">Costo/Racion</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase">Costo Total</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-slate-600 uppercase">Recolección</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {planificacion.dias.map((dia) => (
                  <tr key={dia.dia} className="hover:bg-slate-50">
                    <td className="px-6 py-4">
                      <div className="font-medium text-slate-800">{dia.dia_nombre}</div>
                      <div className="text-xs text-slate-500">Dia {dia.dia}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
                          Receta #{dia.receta_id}
                        </span>
                        <span className="text-sm font-medium text-slate-800">{dia.nombre_receta}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="text-center">
                        <div className="text-sm font-medium text-slate-800">{dia.total_comensales}</div>
                        <div className="text-xs text-slate-500">
                          <span className="text-red-600">{dia.comensales_social}S</span>
                          <span className="text-amber-600">/{dia.comensales_afiliado}A</span>
                          <span className="text-blue-600">/{dia.comensales_normal}N</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-sm text-slate-700">S/ {dia.costo_racion.toFixed(2)}</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-sm font-bold text-slate-800">S/ {dia.costo_total.toFixed(2)}</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="text-sm font-bold text-emerald-600">S/ {dia.recoleccion_proyectada.toFixed(2)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};