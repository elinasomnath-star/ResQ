"""Compare a fair-constrained OR-Tools MILP with a lightweight LinUCB allocator."""

from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
from ortools.linear_solver import pywraplp

from ..config import configured_path, load_config
from ..events import load_events


RESOURCE_COLUMNS = {
    "food_rations": "estimated_food_rations",
    "water_liters": "estimated_water_liters",
    "medical_kits": "estimated_medical_kits",
}
RESOURCE_WEIGHTS = {"food_rations": 1.0, "water_liters": 1.2, "medical_kits": 3.0}


class MilpInfeasible(RuntimeError):
    """Raised when the requested hard min-zone coverage cannot fit inventory."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) and x > 0 else 0.0
    except (TypeError, ValueError): return 0.0


def _required_floor(demand: np.ndarray, pct: float) -> np.ndarray:
    """Integer units required for every zone to meet the common coverage floor."""
    return np.minimum(demand.astype(int), np.ceil(demand * max(0.0, pct) - 1e-12).astype(int))


def _feasible_floor_pct(demands: dict[str, np.ndarray], resources: dict[str, int],
                        requested_pct: float) -> float:
    """Largest common floor whose per-zone integer lower bounds fit every stock cap."""
    requested_pct = min(1.0, max(0.0, requested_pct))

    def feasible(pct: float) -> bool:
        return all(int(_required_floor(demand, pct).sum()) <= max(0, int(resources.get(resource, 0)))
                   for resource, demand in demands.items())

    if feasible(requested_pct):
        return requested_pct
    low, high = 0.0, requested_pct
    for _ in range(60):
        middle = (low + high) / 2
        if feasible(middle):
            low = middle
        else:
            high = middle
    return low


def _fair_floor(demand: np.ndarray, inventory: int, pct: float) -> np.ndarray:
    """Apply the requested floor when feasible, otherwise the largest feasible floor."""
    safe_pct = _feasible_floor_pct({"resource": demand}, {"resource": inventory}, pct)
    return _required_floor(demand, safe_pct)


def _solve_milp(zone_rows: list[dict[str, str]], resources: dict[str, int], fair_pct: float,
                severity: np.ndarray) -> tuple[dict[str, np.ndarray], float, float]:
    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None: raise RuntimeError("OR-Tools CBC solver is unavailable")
    solver.SetTimeLimit(20_000)
    n = len(zone_rows)
    allocation: dict[str, np.ndarray] = {}
    objective = solver.Objective()
    for resource, column in RESOURCE_COLUMNS.items():
        inventory = max(0, int(resources.get(resource, 0)))
        demand = np.asarray([int(math.ceil(_num(row.get(column)))) for row in zone_rows], dtype=int)
        # A hard lower bound: each zone receives at least ceil(target * need).
        # If this does not fit stock, CBC must report infeasible.
        floor = _required_floor(demand, fair_pct)
        vars_ = []
        for index, need in enumerate(demand):
            var = solver.IntVar(int(floor[index]), int(need), f"{resource}_{index}")
            vars_.append(var)
            urgency = 1.0 + max(0.0, float(severity[index]))
            objective.SetCoefficient(var, RESOURCE_WEIGHTS[resource] * urgency / max(1, int(need)))
        solver.Add(solver.Sum(vars_) <= inventory)
        allocation[resource] = np.asarray(vars_, dtype=object)
    objective.SetMaximization()
    start = time.perf_counter()
    status = solver.Solve()
    elapsed = time.perf_counter() - start
    if status == pywraplp.Solver.INFEASIBLE:
        raise MilpInfeasible("MILP status INFEASIBLE: hard min-zone fairness target exceeds available inventory")
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        raise RuntimeError(f"MILP did not find a feasible allocation (status={status})")
    return {resource: np.asarray([int(var.solution_value()) for var in vars_], dtype=int)
            for resource, vars_ in allocation.items()}, elapsed, float(objective.Value())


class LinUCB:
    """Small contextual bandit where each zone is an arm and actions allocate batches."""
    def __init__(self, arms: int, dim: int = 5, alpha: float = 0.45, ridge: float = 1.0):
        self.arms, self.dim, self.alpha = arms, dim, alpha
        self.A = np.tile(np.eye(dim, dtype=float) * ridge, (arms, 1, 1))
        # Keep A^-1 current with a rank-one Sherman–Morrison update. Repeated
        # np.linalg.inv calls for every arm at every decision dominated the
        # ward-scale dynamic benchmark runtime.
        self.A_inverse = np.tile(np.eye(dim, dtype=float) / ridge, (arms, 1, 1))
        self.b = np.zeros((arms, dim), dtype=float)

    def choose(self, contexts: np.ndarray, eligible: np.ndarray) -> int:
        choices = np.flatnonzero(eligible)
        if not len(choices):
            raise ValueError("LinUCB cannot choose an arm when none are eligible")
        inverses = self.A_inverse[choices]
        x = contexts[choices]
        theta = np.einsum("aij,aj->ai", inverses, self.b[choices])
        means = np.einsum("ai,ai->a", theta, x)
        variance = np.maximum(0.0, np.einsum("ai,aij,aj->a", x, inverses, x))
        return int(choices[int(np.argmax(means + self.alpha * np.sqrt(variance)))])

    def update(self, arm: int, context: np.ndarray, reward: float) -> None:
        inverse = self.A_inverse[arm]
        projected = inverse @ context
        denominator = 1.0 + float(context @ projected)
        self.A_inverse[arm] = inverse - np.outer(projected, projected) / denominator
        self.A[arm] += np.outer(context, context)
        self.b[arm] += reward * context


def _context(severity: np.ndarray, demand: np.ndarray, allocated: np.ndarray,
             population: np.ndarray) -> np.ndarray:
    need_left = np.maximum(0, demand - allocated)
    fraction = np.divide(need_left, np.maximum(1, demand))
    coverage = np.divide(allocated, np.maximum(1, demand))
    pop_norm = np.divide(np.log1p(population), max(1.0, float(np.max(np.log1p(population)))))
    return np.column_stack([np.ones(len(demand)), severity, fraction, np.maximum(0.0, 0.4 - coverage), pop_norm])


def _train_contextual_bandit(demands: list[np.ndarray], severities: np.ndarray,
                             populations: np.ndarray, inventory: int, fair_pct: float,
                             seed: int) -> tuple[LinUCB, float, int]:
    start = time.perf_counter()
    policy = LinUCB(len(severities))
    rng = np.random.default_rng(seed)
    episodes = 120
    for _ in range(episodes):
        base = demands[int(rng.integers(0, len(demands)))].astype(float)
        scenario = np.maximum(0, np.rint(base * rng.uniform(0.55, 1.45, size=len(base)))).astype(int)
        stock = int(max(0, round(inventory * rng.uniform(0.75, 1.25))))
        allocated = _fair_floor(scenario, stock, fair_pct)
        remaining = max(0, stock - int(allocated.sum()))
        batch = max(1, stock // 60)
        for _step in range(60):
            eligible = allocated < scenario
            if remaining <= 0 or not np.any(eligible): break
            ctx = _context(severities, scenario, allocated, populations)
            arm = policy.choose(ctx, eligible)
            amount = min(batch, remaining, int(scenario[arm] - allocated[arm]))
            if amount <= 0: break
            before = allocated[arm] / max(1, scenario[arm])
            allocated[arm] += amount
            after = allocated[arm] / max(1, scenario[arm])
            # LinUCB learns a different objective from the MILP: contextual
            # urgency plus a deliberate reward for reducing coverage gaps.
            coverage_gain = after - before
            population_priority = math.log1p(populations[arm]) / max(1.0, float(np.max(np.log1p(populations))))
            fairness_gap = max(0.0, 0.4 - before)
            reward = coverage_gain * (1.0 + 0.65 * severities[arm] + 0.35 * population_priority)
            reward += coverage_gain * 0.8 * fairness_gap
            policy.update(arm, ctx[arm], float(reward))
            remaining -= amount
    return policy, time.perf_counter() - start, episodes


def _bandit_allocate(policy: LinUCB, zone_rows: list[dict[str, str]], resources: dict[str, int],
                     fair_pct: float, severity: np.ndarray, populations: np.ndarray) -> tuple[dict[str, np.ndarray], float]:
    start = time.perf_counter()
    result = {}
    for resource, column in RESOURCE_COLUMNS.items():
        stock = max(0, int(resources.get(resource, 0)))
        demand = np.asarray([int(math.ceil(_num(row.get(column)))) for row in zone_rows], dtype=int)
        allocated = _fair_floor(demand, stock, fair_pct)
        remaining = max(0, stock - int(allocated.sum()))
        batch = max(1, stock // 100)
        for _step in range(120):
            eligible = allocated < demand
            if remaining <= 0 or not np.any(eligible): break
            contexts = _context(severity, demand, allocated, populations)
            arm = policy.choose(contexts, eligible)
            amount = min(batch, remaining, int(demand[arm] - allocated[arm]))
            allocated[arm] += amount
            remaining -= amount
        result[resource] = allocated
    return result, time.perf_counter() - start


def _proportional(zone_rows: list[dict[str, str]], resources: dict[str, int]) -> dict[str, np.ndarray]:
    result = {}
    for resource, column in RESOURCE_COLUMNS.items():
        demand = np.asarray([int(math.ceil(_num(row.get(column)))) for row in zone_rows], dtype=int)
        stock = max(0, int(resources.get(resource, 0)))
        fraction = min(1.0, stock / max(1, int(demand.sum())))
        allocated = np.floor(demand * fraction).astype(int)
        # Assign integer remainders to the currently least-served eligible
        # zone. Stable index-order remainders bias late zones under scarcity.
        left = stock - int(allocated.sum())
        while left > 0:
            eligible = np.flatnonzero(allocated < demand)
            if not len(eligible):
                break
            index = min(eligible, key=lambda i: (allocated[i] / max(1, demand[i]), i))
            allocated[index] += 1
            left -= 1
        result[resource] = allocated
    return result


def _metrics(engine: str, allocation: dict[str, np.ndarray], zone_rows: list[dict[str, str]],
             resources: dict[str, int], elapsed: float, objective: float | None = None) -> dict[str, Any]:
    zone_coverages = []
    weighted_served = 0.0
    pop_total = 0.0
    for i, row in enumerate(zone_rows):
        covers = []
        urgency = 1.0 + _num(row.get("severity_score"))
        for resource, column in RESOURCE_COLUMNS.items():
            need = int(math.ceil(_num(row.get(column))))
            got = int(allocation[resource][i])
            covers.append(min(1.0, got / need) if need else 1.0)
            weighted_served += RESOURCE_WEIGHTS[resource] * urgency * min(got, need) / max(1, need)
        zone_coverages.append(min(covers))
        population = _num(row.get("population_estimate"))
        pop_total += population
        if population: weighted_served += 0.0
    unmet_pct_by_resource = {}
    for resource, column in RESOURCE_COLUMNS.items():
        total_need = sum(int(math.ceil(_num(row.get(column)))) for row in zone_rows)
        total_allocated = sum(min(int(allocation[resource][i]), int(math.ceil(_num(row.get(column)))))
                              for i, row in enumerate(zone_rows))
        unmet_pct_by_resource[resource] = 100.0 * max(0, total_need - total_allocated) / total_need if total_need else 0.0
    medical_need = sum(int(math.ceil(_num(row.get(RESOURCE_COLUMNS["medical_kits"])))) for row in zone_rows)
    medical_got = int(allocation["medical_kits"].sum())
    weighted_population_cover = 0.0
    for i, row in enumerate(zone_rows):
        weighted_population_cover += _num(row.get("population_estimate")) * zone_coverages[i]
    return {
        "engine": engine, "solve_or_inference_time_seconds": elapsed,
        "aggregate_unmet_demand_pct": float(np.mean(list(unmet_pct_by_resource.values()))) if unmet_pct_by_resource else 0.0,
        **{f"{resource}_unmet_demand_pct": pct for resource, pct in unmet_pct_by_resource.items()},
        "minimum_zone_fairness_pct": 100.0 * min(zone_coverages, default=1.0),
        "critical_medical_demand_satisfied_pct": 100.0 * min(1.0, medical_got / medical_need) if medical_need else 100.0,
        "population_coverage_pct": 100.0 * weighted_population_cover / pop_total if pop_total else 0.0,
        "weighted_allocation_objective": objective if objective is not None else weighted_served,
        "inventory_used": json.dumps({r: int(allocation[r].sum()) for r in RESOURCE_COLUMNS}),
    }


def run_allocators(event_date: str, config: dict[str, Any] | None = None) -> tuple[Path, Path]:
    config = config or load_config()
    processed = configured_path(config["data"]["processed_dir"])
    zone_rows = _read_csv(processed / f"severity_demand_{event_date}.csv")
    if not zone_rows: raise ValueError(f"No severity/demand rows found for {event_date}")
    resource_cfg = config["resources"]
    inventory = {key: int(value) for key, value in resource_cfg["prototype_inventory"].items()}
    fair_pct = float(resource_cfg.get("min_fairness_pct", 40)) / 100.0
    severity = np.asarray([_num(row.get("severity_score")) for row in zone_rows], dtype=float)
    population = np.asarray([_num(row.get("population_estimate")) for row in zone_rows], dtype=float)
    demands_by_resource = {
        resource: np.asarray([int(math.ceil(_num(row.get(column)))) for row in zone_rows], dtype=int)
        for resource, column in RESOURCE_COLUMNS.items()
    }
    requested_floor = fair_pct
    effective_floor = _feasible_floor_pct(demands_by_resource, inventory, requested_floor)
    hard_target_status = "FEASIBLE"
    try:
        milp_alloc, milp_time, milp_objective = _solve_milp(zone_rows, inventory, requested_floor, severity)
    except MilpInfeasible:
        hard_target_status = "INFEASIBLE"
        print(f"[{event_date}] hard fairness target {requested_floor:.0%}: INFEASIBLE; rerunning shortage MILP at maximum feasible floor {effective_floor:.2%}")
        # Keep a useful shortage-regime comparator, but label it explicitly:
        # this second MILP enforces the mathematically largest feasible floor.
        milp_alloc, milp_time, milp_objective = _solve_milp(zone_rows, inventory, effective_floor, severity)
    # Train the contextual bandit from perturbed scenarios seeded by all real
    # event-demand vectors; scenarios remain synthetic, as recorded below.
    train_start = time.perf_counter()
    bandit_models = {}
    bandit_train_time = 0.0
    episodes = 0
    for resource, demand in demands_by_resource.items():
        related = []
        for date_str in (event.event_date.isoformat() for event in load_events()):
            candidate = processed / f"severity_demand_{date_str}.csv"
            if candidate.exists():
                rows = _read_csv(candidate)
                if len(rows) == len(zone_rows):
                    related.append(np.asarray([int(math.ceil(_num(row.get(RESOURCE_COLUMNS[resource])))) for row in rows], dtype=int))
        if not related: related = [demand]
        policy, training_time, count = _train_contextual_bandit(related, severity, population,
                                                                inventory.get(resource, 0), requested_floor,
                                                                seed=sum(map(ord, event_date + resource)))
        bandit_models[resource] = policy
        bandit_train_time += training_time
        episodes = max(episodes, count)
    bandit_train_time = max(bandit_train_time, time.perf_counter() - train_start)

    # For each resource retain a separately trained policy and use it to allocate.
    bandit_start = time.perf_counter()
    bandit_alloc = {}
    for resource, column in RESOURCE_COLUMNS.items():
        policy = bandit_models[resource]
        stock = max(0, inventory.get(resource, 0))
        demand = np.asarray([int(math.ceil(_num(row.get(column)))) for row in zone_rows], dtype=int)
        allocated = _fair_floor(demand, stock, effective_floor)
        remaining, batch = max(0, stock - int(allocated.sum())), max(1, stock // 100)
        for _ in range(120):
            eligible = allocated < demand
            if remaining <= 0 or not np.any(eligible): break
            contexts = _context(severity, demand, allocated, population)
            arm = policy.choose(contexts, eligible)
            amount = min(batch, remaining, int(demand[arm] - allocated[arm]))
            allocated[arm] += amount; remaining -= amount
        bandit_alloc[resource] = allocated
    bandit_inference = time.perf_counter() - bandit_start
    baseline_alloc = _proportional(zone_rows, inventory)
    metric_rows = [
        _metrics("MILP", milp_alloc, zone_rows, inventory, milp_time, milp_objective),
        _metrics("LinUCB_contextual_bandit", bandit_alloc, zone_rows, inventory, bandit_inference),
        _metrics("naive_proportional_baseline", baseline_alloc, zone_rows, inventory, 0.0),
    ]
    for row in metric_rows:
        row.update({"event_date": event_date, "bandit_training_time_seconds": bandit_train_time,
                    "bandit_training_episodes": episodes,
                    "requested_fairness_target_pct": 100.0 * requested_floor,
                    "effective_feasible_floor_pct": 100.0 * effective_floor,
                    "hard_fairness_target_status": hard_target_status,
                    "scenario_training_basis": "perturbed modeled demand vectors from the three-event validation set; synthetic simulation only"})
    detail_rows = []
    allocation_map = {"MILP": milp_alloc, "LinUCB_contextual_bandit": bandit_alloc,
                      "naive_proportional_baseline": baseline_alloc}
    for engine, allocations in allocation_map.items():
        for i, zone in enumerate(zone_rows):
            for resource, column in RESOURCE_COLUMNS.items():
                detail_rows.append({
                    "event_date": event_date, "engine": engine, "zone_id": zone["zone_id"],
                    "zone_name": zone["zone_name"], "resource": resource,
                    "estimated_need": int(math.ceil(_num(zone.get(column)))),
                    "allocated": int(allocations[resource][i]),
                    "unmet": max(0, int(math.ceil(_num(zone.get(column)))) - int(allocations[resource][i])),
                    "unmet_pct": 100.0 * max(0, int(math.ceil(_num(zone.get(column)))) - int(allocations[resource][i])) / max(1, int(math.ceil(_num(zone.get(column))))),
                    "inventory_source": "unlocated district prototype pool (config assumption)",
                })
    zone_metric_rows = []
    for engine, allocations in allocation_map.items():
        for i, zone in enumerate(zone_rows):
            coverage = {}
            unmet_pct = {}
            for resource, column in RESOURCE_COLUMNS.items():
                need = int(math.ceil(_num(zone.get(column))))
                allocated = int(allocations[resource][i])
                coverage[resource] = min(1.0, allocated / need) if need else 1.0
                unmet_pct[resource] = 100.0 * max(0, need - allocated) / need if need else 0.0
            zone_metric_rows.append({
                "event_date": event_date, "engine": engine, "zone_id": zone["zone_id"],
                "zone_name": zone["zone_name"],
                "minimum_resource_coverage_pct": 100.0 * min(coverage.values()),
                "mean_resource_coverage_pct": 100.0 * float(np.mean(list(coverage.values()))),
                "food_rations_unmet_pct": unmet_pct["food_rations"],
                "water_liters_unmet_pct": unmet_pct["water_liters"],
                "medical_kits_unmet_pct": unmet_pct["medical_kits"],
                "food_rations_unmet": int(math.ceil(_num(zone.get(RESOURCE_COLUMNS["food_rations"])))) - int(allocations["food_rations"][i]),
                "water_liters_unmet": int(math.ceil(_num(zone.get(RESOURCE_COLUMNS["water_liters"])))) - int(allocations["water_liters"][i]),
                "medical_kits_unmet": int(math.ceil(_num(zone.get(RESOURCE_COLUMNS["medical_kits"])))) - int(allocations["medical_kits"][i]),
            })
    detail_path = processed / f"allocation_matrix_{event_date}.csv"
    metric_path = processed / f"allocation_comparison_{event_date}.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(detail_rows[0])); writer.writeheader(); writer.writerows(detail_rows)
    with metric_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(metric_rows[0])); writer.writeheader(); writer.writerows(metric_rows)
    zone_metric_path = processed / f"allocation_zone_metrics_{event_date}.csv"
    with zone_metric_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(zone_metric_rows[0])); writer.writeheader(); writer.writerows(zone_metric_rows)
    metadata = {"event_date": event_date, "solver": "OR-Tools CBC MILP", "bandit": "Linear UCB contextual bandit",
                "requested_hard_fairness_pct": requested_floor * 100,
                "hard_fairness_target_status": hard_target_status,
                "maximum_feasible_common_floor_pct": effective_floor * 100,
                "milp_final_enforced_floor_pct": effective_floor * 100,
                "prototype_inventory_assumption": inventory,
                "training_episodes_per_resource": episodes,
                "effective_fairness_floor_pct_by_resource": {
                    resource: 100.0 * _feasible_floor_pct(
                        {resource: demands_by_resource[resource]},
                        {resource: inventory.get(resource, 0)}, requested_floor)
                    for resource, column in RESOURCE_COLUMNS.items()},
                "note": "The MILP first enforces the requested hard fairness floor. If infeasible, it records INFEASIBLE and reruns a separately labeled shortage solution at the maximum common floor that fits inventory. Inventory quantities and demand conversions are prototype assumptions."}
    (processed / f"allocation_metadata_{event_date}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return detail_path, metric_path


def main() -> None:
    """Regenerate allocation comparisons after demand artifacts are available."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-date", action="append", help="event date; repeat to select multiple events")
    args = parser.parse_args()
    wanted = set(args.event_date or [])
    events = [e.event_date.isoformat() for e in load_events() if not wanted or e.event_date.isoformat() in wanted]
    if wanted and wanted != set(events):
        raise ValueError(f"Unconfigured event date(s): {sorted(wanted - set(events))}")
    for day in events:
        detail, metrics = run_allocators(day)
        print(f"[{day}] Allocation matrix: {detail}")
        print(f"[{day}] Engine comparison: {metrics}")


if __name__ == "__main__":
    main()

