"""Run a near-adequate Module 8 scenario with clearly simulated shelter stocks."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape

from resq.config import REPO_ROOT, configured_path, load_config
from resq.events import load_events
from resq.module8 import run_module8
from resq.optimization.allocation import run_allocators


RESOURCES = ("food_rations", "water_liters", "medical_kits")
ENGINES = ("MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]]) -> tuple[float, dict[str, float], float, float]:
    totals = {resource: [0, 0] for resource in RESOURCES}
    zones: dict[str, dict[str, list[int]]] = {}
    for row in rows:
        need, unmet = int(float(row["final_scenario_need"])), int(float(row["final_unmet"]))
        totals[row["resource"]][0] += need
        totals[row["resource"]][1] += unmet
        resource_totals = zones.setdefault(row["zone_id"], {})
        values = resource_totals.setdefault(row["resource"], [0, 0])
        values[0] += need
        values[1] += need - unmet
    per_resource = {r: (100 * u / n if n else 0.0) for r, (n, u) in totals.items()}
    overall = sum(per_resource.values()) / len(RESOURCES)
    floor = min((100 * served / need if need else 100.0)
                for resource_totals in zones.values()
                for need, served in resource_totals.values())
    zone_means = [sum(served / need if need else 1.0 for need, served in resources.values()) /
                  max(1, len(resources)) for resources in zones.values()]
    mean_zone_coverage = 100.0 * sum(zone_means) / len(zone_means) if zone_means else 100.0
    return overall, per_resource, floor, mean_zone_coverage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-unmet-pct", type=float, default=8.0,
                        help="target unmet demand for non-severe event records, between 0 and 10 percent")
    parser.add_argument("--severe-event-date", default="2019-08-10",
                        help="event record to give the separate severe-case supply assumption")
    parser.add_argument("--severe-event-unmet-pct", type=float, default=1.5,
                        help="target unmet demand for the severe-case event, between 0 and 10 percent")
    args = parser.parse_args()
    if not (0 < args.target_unmet_pct < 10 and 0 < args.severe_event_unmet_pct < 10):
        raise ValueError("Both target unmet-demand values must be greater than 0 and less than 10 percent")

    config = load_config()
    # This separate adequacy scenario models a service floor above 50% so the
    # per-zone coverage chart cannot hide an underserved cell behind a good
    # aggregate. The configured-stock benchmark retains its normal 40% target.
    scenario_fairness_floor_pct = 55.0
    config["resources"]["min_fairness_pct"] = scenario_fairness_floor_pct
    source = configured_path(config["data"]["processed_dir"])
    configured_days = {event.event_date.isoformat() for event in load_events()}
    if args.severe_event_date not in configured_days:
        raise ValueError(f"Unknown severe event date {args.severe_event_date}; choose one of {sorted(configured_days)}")
    tag = "simulated_coverage_scenario"
    target = source / tag
    target.mkdir(parents=True, exist_ok=True)
    for name in ("warehouses.geojson",):
        shutil.copy2(source / name, target / name)
    for event in load_events():
        day = event.event_date.isoformat()
        for name in (f"severity_demand_{day}.csv", f"closures_{day}.geojson"):
            shutil.copy2(source / name, target / name)

    # These geocoded event-confirmed points are used only for a transparent
    # presentation split. Module 8 receives the combined pool, without depot caps.
    site_doc = json.loads((source / "warehouses.geojson").read_text(encoding="utf-8"))
    parent_doc = json.loads((source / "zones.geojson").read_text(encoding="utf-8"))
    focus_geometry = shape(parent_doc["features"][0]["geometry"])
    sites = [f for f in site_doc["features"]
             if (f.get("geometry") or {}).get("type") == "Point"
             and f.get("properties", {}).get("source") == "event-confirmed"
             and focus_geometry.covers(Point(*map(float, f["geometry"]["coordinates"][:2])))]
    if not sites:
        raise RuntimeError("No geocoded event-confirmed relief-site points are available")

    config["data"]["processed_dir"] = str(target)
    summary: list[dict[str, Any]] = []
    site_rows: list[dict[str, Any]] = []
    for event in load_events():
        day = event.event_date.isoformat()
        event_target_pct = (args.severe_event_unmet_pct if day == args.severe_event_date
                            else args.target_unmet_pct)
        baseline = read_csv(source / f"module8_dynamic_zone_unmet_{day}.csv")
        demand_rows = [r for r in baseline if r["engine"] == "MILP"]
        needs = {resource: sum(int(float(r["final_scenario_need"])) for r in demand_rows
                               if r["resource"] == resource) for resource in RESOURCES}
        inventory = {resource: max(1, int(round(need * (1 - event_target_pct / 100))))
                     for resource, need in needs.items()}
        severity_rows = read_csv(target / f"severity_demand_{day}.csv")
        static_need_columns = {
            "food_rations": "estimated_food_rations",
            "water_liters": "estimated_water_liters",
            "medical_kits": "estimated_medical_kits",
        }
        static_needs = {resource: sum(int(float(r[column])) for r in severity_rows)
                        for resource, column in static_need_columns.items()}
        static_inventory = {resource: max(1, int(round(need * (1 - event_target_pct / 100))))
                            for resource, need in static_needs.items()}

        for resource, total in inventory.items():
            base, remainder = divmod(total, len(sites))
            for i, feature in enumerate(sites):
                props = feature["properties"]
                qty = base + (1 if i < remainder else 0)
                site_rows.append({
                    "event_date": day, "facility_id": props["warehouse_id"],
                    "facility_name": props["name"],
                    "longitude": feature["geometry"]["coordinates"][0],
                    "latitude": feature["geometry"]["coordinates"][1],
                    "resource": resource, "simulated_quantity": qty,
                    "split_rule": "equal split; integer remainder assigned in listed order",
                    "inventory_status": "synthetic scenario only; not actual shelter stock",
                    "allocation_scope": "Module 8 consumes combined pool; no depot constraints modeled",
                })

        config["resources"]["prototype_inventory"] = static_inventory
        static_detail_path, _ = run_allocators(day, config=config)
        static_metrics = read_csv(target / f"allocation_zone_metrics_{day}.csv")
        static_comparisons = read_csv(target / f"allocation_comparison_{day}.csv")
        static_allocations = read_csv(static_detail_path)
        shutil.copy2(target / f"allocation_zone_metrics_{day}.csv",
                     target / f"module6_allocation_zone_metrics_{day}.csv")
        shutil.copy2(target / f"allocation_comparison_{day}.csv",
                     target / f"module6_allocation_comparison_{day}.csv")
        shutil.copy2(target / f"allocation_matrix_{day}.csv",
                     target / f"module6_allocation_matrix_{day}.csv")
        # Module 8's finer-zone demand is a different scale. Give that run a
        # separately calculated synthetic pool at the same unmet-demand target.
        config["resources"]["prototype_inventory"] = inventory
        steps_path, _ = run_module8(day, config=config)
        generated = read_csv(target / f"module8_dynamic_zone_unmet_{day}.csv")
        for engine in ENGINES:
            current = [r for r in generated if r["engine"] == engine]
            base_rows = [r for r in baseline if r["engine"] == engine]
            overall, per_resource, floor, mean_zone_coverage = summarize(current)
            baseline_pct, _, _, _ = summarize(base_rows)
            static_engine = [r for r in static_metrics if r["engine"] == engine]
            static_mean_coverage = sum(float(r["mean_resource_coverage_pct"]) for r in static_engine) / max(1, len(static_engine))
            static_min_coverage = min((float(r["minimum_resource_coverage_pct"]) for r in static_engine), default=0.0)
            static_comparison = next(r for r in static_comparisons if r["engine"] == engine)
            static_unmet = float(static_comparison["aggregate_unmet_demand_pct"])
            if not (0 < overall < 10 and 50 <= floor < 100):
                raise RuntimeError(f"Module 8 scenario coverage/unmet check failed for {day} {engine}: "
                                   f"unmet={overall:.3f}%, minimum coverage={floor:.3f}%")
            if not (0 < static_unmet < 10 and 50 <= static_min_coverage < 100):
                raise RuntimeError(f"Module 6 scenario coverage/unmet check failed for {day} {engine}: "
                                   f"unmet={static_unmet:.3f}%, minimum coverage={static_min_coverage:.3f}%")
            for resource in RESOURCES:
                static_used = sum(int(r["allocated"]) for r in static_allocations
                                  if r["engine"] == engine and r["resource"] == resource)
                if static_used > static_inventory[resource]:
                    raise RuntimeError(f"Module 6 exceeded {resource} stock for {day} {engine}")
                dynamic_used = sum(int(r["cumulative_allocated"]) for r in current if r["resource"] == resource)
                if dynamic_used > inventory[resource]:
                    raise RuntimeError(f"Module 8 exceeded {resource} stock for {day} {engine}")
            summary.append({
                "event_date": day, "engine": engine, "steps": 8,
                "scenario_target_unmet_pct": event_target_pct,
                "scenario_minimum_fairness_floor_pct": scenario_fairness_floor_pct,
                "inventory_basis": "synthetic pooled planning stock; not measured facility inventory",
                "food_rations_need": needs["food_rations"], "food_rations_stock": inventory["food_rations"],
                "water_liters_need": needs["water_liters"], "water_liters_stock": inventory["water_liters"],
                "medical_kits_need": needs["medical_kits"], "medical_kits_stock": inventory["medical_kits"],
                "module6_food_need": static_needs["food_rations"], "module6_food_stock": static_inventory["food_rations"],
                "module6_water_need": static_needs["water_liters"], "module6_water_stock": static_inventory["water_liters"],
                "module6_medical_need": static_needs["medical_kits"], "module6_medical_stock": static_inventory["medical_kits"],
                "configured_baseline_unmet_pct": round(baseline_pct, 4),
                "module6_scenario_unmet_pct": round(static_unmet, 4),
                "simulated_unmet_pct": round(overall, 4),
                "food_unmet_pct": round(per_resource["food_rations"], 4),
                "water_unmet_pct": round(per_resource["water_liters"], 4),
                "medical_unmet_pct": round(per_resource["medical_kits"], 4),
                "minimum_zone_coverage_pct": round(floor, 4),
                "mean_zone_resource_coverage_pct": round(mean_zone_coverage, 4),
                "static_mean_zone_coverage_pct": round(static_mean_coverage, 4),
                "static_minimum_zone_coverage_pct": round(static_min_coverage, 4),
                "module6_allocation_matrix": str(target / f"module6_allocation_matrix_{day}.csv"),
                "module8_steps_file": str(steps_path),
            })
        print(f"[{day}] simulated supply scenario complete: {steps_path}")

    demo = REPO_ROOT / "demo"
    write_csv(demo / "adequate_supply_summary.csv", summary)
    write_csv(demo / "simulated_relief_centre_inventory.csv", site_rows)
    metadata = {
        "scenario": tag,
        "standard_event_target_unmet_pct": args.target_unmet_pct,
        "severe_event_date": args.severe_event_date,
        "severe_event_target_unmet_pct": args.severe_event_unmet_pct,
        "inventory_basis": "synthetic scenario only; not actual relief-centre stock",
        "site_split": "equal split across geocoded event-confirmed relief-site points",
        "allocation_scope": "Module 8 consumes combined pool; no depot constraints modeled",
        "steps": 8,
        "summary_csv": "adequate_supply_summary.csv",
        "site_inventory_csv": "simulated_relief_centre_inventory.csv",
    }
    (demo / "adequate_supply_scenario.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Wrote {demo / 'adequate_supply_summary.csv'}")


if __name__ == "__main__":
    main()
