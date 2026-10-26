"""Run the Phase II headless pipeline from public observations to allocation."""

from __future__ import annotations

import argparse
import json

from .config import configured_path, load_config
from .events import load_events
from .rainfall import write_event_rainfall
from .severity.sar import process_event
from .ml.demand import run_demand_model
from .optimization.allocation import run_allocators
from .zones import ensure_event_locality_assignments
from .subzones import build_grid, summarize_cached_inputs
from .population import estimate_zone_populations


def run(event_dates: list[str] | None = None) -> None:
    config = load_config()
    events = load_events()
    requested_dates = set(event_dates or [])
    configured_dates = {event.event_date.isoformat() for event in events}
    unknown_dates = requested_dates.difference(configured_dates)
    if unknown_dates:
        raise ValueError(f"Unconfigured event date(s): {sorted(unknown_dates)}")
    selected = [event for event in events if not requested_dates or event.event_date.isoformat() in requested_dates]
    if not selected:
        raise ValueError(f"No configured events matched {event_dates}")
    added_localities = ensure_event_locality_assignments(config=config)
    if added_localities:
        print(f"Synchronized {added_localities} new event-locality names to the configured taluk fallback zone")
    zones_path = configured_path(config["data"]["zones_path"])
    analysis_zones_path = configured_path(config["data"].get("analysis_zones_path", config["data"]["zones_path"]))
    if not analysis_zones_path.exists():
        build_grid(config)
    zones = json.loads(analysis_zones_path.read_text(encoding="utf-8"))["features"]
    expected_population_year = int(config["region"].get("population_model_year", 2025))
    if any(int(z["properties"].get("population_year") or 0) != expected_population_year or
           float(z["properties"].get("population_estimate") or 0) <= 0 for z in zones):
        parent_features = json.loads(zones_path.read_text(encoding="utf-8"))["features"]
        parent = next((f for f in parent_features if str(f.get("properties", {}).get("name", "")).casefold().startswith("bantwal")), None)
        control_total = float((parent or {}).get("properties", {}).get("population_estimate") or 0)
        if control_total <= 0:
            raise ValueError("Bantwal parent population is missing; run python -m resq.population after python -m resq.zones")
        estimate_zone_populations(path=analysis_zones_path, year=expected_population_year,
                                  config=config, control_total=control_total)
        zones = json.loads(analysis_zones_path.read_text(encoding="utf-8"))["features"]
    for event in selected:
        day = event.event_date.isoformat()
        print(f"[{day}] Fetching 7-day CHIRPS and Sentinel-1/HAND inputs")
        write_event_rainfall(event.event_date, zones, config)
        tif, table, manifest = process_event(event, config)
        print(f"[{day}] SAR raster: {tif}")
        print(f"[{day}] Zone severity table: {table}")
        print(f"[{day}] Heatmap SVG: {manifest['generated_outputs'][-1]}")
        print(f"[{day}] SAR dates: {manifest['before_date']} -> {manifest['during_date']}")
    summarize_cached_inputs(config)
    print("Fitting severity/demand model and generating estimates")
    run_demand_model(selected, config)
    for event in selected:
        day = event.event_date.isoformat()
        detail, metrics = run_allocators(day, config)
        print(f"[{day}] Allocation matrix: {detail}")
        print(f"[{day}] Engine comparison: {metrics}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-date", action="append", help="process one or more configured event dates")
    args = parser.parse_args()
    run(args.event_date)


if __name__ == "__main__":
    main()
