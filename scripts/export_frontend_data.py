"""Export precomputed data snapshots for offline demo mode in frontend/public/data."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from resq.config import REPO_ROOT, configured_path, load_config
from resq.events import load_events


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def export():
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    public_data = REPO_ROOT / "frontend" / "public" / "data"
    public_data.mkdir(parents=True, exist_ok=True)

    # 1. Events
    events = load_events()
    gauge_rows = read_csv(processed / "gauge_readings.csv") if (processed / "gauge_readings.csv").exists() else []
    gauge_thresholds = {
        row["event_date"]: row for row in gauge_rows if row.get("reading_type") == "peak"
    }
    events_data = {
        "scope": "Bantwal taluk; 16 analytical grid zones",
        "danger_mark_m": 9.0,
        "warning_level_m": 8.5,
        "events": [
            {
                "event_date": e.event_date.isoformat(),
                "river_gauge": e.river_gauge,
                "water_level_m": e.water_level_m,
                "danger_mark_m": float(gauge_thresholds.get(e.event_date.isoformat(), {}).get("danger_level_m") or 9.0),
                "warning_level_m": float(gauge_thresholds.get(e.event_date.isoformat(), {}).get("warning_level_m") or 8.5),
                "affected_localities": list(e.affected_localities),
                "roads_blocked": list(e.roads_blocked),
                "houses_affected": e.houses_affected,
                "source_urls": list(e.source_urls),
            }
            for e in events
        ],
    }
    (public_data / "events.json").write_text(json.dumps(events_data, indent=2), encoding="utf-8")
    print("Wrote events.json")

    # 2. GeoJSONs: analysis_zones, river, simplified_roads, warehouses
    for name in ("analysis_zones.geojson", "river.geojson", "simplified_roads.geojson", "warehouses.geojson"):
        src = processed / name
        if src.exists():
            shutil.copyfile(src, public_data / name)
            print(f"Copied {name}")

    # Stock sweep snapshots power the offline chart and stock slider. Preserve
    # the full computed grid instead of only exporting the API's nearest point.
    for event in load_events():
        day = event.event_date.isoformat()
        sweep = processed / f"stock_sweep_{day}.json"
        if sweep.exists():
            shutil.copyfile(sweep, public_data / sweep.name)
    thresholds = processed / "stock_sweep_thresholds.json"
    if thresholds.exists():
        shutil.copyfile(thresholds, public_data / thresholds.name)

    # 3. For each event: closures, zones with demand, routes, steps, escalations, svg
    for e in events:
        day = e.event_date.isoformat()

        # Offline replay snapshots for the explicitly labeled pooled-stock scenario.
        simulated_dir = processed / "simulated_coverage_scenario"
        for source_name, public_name in (
            (f"module6_allocation_matrix_{day}.csv", f"allocation_matrix_simulated_{day}.json"),
            (f"module8_dynamic_steps_{day}.csv", f"steps_simulated_{day}.json"),
            (f"allocation_metadata_{day}.json", f"allocation_metadata_simulated_{day}.json"),
            (f"escalation_log_{day}.csv", f"escalation_log_simulated_{day}.json"),
        ):
            source = simulated_dir / source_name
            if source.exists():
                if source.suffix == ".csv":
                    (public_data / public_name).write_text(json.dumps(read_csv(source), indent=2), encoding="utf-8")
                else:
                    shutil.copyfile(source, public_data / public_name)

        # Closures GeoJSON
        closure_file = processed / f"closures_{day}.geojson"
        if closure_file.exists():
            shutil.copyfile(closure_file, public_data / f"closures_{day}.geojson")

        # Zones with demand
        demand_rows = {r["zone_id"]: r for r in read_csv(processed / f"severity_demand_{day}.csv")}
        zones_geo = json.loads((processed / "analysis_zones.geojson").read_text(encoding="utf-8"))
        merged_zones = []
        for feat in zones_geo["features"]:
            zid = str(feat["properties"]["zone_id"])
            d = demand_rows[zid]
            merged_zones.append({
                "zone_id": zid,
                "zone_name": feat["properties"]["name"],
                "grid_row": feat["properties"]["grid_row"],
                "grid_column": feat["properties"]["grid_column"],
                "centroid_lat": feat["properties"]["centroid_lat"],
                "centroid_lon": feat["properties"]["centroid_lon"],
                "population_estimate": float(d["population_estimate"]),
                "population_status": "WorldPop modeled estimate",
                "population_year": 2025,
                "population_resolution": "1km",
                "population_density_per_km2": float(feat["properties"]["population_density_per_km2"]),
                "severity_score": float(d["severity_score"]),
                "severity_label": "modeled relative priority",
                "sar_likelihood": float(d["sar_likelihood"]),
                "sar_label": "candidate VH-change signal",
                "antecedent_7day_rainfall_mm": float(d["antecedent_7day_rainfall_mm"]),
                "estimated_affected_people": float(d["estimated_affected_people"]),
                "estimated_food_rations": int(float(d["estimated_food_rations"])),
                "estimated_water_liters": int(float(d["estimated_water_liters"])),
                "estimated_medical_kits": int(float(d["estimated_medical_kits"])),
            })
        (public_data / f"zones_{day}.json").write_text(json.dumps({
            "event": day,
            "scope": "Bantwal",
            "zones": merged_zones
        }, indent=2), encoding="utf-8")

        # Routes GeoJSON & CSV
        routes_geo = processed / f"routes_analysis_{day}.geojson"
        if routes_geo.exists():
            shutil.copyfile(routes_geo, public_data / f"routes_analysis_{day}.geojson")

        routes_csv = processed / f"routes_analysis_{day}.csv"
        if routes_csv.exists():
            (public_data / f"routes_{day}.json").write_text(
                json.dumps(read_csv(routes_csv), indent=2), encoding="utf-8"
            )

        # Module 8 steps
        steps_csv = processed / f"module8_dynamic_steps_{day}.csv"
        if steps_csv.exists():
            (public_data / f"steps_{day}.json").write_text(
                json.dumps(read_csv(steps_csv), indent=2), encoding="utf-8"
            )

        # Module 8 dynamic summary
        summary_json = processed / f"module8_dynamic_summary_{day}.json"
        if summary_json.exists():
            shutil.copyfile(summary_json, public_data / f"module8_dynamic_summary_{day}.json")

        # Escalations
        esc_csv = processed / f"escalation_log_{day}.csv"
        if esc_csv.exists():
            (public_data / f"escalation_log_{day}.json").write_text(
                json.dumps(read_csv(esc_csv), indent=2), encoding="utf-8"
            )

        # Allocations matrix
        alloc_csv = processed / f"allocation_matrix_{day}.csv"
        if alloc_csv.exists():
            (public_data / f"allocation_matrix_{day}.json").write_text(
                json.dumps(read_csv(alloc_csv), indent=2), encoding="utf-8"
            )
        alloc_metadata = processed / f"allocation_metadata_{day}.json"
        if alloc_metadata.exists():
            shutil.copyfile(alloc_metadata, public_data / f"allocation_metadata_{day}.json")

        # SVG candidate SAR
        svg_file = processed / f"flood_likelihood_{day}.svg"
        if svg_file.exists():
            shutil.copyfile(svg_file, public_data / f"flood_likelihood_{day}.svg")

    # 4. Adequate supply summary
    adequate_csv = REPO_ROOT / "demo" / "adequate_supply_summary.csv"
    if adequate_csv.exists():
        (public_data / "adequate_supply_summary.json").write_text(
            json.dumps(read_csv(adequate_csv), indent=2), encoding="utf-8"
        )

    # 5. SAR bounds metadata
    sar_meta = {
        "bounds": [74.934, 12.663, 75.224, 13.016],
        "center": [75.079, 12.840],
        "zoom": 11,
        "label": "candidate VH-change signal",
        "events": {
            "2019-08-10": {"svg": "/data/flood_likelihood_2019-08-10.svg"},
            "2024-07-31": {"svg": "/data/flood_likelihood_2024-07-31.svg"},
            "2026-08-03": {"svg": "/data/flood_likelihood_2026-08-03.svg"},
        }
    }
    (public_data / "sar_bounds.json").write_text(json.dumps(sar_meta, indent=2), encoding="utf-8")

    # Clip map display layers and SAR previews to the 16-zone Bantwal footprint.
    from build_frontend_map_assets import build as build_bantwal_map_assets
    build_bantwal_map_assets()
    print("Export complete.")


if __name__ == "__main__":
    export()
