/**
 * components/usuarios/ModalEditarUsuario.jsx
 * Objetivo: Modal de edición de usuarios (corrección COM-26): precarga los datos
 *           personales, el perfil actual, el grupo/rol y el alcance vigente
 *           (municipalidades o comedores) mediante el endpoint detalle-flujo, y
 *           permite modificar datos, perfil/rol y alcance con las mismas reglas
 *           dinámicas de la creación (sin campo de contraseña).
 * Uso: Abierto por las vistas de gestión de usuarios pasando el `usuarioId` a editar;
 *      `onExito` al guardar. El backend valida la matriz de creación, el alcance y
 *      la unicidad de cargos permanentes (excluyendo al propio usuario editado).
 * Nota: Los nombres describen funcionalidad (no referencian tickets).
 */
import React, { useState, useEffect } from 'react';
import { X, UserCog, Loader2, AlertCircle, ShieldCheck } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { AutocompleteBusqueda } from '../common/AutocompleteBusqueda';

// Etiquetas legibles de los perfiles objetivo
const ETIQUETAS_PERFIL = {
    ADMINISTRADOR_SISTEMA: 'Administrador de Sistema',
    ADMINISTRATIVO: 'Administrativo (Municipalidad)',
    DIRECTIVO: 'Directivo (Comedor)',
    OPERATIVO: 'Operativo (Comedor)',
};

export const ModalEditarUsuario = ({ usuarioId, onClose, onExito }) => {
    const { usuario } = useAuth();

    // Contexto de creación del solicitante y detalle del usuario a editar
    const [contexto, setContexto] = useState(null);
    const [detalle, setDetalle] = useState(null);
    const [cargando, setCargando] = useState(true);
    const [errorCarga, setErrorCarga] = useState('');

    // Datos personales (precargados)
    const [form, setForm] = useState({
        tipo_documento: 'DNI',
        documento_identidad: '',
        nombres: '',
        apellido_paterno: '',
        apellido_materno: '',
        fecha_nacimiento: '',
    });

    // Perfil objetivo, grupo/rol y alcance seleccionado (precargados)
    const [perfilObjetivo, setPerfilObjetivo] = useState('');
    const [rolId, setRolId] = useState('');
    const [municipalidadesSel, setMunicipalidadesSel] = useState([]);
    const [comedoresSel, setComedoresSel] = useState([]);

    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Precarga en paralelo: contexto del solicitante + detalle del usuario objetivo
    useEffect(() => {
        const cargar = async () => {
            setCargando(true);
            setErrorCarga('');
            try {
                const [ctx, det] = await Promise.all([
                    api.getContextoCreacion(usuario.id),
                    api.getDetalleFlujoUsuario(usuarioId, usuario.id),
                ]);
                setContexto(ctx);
                setDetalle(det);
                setForm({
                    tipo_documento: det.usuario.tipo_documento || 'DNI',
                    documento_identidad: det.usuario.documento_identidad || '',
                    nombres: det.usuario.nombres || '',
                    apellido_paterno: det.usuario.apellido_paterno || '',
                    apellido_materno: det.usuario.apellido_materno || '',
                    fecha_nacimiento: det.usuario.fecha_nacimiento ? String(det.usuario.fecha_nacimiento).slice(0, 10) : '',
                });
                setPerfilObjetivo(det.perfil_objetivo);
                setRolId(det.rol_id ? String(det.rol_id) : '');
                setMunicipalidadesSel(det.municipalidades || []);
                setComedoresSel(det.comedores || []);
            } catch (e) {
                setErrorCarga(e.message);
            } finally {
                setCargando(false);
            }
        };
        cargar();
    }, [usuarioId, usuario.id]);

    // Grupo del catálogo correspondiente al perfil objetivo elegido
    const grupoPerfil = contexto?.grupos?.find(g => g.perfil === perfilObjetivo) || null;

    // Al cambiar el perfil objetivo se resetean el rol y el alcance seleccionado
    const cambiarPerfil = (perfil) => {
        setPerfilObjetivo(perfil);
        setRolId('');
        setMunicipalidadesSel([]);
        setComedoresSel([]);
    };

    // Ids permitidos según el alcance del creador (para filtrar el autocompletado)
    const idsMunicipalidadesPermitidas = (contexto?.municipalidades || []).map(m => m.id);
    const idsComedoresPermitidos = (contexto?.comedores || []).map(c => c.id);

    const esAdministrativo = perfilObjetivo === 'ADMINISTRATIVO';
    const esComedor = perfilObjetivo === 'DIRECTIVO' || perfilObjetivo === 'OPERATIVO';

    const validar = () => {
        if (!form.documento_identidad.trim()) return 'El documento es obligatorio.';
        if (!form.nombres.trim()) return 'Los nombres son obligatorios.';
        if (!perfilObjetivo) return 'Seleccione el perfil del usuario.';
        if (!grupoPerfil || !rolId) return 'Seleccione el rol del usuario.';
        if (esAdministrativo && municipalidadesSel.length === 0) {
            return 'Debe seleccionar al menos una municipalidad para el perfil Administrativo.';
        }
        if (esComedor && comedoresSel.length === 0) {
            return 'Debe seleccionar al menos un comedor para este perfil.';
        }
        return '';
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        const errValidacion = validar();
        if (errValidacion) {
            setError(errValidacion);
            return;
        }
        setGuardando(true);
        try {
            await api.editarUsuario(usuarioId, {
                tipo_documento: form.tipo_documento,
                documento_identidad: form.documento_identidad.trim(),
                nombres: form.nombres.trim(),
                apellido_paterno: form.apellido_paterno.trim() || null,
                apellido_materno: form.apellido_materno.trim() || null,
                fecha_nacimiento: form.fecha_nacimiento || null,
                perfil_objetivo: perfilObjetivo,
                grupo_id: grupoPerfil.grupo_id,
                rol_id: Number(rolId),
                municipalidad_ids: esAdministrativo ? municipalidadesSel.map(m => m.id) : [],
                comedor_ids: esComedor ? comedoresSel.map(c => c.id) : [],
                usuario_solicitante_id: usuario.id,
            });
            onExito();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col overflow-hidden">
                {/* Encabezado */}
                <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                    <h3 className="font-bold text-lg flex items-center gap-2">
                        <UserCog size={20} /> Editar Usuario
                    </h3>
                    <button onClick={onClose} className="text-emerald-100 hover:text-white transition-colors" aria-label="Cerrar">
                        <X size={22} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto">
                    {errorCarga && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                            <AlertCircle size={16} /> {errorCarga}
                        </div>
                    )}
                    {error && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                            <AlertCircle size={16} /> {error}
                        </div>
                    )}

                    {cargando ? (
                        <div className="p-8 text-center text-emerald-600">
                            <Loader2 className="animate-spin mx-auto" size={28} />
                            <p className="text-sm mt-2 text-slate-500">Cargando datos del usuario...</p>
                        </div>
                    ) : (
                        <>
                            {/* Datos personales */}
                            <div className="grid grid-cols-3 gap-3">
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Tipo doc.</label>
                                    <select value={form.tipo_documento}
                                        onChange={(e) => setForm({ ...form, tipo_documento: e.target.value })}
                                        className="w-full px-2 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500">
                                        <option value="DNI">DNI</option>
                                        <option value="CE">C.E.</option>
                                    </select>
                                </div>
                                <div className="col-span-2">
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Documento *</label>
                                    <input type="text" value={form.documento_identidad}
                                        onChange={(e) => setForm({ ...form, documento_identidad: e.target.value.replace(/[^0-9A-Za-z]/g, '').slice(0, 15) })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Nombres *</label>
                                <input type="text" value={form.nombres}
                                    onChange={(e) => setForm({ ...form, nombres: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                            </div>

                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Apellido paterno</label>
                                    <input type="text" value={form.apellido_paterno}
                                        onChange={(e) => setForm({ ...form, apellido_paterno: e.target.value })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                                </div>
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Apellido materno</label>
                                    <input type="text" value={form.apellido_materno}
                                        onChange={(e) => setForm({ ...form, apellido_materno: e.target.value })}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                                </div>
                            </div>

                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Fecha de nacimiento</label>
                                <input type="date" value={form.fecha_nacimiento}
                                    onChange={(e) => setForm({ ...form, fecha_nacimiento: e.target.value })}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                            </div>

                            {/* Perfil objetivo */}
                            <div>
                                <label className="block text-xs font-semibold text-slate-600 mb-1">Perfil del usuario *</label>
                                <select value={perfilObjetivo}
                                    onChange={(e) => cambiarPerfil(e.target.value)}
                                    className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500">
                                    <option value="">Seleccionar perfil...</option>
                                    {(contexto?.perfiles_permitidos || []).map(p => (
                                        <option key={p} value={p}>{ETIQUETAS_PERFIL[p] || p}</option>
                                    ))}
                                </select>
                                <p className="mt-1 text-[11px] text-slate-400">
                                    Al cambiar el perfil se reemplazan las membresías del grupo elegido;
                                    las de otros grupos no se alteran.
                                </p>
                            </div>

                            {/* Rol del grupo correspondiente */}
                            {perfilObjetivo && grupoPerfil && (
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                                        Rol ({grupoPerfil.grupo}) *
                                    </label>
                                    <select value={rolId}
                                        onChange={(e) => setRolId(e.target.value)}
                                        className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500">
                                        <option value="">Seleccionar rol...</option>
                                        {grupoPerfil.roles.map(r => (
                                            <option key={r.id} value={r.id}>{r.nombre}</option>
                                        ))}
                                    </select>
                                </div>
                            )}

                            {/* Alcance: municipalidades (solo Administrativo) */}
                            {esAdministrativo && (
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Municipalidades de acceso *</label>
                                    <AutocompleteBusqueda
                                        placeholder="Buscar municipalidad..."
                                        buscarFn={api.buscarMunicipalidades}
                                        seleccionados={municipalidadesSel}
                                        onSeleccionar={(item) => setMunicipalidadesSel([...municipalidadesSel, item])}
                                        onQuitar={(item) => setMunicipalidadesSel(municipalidadesSel.filter(m => m.id !== item.id))}
                                        getLabel={(m) => m.nombre}
                                        getSubLabel={(m) => `${m.distrito}, ${m.provincia} - ${m.departamento}`}
                                        permitidos={idsMunicipalidadesPermitidas}
                                    />
                                </div>
                            )}

                            {/* Alcance: comedores (Directivo y Operativo) */}
                            {esComedor && (
                                <div>
                                    <label className="block text-xs font-semibold text-slate-600 mb-1">Comedores de acceso *</label>
                                    <AutocompleteBusqueda
                                        placeholder="Buscar comedor..."
                                        buscarFn={api.buscarComedores}
                                        seleccionados={comedoresSel}
                                        onSeleccionar={(item) => setComedoresSel([...comedoresSel, item])}
                                        onQuitar={(item) => setComedoresSel(comedoresSel.filter(c => c.id !== item.id))}
                                        getLabel={(c) => c.nombre}
                                        getSubLabel={(c) => `${c.distrito}, ${c.ciudad}`}
                                        permitidos={idsComedoresPermitidos}
                                    />
                                    <p className="mt-1 text-[11px] text-slate-400 flex items-center gap-1">
                                        <ShieldCheck size={11} /> Los cargos Presidente, Tesorero y Secretario no pueden repetirse por comedor.
                                    </p>
                                </div>
                            )}
                        </>
                    )}

                    {/* Acciones */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                            Cancelar
                        </button>
                        <button type="submit" disabled={guardando || cargando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                            {guardando && <Loader2 className="animate-spin" size={15} />} Guardar cambios
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};