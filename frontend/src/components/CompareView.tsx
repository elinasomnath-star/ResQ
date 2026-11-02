import React from 'react';
import { X, BarChart3 } from 'lucide-react';
import { ZoneData, StepRecord } from '../types';

interface CompareViewProps {
  onClose: () => void;
  zones: ZoneData[];
  stepsData: StepRecord[];
  selectedEvent: string;
}

const engineDefinitions: { id: string[]; label: string; color: string; dash: string }[] = [
  { id: ['MILP'], label: 'MILP', color: '#60A5FA', dash: '' },
  { id: ['LinUCB', 'LinUCB_contextual_bandit'], label: 'LinUCB', color: '#FB923C', dash: '' },
  { id: ['proportional', 'naive_proportional_baseline'], label: 'Proportional', color: '#4ADE80', dash: '5 3' },
];

export const CompareView: React.FC<CompareViewProps> = ({ onClose, zones, stepsData, selectedEvent }) => {
  const chartWidth = 720;
  const chartHeight = 260;
  const pad = { left: 52, right: 20, top: 20, bottom: 38 };
  const values = stepsData.map((step) => Number(step.min_zone_coverage_pct)).filter(Number.isFinite);
  const maxValue = Math.max(10, Math.ceil((Math.max(...values, 10) * 1.1) / 5) * 5);
  const xAt = (step: number) => pad.left + ((step - 1) / 7) * (chartWidth - pad.left - pad.right);
  const yAt = (value: number) => chartHeight - pad.bottom - (value / maxValue) * (chartHeight - pad.top - pad.bottom);
  const series = engineDefinitions.map((engine) => ({
    ...engine,
    rows: stepsData
      .filter((step) => engine.id.includes(step.engine))
      .sort((a, b) => Number(a.step) - Number(b.step)),
  }));
  const hasSteps = series.some((item) => item.rows.length > 0);
  const minSeverity = Math.min(...zones.map((zone) => Number(zone.severity_score)).filter(Number.isFinite));
  const maxSeverity = Math.max(...zones.map((zone) => Number(zone.severity_score)).filter(Number.isFinite));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-xl">
      <section className="relative w-full max-w-5xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/15 bg-ink-900/95 p-6 shadow-2xl space-y-6">
        <header className="flex items-start justify-between pb-4 border-b border-white/10">
          <div>
            <div className="flex items-center gap-2 text-text-primary">
              <BarChart3 className="w-5 h-5 text-accent-cyan" />
              <h2 className="font-heading text-xl font-bold">Allocation replay comparison</h2>
            </div>
            <p className="text-sm text-text-secondary mt-1">{selectedEvent} · Bantwal 16-zone study area</p>
          </div>
          <button onClick={onClose} aria-label="Close comparison" className="p-2 rounded-lg text-text-muted hover:text-white hover:bg-white/5">
            <X className="w-5 h-5" />
          </button>
        </header>

        <section className="rounded-xl border border-white/10 bg-ink-950/60 p-4 space-y-3">
          <div>
            <h3 className="text-base font-semibold text-text-primary">Minimum zone coverage by round</h3>
            <p className="text-sm text-text-secondary">Values come from the selected event’s replay data and current stock mode.</p>
          </div>
          {hasSteps ? (
            <div className="overflow-x-auto">
              <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full min-w-[600px] h-auto" role="img" aria-label="Minimum zone coverage over eight rounds">
                {[0, maxValue / 4, maxValue / 2, maxValue * 3 / 4, maxValue].map((value) => (
                  <g key={value}>
                    <line x1={pad.left} x2={chartWidth - pad.right} y1={yAt(value)} y2={yAt(value)} stroke="rgba(255,255,255,.12)" />
                    <text x={pad.left - 8} y={yAt(value) + 4} fill="#A8B6C9" fontSize="11" textAnchor="end">{value.toFixed(0)}%</text>
                  </g>
                ))}
                {Array.from({ length: 8 }, (_, index) => index + 1).map((step) => (
                  <text key={step} x={xAt(step)} y={chartHeight - 10} fill="#A8B6C9" fontSize="11" textAnchor="middle">R{step}</text>
                ))}
                {series.map((engine) => {
                  const points = engine.rows.map((row) => `${xAt(Number(row.step))},${yAt(Number(row.min_zone_coverage_pct))}`).join(' ');
                  return engine.rows.length ? <g key={engine.label}>
                    <polyline points={points} fill="none" stroke={engine.color} strokeWidth="3" strokeDasharray={engine.dash} strokeLinejoin="round" />
                    {engine.rows.map((row) => <circle key={`${engine.label}-${row.step}`} cx={xAt(Number(row.step))} cy={yAt(Number(row.min_zone_coverage_pct))} r="4" fill={engine.color} />)}
                  </g> : null;
                })}
              </svg>
              <div className="flex flex-wrap gap-4 text-sm">
                {series.map((engine) => engine.rows.length > 0 && <span key={engine.label} className="flex items-center gap-2" style={{ color: engine.color }}><i className="w-4 border-t-2" style={{ borderColor: engine.color, borderStyle: engine.dash ? 'dashed' : 'solid' }} />{engine.label}</span>)}
              </div>
            </div>
          ) : <p className="rounded-lg bg-white/5 p-4 text-sm text-text-secondary">No step-by-step allocation replay is available for this event and stock mode.</p>}
        </section>

        <section className="rounded-xl border border-white/10 bg-ink-950/60 p-4 space-y-3">
          <div>
            <h3 className="text-base font-semibold text-text-primary">Modeled zone severity</h3>
            <p className="text-sm text-text-secondary">Relative priority scores used as allocation inputs; these are not observed flood depths.</p>
          </div>
          {zones.length ? <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
            {zones.map((zone, index) => {
              const value = Number(zone.severity_score);
              const t = maxSeverity > minSeverity ? (value - minSeverity) / (maxSeverity - minSeverity) : 0.5;
              return <div key={zone.zone_id} className="rounded-lg border border-white/10 bg-white/[0.03] p-2 text-center">
                <div className="text-xs font-semibold text-text-primary">Grid {String(index + 1).padStart(2, '0')}</div>
                <div className="my-2 h-2 rounded-full bg-white/10 overflow-hidden"><div className="h-full rounded-full bg-emerald-400" style={{ width: `${Math.max(0, Math.min(100, t * 100))}%` }} /></div>
                <div className="text-xs font-mono text-text-secondary">{Number.isFinite(value) ? value.toFixed(2) : '—'}</div>
              </div>;
            })}
          </div> : <p className="text-sm text-text-secondary">Zone severity data is unavailable.</p>}
        </section>
        <p className="text-xs leading-relaxed text-text-muted">Inventory is simulated or configured according to the selected stock mode. This view reports replay data and does not imply live shelter stock.</p>
      </section>
    </div>
  );
};

export default CompareView;
