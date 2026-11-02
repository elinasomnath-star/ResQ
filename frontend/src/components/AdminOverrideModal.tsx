import React, { useState, useEffect, useMemo } from 'react';
import type { AllocationRow, User } from '../types';
import { api } from '../services/api';
import { exportToCSV } from '../utils/export';

interface AdminOverrideModalProps {
  isOpen: boolean;
  onClose: () => void;
  runId: string;
  allocations: AllocationRow[];
  availableInventory: { food_rations: number; water_liters: number; medical_kits: number };
  offlineMode: boolean;
  user: User | null;
  onOverrideApplied: (newAllocations: AllocationRow[]) => void;
}

export const AdminOverrideModal: React.FC<AdminOverrideModalProps> = ({
  isOpen,
  onClose,
  runId,
  allocations,
  availableInventory,
  offlineMode,
  user,
  onOverrideApplied,
}) => {
  const isOperator = user?.role === 'operator';
  const [editedAllocations, setEditedAllocations] = useState<AllocationRow[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successInfo, setSuccessInfo] = useState<string | null>(null);

  const inventoryLimits = useMemo(() => availableInventory, [availableInventory]);

  useEffect(() => {
    if (allocations && allocations.length > 0) {
      setEditedAllocations(JSON.parse(JSON.stringify(allocations)));
    }
  }, [allocations, isOpen]);

  // Totals allocated
  const totals = useMemo(() => {
    const res = { food_rations: 0, water_liters: 0, medical_kits: 0 };
    editedAllocations.forEach((row) => {
      if (row.resource in res) {
        res[row.resource as keyof typeof res] += Number(row.allocated) || 0;
      }
    });
    return res;
  }, [editedAllocations]);

  // Inventory violations
  const inventoryViolations = useMemo(() => {
    const errors: string[] = [];
    if (totals.food_rations > inventoryLimits.food_rations) {
      errors.push(`Food rations (${totals.food_rations.toLocaleString()}) exceed available stock (${inventoryLimits.food_rations.toLocaleString()})`);
    }
    if (totals.water_liters > inventoryLimits.water_liters) {
      errors.push(`Water liters (${totals.water_liters.toLocaleString()}) exceed available stock (${inventoryLimits.water_liters.toLocaleString()})`);
    }
    if (totals.medical_kits > inventoryLimits.medical_kits) {
      errors.push(`Medical kits (${totals.medical_kits.toLocaleString()}) exceed available stock (${inventoryLimits.medical_kits.toLocaleString()})`);
    }
    return errors;
  }, [totals, inventoryLimits]);

  // Match the API rule: a donor floor violation occurs only when an edit reduces
  // a row below 40% of its need.
  const coverageStats = useMemo(() => {
    const original = new Map(allocations.map((row) => [`${row.zone_id}|${row.resource}`, row.allocated]));
    const coverages = editedAllocations.map((row) => ({
      ...row,
      original: original.get(`${row.zone_id}|${row.resource}`) ?? row.allocated,
      pct: row.estimated_need > 0 ? (Number(row.allocated) / row.estimated_need) * 100 : 100,
    }));
    const donorFloorViolations = coverages.filter((row) =>
      row.allocated < row.original && row.allocated < Math.ceil(0.4 * row.estimated_need)
    );
    const meanCoverage = coverages.length ? coverages.reduce((sum, row) => sum + row.pct, 0) / coverages.length : 0;
    const beforeMeanCoverage = coverages.length
      ? coverages.reduce((sum, row) => sum + (row.estimated_need > 0 ? row.original / row.estimated_need * 100 : 100), 0) / coverages.length
      : 0;
    return { meanCoverage, beforeMeanCoverage, donorFloorViolations };
  }, [allocations, editedAllocations]);

  const handleQuantityChange = (index: number, newQty: number) => {
    if (!isOperator) return;
    setEditedAllocations((prev) => {
      const updated = [...prev];
      const target = { ...updated[index] };
      const qty = Math.max(0, Math.floor(newQty || 0));
      target.allocated = qty;
      target.unmet = Math.max(0, target.estimated_need - qty);
      target.unmet_pct = target.estimated_need > 0 ? (target.unmet / target.estimated_need) * 100 : 0;
      updated[index] = target;
      return updated;
    });
  };

  const handleExportCSV = () => {
    exportToCSV(`resq_allocation_override_${runId || 'current'}`, editedAllocations, [
      'zone_id',
      'zone_name',
      'resource',
      'estimated_need',
      'allocated',
      'unmet',
      'unmet_pct',
    ]);
  };

  const handleApplyOverride = async () => {
    if (!isOperator) return;
    if (!runId || runId.startsWith('offline_run_') || offlineMode) {
      setErrorMessage('Run this allocation with the API first. Offline snapshots are read-only and cannot accept overrides.');
      return;
    }
    if (inventoryViolations.length > 0) {
      setErrorMessage(`Cannot apply override: ${inventoryViolations.join('; ')}`);
      return;
    }
    if (coverageStats.donorFloorViolations.length > 0) {
      setErrorMessage(
        `Cannot apply override: ${coverageStats.donorFloorViolations.length} edited row(s) would fall below the 40% donor floor.`
      );
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const overridesPayload = editedAllocations.map((a) => ({
        zone_id: a.zone_id,
        resource: a.resource,
        allocated: a.allocated,
      }));
      const res = await api.applyAllocationOverride(runId, overridesPayload);
      const changes = res.coverage_changes || [];
      const before = changes.length ? changes.reduce((sum, row) => sum + row.before_coverage_pct, 0) / changes.length : coverageStats.beforeMeanCoverage;
      const after = changes.length ? changes.reduce((sum, row) => sum + row.after_coverage_pct, 0) / changes.length : coverageStats.meanCoverage;
      const delta = after - before;
      setSuccessInfo(`Manual override saved · mean resource coverage ${before.toFixed(1)}% → ${after.toFixed(1)}% (${delta > 0 ? '+' : ''}${delta.toFixed(1)} pp).`);
      onOverrideApplied(editedAllocations);
      setTimeout(() => {
        onClose();
      }, 1400);
    } catch (err: any) {
      setErrorMessage(err.message || 'Override application failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden text-slate-100">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold tracking-tight text-white">Manual Allocation Override</h2>
              <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                manual override, not an optimization result
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Adjust this run&apos;s allocations. The API checks resource caps and the 40% donor floor before saving.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Admin Override"
            className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition"
          >
            ✕
          </button>
        </div>

        {/* Status Bar */}
        <div className="bg-slate-950/40 px-6 py-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-slate-400">Food Allocated: </span>
              <span className={totals.food_rations > inventoryLimits.food_rations ? 'text-red-400 font-bold' : 'text-slate-200 font-mono'}>
                {totals.food_rations.toLocaleString()} / {inventoryLimits.food_rations.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-slate-400">Water Allocated: </span>
              <span className={totals.water_liters > inventoryLimits.water_liters ? 'text-red-400 font-bold' : 'text-slate-200 font-mono'}>
                {totals.water_liters.toLocaleString()} / {inventoryLimits.water_liters.toLocaleString()}
              </span>
            </div>
            <div>
              <span className="text-slate-400">Medical Allocated: </span>
              <span className={totals.medical_kits > inventoryLimits.medical_kits ? 'text-red-400 font-bold' : 'text-slate-200 font-mono'}>
                {totals.medical_kits.toLocaleString()} / {inventoryLimits.medical_kits.toLocaleString()}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Min Zone Coverage:</span>
            <span className={`font-bold font-mono px-2 py-0.5 rounded ${coverageStats.donorFloorViolations.length ? 'bg-red-500/20 text-red-400 border border-red-500/40' : 'bg-emerald-500/20 text-emerald-300'}`}>
              Mean {coverageStats.meanCoverage.toFixed(1)}% · before {coverageStats.beforeMeanCoverage.toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Violations Alert */}
        {(inventoryViolations.length > 0 || coverageStats.donorFloorViolations.length > 0) && (
          <div className="bg-red-950/40 border-b border-red-800/50 px-6 py-2.5 text-xs text-red-300 flex flex-col gap-1">
            {inventoryViolations.map((err, i) => (
              <div key={i} className="flex items-center gap-2 font-medium">
                <span>⚠️</span> <span>{err}</span>
              </div>
            ))}
            {coverageStats.donorFloorViolations.length > 0 && (
              <div className="flex items-center gap-2 font-medium">
                <span>⛔</span>
                <span>
                  Donor fairness floor: {coverageStats.donorFloorViolations.length} edited row(s) are below 40% of need.
                </span>
              </div>
            )}
          </div>
        )}

        {errorMessage && (
          <div className="bg-red-950/50 border-b border-red-800 px-6 py-2 text-xs text-red-200">
            {errorMessage}
          </div>
        )}

        {successInfo && (
          <div className="bg-emerald-950/50 border-b border-emerald-800 px-6 py-2 text-xs text-emerald-200">
            {successInfo}
          </div>
        )}

        {/* Table Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="sticky top-0 bg-slate-900 border-b border-slate-700 text-slate-400 uppercase font-medium">
              <tr>
                <th className="py-2.5 px-3">Zone</th>
                <th className="py-2.5 px-3">Resource</th>
                <th className="py-2.5 px-3 text-right">Need</th>
                <th className="py-2.5 px-3 text-right">Allocated</th>
                <th className="py-2.5 px-3 text-right">Unmet</th>
                <th className="py-2.5 px-3 text-right">Coverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {editedAllocations.map((row, idx) => {
                const cov = row.estimated_need > 0 ? (row.allocated / row.estimated_need) * 100 : 100;
                return (
                  <tr key={`${row.zone_id}_${row.resource}`} className="hover:bg-slate-800/40 transition">
                    <td className="py-2 px-3 font-sans font-medium text-slate-200">
                      {row.zone_name} <span className="text-slate-500 font-mono text-[11px]">({row.zone_id})</span>
                    </td>
                    <td className="py-2 px-3 font-sans text-slate-300">
                      {row.resource.replace('_', ' ')}
                    </td>
                    <td className="py-2 px-3 text-right text-slate-400">
                      {row.estimated_need.toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-right">
                      {isOperator ? (
                        <input
                          type="number"
                          min={0}
                          value={row.allocated}
                          onChange={(e) => handleQuantityChange(idx, parseInt(e.target.value) || 0)}
                          className="w-24 px-2 py-1 text-right bg-slate-800 border border-slate-700 focus:border-amber-400 rounded text-slate-100 font-mono"
                        />
                      ) : (
                        <span className="text-slate-200">{row.allocated.toLocaleString()}</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-slate-400">
                      {row.unmet.toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className={`px-1.5 py-0.5 rounded text-[11px] font-bold ${cov < 40 ? 'bg-red-500/20 text-red-400' : cov < 70 ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/20 text-emerald-300'}`}>
                        {cov.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={handleExportCSV}
              className="px-3.5 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-xs text-slate-200 font-medium transition flex items-center gap-2"
            >
              📥 Export CSV
            </button>
            {!isOperator && (
              <span className="text-xs text-slate-400 italic">
                Viewer mode: Log in as operator to modify allocations.
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onClose}
              className="px-4 py-1.5 rounded-lg text-xs text-slate-300 hover:bg-slate-800 transition"
            >
              Cancel
            </button>
            {isOperator && (
              <button
                disabled={isSubmitting || !runId || runId.startsWith('offline_run_') || offlineMode || inventoryViolations.length > 0 || coverageStats.donorFloorViolations.length > 0}
                onClick={handleApplyOverride}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 hover:bg-amber-500 text-slate-950 transition disabled:opacity-40 disabled:cursor-not-allowed shadow-md"
              >
                {isSubmitting ? 'Validating...' : 'Apply Manual Override'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
