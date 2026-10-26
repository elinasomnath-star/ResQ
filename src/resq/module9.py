"""Rule-based escalation alerts and temporary allocation redirects (Module 9)."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .config import configured_path, load_config
from .optimization.allocation import RESOURCE_COLUMNS


def assess_shortage(*, event_date: str, step: int, engine: str,
                    inventory: dict[str, int], demands: dict[str, np.ndarray],
                    allocated: dict[str, np.ndarray], threshold: float,
                    zone_ids: list[str]) -> dict[str, Any] | None:
    """Trigger if remaining inventory covers less than `threshold` of unmet need."""
    if not 0 <= threshold <= 1:
        raise ValueError("shortage threshold must be between zero and one")
    remaining_unmet: dict[str, int] = {}
    ratios: dict[str, float | None] = {}
    shortfall: dict[str, int] = {}
    short_resources: list[str] = []
    affected: set[str] = set()
    for resource in RESOURCE_COLUMNS:
        unmet_by_zone = np.maximum(0, demands[resource] - allocated[resource])
        unmet = int(unmet_by_zone.sum())
        stock = max(0, int(inventory.get(resource, 0)))
        remaining_unmet[resource] = unmet
        ratios[resource] = (stock / unmet) if unmet else None
        shortfall[resource] = max(0, unmet - stock)
        if unmet and stock < threshold * unmet:
            short_resources.append(resource)
            affected.update(zone_ids[i] for i in np.flatnonzero(unmet_by_zone > 0))
    if not short_resources:
        return None
    return {
        "event_date": event_date, "step": step, "engine": engine,
        "threshold": threshold, "resource_types_short": short_resources,
        "remaining_inventory": {r: max(0, int(inventory.get(r, 0))) for r in RESOURCE_COLUMNS},
        "remaining_unmet_demand": remaining_unmet,
        "inventory_to_unmet_ratio": ratios, "shortfall_by_resource": shortfall,
        "affected_zone_ids": sorted(affected),
    }


def minimum_zone_coverage(demands: dict[str, np.ndarray],
                          allocated: dict[str, np.ndarray]) -> float:
    """Return minimum zone/resource coverage as a fraction in [0, 1]."""
    values = []
    for resource in RESOURCE_COLUMNS:
        for need, got in zip(demands[resource], allocated[resource]):
            values.append(min(1.0, int(got) / int(need)) if int(need) else 1.0)
    return min(values, default=1.0)


def global_min_zone_coverage(demands: dict[str, np.ndarray],
                             allocated: dict[str, np.ndarray],
                             zone_ids: list[str]) -> tuple[list[str], float]:
    """Return all tied global-minimum zones and their current coverage fraction."""
    per_zone = []
    for index, zone_id in enumerate(zone_ids):
        coverages = [min(1.0, int(allocated[resource][index]) / int(demands[resource][index]))
                     if int(demands[resource][index]) else 1.0
                     for resource in RESOURCE_COLUMNS]
        per_zone.append((zone_id, min(coverages, default=1.0)))
    minimum = min((value for _, value in per_zone), default=1.0)
    zones = [zone_id for zone_id, value in per_zone if math.isclose(value, minimum, rel_tol=0, abs_tol=1e-12)]
    return zones, minimum


def apply_partial_reallocation(*, event_date: str, step: int, engine: str,
                               trigger_id: str, trigger: dict[str, Any],
                               demands: dict[str, np.ndarray],
                               allocated: dict[str, np.ndarray],
                               severity: np.ndarray, zone_ids: list[str],
                               step_global_min_zones: list[str],
                               step_global_min_value: float,
                               fairness_floor: float,
                               redirect_pct: float) -> list[dict[str, Any]]:
    """Redirect limited allocated stock from a donor above floor to an urgent zone."""
    if not 0 <= fairness_floor <= 1:
        raise ValueError("fairness floor must be between zero and one")
    if not 0 <= redirect_pct <= 1:
        raise ValueError("redirect percentage must be between zero and one")
    transfers: list[dict[str, Any]] = []
    if redirect_pct == 0:
        return transfers

    for resource in trigger["resource_types_short"]:
        demand = demands[resource]
        stock = allocated[resource]
        floors = np.ceil(demand * fairness_floor).astype(int)
        below = [i for i, zone_id in enumerate(zone_ids)
                 if zone_id in step_global_min_zones and demand[i] > 0 and stock[i] < floors[i]]
        above = [i for i in range(len(zone_ids)) if demand[i] > 0 and stock[i] > floors[i]]
        if not below or not above:
            continue
        # Restrict recipients to zones at the freshly recomputed global minimum.
        # If none of those zones is below this resource's fairness floor, this
        # resource has no eligible worst-served recipient for this trigger.
        recipient = max(below, key=lambda i: (float(severity[i]), -i))
        above = [i for i in above if i != recipient]
        if not above:
            continue
        donor = min(above, key=lambda i: (float(severity[i]), i))
        donor_before, recipient_before = int(stock[donor]), int(stock[recipient])
        inventory_total_before = int(stock.sum())
        requested = int(math.floor(donor_before * redirect_pct))
        transferable = min(requested, donor_before - int(floors[donor]),
                           int(floors[recipient]) - recipient_before,
                           int(demand[recipient]) - recipient_before)
        if transferable <= 0:
            continue
        stock[donor] -= transferable
        stock[recipient] += transferable
        transfers.append({
            "event_date": event_date, "step": step, "engine": engine,
            "trigger_id": trigger_id, "resource_type": resource,
            "donor_zone_id": zone_ids[donor], "recipient_zone_id": zone_ids[recipient],
            "donor_severity": float(severity[donor]),
            "recipient_severity": float(severity[recipient]),
            "donor_allocated_before": donor_before,
            "donor_allocated_after": int(stock[donor]),
            "recipient_allocated_before": recipient_before,
            "recipient_allocated_after": int(stock[recipient]),
            "donor_demand": int(demand[donor]),
            "recipient_demand": int(demand[recipient]),
            "redirected_quantity": transferable,
            "redirect_pct_configured": redirect_pct,
            "fairness_floor_pct": fairness_floor * 100,
            "donor_floor_quantity": int(floors[donor]),
            "recipient_floor_quantity": int(floors[recipient]),
            "global_min_zone_ids_before": ";".join(step_global_min_zones),
            "global_min_value_before_pct": step_global_min_value * 100,
            "recipient_matches_global_min": zone_ids[recipient] in step_global_min_zones,
            "inventory_total_before": inventory_total_before,
            "inventory_total_after": int(stock.sum()),
        })
    return transfers


def write_module9_artifacts(processed: Path, event_date: str,
                            triggers: list[dict[str, Any]],
                            transfers: list[dict[str, Any]]) -> tuple[Path, Path]:
    """Write an alert log and auditable resource-transfer rows."""
    alert_path = processed / f"escalation_log_{event_date}.csv"
    transfer_path = processed / f"escalation_reallocation_{event_date}.csv"
    alert_fields = ["trigger_id", "event_date", "step", "engine", "threshold",
                    "resource_types_short", "shortfall_by_resource",
                    "remaining_inventory", "remaining_unmet_demand",
                    "inventory_to_unmet_ratio", "affected_zone_ids",
                    "transfer_count", "min_zone_coverage_before_pct",
                    "min_zone_coverage_after_pct"]
    alert_path.parent.mkdir(parents=True, exist_ok=True)
    with alert_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=alert_fields)
        writer.writeheader()
        for trigger in triggers:
            row = {key: trigger.get(key) for key in alert_fields}
            row["resource_types_short"] = ";".join(trigger["resource_types_short"])
            row["affected_zone_ids"] = ";".join(trigger["affected_zone_ids"])
            for key in ("shortfall_by_resource", "remaining_inventory",
                        "remaining_unmet_demand", "inventory_to_unmet_ratio"):
                row[key] = json.dumps(row[key], sort_keys=True)
            writer.writerow(row)
    transfer_fields = ["event_date", "step", "engine", "trigger_id", "resource_type",
                       "donor_zone_id", "recipient_zone_id", "donor_severity",
                       "recipient_severity", "donor_allocated_before", "donor_allocated_after",
                       "recipient_allocated_before", "recipient_allocated_after",
                       "donor_demand", "recipient_demand",
                       "redirected_quantity", "redirect_pct_configured", "fairness_floor_pct",
                       "donor_floor_quantity", "recipient_floor_quantity",
                       "global_min_zone_ids_before", "global_min_value_before_pct",
                       "recipient_matches_global_min",
                       "inventory_total_before", "inventory_total_after"]
    with transfer_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=transfer_fields)
        writer.writeheader()
        writer.writerows(transfers)
    return alert_path, transfer_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-date", action="append")
    args = parser.parse_args()
    processed = configured_path(load_config()["data"]["processed_dir"])
    dates = args.event_date or [p.stem.removeprefix("module8_dynamic_summary_")
                                for p in sorted(processed.glob("module8_dynamic_summary_*.json"))]
    if not dates:
        raise SystemExit("No Module 8 summaries found; run Module 8 first.")
    for day in dates:
        summary = json.loads((processed / f"module8_dynamic_summary_{day}.json").read_text(encoding="utf-8"))
        if not summary.get("module9", {}).get("integrated"):
            raise SystemExit(f"{day} Module 8 output has no integrated Module 9 triggers; rerun Module 8.")
        print(f"[{day}] Module 9 artifacts: {processed / f'escalation_log_{day}.csv'}")


if __name__ == "__main__":
    main()
