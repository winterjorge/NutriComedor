import { useState, useEffect } from 'react';
import { api } from '../services/api';

export const usePOS = () => {
  const [stats, setStats] = useState({ Social: 0, Afiliado: 0, Normal: 0, recaudacion_total: 0.0 });
  const [ventasHoy, setVentasHoy] = useState([]);
  const [prediccion, setPrediccion] = useState(null);

  const refrescarDatos = async () => {
    try {
      const [s, v, p] = await Promise.all([api.getPadronStats(), api.getVentasHoy(), api.getPrediccionDemanda(new Date().toISOString().split('T')[0])]);
      setStats(s); setVentasHoy(v); setPrediccion(p);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { refrescarDatos(); }, []);

  return { stats, ventasHoy, prediccion, refrescarDatos };
};