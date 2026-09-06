/**
 * components/auth/ModalCambioClave.jsx
 * Objetivo: Modal de cambio de contraseña obligatorio (COM-19) cuando la clave está
 *           expirada (6 meses) o es provisoria. Muestra checklist en vivo de la política:
 *           8-12 caracteres, letras+números, sin contener el DNI.
 * Uso: Renderizado por App.jsx cuando pendienteCambio es TRUE. Bloquea el uso del
 *      sistema hasta cambiar la clave o cerrar sesión.
 */
import React, { useState } from 'react';
import { KeyRound, CheckCircle, XCircle, Loader2, LogOut } from 'lucide-react';
import { api } from '../../services/api';
import { ModalExito } from '../common/ModalExito';

export const ModalCambioClave = ({ usuario, onExito, onSalir }) => {
    const [claveActual, setClaveActual] = useState('');
    const [claveNueva, setClaveNueva] = useState('');
    const [confirmar, setConfirmar] = useState('');
    const [error, setError] = useState('');
    const [cargando, setCargando] = useState(false);
    const [exito, setExito] = useState(false);

    const doc = usuario?.documento_identidad || '';

    // Checklist en vivo de la política de contraseñas (COM-19)
    const reglas = [
        { ok: claveNueva.length >= 8 && claveNueva.length <= 12, texto: 'Entre 8 y 12 caracteres' },
        { ok: /[A-Za-z]/.test(claveNueva) && /\d/.test(claveNueva), texto: 'Contiene letras y números' },
        { ok: claveNueva.length > 0 && doc !== '' && !claveNueva.includes(doc), texto: 'No contiene su documento' },
        { ok: confirmar !== '' && confirmar === claveNueva, texto: 'Las contraseñas coinciden' }
    ];
    const todasOk = reglas.every(r => r.ok);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        if (!claveActual.trim() || !claveNueva.trim() || !confirmar.trim()) {
            setError('Debe ingresar todos los campos, no pueden enviarse en blanco.');
            return;
        }
        if (!todasOk) {
            setError('La contraseña nueva no cumple la política de seguridad.');
            return;
        }
        setCargando(true);
        try {
            const { ok, data } = await api.cambiarClave({
                tipo_documento: usuario.tipo_documento,
                documento_identidad: usuario.documento_identidad,
                clave_actual: claveActual,
                clave_nueva: claveNueva
            });
            if (ok) {
                setExito(true);
            } else {
                const detail = data.detail;
                setError((typeof detail === 'object' && detail !== null) ? detail.mensaje : (detail || 'Error al cambiar la contraseña.'));
            }
        } catch (err) {
            console.error('Error cambiando contraseña:', err);
            setError('Error de conexión con el servidor.');
        } finally {
            setCargando(false);
        }
    };

    return (
        <>
            {/* Modal bloque