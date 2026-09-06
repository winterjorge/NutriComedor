/**
 * context/AuthContext.jsx
 * Objetivo: Gestionar la sesión del usuario autenticado (COM-19): login/logout
 *           persistido en localStorage para mantenerla entre recargas de página.
 * Uso: Envolver la aplicación con <AuthProvider> y consumir el hook useAuth()
 *      en LoginView, App y cualquier componente que requiera datos del usuario.
 */
import React, { createContext, useContext, useState } from 'react';

const AuthContext = createContext();
const CLAVE_STORAGE = 'nutricomedor_usuario';

export const AuthProvider = ({ children }) => {
    // Restaurar sesión previa si existe en localStorage
    const [usuario, setUsuario] = useState(() => {
        try {
            const raw = localStorage.getItem(CLAVE_STORAGE);
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    });

    // TRUE si el usuario debe cambiar su clave (provisoria o expirada) antes de operar
    const [pendienteCambio, setPendienteCambio] = useState(false);

    // Guarda la sesión tras un login exitoso
    const iniciarSesion = (dataLogin) => {
        localStorage.setItem(CLAVE_STORAGE, JSON.stringify(dataLogin.usuario));
        setUsuario(dataLogin.usuario);
        setPendienteCambio(!!dataLogin.requiere_cambio_clave);
    };

    // Se llama al completar el cambio de clave obligatorio
    const completarCambioClave = () => setPendienteCambio(false);

    // Cierra la sesión y limpia el almacenamiento local
    const cerrarSesion = () => {
        localStorage.removeItem(CLAVE_STORAGE);
        setUsuario(null);
        setPendienteCambio(false);
    };

    return (
        <AuthContext.Provider value={{ usuario, pendienteCambio, iniciarSesion, completarCambioClave, cerrarSesion }}>
            {children}
        </AuthContext.Provider>
    );
};

// Hook personalizado para consumir la sesión fácilmente
export const useAuth = () => useContext(AuthContext);