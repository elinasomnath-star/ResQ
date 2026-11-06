import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from '../components/Navbar';
import { LeftRail } from '../components/LeftRail';
import { MapConsole } from '../components/MapConsole';
import { InventoryPanel } from '../components/InventoryPanel';
import { StepTimeline } from '../components/StepTimeline';
import { RightDrawer } from '../components/RightDrawer';
import { CompareView } from '../components/CompareView';
import { EscalationModal } from '../components/EscalationModal';
import { AboutModal } from '../components/AboutModal';
import { AdminOverrideModal } from '../components/AdminOverrideModal';
import { ScarcitySlider } from '../components/ScarcitySlider';
import { ScarcityChart } from '../components/ScarcityChart';
import { GaugeRewind } from '../components/GaugeRewind';
import { ScenarioDeck } from '../components/ScenarioDeck';
import { ShelterInventory } from '../components/ShelterInventory';
import { FieldLogsModal } from '../components/FieldLogsModal';
import '../styles/ConsoleOverlays.css';

import type {
  User,
  EventRecord,
  EngineType,
  StockMode,
  ZoneData,
  AllocationRow,
  RouteFeature,
  StepRecord,
  EscalationRecord,
  StockSweepRow,
  StockSweepThresholds,
  Scenario,
} from '../types';
import { api } from '../services/api';

interface ConsoleViewProps {
  user: User | null;
  onLogout: () => void;
  onToggleRole?: () => void;
  onNavigateHome?: () => void;
  offlineMode: boolean;
  onToggleOffline: () => void;
}

export const ConsoleView: React.FC<ConsoleViewProps> = ({
  user,
  onLogout,
  onToggleRole,
  onNavigateHome,
  offlineMode,
  onToggleOffline,
}) => {
  // Navigation / Selection State
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<string>('2024-07-31');
  const [selectedEngine, setSelectedEngine] = useState<EngineType>('MILP');
  const [stockMode, setStockMode] = useState<StockMode>('configured');

  // Scarcity & Sweep State
  // Begin near the modeled <10% unmet-demand point so the engine tradeoff is visible;
  // this is a stock-sweep scenario, not the configured inventory baseline.
  const [stockPct, setStockPct] = useState<number>(90);
  const [sweepRows, setSweepRows] = useState<StockSweepRow[]>([]);
  const [sweepThresholds, setSweepThresholds] = useState<Record<string, StockSweepThresholds>>({});
  const [isChartOpen, setIsChartOpen] = useState(false);

  // Analytical Data State
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [selectedZone, setSelectedZone] = useState<ZoneData | null>(null);
  const [allocations, setAllocations] = useState<AllocationRow[]>([]);
  const [routes, setRoutes] = useState<RouteFeature[]>([]);
  const [stepsData, setStepsData] = useState<StepRecord[]>([]);
  const [escalations, setEscalations] = useState<EscalationRecord[]>([]);

  // Simulation & Timeline State
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [isClosureApplied, setIsClosureApplied] = useState<boolean>(false);
  const [appliedClosureId, setAppliedClosureId] = useState<string | null>(null);
  const [closureRouteChangeCount, setClosureRouteChangeCount] = useState<number | null>(null);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [allocationProgress, setAllocationProgress] = useState<number | null>(null);
  const [allocationRunKey, setAllocationRunKey] = useState(0);
  const [allocationPaused, setAllocationPaused] = useState(false);
  const [allocationSpeed, setAllocationSpeed] = useState(1);
  const [currentRunId, setCurrentRunId] = useState<string>('');
  const [stockTotals, setStockTotals] = useState({ food_rations: 0, water_liters: 0, medical_kits: 0 });
  const [runInventory, setRunInventory] = useState<{ food_rations: number; water_liters: number; medical_kits: number } | null>(null);
  const [closureDetourInfo, setClosureDetourInfo] = useState<{
    beforeDistanceKm: number;
    afterDistanceKm: number;
  } | null>(null);

  // Reveal the completed API allocation as a paced, zone-by-zone process.
  useEffect(() => {
    if (isSimulating || allocationPaused || allocationProgress == null || allocationProgress >= zones.length) return;
    const timer = window.setTimeout(() => setAllocationProgress((value) =>
      value == null ? null : Math.min(zones.length, value + 1)), 420 / allocationSpeed);
    return () => window.clearTimeout(timer);
  }, [allocationProgress, zones.length, isSimulating, allocationPaused, allocationSpeed]);

  // Modals & Panels State
  const [isCompareOpen, setIsCompareOpen] = useState(false);
  const [isEscalationsOpen, setIsEscalationsOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isOverrideOpen, setIsOverrideOpen] = useState(false);
  const [isScenariosOpen, setIsScenariosOpen] = useState(false);
  const [isInventoryOpen, setIsInventoryOpen] = useState(false);
  const [isFieldLogsOpen, setIsFieldLogsOpen] = useState(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);

  // Load Initial Metadata (Events & Zones)
  useEffect(() => {
    let isMounted = true;
    const fetchMetadata = async () => {
      try {
        const evts = await api.getEvents();
        if (isMounted) {
          setEvents(evts);
          if (evts.length > 0 && !selectedEvent) {
            setSelectedEvent(evts[0].event_date);
          }
        }
      } catch (err) {
        console.error('Error fetching initial console data:', err);
      }
    };
    fetchMetadata();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    api.getZones(selectedEvent).then((eventZones) => { if (mounted) setZones(eventZones); })
      .catch((err) => console.error('Error loading selected event zones:', err));
    return () => { mounted = false; };
  }, [selectedEvent]);

  // Load Event-Specific Data (Routes, Steps, Allocations, Escalations)
  const loadEventData = useCallback(async (
    eventDate: string,
    runId?: string,
    allocationOverride?: AllocationRow[],
    stockModeOverride?: StockMode,
  ): Promise<RouteFeature[]> => {
    const dataStockMode = stockModeOverride ?? stockMode;
    try {
      const [routeFeatures, steps, escs] = await Promise.all([
        api.getRouteGeometries(eventDate, runId),
        dataStockMode === 'entered' || (runId && !runId.startsWith('offline_run_'))
          ? Promise.resolve([])
          : api.getStepResults(eventDate, dataStockMode),
        dataStockMode === 'entered' && (!runId || runId.startsWith('offline_run_')) ? Promise.resolve([]) : api.getEscalations(eventDate, runId, dataStockMode),
      ]);

      setRoutes(routeFeatures);
      setStepsData(steps);
      setEscalations(escs);

      // Load stock sweep curves & bisection thresholds
      try {
        const [swp, thres] = await Promise.all([
          api.getSweep(eventDate),
          api.getSweepThresholds(),
        ]);
        setSweepRows(swp);
        setSweepThresholds(thres);
      } catch (err) {
        console.warn('Sweep load warning:', err);
        setSweepRows([]);
        setSweepThresholds({});
      }

      const engineFileName: Record<EngineType, string> = {
        MILP: 'MILP', LinUCB: 'LinUCB_contextual_bandit', proportional: 'naive_proportional_baseline',
      };
      let allocationRows: AllocationRow[];
      let actualRunInventory: { food_rations: number; water_liters: number; medical_kits: number } | null = null;
      if (runId && !runId.startsWith('offline_run_') && !offlineMode) {
        const allocationResult = await api.getAllocations(runId);
        actualRunInventory = allocationResult.available_inventory || null;
        setRunInventory(actualRunInventory);
        allocationRows = allocationOverride || allocationResult.allocations;
      } else if (allocationOverride) {
        allocationRows = allocationOverride;
      } else if (dataStockMode === 'entered' && (!runId || runId.startsWith('offline_run_'))) {
        allocationRows = [];
      } else {
        const matrixPath = dataStockMode === 'simulated'
          ? `/data/allocation_matrix_simulated_${eventDate}.json`
          : `/data/allocation_matrix_${eventDate}.json`;
        const matrix = await fetch(matrixPath).then((r) => r.ok ? r.json() : []);
        allocationRows = matrix.filter((row: any) => row.engine === engineFileName[selectedEngine]).map((row: any) => ({
          zone_id: row.zone_id, zone_name: row.zone_name, resource: row.resource,
          estimated_need: Number(row.estimated_need), allocated: Number(row.allocated),
          unmet: Number(row.unmet), unmet_pct: Number(row.unmet_pct),
        }));
      }
      setAllocations(allocationRows);

      const metadataPath = dataStockMode === 'simulated'
        ? `/data/allocation_metadata_simulated_${eventDate}.json`
        : `/data/allocation_metadata_${eventDate}.json`;
      if (dataStockMode === 'entered') {
        const summary = await api.getStockSummary();
        setStockTotals({
          food_rations: Number(summary.totals.food_rations?.quantity ?? 0),
          water_liters: Number(summary.totals.water_liters?.quantity ?? 0),
          medical_kits: Number(summary.totals.medical_kits?.quantity ?? 0),
        });
      } else if (actualRunInventory) {
        setStockTotals(actualRunInventory);
      } else {
        const metadata = await fetch(metadataPath).then((r) => r.ok ? r.json() : null).catch(() => null);
        setStockTotals(metadata?.prototype_inventory_assumption || { food_rations: 0, water_liters: 0, medical_kits: 0 });
      }
      return routeFeatures;
    } catch (err) {
      console.error('Error loading event data:', err);
      // Do not leave the prior event/run's routes or allocations painted as current.
      setRoutes([]);
      setStepsData([]);
      setEscalations([]);
      setAllocations([]);
      return [];
    }
  }, [selectedEngine, offlineMode, stockMode]);

  useEffect(() => {
    if (selectedEvent) {
      loadEventData(selectedEvent);
    }
  }, [selectedEvent, loadEventData]);

  // Handle Simulation Run
  const handleRunSimulation = async () => {
    setIsSimulating(true);
    setSimulationError(null);
    setAllocationRunKey((key) => key + 1);
    setAllocationPaused(false);
    setAllocationProgress(0);
    setCurrentRunId('');
    setAllocations([]);
    setEscalations([]);
    setRunInventory(null);
    try {
      if (stockMode === 'entered') {
        const summary = await api.getStockSummary();
        const enteredStock = Object.values(summary.totals || {}).some((item) => Number(item.quantity) > 0);
        if (!enteredStock) {
          throw new Error('No entered stock is available. Open Field Logs and import a CSV before running this allocation.');
        }
      }
      const res = await api.simulate({
        event_date: selectedEvent,
        engine: selectedEngine,
        stock_mode: stockMode,
        ...(stockMode !== 'entered' && !offlineMode ? { stock_pct: stockPct } : {}),
      });
      if (res && res.run_id) {
        setCurrentRunId(res.run_id);
        setRunInventory(res.available_inventory || null);
        if (res.available_inventory) setStockTotals(res.available_inventory);
        setIsClosureApplied(false);
        setAppliedClosureId(null);
        setClosureRouteChangeCount(null);
        const baselineRoutes = await loadEventData(selectedEvent, res.run_id, res.allocations);
        if (!selectedZone) {
          const firstRoadRoute = baselineRoutes.find((route) => route.properties.delivery_mode === 'road');
          const routeZone = firstRoadRoute && zones.find((zone) => zone.zone_id === firstRoadRoute.properties.zone_id);
          if (routeZone) setSelectedZone(routeZone);
        }
      }
    } catch (err) {
      console.error('Simulation error:', err);
      setSimulationError(err instanceof Error ? err.message : 'Allocation could not be completed.');
      setAllocationProgress(null);
    } finally {
      setIsSimulating(false);
    }
  };

  const handleSelectScenario = async (scenario: Scenario) => {
    setSelectedZone(null);
    setRoutes([]);
    setIsClosureApplied(false);
    setAppliedClosureId(null);
    setClosureRouteChangeCount(null);
    setClosureDetourInfo(null);
    // Road blockage scenarios only recalculate routes. They skip allocation
    // simulation and the repeated-disruption benchmark to keep the response fast.
    setIsSimulating(true);
    try {
      const result = await api.rerouteRoadScenario(scenario.id);
      setRoutes(result.routes);
      setIsClosureApplied(true);
      setAppliedClosureId(result.scenario_id);
      setClosureRouteChangeCount(result.route_count);
      const baselineRoutes = result.routes;
      const firstRoadRoute = baselineRoutes.find((route) => route.properties.delivery_mode === 'road');
      const routeZone = firstRoadRoute && zones.find((zone) => zone.zone_id === firstRoadRoute.properties.zone_id);
      if (routeZone) setSelectedZone(routeZone);
    } finally {
      setIsSimulating(false);
    }
  };

  const selectedEngineKey: Record<EngineType, string> = {
    MILP: 'MILP', LinUCB: 'LinUCB_contextual_bandit', proportional: 'naive_proportional_baseline',
  };
  const allocationZoneIds = zones.map((zone) => zone.zone_id).filter((zoneId) => allocations.some((row) => row.zone_id === zoneId));
  const visibleZoneIds = new Set(allocationZoneIds.slice(0, allocationProgress ?? 0));
  const visibleAllocations = allocationProgress == null ? [] : allocations.filter((row) => visibleZoneIds.has(row.zone_id));
  const visibleShortageZones = new Set(visibleAllocations.filter((row) => Number(row.unmet) > 0).map((row) => row.zone_id));
  const visibleShortfallRows = visibleAllocations.filter((row) => Number(row.unmet) > 0);
  const visibleCoverageByZone = new Map<string, number>();
  let processNeed = 0;
  let processUnmet = 0;
  for (const row of visibleAllocations) {
    const need = Math.max(0, Number(row.estimated_need) || 0);
    const allocated = Math.max(0, Number(row.allocated) || 0);
    processNeed += need;
    processUnmet += Math.max(0, Number(row.unmet) || 0);
    const coverage = need > 0 ? Math.min(1, allocated / need) : 1;
    visibleCoverageByZone.set(row.zone_id, Math.min(visibleCoverageByZone.get(row.zone_id) ?? 1, coverage));
  }
  const processMinCoveragePct = visibleCoverageByZone.size
    ? Math.min(...visibleCoverageByZone.values()) * 100
    : 0;
  const processUnmetDemandPct = processNeed > 0 ? (processUnmet / processNeed) * 100 : 0;
  const inventoryStep = stepsData.find((step) => step.engine === selectedEngineKey[selectedEngine] && Number(step.step) === currentStep + 1);
  let remainingInventory: Record<string, number> = {};
  try {
    remainingInventory = typeof inventoryStep?.remaining_inventory === 'string'
      ? JSON.parse(inventoryStep.remaining_inventory)
      : (inventoryStep?.remaining_inventory || {});
  } catch { remainingInventory = {}; }
  const previousInventoryStep = currentStep > 0
    ? stepsData.find((step) => step.engine === selectedEngineKey[selectedEngine] && Number(step.step) === currentStep)
    : undefined;
  let previousInventory: Record<string, number> = { ...stockTotals };
  try {
    if (previousInventoryStep?.remaining_inventory) {
      previousInventory = typeof previousInventoryStep.remaining_inventory === 'string'
        ? JSON.parse(previousInventoryStep.remaining_inventory)
        : previousInventoryStep.remaining_inventory;
    }
  } catch { previousInventory = { ...stockTotals }; }
  const roundAllocation = {
    food_rations: Math.max(0, Number(previousInventory.food_rations ?? stockTotals.food_rations) - Number(remainingInventory.food_rations ?? stockTotals.food_rations)),
    water_liters: Math.max(0, Number(previousInventory.water_liters ?? stockTotals.water_liters) - Number(remainingInventory.water_liters ?? stockTotals.water_liters)),
    medical_kits: Math.max(0, Number(previousInventory.medical_kits ?? stockTotals.medical_kits) - Number(remainingInventory.medical_kits ?? stockTotals.medical_kits)),
  };
  // Live runs animate the selected engine's returned zone allocations, not
  // the old precomputed eight-round inventory snapshots.
  const hasRoundData = false;
  const totalAllocated = visibleAllocations.reduce((totals, row) => {
    if (row.resource in totals) totals[row.resource as keyof typeof totals] += Math.max(0, Number(row.allocated) || 0);
    return totals;
  }, { food_rations: 0, water_liters: 0, medical_kits: 0 });
  const resourcePoolRemaining = hasRoundData
    ? {
      food_rations: Number(remainingInventory.food_rations ?? stockTotals.food_rations),
      water_liters: Number(remainingInventory.water_liters ?? stockTotals.water_liters),
      medical_kits: Number(remainingInventory.medical_kits ?? stockTotals.medical_kits),
    }
    : {
      food_rations: Math.max(0, stockTotals.food_rations - totalAllocated.food_rations),
      water_liters: Math.max(0, stockTotals.water_liters - totalAllocated.water_liters),
      medical_kits: Math.max(0, stockTotals.medical_kits - totalAllocated.medical_kits),
    };
  const stepAllocation = hasRoundData ? roundAllocation : totalAllocated;

  // Selected Zone Route
  const selectedZoneRoute = selectedZone
    ? routes.find((r) => r.properties.zone_id === selectedZone.zone_id) || null
    : null;

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-ink-950 flex flex-col select-none">
      {/* Top Navigation */}
      <Navbar
        user={user}
        onLogout={onLogout}
        onToggleRole={onToggleRole}
        onNavigateHome={onNavigateHome}
        offlineMode={offlineMode}
        onToggleOffline={onToggleOffline}
        onOpenCompare={() => setIsCompareOpen(true)}
        onOpenEscalations={() => setIsEscalationsOpen(true)}
        onOpenAbout={() => setIsAboutOpen(true)}
        onOpenScenarios={() => setIsScenariosOpen(true)}
        onOpenInventory={() => setIsInventoryOpen(true)}
        onOpenOverride={() => setIsOverrideOpen(true)}
        alertCount={allocationProgress != null ? visibleShortageZones.size : escalations.length}
      />

      {/* Main Console Workspace */}
      <div className="relative flex-1 w-full h-[calc(100vh-57px)] overflow-hidden">
        {/* Full-Screen Map (Deck.gl & MapLibre) */}
        <MapConsole
          selectedEvent={selectedEvent}
          zones={zones}
          onSelectZone={setSelectedZone}
          selectedZoneId={selectedZone?.zone_id || null}
          routes={routes}
          coveragePreview={null}
          coveragePreviewStockPct={stockPct}
          isClosureActive={isClosureApplied}
          appliedClosureId={appliedClosureId}
          closureRouteChangeCount={closureRouteChangeCount}
          closureDetourInfo={closureDetourInfo}
          allocations={visibleAllocations}
        />

        {/* Left Rail — Sidebar panels */}
        <div
          className="console-left-rail absolute top-3 left-3 z-20 w-[268px] xl:w-[288px] flex flex-col gap-2 pointer-events-auto overflow-y-auto no-scrollbar"
          style={{ bottom: 'calc(194px + 12px + 10px)' }}
        >
          <LeftRail
            events={events}
            selectedEvent={selectedEvent}
            onSelectEvent={(evt) => {
              setSelectedEvent(evt);
              setSelectedZone(null);
              setRunInventory(null);
              setIsClosureApplied(false);
              setAppliedClosureId(null);
              setClosureRouteChangeCount(null);
              setClosureDetourInfo(null);
              setCurrentRunId('');
              setCurrentStep(0);
              setAllocationProgress(null);
            }}
            selectedEngine={selectedEngine}
            onSelectEngine={(engine) => {
              setSelectedEngine(engine);
              setRunInventory(null);
              setIsClosureApplied(false);
              setAppliedClosureId(null);
              setClosureRouteChangeCount(null);
              setCurrentRunId('');
              setAllocationProgress(null);
              setCurrentStep(0);
            }}
            stockMode={stockMode}
            onToggleStockMode={(mode) => {
              setStockMode(mode);
              setAllocations([]);
              setRoutes([]);
              setStepsData([]);
              setEscalations([]);
              setRunInventory(null);
              setCurrentRunId('');
              setIsClosureApplied(false);
              setAppliedClosureId(null);
              setClosureRouteChangeCount(null);
              setClosureDetourInfo(null);
              setCurrentStep(0);
              setAllocationProgress(null);
              setSimulationError(null);
            }}
            onOpenFieldLogs={() => setIsFieldLogsOpen(true)}
            onRunSimulation={handleRunSimulation}
            isSimulating={isSimulating}
            simulationError={simulationError}
          />
          <GaugeRewind eventDate={selectedEvent} />
        </div>

        {/* Separate Map Legend Box below sidebar — exactly same width, bottom aligned with Dynamic Allocation Replay */}
        <aside
          aria-label="Map Legend"
          className="map-legend-panel-sidebar absolute bottom-3 left-3 z-20 w-[268px] xl:w-[288px] glass-panel rounded-2xl p-3.5 pointer-events-auto shadow-2xl backdrop-blur-xl border border-white/15"
        >
          <div className="flex items-center justify-between mb-2.5 pb-1.5 border-b border-white/10">
            <span className="text-[12px] font-bold uppercase tracking-wider text-white font-heading">Map Legend</span>
            <span className="text-[10px] font-mono text-slate-300 font-semibold">Live layers</span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-200">
              <span className="flex items-center gap-2">
                <span className="legend-severity-inline" />
                <span className="font-medium">Zone severity</span>
              </span>
              <span className="text-[10px] text-slate-300 font-semibold">Low / Mid / High</span>
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-200">
              <span className="flex items-center gap-2">
                <span className="legend-route-inline" />
                <span className="font-medium">Road route</span>
              </span>
              <span className="text-[10px] text-accent-cyan font-bold">Active</span>
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-200">
              <span className="flex items-center gap-2">
                <span className="legend-secondary-inline" />
                <span className="font-medium">Secondary</span>
              </span>
              <span className="text-[10px] text-purple-300 font-bold">Unverified</span>
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-200">
              <span className="flex items-center gap-2">
                <span className="legend-closure-inline" />
                <span className="font-medium">Road closure</span>
              </span>
              <span className="text-[10px] text-rose-400 font-bold">Blocked</span>
            </div>
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-200">
              <span className="flex items-center gap-2">
                <span className="legend-facility-inline" />
                <span className="font-medium">Relief facility</span>
              </span>
              <span className="text-[10px] text-amber-300 font-bold">Shelter / Depot</span>
            </div>
          </div>
        </aside>

        {/* Top Right Resource Inventory: per-round allocation and remaining stock */}
        <div className="absolute top-3 right-3 z-20 w-72 sm:w-80 xl:w-[22rem] pointer-events-auto">
          <InventoryPanel
            key={allocationRunKey}
            foodRemaining={resourcePoolRemaining.food_rations}
            foodTotal={stockTotals.food_rations}
            waterRemaining={resourcePoolRemaining.water_liters}
            waterTotal={stockTotals.water_liters}
            medicalRemaining={resourcePoolRemaining.medical_kits}
            medicalTotal={stockTotals.medical_kits}
            stepAllocation={stepAllocation}
            stepNumber={currentStep + 1}
            hasRoundData={hasRoundData}
            processProgress={allocationProgress}
            processZoneCount={allocationZoneIds.length}
            shortageZoneCount={visibleShortageZones.size}
          />
        </div>
        {/* Bottom Center: Scarcity Sweeper + Step Timeline stacked */}
        <div className="console-bottom-overlays absolute bottom-3 z-20 flex flex-col items-center gap-2 pointer-events-none">
          {/* Scarcity Slider sits just above the step timeline */}
          <div className="w-full pointer-events-auto">
            <ScarcitySlider
              stockPct={stockPct}
              onChange={setStockPct}
              donorFloorThreshold={sweepThresholds[selectedEvent]?.smallest_stock_pct_for_40pct_floor ?? 40.6}
              linucbCollapseThreshold={sweepThresholds[selectedEvent]?.linucb_collapse_below_1pct_stock_pct ?? 10.0}
              onOpenChart={() => setIsChartOpen(true)}
              comparisonRows={sweepRows.filter((row) => Math.abs(row.stock_pct - stockPct) < 0.001)}
              selectedEngine={selectedEngine}
              disabled={offlineMode || stockMode === 'entered'}
              disabledMessage={offlineMode
                ? 'Live API needed to apply a stock percentage'
                : 'Entered stock is fixed; percentage is preview only'}
            />
          </div>

          {/* Step Timeline */}
          <div className="w-full pointer-events-auto">
            <StepTimeline
              currentStep={currentStep}
              totalSteps={8}
              onStepChange={setCurrentStep}
              stepsData={allocationProgress != null ? stepsData : []}
              isClosureApplied={isClosureApplied}
              processProgress={allocationProgress}
              processZoneCount={allocationZoneIds.length}
              processMinCoveragePct={processMinCoveragePct}
              processUnmetDemandPct={processUnmetDemandPct}
              processPaused={allocationPaused}
              processSpeed={allocationSpeed}
              onProcessPause={() => setAllocationPaused((paused) => !paused)}
              onProcessSpeedChange={setAllocationSpeed}
              onProcessStepChange={setAllocationProgress}
            />
          </div>
        </div>

        {/* Right Drawer (Zone Severity, Population, Need vs Allocated, Sparkline, Detour) */}
        {selectedZone && (
          <div className="absolute top-0 right-0 h-full z-30 pointer-events-auto">
            <RightDrawer
              key={`${selectedZone.zone_id}:${currentRunId}`}
              zone={selectedZone}
              onClose={() => setSelectedZone(null)}
              allocations={allocations.filter((a) => a.zone_id === selectedZone.zone_id)}
              route={selectedZoneRoute}
              userRole={user?.role}
              runId={currentRunId}
              offlineMode={offlineMode}
              onOverrideSuccess={(changes) => {
                const changedByKey = new Map(changes.map((change) => [`${change.zone_id}|${change.resource}`, change]));
                setAllocations((previous) => previous.map((allocation) => {
                  const change = changedByKey.get(`${allocation.zone_id}|${allocation.resource}`);
                  if (!change) return allocation;
                  const unmet = Math.max(0, change.estimated_need - change.new_allocated);
                  return {
                    ...allocation,
                    allocated: change.new_allocated,
                    unmet,
                    unmet_pct: change.new_unmet_pct,
                  };
                }));
              }}
              onSwitchToOperator={onToggleRole}
            />
          </div>
        )}

        {/* Compare View (Swipe-Slider Map, Small Multiples, Drawing Line Chart, Bento Grid) */}
        {isCompareOpen && (
          <CompareView
            onClose={() => setIsCompareOpen(false)}
            zones={zones}
            stepsData={stepsData}
            selectedEvent={selectedEvent}
          />
        )}

        {/* Scarcity Curves Modal */}
        {isChartOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
            <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-4xl p-6 relative">
              <button
                onClick={() => setIsChartOpen(false)}
                aria-label="Close Curves Modal"
                className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded"
              >
                ✕
              </button>
              <ScarcityChart
                data={sweepRows}
                activeStockPct={stockPct}
                eventDate={selectedEvent}
              />
            </div>
          </div>
        )}

        {/* Admin Override Modal (Operator only) */}
        <AdminOverrideModal
          isOpen={isOverrideOpen}
          onClose={() => setIsOverrideOpen(false)}
          runId={currentRunId}
          allocations={allocations}
          availableInventory={runInventory || stockTotals}
          offlineMode={offlineMode}
          user={user}
          onOverrideApplied={(newAllocations) => {
            setAllocations(newAllocations);
          }}
        />

        {/* Scenario Benchmark Deck Modal */}
        <ScenarioDeck
          isOpen={isScenariosOpen}
          onClose={() => setIsScenariosOpen(false)}
          onSelectScenario={handleSelectScenario}
        />

        {/* Shelter & Warehouse Inventory Modal */}
        <ShelterInventory
          isOpen={isInventoryOpen}
          onClose={() => setIsInventoryOpen(false)}
          user={user}
          offlineMode={offlineMode}
          onStockModeChanged={(mode) => {
            setStockMode(mode);
            setCurrentRunId('');
            setRunInventory(null);
            setAllocations([]);
            setIsClosureApplied(false);
            setAppliedClosureId(null);
            setClosureRouteChangeCount(null);
            void loadEventData(selectedEvent, undefined, undefined, mode);
          }}
        />

        <FieldLogsModal
          key={isFieldLogsOpen ? 'open' : 'closed'}
          isOpen={isFieldLogsOpen}
          onClose={() => setIsFieldLogsOpen(false)}
          offlineMode={offlineMode}
          user={user}
          onImported={async () => {
            setStockMode('entered');
            setRunInventory(null);
            setCurrentRunId('');
            setAllocations([]);
            setEscalations([]);
            setIsClosureApplied(false);
            setAppliedClosureId(null);
            setClosureRouteChangeCount(null);
            setAllocationProgress(null);
            setSimulationError(null);
            await loadEventData(selectedEvent, undefined, undefined, 'entered');
          }}
          onRunAllocation={handleRunSimulation}
        />

        {/* Escalation Alerts Feed & Transfer Arcs Modal */}
        {isEscalationsOpen && (
          <EscalationModal
            onClose={() => setIsEscalationsOpen(false)}
            escalations={escalations}
            selectedEvent={selectedEvent}
            isAllocationProcess={allocationProgress != null}
            allocationShortfalls={visibleShortfallRows}
            selectedEngine={selectedEngine}
          />
        )}

        {/* About & Limits Modal (Sources, Constraints, Implemented vs Planned, React Bits Attribution) */}
        <AboutModal
          isOpen={isAboutOpen}
          onClose={() => setIsAboutOpen(false)}
        />

      </div>
    </div>
  );
};

export default ConsoleView;
