/**
components/reportes/ReportesMunicipioView.jsx
Objetivo: COM-78: vista macro de la MUNICIPALIDAD / Admin de Sistemas con 3 reportes
      distritales (Dashboard, Observatorio, Cobertura). El drill-down a un comedor
      específico se hace desde la pestaña "Reportes operativos" (COM-77), evitando
      duplicidad de rutas.
Historial:
COM-78 v1: versión original con 4 sub-pestañas (incluía "Focalizar Comedor").
COM-78 v2 (este archivo): se RETIRA la sub-pestaña "Focalizar Comedor" porque
      duplica exactamente la vista "Reportes operativos" del segmento superior.
      El usuario municipal accede al drill-down cambiando de segmento, no dentro
      del mismo. Tooltips re-estilizados con paleta coherente (fondo blanco,
      borde slate, texto multi-línea).
Permisos: el backend exige puede_com78 (municipal con módulo reportes/subsidio o
      Admin de Sistemas); la vista recibe el alcance ya resuelto por ReportesView.
Uso: Montada por ReportesView.jsx en el segmento "Supervisión distrital".
Referencia: ticket COM-78 (solo trazabilidad).
*/
import React, { useState, useCallback } from 'react';
import {
  Loader2, AlertCircle, Building2, LineChart, Users,
  TrendingUp, TrendingDown, AlertTriangle, CheckCircle2, MapPin, Calendar,
  Info
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

const fmtS = (v) => (v === null || v === undefined ? '—' : `S/ ${Number(v).toFixed(2)}`);
const fmtN = (v, d = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

const badgeEstado = (estado) => {
  const map = {
    OK: 'bg-emerald-100 text-emerald-700',
    POR_AGOTAR: 'bg-amber-100 text-amber-700',
    AGOTADO: 'bg-red-100 text-red-700',
    SIN_SUBSIDIO: 'bg-slate-100 text-slate-600',
    EN_RIESGO: 'bg-amber-100 text-amber-700',
    CRITICO: 'bg-red-100 text-red-700',
  };
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${map[estado] || map.SIN_SUBSIDIO}`}>{estado}</span>;
};

// COM-78 v2: Tooltip re-estilizado con paleta coherente (fondo blanco, borde slate,
// texto multi-línea). Reemplaza el anterior bg-slate-800/whitespace-nowrap que
// cortaba el texto y contrastaba mal con el resto de la UI.
const Tooltip = ({ children, content }) => {
  const [show, setShow] = useState(false);
  return (
    <div className="relative inline-block" onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <div className="absolute z-50 bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-white text-slate-700 text-xs rounded-lg shadow-lg border border-slate-200 max-w-[280px] leading-snug">
          {content}
          <div className="absolute top-full left-1/2 transform -translate-x-1/2 border-4 border-transparent border-t-white"></div>
        </div>
      )}
    </div>
  );
};

// Sparkline SVG mínimo para la serie del observatorio
const Sparkline = ({ serie, color = '#059669' }) => {
  if (!serie || serie.length < 2) return <span className="text-[10px] text-slate-400">sin serie</span>;
  const W = 140, H = 36, P = 3;
  const vals = serie.map(s => s.precio);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = (max - min) || 1;
  const pts = serie.map((s, i) => {
    const x = P + (i / (serie.length - 1)) * (W - 2 * P);
    const y = H - P - ((s.precio - min) / span) * (H - 2 * P);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-9">
      <polyline fill="none" stroke={color} strokeWidth="1.6" points={pts} />
    </svg>
  );
};

// COM-78 v2: solo 3 sub-pestañas macro. El drill-down a comedor se hace desde el
// segmento "Reportes operativos" (COM-77), evitando duplicidad de rutas.
const SUBTABS = [
  { clave: 'dashboard', label: 'Dashboard Distrital', icon: Building2 },
  { clave: 'observatorio', label: 'Observatorio de Precios', icon: LineChart },
  { clave: 'cobertura', label: 'Cobertura y Focalización', icon: Users },
];

export const ReportesMunicipioView = ({ alcance }) => {
  const { usuario } = useAuth();
  const ahora = new Date();
  const [sub, setSub] = useState('dashboard');
  const [anio, setAnio] = useState(ahora.getFullYear());
  const [mes, setMes] = useState(ahora.getMonth() + 1);
  const [zonaSel, setZonaSel] = useState('');
  const [diasObs, setDiasObs] = useState(90);
  const [data, setData] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');

  const generar = useCallback(async () => {
    setCargando(true); setError(''); setData(null);
    const base = { usuario_solicitante_id: usuario.id, anio, mes, zona: zonaSel || null };
    try {
      if (sub === 'dashboard') setData(await api.getDashboardDistrital(base));
      else if (sub === 'observatorio') setData(await api.getObservatorioPrecios({ usuario_solicitante_id: usuario.id, dias: diasObs }));
      else if (sub === 'cobertura') setData(await api.getCoberturaFocalizacion(base));
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, [sub, anio, mes, zonaSel, diasObs, usuario.id]);

  return (
    <div className="space-y-4">
      {/* Selectores globales */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Mes</label>
          <select value={mes} onChange={(e) => { setMes(Number(e.target.value)); setData(null); }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500">
            {MESES.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Año</label>
          <input type="number" min="2020" max="2100" value={anio}
            onChange={(e) => { setAnio(Number(e.target.value)); setData(null); }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-emerald-500" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1 flex items-center gap-1">
            <MapPin size={11} /> Zona
          </label>
          <select value={zonaSel} onChange={(e) => { setZonaSel(e.target.value); setData(null); }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500">
            <option value="">Todas las zonas</option>
            {(alcance?.zonas || []).map(z => <option key={z} value={z}>{z}</option>)}
          </select>
        </div>
        {sub === 'observatorio' && (
          <div>
            <label className="text-xs font-semibold text-slate-600 block mb-1">Ventana (días)</label>
            <select value={diasObs} onChange={(e) => { setDiasObs(Number(e.target.value)); setData(null); }}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500">
              <option value={30}>30 días</option>
              <option value={90}>90 días</option>
              <option value={180}>180 días</option>
            </select>
          </div>
        )}
        <div className="col-span-2 md:col-span-1">
          <button onClick={generar} disabled={cargando}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
            {cargando ? <Loader2 className="animate-spin" size={15} /> : <Calendar size={15} />}
            Generar
          </button>
        </div>
      </div>

      {/* Sub-pestañas macro (sin "Focalizar Comedor" — ver COM-78 v2) */}
      <div className="flex flex-wrap gap-1.5">
        {SUBTABS.map(s => {
          const Icon = s.icon;
          return (
            <button key={s.clave} onClick={() => { setSub(s.clave); setData(null); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${sub === s.clave ? 'bg-emerald-600 text-white border-emerald-600' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'}`}>
              <Icon size={13} /> {s.label}
            </button>
          );
        })}
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center gap-2 text-sm">
          <AlertCircle size={16} /> {error}
        </div>
      )}
      {cargando && <div className="p-10 text-center text-emerald-600"><Loader2 className="animate-spin mx-auto" size={26} /></div>}

      {/* ===== 1) DASHBOARD DISTRITAL ===== */}
      {!cargando && data && sub === 'dashboard' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Comedores</p>
              <p className="text-lg font-bold text-slate-800">{data.kpis.n_comedores}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Con menú vigente</p>
              <p className="text-lg font-bold text-emerald-700">{data.kpis.n_con_menu_vigente}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Raciones semana</p>
              <p className="text-lg font-bold text-slate-800">{data.kpis.raciones_semana_total}</p>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
              <p className="text-[11px] text-slate-500 uppercase font-semibold">Margen prom.</p>
              <p className={`text-lg font-bold ${(data.kpis.margen_promedio_pct ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                {fmtN(data.kpis.margen_promedio_pct)}%
              </p>
            </div>
            <div className="bg-white border border-red-200 rounded-xl p-3 text-center">
              <p className="text-[11px] text-red-600 uppercase font-semibold">En riesgo</p>
              <p className="text-lg font-bold text-red-600">{data.kpis.n_en_riesgo}</p>
            </div>
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="bg-slate-100 text-slate-600">
                  <th className="p-2 font-semibold">Comedor</th>
                  <th className="p-2 font-semibold">Zona</th>
                  <th className="p-2 text-center">Menú semana</th>
                  <th className="p-2 text-right">Raciones</th>
                  <th className="p-2 text-right">Margen</th>
                  <th className="p-2 text-center">Subsidio</th>
                  <th className="p-2 text-right">% Nutrición</th>
                  <th className="p-2 text-center">Anemia</th>
                  <th className="p-2 text-center">Riesgo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.comedores.map(c => (
                  <tr key={c.comedor_id} className={`hover:bg-slate-50 ${c.en_riesgo ? 'bg-red-50/40' : ''}`}>
                    <td className="p-2 font-medium text-slate-800">{c.comedor_nombre}</td>
                    <td className="p-2 text-slate-600">{c.zona || '—'}</td>
                    <td className="p-2 text-center">
                      {c.menu_vigente_semana
                        ? <span className="inline-flex items-center gap-1 text-emerald-700 font-bold"><CheckCircle2 size={12} /> {c.dias_planificados}d</span>
                        : <span className="inline-flex items-center gap-1 text-red-600 font-bold"><AlertTriangle size={12} /> NO</span>}
                    </td>
                    <td className="p-2 text-right">{c.raciones_semana}</td>
                    <td className={`p-2 text-right font-bold ${(c.margen_semanal ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>
                      {fmtS(c.margen_semanal)}
                    </td>
                    <td className="p-2 text-center">
                      {badgeEstado(c.estado_subsidio)}
                      {c.subsidio_peor_ingrediente && <span className="block text-[9px] text-slate-500">{c.subsidio_peor_ingrediente}</span>}
                    </td>
                    <td className="p-2 text-right">{fmtN(c.pct_cumplimiento_nutricional, 0)}%</td>
                    <td className="p-2 text-center">{c.cumple_cuota_anemia ? '✅' : '⚠️'}</td>
                    <td className="p-2 text-center">{c.en_riesgo ? '🚨' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-400">
            Objetivo de margen semanal: {fmtN(data.margen_objetivo_pct)}% · Período subsidio/nutrición: {MESES[data.mes - 1]} {data.anio}
          </p>
          {/* COM-78 v2: ayuda contextual para acceder al drill-down */}
          <p className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-2 flex items-center gap-2">
            <Info size={12} className="text-slate-400 shrink-0" />
            Para ver los 5 reportes operativos de un comedor específico, cambie al segmento <b>"Reportes operativos"</b> en la pestaña superior.
          </p>
        </div>
      )}

      {/* ===== 2) OBSERVATORIO DE PRECIOS ===== */}
      {!cargando && data && sub === 'observatorio' && (
        <div className="space-y-4">
          {data.alertas.length > 0 && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              <p className="font-bold flex items-center gap-1 mb-1"><AlertTriangle size={15} /> Alertas tempranas de volatilidad (&gt;{data.umbral_alerta_pct}% en 7d)</p>
              <ul className="list-disc ml-5 text-xs space-y-0.5">
                {data.alertas.map((a, i) => (
                  <li key={i}><b>{a.insumo}</b>: variación 7d {fmtN(a.var_7d_pct)}%</li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-[11px] text-slate-500">
            Fuente: {data.mercados} mercado(s) · última corrida {data.ultima_corrida} · ventana {data.ventana_dias} días
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.canasta.map((it, i) => (
              <div key={i} className={`bg-white border rounded-xl p-3 ${it.alerta ? 'border-red-300 ring-1 ring-red-200' : 'border-slate-200'}`}>
                <div className="flex items-center justify-between mb-1">
                  <p className="text-sm font-bold text-slate-800 capitalize">{it.token}</p>
                  {it.alerta ? badgeEstado('CRITICO') : <span className="text-[10px] text-slate-400">{it.insumo_representativo}</span>}
                </div>
                {it.serie ? (
                  <>
                    <Sparkline serie={it.serie} color={it.alerta ? '#dc2626' : '#059669'} />
                    <div className="grid grid-cols-4 gap-1 text-center mt-1">
                      <div><p className="text-[10px] text-slate-400">Actual</p><p className="text-xs font-bold text-slate-700">{fmtS(it.precio_actual)}</p></div>
                      <div><p className="text-[10px] text-slate-400">Var 7d</p>
                        <p className={`text-xs font-bold flex items-center justify-center gap-0.5 ${(it.var_7d_pct ?? 0) > 0 ? 'text-red-600' : 'text-emerald-700'}`}>
                          {(it.var_7d_pct ?? 0) > 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}{fmtN(it.var_7d_pct)}%
                        </p></div>
                      <div><p className="text-[10px] text-slate-400">Var 30d</p><p className="text-xs font-bold text-slate-700">{fmtN(it.var_30d_pct)}%</p></div>
                      <div><p className="text-[10px] text-slate-400">Volatilidad</p><p className="text-xs font-bold text-slate-700">{fmtN(it.volatilidad_30d_pct)}%</p></div>
                    </div>
                  </>
                ) : (
                  <p className="text-[11px] text-slate-400">{it.detalle || 'Sin serie disponible'}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ===== 3) COBERTURA Y FOCALIZACIÓN ===== */}
      {!cargando && data && sub === 'cobertura' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tooltip content="% de raciones Social (gratuitas) sobre el total de raciones realmente vendidas según el POS">
              <div className="bg-white border border-slate-200 rounded-xl p-3 text-center cursor-help">
                <p className="text-[11px] text-slate-500 uppercase font-semibold flex items-center justify-center gap-1">% gratuito real (POS) <Info size={10} /></p>
                <p className="text-lg font-bold text-red-600">{fmtN(data.pcts.pct_gratuito_real)}%</p>
              </div>
            </Tooltip>
            <Tooltip content="% de raciones Social (gratuitas) sobre el total de raciones proyectadas por los planes vigentes">
              <div className="bg-white border border-slate-200 rounded-xl p-3 text-center cursor-help">
                <p className="text-[11px] text-slate-500 uppercase font-semibold flex items-center justify-center gap-1">% gratuito proyectado <Info size={10} /></p>
                <p className="text-lg font-bold text-amber-600">{fmtN(data.pcts.pct_gratuito_proyectado)}%</p>
              </div>
            </Tooltip>
            <Tooltip content="% de comensales registrados como Social en el padrón sobre el total de fichas declaradas">
              <div className="bg-white border border-slate-200 rounded-xl p-3 text-center cursor-help">
                <p className="text-[11px] text-slate-500 uppercase font-semibold flex items-center justify-center gap-1">% gratuito padrón <Info size={10} /></p>
                <p className="text-lg font-bold text-slate-700">{fmtN(data.pcts.pct_gratuito_declarado)}%</p>
              </div>
            </Tooltip>
            <Tooltip content="Diferencia entre % gratuito real y % gratuito declarado. Positivo = más focalizado de lo declarado; Negativo = menos focalizado">
              <div className="bg-white border border-slate-200 rounded-xl p-3 text-center cursor-help">
                <p className="text-[11px] text-slate-500 uppercase font-semibold flex items-center justify-center gap-1">Brecha focalización <Info size={10} /></p>
                <p className={`text-lg font-bold ${(data.brecha_focalizacion_pp ?? 0) >= 0 ? 'text-emerald-700' : 'text-amber-600'}`}>
                  {fmtN(data.brecha_focalizacion_pp)} pp
                </p>
              </div>
            </Tooltip>
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead><tr className="bg-slate-100 text-slate-600">
                <th className="p-2 font-semibold">Origen</th><th className="p-2 text-right">Social</th>
                <th className="p-2 text-right">Afiliado</th><th className="p-2 text-right">Normal</th>
                <th className="p-2 text-right">Cocinera</th><th className="p-2 text-right">Total</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                <tr><td className="p-2 font-medium">Real POS</td>
                  <td className="p-2 text-right">{data.reales_pos.Social || 0}</td>
                  <td className="p-2 text-right">{data.reales_pos.Afiliado || 0}</td>
                  <td className="p-2 text-right">{data.reales_pos.Normal || 0}</td>
                  <td className="p-2 text-right">{data.reales_pos.Cocinera || 0}</td>
                  <td className="p-2 text-right font-bold">{data.totales.real}</td></tr>
                <tr><td className="p-2 font-medium">Proyectado (planes)</td>
                  <td className="p-2 text-right">{data.proyectadas.Social}</td>
                  <td className="p-2 text-right">{data.proyectadas.Afiliado}</td>
                  <td className="p-2 text-right">{data.proyectadas.Normal}</td>
                  <td className="p-2 text-right">{data.proyectadas.Cocinera}</td>
                  <td className="p-2 text-right font-bold">{data.totales.proyectado}</td></tr>
                <tr><td className="p-2 font-medium">Padrón declarado (fichas)</td>
                  <td className="p-2 text-right">{data.declaradas_padron.Social || 0}</td>
                  <td className="p-2 text-right">{data.declaradas_padron.Afiliado || 0}</td>
                  <td className="p-2 text-right">{data.declaradas_padron.Normal || 0}</td>
                  <td className="p-2 text-right">{data.declaradas_padron.Cocinera || 0}</td>
                  <td className="p-2 text-right font-bold">{data.totales.declarado}</td></tr>
              </tbody>
            </table>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <p className="text-sm font-bold text-slate-700 mb-2">Tendencia últimos 6 meses (real POS)</p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead><tr className="bg-slate-100 text-slate-600">
                  <th className="p-2 font-semibold">Mes</th><th className="p-2 text-right">Total</th>
                  <th className="p-2 text-right">% gratuito</th>
                </tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.tendencia_mensual.map((t, i) => (
                    <tr key={i}><td className="p-2">{MESES[t.mes - 1]} {t.anio}</td>
                      <td className="p-2 text-right">{t.total}</td>
                      <td className="p-2 text-right font-bold">{fmtN(t.pct_gratuito)}%</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="text-[11px] text-slate-400">{data.nota_padron}</p>
        </div>
      )}

      {!cargando && !data && !error && (
        <div className="p-10 text-center bg-slate-50 border border-slate-200 rounded-xl">
          <Building2 size={28} className="text-emerald-600 mx-auto mb-2" />
          <p className="text-sm text-slate-500">Configure el período y pulse "Generar".</p>
        </div>
      )}
    </div>
  );
};