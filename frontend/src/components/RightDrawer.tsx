import React, { useState } from 'react';
import {
  X,
  MapPin,
  Users,
  Package,
  Droplets,
  HeartPulse,
  Route,
  Sparkles,
  Lock,
  CheckCircle,
} from 'lucide-react';
import { ZoneData, AllocationRow, RouteFeature, UserRole } from '../types';
import CountUp from './reactbits/CountUp';
import { api } from '../services/api';

interface RightDrawerProps {
  zone: ZoneData | null;
  onClose: () => void;
  allocations: AllocationRow[];
  route?: RouteFeature | null;
  userRole?: UserRole;
  runId?: string;
  onOverrideSuccess?: () => void;
  onSwitchToOperator?: () => void;
}

export const RightDrawer: React.FC<RightDrawerProps> = ({
  zone,
  onClose,
  allocations,
  route,
  userRole = 'viewer',
  runId,
  onOverrideSuccess,
  onSwitchToOperator,
}) => {
  const [boostResource, setBoostResource] = useState<'food_rations' | 'water_liters' | 'medical_kits'>('food_rations');
  const [boostAmount, setBoostAmount] = useState(100);
  const [overrideMsg, setOverrideMsg] = useState<string | null>(null);
  const [isOverriding, setIsOverriding] = useState(false);

  if (!zone) return null;

  const zoneAllocations = allocations.filter((a) => a.zone_id === zone.zone_id);
  const foodAlloc = zoneAllocations.find((a) => a.resource === 'food_rations');
  const waterAlloc = zoneAllocations.find((a) => a.resource === 'water_liters');
  const medicalAlloc = zoneAllocations.find((a) => a.resource === 'medical_kits');

  const severityScore = zone.severity_score;
  const severityColor =
    severityScore > 0.65 ? '#FB7185' : severityScore > 0.35 ? '#FDE047' : '#2DD4BF';
  const severityLabel =
    severityScore > 0.65 ? 'High Priority' : severityScore > 0.35 ? 'Moderate' : 'Low Priority';

  const routeProps = route?.properties;
  const deliveryMode = routeProps?.delivery_mode || 'road';
  const isSecondary = deliveryMode === 'secondary';
  const roadDistanceKm = routeProps?.road_distance_m ? (routeProps.road_distance_m / 1000).toFixed(1) : null;
  const secondaryDistanceKm = routeProps?.secondary_distance_km ? routeProps.secondary_distance_km.toFixed(1) : null;

  const handleAdminOverride = async () => {
    if (userRole !== 'operator') return;
    setIsOverriding(true);
    setOverrideMsg(null);
    try {
      await api.adminOverride(
        runId || 'current_run',
        zone.zone_id,
        boostResource,
        boostAmount,
        `Emergency relief override for ${zone.zone_name}`
      );
      setOverrideMsg(`Boosted ${boostResource.replace('_', ' ')} by +${boostAmount}`);
      if (onOverrideSuccess) onOverrideSuccess();
    } catch (err: any) {
      setOverrideMsg(`Failed: ${err.message}`);
    } finally {
      setIsOverriding(false);
    }
  };

  return (
    <aside className="w-80 flex-shrink-0 flex flex-col gap-3 p-3.5 overflow-y-auto no-scrollbar border-l border-white/[0.08] bg-[#04070D]/85 backdrop-blur-2xl">
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-accent-cyan/10 border border-accent-cyan/25 font-heading font-bold text-sm text-accent-cyan">
            {zone.zone_id.replace('bantwal_grid_', '')}
          </div>
          <div>
            <h3 className="font-heading font-bold text-[13px] text-white leading-tight">
              {zone.zone_name}
            </h3>
            <span className="text-[10px] text-text-muted font-mono">
              Row {zone.grid_row}, Col {zone.grid_column}
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-text-muted hover:text-text-primary p-1.5 rounded-lg hover:bg-white/[0.05] transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Severity Ring */}
      <div className="glass-panel rounded-2xl p-3.5 flex items-center gap-4">
        <div className="relative flex-shrink-0 w-16 h-16 flex items-center justify-center">
          <svg className="w-16 h-16 transform -rotate-90">
            <circle cx="32" cy="32" r="26" className="stroke-white/10" strokeWidth="4.5" fill="transparent" />
            <circle
              cx="32" cy="32" r="26"
              stroke={severityColor}
              strokeWidth="4.5"
              strokeDasharray={163.3}
              strokeDashoffset={163.3 * (1 - severityScore)}
              strokeLinecap="round"
              fill="transparent"
              className="transition-all duration-700"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-heading font-bold text-[14px] text-white">
              {(severityScore * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        <div className="space-y-1 min-w-0">
          <div className="text-[10px] font-mono text-text-muted tracking-wider uppercase">Modelled Priority</div>
          <div className="text-[12px] font-heading font-semibold" style={{ color: severityColor }}>
            {severityLabel}
          </div>
          <div className="text-[10px] text-text-muted leading-relaxed">
            SAR: {(zone.sar_likelihood * 100).toFixed(1)}% &middot; Rain: {zone.antecedent_7day_rainfall_mm.toFixed(0)} mm
          </div>
        </div>
      </div>

      {/* Population */}
      <div className="glass-panel rounded-2xl p-3.5 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-text-secondary font-heading">
            <Users className="w-3.5 h-3.5 text-accent-cyan" />
            Population
          </span>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/[0.07] text-text-muted">
            WorldPop 2025
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-ink-900/50 p-2.5 border border-white/[0.05]">
            <div className="text-[10px] text-text-muted">Total</div>
            <div className="font-heading font-bold text-[15px] text-white mt-0.5">
              <CountUp to={zone.population_estimate} />
            </div>
            <div className="text-[9px] text-text-muted">WorldPop estimate</div>
          </div>
          <div className="rounded-xl bg-ink-900/50 p-2.5 border border-white/[0.05]">
            <div className="text-[10px] text-text-muted">Affected</div>
            <div className="font-heading font-bold text-[15px] text-amber-400 mt-0.5">
              <CountUp to={zone.estimated_affected_people} />
            </div>
            <div className="text-[9px] text-text-muted">Demand basis</div>
          </div>
        </div>
      </div>

      {/* Resource allocation */}
      <div className="glass-panel rounded-2xl p-3.5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-heading font-semibold text-text-primary">Allocated vs Need</span>
          <span className="text-[10px] font-mono text-accent-violet font-semibold">ASSUMED</span>
        </div>

        {[
          {
            icon: <Package className="w-3 h-3 text-amber-400" />,
            label: 'Food Rations',
            alloc: Math.min(foodAlloc?.estimated_need ?? zone.estimated_food_rations, Math.max(0, foodAlloc?.allocated ?? 0)),
            need: foodAlloc?.estimated_need ?? zone.estimated_food_rations,
            loaded: Boolean(foodAlloc),
            barColor: 'bg-amber-400',
          },
          {
            icon: <Droplets className="w-3 h-3 text-accent-cyan" />,
            label: 'Water (Litres)',
            alloc: Math.min(waterAlloc?.estimated_need ?? zone.estimated_water_liters, Math.max(0, waterAlloc?.allocated ?? 0)),
            need: waterAlloc?.estimated_need ?? zone.estimated_water_liters,
            loaded: Boolean(waterAlloc),
            barColor: 'bg-accent-cyan',
          },
          {
            icon: <HeartPulse className="w-3 h-3 text-rose-400" />,
            label: 'Medical Kits',
            alloc: Math.min(medicalAlloc?.estimated_need ?? zone.estimated_medical_kits, Math.max(0, medicalAlloc?.allocated ?? 0)),
            need: medicalAlloc?.estimated_need ?? zone.estimated_medical_kits,
            loaded: Boolean(medicalAlloc),
            barColor: 'bg-rose-400',
          },
        ].map(({ icon, label, alloc, need, loaded, barColor }) => (
          <div key={label} className="space-y-1">
            <div className="flex items-center justify-between text-[11px]">
              <span className="flex items-center gap-1 text-text-secondary">
                {icon} {label}
              </span>
              <span className="font-mono text-[10px]">
                <span className="text-text-primary font-bold">{loaded ? alloc.toLocaleString() : '—'}</span>
                <span className="text-text-muted"> / {need}</span>
              </span>
            </div>
            <div className="h-1.5 w-full bg-ink-900 rounded-full overflow-hidden border border-white/[0.05]">
              <div
                style={{ width: `${Math.min(100, (alloc / (need || 1)) * 100)}%` }}
                className={`h-full rounded-full ${barColor} transition-all duration-500`}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Dispatch route */}
      <div className="glass-panel rounded-2xl p-3.5 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-[11px] font-heading font-semibold text-text-secondary">
            <Route className="w-3.5 h-3.5 text-accent-cyan" />
            Dispatch Route
          </span>
          <span
            className={`text-[10px] font-mono px-2 py-0.5 rounded-md font-bold uppercase ${
              isSecondary
                ? 'bg-accent-violet/15 text-accent-violet border border-accent-violet/25'
                : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
            }`}
          >
            {isSecondary ? 'Secondary' : 'Road Routed'}
          </span>
        </div>

        {isSecondary ? (
          <div className="rounded-xl bg-accent-violet/[0.08] border border-accent-violet/20 p-2.5 text-[11px]">
            <span className="font-semibold text-accent-violet">UNVERIFIED CANDIDATE</span>
            <p className="text-[10px] text-text-muted mt-1 leading-relaxed">
              Straight-line secondary ({secondaryDistanceKm} km). Water/air navigability not confirmed.
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-between font-mono text-[11px]">
            <span className="text-text-muted">Road distance</span>
            <span className="font-bold text-white">{roadDistanceKm ? `${roadDistanceKm} km` : 'Calculated'}</span>
          </div>
        )}
      </div>

      {/* Admin override */}
      <div className="glass-panel rounded-2xl p-3.5 space-y-2.5 mt-auto">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-heading font-semibold text-text-primary flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-accent-indigo" />
            Admin Override
          </span>
          {userRole !== 'operator' && (
            <span className="text-[10px] text-text-muted font-mono flex items-center gap-1" title="Operator required">
              <Lock className="w-3 h-3" /> Locked
            </span>
          )}
        </div>

        {userRole === 'operator' ? (
          <div className="space-y-2.5">
            <div className="grid grid-cols-3 gap-1.5">
              {(['food_rations', 'water_liters', 'medical_kits'] as const).map((res) => (
                <button
                  key={res}
                  onClick={() => setBoostResource(res)}
                  className={`py-1.5 px-1 rounded-lg text-[10px] font-mono border capitalize transition-all ${
                    boostResource === res
                      ? 'border-accent-indigo/60 bg-accent-indigo/15 text-accent-indigo font-bold'
                      : 'border-white/[0.08] bg-white/[0.02] text-text-muted hover:border-white/20'
                  }`}
                >
                  {res.split('_')[0]}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <input
                type="number"
                min="10"
                step="50"
                value={boostAmount}
                onChange={(e) => setBoostAmount(parseInt(e.target.value) || 0)}
                className="w-20 rounded-lg border border-white/[0.1] bg-ink-950 px-2.5 py-1.5 text-[11px] font-mono text-text-primary focus:outline-none focus:border-accent-indigo/50"
              />
              <button
                onClick={handleAdminOverride}
                disabled={isOverriding}
                className="flex-1 py-1.5 px-3 rounded-lg bg-accent-indigo/15 border border-accent-indigo/35 hover:bg-accent-indigo/25 hover:border-accent-indigo/55 text-accent-indigo text-[11px] font-semibold transition-all disabled:opacity-40"
              >
                {isOverriding ? 'Applying…' : `+ Boost ${boostResource.split('_')[0]}`}
              </button>
            </div>

            {overrideMsg && (
              <div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5">
                <CheckCircle className="w-3 h-3" /> {overrideMsg}
              </div>
            )}
          </div>
        ) : (
          <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] text-[11px] text-text-muted flex items-center justify-between gap-2">
            <div>
              <span className="text-text-secondary">Operator role required</span>
              <span className="block text-[10px] text-text-muted mt-0.5">Current role: viewer</span>
            </div>
            {onSwitchToOperator && (
              <button
                onClick={onSwitchToOperator}
                className="px-2.5 py-1 rounded-lg bg-accent-indigo/15 border border-accent-indigo/40 text-accent-indigo hover:bg-accent-indigo/25 font-semibold text-[10px] transition cursor-pointer flex-shrink-0"
              >
                Switch Role
              </button>
            )}
          </div>
        )}
      </div>
    </aside>
  );
};

export default RightDrawer;
