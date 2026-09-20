/**
 * components/usuarios/VistaPermisosView.jsx
 * Objetivo: Editor de la matriz de permisos por rol (sub-pestaña "Vistas" del panel
 *           de administración global). Muestra los grupos del sistema con sus roles
 *           y, para cada rol, un checklist con los módulos del sistema que el rol
 *           tiene permitidos. Al guardar se REEMPLAZA el conjunto de módulos del rol.
 * Uso: Renderizado por GestionUsuariosSistemaView como sub-pestaña "Vistas".
 *      Solo el administrador de sistemas puede editar (el backend valida con 403).
 * Nota: Los nombres de componentes describen funcionalidad (no referencian tickets).
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Save, Loader2, AlertCircle, CheckCircle, Eye } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { ModalExito } from '../common/ModalExito';

export const VistaPermisosView = () => {
    const { usuario } = useAuth();

    const [matriz, setMatriz] = useState([]);        // grupos -> roles -> módulos (actuales)
    const [modulos, setModulos] = useState([]);      // catálogo completo de módulos
    const [edicion, setEdicion] = useState({});      // rolId -> [moduloIds seleccionados]
    const [cargando, setCargando] = useState(true);
    const [guardandoRol, setGuardandoRol] = useState(null);
    const [error, setError] = useState('');
    const [exito, setExito] = useState('');

    // Carga matriz y catálogo de módulos
    const cargar = useCallback(async () => {
        setCargando(true);
        setError('');
        try {
            const [m, matrizRes] = await Promise.all([
                api.getModulosSistema(),
                api.getMatrizPermisos()
            ]);
            setModulos(m);
            setMatriz(matrizRes);
            // Precargar el estado de edición con los módulos actualmente asignados a cada rol
            const estadoInicial = {};
            matrizRes.forEach(grupo => {
                grupo.roles.forEach(rol => {
                    estadoInicial[rol.rol_id] = rol.modulos
                        .map(clave => m.find(mod => mod.clave === clave)?.id)
                        .filter(Boolean);
                });
            });
            setEdicion(estadoInicial);
        } catch (e) {
            setError(e.message);
        } finally {
            setCargando(false);
        }
    }, []);

    useEffect(() => { cargar(); }, [cargar]);

    // Toggle de un módulo para un rol específico
    const toggleModulo = (rolId, moduloId) => {
        setEdicion(prev => {
            const actuales = prev[rolId] || [];
            const nuevas = actuales.includes(moduloId)
                ? actuales.filter(id => id !== moduloId)
                : [...actuales, moduloId];
            return { ...prev, [rolId]: nuevas };
        });
    };

    // Detecta si un rol tiene cambios respecto a la matriz original
    const tieneCambios = (rol) => {
        const originales = (rol.modulos || [])
            .map(clave => modulos.find(m => m.clave === clave)?.id)
            .filter(Boolean)
            .sort((a, b) => a - b);
        const editados = [...(edicion[rol.rol_id] || [])].sort((a, b) => a - b);
        return JSON.stringify(originales) !== JSON.stringify(editados);
    };

    // Persiste los cambios de un rol (PUT a /vistas/permisos/{rolId})
    const guardarRol = async (rol) => {
        setGuardandoRol(rol.rol_id);
        setError('');
        try {
            await api.updatePermisosRol(rol.rol_id, {
                modulo_ids: edicion[rol.rol_id] || [],
                usuario_solicitante_id: usuario.id
            });
            setExito(`Permisos del rol "${rol.rol}" actualizados correctamente.`);
            // Sincronizar la matriz local con el cambio aplicado
            setMatriz(prev => prev.map(g => ({
                ...g,
                roles: g.roles.map(r =>
                    r.rol_id === rol.rol_id
                        ? { ...r, modulos: (edicion[rol.rol_id] || []).map(id => modulos.find(m => m.id === id)?.clave).filter(Boolean) }
                        : r
                )
            })));
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardandoRol(null);
        }
    };

    // Color del chip de ámbito del grupo
    const colorAmbito = (ambito) => ({
        SISTEMA: 'bg-purple-100 text-purple-700',
        GLOBAL: 'bg-blue-100 text-blue-700',
        COMEDOR: 'bg-emerald-100 text-emerald-700'
    }[ambito] || 'bg-slate-100 text-slate-600');

    return (
        <div className="animate-in fade-in duration-300">
            <div className="mb-5">
                <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                    <Eye className="text-emerald-600" size={20} /> Permisos por Vistas
                </h3>
                <p className="text-sm text-slate-500">
                    Defina qué módulos del sistema puede ver cada rol. Marque los módulos
                    permitidos y guarde los cambios por rol.
                </p>
            </div>

            {error && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                    <AlertCircle size={16} /> {error}
                </div>
            )}

            {cargando ? (
                <div className="p-8 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={28} /></div>
            ) : matriz.length === 0 ? (
                <p className="p-8 text-center text-slate-500">No se encontraron grupos en el sistema.</p>
            ) : (
                <div className="space-y-5">
                    {matriz.map(grupo => (
                        <div key={grupo.grupo_id} className="border border-slate-200 rounded-xl overflow-hidden">
                            {/* Encabezado del grupo */}
                            <div className="bg-slate-100 px-5 py-3 flex flex-wrap justify-between items-center gap-2">
                                <div>
                                    <p className="font-bold text-slate-800">{grupo.grupo}</p>
                                    <p className="text-xs text-slate-500">{grupo.roles.length} rol(es) en este grupo</p>
                                </div>
                                <span className={`px-3 py-1 rounded-full text-xs font-bold ${colorAmbito(grupo.ambito)}`}>
                                    {grupo.ambito}
                                </span>
                            </div>

                            {/* Roles con su matriz de módulos */}
                            <div className="divide-y divide-slate-200">
                                {grupo.roles.map(rol => (
                                    <div key={rol.rol_id} className="p-5">
                                        <div className="flex flex-wrap justify-between items-center gap-2 mb-3">
                                            <p className="font-semibold text-slate-800">{rol.rol}</p>
                                            <button
                                                onClick={() => guardarRol(rol)}
                                                disabled={guardandoRol === rol.rol_id || !tieneCambios(rol)}
                                                className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {guardandoRol === rol.rol_id ? (
                                                    <Loader2 className="animate-spin" size={14} />
                                                ) : (
                                                    <Save size={14} />
                                                )}
                                                {guardandoRol === rol.rol_id ? 'Guardando...' : 'Guardar cambios'}
                                            </button>
                                        </div>

                                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                                            {modulos.map(mod => {
                                                const marcado = (edicion[rol.rol_id] || []).includes(mod.id);
                                                return (
                                                    <label
                                                        key={mod.id}
                                                        className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${
                                                            marcado
                                                                ? 'bg-emerald-50 border-emerald-300'
                                                                : 'bg-white border-slate-200 hover:bg-slate-50'
                                                        }`}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            checked={marcado}
                                                            onChange={() => toggleModulo(rol.rol_id, mod.id)}
                                                            className="accent-emerald-600"
                                                        />
                                                        <span className="text-xs text-slate-700" title={mod.descripcion}>
                                                            {mod.nombre}
                                                        </span>
                                                    </label>
                                                );
                                            })}
                                        </div>

                                        {tieneCambios(rol) && (
                                            <p className="mt-2 text-xs text-amber-600 flex items-center gap-1">
                                                <AlertCircle size={12} /> Hay cambios sin guardar.
                                            </p>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <ModalExito isOpen={!!exito} onClose={() => setExito('')} mensaje={exito} />
        </div>
    );
};