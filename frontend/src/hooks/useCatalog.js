import { useState, useEffect, useMemo } from 'react';
import { api } from '../services/api';

export const useCatalog = (fechaFiltro, busqueda) => {
  const [catalogo, setCatalogo] = useState([]);
  const [historico, setHistorico] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [cargandoHistorico, setCargandoHistorico] = useState(false);
  const [ingredienteSel, setIngredienteSel] = useState(null);
  const [rangoTiempo, setRangoTiempo] = useState('1w');

  useEffect(() => {
    const cargar = async () => {
      // VALIDACIÓN CLAVE: Si fechaFiltro está vacío o undefined, usar la fecha actual
      const fechaParaConsulta = fechaFiltro || new Date().toISOString().split('T')[0];
      
      setCargando(true);
      try {
        const data = await api.getIngredientes(fechaParaConsulta);
        setCatalogo(data || []);
      } catch (error) {
        console.error('Error cargando catálogo:', error);
        setCatalogo([]);
      } finally {
        setCargando(false);
      }
    };
    cargar();
  }, [fechaFiltro]);

  useEffect(() => {
    if (!ingredienteSel) return;
    
    const cargarHist = async () => {
      setCargandoHistorico(true);
      try {
        const data = await api.getHistoricoPrecios(ingredienteSel.id, rangoTiempo);
        setHistorico(data || []);
      } catch (error) {
        console.error('Error cargando histórico:', error);
        setHistorico([]);
      } finally {
        setCargandoHistorico(false);
      }
    };
    cargarHist();
  }, [ingredienteSel, rangoTiempo]);

  const catalogoFiltrado = useMemo(() => {
    return catalogo.filter(i => 
      (i.nombre || '').toLowerCase().includes(busqueda.toLowerCase()) || 
      (i.categoria || '').toLowerCase().includes(busqueda.toLowerCase())
    );
  }, [busqueda, catalogo]);

  return { 
    catalogo: catalogoFiltrado, 
    historico, 
    cargando, 
    cargandoHistorico, 
    ingredienteSel, 
    setIngredienteSel, 
    rangoTiempo, 
    setRangoTiempo 
  };
};