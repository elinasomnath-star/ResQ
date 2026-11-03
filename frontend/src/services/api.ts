import type {
  EventRecord,
  ZoneData,
  EngineType,
  StockMode,
  SimulationResult,
  ClosureResult,
  AllocationRow,
  RouteFeature,
  StepRecord,
  EscalationRecord,
  User,
  UserRole,
  StockSweepRow,
  StockSweepThresholds,
  GaugeReading,
  Facility,
  FacilityStockSummary,
  Scenario,
  AdminOverrideItem,
  AdminOverrideResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function normalizeStepRecord(row: Record<string, any>): StepRecord {
  const finiteNumber = (...values: unknown[]) => {
    for (const value of values) {
      const parsed = typeof value === 'number' ? value : Number.parseFloat(String(value ?? ''));
      if (Number.isFinite(parsed)) return parsed;
    }
    return 0;
  };
  const closure = row.closure_active;
  return {
    ...row,
    event_date: String(row.event_date ?? ''),
    engine: String(row.engine ?? ''),
    step: finiteNumber(row.step),
    closure_active: closure === true || String(closure).toLowerCase() === 'true',
    min_zone_coverage_pct: finiteNumber(row.min_zone_coverage_pct, row.step_minimum_zone_coverage_pct),
    unmet_demand_pct: finiteNumber(row.unmet_demand_pct, row.step_unmet_demand_pct),
  };
}

// Offline salted hash verification for presentation gate
// Salt: "resq_presentation_gate_2026_"
// Hash of "resq_presentation_gate_2026_viewer2026" and "...operator2026"
async function sha256(message: string): Promise<string> {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

const OFFLINE_CREDENTIAL_HASHES: Record<string, { role: UserRole; hash: string }> = {
  viewer: {
    role: 'viewer',
    // SHA-256 of "resq_demo_salt_viewer2026"
    hash: '54b9ca04130b0f841053a34560ce3ba25f93e0a2601ce4b31571709c9afcfd4e',
  },
  operator: {
    role: 'operator',
    // SHA-256 of "resq_demo_salt_operator2026"
    hash: 'cde4c5ee5f66117c16a773f322a43edb54e24aeee9a0eb4df18098bd58560b14',
  },
};

class ResQApiClient {
  private token: string | null = null;
  private currentUser: User | null = null;
  private isOfflineMode: boolean = false;

  constructor() {
    const savedToken = sessionStorage.getItem('resq_token');
    const savedUser = sessionStorage.getItem('resq_user');
    const savedOffline = localStorage.getItem('resq_offline_mode');
    if (savedToken && savedUser) {
      this.token = savedToken;
      try {
        this.currentUser = JSON.parse(savedUser);
      } catch {
        this.currentUser = { username: 'operator', role: 'operator' };
      }
    } else {
      this.currentUser = null;
      this.token = null;
    }
    if (savedOffline === 'true') {
      this.isOfflineMode = true;
    }
    // Probe backend asynchronously to auto-connect if alive
    this.checkBackendHealth();
  }

  public async checkBackendHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        this.isOfflineMode = false;
        localStorage.setItem('resq_offline_mode', 'false');
        return true;
      }
    } catch {
      // Backend not reached, keep fallback
    }
    return false;
  }

  public setOfflineMode(enabled: boolean) {
    this.isOfflineMode = enabled;
    localStorage.setItem('resq_offline_mode', enabled ? 'true' : 'false');
  }

  public getOfflineMode(): boolean {
    return this.isOfflineMode;
  }

  public getCurrentUser(): User | null {
    return this.currentUser;
  }

  public async getMe(): Promise<User | null> {
    if (this.isOfflineMode) {
      return this.currentUser;
    }
    if (!this.token) {
      return this.currentUser;
    }
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: this.getHeaders(),
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        this.currentUser = { username: data.username, role: data.role };
        sessionStorage.setItem('resq_user', JSON.stringify(this.currentUser));
        return this.currentUser;
      }
    } catch {
      // Return cached
    }
    return this.currentUser;
  }

  public async login(username: string, password: string): Promise<User> {
    // If explicitly in offline mode, verify via salted hash
    if (this.isOfflineMode) {
      return this.verifyOfflineLogin(username, password);
    }

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail?.message || 'Invalid username or password.');
      }

      const data = await res.json();
      this.token = data.access_token;
      this.currentUser = { username: data.username, role: data.role };
      sessionStorage.setItem('resq_token', data.access_token);
      sessionStorage.setItem('resq_user', JSON.stringify(this.currentUser));
      return this.currentUser;
    } catch (err: any) {
      // Fallback: if server is unreachable, try offline login and notify
      if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
        console.warn('Backend API unreachable. Falling back to offline demo presentation gate.');
        this.setOfflineMode(true);
        return this.verifyOfflineLogin(username, password);
      }
      throw err;
    }
  }

  private async verifyOfflineLogin(username: string, password: string): Promise<User> {
    const cred = OFFLINE_CREDENTIAL_HASHES[username];
    if (!cred) {
      throw new Error('Invalid username or password.');
    }
    const computedHash = await sha256(`resq_demo_salt_${password}`);
    if (computedHash !== cred.hash) {
      throw new Error('Invalid username or password.');
    }
    this.currentUser = { username, role: cred.role };
    this.token = 'demo_offline_token_' + username;
    sessionStorage.setItem('resq_token', this.token);
    sessionStorage.setItem('resq_user', JSON.stringify(this.currentUser));
    return this.currentUser;
  }

  public async logout(): Promise<void> {
    if (!this.isOfflineMode && this.token) {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      }).catch(() => {});
    }
    this.token = null;
    this.currentUser = null;
    sessionStorage.removeItem('resq_token');
    sessionStorage.removeItem('resq_user');
  }

  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.token && !this.token.startsWith('demo_offline_token_')) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }
    return headers;
  }

  public async getEvents(): Promise<EventRecord[]> {
    if (this.isOfflineMode) {
      const res = await fetch('/data/events.json');
      const data = await res.json();
      return data.events;
    }
    try {
      const res = await fetch(`${API_BASE}/events`);
      if (!res.ok) throw new Error('API events unavailable');
      const data = await res.json();
      return data.events;
    } catch {
      const res = await fetch('/data/events.json');
      const data = await res.json();
      return data.events;
    }
  }

  public async getZones(eventDate: string = '2024-07-31'): Promise<ZoneData[]> {
    const addMapReferenceFields = async (zones: ZoneData[]): Promise<ZoneData[]> => {
      try {
        const response = await fetch(`/data/zones_${eventDate}.json`);
        if (!response.ok) return zones;
        const snapshot = await response.json();
        const references = new Map<string, any>((snapshot.zones || []).map((zone: any) => [zone.zone_id, zone]));
        return zones.map((zone) => {
          const reference = references.get(zone.zone_id);
          return {
            ...zone,
            centroid_lat: zone.centroid_lat ?? reference?.centroid_lat,
            centroid_lon: zone.centroid_lon ?? reference?.centroid_lon,
            grid_row: zone.grid_row ?? reference?.grid_row,
            grid_column: zone.grid_column ?? reference?.grid_column,
          };
        });
      } catch {
        return zones;
      }
    };
    if (this.isOfflineMode) {
      const res = await fetch(`/data/zones_${eventDate}.json`);
      const data = await res.json();
      return data.zones;
    }
    try {
      const res = await fetch(`${API_BASE}/zones?event=${eventDate}`);
      if (!res.ok) throw new Error('API zones unavailable');
      const data = await res.json();
      return addMapReferenceFields(data.zones || []);
    } catch {
      const res = await fetch(`/data/zones_${eventDate}.json`);
      const data = await res.json();
      return data.zones;
    }
  }

  public async simulate(
    eventDateOrOpts: string | { event_date: string; engine: EngineType; stock_mode?: StockMode; stock_pct?: number },
    engine?: EngineType,
    stockMode?: StockMode
  ): Promise<SimulationResult> {
    const eventDate = typeof eventDateOrOpts === 'string' ? eventDateOrOpts : eventDateOrOpts.event_date;
    const resolvedEngine = typeof eventDateOrOpts === 'string' ? (engine || 'MILP') : eventDateOrOpts.engine;
    const resolvedStockMode = typeof eventDateOrOpts === 'string' ? (stockMode || 'configured') : (eventDateOrOpts.stock_mode || 'configured');
    const stockPct = typeof eventDateOrOpts === 'string' ? undefined : eventDateOrOpts.stock_pct;

    if (this.isOfflineMode) {
      if (stockPct != null) {
        throw new Error('Percentage-based allocation runs require the API; offline snapshots use fixed inventory pools.');
      }
      return this.offlineSimulate(eventDate, resolvedEngine, resolvedStockMode);
    }
    const res = await fetch(`${API_BASE}/simulate`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ event: eventDate, engine: resolvedEngine, stock_mode: resolvedStockMode, stock_pct: stockPct }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail?.message || `Simulation solve failed (${res.status})`);
    }
    const data = await res.json();
    // Fetch the generated allocations. A failed live call must remain visible;
    // silently substituting an offline snapshot makes the closure action fail
    // later with an opaque offline_run_* error.
    const allocRes = await this.getAllocations(data.run_id);
    data.allocations = allocRes.allocations;
    return data;
  }

  private async offlineSimulate(
    eventDate: string,
    engine: EngineType,
    stockMode: StockMode
  ): Promise<SimulationResult> {
    if (stockMode === 'entered') {
      throw new Error('Operator-entered inventory requires the API backend; offline mode has no saved field stock for allocation.');
    }
    const matrixPath = stockMode === 'simulated'
      ? `/data/allocation_matrix_simulated_${eventDate}.json`
      : `/data/allocation_matrix_${eventDate}.json`;
    const matrixRes = await fetch(matrixPath);
    if (!matrixRes.ok) throw new Error(`No ${stockMode} allocation snapshot is available for ${eventDate}.`);
    const allRows: any[] = await matrixRes.json();
    const engineMap: Record<string, string> = {
      MILP: 'MILP',
      LinUCB: 'LinUCB_contextual_bandit',
      proportional: 'naive_proportional_baseline',
    };
    const targetEngine = engineMap[engine] || engine;
    const filteredRows = allRows
      .filter((r) => r.engine === targetEngine)
      .map((r) => ({
        zone_id: r.zone_id,
        zone_name: r.zone_name,
        resource: r.resource,
        estimated_need: parseInt(r.estimated_need),
        allocated: parseInt(r.allocated),
        unmet: parseInt(r.unmet),
        unmet_pct: parseFloat(r.unmet_pct),
      }));

    const totalNeed = filteredRows.reduce((sum, row) => sum + row.estimated_need, 0);
    const totalUnmet = filteredRows.reduce((sum, row) => sum + row.unmet, 0);
    const avgUnmet = totalNeed ? (totalUnmet / totalNeed) * 100 : 0;

    return {
      run_id: `offline_run_${eventDate}_${engine}_${stockMode}`,
      event: eventDate,
      engine,
      stock_mode: stockMode,
      inventory_basis:
        stockMode === 'configured'
          ? 'assumed_inventory: config/region.yaml prototype_inventory'
          : 'assumed_inventory: demo/adequate_supply_summary.csv pooled simulated stock',
      hard_fairness_target_status: stockMode === 'configured' ? 'Configured inventory scenario' : 'Pooled simulated inventory scenario',
      summary: {
        engine,
        aggregate_unmet_demand_pct: `${avgUnmet.toFixed(2)}%`,
        hard_fairness_target_status: stockMode === 'configured' ? 'Configured inventory scenario' : 'Pooled simulated inventory scenario',
      },
      allocations: filteredRows,
    };
  }

  public async getAllocations(runId: string): Promise<{
    allocations: AllocationRow[];
    available_inventory?: { food_rations: number; water_liters: number; medical_kits: number };
  }> {
    if (this.isOfflineMode || runId.startsWith('offline_run_')) {
      const parts = runId.split('_');
      const eventDate = parts[2] || '2019-08-10';
      const engine = (parts[3] as EngineType) || 'MILP';
      const stockMode = (parts[4] as StockMode) || 'configured';
      const sim = await this.offlineSimulate(eventDate, engine, stockMode);
      return { allocations: sim.allocations || [] };
    }
    const res = await fetch(`${API_BASE}/allocation/${runId}`, {
      headers: this.getHeaders(),
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Allocations unavailable');
    return res.json();
  }

  public async rerouteRoadScenario(scenarioId: string): Promise<{
    scenario_id: string;
    blocked_road: string;
    blocked_roads: string[];
    closure_points: [number, number][];
    routing_origin_ids: string[];
    route_count: number;
    zone_routes: Array<{ zone_id: string; status: string; delivery_mode: 'road' | 'secondary' | 'none' }>;
    routes: RouteFeature[];
  }> {
    if (this.currentUser?.role !== 'operator') {
      throw new Error('Operator role required to block roads and reroute.');
    }
    if (this.isOfflineMode) {
      throw new Error('Connect the ResQ API to block this Bantwal road and calculate live detours.');
    }
    const res = await fetch(`${API_BASE}/scenario-reroutes`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ scenario_id: scenarioId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = typeof err.detail === 'string' ? err.detail : err.detail?.message;
      if (res.status === 404 && detail === 'Not Found') {
        throw new Error('The running ResQ API is outdated. Restart or rebuild the backend to enable fast road rerouting.');
      }
      throw new Error(detail || `Road scenario rerouting failed (HTTP ${res.status}).`);
    }
    return res.json();
  }

  public async applyClosure(
    runIdOrOpts: string | { event_date?: string; run_id?: string; corridor?: string; action?: string },
    closureId?: string
  ): Promise<ClosureResult> {
    const runId = typeof runIdOrOpts === 'string' ? runIdOrOpts : (runIdOrOpts.run_id || `offline_run_${runIdOrOpts.event_date || '2024-07-31'}_MILP_configured`);
    const resolvedClosureId = closureId || (typeof runIdOrOpts === 'object' ? runIdOrOpts.corridor : undefined) || 'BC_Road_closure';

    if (this.currentUser?.role !== 'operator') {
      throw new Error('Operator role required to apply closures or reroute roads.');
    }

    if (this.isOfflineMode || runId.startsWith('offline_run_')) {
      throw new Error('Closure re-solving requires the API and cached road graph; offline replay is read-only.');
    }

    const res = await fetch(`${API_BASE}/closures`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ run_id: runId, closure_id: resolvedClosureId }),
    });
    if (res.status === 403) {
      throw new Error('Operator role required to apply road closures.');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail?.message || 'Closure benchmark failed');
    }
    const result = await res.json();
    return { ...result, steps: (result.steps || []).map(normalizeStepRecord) };
  }

  public async getRoutes(eventDate: string = '2024-07-31', runId?: string): Promise<RouteFeature[]> {
    if (this.isOfflineMode || !runId || runId.startsWith('offline_run_')) {
      const res = await fetch(`/data/bantwal_routes_${eventDate}.geojson`);
      const data = await res.json();
      return data.features || [];
    }
    const res = await fetch(`${API_BASE}/routes/${runId}`, {
      headers: this.getHeaders(),
      credentials: 'include',
    });
    if (!res.ok) throw new Error(`Routes unavailable for run ${runId} (${res.status})`);
    const data = await res.json();
    // Once a live run exists, never disguise an API failure with a stale snapshot.
    return (data.routes || []).map((r: any) => ({
      type: 'Feature',
      geometry: r.geometry || null,
      properties: r,
    }));
  }

  public async getRouteGeometries(eventDate: string = '2024-07-31', runId?: string): Promise<RouteFeature[]> {
    return this.getRoutes(eventDate, runId);
  }

  public async getEscalations(eventDate: string = '2024-07-31', runId?: string, stockMode: StockMode = 'configured'): Promise<EscalationRecord[]> {
    if (this.isOfflineMode || !runId || runId.startsWith('offline_run_')) {
      const mode = runId?.startsWith('offline_run_') ? (runId.split('_')[4] as StockMode) || stockMode : stockMode;
      const fileName = mode === 'simulated' ? `escalation_log_simulated_${eventDate}.json` : `escalation_log_${eventDate}.json`;
      const res = await fetch(`/data/${fileName}`);
      const rows: any[] = await res.json();
      return rows.map((r) => ({
        ...r,
        step: parseInt(r.step),
        threshold: parseFloat(r.threshold),
        transfer_count: parseInt(r.transfer_count || '0'),
        min_zone_coverage_before_pct: r.min_zone_coverage_before_pct
          ? parseFloat(r.min_zone_coverage_before_pct)
          : null,
        min_zone_coverage_after_pct: r.min_zone_coverage_after_pct
          ? parseFloat(r.min_zone_coverage_after_pct)
          : null,
        shortfall_by_resource: typeof r.shortfall_by_resource === 'string' ? JSON.parse(r.shortfall_by_resource) : r.shortfall_by_resource,
        remaining_inventory: typeof r.remaining_inventory === 'string' ? JSON.parse(r.remaining_inventory) : r.remaining_inventory,
        remaining_unmet_demand: typeof r.remaining_unmet_demand === 'string' ? JSON.parse(r.remaining_unmet_demand) : r.remaining_unmet_demand,
      }));
    }
    try {
      const res = await fetch(`${API_BASE}/escalations/${runId}`, {
        headers: this.getHeaders(),
        credentials: 'include',
      });
      if (!res.ok) throw new Error('Escalations unavailable');
      const data = await res.json();
      return data.escalations;
    } catch {
      const res = await fetch(`/data/escalation_log_${eventDate}.json`);
      const rows: any[] = await res.json();
      return rows;
    }
  }

  public async getSteps(eventDate: string = '2024-07-19', stockMode: StockMode = 'configured'): Promise<StepRecord[]> {
    const path = stockMode === 'simulated' ? `/data/steps_simulated_${eventDate}.json` : `/data/steps_${eventDate}.json`;
    const res = await fetch(path);
    const rows: any[] = await res.json();
    return rows.map(normalizeStepRecord);
  }

  public async getStepResults(eventDate: string = '2024-07-19', stockMode: StockMode = 'configured'): Promise<StepRecord[]> {
    return this.getSteps(eventDate, stockMode);
  }

  public async getGeoLayer(name: 'analysis_zones' | 'river' | 'simplified_roads' | 'warehouses'): Promise<any> {
    const res = await fetch(`/data/${name}.geojson`);
    return res.json();
  }

  public async getClosures(eventDate: string): Promise<any> {
    const res = await fetch(`/data/closures_${eventDate}.geojson`);
    return res.json();
  }

  public async getAdequateSupplySummary(): Promise<any[]> {
    const res = await fetch(`/data/adequate_supply_summary.json`);
    return res.json();
  }

  public async adminOverride(
    runId: string,
    zoneId: string,
    resource: string,
    boostAmount: number,
    reason: string
  ): Promise<any> {
    if (this.currentUser?.role !== 'operator') {
      throw new Error('Operator role required to apply an admin override.');
    }
    if (this.isOfflineMode) {
      throw new Error('Allocation overrides require the API backend; offline mode is read-only.');
    }
    const res = await fetch(`${API_BASE}/admin/override`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
      body: JSON.stringify({
        run_id: runId,
        zone_id: zoneId,
        resource,
        boost_amount: boostAmount,
        reason,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail?.message || 'Override failed');
    }
    return res.json();
  }

  public async getSweep(eventDate: string): Promise<StockSweepRow[]> {
    try {
      const res = await fetch(`/data/stock_sweep_${eventDate}.json`);
      if (res.ok) {
        const data = await res.json();
        const engineNames: Record<string, EngineType> = {
          MILP: 'MILP',
          LinUCB_contextual_bandit: 'LinUCB',
          naive_proportional_baseline: 'proportional',
        };
        return (data.records || data.rows || []).map((row: any) => ({
          ...row,
          engine: engineNames[row.engine] || row.engine,
          unmet_demand_pct: Number(row.aggregate_unmet_demand_pct ?? row.unmet_demand_pct),
          unmet_demand_min_pct: Number(row.aggregate_unmet_demand_min ?? row.unmet_demand_min_pct),
          unmet_demand_max_pct: Number(row.aggregate_unmet_demand_max ?? row.unmet_demand_max_pct),
          min_zone_coverage_pct: Number(row.minimum_zone_coverage_pct ?? row.min_zone_coverage_pct),
          min_zone_cov_min: Number(row.minimum_zone_coverage_min ?? row.min_zone_cov_min),
          min_zone_cov_max: Number(row.minimum_zone_coverage_max ?? row.min_zone_cov_max),
          weighted_service_score: Number(row.weighted_service_score),
          zone_coverage_vector: Array.isArray(row.zone_coverage_vector) ? row.zone_coverage_vector.map((n: number) => Number(n) * 100) : [],
        }));
      }
    } catch {
      // If offline snapshots are unavailable, fall through to the API grid.
    }
    if (this.isOfflineMode) return [];
    const levels = Array.from({ length: 29 }, (_, i) => 10 + i * 5);
    const results = await Promise.all(levels.map(async (stockPct) => {
      const res = await fetch(`${API_BASE}/sweep?event=${eventDate}&stock_pct=${stockPct}`, {
        headers: this.getHeaders(), credentials: 'include',
      });
      if (!res.ok) return [];
      const data = await res.json();
      return data.records || [];
    }));
    return results.flat().map((row: any) => ({
      ...row,
      engine: ({ MILP: 'MILP', LinUCB_contextual_bandit: 'LinUCB', naive_proportional_baseline: 'proportional' } as Record<string, EngineType>)[row.engine] || row.engine,
      unmet_demand_pct: Number(row.aggregate_unmet_demand_pct ?? row.unmet_demand_pct),
      unmet_demand_min_pct: Number(row.aggregate_unmet_demand_min ?? row.unmet_demand_min_pct),
      unmet_demand_max_pct: Number(row.aggregate_unmet_demand_max ?? row.unmet_demand_max_pct),
      min_zone_coverage_pct: Number(row.minimum_zone_coverage_pct ?? row.min_zone_coverage_pct),
      min_zone_cov_min: Number(row.minimum_zone_coverage_min ?? row.min_zone_cov_min),
      min_zone_cov_max: Number(row.minimum_zone_coverage_max ?? row.min_zone_cov_max),
      zone_coverage_vector: Array.isArray(row.zone_coverage_vector) ? row.zone_coverage_vector.map((n: number) => Number(n) * 100) : [],
    }));
  }

  public async getSweepThresholds(): Promise<Record<string, StockSweepThresholds>> {
    const normalize = (thresholds: Record<string, any>) => Object.fromEntries(Object.entries(thresholds).map(([event, raw]: [string, any]) => [event, {
      event_date: raw.event_date || event,
      smallest_stock_pct_for_40pct_floor: Number(raw.smallest_stock_pct_for_40pct_floor ?? raw.smallest_stock_pct_for_40pct_floor_feasible),
      stock_pct_unmet_demand_sub_10pct: Number(raw.stock_pct_unmet_demand_sub_10pct ?? raw.stock_pct_unmet_demand_below_10pct),
      linucb_collapse_below_1pct_stock_pct: Number(raw.linucb_collapse_below_1pct_stock_pct ?? raw.stock_pct_linucb_collapse_below_1pct),
    }]));
    if (!this.isOfflineMode) {
      try {
        const res = await fetch(`${API_BASE}/sweep/summary`, {
          headers: this.getHeaders(),
          credentials: 'include',
        });
        if (res.ok) {
          const data = await res.json();
          const thresholds = data.thresholds || data.events || data;
          return normalize(thresholds);
        }
      } catch {
        // Fallback
      }
    }
    const res = await fetch(`/data/stock_sweep_thresholds.json`);
    const data = await res.json();
    const thresholds = data.thresholds || data.events || data;
    return normalize(thresholds);
  }

  public async getGaugeReadings(eventDate?: string): Promise<GaugeReading[]> {
    const normalize = (row: any): GaugeReading => {
      const waterLevel = Number(row.water_level_m);
      const dangerLevel = Number(row.danger_mark_m ?? row.danger_level_m ?? 9.0);
      const warningLevel = Number(row.warning_level_m ?? row.warning_mark_m ?? 8.0);
      const readingType = String(row.reading_type ?? '').toLowerCase();
      const peakValue = row.is_peak_reading;
      return {
        ...row,
        event_date: String(row.event_date ?? eventDate ?? ''),
        reading_timestamp_utc: String(row.reading_timestamp_utc ?? row.timestamp ?? ''),
        water_level_m: waterLevel,
        danger_mark_m: dangerLevel,
        warning_level_m: warningLevel,
        distance_above_danger_m: waterLevel - dangerLevel,
        gauge_station: String(row.gauge_station ?? row.river_gauge ?? 'Bantwal'),
        cwc_station_code: String(row.cwc_station_code ?? ''),
        reporting_agency: String(row.reporting_agency ?? 'CWC / sourced event record'),
        source_document_title: String(row.source_document_title ?? row.notes ?? 'Gauge stage record'),
        source_url: String(row.source_url ?? ''),
        is_peak_reading: peakValue === true || String(peakValue).toLowerCase() === 'true' || readingType === 'peak',
        notes: String(row.notes ?? ''),
      };
    };

    if (!this.isOfflineMode) {
      try {
        const url = eventDate ? `${API_BASE}/data/gauge-readings?event_date=${eventDate}` : `${API_BASE}/data/gauge-readings`;
        const res = await fetch(url, {
          headers: this.getHeaders(),
          credentials: 'include',
        });
        if (res.ok) {
          const data = await res.json();
          const rows = Array.isArray(data) ? data : data.readings;
          if (Array.isArray(rows)) {
            return rows.filter((row: any) => !eventDate || row.event_date === eventDate).map(normalize);
          }
        }
      } catch {
        // Fallback
      }
    }
    const res = await fetch(`/data/gauge_readings.csv`);
    const text = await res.text();
    const parseCsvLine = (line: string): string[] => {
      const cells: string[] = [];
      let cell = '';
      let quoted = false;
      for (let i = 0; i < line.length; i += 1) {
        const char = line[i];
        if (char === '"' && line[i + 1] === '"' && quoted) { cell += '"'; i += 1; }
        else if (char === '"') quoted = !quoted;
        else if (char === ',' && !quoted) { cells.push(cell); cell = ''; }
        else cell += char;
      }
      cells.push(cell);
      return cells;
    };
    const lines = text.trim().split(/\r?\n/);
    const headers = parseCsvLine(lines[0]).map((h) => h.trim());
    const readings: GaugeReading[] = [];
    for (let i = 1; i < lines.length; i++) {
      const parts = parseCsvLine(lines[i]);
      if (parts.length >= headers.length) {
        const obj: any = {};
        headers.forEach((h, idx) => {
          obj[h] = parts[idx]?.trim();
        });
        if (!eventDate || obj.event_date === eventDate) {
          readings.push(normalize(obj));
        }
      }
    }
    return readings;
  }

  public async getFacilities(): Promise<Facility[]> {
    if (!this.isOfflineMode) {
      try {
        const res = await fetch(`${API_BASE}/facilities`, {
          headers: this.getHeaders(),
          credentials: 'include',
        });
        if (res.ok) {
          const data = await res.json();
          return Array.isArray(data) ? data : (data.facilities || []);
        }
      } catch {
        // Fallback
      }
    }
    const res = await fetch(`/data/facilities.json`);
    const data = await res.json();
    return data;
  }

  public async updateFacilityStock(
    facilityId: string,
    stock: { resource: string; quantity: number; unit?: string; note?: string }[]
  ): Promise<any> {
    if (this.currentUser?.role !== 'operator') {
      throw new Error('Operator role required to edit facility inventory.');
    }
    if (this.isOfflineMode) {
      throw new Error('Facility stock updates require the API backend; offline mode is read-only.');
    }
    const res = await fetch(`${API_BASE}/facilities/${facilityId}/stock`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
      body: JSON.stringify({ stock }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail?.message || 'Failed to update stock');
    }
    return res.json();
  }

  public async getStockSummary(): Promise<FacilityStockSummary> {
    if (!this.isOfflineMode) {
      try {
        const res = await fetch(`${API_BASE}/stock/summary`, {
          headers: this.getHeaders(),
          credentials: 'include',
        });
        if (res.ok) return res.json();
      } catch {
        // Fallback
      }
    }
    return {
      totals: {
        food_rations: { quantity: 0, unit: 'rations', entered_count: 0, assumed_count: 0 },
        water_liters: { quantity: 0, unit: 'liters', entered_count: 0, assumed_count: 0 },
        medical_kits: { quantity: 0, unit: 'kits', entered_count: 0, assumed_count: 0 },
      },
      stale_count: 0,
      total_facilities: 0,
      unroutable_facilities_count: 0,
      mode_status: 'Facility stock is unavailable in offline mode. Run an allocation using configured or simulated assumed inventory.',
    };
  }

  public async resetStockToAssumed(): Promise<any> {
    if (this.currentUser?.role !== 'operator') {
      throw new Error('Operator role required to reset stock.');
    }
    if (this.isOfflineMode) {
      throw new Error('Resetting facility stock requires the API backend.');
    }
    const res = await fetch(`${API_BASE}/stock/reset-to-assumed`, {
      method: 'POST',
      headers: this.getHeaders(),
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Reset failed');
    return res.json();
  }

  public async getScenarios(): Promise<Scenario[]> {
    const normalizeScenarios = (rows: any[]): Scenario[] => rows
      .filter((scenario) => Boolean(scenario.closure_id))
      .map((scenario) => ({
        ...scenario,
        category: 'road_closure' as const,
      }));
    const res = await fetch(`/data/scenarios.json`);
    const data = await res.json();
    return normalizeScenarios(data.scenarios || data);
  }

  public async applyAllocationOverride(
    runId: string,
    overrides: AdminOverrideItem[]
  ): Promise<AdminOverrideResponse> {
    if (this.currentUser?.role !== 'operator') {
      throw new Error('Operator role required to apply manual allocation override.');
    }
    if (!this.isOfflineMode) {
      const res = await fetch(`${API_BASE}/allocation/override`, {
        method: 'POST',
        headers: this.getHeaders(),
        credentials: 'include',
        body: JSON.stringify({
          run_id: runId,
          overrides: overrides.map((item) => ({ zone_id: item.zone_id, resource: item.resource, new_allocated: item.allocated })),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail?.message || err.detail || 'Override rejected');
      }
      return res.json();
    }

    throw new Error('Allocation overrides require the API backend; offline mode is read-only.');
  }
}

export const api = new ResQApiClient();
