import React from 'react';
import { AlertTriangle, ChartNoAxesCombined } from 'lucide-react';
import type { EngineType, StockSweepRow } from '../types';

interface ScarcitySliderProps {
  stockPct: number;
  onChange: (newPct: number) => void;
  donorFloorThreshold?: number;
  linucbCollapseThreshold?: number;
  onOpenChart?: () => void;
  comparisonRows?: StockSweepRow[];
  selectedEngine?: EngineType;
  disabled?: boolean;
  disabledMessage?: string;
}

const metric = (value: number | undefined) =>
  Number.isFinite(value) ? `${value!.toFixed(1)}%` : '—';

export const ScarcitySlider: React.FC<ScarcitySliderProps> = ({
  stockPct,
  onChange,
  donorFloorThreshold = 40,
  linucbCollapseThreshold = 10,
  onOpenChart,
  comparisonRows = [],
  selectedEngine = 'MILP',
  disabled = false,
  disabledMessage,
}) => {
  const engines: { engine: EngineType; color: string; label: string }[] = [
    { engine: 'MILP', color: '#60A5FA', label: 'MILP' },
    { engine: 'LinUCB', color: '#C084FC', label: 'LinUCB' },
    { engine: 'proportional', color: '#4ADE80', label: 'Proportional' },
  ];
  const floorThreshold = Number.isFinite(donorFloorThreshold) ? donorFloorThreshold : 40;
  const collapseThreshold = Number.isFinite(linucbCollapseThreshold) ? linucbCollapseThreshold : 10;
  const floorX = `${((floorThreshold - 10) / 140) * 100}%`;
  const collapseX = `${((collapseThreshold - 10) / 140) * 100}%`;

  return (
    <section className="stock-sensitivity frost-panel" aria-label="Stock sensitivity explorer">
      {/* ── Single-row heading ── */}
      <div className="stock-sensitivity-heading flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-[12.5px] font-bold uppercase tracking-[.12em] text-white whitespace-nowrap font-heading">
            Stock Sensitivity
          </span>
          <span className="rounded-full border border-cyan-400/40 bg-cyan-950/60 px-2.5 py-0.5 text-[11px] font-bold text-cyan-300 whitespace-nowrap font-mono shadow-sm">
            {stockPct}% of modeled need
          </span>
          <span className="text-[11px] text-slate-300 font-medium hidden xl:block whitespace-nowrap">
            5% steps · assumed supply
          </span>
        </div>
        {onOpenChart && (
          <button
            onClick={onOpenChart}
            className="flex-shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-accent-indigo/50 bg-accent-indigo/20 px-3 py-1 text-[11px] font-semibold text-accent-indigo hover:bg-accent-indigo/30 transition-all shadow-sm"
          >
            <ChartNoAxesCombined size={13} />
            <span className="hidden sm:inline font-bold">View curves</span>
          </button>
        )}
      </div>

      {/* ── Slider + threshold marks (cutting cleanly right through the bar) ── */}
      <div className="stock-sensitivity-range relative mx-0.5 mt-2">
        <div className="relative flex items-center h-5 w-full">
          <input
            aria-label="Assumed stock percentage"
            type="range"
            min={10} max={150} step={5}
            value={stockPct}
            onChange={(e) => onChange(Number(e.target.value))}
            disabled={disabled}
            title={disabled ? disabledMessage : 'This percentage is applied to modeled need when you run an allocation'}
            className="relative z-10 h-2 w-full cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 appearance-none rounded-full
                       bg-gradient-to-r from-rose-500/80 via-accent-violet/80 to-accent-cyan/80
                       accent-accent-violet my-0"
          />
          {/* Threshold markers bisecting/cutting right through the track */}
          <div className="pointer-events-none absolute inset-0 flex items-center z-20">
            <span
              title={`LinUCB collapse threshold ${collapseThreshold}%`}
              className="absolute top-1/2 -translate-y-1/2 h-4 w-[2.5px] bg-rose-500 rounded-sm shadow-[0_0_6px_rgba(244,63,94,0.9)]"
              style={{ left: collapseX }}
            />
            <span
              title={`40% floor threshold: ${floorThreshold.toFixed(1)}%`}
              className="absolute top-1/2 -translate-y-1/2 h-4 w-[2.5px] bg-amber-400 rounded-sm shadow-[0_0_6px_rgba(251,191,36,0.9)]"
              style={{ left: floorX }}
            />
          </div>
        </div>

        {/* Scale labels + threshold hints with clear dots & spacing */}
        <div className="mt-1 flex items-center justify-between gap-3 text-[11px] font-mono leading-none">
          <span className="text-slate-300 font-bold">10%</span>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-rose-300 font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400 inline-block shadow-[0_0_4px_#f43f5e]" />
              LinUCB &lt;1%: {collapseThreshold}%
            </span>
            <span className="flex items-center gap-1.5 text-amber-300 font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block shadow-[0_0_4px_#fbbf24]" />
              Floor: {floorThreshold.toFixed(1)}%
            </span>
          </div>
          <span className="text-slate-400 hidden lg:block text-[10px]">{disabled ? disabledMessage : 'Applied to pool on next run · assumed supply'}</span>
          <span className="text-slate-300 font-bold">150%</span>
        </div>
      </div>

      {/* ── Engine comparison cards — clean, readable, spacious ── */}
      <div className="stock-sensitivity-engines mt-2.5 grid grid-cols-3 gap-2" aria-live="polite">
        {engines.map(({ engine, color, label }) => {
          const row = comparisonRows.find((item) => item.engine === engine);
          const selected = selectedEngine === engine;
          return (
            <div
              key={engine}
              className={`flex items-center justify-between gap-2 rounded-xl border px-3 py-1.5 transition-all ${
                selected
                  ? 'border-white/35 bg-white/[0.09] shadow-[0_2px_14px_rgba(0,0,0,0.4)]'
                  : 'border-white/[0.12] bg-white/[0.035]'
              }`}
              style={{ borderColor: selected ? `${color}88` : undefined }}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
                <span className="text-[12.5px] font-bold truncate font-heading" style={{ color }}>{label}</span>
                {selected && <span className="px-1.5 py-0.5 rounded bg-accent-indigo/30 text-[8.5px] font-mono font-bold text-accent-indigo uppercase tracking-wider hidden xl:block">ACTIVE</span>}
              </div>
              <div className="flex items-center gap-2 font-mono flex-shrink-0">
                <span className="flex items-center gap-1 bg-black/50 px-2 py-0.5 rounded-md border border-white/10"><span className="text-[9.5px] uppercase tracking-wider text-slate-300 font-bold">cov</span><b className="text-[12px] font-extrabold text-white">{metric(row?.min_zone_coverage_pct)}</b></span>
                <span className="flex items-center gap-1 bg-black/50 px-2 py-0.5 rounded-md border border-white/10"><span className="text-[9.5px] uppercase tracking-wider text-slate-300 font-bold">unmet</span><b className="text-[12px] font-extrabold text-amber-300">{metric(row?.unmet_demand_pct)}</b></span>
              </div>
            </div>
          );
        })}
      </div>

      {comparisonRows.some((row) => row.engine === selectedEngine && (row.zone_coverage_vector?.length ?? 0) > 0) && (() => {
        const selected = comparisonRows.find((row) => row.engine === selectedEngine);
        const vector = selected?.zone_coverage_vector ?? [];
        const fullyCovered = vector.filter((c) => c >= 99.5).length;
        const leastIdx = vector.reduce((l, c, i, v) => (c < v[l] ? i : l), 0);
        return <p className="mt-1.5 truncate text-[11px] font-mono text-slate-200 leading-tight"><span className="text-cyan-300 font-semibold">{stockPct}% stock</span> &middot; {fullyCovered}/{vector.length} zones fully covered &middot; lowest: Zone {String(leastIdx + 1).padStart(2, '0')} (<span className="text-amber-300 font-bold">{metric(vector[leastIdx])}</span>)</p>;
      })()}

      {stockPct < floorThreshold && (
        <p className="mt-1 flex items-center gap-1.5 text-[10px] text-amber-400 leading-tight">
          <AlertTriangle size={12} />
          40% floor below feasibility at this stock level
        </p>
      )}
    </section>
  );
};

export default ScarcitySlider;
