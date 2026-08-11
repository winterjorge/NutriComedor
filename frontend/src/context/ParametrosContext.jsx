import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../services/api';
import { CONSTANTS } from '../utils/constants'; // Fallback de emergencia

const ParametrosContext = createContext();

export const ParametrosProvider = ({ children }) => {
    // Inicia con las constantes locales como fallback por si la API falla o tarda
    const [parametros, setParametros] = useState(CONSTANTS); 
    const [cargando, setCargando] = useState(true);

    useEffect(() => {
        const cargarParametros = async () => {
            try {
                const data = await api.getParametros();
                // El backend devuelve un diccionario {clave: valor} ya casteado
                setParametros(data);
            } catch (error) {
                console.error("Error cargando parámetros dinámicos, usando fallback local:", error);
            } finally {
                setCargando(false);
            }
        };
        cargarParametros();
    }, []);

    return (
        <ParametrosContext.Provider value={{ parametros, cargando }}>
            {children}
        </ParametrosContext.Provider>
    );
};

// Hook personalizado para consumir los parámetros fácilmente
export const useParametros = () => useContext(ParametrosContext);