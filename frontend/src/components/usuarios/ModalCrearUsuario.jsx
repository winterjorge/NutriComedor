/**
 * components/usuarios/ModalCrearUsuario.jsx
 * Objetivo: Modal de creación de usuarios con el flujo por perfil (COM-26) y la
 *           ubicación geográfica en cascada con desbloqueo progresivo (COM-27).
 *           Para el personal que NO es administrador de sistema se muestran los campos
 *           departamento -> provincia -> distrito -> municipalidad, que se van
 *           desbloqueando a medida que se selecciona el nivel superior.
 * Uso: Abierto por las vistas de gestión de usuarios; `onExito` al guardar.
 * Referencia: tickets COM-26 (flujo por perfil) y COM-27 (ubicación en cascada).
 */
import React, { useState, useEffect } from 'react';
import { X, UserPlus, Loader2, AlertCircle, MapPin } from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { AutocompleteBusqueda } from '../common/AutocompleteBusqueda';
// COM-27: selector de ubicación en cascada con desbloqueo progresivo
import { SelectorUbicacionCascada } from '../common/SelectorUbicacionCascada';

const PERFIL_ADMIN_SISTEMA = 'ADMINISTRADOR_SISTEMA';

const FORM_INICIAL = {
    tipo_documento: 'DNI',
    documento_identidad: '',
    nombres: '',
    apellido_paterno: '',
    apellido_materno: '',
    fecha_nacimiento: '',
    clave_inicial: '',
    confirmar_clave: '',
};

// COM-27: estado inicial de la ubicación geográfica en cascada
const UBICACION_INICIAL = {
    departamento_id: null,
    provincia_id: null,
    distrito_id: null,
    municipalidad_id: null,
};

export const ModalCrearUsuario = ({ onClose, onExito }) => {
    const { usuario } = useAuth();

    // Datos personales del nuevo usuario
    const [form, setForm] = useState(FORM_INICIAL);
    // Perfil objetivo, grupo/rol y alcance (COM-26)
    const [perfilObjetivo, setPerfilObjetivo] = useState('');
    const [grupoId, setGrupoId] = useState('');
    const [rolId, setRolId] = useState('');
    const [municipalidadesSel, setMunicipalidadesSel] = useState([]);
    const [comedoresSel, setComedoresSel] = useState([]);
    // COM-27: ubicación geográfica en cascada
    const [ubicacion, setUbicacion] = useState(UBICACION_INICIAL);

    const [contexto, setContexto] = useState(null);
    const [error, setError] = useState('');
    const [guardando, setGuardando] = useState(false);

    // Carga el contexto de creación (perfiles permitidos para el solicitante)
    useEffect(() => {
        const cargar = async () => {
            try {
                setContexto(await api.getContextoCreacion(usuario.id));
            } catch (e) {
                setError(e.message);
            }
        };
        cargar();
    }, [usuario.id]);

    const grupoPerfil = contexto?.grupos?.find(g => g.perfil === perfilObjetivo) || null;

    // COM-27: el personal que NO es administrador de sistema requiere ubicación geográfica
    const requiereUbicacion = !!perfilObjetivo && perfilObjetivo !== PERFIL_ADMIN_SISTEMA;

    const cambiarPerfil = (perfil) => {
        setPerfilObjetivo(perfil);
        setGrupoId('');
        setRolId('');
        setMunicipalidadesSel([]);
        setComedoresSel([]);
        // COM-27: al cambiar el perfil se reinicia también la ubicación
        setUbicacion(UBICACION_INICIAL);
    };

    const validar = () => {
        if (!form.documento_identidad.trim()) return 'El documento es obligatorio.';
        if (!form.nombres.trim()) return 'Los nombres son obligatorios.';
        if (!form.clave_inicial || form.clave_inicial !== form.confirmar_clave) {
            return 'Las contraseñas no coinciden o están vacías.';
        }
        if (!perfilObjetivo) return 'Seleccione el perfil del usuario.';
        if (!grupoId || !rolId) return 'Seleccione el grupo y el rol.';
        // COM-27: para personal no-admin se exige la ubicación geográfica completa
        if (requiereUbicacion) {
            if (!ubicacion.departamento_id || !ubicacion.provincia_id || !ubicacion.distrito_id) {
                return 'Complete la ubicación geográfica (departamento, provincia y distrito).';
            }
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
            const payload = {
                tipo_documento: form.tipo_documento,
                documento_identidad: form.documento_identidad.trim(),
                nombres: form.nombres.trim(),
                apellido_paterno: form.apellido_paterno.trim() || null,
                apellido_materno: form.apellido_materno.trim() || null,
                fecha_nacimiento: form.fecha_nacimiento || null,
                clave_inicial: form.clave_inicial,
                perfil_objetivo: perfilObjetivo,
                grupo_id: Number(grupoId),
                rol_id: Number(rolId),
                municipalidad_ids: municipalidadesSel.map(m => m.id),
                comedor_ids: comedoresSel.map(c => c.id),
                usuario_solicitante_id: usuario.id,
                // COM-27: ubicación geográfica del nuevo usuario (solo personal no-admin)
                departamento_id: requiereUbicacion ? ubicacion.departamento_id : null,
                provincia_id: requiereUbicacion ? ubicacion.provincia_id : null,
                distrito_id: requiereUbicacion ? ubicacion.distrito_id : null,
                municipalidad_id: requiereUbicacion ? ubicacion.municipalidad_id : null,
            };
            await api.crearUsuario(payload);
            onExito();
        } catch (err) {
            setError(err.message);
        } finally {
            setGuardando(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden">
                {/* Encabezado */}
                <div className="flex justify-between items-center px-6 py-4 bg-emerald-700 text-white shrink-0">
                    <h3 className="font-bold text-lg flex items-center gap-2">
                        <UserPlus size={20} /> Nuevo Usuario
                    </h3>
                    <button onClick={onClose} className="text-emerald-100 hover:text-white transition-colors" aria-label="Cerrar">
                        <X size={22} />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto">
                    {error && (
                        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
                            <AlertCircle size={16} /> {error}
                        </div>
                    )}

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
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500"
                                placeholder="Ej: 70000001" />
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
                                <option key={p} value={p}>{p}</option>
                            ))}
                        </select>
                    </div>

                    {/* Grupo y rol */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Grupo *</label>
                            <select value={grupoId}
                                onChange={(e) => { setGrupoId(e.target.value); setRolId(''); }}
                                disabled={!grupoPerfil}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50">
                                <option value="">Seleccionar grupo...</option>
                                {grupoPerfil && <option value={grupoPerfil.grupo_id}>{grupoPerfil.grupo}</option>}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Rol *</label>
                            <select value={rolId}
                                onChange={(e) => setRolId(e.target.value)}
                                disabled={!grupoPerfil}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50">
                                <option value="">Seleccionar rol...</option>
                                {(grupoPerfil?.roles || []).map(r => (
                                    <option key={r.id} value={r.id}>{r.nombre}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    {/* COM-27: Ubicación geográfica en cascada (solo personal no-admin) */}
                    {requiereUbicacion && (
                        <div>
                            <label className="flex items-center gap-1 text-xs font-semibold text-slate-600 mb-1">
                                <MapPin size={12} className="text-emerald-600" /> Ubicación geográfica *
                            </label>
                            <SelectorUbicacionCascada
                                valores={ubicacion}
                                onCambiar={setUbicacion}
                                mostrarMunicipalidad={true}
                            />
                        </div>
                    )}

                    {/* Alcance por municipalidades (perfil Administrativo) */}
                    {perfilObjetivo === 'ADMINISTRATIVO' && (
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Municipalidades de acceso</label>
                            <AutocompleteBusqueda
                                placeholder="Buscar municipalidad..."
                                buscarFn={api.buscarMunicipalidades}
                                seleccionados={municipalidadesSel}
                                onSeleccionar={(item) => setMunicipalidadesSel([...municipalidadesSel, item])}
                                onQuitar={(item) => setMunicipalidadesSel(municipalidadesSel.filter(m => m.id !== item.id))}
                                getLabel={(m) => m.nombre}
                                getSubLabel={(m) => m.distrito}
                            />
                        </div>
                    )}

                    {/* Alcance por comedores (perfiles Directivo / Operativo) */}
                    {(perfilObjetivo === 'DIRECTIVO' || perfilObjetivo === 'OPERATIVO') && (
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Comedores de acceso</label>
                            <AutocompleteBusqueda
                                placeholder="Buscar comedor..."
                                buscarFn={api.buscarComedores}
                                seleccionados={comedoresSel}
                                onSeleccionar={(item) => setComedoresSel([...comedoresSel, item])}
                                onQuitar={(item) => setComedoresSel(comedoresSel.filter(c => c.id !== item.id))}
                                getLabel={(c) => c.nombre}
                                getSubLabel={(c) => c.distrito}
                            />
                        </div>
                    )}

                    {/* Contraseña */}
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Clave inicial *</label>
                            <input type="password" value={form.clave_inicial}
                                onChange={(e) => setForm({ ...form, clave_inicial: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-600 mb-1">Confirmar clave *</label>
                            <input type="password" value={form.confirmar_clave}
                                onChange={(e) => setForm({ ...form, confirmar_clave: e.target.value })}
                                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
                        </div>
                    </div>

                    {/* Acciones */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button type="button" onClick={onClose}
                            className="px-5 py-2 border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-100 transition-colors text-sm">
                            Cancelar
                        </button>
                        <button type="submit" disabled={guardando}
                            className="px-5 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2">
                            {guardando && <Loader2 className="animate-spin" size={15} />} Crear usuario
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};