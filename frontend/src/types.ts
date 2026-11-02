export type UserRole = 'viewer' | 'operator';

export interface User {
  username: string;
  role: UserRole;
}

export interface EventRecord {
  event_date: string;
  river_gauge: string;
  water_level_m: number;
  danger_mark_m?: number;
  warning_level_m?: number;
  affected_localities: string[];
  roads_blocked: string[];
  houses_affected: string;
  source_urls: string[];
}

export interface ZoneData {
  zone_id: string;
  zone_name: string;
  grid_row: number;
  grid_column: number;
  centroid_lat: number;
  centroid_lon: number;
  population_estimate: number;
  population_status?: string;
  population_year?: number;
  population_resolution?: string;
  population_density_per_km2: number;
  severity_score: number;
  severity_label?: string;
  sar_likelihood: number;
  sar_label?: string;
  antecedent_7day_rainfall_mm: number;
  estimated_affected_people: number;
  estimated_food_rations: number;
  estimated_water_liters: number;
  estimated_medical_kits: number;
}

export type EngineType = 'MILP' | 'LinUCB' | 'proportional';
export type StockMode = 'configured' | 'simulated' | 'entered';

export interface AllocationRow {
  zone_id: string;
  zone_name: string;
  resource: 'food_rations' | 'water_liters' | 'medical_kits' | string;
  estimated_need: number;
  allocated: number;
  unmet: number;
  unmet_pct: number;
}

export interface RouteFeature {
  type: string;
  geometry: {
    type: string;
    coordinates: any;
  } | null;
  properties: {
    zone_id: string;
    zone_name: string;
    status: string;
    road_status: string;
    secondary_status: string;
    delivery_mode: 'road' | 'secondary' | 'none';
    origin_id: string;
    road_distance_m: number | null;
    secondary_distance_km: number | null;
    secondary_payload_capacity_kg?: number;
    secondary_trip_count?: number;
    path_node_ids?: string;
  };
}

export interface StepRecord {
  step: string | number;
  event_date: string;
  engine: string;
  closure_active: string | boolean;
  min_zone_coverage_pct: number;
  unmet_demand_pct?: number;
  total_allocated?: number;
  stock_remaining_food?: number;
  stock_remaining_water?: number;
  stock_remaining_medical?: number;
  [key: string]: any;
}

export interface EscalationRecord {
  trigger_id: string;
  event_date: string;
  step: number;
  engine: string;
  threshold: number;
  resource_types_short: string;
  shortfall_by_resource: Record<string, number>;
  remaining_inventory: Record<string, number>;
  remaining_unmet_demand: Record<string, number>;
  affected_zone_ids: string;
  transfer_count: number;
  min_zone_coverage_before_pct: number | null;
  min_zone_coverage_after_pct: number | null;
}

export interface SimulationResult {
  run_id: string;
  event: string;
  engine: EngineType;
  stock_mode: StockMode;
  inventory_basis: string;
  hard_fairness_target_status: string;
  summary: any;
  allocations?: AllocationRow[];
  unroutable_candidate_facilities?: string[];
  stock_status_chip?: string;
}

export interface ClosureResult {
  run_id: string;
  event: string;
  engine: EngineType;
  applied_closure_id: string;
  closure_geometry?: string;
  closure_scope?: string;
  stock_mode: StockMode;
  inventory_basis: string;
  steps: StepRecord[];
  module9: any;
  module7_routes: {
    zone_count: number;
    road_count: number;
    secondary_count: number;
    unreachable_count: number;
  };
  before_distance_km?: number;
  after_distance_km?: number;
}

export interface StockSweepRow {
  stock_pct: number;
  engine: EngineType;
  min_zone_coverage_pct: number;
  unmet_demand_pct: number;
  unmet_demand_min_pct?: number;
  unmet_demand_max_pct?: number;
  total_allocated: number;
  total_demand: number;
  donor_floor_feasible: boolean;
  donor_floor_target: number;
  min_zone_cov_min?: number;
  min_zone_cov_max?: number;
  min_zone_cov_mean?: number;
  weighted_service_score?: number;
  zone_coverage_vector?: number[];
  collapse_below_1pct?: boolean;
  seed_count?: number;
}

export interface StockSweepThresholds {
  event_date: string;
  smallest_stock_pct_for_40pct_floor: number;
  stock_pct_unmet_demand_sub_10pct: number;
  linucb_collapse_below_1pct_stock_pct: number;
}

export interface GaugeReading {
  event_date: string;
  reading_timestamp_utc: string;
  water_level_m: number;
  danger_mark_m: number;
  warning_level_m: number;
  distance_above_danger_m: number;
  gauge_station: string;
  cwc_station_code: string;
  reporting_agency: string;
  source_document_title: string;
  source_url: string;
  is_peak_reading: boolean;
  notes: string;
}

export interface FacilityStock {
  resource: string;
  quantity: number;
  unit: string;
  mode: 'assumed' | 'entered';
  updated_by: string;
  updated_at: string;
  note: string | null;
  is_stale: boolean;
}

export interface Facility {
  id: string;
  name: string;
  type: string;
  lat: number | null;
  lon: number | null;
  source: string;
  confidence: string;
  geometry_verified: boolean | number;
  is_routable: boolean;
  unroutable_reason?: string | null;
  stock: FacilityStock[];
}

export interface FacilityStockSummary {
  totals: Record<string, { quantity: number; unit: string; entered_count: number; assumed_count: number }>;
  stale_count: number;
  total_facilities: number;
  unroutable_facilities_count: number;
  mode_status: string;
}

export interface Scenario {
  id: string;
  title: string;
  category: 'documented_replay' | 'hypothetical_what_if' | string;
  description: string;
  event_date: string;
  parameters: Record<string, any>;
  assumptions_statement?: string;
}

export interface ScenarioResult {
  scenario_id: string;
  scenario_title: string;
  category: string;
  event_date: string;
  seed?: number;
  summary: Record<string, any>;
  steps?: StepRecord[];
  disclaimer: string;
}

export interface AdminOverrideItem {
  zone_id: string;
  resource: string;
  allocated: number;
}

export interface AdminOverrideResponse {
  run_id: string;
  operator: string;
  label: string;
  status: string;
  donor_floor_pct: number;
  reason: string;
  coverage_changes: {
    zone_id: string;
    resource: string;
    before_coverage_pct: number;
    after_coverage_pct: number;
    coverage_delta_pct: number;
  }[];
  timestamp: string;
}
