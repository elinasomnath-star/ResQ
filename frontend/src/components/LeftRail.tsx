import React from 'react';
import {
  Calendar,
  Waves,
  Cpu,
  Layers,
  Play,
  RotateCcw,
} from 'lucide-react';
import { EventRecord, EngineType, StockMode } from '../types';

interface LeftRailProps {
  events: EventRecord[];
  selectedEvent: string;
  onSelectEvent: (eventDate: string) => void;
  selectedEngine: EngineType;
  onSelectEngine: (engine: EngineType) => void;
  stockMode: StockMode;
  onToggleStockMode: (mode: StockMode) => void;
  onRunSimulation: () => void;
  isSimulating: boolean;
}

export const LeftRail: React.FC<LeftRailProps> = ({
  events,
  selectedEvent,
  onSelectEvent,
  selectedEngine,
  onSelectEngine,
  stockMode,
  onToggleStockMode,
  onRunSimulation,
  isSimulating,
}) => {
  const currentEventData = events.find((e) => e.event_date === selectedEvent) || events[0];
  const waterLevel = currentEventData?.water_level_m;
  const dangerLine = currentEventData?.danger_mark_m ?? 9.0;
  const warningLine = currentEventData?.warning_level_m ?? 8.0;
  const maxScale = 13.0;
  const waterPct = waterLevel == null ? 0 : Math.min(Math.max((waterLevel / maxScale) * 100, 10), 100);
  const dangerPct = (dangerLine / maxScale) * 100;
  const warningPct = (warningLine / maxScale) * 100;
  const isAboveDanger = waterLevel != null && waterLevel >= dangerLine;
  const isAtWarning = waterLevel != null && waterLevel >= warningLine;

  return (
    <aside className="w-full flex flex-col gap-3">
      {/* ── Event Selection & Gauge ─────────────────────────── */}
      <div className="glass-panel rounded-2xl p-4 space-y-3.5">
        {/* Section header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[12px] font-bold text-white font-heading">
            <Calendar className="w-3.5 h-3.5 text-accent-cyan" />
            <span>Flood Event</span>
          </div>
          <span className="text-[10px] font-mono text-slate-300 font-semibold tracking-wider">Bantwal CWC</span>
        </div>

        {/* Event Pills */}
        <div className="grid grid-cols-3 gap-1.5">
          {events.map((ev) => {
            const isSelected = ev.event_date === selectedEvent;
            const year = ev.event_date.split('-')[0];
            return (
              <button
                key={ev.event_date}
                onClick={() => onSelectEvent(ev.event_date)}
                className={`py-2.5 px-2 rounded-xl border text-center transition-all duration-200 ${
                  isSelected
                    ? 'border-accent-cyan/60 bg-accent-cyan/15 text-accent-cyan shadow-[0_0_14px_rgba(34,211,238,0.22)]'
                    : 'border-white/[0.1] bg-white/[0.025] text-slate-200 hover:border-white/20 hover:text-white hover:bg-white/[0.05]'
                }`}
              >
                <div className="font-heading font-bold text-[13.5px] leading-tight">{year}</div>
                <div className="text-[11px] font-mono text-slate-300 font-medium mt-0.5">{ev.water_level_m}m</div>
              </button>
            );
          })}
        </div>

        {/* Water Gauge */}
        <div className="rounded-xl border border-white/[0.1] bg-ink-950/70 p-3.5">
          <div className="flex items-center justify-between mb-2.5">
            <span className="flex items-center gap-1.5 text-[11.5px] font-semibold text-slate-200">
              <Waves className="w-3.5 h-3.5 text-accent-cyan" />
              Netravati River
            </span>
            <span
              className={`font-mono text-[10.5px] font-bold px-2 py-0.5 rounded-md ${
                isAboveDanger
                  ? 'bg-accent-alert/20 text-rose-300 border border-accent-alert/40 shadow-[0_0_8px_rgba(244,63,94,0.3)]'
                  : isAtWarning
                  ? 'bg-amber-400/18 text-amber-200 border border-amber-300/40 shadow-[0_0_8px_rgba(251,191,36,0.25)]'
                  : 'bg-severity-teal/18 text-teal-200 border border-severity-teal/40'
              }`}
            >
              {waterLevel == null ? '–' : `${waterLevel.toFixed(1)} m`}
            </span>
          </div>

          <div className="relative h-28 w-full rounded-lg bg-ink-900 border border-white/[0.08] overflow-hidden flex items-end">
            {/* Water fill */}
            <div
              style={{ height: `${waterPct}%` }}
              className={`w-full transition-all duration-700 relative ${
                isAboveDanger
                  ? 'bg-gradient-to-t from-accent-alert/65 to-red-400/85'
                  : isAtWarning
                  ? 'bg-gradient-to-t from-amber-500/65 to-yellow-300/85'
                  : 'bg-gradient-to-t from-accent-cyan/55 to-severity-teal/75'
              }`}
            >
              <div className="absolute top-0 inset-x-0 h-1 bg-white/60 animate-pulse" />
            </div>

            {/* Danger line */}
            <div
              style={{ bottom: `${dangerPct}%` }}
              className="absolute inset-x-0 border-b-2 border-dashed border-accent-alert z-10 pointer-events-none h-0"
            >
              <span className="absolute right-2 bottom-0 translate-y-[-115%] text-[9.5px] font-mono font-bold text-rose-300 bg-ink-950/95 px-1.5 rounded whitespace-nowrap shadow-sm border border-rose-500/30">
                {dangerLine.toFixed(1)}m DANGER
              </span>
            </div>
            {/* Warning line */}
            <div
              style={{ bottom: `${warningPct}%` }}
              className="absolute inset-x-0 border-b border-dashed border-amber-300/80 z-10 pointer-events-none h-0"
            >
              <span className="absolute left-2 top-0 translate-y-[115%] text-[9.5px] font-mono font-bold text-amber-200 bg-ink-950/95 px-1.5 rounded whitespace-nowrap shadow-sm border border-amber-400/30">
                {warningLine.toFixed(1)}m WARNING
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between text-[10.5px] font-mono text-slate-300 font-semibold mt-1.5">
            <span>0.0 m</span>
            <span className={isAboveDanger ? 'text-rose-400' : isAtWarning ? 'text-amber-300' : 'text-slate-300'}>
              {isAboveDanger
                ? `${(waterLevel! - dangerLine).toFixed(1)}m above danger`
                : isAtWarning
                ? `${(dangerLine - waterLevel!).toFixed(1)}m below danger`
                : 'Below warning'}
            </span>
            <span>14.0 m</span>
          </div>
        </div>
      </div>

      {/* ── Allocation Engine ────────────────────────────────── */}
      <div className="glass-panel rounded-2xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[12px] font-bold text-white font-heading">
            <Cpu className="w-3.5 h-3.5 text-engine-milp" />
            <span>Allocation Engine</span>
          </div>
          <span className="text-[10px] font-mono text-slate-300 font-semibold">Module 6</span>
        </div>

        <div className="space-y-1.5">
          {/* MILP */}
          <button
            onClick={() => onSelectEngine('MILP')}
            className={`w-full flex items-center justify-between p-3 rounded-xl border text-left transition-all duration-200 ${
              selectedEngine === 'MILP'
                ? 'border-engine-milp/60 bg-engine-milp/15 text-white shadow-[0_0_14px_rgba(96,165,250,0.18)]'
                : 'border-white/[0.08] bg-white/[0.025] text-slate-200 hover:border-white/18 hover:bg-white/[0.05]'
            }`}
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-engine-milp shadow-[0_0_6px_#60a5fa]" />
                <span className="font-heading font-bold text-[12.5px] text-white">MILP Optimizer</span>
              </div>
              <p className="text-[11px] text-slate-300 mt-1 pl-[18px] leading-relaxed font-medium">
                Exact solver &middot; 40% target with feasible floor
              </p>
            </div>
            {selectedEngine === 'MILP' && (
              <span className="text-[10px] font-mono font-extrabold text-engine-milp flex-shrink-0 ml-2 tracking-wider">ACTIVE</span>
            )}
          </button>

          {/* LinUCB */}
          <button
            onClick={() => onSelectEngine('LinUCB')}
            className={`w-full flex items-center justify-between p-3 rounded-xl border text-left transition-all duration-200 ${
              selectedEngine === 'LinUCB'
                ? 'border-engine-linucb/60 bg-engine-linucb/15 text-white shadow-[0_0_14px_rgba(251,146,60,0.18)]'
                : 'border-white/[0.08] bg-white/[0.025] text-slate-200 hover:border-white/18 hover:bg-white/[0.05]'
            }`}
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-engine-linucb shadow-[0_0_6px_#fb923c]" />
                <span className="font-heading font-bold text-[12.5px] text-white">LinUCB Bandit</span>
              </div>
              <p className="text-[11px] text-slate-300 mt-1 pl-[18px] leading-relaxed font-medium">
                Contextual exploration &middot; Reward maximization
              </p>
            </div>
            {selectedEngine === 'LinUCB' && (
              <span className="text-[10px] font-mono font-extrabold text-engine-linucb flex-shrink-0 ml-2 tracking-wider">ACTIVE</span>
            )}
          </button>

          {/* Proportional */}
          <button
            onClick={() => onSelectEngine('proportional')}
            className={`w-full flex items-center justify-between p-3 rounded-xl border text-left transition-all duration-200 ${
              selectedEngine === 'proportional'
                ? 'border-engine-proportional/60 bg-engine-proportional/15 text-white shadow-[0_0_14px_rgba(74,222,128,0.18)]'
                : 'border-white/[0.08] bg-white/[0.025] text-slate-200 hover:border-white/18 hover:bg-white/[0.05]'
            }`}
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-engine-proportional shadow-[0_0_6px_#4ade80]" />
                <span className="font-heading font-bold text-[12.5px] text-white">Proportional</span>
              </div>
              <p className="text-[11px] text-slate-300 mt-1 pl-[18px] leading-relaxed font-medium">
                Heuristic ratio &middot; Severity-weighted
              </p>
            </div>
            {selectedEngine === 'proportional' && (
              <span className="text-[10px] font-mono font-extrabold text-engine-proportional flex-shrink-0 ml-2 tracking-wider">ACTIVE</span>
            )}
          </button>
        </div>
      </div>

      {/* ── Stock Assumption ─────────────────────────────────── */}
      <div className="glass-panel rounded-2xl p-4 space-y-3.5 border border-white/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-[12.5px] font-bold text-white font-heading">
            <Layers className="w-4 h-4 text-violet-400" />
            <span>Stock Assumption</span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-violet-950/70 border border-violet-400/40 text-violet-300 font-bold tracking-wider">
            ASSUMED
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={() => onToggleStockMode('configured')}
            className={`p-2.5 rounded-xl border text-left transition-all duration-200 ${
              stockMode === 'configured'
                ? 'border-violet-400/70 bg-violet-950/50 text-violet-200 font-semibold shadow-[0_0_12px_rgba(167,139,250,0.25)]'
                : 'border-white/10 bg-black/40 text-slate-300 hover:border-white/20 hover:bg-white/[0.05]'
            }`}
          >
            <div className={`text-[12px] font-heading font-bold ${stockMode === 'configured' ? 'text-white' : 'text-slate-200'}`}>
              Configured
            </div>
            <div className={`text-[10px] mt-0.5 font-medium ${stockMode === 'configured' ? 'text-violet-300' : 'text-slate-400'}`}>
              Prototype stock
            </div>
          </button>

          <button
            onClick={() => onToggleStockMode('simulated')}
            className={`p-2.5 rounded-xl border text-left transition-all duration-200 ${
              stockMode === 'simulated'
                ? 'border-cyan-400/70 bg-cyan-950/50 text-cyan-200 font-semibold shadow-[0_0_12px_rgba(34,211,238,0.25)]'
                : 'border-white/10 bg-black/40 text-slate-300 hover:border-white/20 hover:bg-white/[0.05]'
            }`}
          >
            <div className={`text-[12px] font-heading font-bold ${stockMode === 'simulated' ? 'text-white' : 'text-slate-200'}`}>
              Simulated
            </div>
            <div className={`text-[10px] mt-0.5 font-medium ${stockMode === 'simulated' ? 'text-cyan-300' : 'text-slate-400'}`}>
              Pooled reserve
            </div>
          </button>

          <button
            onClick={() => onToggleStockMode('entered')}
            className={`p-2.5 rounded-xl border text-left transition-all duration-200 ${
              stockMode === 'entered'
                ? 'border-amber-400/80 bg-amber-950/50 text-amber-200 font-semibold shadow-[0_0_12px_rgba(251,191,36,0.25)]'
                : 'border-white/10 bg-black/40 text-slate-300 hover:border-white/20 hover:bg-white/[0.05]'
            }`}
          >
            <div className={`text-[12px] font-heading font-bold ${stockMode === 'entered' ? 'text-amber-100' : 'text-slate-200'}`}>
              Entered
            </div>
            <div className={`text-[10px] mt-0.5 font-medium ${stockMode === 'entered' ? 'text-amber-300' : 'text-amber-400/80'}`}>
              Field logs
            </div>
          </button>
        </div>

        <div className="bg-black/40 p-2.5 rounded-xl border border-white/[0.07]">
          <p className="text-[11.5px] text-slate-200 font-medium leading-relaxed">
            {stockMode === 'configured'
              ? 'Prototype inventory assumption. Results depend on this modelled stock profile.'
              : stockMode === 'simulated'
              ? 'Event-specific pooled simulated reserve; not measured shelter inventory.'
              : 'Operator-entered quantities. Not synced with a live warehouse system.'}
          </p>
        </div>

        {/* Run button */}
        <button
          onClick={onRunSimulation}
          disabled={isSimulating}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl border border-accent-cyan/60 bg-gradient-to-r from-accent-cyan/20 to-blue-500/20 text-cyan-200 font-bold text-[12.5px] hover:from-accent-cyan/30 hover:to-blue-500/30 hover:border-accent-cyan/80 transition-all shadow-[0_0_18px_rgba(34,211,238,0.2)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {isSimulating ? (
            <>
              <RotateCcw className="w-4 h-4 animate-spin text-cyan-300" />
              <span>Solving…</span>
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-cyan-300 text-cyan-300" />
              <span>Run Allocation Replay</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
};

export default LeftRail;
