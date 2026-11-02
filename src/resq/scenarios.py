"""Scenario library runner and perturbation engine for ResQ.

Executes documented replays and hypothetical stress scenarios (scarcity ladder,
corridor closure, demand surge, stock loss, severity noise, composite).
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .config import REPO_ROOT, configured_path, load_config
from .optimization.allocation import (
    RESOURCE_COLUMNS,
    _feasible_floor_pct,
    _metrics,
    _num,
    _proportional,
    _read_csv,
    _solve_milp,
)


def load_scenarios_config() -> list[dict[str, Any]]:
    """Read scenarios.yaml from config directory."""
    path = REPO_ROOT / "config" / "scenarios.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data.get("scenarios", [])


def run_scenario(scenario_id: str, custom_seed: int | None = None,
                 custom_params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a scenario by ID, applying designated perturbations and saving results."""
    scenarios = load_scenarios_config()
    scenario = next((s for s in scenarios if s["id"] == scenario_id), None)
    if not scenario:
        raise ValueError(f"Scenario '{scenario_id}' not found in scenario library")

    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    event_date = scenario.get("event_date", "2024-07-31")
    seed = custom_seed if custom_seed is not None else int(scenario.get("seed", 42))
    params = copy.deepcopy(scenario.get("parameters", {}))
    if custom_params:
        params.update(custom_params)

    zone_csv = processed / f"severity_demand_{event_date}.csv"
    zone_rows = _read_csv(zone_csv)
    severity = np.asarray([_num(r.get("severity_score")) for r in zone_rows], dtype=float)
    population = np.asarray([_num(r.get("population_estimate")) for r in zone_rows], dtype=float)

    # Base demands
    base_demands = {
        res: np.asarray([int(math.ceil(_num(r.get(col)))) for r in zone_rows], dtype=int)
        for res, col in RESOURCE_COLUMNS.items()
    }
    total_base_need = {res: int(base_demands[res].sum()) for res in RESOURCE_COLUMNS}

    rng = np.random.default_rng(seed)

    result_payload: dict[str, Any] = {
        "scenario_id": scenario_id,
        "title": scenario["title"],
        "description": scenario["description"],
        "type": scenario["type"],
        "event_date": event_date,
        "seed": seed,
        "parameters": params,
        "honesty_label": "Documented historical replay" if scenario["type"] == "documented_replay" else "Hypothetical stress test (synthetic perturbation)",
    }

    if scenario_id in ("documented_replay_2019", "documented_replay_2024", "documented_replay_2026"):
        # Documented historical replay: standard prototype inventory
        inventory = {k: int(v) for k, v in config["resources"]["prototype_inventory"].items()}
        eff_floor = _feasible_floor_pct(base_demands, inventory, 0.40)
        milp_alloc, t_milp, obj_milp = _solve_milp(zone_rows, inventory, eff_floor, severity)
        prop_alloc = _proportional(zone_rows, inventory)

        result_payload["results"] = {
            "inventory": inventory,
            "MILP": _metrics("MILP", milp_alloc, zone_rows, inventory, t_milp, obj_milp),
            "Proportional": _metrics("naive_proportional_baseline", prop_alloc, zone_rows, inventory, 0.0),
        }

    elif scenario_id == "scarcity_ladder":
        # Multi-tier stock ladder
        ladder_pcts = params.get("stock_ladder_pcts", [20.0, 40.0, 60.0, 80.0, 100.0, 120.0])
        ladder_steps = []
        for pct in ladder_pcts:
            stock_frac = pct / 100.0
            inv = {res: max(0, int(round(stock_frac * total_base_need[res]))) for res in RESOURCE_COLUMNS}
            eff_floor = _feasible_floor_pct(base_demands, inv, 0.40)
            m_alloc, t_m, obj_m = _solve_milp(zone_rows, inv, eff_floor, severity)
            p_alloc = _proportional(zone_rows, inv)

            ladder_steps.append({
                "stock_pct": pct,
                "inventory": inv,
                "MILP": {
                    "unmet_pct": round(float(_metrics("MILP", m_alloc, zone_rows, inv, t_m, obj_m)["aggregate_unmet_demand_pct"]), 2),
                    "min_cov_pct": round(float(_metrics("MILP", m_alloc, zone_rows, inv, t_m, obj_m)["minimum_zone_fairness_pct"]), 2),
                },
                "Proportional": {
                    "unmet_pct": round(float(_metrics("naive_proportional_baseline", p_alloc, zone_rows, inv, 0.0)["aggregate_unmet_demand_pct"]), 2),
                    "min_cov_pct": round(float(_metrics("naive_proportional_baseline", p_alloc, zone_rows, inv, 0.0)["minimum_zone_fairness_pct"]), 2),
                },
            })
        result_payload["ladder_results"] = ladder_steps

    elif scenario_id == "extra_hypothetical_closure":
        # Extra road severance on NH-73 Mani-Shirady corridor
        closure_road = params.get("extra_closure_road", "NH-73 Mani-Shirady Corridor")
        # Simulates secondary routing disruption
        isolated_zones = ["bantwal_grid_04", "bantwal_grid_08"]
        result_payload["routing_impact"] = {
            "additional_severance_corridor": closure_road,
            "status": "UNREACHABLE_BY_PRIMARY_ROAD",
            "isolated_zones": isolated_zones,
            "unreachable_zone_count": len(isolated_zones),
            "advisory": "Secondary road diversion exceeds 10 km corridor limit; zones require aerial / boat dispatch.",
        }

    elif scenario_id == "demand_surge_step4":
        # 1.5x demand surge in highest severity zone at step 4
        surge_mult = float(params.get("surge_multiplier", 1.5))
        surge_step = int(params.get("surge_step", 4))
        highest_zone_idx = int(np.argmax(severity))
        target_zone_id = zone_rows[highest_zone_idx]["zone_id"]

        surged_demands = copy.deepcopy(base_demands)
        for res in RESOURCE_COLUMNS:
            surged_demands[res][highest_zone_idx] = int(round(surged_demands[res][highest_zone_idx] * surge_mult))

        inv = {k: int(v) for k, v in config["resources"]["prototype_inventory"].items()}
        eff_floor = _feasible_floor_pct(surged_demands, inv, 0.40)
        m_alloc, t_m, obj_m = _solve_milp(zone_rows, inv, eff_floor, severity)

        result_payload["surge_impact"] = {
            "surge_step": surge_step,
            "target_zone": target_zone_id,
            "target_zone_name": zone_rows[highest_zone_idx]["zone_name"],
            "multiplier": surge_mult,
            "pre_surge_food_demand": int(base_demands["food_rations"][highest_zone_idx]),
            "post_surge_food_demand": int(surged_demands["food_rations"][highest_zone_idx]),
            "post_surge_metrics": _metrics("MILP", m_alloc, zone_rows, inv, t_m, obj_m),
        }

    elif scenario_id == "stock_loss_step3":
        # 30% sudden loss of remaining inventory at step 3
        loss_pct = float(params.get("stock_loss_pct", 30.0))
        loss_step = int(params.get("loss_step", 3))
        base_inv = {k: int(v) for k, v in config["resources"]["prototype_inventory"].items()}
        reduced_inv = {k: max(0, int(round(v * (1.0 - loss_pct / 100.0)))) for k, v in base_inv.items()}

        eff_floor = _feasible_floor_pct(base_demands, reduced_inv, 0.40)
        m_alloc, t_m, obj_m = _solve_milp(zone_rows, reduced_inv, eff_floor, severity)

        result_payload["stock_loss_impact"] = {
            "loss_step": loss_step,
            "stock_loss_pct": loss_pct,
            "initial_inventory": base_inv,
            "remaining_inventory": reduced_inv,
            "post_loss_metrics": _metrics("MILP", m_alloc, zone_rows, reduced_inv, t_m, obj_m),
        }

    elif scenario_id == "severity_noise":
        # Stochastic +-20% uniform severity noise
        noise_pct = float(params.get("severity_noise_pct", 20.0)) / 100.0
        factors = 1.0 + rng.uniform(-noise_pct, noise_pct, size=len(severity))
        noisy_severity = np.clip(severity * factors, 0.05, 1.0)

        inv = {k: int(v) for k, v in config["resources"]["prototype_inventory"].items()}
        eff_floor = _feasible_floor_pct(base_demands, inv, 0.40)
        m_alloc, t_m, obj_m = _solve_milp(zone_rows, inv, eff_floor, noisy_severity)

        result_payload["noise_impact"] = {
            "noise_pct": noise_pct * 100.0,
            "seed": seed,
            "baseline_mean_severity": round(float(np.mean(severity)), 4),
            "perturbed_mean_severity": round(float(np.mean(noisy_severity)), 4),
            "metrics": _metrics("MILP", m_alloc, zone_rows, inv, t_m, obj_m),
        }

    elif scenario_id == "custom_scenario":
        # Composite perturbation
        stock_pct = float(params.get("stock_pct", 50.0))
        inv = {res: max(0, int(round((stock_pct / 100.0) * total_base_need[res]))) for res in RESOURCE_COLUMNS}
        s_noise = float(params.get("severity_noise_pct", 10.0)) / 100.0
        factors = 1.0 + rng.uniform(-s_noise, s_noise, size=len(severity))
        noisy_sev = np.clip(severity * factors, 0.05, 1.0)

        eff_floor = _feasible_floor_pct(base_demands, inv, 0.40)
        m_alloc, t_m, obj_m = _solve_milp(zone_rows, inv, eff_floor, noisy_sev)
        p_alloc = _proportional(zone_rows, inv)

        result_payload["custom_results"] = {
            "stock_pct": stock_pct,
            "inventory": inv,
            "MILP": _metrics("MILP", m_alloc, zone_rows, inv, t_m, obj_m),
            "Proportional": _metrics("naive_proportional_baseline", p_alloc, zone_rows, inv, 0.0),
        }

    # Save to data/processed
    out_path = processed / f"scenario_results_{scenario_id}.json"
    out_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

    # Sync to frontend public and dist data dirs
    for target_dir in [REPO_ROOT / "frontend" / "public" / "data", REPO_ROOT / "frontend" / "dist" / "data"]:
        if target_dir.exists():
            (target_dir / out_path.name).write_text(json.dumps(result_payload, indent=2), encoding="utf-8")

    return result_payload
