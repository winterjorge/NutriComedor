import { useState, useEffect } from 'react';
import { api } from '../services/api';

export const useRecipes = () => {
  const [recetas, setRecetas] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [datosCosto, setDatosCosto] = useState(null);
  const [cargandoCosto, setCargandoCosto] = useState(false);

  const cargarRecetas = async () => {
    setCargando(true);
    try { setRecetas(await api.getRecetas() || []); } catch (e) { console.error(e); } finally { setCargando(false); }
  };

  const evaluarCosto = async (id, fecha) => {
    setCargandoCosto(true); setDatosCosto(null);
    try { setDatosCosto(await api.getCostoReceta(id, fecha)); } catch (e) { setDatosCosto({ error: e.message }); } finally { setCargandoCosto(false); }
  };

  return { recetas, cargando, datosCosto, cargandoCosto, cargarRecetas, evaluarCosto, setDatosCosto };
};