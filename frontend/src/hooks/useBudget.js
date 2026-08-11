import { useState } from 'react';
import { api } from '../services/api';

export const useBudget = () => {
  const [presupuesto, setPresupuesto] = useState('');
  const [diasOperativos, setDiasOperativos] = useState('5');
  const [planificacion, setPlanificacion] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(null);

  const generarPlanificacion = async (prediccionPorDia, fechaReferencia) => {
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

    // Si no hay predicción por día, usar valores por defecto
    const comensales = prediccionPorDia && prediccionPorDia.length === diasNum
      ? prediccionPorDia
      : Array(diasNum).fill(0).map(() => ({
          social: 20,
          afiliado: 40,
          normal: 90
        }));

    setCargando(true);
    setError(null);

    try {
      const data = await api.planificarSemana({
        presupuesto: presupuestoNum,
        dias_operativos: diasNum,
        prediccion_comensales: comensales,
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

  const resetPlanificacion = () => {
    setPlanificacion(null);
    setError(null);
  };

  return {
    presupuesto,
    setPresupuesto,
    diasOperativos,
    setDiasOperativos,
    planificacion,
    cargando,
    error,
    generarPlanificacion,
    resetPlanificacion
  };
};