import React, { useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle, Download, FileUp, Upload, X } from 'lucide-react';
import type { FacilityStockSummary, User } from '../types';
import { api } from '../services/api';

interface FieldLogsModalProps {
  isOpen: boolean;
  onClose: () => void;
  offlineMode: boolean;
  user: User | null;
  onImported: () => Promise<void>;
  onRunAllocation: () => void;
}

const RESOURCES = [
  { id: 'food_rations', label: 'Food rations', unit: 'rations' },
  { id: 'water_liters', label: 'Water', unit: 'L' },
  { id: 'medical_kits', label: 'Medical kits', unit: 'kits' },
] as const;

export const FieldLogsModal: React.FC<FieldLogsModalProps> = ({
  isOpen,
  onClose,
  offlineMode,
  user,
  onImported,
  onRunAllocation,
}) => {
  const isOperator = user?.role === 'operator';
  const [summary, setSummary] = useState<FacilityStockSummary | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const [message, setMessage] = useState<{ text: string; isError: boolean } | null>(null);

  const loadSummary = useCallback(async () => {
    setSummary(await api.getStockSummary());
  }, []);

  useEffect(() => {
    if (isOpen) {
      void api.getStockSummary().then(setSummary).catch(() => {
        setMessage({ text: 'Could not load the current stock pool.', isError: true });
      });
    }
  }, [isOpen]);

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setIsImporting(true);
    setMessage(null);
    try {
      const result = await api.importStockCSV(await file.text());
      await onImported();
      await loadSummary();
      setMessage({
        text: `Imported ${result.stock_items_updated} stock rows across ${result.facilities_updated} sites. The next allocation will use these entered quantities.`,
        isError: false,
      });
    } catch (error) {
      setMessage({ text: error instanceof Error ? error.message : 'Field log CSV import failed.', isError: true });
    } finally {
      setIsImporting(false);
    }
  };

  if (!isOpen) return null;

  const pool = summary?.totals || {};
  const hasEnteredStock = RESOURCES.some((resource) => Number(pool[resource.id]?.quantity || 0) > 0);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 backdrop-blur-sm p-4" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="field-logs-title"
        className="w-full max-w-2xl overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-800 bg-slate-950/70 px-6 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h2 id="field-logs-title" className="text-xl font-bold tracking-tight text-white">Field Logs</h2>
              <span className="rounded border border-amber-500/40 bg-amber-500/15 px-2.5 py-0.5 text-xs font-semibold text-amber-300">
                ENTERED, UNVERIFIED
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">Import operator-recorded shelter stock for the next allocation run.</p>
          </div>
          <button onClick={onClose} aria-label="Close Field Logs" className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="space-y-5 px-6 py-5">
          <div className="rounded-xl border border-amber-800/60 bg-amber-950/35 px-4 py-3 text-xs leading-relaxed text-amber-200">
            Each upload replaces the previous field-log snapshot. Only rows in the selected CSV enter the allocation pool; omitted sites/resources return to assumed stock and are excluded from field-log runs. Values are manual reports, not live telemetry.
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-300">Current field-log pool</h3>
              {!summary && <span className="text-[11px] text-slate-500">Loading…</span>}
            </div>
            <div className="grid grid-cols-3 gap-2">
              {RESOURCES.map((resource) => (
                <div key={resource.id} className="rounded-xl border border-slate-700/80 bg-slate-950/45 px-3 py-2.5">
                  <div className="text-[10px] font-medium text-slate-400">{resource.label}</div>
                  <div className="mt-1 font-mono text-sm font-semibold text-white">
                    {Number(pool[resource.id]?.quantity || 0).toLocaleString()} <span className="text-[10px] font-normal text-slate-500">{resource.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {isOperator ? (
            <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <FileUp className="h-4 w-4 text-cyan-300" />
                  <div>
                    <div className="text-sm font-semibold text-slate-100">Import stock CSV</div>
                    <div className="text-[11px] text-slate-400">Headers: facility_id, resource, quantity, unit, note</div>
                  </div>
                </div>
                <a href="/data/sample_field_logs.csv" download className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-cyan-400/50 hover:bg-cyan-950/30 hover:text-cyan-200">
                  <Download className="h-3.5 w-3.5" /> Sample CSV
                </a>
              </div>
              <label className={`mt-4 flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-cyan-500/40 bg-cyan-950/20 px-4 py-4 text-sm font-semibold text-cyan-100 transition hover:border-cyan-300/70 hover:bg-cyan-950/35 ${offlineMode || isImporting ? 'cursor-not-allowed opacity-50' : ''}`}>
                <Upload className="h-4 w-4" />
                {isImporting ? 'Validating and importing…' : 'Choose field log CSV'}
                <input type="file" accept=".csv,text/csv" onChange={handleImport} disabled={offlineMode || isImporting} className="sr-only" />
              </label>
              {offlineMode && <p className="mt-2 text-[11px] text-amber-300">Connect the API to import field logs or run an allocation with entered stock.</p>}
            </div>
          ) : (
            <div className="rounded-xl border border-slate-700 bg-slate-950/40 px-4 py-3 text-xs text-slate-300">
              Field-log CSV imports are available to operators. Viewers can inspect the current pool.
            </div>
          )}

          {message && (
            <div className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-xs ${message.isError ? 'border-rose-800 bg-rose-950/40 text-rose-200' : 'border-emerald-800 bg-emerald-950/35 text-emerald-200'}`} role={message.isError ? 'alert' : 'status'}>
              {message.isError ? <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <CheckCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
              <span>{message.text}</span>
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-800 bg-slate-950/70 px-6 py-4">
          <span className="text-[11px] text-slate-500">{hasEnteredStock ? 'Field-log stock is ready for allocation.' : 'Import a CSV to create an entered-stock pool.'}</span>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="rounded-lg px-3 py-2 text-xs font-medium text-slate-300 transition hover:bg-slate-800">Close</button>
            <button
              onClick={() => { onClose(); onRunAllocation(); }}
              disabled={!hasEnteredStock || offlineMode}
              className="rounded-lg border border-cyan-400/30 bg-cyan-600 px-4 py-2 text-xs font-semibold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Run allocation with field logs
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
};

export default FieldLogsModal;
