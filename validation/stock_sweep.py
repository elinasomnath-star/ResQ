"""Stock sweep across shortage and surplus regimes (10% to 150% in 5% increments).

Runs MILP, LinUCB (5 seeds: mean, min, max), and Proportional baseline.
Computes critical feasibility and collapse thresholds via bisection.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from resq.config import REPO_ROOT, configured_path, load_config
from resq.events import load_events
from resq.optimization.allocation import (
    MilpInfeasible,
    RESOURCE_COLUMNS,
    RESOURCE_WEIGHTS,
    _context,
    _feasible_floor_pct,
    _metrics,
    _num,
    _proportional,
    _read_csv,
    _required_floor,
    _solve_milp,
    _train_contextual_bandit,
)

SWEEP_GRID_PCTS = [round(x, 2) for x in np.arange(0.10, 1.5001, 0.05)]
LINUCB_SEEDS = [42, 43, 44, 45, 46]


def compute_zone_metrics(allocation: dict[str, np.ndarray], zone_rows: list[dict[str, str]],
                         demands: dict[str, np.ndarray]) -> tuple[list[float], float, float, int, int]:
    """Compute per-zone coverages (min across resources), std, gini, and counts below 10% & 50%."""
    zone_coverages: list[float] = []
    for i in range(len(zone_rows)):
        res_covers = []
        for resource in RESOURCE_COLUMNS:
            need = int(demands[resource][i])
            got = int(allocation[resource][i])
            res_covers.append(min(1.0, got / need) if need > 0 else 1.0)
        zone_coverages.append(min(res_covers))
    arr = np.asarray(zone_coverages, dtype=float)
    std = float(np.std(arr))
    # Gini coefficient of zone coverage
    mean = float(np.mean(arr))
    if mean > 1e-9:
        diff_matrix = np.abs(arr[:, None] - arr[None, :])
        gini = float(np.sum(diff_matrix) / (2.0 * len(arr) ** 2 * mean))
    else:
        gini = 0.0
    below_10 = int(np.sum(arr < 0.10))
    below_50 = int(np.sum(arr < 0.50))
    return zone_coverages, std, gini, below_10, below_50


def run_single_linucb(zone_rows: list[dict[str, str]], demands: dict[str, np.ndarray],
                      inventory: dict[str, int], severity: np.ndarray, population: np.ndarray,
                      related_demands: dict[str, list[np.ndarray]], seed: int) -> dict[str, np.ndarray]:
    """Train LinUCB on synthetic perturbed episodes for this stock level and allocate."""
    effective_floor = _feasible_floor_pct(demands, inventory, 0.40)
    alloc: dict[str, np.ndarray] = {}
    for resource, demand in demands.items():
        related = related_demands.get(resource, [demand])
        stock = max(0, int(inventory.get(resource, 0)))
        policy, _, _ = _train_contextual_bandit(related, severity, population, stock, 0.40, seed=seed)
        allocated = _required_floor(demand, effective_floor)
        remaining = max(0, stock - int(allocated.sum()))
        batch = max(1, stock // 100)
        for _ in range(120):
            eligible = allocated < demand
            if remaining <= 0 or not np.any(eligible):
                break
            contexts = _context(severity, demand, allocated, population)
            arm = policy.choose(contexts, eligible)
            amount = min(batch, remaining, int(demand[arm] - allocated[arm]))
            allocated[arm] += amount
            remaining -= amount
        alloc[resource] = allocated
    return alloc


def bisect_smallest_40_pct_feasible(zone_rows: list[dict[str, str]], demands: dict[str, np.ndarray],
                                    total_demands: dict[str, int], severity: np.ndarray) -> float:
    """Find smallest stock percentage at which the 40% fairness floor is feasible for MILP."""
    def is_feasible(pct: float) -> bool:
        inv = {r: max(0, int(round(pct * total_demands[r]))) for r in RESOURCE_COLUMNS}
        floor = _feasible_floor_pct(demands, inv, 0.40)
        if floor < 0.40 - 1e-6:
            return False
        try:
            _solve_milp(zone_rows, inv, 0.40, severity)
            return True
        except (MilpInfeasible, RuntimeError):
            return False

    low, high = 0.05, 1.50
    if is_feasible(low):
        return low
    if not is_feasible(high):
        return float("nan")

    for _ in range(35):
        mid = (low + high) / 2.0
        if is_feasible(mid):
            high = mid
        else:
            low = mid
    return round(high * 100.0, 2)


def bisect_unmet_demand_below_10_pct(zone_rows: list[dict[str, str]], demands: dict[str, np.ndarray],
                                    total_demands: dict[str, int], severity: np.ndarray) -> float:
    """Find smallest stock percentage where MILP unmet demand drops below 10%."""
    def get_unmet(pct: float) -> float:
        inv = {r: max(0, int(round(pct * total_demands[r]))) for r in RESOURCE_COLUMNS}
        floor = _feasible_floor_pct(demands, inv, 0.40)
        try:
            alloc, t, obj = _solve_milp(zone_rows, inv, floor, severity)
        except MilpInfeasible:
            alloc, t, obj = _solve_milp(zone_rows, inv, 0.0, severity)
        m = _metrics("MILP", alloc, zone_rows, inv, t, obj)
        return float(m["aggregate_unmet_demand_pct"])

    low, high = 0.50, 1.50
    if get_unmet(high) > 10.0:
        return float("nan")
    if get_unmet(low) <= 10.0:
        return round(low * 100.0, 2)

    for _ in range(30):
        mid = (low + high) / 2.0
        if get_unmet(mid) <= 10.0:
            high = mid
        else:
            low = mid
    return round(high * 100.0, 2)


def find_linucb_collapse_threshold(sweep_records: list[dict[str, Any]]) -> float:
    """Find stock % below which LinUCB's minimum zone coverage drops below 1.0%."""
    linucb_records = [r for r in sweep_records if r["engine"] == "LinUCB_contextual_bandit"]
    linucb_records.sort(key=lambda r: r["stock_pct"])
    # Find the transition where mean minimum coverage is < 1.0%
    collapse_pct = linucb_records[0]["stock_pct"]
    for i, r in enumerate(linucb_records):
        cov = float(r.get("minimum_zone_coverage_pct", 0.0))
        if cov >= 1.0:
            if i > 0:
                prev = linucb_records[i - 1]
                prev_cov = float(prev.get("minimum_zone_coverage_pct", 0.0))
                denom = max(1e-6, cov - prev_cov)
                frac = (1.0 - prev_cov) / denom
                collapse_pct = round(prev["stock_pct"] + frac * (r["stock_pct"] - prev["stock_pct"]), 2)
            else:
                collapse_pct = r["stock_pct"]
            break
    return collapse_pct


def run_stock_sweep() -> dict[str, Any]:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    events = [e.event_date.isoformat() for e in load_events()]

    thresholds_by_event: dict[str, dict[str, Any]] = {}
    all_summary_rows: list[dict[str, Any]] = []

    for event_date in events:
        print(f"\n==================================================")
        print(f"Running stock sweep for event: {event_date}")
        print(f"==================================================")
        zone_csv = processed / f"severity_demand_{event_date}.csv"
        zone_rows = _read_csv(zone_csv)
        severity = np.asarray([_num(r.get("severity_score")) for r in zone_rows], dtype=float)
        population = np.asarray([_num(r.get("population_estimate")) for r in zone_rows], dtype=float)
        demands = {
            res: np.asarray([int(math.ceil(_num(r.get(col)))) for r in zone_rows], dtype=int)
            for res, col in RESOURCE_COLUMNS.items()
        }
        total_demands = {res: int(demands[res].sum()) for res in RESOURCE_COLUMNS}
        print(f"Total modeled need: {total_demands}")

        # Gather related demand vectors from all events for LinUCB training
        related_demands: dict[str, list[np.ndarray]] = {res: [] for res in RESOURCE_COLUMNS}
        for d_str in events:
            cand = processed / f"severity_demand_{d_str}.csv"
            if cand.exists():
                c_rows = _read_csv(cand)
                if len(c_rows) == len(zone_rows):
                    for res, col in RESOURCE_COLUMNS.items():
                        related_demands[res].append(
                            np.asarray([int(math.ceil(_num(r.get(col)))) for r in c_rows], dtype=int)
                        )

        event_sweep_data: list[dict[str, Any]] = []
        csv_rows: list[dict[str, Any]] = []

        for stock_fraction in SWEEP_GRID_PCTS:
            stock_pct = round(stock_fraction * 100.0, 1)
            inventory = {res: max(0, int(round(stock_fraction * total_demands[res]))) for res in RESOURCE_COLUMNS}
            effective_floor = _feasible_floor_pct(demands, inventory, 0.40)

            # 1. MILP Engine
            milp_status = "optimal"
            try:
                milp_alloc, milp_time, milp_obj = _solve_milp(zone_rows, inventory, 0.40, severity)
                milp_status = "optimal"
            except MilpInfeasible:
                try:
                    milp_alloc, milp_time, milp_obj = _solve_milp(zone_rows, inventory, effective_floor, severity)
                    milp_status = "fallback_floor"
                except Exception:
                    milp_alloc, milp_time, milp_obj = _solve_milp(zone_rows, inventory, 0.0, severity)
                    milp_status = "infeasible"

            milp_metrics = _metrics("MILP", milp_alloc, zone_rows, inventory, milp_time, milp_obj)
            m_covers, m_std, m_gini, m_b10, m_b50 = compute_zone_metrics(milp_alloc, zone_rows, demands)

            milp_entry = {
                "event_date": event_date,
                "engine": "MILP",
                "stock_pct": stock_pct,
                "inventory": inventory,
                "milp_status": milp_status,
                "effective_floor_pct": round(effective_floor * 100.0, 2),
                "aggregate_unmet_demand_pct": round(float(milp_metrics["aggregate_unmet_demand_pct"]), 2),
                "minimum_zone_coverage_pct": round(float(milp_metrics["minimum_zone_fairness_pct"]), 2),
                "weighted_service_score": round(float(milp_metrics["weighted_allocation_objective"]), 2),
                "zones_below_10_pct": m_b10,
                "zones_below_50_pct": m_b50,
                "coverage_std": round(m_std, 4),
                "coverage_gini": round(m_gini, 4),
                "zone_coverage_vector": [round(c, 4) for c in m_covers],
            }
            event_sweep_data.append(milp_entry)
            csv_rows.append({
                "event_date": event_date, "engine": "MILP", "stock_pct": stock_pct,
                "milp_status": milp_status, "effective_floor_pct": milp_entry["effective_floor_pct"],
                "aggregate_unmet_demand_pct": milp_entry["aggregate_unmet_demand_pct"],
                "minimum_zone_coverage_pct": milp_entry["minimum_zone_coverage_pct"],
                "weighted_service_score": milp_entry["weighted_service_score"],
                "zones_below_10_pct": m_b10, "zones_below_50_pct": m_b50,
                "coverage_std": round(m_std, 4), "coverage_gini": round(m_gini, 4),
            })

            # 2. Proportional Engine
            prop_alloc = _proportional(zone_rows, inventory)
            prop_metrics = _metrics("naive_proportional_baseline", prop_alloc, zone_rows, inventory, 0.0)
            p_covers, p_std, p_gini, p_b10, p_b50 = compute_zone_metrics(prop_alloc, zone_rows, demands)

            prop_entry = {
                "event_date": event_date,
                "engine": "naive_proportional_baseline",
                "stock_pct": stock_pct,
                "inventory": inventory,
                "aggregate_unmet_demand_pct": round(float(prop_metrics["aggregate_unmet_demand_pct"]), 2),
                "minimum_zone_coverage_pct": round(float(prop_metrics["minimum_zone_fairness_pct"]), 2),
                "weighted_service_score": round(float(prop_metrics["weighted_allocation_objective"]), 2),
                "zones_below_10_pct": p_b10,
                "zones_below_50_pct": p_b50,
                "coverage_std": round(p_std, 4),
                "coverage_gini": round(p_gini, 4),
                "zone_coverage_vector": [round(c, 4) for c in p_covers],
            }
            event_sweep_data.append(prop_entry)
            csv_rows.append({
                "event_date": event_date, "engine": "naive_proportional_baseline", "stock_pct": stock_pct,
                "milp_status": "N/A", "effective_floor_pct": round(effective_floor * 100.0, 2),
                "aggregate_unmet_demand_pct": prop_entry["aggregate_unmet_demand_pct"],
                "minimum_zone_coverage_pct": prop_entry["minimum_zone_coverage_pct"],
                "weighted_service_score": prop_entry["weighted_service_score"],
                "zones_below_10_pct": p_b10, "zones_below_50_pct": p_b50,
                "coverage_std": round(p_std, 4), "coverage_gini": round(p_gini, 4),
            })

            # 3. LinUCB Engine across 5 seeds
            seed_unmet: list[float] = []
            seed_min_cov: list[float] = []
            seed_scores: list[float] = []
            seed_b10: list[int] = []
            seed_b50: list[int] = []
            seed_stds: list[float] = []
            seed_ginis: list[float] = []
            seed_vectors: list[list[float]] = []

            for s in LINUCB_SEEDS:
                b_alloc = run_single_linucb(zone_rows, demands, inventory, severity, population, related_demands, seed=s)
                b_metrics = _metrics("LinUCB_contextual_bandit", b_alloc, zone_rows, inventory, 0.0)
                b_covers, b_std, b_gini, b_b10, b_b50 = compute_zone_metrics(b_alloc, zone_rows, demands)
                seed_unmet.append(float(b_metrics["aggregate_unmet_demand_pct"]))
                seed_min_cov.append(float(b_metrics["minimum_zone_fairness_pct"]))
                seed_scores.append(float(b_metrics["weighted_allocation_objective"]))
                seed_b10.append(b_b10)
                seed_b50.append(b_b50)
                seed_stds.append(b_std)
                seed_ginis.append(b_gini)
                seed_vectors.append(b_covers)

            mean_vector = [round(float(x), 4) for x in np.mean(seed_vectors, axis=0)]

            linucb_entry = {
                "event_date": event_date,
                "engine": "LinUCB_contextual_bandit",
                "stock_pct": stock_pct,
                "inventory": inventory,
                "aggregate_unmet_demand_pct": round(float(np.mean(seed_unmet)), 2),
                "aggregate_unmet_demand_min": round(float(np.min(seed_unmet)), 2),
                "aggregate_unmet_demand_max": round(float(np.max(seed_unmet)), 2),
                "minimum_zone_coverage_pct": round(float(np.mean(seed_min_cov)), 2),
                "minimum_zone_coverage_min": round(float(np.min(seed_min_cov)), 2),
                "minimum_zone_coverage_max": round(float(np.max(seed_min_cov)), 2),
                "weighted_service_score": round(float(np.mean(seed_scores)), 2),
                "weighted_service_score_min": round(float(np.min(seed_scores)), 2),
                "weighted_service_score_max": round(float(np.max(seed_scores)), 2),
                "zones_below_10_pct": int(round(float(np.mean(seed_b10)))),
                "zones_below_50_pct": int(round(float(np.mean(seed_b50)))),
                "coverage_std": round(float(np.mean(seed_stds)), 4),
                "coverage_gini": round(float(np.mean(seed_ginis)), 4),
                "zone_coverage_vector": mean_vector,
                "seeds_evaluated": LINUCB_SEEDS,
            }
            event_sweep_data.append(linucb_entry)
            csv_rows.append({
                "event_date": event_date, "engine": "LinUCB_contextual_bandit", "stock_pct": stock_pct,
                "milp_status": "N/A", "effective_floor_pct": round(effective_floor * 100.0, 2),
                "aggregate_unmet_demand_pct": linucb_entry["aggregate_unmet_demand_pct"],
                "minimum_zone_coverage_pct": linucb_entry["minimum_zone_coverage_pct"],
                "weighted_service_score": linucb_entry["weighted_service_score"],
                "zones_below_10_pct": linucb_entry["zones_below_10_pct"],
                "zones_below_50_pct": linucb_entry["zones_below_50_pct"],
                "coverage_std": linucb_entry["coverage_std"],
                "coverage_gini": linucb_entry["coverage_gini"],
                "aggregate_unmet_min": linucb_entry["aggregate_unmet_demand_min"],
                "aggregate_unmet_max": linucb_entry["aggregate_unmet_demand_max"],
                "min_zone_cov_min": linucb_entry["minimum_zone_coverage_min"],
                "min_zone_cov_max": linucb_entry["minimum_zone_coverage_max"],
            })

        # Save event json and csv
        event_json_path = processed / f"stock_sweep_{event_date}.json"
        event_csv_path = processed / f"stock_sweep_{event_date}.csv"
        with event_json_path.open("w", encoding="utf-8") as f:
            json.dump({
                "event_date": event_date,
                "stock_levels": [round(x * 100.0, 1) for x in SWEEP_GRID_PCTS],
                "total_modeled_need": total_demands,
                "records": event_sweep_data,
            }, f, indent=2)

        # Collect all unique fieldnames across all rows
        all_keys: list[str] = []
        for row in csv_rows:
            for k in row.keys():
                if k not in all_keys:
                    all_keys.append(k)

        fieldnames = all_keys
        with event_csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            writer.writerows(csv_rows)

        # Compute critical thresholds via bisection
        t_floor40 = bisect_smallest_40_pct_feasible(zone_rows, demands, total_demands, severity)
        t_unmet10 = bisect_unmet_demand_below_10_pct(zone_rows, demands, total_demands, severity)
        t_linucb_collapse = find_linucb_collapse_threshold([r for r in event_sweep_data if r["engine"] == "LinUCB_contextual_bandit"])

        thresholds = {
            "event_date": event_date,
            "smallest_stock_pct_for_40pct_floor_feasible": t_floor40,
            "stock_pct_unmet_demand_below_10pct": t_unmet10,
            "stock_pct_linucb_collapse_below_1pct": t_linucb_collapse,
            "methodology": "Exact bisection over OR-Tools CBC MILP hard fairness constraint and 5-seed LinUCB contextual bandit evaluations.",
        }
        thresholds_by_event[event_date] = thresholds
        print(f"[{event_date}] Thresholds: 40% floor feasible={t_floor40}%, unmet<10%={t_unmet10}%, LinUCB collapse={t_linucb_collapse}%")

        all_summary_rows.extend(csv_rows)

    # Save combined thresholds
    thresholds_path = processed / "stock_sweep_thresholds.json"
    with thresholds_path.open("w", encoding="utf-8") as f:
        json.dump(thresholds_by_event, f, indent=2)

    # Copy files to frontend public and dist data directories
    targets = [
        REPO_ROOT / "frontend" / "public" / "data",
        REPO_ROOT / "frontend" / "dist" / "data",
    ]
    for target_dir in targets:
        if target_dir.exists():
            for event_date in events:
                src_json = processed / f"stock_sweep_{event_date}.json"
                src_csv = processed / f"stock_sweep_{event_date}.csv"
                (target_dir / src_json.name).write_text(src_json.read_text(encoding="utf-8"), encoding="utf-8")
                (target_dir / src_csv.name).write_text(src_csv.read_text(encoding="utf-8"), encoding="utf-8")
            (target_dir / "stock_sweep_thresholds.json").write_text(thresholds_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"Copied sweep artifacts to {target_dir}")

    print("\nStock sweep completed successfully!")
    return thresholds_by_event


if __name__ == "__main__":
    run_stock_sweep()
