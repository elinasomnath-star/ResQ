"""Run a cached-data routing/escalation walkthrough for one configured event."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resq.config import configured_path, load_config  # noqa: E402
from resq.events import load_events  # noqa: E402
from resq.routing import _load_graph, _nearest_node, block_matching_lines  # noqa: E402


def load_closure_lines(path: Path) -> list[dict]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    lines = []
    for feature in collection.get("features", []):
        geometry, props = feature.get("geometry"), feature.get("properties", {})
        if props.get("status") != "verified" or not geometry:
            continue
        if geometry["type"] == "LineString":
            lines.append({**props, "coordinates": geometry["coordinates"]})
        elif geometry["type"] == "MultiLineString":
            lines.append({**props, "coordinate_parts": geometry["coordinates"]})
    if not lines:
        raise ValueError(f"No verified cached road closure line in {path}")
    return lines


def path_roads(graph, path: list[str]) -> list[str]:
    distance = sum(float(graph[a][b]["length"]) for a, b in zip(path, path[1:]))
    road_names = []
    for a, b in zip(path, path[1:]):
        name = str(graph[a][b].get("name") or "").strip()
        if name and name not in road_names:
            road_names.append(name)
    return road_names or ["unnamed road segments"]


def find_largest_detour(day: str, graph, zone_number: int, processed: Path,
                        config: dict) -> tuple[dict | None, int, object]:
    import networkx as nx
    from shapely.geometry import Point, shape

    facilities = json.loads((processed / "warehouses.geojson").read_text(encoding="utf-8"))["features"]
    zones = json.loads(configured_path(config["data"]["zones_path"]).read_text(encoding="utf-8"))["features"]
    bantwal = next(feature for feature in zones
                   if feature["properties"].get("name", "").casefold().startswith("bantwal"))
    focus = shape(bantwal["geometry"])

    points = []
    for feature in facilities:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Point":
            lon, lat = map(float, geometry["coordinates"][:2])
            if focus.covers(Point(lon, lat)):
                points.append({"name": feature["properties"].get("name", "facility"),
                               "lon": lon, "lat": lat, "kind": "facility"})
    snapped = []
    for point in points:
        node, snap = _nearest_node(graph, float(point["lon"]), float(point["lat"]), zone_number)
        if snap <= float(config.get("routing", {}).get("max_snap_distance_m", 5000)):
            snapped.append({**point, "node": node, "snap_m": snap})

    closure_lines = load_closure_lines(processed / f"closures_{day}.geojson")
    closed_graph = graph.copy()
    removed = block_matching_lines(
        closed_graph, closure_lines, zone_number,
        tolerance_m=float(config.get("routing", {}).get("blockage_snap_radius_m", 35)),
    )
    removed_pairs = {(row["source"], row["target"]): row for row in removed}
    if not removed_pairs:
        return None, 0, closed_graph

    # One single-source shortest-path run per snapped origin makes exhaustive
    # point-pair comparison fast enough for a live cached-data demo.
    baseline_by_node = {}
    closed_by_node = {}
    for origin in snapped:
        node = origin["node"]
        if node not in baseline_by_node:
            baseline_by_node[node] = nx.single_source_dijkstra(graph, node, weight="length")
            closed_by_node[node] = nx.single_source_dijkstra(closed_graph, node, weight="length")

    best = None
    for i, origin in enumerate(snapped):
        base_distances, base_paths = baseline_by_node[origin["node"]]
        closed_distances, closed_paths = closed_by_node[origin["node"]]
        for j, destination in enumerate(snapped):
            if i == j or origin["node"] == destination["node"]:
                continue
            target = destination["node"]
            if target not in base_distances or target not in closed_distances:
                continue
            base_path = base_paths[target]
            crossing = [removed_pairs[(a, b)] for a, b in zip(base_path, base_path[1:])
                        if (a, b) in removed_pairs]
            if not crossing:
                continue
            before = float(base_distances[target])
            after = float(closed_distances[target])
            candidate = {
                "origin": origin, "destination": destination,
                "before_m": before, "after_m": after,
                "extra_m": max(0.0, after - before),
                "before_path": base_path, "after_path": closed_paths[target],
                "affected_roads": sorted({row.get("name") or "unnamed verified OSM way" for row in crossing}),
                "crossing_edges": len(crossing),
            }
            if best is None or candidate["extra_m"] > best["extra_m"]:
                best = candidate
    return best, len(removed), closed_graph


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_date", help="configured event date, e.g. 2019-08-10")
    day = parser.parse_args().event_date
    if day not in {event.event_date.isoformat() for event in load_events()}:
        parser.error(f"unknown event date: {day}")

    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    graph_path = configured_path(config["data"]["road_graph_path"])
    zones_path = configured_path(config["data"]["zones_path"])
    warehouse_path = processed / "warehouses.geojson"
    closures_path = processed / f"closures_{day}.geojson"

    warehouses = json.loads(warehouse_path.read_text(encoding="utf-8"))["features"]
    origin = next((feature for feature in warehouses
                   if feature.get("geometry", {}).get("type") == "Point"
                   and feature.get("properties", {}).get("route_origin", True)), None)
    if origin is None:
        raise ValueError("No cached routable warehouse Point exists")
    graph, zone_number = _load_graph(graph_path)
    print(f"Event: {day}")
    best, removed_count, closed_graph = find_largest_detour(day, graph, zone_number, processed, config)
    if best is None:
        print("No candidate origin-destination pair has a full-graph shortest route crossing a verified closure edge.")
        print("The event's verified closure geometry was left unchanged; no detour route was applied.")
    else:
        before_roads = path_roads(graph, best["before_path"])
        # Recover the source geometry's road label for the closure edge crossed.
        print(f"Origin: {best['origin']['name']} ({best['origin']['kind']}) -> "
              f"{best['destination']['name']} ({best['destination']['kind']})")
        print(f"Route before: {best['before_m'] / 1000:.2f} km ({' -> '.join(before_roads[:6])})")
        print(f"Route after: {best['after_m'] / 1000:.2f} km "
              f"({' -> '.join(path_roads(closed_graph, best['after_path'])[:6])})")
        print(f"Extra distance: {best['extra_m'] / 1000:.2f} km")
        print(f"Road affected: {'; '.join(best['affected_roads'])}; "
              f"closure removes {removed_count} directed edges")

    alert_path = processed / f"escalation_log_{day}.csv"
    with alert_path.open(newline="", encoding="utf-8-sig") as stream:
        alerts = list(csv.DictReader(stream))
    print("First three escalation log rows:")
    for row in alerts[:3]:
        print(f"  step={row['step']} engine={row['engine']} short={row['resource_types_short']} "
              f"transfers={row['transfer_count']}")


if __name__ == "__main__":
    main()
