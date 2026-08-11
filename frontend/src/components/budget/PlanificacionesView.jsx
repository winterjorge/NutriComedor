import React, { useState, useEffect } from 'react';
import { Calendar, ShoppingBag, Eye, Trash2, Download, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { api } from '../../services/api';
import { ModalConfirmacion } from '../common/ModalConfirmacion';

export const PlanificacionesView = () => {
    const [planificaciones, setPlanificaciones] = useState([]);
    const [cargando, setCargando] = useState(true);
    const [planificacionSel, setPlanificacionSel] = useState(null);
    const [listaCompras, setListaCompras] = useState(null);
    const [cargandoLista, setCargandoLista] = useState(false);
    const [tipoLista, setTipoLista] = useState('semanal'); // 'semanal' o 'diaria'
    const [diaSeleccionado, setDiaSeleccionado] = useState(null);
    const [modalEliminar, setModalEliminar] = useState(null);
    const [error, setError] = useState('');

    useEffect(() => {
        cargarPlanificaciones();
    }, []);

    const cargarPlanificaciones = async () => {
        setCargando(true);
        setError('');
        try {
            const data = await api.getPlanificaciones();
            setPlanificaciones(data);
        } catch (err) {
            console.error('Error cargando planificaciones:', err);
            setError('Error al cargar las planificaciones guardadas');
        } finally {
            setCargando(false);
        }
    };

    const verDetalle = async (id) => {
        setCargando(true);
        setError('');
        try {
            const data = await api.getPlanificacionDetalle(id);
            setPlanificacionSel(data);
            setListaCompras(null);
            setTipoLista('semanal');
            setDiaSeleccionado(null);
        } catch (err) {
            console.error('Error cargando detalle:', err);
            setError('Error al cargar el detalle de la planificación');
        } finally {
            setCargando(false);
        }
    };

    const generarListaCompras = async (dia = null) => {
        if (!planificacionSel) return;
        
        setCargandoLista(true);
        setError('');
        try {
            const data = await api.getListaCompras(planificacionSel.id, dia);
            setListaCompras(data);
            setTipoLista(dia ? 'diaria' : 'semanal');
            setDiaSeleccionado(dia);
        } catch (err) {
            console.error('Error generando lista de compras:', err);
            setError('Error al generar la lista de compras');
        } finally {
            setCargandoLista(false);
        }
    };

    const confirmarEliminacion = async () => {
        if (!modalEliminar) return;
        
        try {
            await api.eliminarPlanificacion(modalEliminar.id);
            setPlanificaciones(planificaciones.filter(p => p.id !== modalEliminar.id));
            if (planificacionSel && planificacionSel.id === modalEliminar.id) {
                setPlanificacionSel(null);
                setListaCompras(null);
            }
            setModalEliminar(null);
        } catch (err) {
            console.error('Error eliminando planificación:', err);
            setError('Error al eliminar la planificación');
        }
    };

    const exportarListaCompras = () => {
        if (!listaCompras) return;
        
        let contenido = `LISTA DE COMPRAS - ${tipoLista === 'diaria' ? `Día ${diaSeleccionado}` : 'SEMANAL'}\n`;
        contenido += `Planificación ID: ${listaCompras.planificacion_id}\n`;
        contenido += `Total de ingredientes: ${listaCompras.total_ingredientes}\n\n`;
        contenido += `${'INGREDIENTE'.padEnd(40)} ${'CANTIDAD'.padEnd(10)} ${'UNIDAD'.padEnd(10)} DÍAS DE USO\n`;
        contenido += '-'.repeat(80) + '\n';
        
        listaCompras.lista_compras.forEach(item => {
            const nombre = item.nombre.padEnd(40);
            const cantidad = item.cantidad.toString().padEnd(10);
            const unidad = item.unidad.padEnd(10);
            const dias = item.dias_uso.join(', ');
            contenido += `${nombre} ${cantidad} ${unidad} ${dias}\n`;
        });
        
        const blob = new Blob([contenido], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `lista_compras_${planificacionSel.id}_${tipoLista}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const formatearFecha = (fechaStr) => {
        if (!fechaStr) return '-';
        const fecha = new Date(fechaStr);
        return fecha.toLocaleDateString('es-PE', { year: 'numeric', month: 'long', day: 'numeric' });
    };

    if (cargando) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="animate-spin text-emerald-600" size={32} />
            </div>
        );
    }

    return (
        <div className="animate-in fade-in duration-300">
            {error && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2">
                    <AlertCircle size={20} />
                    {error}
                </div>
            )}

            {!planificacionSel ? (
                // Lista de planificaciones guardadas
                <div>
                    <div className="mb-6">
                        <h2 className="text-xl font-bold text-slate-800">Planificaciones Guardadas</h2>
                        <p className="text-sm text-slate-500">Consulta tus planificaciones semanales y genera listas de compras</p>
                    </div>

                    {planificaciones.length === 0 ? (
                        <div className="bg-slate-50 border border-slate-200 rounded-xl p-12 text-center">
                            <Calendar className="mx-auto text-slate-400 mb-4" size={48} />
                            <p className="text-slate-600 font-medium">No hay planificaciones guardadas</p>
                            <p className="text-slate-500 text-sm mt-2">Genera una nueva planificación desde la pestaña "Presupuesto"</p>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {planificaciones.map((plan) => (
                                <div key={plan.id} className="bg-white border border-slate-200 rounded-xl p-5 hover:shadow-md transition-shadow">
                                    <div className="flex justify-between items-start">
                                        <div className="flex-1">
                                            <div className="flex items-center gap-3 mb-2">
                                                <h3 className="font-bold text-lg text-slate-800">
                                                    Planificación #{plan.id}
                                                </h3>
                                                <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                                                    plan.viable 
                                                        ? 'bg-emerald-100 text-emerald-700' 
                                                        : 'bg-amber-100 text-amber-700'
                                                }`}>
                                                    {plan.viable ? 'Viable' : 'No Viable'}
                                                </span>
                                            </div>
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                                <div>
                                                    <p className="text-slate-500">Fecha de Referencia</p>
                                                    <p className="font-medium text-slate-700">{formatearFecha(plan.fecha_referencia)}</p>
                                                </div>
                                                <div>
                                                    <p className="text-slate-500">Presupuesto</p>
                                                    <p className="font-medium text-slate-700">S/ {parseFloat(plan.presupuesto).toFixed(2)}</p>
                                                </div>
                                                <div>
                                                    <p className="text-slate-500">Costo Total</p>
                                                    <p className="font-medium text-slate-700">S/ {parseFloat(plan.costo_total_semana).toFixed(2)}</p>
                                                </div>
                                                <div>
                                                    <p className="text-slate-500">Días</p>
                                                    <p className="font-medium text-slate-700">{plan.total_dias} días</p>
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex gap-2 ml-4">
                                            <button
                                                onClick={() => verDetalle(plan.id)}
                                                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                                            >
                                                <Eye size={18} />
                                                Ver Detalle
                                            </button>
                                            <button
                                                onClick={() => setModalEliminar(plan)}
                                                className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            ) : (
                // Detalle de planificación y lista de compras
                <div>
                    <div className="mb-6">
                        <button
                            onClick={() => {
                                setPlanificacionSel(null);
                                setListaCompras(null);
                            }}
                            className="text-slate-600 hover:text-slate-800 mb-2 flex items-center gap-2"
                        >
                            ← Volver a planificaciones
                        </button>
                        <h2 className="text-xl font-bold text-slate-800">
                            Detalle de Planificación #{planificacionSel.id}
                        </h2>
                        <p className="text-sm text-slate-500">
                            {formatearFecha(planificacionSel.fecha_referencia)} - {planificacionSel.dias_operativos} días
                        </p>
                    </div>

                    {/* Resumen financiero */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                        <div className="bg-white p-4 rounded-xl border border-slate-200">
                            <p className="text-xs text-slate-500 uppercase">Presupuesto</p>
                            <p className="text-xl font-bold text-slate-800">S/ {parseFloat(planificacionSel.presupuesto).toFixed(2)}</p>
                        </div>
                        <div className="bg-white p-4 rounded-xl border border-slate-200">
                            <p className="text-xs text-slate-500 uppercase">Costo Total</p>
                            <p className="text-xl font-bold text-slate-800">S/ {parseFloat(planificacionSel.costo_total_semana).toFixed(2)}</p>
                        </div>
                        <div className="bg-white p-4 rounded-xl border border-slate-200">
                            <p className="text-xs text-slate-500 uppercase">Recolección</p>
                            <p className="text-xl font-bold text-emerald-600">S/ {parseFloat(planificacionSel.recoleccion_total_proyectada).toFixed(2)}</p>
                        </div>
                        <div className="bg-white p-4 rounded-xl border border-slate-200">
                            <p className="text-xs text-slate-500 uppercase">Margen</p>
                            <p className={`text-xl font-bold ${planificacionSel.margen >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                                S/ {parseFloat(planificacionSel.margen).toFixed(2)}
                            </p>
                        </div>
                    </div>

                    {/* Tabla de días planificados */}
                    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mb-6">
                        <div className="p-4 border-b bg-slate-50">
                            <h3 className="font-bold text-slate-800">Menú Semanal</h3>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full">
                                <thead className="bg-slate-50">
                                    <tr>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-slate-600 uppercase">Día</th>
                                        <th className="px-4 py-3 text-left text-xs font-medium text-slate-600 uppercase">Receta</th>
                                        <th className="px-4 py-3 text-center text-xs font-medium text-slate-600 uppercase">Comensales</th>
                                        <th className="px-4 py-3 text-right text-xs font-medium text-slate-600 uppercase">Costo</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200">
                                    {planificacionSel.dias.map((dia) => (
                                        <tr key={dia.dia} className="hover:bg-slate-50">
                                            <td className="px-4 py-3">
                                                <div className="font-medium text-slate-800">{dia.dia_nombre}</div>
                                                <div className="text-xs text-slate-500">Día {dia.dia}</div>
                                            </td>
                                            <td className="px-4 py-3">
                                                <div className="font-medium text-slate-700">{dia.nombre_receta}</div>
                                            </td>
                                            <td className="px-4 py-3 text-center">
                                                <div className="text-sm font-medium text-slate-800">{dia.total_comensales}</div>
                                                <div className="text-xs text-slate-500">
                                                    <span className="text-red-600">{dia.comensales_social}S</span>
                                                    <span className="text-amber-600">/{dia.comensales_afiliado}A</span>
                                                    <span className="text-blue-600">/{dia.comensales_normal}N</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3 text-right">
                                                <div className="text-sm font-bold text-slate-800">S/ {parseFloat(dia.costo_total).toFixed(2)}</div>
                                                <div className="text-xs text-slate-500">S/ {parseFloat(dia.costo_racion).toFixed(2)}/ración</div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Generador de Lista de Compras */}
                    <div className="bg-white border border-slate-200 rounded-xl p-6 mb-6">
                        <h3 className="font-bold text-lg text-slate-800 mb-4 flex items-center gap-2">
                            <ShoppingBag size={20} className="text-emerald-600" />
                            Lista de Compras
                        </h3>
                        
                        <div className="flex gap-3 mb-4">
                            <button
                                onClick={() => generarListaCompras(null)}
                                disabled={cargandoLista}
                                className={`flex-1 px-4 py-3 rounded-lg font-medium transition-colors ${
                                    tipoLista === 'semanal' && !diaSeleccionado
                                        ? 'bg-emerald-600 text-white'
                                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                }`}
                            >
                                {cargandoLista && tipoLista === 'semanal' ? 'Generando...' : 'Lista Semanal'}
                            </button>
                            {planificacionSel.dias.map((dia) => (
                                <button
                                    key={dia.dia}
                                    onClick={() => generarListaCompras(dia.dia)}
                                    disabled={cargandoLista}
                                    className={`flex-1 px-4 py-3 rounded-lg font-medium transition-colors ${
                                        tipoLista === 'diaria' && diaSeleccionado === dia.dia
                                            ? 'bg-emerald-600 text-white'
                                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                    }`}
                                >
                                    {cargandoLista && diaSeleccionado === dia.dia ? 'Generando...' : `Día ${dia.dia}`}
                                </button>
                            ))}
                        </div>

                        {cargandoLista ? (
                            <div className="flex items-center justify-center h-32">
                                <Loader2 className="animate-spin text-emerald-600" size={32} />
                            </div>
                        ) : listaCompras ? (
                            <div>
                                <div className="flex justify-between items-center mb-4">
                                    <div>
                                        <p className="text-sm text-slate-600">
                                            Tipo: <span className="font-bold">{tipoLista === 'diaria' ? `Diaria (Día ${diaSeleccionado})` : 'Semanal'}</span>
                                        </p>
                                        <p className="text-sm text-slate-600">
                                            Total de ingredientes: <span className="font-bold">{listaCompras.total_ingredientes}</span>
                                        </p>
                                    </div>
                                    <button
                                        onClick={exportarListaCompras}
                                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                                    >
                                        <Download size={18} />
                                        Exportar
                                    </button>
                                </div>

                                <div className="overflow-x-auto">
                                    <table className="w-full">
                                        <thead className="bg-slate-50">
                                            <tr>
                                                <th className="px-4 py-3 text-left text-xs font-medium text-slate-600 uppercase">Ingrediente</th>
                                                <th className="px-4 py-3 text-right text-xs font-medium text-slate-600 uppercase">Cantidad</th>
                                                <th className="px-4 py-3 text-left text-xs font-medium text-slate-600 uppercase">Unidad</th>
                                                <th className="px-4 py-3 text-left text-xs font-medium text-slate-600 uppercase">Días de Uso</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-200">
                                            {listaCompras.lista_compras.map((item, idx) => (
                                                <tr key={idx} className="hover:bg-slate-50">
                                                    <td className="px-4 py-3 font-medium text-slate-800">{item.nombre}</td>
                                                    <td className="px-4 py-3 text-right font-bold text-emerald-600">{item.cantidad}</td>
                                                    <td className="px-4 py-3 text-slate-700">{item.unidad}</td>
                                                    <td className="px-4 py-3 text-sm text-slate-600">{item.dias_uso.join(', ')}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        ) : (
                            <div className="text-center py-8 text-slate-500">
                                <ShoppingBag className="mx-auto mb-2 text-slate-400" size={32} />
                                <p>Selecciona un tipo de lista para generar</p>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Modal de confirmación para eliminar */}
            <ModalConfirmacion
                isOpen={!!modalEliminar}
                onClose={() => setModalEliminar(null)}
                onConfirm={confirmarEliminacion}
                mensaje={`¿Estás seguro de eliminar la Planificación #${modalEliminar?.id}? Esta acción no se puede deshacer.`}
                tipo="danger"
            />
        </div>
    );
};