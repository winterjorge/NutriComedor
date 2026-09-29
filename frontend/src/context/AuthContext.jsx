/**
 * context/AuthContext.jsx
 * Objetivo: Gestionar la sesión del usuario autenticado (COM-19) y la selección de
 *           comedor de trabajo (COM-20): persistencia en localStorage hasta logout
 *           manual, verificación de vigencia al login recordado y logout forzado con
 *           aviso cuando la membresía ya no está activa.
 * Uso: Envolver la aplicación con <AuthProvider> y consumir el hook useAuth()
 *      en LoginView, App, SeleccionComedorView y cualquier componente que requiera
 *      datos del usuario o del comedor seleccionado.
 *
 * Historial:
 *  - COM-19: sesión persistida, pendienteCambio (clave provisoria/expirada).
 *  - COM-20: estado `seleccion` (comedor/alcance recordado), `avisoLogout` (mensaje
 *            de deslogueo forzado), `validando` (verificación al restaurar sesión),
 *            establecerSeleccion() y limpieza de selección solo en logout manual.
 */
import React, { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../services/api';

const AuthContext = createContext();
const CLAVE_STORAGE = 'nutricomedor_usuario';
const CLAVE_SELECCION = 'nutricomedor_seleccion'; // COM-20: comedor recordado

// Mensaje exacto requerido por COM-20 cuando la membresía ya no está activa
const MSG_NO_REGISTRADO = 'Ya no te encuentras registrado en el comedor.';

/**
 * Lee la selección recordada únicamente si pertenece al usuario indicado.
 */
const leerSeleccion = (usuarioId) => {
    try {
        const raw = localStorage.getItem(CLAVE_SELECCION);
        if (!raw) return null;
        const sel = JSON.parse(raw);
        return sel && sel.usuario_id === usuarioId ? sel : null;
    } catch {
        return null;
    }
};

/**
 * Estado inicial coherente de usuario + selección (una sola lectura de storage).
 */
const estadoInicial = () => {
    try {
        const rawU = localStorage.getItem(CLAVE_STORAGE);
        const u = rawU ? JSON.parse(rawU) : null;
        const sel = u ? leerSeleccion(u.id) : null;
        return { u, sel };
    } catch {
        return { u: null, sel: null };
    }
};

export const AuthProvider = ({ children }) => {
    // Sesión restaurada de localStorage (si existe)
    const [usuario, setUsuario] = useState(() => estadoInicial().u);
    // COM-20: selección de comedor recordada (null => debe pasar por la pantalla de selección)
    const [seleccion, setSeleccion] = useState(() => estadoInicial().sel);
    // COM-19: cambio de clave obligatorio pendiente
    const [pendienteCambio, setPendienteCambio] = useState(false);
    // COM-20: mensaje de deslogueo forzado visible en LoginView
    const [avisoLogout, setAvisoLogout] = useState('');
    // COM-20: true mientras se verifica la selección recordada (evita parpadeos de UI)
    const [validando, setValidando] = useState(() => {
        const { u, sel } = estadoInicial();
        return Boolean(u && sel);
    });

    /**
     * COM-20: al montar (sesión restaurada), si hay selección recordada se verifica
     * que el usuario siga activo en ese contexto; si no, se deslogea con aviso.
     */
    useEffect(() => {
        let vivo = true;
        const verificarRecordado = async () => {
            const { u, sel } = estadoInicial();
            if (!u || !sel) {
                if (vivo) setValidando(false);
                return;
            }
            try {
                const res = await api.verificarMembresia(u.id, sel.comedor_id, sel.perfil);
                if (!vivo) return;
                if (res.activo) {
                    setSeleccion(sel);
                } else {
                    forzarCierre(MSG_NO_REGISTRADO);
                }
            } catch (e) {
                // Error de red: se descarta la selección recordada y se mostrará
                // la pantalla de selección para volver a elegir comedor.
                if (!vivo) return;
                localStorage.removeItem(CLAVE_SELECCION);
                setSeleccion(null);
            } finally {
                if (vivo) setValidando(false);
            }
        };
        verificarRecordado();
        return () => { vivo = false; };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    /**
     * COM-19 + COM-20: guarda la sesión tras login exitoso y, si existe selección
     * recordada para este usuario, la verifica antes de omitir la pantalla de selección.
     */
    const iniciarSesion = async (dataLogin) => {
        setAvisoLogout('');
        localStorage.setItem(CLAVE_STORAGE, JSON.stringify(dataLogin.usuario));
        setUsuario(dataLogin.usuario);
        setPendienteCambio(!!dataLogin.requiere_cambio_clave);

        const sel = leerSeleccion(dataLogin.usuario.id);
        if (sel) {
            // Login recordado: verificar vigencia de la membresía (regla COM-20)
            setValidando(true);
            try {
                const res = await api.verificarMembresia(dataLogin.usuario.id, sel.comedor_id, sel.perfil);
                if (res.activo) {
                    setSeleccion(sel);
                } else {
                    localStorage.removeItem(CLAVE_SELECCION);
                    localStorage.removeItem(CLAVE_STORAGE);
                    setUsuario(null);
                    setSeleccion(null);
                    setPendienteCambio(false);
                    setAvisoLogout(MSG_NO_REGISTRADO);
                }
            } catch (e) {
                // Sin conexión para verificar: se obliga a seleccionar de nuevo
                localStorage.removeItem(CLAVE_SELECCION);
                setSeleccion(null);
            } finally {
                setValidando(false);
            }
        } else {
            setSeleccion(null);
            setValidando(false);
        }
    };

    // COM-19: se llama al completar el cambio de clave obligatorio
    const completarCambioClave = () => setPendienteCambio(false);

    /**
     * COM-20: persiste la selección elegida en la pantalla de selección.
     */
    const establecerSeleccion = (sel) => {
        const completa = { ...sel, usuario_id: usuario.id };
        localStorage.setItem(CLAVE_SELECCION, JSON.stringify(completa));
        setSeleccion(completa);
    };

    /**
     * COM-20: logout MANUAL: olvida sesión Y comedor recordado
     * (el próximo login volverá a mostrar la pantalla de selección).
     */
    const cerrarSesion = () => {
        localStorage.removeItem(CLAVE_STORAGE);
        localStorage.removeItem(CLAVE_SELECCION);
        setUsuario(null);
        setSeleccion(null);
        setPendienteCambio(false);
        setAvisoLogout('');
        setValidando(false);
    };

    /**
     * COM-20: logout FORZADO (membresía inactiva): limpia todo y deja el aviso
     * para mostrarlo en la pantalla de login.
     */
    const forzarCierre = (mensaje) => {
        localStorage.removeItem(CLAVE_STORAGE);
        localStorage.removeItem(CLAVE_SELECCION);
        setUsuario(null);
        setSeleccion(null);
        setPendienteCambio(false);
        setAvisoLogout(mensaje);
        setValidando(false);
    };

    return (
        <AuthContext.Provider value={{
            usuario,
            pendienteCambio,
            seleccion,
            avisoLogout,
            validando,
            iniciarSesion,
            completarCambioClave,
            establecerSeleccion,
            cerrarSesion
        }}>
            {children}
        </AuthContext.Provider>
    );
};

// Hook personalizado para consumir la sesión y la selección fácilmente
export const useAuth = () => useContext(AuthContext);