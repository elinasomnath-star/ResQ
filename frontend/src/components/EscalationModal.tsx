import React from 'react';
import { X, AlertTriangle, ArrowRight, RefreshCw, ShieldAlert, Zap } from 'lucide-react';
import { EscalationRecord } from '../types';
import AnimatedList from './reactbits/AnimatedList';

interface EscalationModalProps {
  onClose: () => void;
  escalations: EscalationRecord[];
  selectedEvent: string;
}

export const EscalationModal: React.FC<EscalationModalProps> = ({
  onClose,
  escalations,
  selectedEvent,
}) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/80 backdrop-blur-xl">
      <div className="relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-2xl border border-white/15 bg-ink-900/95 p-6 shadow-2xl space-y-4">
        {/* Header with DecryptedText animation */}
        <div className="flex items-center justify-between pb-3 border-b border-white/10">
          <div>
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-accent-alert animate-pulse" />
              <h2 className="font-heading text-lg font-bold text-text-primary tracking-wide">
                MODULE 9: SHORTAGE ALERTS &amp; REALLOCATION
              </h2>
            </div>
            <p className="text-xs text-text-secondary mt-0.5">
              Event {selectedEvent} &middot; Automatic threshold-triggered inter-zone resource transfers
            </p>
          </div>

          <button
            onClick={onClose}
            aria-label="Close Alerts"
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/5 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Shortage Summary Banner */}
        <div className="rounded-xl border border-accent-alert/30 bg-accent-alert/10 p-3 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-accent-alert" />
            <span className="text-text-primary font-medium">
              Shortage Trigger Threshold: <span className="font-mono font-bold text-accent-alert">20% unmet ratio</span>
            </span>
          </div>
          <span className="font-mono text-[11px] text-text-secondary">
            {escalations.length} shortage alerts recorded
          </span>
        </div>

        {/* AnimatedList of Escalation & Reallocation Triggers */}
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          <AnimatedList delay={0.04}>
            {escalations.map((esc, index) => {
              const shortfallMap = esc.shortfall_by_resource || {};
              const shortfallEntries = Object.entries(shortfallMap);
              const formatEngine = (eng: string) => {
                if (eng.includes('MILP')) return 'MILP';
                if (eng.includes('LinUCB')) return 'LinUCB Bandit';
                if (eng.includes('proportional')) return 'Proportional';
                return eng.replace(/_/g, ' ');
              };

              return (
                <div
                  key={esc.trigger_id || index}
                  className="rounded-xl border border-white/10 bg-gradient-to-r from-white/[0.04] to-white/[0.015] p-3.5 space-y-2.5 hover:border-white/20 transition-all shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-accent-alert animate-ping" />
                      <span className="font-mono font-bold text-xs text-text-primary">
                        Round {esc.step}: {esc.resource_types_short} Shortfall
                      </span>
                      <span className="text-[11px] font-mono font-semibold text-accent-cyan/90">
                        &middot; {formatEngine(esc.engine)}
                      </span>
                    </div>

                    <span className="text-[10.5px] font-mono px-2 py-0.5 rounded-full bg-accent-cyan/10 border border-accent-cyan/30 text-accent-cyan font-bold">
                      {esc.transfer_count > 0 ? `${esc.transfer_count} Redirects` : 'Shortage Alert'}
                    </span>
                  </div>

                  {/* Shortfalls */}
                  {shortfallEntries.length > 0 && (
                    <div className="flex flex-wrap gap-2 text-[11px] font-mono">
                      {shortfallEntries.map(([res, amount]) => (
                        <div
                          key={res}
                          className="px-2.5 py-1 rounded-lg bg-rose-950/40 border border-rose-500/25 text-slate-200"
                        >
                          <span className="capitalize text-slate-400">{res.split('_')[0]}: </span>
                          <span className="text-accent-alert font-bold">-{Number(amount).toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Donor to Recipient Transfer Route */}
                  <div className="flex items-center justify-between text-[11px] text-text-muted pt-1 border-t border-white/5 font-mono">
                    <div className="flex items-center gap-1.5 text-accent-indigo">
                      <RefreshCw className="w-3 h-3 text-accent-indigo" />
                      <span>Donor Transfer: Zone 06 → Zone 01 & Zone 10</span>
                    </div>
                    <span>
                      Floor: {esc.min_zone_coverage_before_pct?.toFixed(1) ?? '13.4'}% →{' '}
                      <span className="text-emerald-400 font-bold">
                        {esc.min_zone_coverage_after_pct?.toFixed(1) ?? '13.4'}%
                      </span>
                    </span>
                  </div>
                </div>
              );
            })}
          </AnimatedList>
        </div>

        {/* Footer */}
        <div className="pt-2 border-t border-white/10 flex items-center justify-between text-[11px] text-text-muted">
          <span>Module 9 bounded heuristic transfers</span>
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-text-primary font-medium text-xs transition-colors"
          >
            Close Feed
          </button>
        </div>
      </div>
    </div>
  );
};

export default EscalationModal;
