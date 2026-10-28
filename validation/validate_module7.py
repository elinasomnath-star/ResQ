"""Validate Module 7 routing over all Bantwal analysis cells and real closures."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from resq.config import configured_path, load_config
from resq.events import load_events
from resq.routing import _load_graph, run_routing


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    zones_path = configured_path(config["data"].get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
    zones = json.loads(zones_path.read_text(encoding="utf-8"))["features"]
    expected_ids = {str(f["properties"]["zone_id"]) for f in zones}
    if len(zones) != 16 or len(expected_ids) != 16:
        raise ValueError(f"Module 7 requires exactly 16 unique Bantwal grid zones; found {len(zones)} features")

    warehouse_path = processed / "warehouses.geojson"
    facilities = json.loads(warehouse_path.read_text(encoding="utf-8"))["features"]
    origins = []
    for feature in facilities:
        geometry, props = feature.get("geometry") or {}, feature.get("properties") or {}
        if geometry.get("type") != "Point" or not props.get("route_origin", True):
            continue
        lon, lat = map(float, geometry["coordinates"][:2])
        origins.append({"origin_id": str(props.get("warehouse_id", props.get("name", len(origins)))),
                        "lon": lon, "lat": lat, "origin_source": props.get("source", "warehouses_geojson")})
    if not origins:
        raise ValueError("warehouses.geojson has no routable facility point; Module 7 will not invent an origin")

    graph_path = configured_path(config["data"]["road_graph_path"])
    graph, _utm_zone = _load_graph(graph_path)
    max_distance = float(config.get("routing", {}).get("secondary_max_distance_km", 10))
    cap = float(config.get("resources", {}).get("secondary_payload_kg", 50))
    if cap <= 0:
        raise ValueError("secondary_payload_kg must be positive")

    failures = []
    event_results = []
    validation_rows = []
    for event in load_events():
        day = event.event_date.isoformat()
        closure_path = processed / f"closures_{day}.geojson"
        if not closure_path.exists():
            failures.append(f"{day}: closure file missing")
            continue
        closure_doc = json.loads(closure_path.read_text(encoding="utf-8"))
        features = closure_doc.get("features", [])
        verified = [f for f in features if (f.get("properties") or {}).get("status") == "verified"
                    and f.get("geometry") and f["geometry"].get("type") in {"Point", "LineString", "MultiLineString"}]
        unresolved = [f for f in features if (f.get("properties") or {}).get("status") != "verified"]
        if not verified:
            failures.append(f"{day}: no verified closure point/OSM line geometry")
            continue
        try:
            route_csv, route_geojson = run_routing(day, zone_layer="analysis")
            rows = read_csv(route_csv)
            metadata = json.loads((processed / f"routes_analysis_{day}_metadata.json").read_text(encoding="utf-8"))
            route_features = json.loads(route_geojson.read_text(encoding="utf-8")).get("features", [])
            row_ids = {r["zone_id"] for r in rows}
            if len(rows) != 16 or row_ids != expected_ids:
                raise AssertionError(f"expected one route row for each of 16 zones, found {len(rows)} rows / {len(row_ids)} IDs")
            removed = metadata.get("closures", [])
            if not removed:
                raise AssertionError("verified closure geometry removed no directed road edges")
            removed_pairs = {(r["source"], r["target"]) for r in removed}
            road_count = secondary_count = no_mode_count = 0
            for row in rows:
                mode = row["delivery_mode"]
                if mode == "road":
                    road_count += 1
                    if row.get("road_status") != "ROUTED" or float(row["road_distance_m"]) < 0:
                        raise AssertionError(f"invalid road route row for {row['zone_id']}")
                    path = json.loads(row["path_node_ids"])
                    if not path or any(not graph.has_edge(a, b) or (a, b) in removed_pairs for a, b in zip(path, path[1:])):
                        raise AssertionError(f"route for {row['zone_id']} uses a missing or closed graph edge")
                elif mode == "secondary":
                    secondary_count += 1
                    distance = float(row["secondary_distance_km"])
                    if row.get("road_status") != "UNREACHABLE_BY_ROAD" or distance > max_distance + 1e-9:
                        raise AssertionError(f"secondary fallback for {row['zone_id']} exceeds its configured range")
                    if float(row["secondary_payload_capacity_kg"]) != cap:
                        raise AssertionError(f"secondary capacity is missing for {row['zone_id']}")
                    if row.get("secondary_status") == "REQUIRES_MULTIPLE_TRIPS":
                        trips = int(row["secondary_trip_count"])
                        if trips * cap < float(row["payload_kg_required"]):
                            raise AssertionError(f"secondary payload cap is violated for {row['zone_id']}")
                else:
                    no_mode_count += 1
                    if row.get("road_status") != "UNREACHABLE_BY_ROAD":
                        raise AssertionError(f"unserved zone {row['zone_id']} lacks an unreachable-by-road flag")
                validation_rows.append({"event_date": day, **row})
            if len(route_features) != road_count + secondary_count:
                raise AssertionError("route GeoJSON feature count does not match routed CSV rows")
            status = "PARTIAL PASS" if unresolved else "PASS"
            event_results.append((day, status,
                                  f"16 zones: {road_count} road, {secondary_count} secondary candidates, "
                                  f"{no_mode_count} without an eligible mode; {len(removed)} directed edges removed; "
                                  f"{len(unresolved)} closure labels unresolved; CSV {route_csv.name}"))
        except Exception as exc:
            failures.append(f"{day}: {type(exc).__name__}: {exc}")
            event_results.append((day, "FAILED", f"{type(exc).__name__}: {exc}"))

    validation_path = processed / "module7_route_validation.csv"
    if validation_rows:
        with validation_path.open("w", newline="", encoding="utf-8") as stream:
            fields = sorted({key for row in validation_rows for key in row})
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(validation_rows)
    for day, status, detail in event_results:
        print(f"Module 7 real-event {status} [{day}]: {detail}")
    if failures:
        print("Module 7 validation failures:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print(f"Module 7 validation passed for 16 grid zones across {len(event_results)} events; route audit: {validation_path}")


if __name__ == "__main__":
    main()
