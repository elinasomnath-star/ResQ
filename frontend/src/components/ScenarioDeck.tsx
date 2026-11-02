import React, { useState, useEffect } from 'react';
import type { Scenario, ScenarioResult } from '../types';
import { api } from '../services/api';

interface ScenarioDeckProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectScenario: (scenario: Scenario, seed?: number) => void | Promise<void>;
}

function scenarioHighlights(result: ScenarioResult): string[] {
  if (result.category === 'road_closure') {
    return ['Mapped main road blocked', 'Live Bantwal routes recalculated'];
  }
  const payload = result as unknown as Record<string, any>;
  const metrics = payload.results?.MILP
    ?? payload.surge_impact?.post_surge_metrics
    ?? payload.stock_loss_impact?.post_loss_metrics
    ?? payload.noise_impact?.metrics
    ?? payload.custom_results?.MILP
    ?? null;
  if (metrics) {
    const highlights: string[] = [];
    const unmet = Number(metrics.aggregate_unmet_demand_pct);
    const minimum = Number(metrics.minimum_zone_fairness_pct ?? metrics.minimum_zone_coverage_pct);
    if (Number.isFinite(unmet)) highlights.push(`Unmet demand ${unmet.toFixed(1)}%`);
    if (Number.isFinite(minimum)) highlights.push(`Minimum zone coverage ${minimum.toFixed(1)}%`);
    if (Number.isFinite(Number(metrics.solve_or_inference_time_seconds))) {
      highlights.push(`Solve ${Number(metrics.solve_or_inference_time_seconds).toFixed(3)} s`);
    }
    if (highlights.length) return highlights;
  }
  if (Array.isArray(payload.ladder_results)) {
    const tiers = payload.ladder_results;
    const finalTier = tiers.at(-1);
    return [
      `${tiers.length} stock tiers evaluated`,
      finalTier ? `At ${finalTier.stock_pct}% stock: ${Number(finalTier.MILP?.unmet_pct ?? 0).toFixed(1)}% unmet` : '',
    ].filter(Boolean);
  }
  if (payload.routing_impact) {
    return [`${Number(payload.routing_impact.unreachable_zone_count ?? 0)} zones marked unreachable in the hypothetical stress case`];
  }
  return ['Scenario run completed with the selected event assumptions.'];
}

export const ScenarioDeck: React.FC<ScenarioDeckProps> = ({
  isOpen,
  onClose,
  onSelectScenario,
}) => {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null);
  const [comparisonScenario, setComparisonScenario] = useState<Scenario | null>(null);
  const [isComparing, setIsComparing] = useState<boolean>(false);
  const [randomSeed, setRandomSeed] = useState<number>(42);
  const [loading, setLoading] = useState<boolean>(true);
  const [executing, setExecuting] = useState<boolean>(false);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isOffline = api.getOfflineMode();

  useEffect(() => {
    let mounted = true;
    const fetchScenarios = async () => {
      setLoading(true);
      try {
        const data = await api.getScenarios();
        if (mounted) {
          setScenarios(data);
          if (data.length > 0) setSelectedScenario(data[0]);
        }
      } catch (err) {
        console.error('Failed to load scenarios:', err);
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchScenarios();
    return () => {
      mounted = false;
    };
  }, []);

  const handleRandomizeSeed = () => {
    const nextSeed = Math.floor(Math.random() * 90000) + 1000;
    setRandomSeed(nextSeed);
  };

  const handleRunScenario = async (sc: Scenario) => {
    setExecuting(true);
    setError(null);
    setResult(null);
    try {
      if (sc.closure_id) {
        await onSelectScenario(sc, randomSeed);
        setResult({
          scenario_id: sc.id,
          scenario_title: sc.title,
          category: sc.category || 'road_closure',
          event_date: sc.event_date,
          seed: randomSeed,
          summary: {},
          disclaimer: sc.assumptions_statement || '',
        });
      } else {
        const res = await api.runScenario(sc.id, randomSeed);
        setResult(res);
        await onSelectScenario(sc, randomSeed);
      }
    } catch (err: any) {
      setError(err.message || 'Execution failed');
    } finally {
      setExecuting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden text-slate-100">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/70">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold tracking-tight text-white">Scenario Evaluation Deck</h2>
              <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                3 Bantwal Road Blockage Scenarios
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Block mapped Bantwal roads and recalculate relief routes across the local road network.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Scenario Deck"
            className="text-slate-400 hover:text-white p-2 rounded-lg hover:bg-slate-800 transition"
          >
            ✕
          </button>
        </div>

        {/* Evaluator Toolbar */}
        <div className="bg-slate-950/40 px-6 py-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-3">
            <button
              onClick={handleRandomizeSeed}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-mono transition flex items-center gap-1.5"
            >
              🎲 Randomize Seed: <strong className="text-indigo-400">{randomSeed}</strong>
            </button>
            <button
              onClick={() => setIsComparing(!isComparing)}
              className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition ${isComparing ? 'bg-indigo-600 border-indigo-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'}`}
            >
              {isComparing ? 'Exit Comparison' : 'Compare Two Scenarios'}
            </button>
          </div>
          {isOffline && (
            <span className="px-2 py-0.5 rounded text-[11px] bg-amber-500/20 text-amber-300 border border-amber-500/30">
              Road blockage scenarios need the live API to recalculate routes
            </span>
          )}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Scenario Cards List */}
          <div className="md:col-span-1 flex flex-col gap-3 overflow-y-auto max-h-[580px] pr-2">
            {loading ? (
              <div className="text-xs text-slate-400">Loading scenario library...</div>
            ) : (
              (Array.isArray(scenarios) ? scenarios : []).map((sc) => {
                const isSelected = selectedScenario?.id === sc.id;
                const isCompSelected = comparisonScenario?.id === sc.id;
                const isReplay = sc.category === 'road_closure';
                return (
                  <button
                    type="button"
                    key={sc.id}
                    aria-pressed={isSelected}
                    aria-label={`Run scenario: ${sc.title}`}
                    disabled={executing}
                    onClick={() => {
                      if (isComparing && selectedScenario && selectedScenario.id !== sc.id) {
                        setComparisonScenario(sc);
                      } else {
                        setSelectedScenario(sc);
                        void handleRunScenario(sc);
                      }
                    }}
                    className={`w-full text-left p-3.5 rounded-xl border cursor-pointer transition flex flex-col gap-2 disabled:opacity-60 ${
                      isSelected
                        ? 'bg-indigo-950/40 border-indigo-500 shadow-md ring-1 ring-indigo-500/40'
                        : isCompSelected
                        ? 'bg-teal-950/40 border-teal-500 shadow-md ring-1 ring-teal-500/40'
                        : 'bg-slate-900/90 border-slate-800 hover:border-slate-700 hover:bg-slate-850'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold text-white leading-snug">{sc.title}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider shrink-0 ${
                          isReplay
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                        }`}
                      >
                        {isReplay ? 'Bantwal Road Blockage' : 'Hypothetical What-If'}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                      {sc.description}
                    </p>
                    <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono mt-1">
                      <span>Map: Bantwal</span>
                      <span>{String(sc.parameters?.highway || 'main road').toUpperCase()}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Details & Runner Panel */}
          <div className="md:col-span-2 flex flex-col gap-4 bg-slate-950/50 p-5 rounded-xl border border-slate-800 overflow-y-auto max-h-[580px]">
            {selectedScenario ? (
              <>
                <div className="flex items-start justify-between flex-wrap gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-white">{selectedScenario.title}</h3>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          selectedScenario.category === 'road_closure'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                        }`}
                      >
                        {selectedScenario.category === 'road_closure'
                          ? 'Bantwal Road Blockage'
                          : 'Hypothetical What-If'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                      {selectedScenario.description}
                    </p>
                  </div>
                </div>

                {/* Parameters & Assumptions */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <div className="bg-slate-900 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400 font-semibold block mb-1">Scenario Parameters</span>
                    <pre className="text-[11px] font-mono text-slate-300 bg-slate-950 p-2 rounded overflow-x-auto">
                      {JSON.stringify(selectedScenario.parameters, null, 2)}
                    </pre>
                  </div>
                  <div className="bg-slate-900 p-3 rounded-lg border border-slate-800">
                    <span className="text-slate-400 font-semibold block mb-1">Honesty & Assumptions Statement</span>
                    <p className="text-[11px] text-slate-300 leading-relaxed italic">
                      {selectedScenario.assumptions_statement ||
                        'Model parameters assume simulated conditions for evaluation. Real-world emergency response must rely on physical field verification.'}
                    </p>
                  </div>
                </div>

                {/* Side-by-side comparison view if active */}
                {isComparing && comparisonScenario && (
                  <div className="border-t border-slate-800 pt-3 flex flex-col gap-2">
                    <h4 className="text-xs font-bold text-teal-300">
                      Comparison Target: {comparisonScenario.title}
                    </h4>
                    <p className="text-xs text-slate-400">{comparisonScenario.description}</p>
                    <div className="grid grid-cols-2 gap-3 text-[11px] font-mono bg-slate-900 p-3 rounded-lg border border-slate-800">
                      <div>
                        <strong className="text-indigo-400 block mb-1">{selectedScenario.title}:</strong>
                        <div>Map: Bantwal</div>
                        <div>Category: {selectedScenario.category}</div>
                        <div>Stock Level: {selectedScenario.parameters?.stock_pct ?? 100}%</div>
                      </div>
                      <div>
                        <strong className="text-teal-400 block mb-1">{comparisonScenario.title}:</strong>
                        <div>Map: Bantwal</div>
                        <div>Category: {comparisonScenario.category}</div>
                        <div>Stock Level: {comparisonScenario.parameters?.stock_pct ?? 100}%</div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Result or Run Trigger */}
                <div className="mt-auto border-t border-slate-800 pt-4 flex flex-col gap-3">
                  {error && (
                    <div className="bg-red-950/50 border border-red-800 p-3 rounded-lg text-xs text-red-200">
                      {error}
                    </div>
                  )}
                  {result && (
                    <div className="bg-emerald-950/40 border border-emerald-800/80 p-3 rounded-lg text-xs text-emerald-200 flex flex-col gap-1">
                      <div className="font-bold flex items-center justify-between">
                        <span>Road blocked · routes recalculated</span>
                        <span className="font-mono text-[10px] text-emerald-400">Bantwal network</span>
                      </div>
                      <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                        {isOffline ? 'Saved result · offline' : 'Live API run'}
                      </span>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1 text-[11px] text-emerald-100">
                        {scenarioHighlights(result).map((highlight) => <span key={highlight}>{highlight}</span>)}
                      </div>
                      {(result as unknown as Record<string, any>).honesty_label && (
                        <p className="pt-1 text-[10px] text-emerald-300/80">
                          {(result as unknown as Record<string, any>).honesty_label}
                        </p>
                      )}
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-3">
                    <button
                      disabled={executing}
                      onClick={() => handleRunScenario(selectedScenario)}
                      className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow-md transition disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {executing ? 'Blocking road and recalculating routes...' : 'Run road blockage live'}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-xs text-slate-400 p-6 text-center">
                Select a scenario from the left to inspect parameters and run evaluations.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
