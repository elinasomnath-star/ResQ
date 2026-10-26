"""Check hard fairness feasibility at current and synthetic inventory levels."""

from __future__ import annotations

import json
import math

import numpy as np

from resq.config import configured_path, load_config
from resq.events import load_events
from resq.optimization.allocation import (
    RESOURCE_COLUMNS,
    MilpInfeasible,
    _feasible_floor_pct,
    _read_csv,
    _solve_milp,
)


def main() -> None:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    target = float(config["resources"].get("min_fairness_pct", 40)) / 100.0
    configured_inventory = {k: int(v) for k, v in config["resources"]["prototype_inventory"].items()}
    results = []
    for event in load_events():
        day = event.event_date.isoformat()
        rows = _read_csv(processed / f"severity_demand_{day}.csv")
        severity = np.asarray([float(r["severity_score"]) for r in rows], dtype=float)
        demands = {
            resource: np.asarray([int(math.ceil(float(r[column]))) for r in rows], dtype=int)
            for resource, column in RESOURCE_COLUMNS.items()
        }
        feasible_floor = _feasible_floor_pct(demands, configured_inventory, target)
        try:
            _solve_milp(rows, configured_inventory, target, severity)
            hard_status = "FEASIBLE"
        except MilpInfeasible:
            hard_status = "INFEASIBLE"
        assert hard_status == ("FEASIBLE" if feasible_floor >= target - 1e-9 else "INFEASIBLE")

        # Synthetic stress supply at 50% of each resource's total event demand
        # must satisfy the requested 40% floor, including integer rounding.
        synthetic_inventory = {
            resource: int(math.ceil(float(demand.sum()) * 0.5))
            for resource, demand in demands.items()
        }
        alloc, _, objective = _solve_milp(rows, synthetic_inventory, target, severity)
        actual_floor = min(
            min((int(alloc[resource][i]) / int(demand[i])) if demand[i] else 1.0
                for i in range(len(rows)))
            for resource, demand in demands.items()
        )
        assert actual_floor >= target - 1e-9
        results.append({
            "event_date": day,
            "requested_hard_floor_pct": target * 100,
            "current_inventory_hard_status": hard_status,
            "current_inventory_max_feasible_floor_pct": feasible_floor * 100,
            "synthetic_inventory_basis": "50% of each resource's total modeled demand",
            "synthetic_inventory": synthetic_inventory,
            "synthetic_hard_status": "FEASIBLE",
            "synthetic_achieved_min_zone_coverage_pct": actual_floor * 100,
            "synthetic_milp_objective": objective,
        })
    output = processed / "module6_fairness_feasibility.json"
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Validated hard fairness feasibility for {len(results)} events; wrote {output}")


if __name__ == "__main__":
    main()
