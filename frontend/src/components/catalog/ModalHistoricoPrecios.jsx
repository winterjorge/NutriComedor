import React, { useState, useEffect } from 'react';
import { X, TrendingUp, Loader2, ArrowDownToLine, ArrowUpToLine, Tag } from 'lucide-react';
import { api } from '../../services/api';

export const ModalHistoricoPrecios = ({ ingrediente, onClose }) => {
  const [rango, setRango] = useState('1w');
  const [historico, setHistorico] = useState([]);
  const [cargando, setCargando] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState(null);

  useEffect(() => {
    if (!ingrediente) return;
    
    const cargarHistorico = async () => {
      setCargando(true);
      setHoveredPoint(null);
      try {
        const data = await api.getHistoricoPrecios(ingrediente.id, rango);
        setHistorico(data || []);
      } catch (error) {
        console.error('Error cargando histórico:', error);
        setHistorico([]);
      } finally {
        setCargando(false);
      }
    };
    
    cargarHistorico();
  }, [ingrediente, rango]);

  const stats = React.useMemo(() => {
    if (!historico || historico.length === 0) return null;
    const precios = historico.map(h => h.precio);
    const min = Math.min(...precios);
    const max = Math.max(...precios);
    const actual = precios[precios.length - 1];
    return { min, max, actual };
  }, [historico]);

  if (!ingrediente) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="flex justify-between items-center p-5 border-b bg-slate-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-100 text-emerald-600 rounded-lg">
              <TrendingUp size={24} />
            </div>
            <div>
              <h3 className="font-bold text-xl">{ingrediente.nombre}</h3>
              <p className="text-sm text-slate-500 font-medium">{ingrediente.categoria}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-200 rounded-full transition-colors">
            <X size={24} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto">
          <div className="flex justify-center mb-6">
            <div className="inline-flex bg-slate-100 p-1 rounded-lg">
              {[{id:'1w',l:'1 Semana'},{id:'1m',l:'1 Mes'},{id:'6m',l:'6 Meses'},{id:'1y',l:'1 Año'}].map(r => (
                <button 
                  key={r.id} 
                  onClick={() => setRango(r.id)} 
                  className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${rango===r.id?'bg-white text-emerald-700 shadow-sm':'text-slate-500 hover:text-slate-700'}`}
                >
                  {r.l}
                </button>
              ))}
            </div>
          </div>

          {stats && (
            <div className="grid grid-cols-3 gap-3 mb-6">
              <div className="bg-blue-50 p-3 rounded-lg border border-blue-200 text-center">
                <div className="flex items-center justify-center gap-2 mb-1">
                  <ArrowDownToLine size={16} className="text-blue-600" />
                  <p className="text-xs font-semibold text-blue-800">Mínimo</p>
                </div>
                <p className="text-2xl font-black text-blue-700">S/ {stats.min.toFixed(2)}</p>
              </div>
              <div className="bg-emerald-50 p-3 rounded-lg border border-emerald-200 text-center">
                <div className="flex items-center justify-center gap-2 mb-1">
                  <Tag size={16} className="text-emerald-600" />
                  <p className="text-xs font-semibold text-emerald-800">Actual</p>
                </div>
                <p className="text-2xl font-black text-emerald-700">S/ {stats.actual.toFixed(2)}</p>
              </div>
              <div className="bg-amber-50 p-3 rounded-lg border border-amber-200 text-center">
                <div className="flex items-center justify-center gap-2 mb-1">
                  <ArrowUpToLine size={16} className="text-amber-600" />
                  <p className="text-xs font-semibold text-amber-800">Máximo</p>
                </div>
                <p className="text-2xl font-black text-amber-700">S/ {stats.max.toFixed(2)}</p>
              </div>
            </div>
          )}

          {cargando ? (
            <div className="h-64 flex items-center justify-center">
              <Loader2 className="animate-spin text-emerald-600" size={32}/>
            </div>
          ) : historico && historico.length > 0 ? (
            <GraficoEvolucionCorregido 
              data={historico} 
              hoveredPoint={hoveredPoint}
              setHoveredPoint={setHoveredPoint}
            />
          ) : (
            <div className="h-64 flex items-center justify-center bg-slate-50 rounded-xl border border-slate-200">
              <p className="text-slate-400 text-sm">No hay datos históricos disponibles para este rango.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const GraficoEvolucionCorregido = ({ data, hoveredPoint, setHoveredPoint }) => {
  if (!data || data.length === 0) return null;

  const width = 600;
  const height = 260;
  const padding = { top: 30, right: 30, bottom: 50, left: 70 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const minPrecio = Math.min(...data.map(d => d.precio));
  const maxPrecio = Math.max(...data.map(d => d.precio));
  
  const minY = Math.floor(minPrecio);
  const maxY = Math.ceil(maxPrecio);
  
  let rango = maxY - minY;
  if (rango === 0) rango = 1;
  const minYAdjusted = rango === 1 ? minY - 1 : minY;
  const maxYAdjusted = rango === 1 ? maxY + 1 : maxY;
  const rangoAdjusted = maxYAdjusted - minYAdjusted;

  const gridLines = [];
  for (let i = 0; i <= 4; i++) {
    const valorEquidistante = minYAdjusted + (rangoAdjusted * (i / 4));
    const y = padding.top + chartHeight - (i / 4) * chartHeight;
    
    let valorRedondeado;
    if (i === 0) {
      valorRedondeado = minYAdjusted;
    } else if (i === 4) {
      valorRedondeado = maxYAdjusted;
    } else {
      valorRedondeado = Math.ceil(valorEquidistante * 10) / 10;
    }
    
    gridLines.push({ valor: valorRedondeado, y });
  }

  const puntos = data.map((d, i) => {
    const x = data.length === 1 
      ? padding.left + chartWidth / 2 
      : padding.left + (i / (data.length - 1)) * chartWidth;
    const y = padding.top + chartHeight - ((d.precio - minYAdjusted) / rangoAdjusted) * chartHeight;
    return { x, y, precio: d.precio, label: d.label, index: i };
  });

  const pathD = puntos.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  return (
    <div className="w-full overflow-x-auto bg-slate-50 p-4 rounded-xl border border-slate-200">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-64 min-w-[400px]">
        {gridLines.map((line, i) => (
          <g key={`grid-${i}`}>
            <line 
              x1={padding.left} 
              y1={line.y} 
              x2={width - padding.right} 
              y2={line.y} 
              stroke="#e2e8f0" 
              strokeDasharray="4 4" 
            />
            <text 
              x={padding.left - 10} 
              y={line.y + 4} 
              textAnchor="end" 
              className="text-[11px] fill-slate-500 font-medium"
            >
              S/ {line.valor.toFixed(2)}
            </text>
          </g>
        ))}

        {data.length > 1 && (
          <path 
            d={pathD} 
            fill="none" 
            stroke="#10b981" 
            strokeWidth="3" 
            strokeLinecap="round" 
            strokeLinejoin="round" 
          />
        )}

        {puntos.map((p) => (
          <g key={`hover-${p.index}`}>
            <circle 
              cx={p.x} 
              cy={p.y} 
              r="20" 
              fill="transparent"
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoveredPoint(p)}
              onMouseLeave={() => setHoveredPoint(null)}
            />
            
            <circle 
              cx={p.x} 
              cy={p.y} 
              r={hoveredPoint?.index === p.index ? 7 : 5} 
              fill={hoveredPoint?.index === p.index ? '#10b981' : '#fff'} 
              stroke="#10b981" 
              strokeWidth="2"
              style={{ transition: 'all 0.2s ease', pointerEvents: 'none' }}
            />
            
            {hoveredPoint?.index === p.index && (
              <g>
                <rect 
                  x={p.x - 50} 
                  y={p.y - 45} 
                  width="100" 
                  height="32" 
                  rx="6" 
                  fill="#1e293b" 
                  opacity="0.95"
                />
                <text 
                  x={p.x} 
                  y={p.y - 30} 
                  textAnchor="middle" 
                  className="text-[11px] fill-white font-bold"
                >
                  S/ {p.precio.toFixed(2)}
                </text>
                <text 
                  x={p.x} 
                  y={p.y - 18} 
                  textAnchor="middle" 
                  className="text-[10px] fill-slate-300"
                >
                  {p.label}
                </text>
                <polygon 
                  points={`${p.x - 5},${p.y - 13} ${p.x + 5},${p.y - 13} ${p.x},${p.y - 7}`}
                  fill="#1e293b"
                  opacity="0.95"
                />
              </g>
            )}
            
            {(puntos.length <= 7 || p.index === 0 || p.index === puntos.length - 1 || p.index === Math.floor(puntos.length/2)) && (
              <text 
                x={p.x} 
                y={height - 10} 
                textAnchor="middle" 
                className="text-[10px] fill-slate-500 font-medium"
              >
                {p.label}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
};