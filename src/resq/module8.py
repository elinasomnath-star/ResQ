"""Synthetic repeated-disruption benchmark across 16 Bantwal grid zones."""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import networkx as nx
from shapely.geometry import LineString, Point, shape

from .config import configured_path, load_config
from .events import load_events
from .optimization.allocation import (
    RESOURCE_COLUMNS, _feasible_floor_pct, _metrics,
    _num, _proportional, _read_csv, _solve_milp, _train_contextual_bandit,
)
from .module9 import (
    apply_partial_reallocation, assess_shortage, global_min_zone_coverage, minimum_zone_coverage,
    write_module9_artifacts,
)
from .routing import _load_graph, _nearest_node, _zone_points, block_matching_lines, block_near_points


STEPS = 8


def build_analysis_event_demand(event_date: str, config: dict[str, Any] | None = None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Read demand for exactly the 16 SAR-covered Bantwal grid zones."""
    config = config or load_config()
    processed = configured_path(config["data"]["processed_dir"])
    rows = _read_csv(processed / f"severity_demand_{event_date}.csv")
    zones_path = configured_path(config["data"].get("analysis_zones_path", config["data"]["zones_path"]))
    collection = json.loads(zones_path.read_text(encoding="utf-8"))
    features = collection.get("features", [])
    if len(features) != 16 or any(f.get("properties", {}).get("zone_type") != "analysis_grid" for f in features):
        raise ValueError(f"Expected exactly 16 Bantwal analysis-grid zones in {zones_path}")
    demand_ids = {row["zone_id"] for row in rows}
    geometry_ids = {f["properties"]["zone_id"] for f in features}
    if demand_ids != geometry_ids:
        raise ValueError(f"Demand/geometry zone mismatch: demand-only={demand_ids - geometry_ids}; geometry-only={geometry_ids - demand_ids}")
    output_path = processed / "zones_module8_analysis_grid.geojson"
    output_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return rows, {
        "event_date": event_date,
        "zone_count": len(rows),
        "mangaluru_ward_count": 0,
        "zone_method": "16-cell regular grid clipped to Bantwal and checked for valid SAR coverage on every event date",
        "population_method": "area-weighted Bantwal parent population proxy",
        "analysis_zone_geojson": str(output_path),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Cannot write an empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

def _verified_closures(event_date: str, processed: Path) -> tuple[list[tuple[float, float]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load only Module 7 verified closure geometry for this event."""
    path = processed / f"closures_{event_date}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"Module 7 closure file is missing: {path}")
    collection = json.loads(path.read_text(encoding="utf-8"))
    points: list[tuple[float, float]] = []
    lines: list[dict[str, Any]] = []
    verified = []
    for feature in collection.get("features", []):
        geometry, props = feature.get("geometry"), feature.get("properties", {})
        if not geometry or props.get("status") != "verified":
            continue
        verified.append({"closure_id": props.get("closure_id"), "name": props.get("name"),
                         "geometry_type": geometry.get("type"), "osm_way_ids": props.get("osm_way_ids")})
        if geometry["type"] == "Point":
            points.append(tuple(map(float, geometry["coordinates"][:2])))
        elif geometry["type"] == "LineString":
            lines.append({**props, "coordinates": geometry["coordinates"]})
        elif geometry["type"] == "MultiLineString":
            lines.append({**props, "coordinate_parts": geometry["coordinates"]})
    if not points and not lines:
        raise ValueError(f"{path} contains no verified closure Point/LineString geometry")
    return points, lines, verified


def _closure_impacts(event_date: str, config: dict[str, Any], processed: Path,
                     zone_path: Path) -> tuple[set[str], dict[str, Any]]:
    """Apply real closure geometry to the cached graph and identify impacted zones."""
    points, lines, verified = _verified_closures(event_date, processed)
    graph_path = configured_path(config["data"]["road_graph_path"])
    graph, utm_zone = _load_graph(graph_path)
    open_graph = graph.copy()
    closed_graph = graph.copy()
    radius = float(config.get("routing", {}).get("blockage_snap_radius_m", 35))
    removed = block_near_points(closed_graph, points, utm_zone, radius)
    removed.extend(block_matching_lines(closed_graph, lines, utm_zone, tolerance_m=radius))

    warehouse_path = processed / "warehouses.geojson"
    collection = json.loads(warehouse_path.read_text(encoding="utf-8")) if warehouse_path.exists() else {"features": []}
    origins = []
    for feature in collection.get("features", []):
        geom, props = feature.get("geometry"), feature.get("properties", {})
        if geom and geom.get("type") == "Point" and props.get("route_origin", True):
            origins.append(tuple(map(float, geom["coordinates"][:2])))
    if not origins:
        origins = [(float(row["lon"]), float(row["lat"])) for row in config.get("warehouses", [])]
    if not origins:
        raise ValueError("Module 8 road impact analysis requires at least one configured warehouse candidate")
    max_snap = float(config.get("routing", {}).get("max_snap_distance_m", 5000))
    sources = {_nearest_node(open_graph, lon, lat, utm_zone)[0] for lon, lat in origins
               if _nearest_node(open_graph, lon, lat, utm_zone)[1] <= max_snap}
    if not sources:
        raise ValueError("No Module 8 warehouse candidate snaps within configured routing distance")
    baseline_distances = nx.multi_source_dijkstra_path_length(open_graph, sources, weight="length")
    closed_distances = nx.multi_source_dijkstra_path_length(closed_graph, sources, weight="length")

    # A closure lies in a zone even when alternate roads preserve reachability;
    # a route detour/unreachable result also marks a zone affected.
    closure_shapes = [Point(lon, lat) for lon, lat in points]
    for line in lines:
        parts = line.get("coordinate_parts") or [line.get("coordinates", [])]
        closure_shapes.extend(LineString(part) for part in parts if len(part) >= 2)
    impact: set[str] = set()
    route_deltas: dict[str, dict[str, Any]] = {}
    zone_collection = json.loads(zone_path.read_text(encoding="utf-8"))
    polygons = {str(f.get("properties", {}).get("zone_id")): shape(f["geometry"])
                for f in zone_collection.get("features", []) if f.get("geometry")}
    for target in _zone_points(zone_path):
        polygon = polygons.get(target["zone_id"])
        if polygon is not None and any(polygon.intersects(item) for item in closure_shapes):
            impact.add(target["zone_id"])
        node, snap = _nearest_node(open_graph, target["lon"], target["lat"], utm_zone)
        before = baseline_distances.get(node)
        after = closed_distances.get(node)
        changed = before is not None and (after is None or after > before + max(500.0, before * 0.1))
        if changed:
            impact.add(target["zone_id"])
        route_deltas[target["zone_id"]] = {
            "baseline_distance_m": before, "closed_distance_m": after,
            "route_changed": bool(changed), "target_snap_distance_m": snap,
        }
    return impact, {"verified_closures": verified, "removed_directed_edges": len(removed),
                    "closure_radius_m": radius, "impacted_zone_ids": sorted(impact),
                    "route_effects_by_zone": route_deltas,
                    "method": "cached Module 7 graph edge removal; zone polygon intersection and multi-source shortest-route comparison"}


def _allocate_bandit(policy: Any, rows: list[dict[str, str]], stocks: dict[str, int], severity: np.ndarray, pop: np.ndarray) -> tuple[dict[str, np.ndarray], float]:
    from .optimization.allocation import _context
    out = {}
    start = time.perf_counter()
    for resource, column in RESOURCE_COLUMNS.items():
        demand = np.asarray([math.ceil(_num(r.get(column))) for r in rows], dtype=int)
        allocated = np.zeros(len(rows), dtype=int)
        left = max(0, int(stocks.get(resource, 0)))
        batch = max(1, left // 100)
        while left and np.any(allocated < demand):
            arm = policy.choose(_context(severity, demand, allocated, pop), allocated < demand)
            amount = min(batch, left, int(demand[arm] - allocated[arm]))
            allocated[arm] += amount; left -= amount
        out[resource] = allocated
    return out, time.perf_counter() - start


def run_module8(event_date: str, *, steps: int = STEPS, seed: int = 20261026,
                config: dict[str, Any] | None = None) -> tuple[Path, Path]:
    """Run repeated, synthetic disruption/reallocation comparison for one event."""
    if steps < 5 or steps > 10: raise ValueError("Module 8 uses 5–10 disruption steps")
    config = config or load_config()
    processed = configured_path(config["data"]["processed_dir"])
    base_rows, zone_meta = build_analysis_event_demand(event_date, config)
    severity_base = np.asarray([_num(r.get("severity_score")) for r in base_rows])
    population = np.asarray([_num(r.get("population_estimate")) for r in base_rows])
    stocks0 = {key: int(value) for key, value in config["resources"]["prototype_inventory"].items()}

    # Train on broad, seeded perturbations around all three event vectors.
    event_rows = []
    for event in load_events():
        day = event.event_date.isoformat()
        rows, _ = build_analysis_event_demand(day, config)
        event_rows.append(rows)
    policies = {}
    augmentation_episodes = 600
    training_episodes = augmentation_episodes + 120
    rng = np.random.default_rng(seed)
    training_start = time.perf_counter()
    for resource, column in RESOURCE_COLUMNS.items():
        anchors = [np.asarray([math.ceil(_num(r.get(column))) for r in rows], dtype=int) for rows in event_rows]
        policy, _, _ = _train_contextual_bandit(anchors, severity_base, population,
                                                 stocks0.get(resource, 0),
                                                 float(config["resources"].get("min_fairness_pct", 40)) / 100,
                                                 seed + sum(map(ord, resource)))
        # Additional broad scenario augmentation updates the learned policy on
        # zone distributions/stock ratios beyond the base 120 episode routine.
        from .optimization.allocation import _context
        for _ in range(augmentation_episodes):
            anchor = anchors[int(rng.integers(len(anchors)))].astype(float)
            scenario = np.maximum(0, np.rint(anchor * rng.uniform(0.2, 1.8, size=len(anchor)))).astype(int)
            stock = max(0, int(stocks0.get(resource, 0) * rng.uniform(0.3, 1.5)))
            allocated = np.zeros(len(scenario), dtype=int)
            rem = stock; batch = max(1, stock // 80)
            synthetic_sev = np.clip(severity_base * rng.uniform(0.5, 1.6, len(scenario)), 0, 1)
            while rem and np.any(allocated < scenario):
                ctx = _context(synthetic_sev, scenario, allocated, population)
                arm = policy.choose(ctx, allocated < scenario)
                amount = min(batch, rem, int(scenario[arm] - allocated[arm]))
                before = allocated[arm] / max(1, scenario[arm]); allocated[arm] += amount
                after = allocated[arm] / max(1, scenario[arm]); gain = after - before
                reward = gain * (1 + 0.7 * synthetic_sev[arm] + 0.5 * max(0, 0.4 - before))
                policy.update(arm, ctx[arm], reward); rem -= amount
        policies[resource] = policy
    training_time = time.perf_counter() - training_start

    module8_zone_path = processed / "zones_module8_analysis_grid.geojson"
    closure_zone_ids, closure_impact = _closure_impacts(event_date, config, processed, module8_zone_path)
    zone_ids = [r["zone_id"] for r in base_rows]
    zone_index = {zone_id: i for i, zone_id in enumerate(zone_ids)}
    affected_indices = {zone_index[z] for z in closure_zone_ids if z in zone_index}
    module8_config = config.get("module8", {})
    closure_activation_step = int(module8_config.get("closure_activation_step", 2))
    shortage_threshold = float(module8_config.get("shortage_threshold", 0.20))
    redirect_pct = float(module8_config.get("escalation_redirect_pct", 0.15))
    fairness_floor = float(config["resources"].get("min_fairness_pct", 40)) / 100
    engines = ("MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline")
    remaining = {e: stocks0.copy() for e in engines}
    cumulative_alloc = {e: {r: np.zeros(len(base_rows), dtype=int) for r in RESOURCE_COLUMNS} for e in engines}
    records: list[dict[str, Any]] = []
    escalation_triggers: list[dict[str, Any]] = []
    reallocation_rows: list[dict[str, Any]] = []
    redirect_trace_rows: list[dict[str, Any]] = []
    cumulative_time = {e: 0.0 for e in engines}
    for step in range(1, steps + 1):
        rows = [r.copy() for r in base_rows]
        sev = severity_base.copy()
        closure_active = step >= closure_activation_step
        active_indices = affected_indices if closure_active else set()
        for idx in active_indices:
            sev[idx] = min(1.0, sev[idx] + 0.35)
            for resource, column in RESOURCE_COLUMNS.items():
                value = _num(rows[idx].get(column))
                rows[idx][column] = str(math.ceil(value * 1.25))
        # Event-wide hazard evolution is a bounded synthetic stress ramp.
        factor = 1.0 + 0.025 * (step - 1)
        for row in rows:
            for column in RESOURCE_COLUMNS.values(): row[column] = str(math.ceil(_num(row.get(column)) * factor))
        stock_before = {e: remaining[e].copy() for e in engines}
        floor_demands = {r: np.asarray([math.ceil(_num(x.get(col))) for x in rows], dtype=int)
                         for r, col in RESOURCE_COLUMNS.items()}
        for engine in engines:
            need_rows = []
            for i, row in enumerate(rows):
                item = row.copy()
                for resource, col in RESOURCE_COLUMNS.items():
                    item[col] = str(max(0, floor_demands[resource][i] - cumulative_alloc[engine][resource][i]))
                need_rows.append(item)
            # Unserved demand after previous steps is the live demand.
            rem_demands = {r: np.asarray([int(float(x[RESOURCE_COLUMNS[r]])) for x in need_rows], dtype=int) for r in RESOURCE_COLUMNS}
            total_time = 0.0
            if engine == "MILP":
                target = float(config["resources"].get("min_fairness_pct", 40)) / 100
                floor = _feasible_floor_pct(rem_demands, remaining[engine], target)
                try:
                    alloc, elapsed, _ = _solve_milp(need_rows, remaining[engine], target, sev)
                except Exception as exc:
                    if "INFEASIBLE" not in str(exc): raise
                    alloc, elapsed, _ = _solve_milp(need_rows, remaining[engine], floor, sev)
                total_time += elapsed
            elif engine == "LinUCB_contextual_bandit":
                start = time.perf_counter(); alloc = {}
                for resource, col in RESOURCE_COLUMNS.items():
                    partial, _ = _allocate_bandit(policies[resource], need_rows,
                                                   {resource: remaining[engine].get(resource, 0)}, sev, population)
                    alloc[resource] = partial[resource]
                total_time += time.perf_counter() - start
            else:
                start = time.perf_counter(); alloc = _proportional(need_rows, remaining[engine]); total_time = time.perf_counter() - start
            cumulative_time[engine] += total_time
            for resource in RESOURCE_COLUMNS:
                got = np.minimum(alloc[resource], rem_demands[resource])
                cumulative_alloc[engine][resource] += got
                remaining[engine][resource] = max(0, remaining[engine][resource] - int(got.sum()))
            metric = _metrics(engine, alloc, need_rows, stock_before[engine], total_time)
            min_before = minimum_zone_coverage(floor_demands, cumulative_alloc[engine])
            min_zones_before, min_value_before = global_min_zone_coverage(
                floor_demands, cumulative_alloc[engine], zone_ids)
            unmet_snapshot = {
                resource: int(np.maximum(0, floor_demands[resource] - cumulative_alloc[engine][resource]).sum())
                for resource in RESOURCE_COLUMNS
            }
            ratio_snapshot = {
                resource: (remaining[engine][resource] / unmet_snapshot[resource]) if unmet_snapshot[resource] else None
                for resource in RESOURCE_COLUMNS
            }
            shortage_resources = [resource for resource in RESOURCE_COLUMNS
                                  if unmet_snapshot[resource] and
                                  remaining[engine][resource] < shortage_threshold * unmet_snapshot[resource]]
            trigger = assess_shortage(event_date=event_date, step=step, engine=engine,
                                      inventory=remaining[engine], demands=floor_demands,
                                      allocated=cumulative_alloc[engine], threshold=shortage_threshold,
                                      zone_ids=zone_ids)
            stopgap_rows = []
            if trigger is not None:
                trigger_id = f"{event_date}_{engine}_{step:02d}"
                trigger["trigger_id"] = trigger_id
                trigger["min_zone_coverage_before_pct"] = min_before * 100
                stopgap_rows = apply_partial_reallocation(
                    event_date=event_date, step=step, engine=engine, trigger_id=trigger_id,
                    trigger=trigger, demands=floor_demands, allocated=cumulative_alloc[engine],
                    severity=sev, zone_ids=zone_ids,
                    step_global_min_zones=min_zones_before,
                    step_global_min_value=min_value_before,
                    fairness_floor=fairness_floor,
                    redirect_pct=redirect_pct,
                )
                reallocation_rows.extend(stopgap_rows)
                for transfer in stopgap_rows:
                    redirect_trace_rows.append({
                        "step": step,
                        "global_min_zone": transfer["global_min_zone_ids_before"],
                        "global_min_value": transfer["global_min_value_before_pct"],
                        "redirect_fired": "yes",
                        "redirect_recipient_zone": transfer["recipient_zone_id"],
                        "recipient_matches_global_min": ("yes" if transfer["recipient_matches_global_min"] else "no"),
                        "engine": engine,
                    })
                min_zones_after, min_value_after = global_min_zone_coverage(
                    floor_demands, cumulative_alloc[engine], zone_ids)
                min_after = min_value_after
                trigger["min_zone_coverage_after_pct"] = min_after * 100
                trigger["transfer_count"] = len(stopgap_rows)
                escalation_triggers.append(trigger)
            else:
                min_after = min_before
                min_zones_after = min_zones_before
                min_value_after = min_value_before
            if not stopgap_rows:
                redirect_trace_rows.append({
                    "step": step,
                    "global_min_zone": ";".join(min_zones_before),
                    "global_min_value": min_value_before * 100,
                    "redirect_fired": "no",
                    "redirect_recipient_zone": "",
                    "recipient_matches_global_min": "n/a",
                    "engine": engine,
                })
            records.append({"event_date": event_date, "step": step, "engine": engine,
                            "disruption": ("real Module 7 closure activated" if step == closure_activation_step else
                                           "real Module 7 closure active; stock-depletion reallocation" if closure_active else
                                           "pre-closure stock-depletion reallocation"),
                            "closure_active": closure_active,
                            "closure_edges_removed": closure_impact["removed_directed_edges"] if step == closure_activation_step else 0,
                            "affected_zone_id": ";".join(zone_ids[i] for i in sorted(active_indices)),
                            "zones": len(rows), "step_inference_or_solve_seconds": total_time,
                            "cumulative_solve_or_inference_seconds": cumulative_time[engine],
                            "remaining_inventory": json.dumps(remaining[engine], sort_keys=True),
                            "step_minimum_zone_coverage_pct": min_after * 100,
                            "minimum_zone_coverage_before_escalation_pct": min_before * 100,
                            "minimum_zone_coverage_after_escalation_pct": min_after * 100,
                            "global_min_zone_before_redirect": ";".join(min_zones_before),
                            "global_min_zone_after_redirect": ";".join(min_zones_after),
                            "minimum_floor_persisted_at_other_zone": (
                                math.isclose(min_value_before, min_value_after, rel_tol=0, abs_tol=1e-12)
                                and bool(set(min_zones_after).difference(
                                    {r["recipient_zone_id"] for r in stopgap_rows}))
                            ),
                            "escalation_triggered": trigger is not None,
                            "escalation_trigger_id": trigger.get("trigger_id") if trigger else "",
                            "shortfall_by_resource": json.dumps(trigger["shortfall_by_resource"], sort_keys=True) if trigger else "{}",
                            "remaining_unmet_demand": json.dumps(unmet_snapshot, sort_keys=True),
                            "inventory_to_unmet_ratio": json.dumps(ratio_snapshot, sort_keys=True),
                            "shortage_resource_types": ";".join(shortage_resources),
                            "stopgap_transfer_count": len(stopgap_rows),
                            "weighted_service_objective": metric["weighted_allocation_objective"],
                            "step_unmet_demand_pct": metric["aggregate_unmet_demand_pct"]})
    step_path = processed / f"module8_dynamic_steps_{event_date}.csv"
    summary_path = processed / f"module8_dynamic_summary_{event_date}.json"
    zone_path = processed / f"module8_dynamic_zone_unmet_{event_date}.csv"
    _write_csv(step_path, records)
    final_factor = 1.0 + 0.025 * (steps - 1)
    zone_shortfalls: list[dict[str, Any]] = []
    final_needs: dict[str, np.ndarray] = {}
    for resource, column in RESOURCE_COLUMNS.items():
        needs = np.asarray([
            math.ceil((math.ceil(_num(row.get(column)) * 1.25) if i in affected_indices else _num(row.get(column))) * final_factor)
            for i, row in enumerate(base_rows)
        ], dtype=int)
        final_needs[resource] = needs
    for engine in engines:
        for i, zone in enumerate(base_rows):
            for resource in RESOURCE_COLUMNS:
                need = int(final_needs[resource][i])
                served = min(need, int(cumulative_alloc[engine][resource][i]))
                zone_shortfalls.append({"event_date": event_date, "engine": engine,
                                        "zone_id": zone["zone_id"], "zone_name": zone["zone_name"],
                                        "resource": resource, "final_scenario_need": need,
                                        "cumulative_allocated": int(cumulative_alloc[engine][resource][i]),
                                        "served_of_final_need": served, "final_unmet": need - served,
                                        "final_unmet_pct": 100.0 * (need - served) / need if need else 0.0})
    _write_csv(zone_path, zone_shortfalls)
    alert_path, transfer_path = write_module9_artifacts(processed, event_date, escalation_triggers, reallocation_rows)
    trace_paths = {}
    trace_fields = ["step", "global_min_zone", "global_min_value", "redirect_fired",
                    "redirect_recipient_zone", "recipient_matches_global_min"]
    for engine in engines:
        engine_slug = engine
        trace_path = processed / f"module9_redirect_trace_{event_date}_{engine_slug}.csv"
        with trace_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=trace_fields)
            writer.writeheader()
            engine_rows = [row for row in redirect_trace_rows if row["engine"] == engine]
            by_step: dict[int, list[dict[str, Any]]] = {}
            for row in engine_rows:
                by_step.setdefault(int(row["step"]), []).append(row)
            for step in sorted(by_step):
                step_rows = by_step[step]
                fired = [row for row in step_rows if row["redirect_fired"] == "yes"]
                first = step_rows[0]
                writer.writerow({
                    "step": step,
                    "global_min_zone": first["global_min_zone"],
                    "global_min_value": first["global_min_value"],
                    "redirect_fired": "yes" if fired else "no",
                    "redirect_recipient_zone": ";".join(sorted({row["redirect_recipient_zone"] for row in fired})),
                    "recipient_matches_global_min": (
                        "yes" if fired and all(row["recipient_matches_global_min"] == "yes" for row in fired)
                        else "no" if fired else "n/a"
                    ),
                })
        trace_paths[engine] = str(trace_path)
    summary: dict[str, Any] = {"event_date": event_date, "steps": steps, "zone_metadata": zone_meta,
                               "disruption_model": "event-specific verified Module 7 closure geometry is removed from the cached OSM graph at the configured activation step; affected zones are identified by polygon intersection and route detours; a bounded hazard ramp and inventory depletion continue between rounds",
                               "road_network_note": "Real verified closure geometries remove directed cached graph edges; route changes and affected zones are recorded. Closure coordinates may be corridor-level rather than pinpoint flood points.",
                               "module7_closure_impact": closure_impact,
                               "closure_activation_step": closure_activation_step,
                               "shortage_threshold": shortage_threshold,
                               "escalation_redirect_pct": redirect_pct,
                               "fairness_floor_pct_for_stopgap": fairness_floor * 100,
                               "module9": {"integrated": True, "alert_log": str(alert_path),
                                           "reallocation_log": str(transfer_path),
                                           "redirect_trace_paths": trace_paths,
                                           "trigger_count": len(escalation_triggers),
                                           "transfer_count": len(reallocation_rows),
                                           "engines": {}},
                               "linucb_training": {"episodes_per_resource": training_episodes, "base_synthetic_episodes": 120, "broad_augmentation_episodes": augmentation_episodes, "event_vectors": [e.event_date.isoformat() for e in load_events()], "training_wall_time_seconds": training_time, "basis": "synthetic perturbations across all three event demand vectors; not observed realizations"},
                               "zone_shortfall_csv": str(zone_path),
                               "engines": {}}
    for engine in engines:
        subset = [r for r in records if r["engine"] == engine]
        final_zone_coverages = []
        for i in range(len(base_rows)):
            by_resource = [
                min(1.0, int(cumulative_alloc[engine][resource][i]) / int(final_needs[resource][i]))
                if final_needs[resource][i] else 1.0
                for resource in RESOURCE_COLUMNS
            ]
            final_zone_coverages.append(min(by_resource))
        summary["engines"][engine] = {
            "cumulative_solve_or_inference_seconds": cumulative_time[engine],
            "mean_step_seconds": float(np.mean([r["step_inference_or_solve_seconds"] for r in subset])),
            "mean_step_unmet_demand_pct": float(np.mean([r["step_unmet_demand_pct"] for r in subset])),
            "mean_step_weighted_service_objective": float(np.mean([r["weighted_service_objective"] for r in subset])),
            "final_minimum_zone_coverage_pct": 100.0 * min(final_zone_coverages, default=1.0),
            "final_remaining_inventory": json.loads(subset[-1]["remaining_inventory"]),
            "final_per_zone_unmet": {r["zone_id"]: {resource: int(final_needs[resource][i]) - min(int(final_needs[resource][i]), int(cumulative_alloc[engine][resource][i]))
                                                        for resource in RESOURCE_COLUMNS}
                                      for i, r in enumerate(base_rows)},
        }
        engine_triggers = [t for t in escalation_triggers if t["engine"] == engine]
        engine_transfers = [t for t in reallocation_rows if t["engine"] == engine]
        summary["module9"]["engines"][engine] = {
            "trigger_count": len(engine_triggers),
            "trigger_steps": [t["step"] for t in engine_triggers],
            "transfer_count": len(engine_transfers),
            "mean_min_zone_coverage_before_pct": float(np.mean([t["min_zone_coverage_before_pct"] for t in engine_triggers])) if engine_triggers else None,
            "mean_min_zone_coverage_after_pct": float(np.mean([t["min_zone_coverage_after_pct"] for t in engine_triggers])) if engine_triggers else None,
            "mean_coverage_change_pct_points": float(np.mean([t["min_zone_coverage_after_pct"] - t["min_zone_coverage_before_pct"] for t in engine_triggers])) if engine_triggers else 0.0,
        }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return step_path, summary_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-date", action="append")
    parser.add_argument("--steps", type=int, default=STEPS)
    args = parser.parse_args()
    wanted = set(args.event_date or [])
    events = [e.event_date.isoformat() for e in load_events() if not wanted or e.event_date.isoformat() in wanted]
    if wanted and wanted != set(events): raise ValueError(f"Unknown event dates: {sorted(wanted - set(events))}")
    for day in events:
        steps, summary = run_module8(day, steps=args.steps)
        print(f"[{day}] Dynamic steps: {steps}; summary: {summary}")


if __name__ == "__main__": main()
