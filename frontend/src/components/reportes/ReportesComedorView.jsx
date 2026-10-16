/**
components/reportes/ReportesComedorView.jsx
Objetivo: COM-77: vista de los 5 REPORTES OPERATIVOS del comedor (Directiva/Tesorero/
      Operativo) y del drill-down municipal (solo lectura):
        A) Estado de Resultados y Margen Real (semanal/mensual).
        B) Tablero de Consumo de Subsidio con fecha estimada de quiebre.
        C) Inteligencia de Compras (ahorro por IA/scraper vs promedio histórico).
        D) Merma y Precisión de Demanda (proyectado IA vs atendido POS).
        E) Semáforo Nutricional y Anemia Cero (metas parametrizables).
Historial:
COM-77 (este archivo): versión original.
COM-78 v2: Tooltip re-estilizado con paleta coherente (fondo blanco, borde slate,
      texto multi-línea). Reemplaza el anterior bg-slate-800/whitespace-nowrap que
      cortaba el texto y contrastaba mal con el resto de la UI.
Permisos: el backend valida el alcance (403); la vista recibe `alcance` ya resuelto.
Uso: Montada por ReportesView.jsx en el segmento "Reportes operativos".
Referencia: ticket COM-77 (solo trazabilidad).
*/
import React, { useState, useCallback } from 'react';
import {
  Loader2, AlertCircle, Wallet, Gift, Lightbulb, Scale, Heart,
  Calendar, RefreshCw, FileDown, Info
} from 'lucide-react';
import { api } from '../../services/api';
import { useAuth } from '../../context/AuthContext';

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

const fmtS = (v) => (v === null || v === undefined ? '—' : `S/ ${Number(v).toFixed(2)}`);
const fmtN = (v, d = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

const badgeSemaforo = (estado) => {
  const map = {
    OK: 'bg-emerald-100 text-emerald-700',
    POR_AGOTAR: 'bg-amber-100 text-amber-700',
    AGOTADO: 'bg-red-100 text-red-700',
    SIN_CONSUMO: 'bg-slate-100 text-slate-600',
    SIN_REGISTRO_POS: 'bg-slate-100 text-slate-600',
    EN_RIESGO: 'bg-amber-100 text-amber-700',
    CRITICO: 'bg-red-100 text-red-700',
    SIN_DATOS: 'bg-slate-100 text-slate-600',
  };
  return <span className={`px-2 py-0.5 rounded-full text-[10px] font-black ${map[estado] || map.SIN_DATOS}`}>{estado}</span>;
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

const Tarjeta = ({ label, valor, sub, tono = 'text-slate-800' }) => (
  <div className="bg-white border border-slate-200 rounded-xl p-3 text-center">
    <p className="text-[11px] text-slate-500 uppercase font-semibold">{label}</p>
    <p className={`text-lg font-bold ${tono}`}>{valor}</p>
    {sub && <p className="text-[10px] text-slate-400">{sub}</p>}
  </div>
);

const SUBREPORTES = [
  { clave: 'estado', label: 'Estado de Resultados', icon: Wallet },
  { clave: 'subsidio', label: 'Consumo de Subsidio', icon: Gift },
  { clave: 'compras', label: 'Inteligencia de Compras', icon: Lightbulb },
  { clave: 'merma', label: 'Merma y Demanda', icon: Scale },
  { clave: 'nutricional', label: 'Semáforo Nutricional', icon: Heart },
];

export const ReportesComedorView = ({ alcance, comedorForzado = null }) => {
  const { usuario } = useAuth();
  const ahora = new Date();
  const [comedorId, setComedorId] = useState(comedorForzado || alcance?.comedor_fijo || alcance?.comedores?.[0]?.id || '');
  const [anio, setAnio] = useState(ahora.getFullYear());
  const [mes, setMes] = useState(ahora.getMonth() + 1);
  const [sub, setSub] = useState('estado');
  const [data, setData] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');

  React.useEffect(() => { if (comedorForzado) setComedorId(comedorForzado); }, [comedorForzado]);

  const generar = useCallback(async () => {
    if (!comedorId) { setError('Seleccione un comedor.'); return; }
    setCargando(true); setError(''); setData(null);
    const params = { usuario_solicitante_id: usuario.id, comedor_id: Number(comedorId), anio, mes };
    try {
      const fn = {
        estado: api.getReporteEstadoResultados,
        subsidio: api.getReporteConsumoSubsidio,
        compras: api.getReporteInteligenciaCompras,
        merma: api.getReporteMermaDemanda,
        nutricional: api.getReporteSemaforoNutricional,
      }[sub];
      setData(await fn(params));
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, [comedorId, anio, mes, sub, usuario.id]);

  // Exportar a PDF
  const exportarPDF = () => {
    if (!data) return;
    const ventana = window.open('', '_blank', 'width=900,height=700');
    if (!ventana) {
      setError('El navegador bloqueó la ventana de impresión. Permita popups.');
      return;
    }

    let contenido = '';
    const titulo = SUBREPORTES.find(s => s.clave === sub)?.label || 'Reporte';
    const comedorNombre = alcance?.comedores?.find(c => c.id == comedorId)?.nombre || 'Comedor';

    if (sub === 'estado' && data) {
      contenido = `
        <h2>Estado de Resultados y Margen Real</h2>
        <p><strong>Comedor:</strong> ${comedorNombre}</p>
        <p><strong>Período:</strong> ${MESES[mes - 1]} ${anio}</p>
        <p><strong>Generado:</strong> ${new Date().toLocaleDateString('es-PE')}</p>

        <h3>Totales del Mes</h3>
        <table>
          <tr><th>Concepto</th><th>Valor</th></tr>
          <tr><td>Ingreso real (tarifa)</td><td>${fmtS(data.totales.ingreso_real_tarifa)}</td></tr>
          <tr><td>Ingreso real (caja)</td><td>${fmtS(data.totales.ingreso_real_caja)}</td></tr>
          <tr><td>Ingreso proyectado</td><td>${fmtS(data.totales.ingreso_proyectado)}</td></tr>
          <tr><td>Costo ejecutado</td><td>${fmtS(data.totales.costo_ejecutado)}</td></tr>
          <tr><td>Costo proyectado</td><td>${fmtS(data.totales.costo_proyectado)}</td></tr>
          <tr><td>Valor subsidio consumido</td><td>${fmtS(data.totales.valor_subsidio_consumido)}</td></tr>
          <tr><td>Costo sin subsidio</td><td>${fmtS(data.totales.costo_sin_subsidio)}</td></tr>
          <tr><td>Margen ejecutado</td><td>${fmtS(data.totales.margen_ejecutado)}</td></tr>
          <tr><td>Margen proyectado</td><td>${fmtS(data.totales.margen_proyectado)}</td></tr>
          <tr><td>Margen % ejecutado</td><td>${fmtN(data.totales.margen_pct_ejecutado)}%</td></tr>
          <tr><td>Margen objetivo %</td><td>${fmtN(data.totales.margen_objetivo_pct)}%</td></tr>
          <tr><td>¿Cumple objetivo?</td><td>${data.totales.cumple_objetivo ? 'SÍ' : 'NO'}</td></tr>
        </table>

        <h3>Desglose Semanal</h3>
        <table>
          <tr><th>Semana</th><th>Estado</th><th>Ingreso proy.</th><th>Ingreso real</th><th>Costo</th><th>Margen ejec.</th><th>Margen %</th><th>Objetivo</th></tr>
          ${data.semanas.map(s => `
            <tr>
              <td>${s.semana}</td>
              <td>${s.estado}</td>
              <td>${fmtS(s.ingreso_proyectado)}</td>
              <td>${fmtS(s.ingreso_real_tarifa)}</td>
              <td>${fmtS(s.costo_ejecutado)}</td>
              <td>${fmtS(s.margen_ejecutado)}</td>
              <td>${fmtN(s.margen_pct_ejecutado)}%</td>
              <td>${s.cumple_objetivo ? '✅' : '⚠️'}</td>
            </tr>
          `).join('')}
        </table>
      `;
    } else if (sub === 'subsidio' && data) {
      contenido = `
        <h2>Tablero de Consumo de Subsidio</h2>
        <p><strong>Comedor:</strong> ${comedorNombre}</p>
        <p><strong>Período:</strong> ${MESES[mes - 1]} ${anio}</p>

        <h3>Resumen</h3>
        <table>
          <tr><th>Concepto</th><th>Valor</th></tr>
          <tr><td>Ingredientes con subsidio</td><td>${data.totales.ingredientes_con_subsidio}</td></tr>
          <tr><td>OK</td><td>${data.totales.ok}</td></tr>
          <tr><td>Por agotar</td><td>${data.totales.por_agotar}</td></tr>
          <tr><td>Agotados</td><td>${data.totales.agotados}</td></tr>
          <tr><td>Sin consumo</td><td>${data.totales.sin_consumo}</td></tr>
        </table>

        <h3>Detalle por Ingrediente</h3>
        <table>
          <tr><th>Ingrediente</th><th>Stock</th><th>Consumo real</th><th>Comprometido</th><th>Restante</th><th>% uso</th><th>Consumo/día</th><th>Quiebre est.</th><th>Estado</th></tr>
          ${data.lineas.map(l => `
            <tr>
              <td>${l.ingrediente}</td>
              <td>${fmtN(l.gramos_stock / 1000, 2)} kg/L</td>
              <td>${fmtN(l.gramos_consumo_real / 1000, 2)}</td>
              <td>${fmtN(l.gramos_comprometido_futuro / 1000, 2)}</td>
              <td>${fmtN(l.gramos_restante / 1000, 2)}</td>
              <td>${fmtN(l.pct_uso)}%</td>
              <td>${fmtN(l.consumo_diario_planificado / 1000, 2)}</td>
              <td>${l.fecha_estimada_quiebre || '—'}</td>
              <td>${l.estado}</td>
            </tr>
          `).join('')}
        </table>
      `;
    } else if (sub === 'compras' && data) {
      contenido = `
        <h2>Inteligencia de Compras</h2>
        <p><strong>Comedor:</strong> ${comedorNombre}</p>
        <p><strong>Período:</strong> ${MESES[mes - 1]} ${anio}</p>

        <h3>Totales</h3>
        <table>
          <tr><th>Concepto</th><th>Valor</th></tr>
          <tr><td>Ahorro por IA/Scraper</td><td>${fmtS(data.totales.ahorro_ia)}</td></tr>
          <tr><td>Costo a precio usado</td><td>${fmtS(data.totales.costo_usado)}</td></tr>
          <tr><td>Costo a promedio mes</td><td>${fmtS(data.totales.costo_a_promedio_mes)}</td></tr>
          <tr><td>Diferencia</td><td>${fmtS(data.totales.diferencia_usado_vs_prommes)}</td></tr>
        </table>

        <h3>Detalle por Planificación</h3>
        <table>
          <tr><th>Semana</th><th>Fecha compra</th><th>Costo usado</th><th>Ahorro IA</th><th>Fuentes</th><th>Top ahorros</th></tr>
          ${data.planes.map(p => `
            <tr>
              <td>${p.semana}</td>
              <td>${p.fecha_compra}</td>
              <td>${fmtS(p.costo_usado)}</td>
              <td>${fmtS(p.ahorro_ia)}</td>
              <td>${Object.entries(p.items_por_fuente).map(([f, n]) => `${f}(${n})`).join(' · ')}</td>
              <td>${p.top_ahorros.map(t => `${t.insumo}: ${fmtS(t.ahorro)}`).join(' · ') || '—'}</td>
            </tr>
          `).join('')}
        </table>
      `;
    } else if (sub === 'merma' && data) {
      contenido = `
        <h2>Merma y Precisión de Demanda</h2>
        <p><strong>Comedor:</strong> ${comedorNombre}</p>
        <p><strong>Período:</strong> ${MESES[mes - 1]} ${anio}</p>

        <h3>Totales</h3>
        <table>
          <tr><th>Concepto</th><th>Valor</th></tr>
          <tr><td>Días planificados</td><td>${data.totales.dias_planificados}</td></tr>
          <tr><td>Días con registro POS</td><td>${data.totales.dias_con_registro_pos}</td></tr>
          <tr><td>Días sin registro POS</td><td>${data.totales.dias_sin_registro_pos}</td></tr>
          <tr><td>Raciones proyectadas</td><td>${data.totales.raciones_proyectadas}</td></tr>
          <tr><td>Raciones reales</td><td>${data.totales.raciones_reales}</td></tr>
          <tr><td>Merma total</td><td>${data.totales.merma_total}</td></tr>
          <tr><td>Precisión promedio %</td><td>${fmtN(data.totales.precision_promedio_pct)}%</td></tr>
          <tr><td>Sesgo acumulado</td><td>${data.totales.sesgo_acumulado}</td></tr>
          <tr><td>Interpretación sesgo</td><td>${data.totales.interpretacion_sesgo}</td></tr>
          <tr><td>Días con predicción IA</td><td>${data.totales.dias_con_prediccion_ia}</td></tr>
        </table>

        <h3>Detalle por Día</h3>
        <table>
          <tr><th>Fecha</th><th>Día</th><th>Proyectado</th><th>Atendido</th><th>Merma</th><th>Precisión</th><th>Fuente</th><th>Estado</th></tr>
          ${data.dias.map(d => `
            <tr>
              <td>${d.fecha}</td>
              <td>${d.dia_nombre}</td>
              <td>${d.proyectado}</td>
              <td>${d.atendido_real ?? '—'}</td>
              <td>${d.merma ?? '—'}</td>
              <td>${d.precision != null ? `${d.precision}%` : '—'}</td>
              <td>${d.fuente === 'prediccion_ia' ? 'IA' : 'Parámetro'}</td>
              <td>${d.estado}</td>
            </tr>
          `).join('')}
        </table>
      `;
    } else if (sub === 'nutricional' && data) {
      contenido = `
        <h2>Semáforo Nutricional y Anemia Cero</h2>
        <p><strong>Comedor:</strong> ${comedorNombre}</p>
        <p><strong>Período:</strong> ${MESES[mes - 1]} ${anio}</p>

        <h3>Indicadores Nutricionales</h3>
        <table>
          <tr><th>Nutriente</th><th>Valor</th><th>Meta</th><th>Semáforo</th></tr>
          ${data.nutrientes.map(n => `
            <tr>
              <td>${n.nutriente}</td>
              <td>${fmtN(n.valor, 2)}</td>
              <td>${fmtN(n.meta, 1)}</td>
              <td>${n.semaforo}</td>
            </tr>
          `).join('')}
        </table>

        <h3>Anemia Cero</h3>
        <table>
          <tr><th>Concepto</th><th>Valor</th></tr>
          <tr><td>Días con receta Anti-Anemia</td><td>${data.anemia_cero.dias_con_receta_anti_anemia}</td></tr>
          <tr><td>% días Anti-Anemia</td><td>${fmtN(data.anemia_cero.pct_dias_anti_anemia)}%</td></tr>
          <tr><td>Cuota mensual esperada</td><td>${data.anemia_cero.cuota_mensual_esperada}</td></tr>
          <tr><td>¿Cumple cuota?</td><td>${data.anemia_cero.cumple_cuota ? 'SÍ' : 'NO'}</td></tr>
          <tr><td>Semáforo</td><td>${data.anemia_cero.semaforo}</td></tr>
        </table>

        <h3>Detalle por Día</h3>
        <table>
          <tr><th>Fecha</th><th>Receta</th><th>Fe (mg)</th><th>Prot (g)</th><th>Kcal</th><th>Anti-Anemia</th></tr>
          ${data.dias.map(d => `
            <tr>
              <td>${d.fecha}</td>
              <td>${d.receta}</td>
              <td>${fmtN(d.hierro_mg_racion, 2)}</td>
              <td>${fmtN(d.proteina_g_racion, 2)}</td>
              <td>${fmtN(d.energia_kcal_racion, 0)}</td>
              <td>${d.es_anti_anemia ? '🩸' : '—'}</td>
            </tr>
          `).join('')}
        </table>
      `;
    }

    ventana.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="UTF-8">
        <title>${titulo} - NutriComedor OSB</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 20px; color: #1e293b; }
          h1 { color: #059669; border-bottom: 2px solid #059669; padding-bottom: 8px; font-size: 20px; }
          h2 { font-size: 16px; color: #475569; margin-top: 24px; }
          h3 { font-size: 14px; color: #1e293b; margin-top: 16px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; }
          th { background: #f1f5f9; padding: 8px; text-align: left; border: 1px solid #cbd5e1; font-size: 11px; text-transform: uppercase; }
          td { padding: 7px 8px; border: 1px solid #e2e8f0; font-size: 12px; }
          tr:nth-child(even) { background: #f8fafc; }
          .footer { margin-top: 40px; font-size: 11px; color: #64748b; text-align: center; border-top: 1px solid #cbd5e1; padding-top: 12px; }
          @media print { body { margin: 10mm; } .no-print { display: none; } }
        </style>
      </head>
      <body>
        <h1>${titulo}</h1>
        ${contenido}
        <div class="footer">
          NutriComedor OSB · Reporte generado automáticamente
        </div>
        <div class="no-print" style="margin-top: 20px; text-align: center;">
          <button onclick="window.print()" style="padding: 10px 24px; background: #059669; color: white; border: none; border-radius: 6px; font-size: 14px; cursor: pointer;">
            🖨️ Imprimir / Guardar como PDF
          </button>
        </div>
      </body>
      </html>
    `);
    ventana.document.close();
  };

  return (
    <div className="space-y-4">
      {/* Selectores */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Comedor</label>
          <select value={comedorId} disabled={!!comedorForzado}
            onChange={(e) => { setComedorId(e.target.value); setData(null); }}
            className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white outline-none focus:ring-2 focus:ring-emerald-500 disabled:bg-slate-50">
            {(alcance?.comedores || []).map(c => <option key={c.id} value={c.id}>{c.nombre}{c.zona ? ` · ${c.zona}` : ''}</option>)}
          </select>
        </div>
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
        <div className="md:col-span-2 flex items-end gap-2">
          <button onClick={generar} disabled={cargando}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50">
            {cargando ? <Loader2 className="animate-spin" size={15} /> : <Calendar size={15} />}
            Generar reporte
          </button>
          {data && (
            <button onClick={exportarPDF}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors">
              <FileDown size={15} /> PDF
            </button>
          )}
        </div>
      </div>

      {/* Sub-reportes */}
      <div className="flex flex-wrap gap-1.5">
        {SUBREPORTES.map(s => {
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

      {!cargando && data && sub === 'estado' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tarjeta label="Ingreso real (tarifa)" valor={fmtS(data.totales.ingreso_real_tarifa)} sub={`caja: ${fmtS(data.totales.ingreso_real_caja)}`} />
            <Tarjeta label="Ingreso proyectado" valor={fmtS(data.totales.ingreso_proyectado)} />
            <Tarjeta label="Costo ejecutado" valor={fmtS(data.totales.costo_ejecutado)} sub={`sin subsidio: ${fmtS(data.totales.costo_sin_subsidio)}`} />
            <Tarjeta label="Subsidio consumido" valor={fmtS(data.totales.valor_subsidio_consumido)} tono="text-red-600" />
            <Tarjeta label="Margen ejecutado" valor={fmtS(data.totales.margen_ejecutado)} tono={data.totales.margen_ejecutado >= 0 ? 'text-emerald-700' : 'text-red-600'} sub={`${fmtN(data.totales.margen_pct_ejecutado)}%`} />
            <Tarjeta label="Margen proyectado" valor={fmtS(data.totales.margen_proyectado)} />
            <Tarjeta label="Objetivo semanal" valor={`${fmtN(data.totales.margen_objetivo_pct)}%`} />
            <Tarjeta label="¿Cumple objetivo?" valor={data.totales.cumple_objetivo ? 'SÍ' : 'NO'} tono={data.totales.cumple_objetivo ? 'text-emerald-700' : 'text-red-600'} />
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead><tr className="bg-slate-100 text-slate-600">
                <th className="p-2">Semana</th><th className="p-2">Estado</th>
                <th className="p-2 text-right">Ingreso proy.</th><th className="p-2 text-right">Ingreso real</th>
                <th className="p-2 text-right">Costo</th><th className="p-2 text-right">Margen ejec.</th>
                <th className="p-2 text-right">Margen %</th><th className="p-2 text-center">Objetivo</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.semanas.map(s => (
                  <tr key={s.plan_id} className="hover:bg-slate-50">
                    <td className="p-2 font-medium">{s.semana}</td>
                    <td className="p-2">{s.estado}</td>
                    <td className="p-2 text-right">{fmtS(s.ingreso_proyectado)}</td>
                    <td className="p-2 text-right">{fmtS(s.ingreso_real_tarifa)}</td>
                    <td className="p-2 text-right">{fmtS(s.costo_ejecutado)}</td>
                    <td className={`p-2 text-right font-bold ${s.margen_ejecutado >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmtS(s.margen_ejecutado)}</td>
                    <td className="p-2 text-right">{fmtN(s.margen_pct_ejecutado)}%</td>
                    <td className="p-2 text-center">{s.cumple_objetivo ? '✅' : '⚠️'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-400">{data.nota_padron}</p>
        </div>
      )}

      {!cargando && data && sub === 'subsidio' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tarjeta label="Con subsidio" valor={data.totales.ingredientes_con_subsidio} />
            <Tarjeta label="OK" valor={data.totales.ok} tono="text-emerald-700" />
            <Tarjeta label="Por agotar" valor={data.totales.por_agotar} tono="text-amber-600" />
            <Tarjeta label="Agotados" valor={data.totales.agotados} tono="text-red-600" />
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead><tr className="bg-slate-100 text-slate-600">
                <th className="p-2">Ingrediente</th><th className="p-2 text-right">Stock</th>
                <th className="p-2 text-right">Consumo real</th><th className="p-2 text-right">Comprometido</th>
                <th className="p-2 text-right">Restante</th><th className="p-2 text-right">% uso</th>
                <th className="p-2 text-right">Consumo/día</th><th className="p-2">Quiebre est.</th>
                <th className="p-2 text-center">Estado</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.lineas.map(l => (
                  <tr key={l.ingrediente_id} className="hover:bg-slate-50">
                    <td className="p-2 font-medium">{l.ingrediente}</td>
                    <td className="p-2 text-right">{fmtN(l.gramos_stock / 1000, 2)} kg/L</td>
                    <td className="p-2 text-right">{fmtN(l.gramos_consumo_real / 1000, 2)}</td>
                    <td className="p-2 text-right">{fmtN(l.gramos_comprometido_futuro / 1000, 2)}</td>
                    <td className={`p-2 text-right font-bold ${l.gramos_restante < 0 ? 'text-red-600' : 'text-slate-700'}`}>{fmtN(l.gramos_restante / 1000, 2)}</td>
                    <td className="p-2 text-right">{fmtN(l.pct_uso)}%</td>
                    <td className="p-2 text-right">{fmtN(l.consumo_diario_planificado / 1000, 2)}</td>
                    <td className="p-2">{l.fecha_estimada_quiebre || '—'}</td>
                    <td className="p-2 text-center">{badgeSemaforo(l.estado)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!cargando && data && sub === 'compras' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tarjeta label="Ahorro por IA/Scraper" valor={fmtS(data.totales.ahorro_ia)} tono="text-emerald-700" />
            <Tarjeta label="Costo a precio usado" valor={fmtS(data.totales.costo_usado)} />
            <Tarjeta label="Costo a promedio mes" valor={fmtS(data.totales.costo_a_promedio_mes)} />
            <Tarjeta label="Diferencia" valor={fmtS(data.totales.diferencia_usado_vs_prommes)} tono={data.totales.diferencia_usado_vs_prommes <= 0 ? 'text-emerald-700' : 'text-amber-600'} />
          </div>
          <p className="text-[11px] text-slate-500">{data.criterio}</p>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead><tr className="bg-slate-100 text-slate-600">
                <th className="p-2">Semana</th><th className="p-2">Fecha compra</th>
                <th className="p-2 text-right">Costo usado</th><th className="p-2 text-right">Ahorro IA</th>
                <th className="p-2">Fuentes</th><th className="p-2">Top ahorros</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.planes.map(p => (
                  <tr key={p.plan_id} className="hover:bg-slate-50">
                    <td className="p-2 font-medium">{p.semana}</td>
                    <td className="p-2">{p.fecha_compra}</td>
                    <td className="p-2 text-right">{fmtS(p.costo_usado)}</td>
                    <td className={`p-2 text-right font-bold ${(p.ahorro_ia || 0) >= 0 ? 'text-emerald-700' : 'text-red-600'}`}>{fmtS(p.ahorro_ia)}</td>
                    <td className="p-2">{Object.entries(p.items_por_fuente).map(([f, n]) => `${f}(${n})`).join(' · ')}</td>
                    <td className="p-2 text-[10px] text-slate-500">{p.top_ahorros.map(t => `${t.insumo}: ${fmtS(t.ahorro)}`).join(' · ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!cargando && data && sub === 'merma' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Tarjeta label="Raciones proyectadas" valor={data.totales.raciones_proyectadas} />
            <Tarjeta label="Raciones reales" valor={data.totales.raciones_reales} />
            <Tarjeta label="Merma total" valor={data.totales.merma_total} tono={data.totales.merma_total > 0 ? 'text-amber-600' : 'text-emerald-700'} />
            <Tarjeta label="Precisión promedio" valor={`${fmtN(data.totales.precision_promedio_pct)}%`} tono="text-emerald-700" />
            <Tarjeta label="Sesgo acumulado" valor={data.totales.sesgo_acumulado} sub={data.totales.interpretacion_sesgo} />
            <Tarjeta label="Días con IA" valor={data.totales.dias_con_prediccion_ia} />
            <Tarjeta label="Días sin POS" valor={data.totales.dias_sin_registro_pos} tono="text-amber-600" />
            <Tarjeta label="Días planificados" valor={data.totales.dias_planificados} />
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead><tr className="bg-slate-100 text-slate-600">
                <th className="p-2">Fecha</th><th className="p-2">Día</th>
                <th className="p-2 text-right">Proyectado</th><th className="p-2 text-right">Atendido</th>
                <th className="p-2 text-right">Merma</th><th className="p-2 text-right">Precisión</th>
                <th className="p-2">Fuente</th><th className="p-2 text-center">Estado</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.dias.map((d, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="p-2 font-medium">{d.fecha}</td>
                    <td className="p-2">{d.dia_nombre}</td>
                    <td className="p-2 text-right">{d.proyectado}</td>
                    <td className="p-2 text-right">{d.atendido_real ?? '—'}</td>
                    <td className={`p-2 text-right font-bold ${(d.merma || 0) > 0 ? 'text-amber-600' : 'text-emerald-700'}`}>{d.merma ?? '—'}</td>
                    <td className="p-2 text-right">{d.precision != null ? `${d.precision}%` : '—'}</td>
                    <td className="p-2">{d.fuente === 'prediccion_ia' ? 'IA' : 'Parámetro'}</td>
                    <td className="p-2 text-center">{badgeSemaforo(d.estado)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-slate-400">{data.nota_padron}</p>
        </div>
      )}

      {!cargando && data && sub === 'nutricional' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {data.nutrientes.map(n => (
              <Tooltip key={n.nutriente} content={`Promedio mensual de ${n.nutriente.split(' ')[0]} por ración vs meta de ${fmtN(n.meta, 1)}`}>
                <div className="bg-white border border-slate-200 rounded-xl p-3 text-center cursor-help">
                  <p className="text-[11px] text-slate-500 uppercase font-semibold flex items-center justify-center gap-1">{n.nutriente} <Info size={10} /></p>
                  <p className="text-lg font-bold text-slate-800">{fmtN(n.valor, 2)} / meta {fmtN(n.meta, 1)}</p>
                  <div className="mt-1">{badgeSemaforo(n.semaforo)}</div>
                </div>
              </Tooltip>
            ))}
            <Tooltip content={`Días con receta del cluster Anti-Anemia Premium vs cuota mensual esperada de ${data.anemia_cero.cuota_mensual_esperada} días`}>
              <div className="bg-white border border-slate-200 rounded-xl p-3 text-center cursor-help">
                <p className="text-[11px] text-slate-500 uppercase font-semibold flex items-center justify-center gap-1">Días Anti-Anemia <Info size={10} /></p>
                <p className="text-lg font-bold text-red-700">{data.anemia_cero.dias_con_receta_anti_anemia} ({fmtN(data.anemia_cero.pct_dias_anti_anemia)}%)</p>
                <p className="text-[10px] text-slate-400">cuota mensual: {data.anemia_cero.cuota_mensual_esperada}</p>
                <div className="mt-1">{badgeSemaforo(data.anemia_cero.semaforo)}</div>
              </div>
            </Tooltip>
          </div>
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-xs">
              <thead><tr className="bg-slate-100 text-slate-600">
                <th className="p-2">Fecha</th><th className="p-2">Receta</th>
                <th className="p-2 text-right">Fe (mg)</th><th className="p-2 text-right">Prot (g)</th>
                <th className="p-2 text-right">Kcal</th><th className="p-2 text-center">Anti-Anemia</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.dias.map((d, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    <td className="p-2 font-medium">{d.fecha}</td>
                    <td className="p-2">{d.receta}</td>
                    <td className={`p-2 text-right font-bold ${d.hierro_mg_racion >= data.nutrientes[0].meta ? 'text-emerald-700' : 'text-amber-600'}`}>{fmtN(d.hierro_mg_racion, 2)}</td>
                    <td className="p-2 text-right">{fmtN(d.proteina_g_racion, 2)}</td>
                    <td className="p-2 text-right">{fmtN(d.energia_kcal_racion, 0)}</td>
                    <td className="p-2 text-center">{d.es_anti_anemia ? '🩸' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!cargando && !data && !error && (
        <div className="p-10 text-center bg-slate-50 border border-slate-200 rounded-xl">
          <RefreshCw size={28} className="text-emerald-600 mx-auto mb-2" />
          <p className="text-sm text-slate-500">Configure el período y pulse "Generar reporte".</p>
        </div>
      )}
    </div>
  );
};