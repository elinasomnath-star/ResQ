import React from 'react';
import { ChartNoAxesCombined } from 'lucide-react';
import type { StockSweepRow } from '../types';

interface ScarcityChartProps {
  data: StockSweepRow[];
  activeStockPct: number;
  eventDate: string;
}

const engines = [
  { name: 'MILP', color: '#58C7FA' },
  { name: 'LinUCB', color: '#B49AFF' },
  { name: 'proportional', label: 'Proportional', color: '#51D6B0' },
];

function MetricChart({ data, activeStockPct, metric }: { data: StockSweepRow[]; activeStockPct: number; metric: 'coverage' | 'unmet' }) {
  const width = 620;
  const height = 250;
  const margin = { top: 18, right: 18, bottom: 38, left: 48 };
  const bottom = height - margin.bottom;
  const x = (value: number) => margin.left + ((value - 10) / 140) * (width - margin.left - margin.right);
  const y = (value: number) => bottom - (Math.max(0, Math.min(100, value)) / 100) * (bottom - margin.top);
  const valueKey = metric === 'coverage' ? 'min_zone_coverage_pct' : 'unmet_demand_pct';
  const bandMinKey = metric === 'coverage' ? 'min_zone_cov_min' : 'unmet_demand_min_pct';
  const bandMaxKey = metric === 'coverage' ? 'min_zone_cov_max' : 'unmet_demand_max_pct';
  const title = metric === 'coverage' ? 'Minimum zone coverage' : 'Unmet demand';

  const linePath = (rows: StockSweepRow[]) => rows
    .sort((a, b) => a.stock_pct - b.stock_pct)
    .map((row, index) => `${index ? 'L' : 'M'} ${x(row.stock_pct).toFixed(1)} ${y(Number(row[valueKey])).toFixed(1)}`)
    .join(' ');

  const bandPath = (rows: StockSweepRow[]) => {
    const sorted = [...rows].sort((a, b) => a.stock_pct - b.stock_pct);
    if (sorted.length < 2 || !sorted.some((row) => row[bandMinKey] != null && row[bandMaxKey] != null)) return '';
    const upper = sorted.map((row) => `${x(row.stock_pct).toFixed(1)},${y(Number(row[bandMaxKey] ?? row[valueKey])).toFixed(1)}`);
    const lower = [...sorted].reverse().map((row) => `${x(row.stock_pct).toFixed(1)},${y(Number(row[bandMinKey] ?? row[valueKey])).toFixed(1)}`);
    return `M ${upper.join(' L ')} L ${lower.join(' L ')} Z`;
  };

  const engineRows = engines.map((engine) => ({
    ...engine,
    rows: data.filter((row) => row.engine === engine.name),
  }));

  return (
    <section className="min-w-0 rounded-xl border border-white/10 bg-[#091321] p-3 sm:p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-slate-100">{title}</h4>
        
      </div>
      <div className="overflow-x-auto">
        <svg id={`scarcity-${metric}-svg`} viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[480px]" role="img" aria-label={`${title} over stock levels`}>
          {[0, 20, 40, 60, 80, 100].map((value) => <g key={value}>
            <line x1={margin.left} x2={width - margin.right} y1={y(value)} y2={y(value)} stroke={value === 40 && metric === 'coverage' ? '#f3b75f66' : '#ffffff14'} strokeDasharray={value === 40 && metric === 'coverage' ? '5 4' : undefined} />
            <text x={margin.left - 7} y={y(value) + 4} textAnchor="end" fill="#9aacc1" fontSize="10">{value}</text>
          </g>)}
          {metric === 'coverage' && <text x={width - margin.right - 2} y={y(40) - 5} textAnchor="end" fill="#f2c36a" fontSize="9">40% floor target</text>}
          {[10, 30, 50, 70, 90, 110, 130, 150].map((value) => <g key={value}>
            <line x1={x(value)} x2={x(value)} y1={bottom} y2={bottom + 4} stroke="#65778d" />
            <text x={x(value)} y={height - 9} textAnchor="middle" fill="#9aacc1" fontSize="9">{value}%</text>
          </g>)}
          {engineRows.map((engine) => <g key={engine.name}>
            {engine.name === 'LinUCB' && bandPath(engine.rows) && <path d={bandPath(engine.rows)} fill={engine.color} fillOpacity=".12" />}
            <path d={linePath(engine.rows)} fill="none" stroke={engine.color} strokeWidth="2.7" strokeLinejoin="round" strokeLinecap="round" />
            {engine.rows.map((row) => <circle key={`${engine.name}-${row.stock_pct}`} cx={x(row.stock_pct)} cy={y(Number(row[valueKey]))} r="2.3" fill={engine.color} />)}
          </g>)}
          <line x1={x(activeStockPct)} x2={x(activeStockPct)} y1={margin.top} y2={bottom} stroke="#f3b75f" strokeWidth="1.5" strokeDasharray="4 3" />
        </svg>
      </div>
      <p className="mt-1 text-[11px] text-slate-400">Y axis: percent · X axis: assumed stock as percent of modeled need{metric === 'coverage' ? ' · LinUCB shaded band: five-seed range' : ' · LinUCB shaded band: five-seed range'}</p>
    </section>
  );
}

export const ScarcityChart: React.FC<ScarcityChartProps> = ({ data, activeStockPct, eventDate }) => {
  const rows = Array.isArray(data) ? data : [];
  const hasData = rows.some((row) => Number.isFinite(row.min_zone_coverage_pct) && Number.isFinite(row.unmet_demand_pct));

  return (
    <div className="rounded-2xl border border-indigo-300/15 bg-gradient-to-br from-[#10182c] via-[#111a2c] to-[#17142c] p-4 sm:p-5 shadow-xl shadow-black/30 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl border border-indigo-300/20 bg-indigo-400/10 text-indigo-200"><ChartNoAxesCombined size={19} /></span>
          <div><h3 className="text-base font-bold text-white">Stock response curves</h3><p className="text-xs text-slate-300">{eventDate} · existing precomputed sweep results</p></div>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {engines.map((engine) => <span key={engine.name} className="inline-flex items-center gap-1.5" style={{ color: engine.color }}><i className="h-0.5 w-4" style={{ backgroundColor: engine.color }} />{engine.label || engine.name}</span>)}
          {rows.some((row) => row.engine === 'LinUCB' && row.min_zone_cov_min != null) && <span className="text-slate-400">LinUCB band: 5 seeds</span>}
        </div>
      </div>
      {!hasData ? <div className="rounded-xl border border-dashed border-white/15 bg-black/10 px-5 py-10 text-center">
        <p className="font-semibold text-slate-100">No stock-sweep results are available yet.</p>
        <p className="mt-1 text-sm text-slate-400">The chart is ready. Run <code>python validation/stock_sweep.py</code> and export frontend snapshots to populate it.</p>
      </div> : <div className="grid gap-3 xl:grid-cols-2">
        <MetricChart data={rows} activeStockPct={activeStockPct} metric="coverage" />
        <MetricChart data={rows} activeStockPct={activeStockPct} metric="unmet" />
      </div>}
      <p className="text-[11px] text-slate-400">Stock levels and resource amounts are assumptions for analysis, not measured shelter inventory.</p>
    </div>
  );
};

export default ScarcityChart;
