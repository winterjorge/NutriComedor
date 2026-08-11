import React from 'react';

export const GraficoEvolucion = ({ data }) => {
  if (!data || data.length === 0) return <div className="w-full h-48 flex items-center justify-center bg-slate-50 rounded-xl border border-slate-200"><p className="text-slate-400 text-sm">No hay datos históricos.</p></div>;
  const w = 600, h = 200;
  const min = Math.min(...data.map(d => d.precio)) * 0.95;
  const max = Math.max(...data.map(d => d.precio)) * 1.05;
  const rango = max - min === 0 ? 1 : max - min;
  const path = data.map((d, i) => { const x = (i / (data.length - 1)) * (w - 40) + 20; const y = h - ((d.precio - min) / rango) * (h - 40) - 20; return `${i === 0 ? 'M' : 'L'} ${x} ${y}`; }).join(' ');

  return (
    <div className="w-full overflow-x-auto bg-slate-50 p-4 rounded-xl border border-slate-200">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-48 min-w-[400px]">
        {[0, 0.5, 1].map(r => { const y = h - (r * (h - 40)) - 20; return <g key={r}><line x1="40" y1={y} x2={w} y2={y} stroke="#e2e8f0" strokeDasharray="4 4" /><text x="0" y={y + 4} className="text-[10px] fill-slate-400 font-medium">S/{(min + (rango * r)).toFixed(2)}</text></g>; })}
        <path d={path} fill="none" stroke="#10b981" strokeWidth="3" strokeLinecap="round" />
        {data.map((d, i) => { const x = (i / (data.length - 1)) * (w - 40) + 20; const y = h - ((d.precio - min) / rango) * (h - 40) - 20; return <g key={i}><circle cx={x} cy={y} r="4" fill="#fff" stroke="#10b981" strokeWidth="2" />{(i === 0 || i === Math.floor(data.length/2) || i === data.length - 1) && <text x={x} y={h} textAnchor="middle" className="text-[10px] fill-slate-400 font-medium">{d.label}</text>}</g>; })}
      </svg>
    </div>
  );
};