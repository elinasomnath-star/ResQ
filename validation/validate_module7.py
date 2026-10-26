"""Check the A* road-route engine and coordinate-driven edge removal."""

from __future__ import annotations

import json
import sys

from shapely.geometry import shape

from resq.config import configured_path, load_config
from resq.events import load_events
from resq.routing import _load_graph, compute_routes, run_routing


def main() -> None:
    config = load_config()
    graph_path = configured_path(config["data"]["road_graph_path"])
    zone_path = configured_path(config["data"]["zones_path"])
    zones = json.loads(zone_path.read_text(encoding="utf-8"))["features"]
    bantwal = next(f for f in zones if f["properties"]["name"].casefold().startswith("bantwal"))
    point = shape(bantwal["geometry"]).representative_point()
    # This is a route-engine scenario fixture at a taluk polygon point, not a
    # claim that an actual warehouse exists there.
    origin = {"origin_id": "module7_validation_scenario", "lon": point.x, "lat": point.y,
              "origin_source": "validation_scenario_origin"}
    rows, details = compute_routes(graph_path=graph_path, zone_path=zone_path, origins=[origin])
    assert len(rows) == len(zones)
    assert details["reachable_road_count"] >= 1
    assert all(r["road_distance_m"] is not None for r in rows if r["delivery_mode"] == "road")

    graph, zone = _load_graph(graph_path)
    selected = next((data for _u, _v, data in graph.edges(data=True)
                     if data.get("length", 0) >= 100 and len(data.get("geometry", [])) >= 2), None)
    assert selected is not None, "No road edge suitable for the closure-removal check"
    a, b = selected["geometry"][0], selected["geometry"][1]
    closure = ((float(a[0]) + float(b[0])) / 2, (float(a[1]) + float(b[1])) / 2)
    _rows_after_closure, closure_details = compute_routes(
        graph_path=graph_path, zone_path=zone_path, origins=[origin], closure_points=[closure],
        closure_radius_m=10,
    )
    assert closure_details["closures"], "The test closure did not remove any OSM graph edges"
    print(f"Module 7 A* validation passed: {len(rows)} zones, {details['reachable_road_count']} road routes; "
          f"coordinate closure removed {len(closure_details['closures'])} directed edges.")
    print("Origin is a validation scenario point, not an operational warehouse.")

    processed = configured_path(config["data"]["processed_dir"])
    warehouse_path = processed / "warehouses.geojson"
    missing: list[str] = []
    if not warehouse_path.exists():
        missing.append("warehouses.geojson is missing")
    else:
        warehouse_data = json.loads(warehouse_path.read_text(encoding="utf-8"))
        if not any((f.get("geometry") or {}).get("type") == "Point" and
                   f.get("properties", {}).get("route_origin", True)
                   for f in warehouse_data.get("features", [])):
            missing.append("warehouses.geojson contains no verified routable Point origin")
    event_results = []
    for event in load_events():
        event_date = event.event_date.isoformat()
        closure_path = processed / f"closures_{event_date}.geojson"
        if not closure_path.exists():
            event_results.append((event_date, "BLOCKED", "closure file missing"))
            continue
        data = json.loads(closure_path.read_text(encoding="utf-8"))
        verified = [f for f in data.get("features", [])
                    if f.get("properties", {}).get("status") == "verified" and
                    (f.get("geometry") or {}).get("type") in {"Point", "LineString", "MultiLineString"}]
        unresolved = sum(f.get("properties", {}).get("status") != "verified" for f in data.get("features", []))
        if not verified:
            event_results.append((event_date, "BLOCKED", "no verified closure point/OSM way geometry"))
            continue
        try:
            route_csv, _route_geojson = run_routing(event_date, zone_layer="taluk")
            routes = json.loads((processed / f"routes_taluk_{event_date}_metadata.json").read_text(encoding="utf-8"))
            removed = len(routes.get("closures", []))
            status = "PARTIAL PASS" if unresolved else "PASS"
            event_results.append((event_date, status,
                                  f"{len(verified)} verified closure feature(s), {removed} directed graph edges removed, "
                                  f"{routes.get('reachable_road_count', 0)} road routes; outputs {route_csv.name}"))
        except Exception as exc:
            event_results.append((event_date, "FAILED", f"{type(exc).__name__}: {exc}"))
    for event_date, status, details in event_results:
        print(f"Module 7 real-event {status} [{event_date}]: {details}")
    failures = [result for result in event_results if result[1] in {"BLOCKED", "FAILED"}]
    if missing or failures:
        for item in missing:
            print(f"Module 7 real-event integration FAILED: {item}")
        if failures:
            print(f"Module 7 real-event integration incomplete: {len(failures)} of {len(event_results)} events have no validated route.")
        sys.exit(1)
    print("Module 7 real-event integration validation passed for all configured events.")


if __name__ == "__main__":
    main()
