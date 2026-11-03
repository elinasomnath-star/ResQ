import React from 'react';
import { Package, Droplets, HeartPulse, AlertTriangle } from 'lucide-react';
import CountUp from './reactbits/CountUp';

interface ResourceMeterProps {
  label: string;
  icon: React.ReactNode;
  remaining: number;
  total: number;
  allocatedThisStep: number;
  color: 'amber' | 'cyan' | 'rose';
}

const barGradient = {
  amber: 'from-amber-600 via-amber-500 to-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.4)]',
  cyan: 'from-cyan-600 via-accent-cyan to-sky-300 shadow-[0_0_12px_rgba(34,211,238,0.4)]',
  rose: 'from-rose-600 via-rose-500 to-pink-400 shadow-[0_0_12px_rgba(244,63,94,0.4)]',
};

const ResourceMeter: React.FC<ResourceMeterProps> = ({ label, icon, remaining, total, allocatedThisStep, color }) => {
  const safeTotal = Math.max(0, total);
  const safeRemaining = Math.min(safeTotal, Math.max(0, remaining));
  const allocated = safeTotal - safeRemaining;
  const remainingPct = safeTotal > 0 ? (safeRemaining / safeTotal) * 100 : 0;
  const allocatedPct = safeTotal > 0 ? (allocated / safeTotal) * 100 : 0;
  const depleted = remainingPct <= 20;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-[12px] font-bold text-white">
          {icon}
          <span>{label}</span>
        </span>
        <span
          className="whitespace-nowrap font-mono text-[11.5px]"
          aria-label={`${allocated.toLocaleString()} allocated of ${safeTotal.toLocaleString()}; ${safeRemaining.toLocaleString()} remaining`}
        >
          <b className="font-extrabold text-white text-[12px]">
            <CountUp to={allocated} />
          </b>
          <span className="text-slate-300 font-semibold"> / {safeTotal.toLocaleString()}</span>
        </span>
      </div>

      <div
        className={`relative h-2.5 w-full overflow-hidden rounded-full border border-white/15 bg-black/60 shadow-inner ${
          depleted ? 'ring-2 ring-accent-alert/80' : ''
        }`}
      >
        <div
          className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 bg-gradient-to-r ${barGradient[color]}`}
          style={{ width: `${allocatedPct}%` }}
        />
        <div
          className="absolute bottom-0 top-0 z-10 w-[2px] bg-rose-400 shadow-[0_0_6px_rgba(244,63,94,0.9)]"
          style={{ left: '80%' }}
          title="20% remaining threshold"
        />
      </div>

      <div className="flex items-center justify-between text-[10.5px] font-mono leading-none pt-0.5">
        <span className="text-cyan-300 font-bold bg-cyan-950/60 border border-cyan-400/30 px-2 py-0.5 rounded-md">
          {Math.max(0, allocatedThisStep).toLocaleString()} allocated
        </span>
        <span className={`font-bold ${depleted ? 'text-rose-300' : 'text-slate-200'}`}>
          {safeRemaining.toLocaleString()} left &middot; {remainingPct.toFixed(0)}%
        </span>
      </div>
    </div>
  );
};

interface InventoryPanelProps {
  foodRemaining: number;
  foodTotal: number;
  waterRemaining: number;
  waterTotal: number;
  medicalRemaining: number;
  medicalTotal: number;
  stepAllocation: { food_rations: number; water_liters: number; medical_kits: number };
  stepNumber: number;
  hasRoundData: boolean;
  className?: string;
}

export const InventoryPanel: React.FC<InventoryPanelProps> = ({
  foodRemaining,
  foodTotal,
  waterRemaining,
  waterTotal,
  medicalRemaining,
  medicalTotal,
  stepAllocation,
  stepNumber,
  hasRoundData,
  className = '',
}) => {
  return (
    <section
      role="region"
      aria-label="Assumed Resource Pool"
      className={`glass-panel rounded-2xl p-4 space-y-3.5 shadow-2xl backdrop-blur-2xl border border-white/20 bg-gradient-to-b from-[#0c1322]/95 via-[#080d19]/95 to-[#050813]/95 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-white/10">
        <div className="flex items-center gap-2 text-[13px] font-bold text-white font-heading tracking-wide">
          <div className="p-1 rounded-lg bg-cyan-950/60 border border-cyan-400/30 text-accent-cyan shadow-[0_0_10px_rgba(34,211,238,0.2)]">
            <Package className="w-4 h-4 text-accent-cyan" />
          </div>
          <span>Resource Pool</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-violet-950/70 text-violet-300 border border-violet-400/40 font-bold tracking-wider">
            ASSUMED
          </span>
          <span className="text-[10.5px] font-mono font-bold text-slate-200 bg-black/50 px-2 py-0.5 rounded-md border border-white/10">
            {hasRoundData ? `Round ${stepNumber}/8` : 'Run result'}
          </span>
        </div>
      </div>

      {/* Meters */}
      <div className="space-y-3">
        <ResourceMeter
          label="Food Rations"
          icon={
            <div className="p-1 rounded-md bg-amber-500/15 border border-amber-500/30 text-amber-400">
              <Package className="h-3.5 w-3.5 text-amber-400" />
            </div>
          }
          remaining={foodRemaining}
          total={foodTotal}
          allocatedThisStep={stepAllocation.food_rations}
          color="amber"
        />
        <ResourceMeter
          label="Water (Litres)"
          icon={
            <div className="p-1 rounded-md bg-cyan-500/15 border border-cyan-500/30 text-accent-cyan">
              <Droplets className="h-3.5 w-3.5 text-accent-cyan" />
            </div>
          }
          remaining={waterRemaining}
          total={waterTotal}
          allocatedThisStep={stepAllocation.water_liters}
          color="cyan"
        />
        <ResourceMeter
          label="Medical Kits"
          icon={
            <div className="p-1 rounded-md bg-rose-500/15 border border-rose-500/30 text-rose-400">
              <HeartPulse className="h-3.5 w-3.5 text-rose-400" />
            </div>
          }
          remaining={medicalRemaining}
          total={medicalTotal}
          allocatedThisStep={stepAllocation.medical_kits}
          color="rose"
        />
      </div>

      {/* Legend & status hint */}
      <div className="pt-2 border-t border-white/10 flex items-center justify-between text-[10px] font-mono">
        <span className="flex items-center gap-1.5 text-rose-300 font-bold">
          <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
          <span>Mark = 20% remaining</span>
        </span>
        <span className="text-slate-300 font-medium truncate max-w-[190px]">
          {foodRemaining <= 0 && waterRemaining <= 0
            ? 'Food/water depleted; meds remain'
            : '80% of pool used'}
        </span>
      </div>
    </section>
  );
};

export default InventoryPanel;
