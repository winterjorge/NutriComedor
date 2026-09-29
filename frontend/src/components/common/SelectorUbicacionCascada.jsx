/**
 * components/common/SelectorUbicacionCascada.jsx
 * Objetivo: Componente reutilizable de selección de ubicación geográfica en cascada
 *           (COM-27). Implementa el desbloqueo progresivo de los campos:
 *             - "Departamento" inicia desbloqueado; provincia, distrito y municipalidad bloqueados.
 *             - Al elegir departamento se desbloquea provincia (distrito y municipalidad siguen bloqueados).
 *             - Al elegir provincia se desbloquea distrito (municipalidad sigue bloqueada).
 *             - Al elegir distrito se desbloquea municipalidad.
 *             - Si cambia un nivel superior, se limpian automáticamente los niveles inferiores.
 *           Los datos provienen del catálogo geográfico (endpoints /ubicaciones), nunca de texto libre.
 * Uso: Importar en los formularios de creación/edición (usuarios, comedores, municipalidades).
 * Props:
 *   - valores: { departamento_id, provincia_id, distrito_id, municipalidad_id }
 *   - onCambiar: (nuevosValores) => void
 *   - mostrarMunicipalidad: bool (true por defecto; false para comedores que solo llegan a distrito)
 *   - deshabilitado: bool (bloquea toda la cascada)
 * Referencia: ticket COM-27 (solo trazabilidad; los nombres obedecen a la funcionalidad).
 */
import React, { useState, useEffect } from 'react';
import { Loader2, MapPin } from 'lucide-react';
import { api } from '../../services/api';

export const SelectorUbicacionCascada = ({
    valores,
    onCambiar,
    mostrarMunicipalidad = true,
    deshabilitado = false,
}) => {
    // Catálogos por nivel
    const [departamentos, setDepartamentos] = useState([]);
    const [provincias, setProvincias] = useState([]);
    const [distritos, setDistritos] = useState([]);
    const [municipalidades, setMunicipalidades] = useState([]);
    // Indicadores de carga por nivel
    const [cargando, setCargando] = useState({ dep: false, prov: false, dist: false, muni: false });

    // ---------- Carga de departamentos (nivel 1, al montar) ----------
    useEffect(() => {
        const cargar = async () => {
            setCargando(c => ({ ...c, dep: true }));
            try {
                setDepartamentos(await api.getDepartamentos());
            } catch (e) {
                console.error('Error cargando departamentos:', e);
            } finally {
                setCargando(c => ({ ...c, dep: false }));
            }
        };
        cargar();
    }, []);

    // ---------- Carga de provincias (nivel 2, al elegir departamento) ----------
    useEffect(() => {
        const cargar = async () => {
            if (!valores.departamento_id) {
                setProvincias([]);
                return;
            }
            setCargando(c => ({ ...c, prov: true }));
            try {
                setProvincias(await api.getProvincias(valores.departamento_id));
            } catch (e) {
                console.error('Error cargando provincias:', e);
            } finally {
                setCargando(c => ({ ...c, prov: false }));
            }
        };
        cargar();
    }, [valores.departamento_id]);

    // ---------- Carga de distritos (nivel 3, al elegir provincia) ----------
    useEffect(() => {
        const cargar = async () => {
            if (!valores.provincia_id) {
                setDistritos([]);
                return;
            }
            setCargando(c => ({ ...c, dist: true }));
            try {
                setDistritos(await api.getDistritos(valores.provincia_id));
            } catch (e) {
                console.error('Error cargando distritos:', e);
            } finally {
                setCargando(c => ({ ...c, dist: false }));
            }
        };
        cargar();
    }, [valores.provincia_id]);

    // ---------- Carga de municipalidades (nivel 4, al elegir distrito) ----------
    useEffect(() => {
        const cargar = async () => {
            if (!valores.distrito_id || !mostrarMunicipalidad) {
                setMunicipalidades([]);
                return;
            }
            setCargando(c => ({ ...c, muni: true }));
            try {
                setMunicipalidades(await api.getMunicipalidadesPorDistrito(valores.distrito_id));
            } catch (e) {
                console.error('Error cargando municipalidades:', e);
            } finally {
                setCargando(c => ({ ...c, muni: false }));
            }
        };
        cargar();
    }, [valores.distrito_id, mostrarMunicipalidad]);

    // ---------- Manejadores: limpian los niveles inferiores al cambiar uno superior ----------
    const cambiarDepartamento = (e) => {
        const id = e.target.value ? Number(e.target.value) : null;
        onCambiar({
            ...valores,
            departamento_id: id,
            provincia_id: null,      // limpia niveles inferiores
            distrito_id: null,
            municipalidad_id: null,
        });
    };

    const cambiarProvincia = (e) => {
        const id = e.target.value ? Number(e.target.value) : null;
        onCambiar({
            ...valores,
            provincia_id: id,
            distrito_id: null,       // limpia niveles inferiores
            municipalidad_id: null,
        });
    };

    const cambiarDistrito = (e) => {
        const id = e.target.value ? Number(e.target.value) : null;
        onCambiar({
            ...valores,
            distrito_id: id,
            municipalidad_id: null,  // limpia nivel inferior
        });
    };

    const cambiarMunicipalidad = (e) => {
        const id = e.target.value ? Number(e.target.value) : null;
        onCambiar({ ...valores, municipalidad_id: id });
    };

    // ---------- Reglas de desbloqueo progresivo ----------
    const bloqueadoDep = deshabilitado;
    const bloqueadoProv = deshabilitado || !valores.departamento_id;
    const bloqueadoDist = deshabilitado || !valores.provincia_id;
    const bloqueadoMuni = deshabilitado || !valores.distrito_id;

    // Estilo compartido de los selects según su estado
    const claseSelect = (bloqueado) =>
        `w-full px-3 py-2 border rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500 ${
            bloqueado ? 'bg-slate-100 text-slate-400 cursor-not-allowed border-slate-200' : 'border-slate-300'
        }`;

    return (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
            <p className="text-xs font-semibold text-slate-500 flex items-center gap-1">
                <MapPin size={13} className="text-emerald-600" />
                Ubicación geográfica (selección en cascada)
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* Nivel 1: Departamento */}
                <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">Departamento</label>
                    <div className="relative">
                        <select
                            value={valores.departamento_id || ''}
                            onChange={cambiarDepartamento}
                            disabled={bloqueadoDep || cargando.dep}
                            className={claseSelect(bloqueadoDep)}
                        >
                            <option value="">Seleccione departamento...</option>
                            {departamentos.map(d => (
                                <option key={d.id} value={d.id}>{d.nombre}</option>
                            ))}
                        </select>
                        {cargando.dep && (
                            <Loader2 size={14} className="animate-spin absolute right-3 top-2.5 text-emerald-600" />
                        )}
                    </div>
                </div>

                {/* Nivel 2: Provincia */}
                <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">Provincia</label>
                    <div className="relative">
                        <select
                            value={valores.provincia_id || ''}
                            onChange={cambiarProvincia}
                            disabled={bloqueadoProv || cargando.prov}
                            className={claseSelect(bloqueadoProv)}
                        >
                            <option value="">
                                {valores.departamento_id ? 'Seleccione provincia...' : 'Primero elija departamento'}
                            </option>
                            {provincias.map(p => (
                                <option key={p.id} value={p.id}>{p.nombre}</option>
                            ))}
                        </select>
                        {cargando.prov && (
                            <Loader2 size={14} className="animate-spin absolute right-3 top-2.5 text-emerald-600" />
                        )}
                    </div>
                </div>

                {/* Nivel 3: Distrito */}
                <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">Distrito</label>
                    <div className="relative">
                        <select
                            value={valores.distrito_id || ''}
                            onChange={cambiarDistrito}
                            disabled={bloqueadoDist || cargando.dist}
                            className={claseSelect(bloqueadoDist)}
                        >
                            <option value="">
                                {valores.provincia_id ? 'Seleccione distrito...' : 'Primero elija provincia'}
                            </option>
                            {distritos.map(d => (
                                <option key={d.id} value={d.id}>{d.nombre}</option>
                            ))}
                        </select>
                        {cargando.dist && (
                            <Loader2 size={14} className="animate-spin absolute right-3 top-2.5 text-emerald-600" />
                        )}
                    </div>
                </div>

                {/* Nivel 4: Municipalidad (opcional según el formulario) */}
                {mostrarMunicipalidad && (
                    <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">Municipalidad</label>
                        <div className="relative">
                            <select
                                value={valores.municipalidad_id || ''}
                                onChange={cambiarMunicipalidad}
                                disabled={bloqueadoMuni || cargando.muni}
                                className={claseSelect(bloqueadoMuni)}
                            >
                                <option value="">
                                    {valores.distrito_id ? 'Seleccione municipalidad...' : 'Primero elija distrito'}
                                </option>
                                {municipalidades.map(m => (
                                    <option key={m.id} value={m.id}>{m.nombre}</option>
                                ))}
                            </select>
                            {cargando.muni && (
                                <Loader2 size={14} className="animate-spin absolute right-3 top-2.5 text-emerald-600" />
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};