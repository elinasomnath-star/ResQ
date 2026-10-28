"""Module 7: A* routes on the cached directed OSM road graph.

Routes can use configured warehouse coordinates or an explicitly supplied
scenario origin. Blockage points are coordinates supplied by a caller; this
module does not infer exact closure coordinates from locality names.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import networkx as nx
from shapely.geometry import LineString, shape

from .config import configured_path, load_config
from .events import load_events
from .osm import haversine_m, utm_project
from .roads import _read_graph_nodes


def _load_graph(path: Path) -> tuple[nx.DiGraph, int]:
    raw = nx.read_graphml(path, force_multigraph=True)
    if not raw.is_directed():
        raise ValueError("The cached OSM graph must preserve one-way road directions")
    graph = nx.DiGraph()
    for node, values in raw.nodes(data=True):
        data = dict(values)
        for key in ("x", "y", "lat", "lon"):
            data[key] = float(data[key])
        graph.add_node(str(node), **data)
    for u, v, values in raw.edges(data=True):
        data = dict(values)
        data["length"] = float(data["length"])
        data["geometry"] = json.loads(data.get("geometry", "[]"))
        source, target = str(u), str(v)
        if not graph.has_edge(source, target) or data["length"] < graph[source][target]["length"]:
            graph.add_edge(source, target, **data)
    nodes, zone, _hemisphere = _read_graph_nodes(path)
    if not nodes:
        raise ValueError("The road graph contains no nodes")
    return graph, zone


def _nearest_node(graph: nx.DiGraph, lon: float, lat: float, zone: int) -> tuple[str, float]:
    x, y, _, _ = utm_project(lon, lat, zone)
    node = min(graph.nodes, key=lambda n: (graph.nodes[n]["x"] - x) ** 2 + (graph.nodes[n]["y"] - y) ** 2)
    return str(node), math.hypot(graph.nodes[node]["x"] - x, graph.nodes[node]["y"] - y)


def _segment_distance(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - a[0], point[1] - a[1])
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy))


def block_near_points(graph: nx.DiGraph, points: list[tuple[float, float]], zone: int,
                      radius_m: float) -> list[dict[str, Any]]:
    """Remove road edges within `radius_m` of each (lon,lat) closure point."""
    removed: list[dict[str, Any]] = []
    for lon, lat in points:
        px, py, _, _ = utm_project(lon, lat, zone)
        candidates = []
        for u, v, data in graph.edges(data=True):
            coordinates = data.get("geometry") or [
                [graph.nodes[u]["lon"], graph.nodes[u]["lat"]],
                [graph.nodes[v]["lon"], graph.nodes[v]["lat"]],
            ]
            projected = [utm_project(float(x), float(y), zone)[:2] for x, y in coordinates]
            distance = min(_segment_distance((px, py), a, b) for a, b in zip(projected, projected[1:]))
            if distance <= radius_m:
                candidates.append((u, v, distance, data.get("name", ""), data.get("length", 0.0)))
        if not candidates:
            raise ValueError(f"No OSM edge lies within {radius_m:g} m of closure point ({lon},{lat})")
        for u, v, distance, name, length in candidates:
            if graph.has_edge(u, v):
                graph.remove_edge(u, v)
                removed.append({"source": str(u), "target": str(v), "name": name,
                                "distance_to_closure_m": distance, "edge_length_m": length,
                                "closure_lon": lon, "closure_lat": lat})
    return removed


def block_matching_lines(graph: nx.DiGraph, closures: list[dict[str, Any]], zone: int,
                         tolerance_m: float = 3.0) -> list[dict[str, Any]]:
    """Remove cached graph edges geometrically coincident with verified OSM way lines."""
    removed: list[dict[str, Any]] = []
    for closure in closures:
        coordinate_parts = closure.get("coordinate_parts") or [closure["coordinates"]]
        closure_lines = [LineString([utm_project(float(lon), float(lat), zone)[:2]
                                     for lon, lat in coordinates]) for coordinates in coordinate_parts]
        closure_lines = [line for line in closure_lines if not line.is_empty and line.length > 0]
        if not closure_lines:
            raise ValueError(f"Closure {closure.get('closure_id', closure.get('name'))} has empty line geometry")
        candidates = []
        for u, v, data in graph.edges(data=True):
            edge_coords = data.get("geometry") or [
                [graph.nodes[u]["lon"], graph.nodes[u]["lat"]],
                [graph.nodes[v]["lon"], graph.nodes[v]["lat"]],
            ]
            edge_line = LineString([utm_project(float(lon), float(lat), zone)[:2]
                                    for lon, lat in edge_coords])
            if edge_line.is_empty or edge_line.length == 0:
                continue
            matches = []
            for closure_line in closure_lines:
                distance = edge_line.distance(closure_line)
                if distance <= tolerance_m:
                    overlap = edge_line.intersection(closure_line.buffer(tolerance_m)).length / edge_line.length
                    if overlap >= 0.8:
                        matches.append(distance)
            if matches:
                candidates.append((u, v, min(matches), data.get("length", 0.0)))
        if not candidates:
            raise ValueError(f"No cached directed graph edge matches verified OSM way closure "
                             f"{closure.get('osm_way_ids', closure.get('closure_id', closure.get('name')))}")
        for u, v, distance, length in candidates:
            if graph.has_edge(u, v):
                graph.remove_edge(u, v)
                removed.append({"source": str(u), "target": str(v),
                                "closure_id": closure.get("closure_id"), "name": closure.get("name"),
                                "osm_way_ids": closure.get("osm_way_ids"),
                                "distance_to_closure_m": distance, "edge_length_m": length})
    return removed


def _zone_points(path: Path) -> list[dict[str, Any]]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    points = []
    for feature in collection.get("features", []):
        props = feature.get("properties", {})
        point = shape(feature["geometry"]).representative_point()
        points.append({"zone_id": str(props["zone_id"]), "zone_name": str(props.get("name", props["zone_id"])),
                       "lon": point.x, "lat": point.y,
                       "payload_kg_required": props.get("payload_kg_required")})
    return points


def _path_geometry(graph: nx.DiGraph, path: list[str]) -> list[list[float]]:
    coordinates: list[list[float]] = []
    for u, v in zip(path, path[1:]):
        data = graph.get_edge_data(u, v) or {}
        line = [[float(x), float(y)] for x, y in (data.get("geometry") or [])]
        if not line:
            line = [[graph.nodes[u]["lon"], graph.nodes[u]["lat"]],
                    [graph.nodes[v]["lon"], graph.nodes[v]["lat"]]]
        if haversine_m(line[0][0], line[0][1], graph.nodes[u]["lon"], graph.nodes[u]["lat"]) > \
                haversine_m(line[-1][0], line[-1][1], graph.nodes[u]["lon"], graph.nodes[u]["lat"]):
            line.reverse()
        coordinates.extend(line if not coordinates else line[1:])
    if not path:
        return []
    if len(path) == 1:
        return [[graph.nodes[path[0]]["lon"], graph.nodes[path[0]]["lat"]]]
    return coordinates


def _heuristic(graph: nx.DiGraph, target: str):
    tx, ty = graph.nodes[target]["x"], graph.nodes[target]["y"]
    return lambda node, _target: math.hypot(graph.nodes[node]["x"] - tx, graph.nodes[node]["y"] - ty)


def compute_routes(*, graph_path: Path, zone_path: Path, origins: list[dict[str, Any]],
                   closure_points: list[tuple[float, float]] | None = None,
                   closure_lines: list[dict[str, Any]] | None = None,
                   closure_radius_m: float = 25.0, max_snap_distance_m: float = 5000.0,
                   secondary_max_distance_km: float = 10.0,
                   secondary_payload_kg: float = 50.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Route every zone from its lowest-network-cost supplied origin using A*."""
    if not origins:
        raise ValueError("No warehouse origins configured; add verified warehouses or pass an explicit scenario origin")
    if secondary_payload_kg <= 0 or secondary_max_distance_km < 0:
        raise ValueError("secondary payload capacity must be positive and maximum distance cannot be negative")
    if max_snap_distance_m < 0 or closure_radius_m < 0:
        raise ValueError("snap distances and closure radius cannot be negative")
    graph, zone_number = _load_graph(graph_path)
    closures = block_near_points(graph, closure_points or [], zone_number, closure_radius_m)
    closures.extend(block_matching_lines(graph, closure_lines or [], zone_number,
                                         tolerance_m=closure_radius_m))
    snapped_origins = []
    rejected_origins = []
    for origin in origins:
        origin_id = str(origin.get("origin_id", origin.get("name", "unnamed origin")))
        lon, lat = float(origin["lon"]), float(origin["lat"])
        if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
            rejected_origins.append({"origin_id": origin_id, "reason": "invalid_coordinates"})
            continue
        node, distance = _nearest_node(graph, lon, lat, zone_number)
        if distance > max_snap_distance_m:
            rejected_origins.append({"origin_id": origin_id, "reason": "too_far_from_graph",
                                     "snap_distance_m": distance})
            continue
        snapped_origins.append({**origin, "origin_id": origin_id, "node_id": node,
                                "snap_distance_m": distance})
    if not snapped_origins:
        raise ValueError("No configured origin snaps within the maximum distance of the road graph")
    route_rows = []
    route_features = []
    for target in _zone_points(zone_path):
        target_node, target_snap = _nearest_node(graph, target["lon"], target["lat"], zone_number)
        choices = []
        if target_snap <= max_snap_distance_m:
            for origin in snapped_origins:
                try:
                    path = nx.astar_path(graph, origin["node_id"], target_node,
                                         heuristic=_heuristic(graph, target_node), weight="length")
                    distance = sum(float(graph.get_edge_data(a, b)["length"]) for a, b in zip(path, path[1:]))
                    choices.append((distance, origin, path))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
        if choices:
            distance, origin, path = min(choices, key=lambda item: item[0])
            geometry = _path_geometry(graph, path)
            route_rows.append({"zone_id": target["zone_id"], "zone_name": target["zone_name"],
                               "status": "ROUTED", "road_status": "ROUTED", "secondary_status": "NOT_NEEDED",
                               "delivery_mode": "road", "origin_id": origin["origin_id"],
                               "origin_source": origin.get("origin_source", "configured_warehouse"),
                               "origin_snap_distance_m": origin["snap_distance_m"],
                               "target_snap_distance_m": target_snap, "road_distance_m": distance,
                               "road_distance_km": distance / 1000.0, "path_node_count": len(path),
                               "path_node_ids": json.dumps(path),
                               "payload_kg_required": target.get("payload_kg_required"),
                               "secondary_payload_capacity_kg": secondary_payload_kg,
                               "secondary_trip_count": None, "secondary_distance_km": None})
            route_features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": geometry},
                                   "properties": {"zone_id": target["zone_id"], "zone_name": target["zone_name"],
                                                  "origin_id": origin["origin_id"], "distance_m": distance,
                                                  "delivery_mode": "road"}})
        else:
            origin = min(snapped_origins, key=lambda item: haversine_m(item["lon"], item["lat"], target["lon"], target["lat"]))
            straight_km = haversine_m(origin["lon"], origin["lat"], target["lon"], target["lat"]) / 1000.0
            within_limit = straight_km <= secondary_max_distance_km
            payload = target.get("payload_kg_required")
            try:
                payload_value = float(payload)
                payload_known = math.isfinite(payload_value) and payload_value >= 0
            except (TypeError, ValueError):
                payload_value, payload_known = 0.0, False
            trips = math.ceil(payload_value / secondary_payload_kg) if payload_known else None
            secondary_status = ("REQUIRES_PAYLOAD_CHECK" if within_limit and not payload_known else
                                "AVAILABLE" if within_limit and trips <= 1 else
                                "REQUIRES_MULTIPLE_TRIPS" if within_limit and trips and trips > 1 else
                                "EXCEEDS_DISTANCE_LIMIT")
            status = ("SECONDARY_ROUTE_REQUIRES_PAYLOAD_CHECK" if secondary_status == "REQUIRES_PAYLOAD_CHECK" else
                      "SECONDARY_ROUTE_AVAILABLE" if secondary_status == "AVAILABLE" else
                      "SECONDARY_ROUTE_REQUIRES_MULTIPLE_TRIPS" if secondary_status == "REQUIRES_MULTIPLE_TRIPS" else
                      "UNREACHABLE")
            route_rows.append({"zone_id": target["zone_id"], "zone_name": target["zone_name"],
                               "road_status": "UNREACHABLE_BY_ROAD", "secondary_status": secondary_status,
                               "status": status, "delivery_mode": "secondary" if status.startswith("SECONDARY") else "none",
                               "origin_id": origin["origin_id"], "origin_source": origin.get("origin_source", "configured_warehouse"),
                               "target_snap_distance_m": target_snap, "road_distance_m": None, "road_distance_km": None,
                               "path_node_count": 0, "path_node_ids": "[]", "payload_kg_required": payload,
                               "secondary_payload_capacity_kg": secondary_payload_kg,
                               "secondary_trip_count": trips if within_limit else None,
                               "secondary_distance_km": straight_km if within_limit else None})
            if within_limit:
                route_features.append({"type": "Feature", "geometry": {"type": "LineString",
                                                                          "coordinates": [[origin["lon"], origin["lat"]], [target["lon"], target["lat"]]]},
                                       "properties": {"zone_id": target["zone_id"], "zone_name": target["zone_name"],
                                                      "origin_id": origin["origin_id"], "distance_km": straight_km,
                                                      "delivery_mode": "secondary", "status": status}})
    return route_rows, {"closures": closures, "route_features": route_features,
                        "origin_count": len(snapped_origins), "zone_count": len(route_rows),
                        "rejected_origins": rejected_origins,
                        "reachable_road_count": sum(r["delivery_mode"] == "road" for r in route_rows),
                        "secondary_count": sum(r["delivery_mode"] == "secondary" for r in route_rows)}


def run_routing(event_date: str | None = None, *, zone_layer: str = "analysis",
                origins: list[dict[str, Any]] | None = None,
                closure_points: list[tuple[float, float]] | None = None,
                closure_lines: list[dict[str, Any]] | None = None,
                config: dict[str, Any] | None = None) -> tuple[Path, Path]:
    config = config or load_config()
    data = config["data"]
    processed = configured_path(data["processed_dir"])
    if origins is None:
        warehouse_path = processed / "warehouses.geojson"
        if warehouse_path.exists():
            collection = json.loads(warehouse_path.read_text(encoding="utf-8"))
            origins = []
            for feature in collection.get("features", []):
                geometry = feature.get("geometry")
                props = feature.get("properties", {})
                if geometry and geometry.get("type") == "Point" and props.get("route_origin", True):
                    lon, lat = geometry["coordinates"][:2]
                    origins.append({"origin_id": str(props.get("warehouse_id", props.get("name", len(origins)))),
                                    "lon": float(lon), "lat": float(lat),
                                    "origin_source": props.get("source", "warehouses_geojson")})
        else:
            origins = [{"origin_id": str(w.get("warehouse_id", w.get("name", i))),
                        "lon": float(w["lon"]), "lat": float(w["lat"]),
                        "origin_source": "configured_warehouse"}
                       for i, w in enumerate(config.get("warehouses", []))]
    if closure_points is None and event_date:
        closure_path = processed / f"closures_{event_date}.geojson"
        if not closure_path.exists():
            raise FileNotFoundError(f"Event closure file not found: {closure_path}")
        closure_collection = json.loads(closure_path.read_text(encoding="utf-8"))
        closure_points = []
        closure_lines = []
        for feature in closure_collection.get("features", []):
            geometry = feature.get("geometry")
            props = feature.get("properties", {})
            if not geometry or props.get("status") != "verified":
                continue
            if geometry.get("type") == "Point":
                lon, lat = geometry["coordinates"][:2]
                closure_points.append((float(lon), float(lat)))
            elif geometry.get("type") == "LineString":
                closure_lines.append({**props, "coordinates": geometry["coordinates"]})
            elif geometry.get("type") == "MultiLineString":
                closure_lines.append({**props, "coordinate_parts": geometry["coordinates"]})
        if not closure_points and not closure_lines:
            raise ValueError(f"Event closure file contains no verified Point or OSM way geometry: {closure_path}")
    if zone_layer == "taluk":
        zone_path = configured_path(data["zones_path"])
    elif zone_layer == "module8":
        zone_path = configured_path(data["processed_dir"]) / "zones_module8_analysis_grid.geojson"
    elif zone_layer == "analysis":
        zone_path = configured_path(data.get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
    else:
        raise ValueError("zone_layer must be 'analysis', 'module8', or 'taluk'")
    if not zone_path.exists():
        raise FileNotFoundError(f"Zone GeoJSON not found: {zone_path}")
    if zone_layer in {"analysis", "module8"}:
        zone_collection = json.loads(zone_path.read_text(encoding="utf-8"))
        if len(zone_collection.get("features", [])) != 16:
            raise ValueError(f"Expected 16 Bantwal grid zones for Module 7, found {len(zone_collection.get('features', []))}")
    graph_path = configured_path(data["road_graph_path"])
    rows, details = compute_routes(
        graph_path=graph_path, zone_path=zone_path, origins=origins,
        closure_points=closure_points, closure_lines=closure_lines,
        closure_radius_m=float(config.get("routing", {}).get("blockage_snap_radius_m", 35)),
        max_snap_distance_m=float(config.get("routing", {}).get("max_snap_distance_m", 5000)),
        secondary_max_distance_km=float(config.get("routing", {}).get("secondary_max_distance_km", 10)),
        secondary_payload_kg=float(config["resources"].get("secondary_payload_kg", 50)),
    )
    suffix = event_date or "scenario"
    csv_path = processed / f"routes_{zone_layer}_{suffix}.csv"
    geo_path = processed / f"routes_{zone_layer}_{suffix}.geojson"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    geo_path.write_text(json.dumps({"type": "FeatureCollection", "features": details["route_features"]}, ensure_ascii=False), encoding="utf-8")
    metadata = {key: value for key, value in details.items() if key != "route_features"}
    metadata.update({"event_date": event_date, "zone_layer": zone_layer,
                    "note": "Routes are candidate paths from configured relief-site points. Secondary geometries are straight-line abstractions, not boat/drone navigation; payload feasibility must be checked when zone payload is missing. Explicit CLI origins are scenario-only."})
    (processed / f"routes_{zone_layer}_{suffix}_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return csv_path, geo_path


def _parse_point(value: str) -> tuple[float, float]:
    try:
        lon, lat = (float(part.strip()) for part in value.split(",", 1))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("coordinates must be lon,lat") from exc
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise argparse.ArgumentTypeError("coordinates are outside lon/lat ranges")
    return lon, lat


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-date", help="label outputs for a configured event")
    parser.add_argument("--zone-layer", choices=("analysis", "module8", "taluk"), default="analysis")
    parser.add_argument("--origin", action="append", type=_parse_point,
                        help="explicit scenario origin as lon,lat; repeatable. Real warehouses should be configured in YAML.")
    parser.add_argument("--block-point", action="append", type=_parse_point,
                        help="verified road-closure point as lon,lat; nearby graph edges are removed before routing")
    args = parser.parse_args()
    origins = ([{"origin_id": f"scenario_{i+1}", "lon": point[0], "lat": point[1],
                 "origin_source": "explicit_cli_scenario_origin"} for i, point in enumerate(args.origin)]
               if args.origin else None)
    route_csv, route_geojson = run_routing(args.event_date, zone_layer=args.zone_layer,
                                           origins=origins, closure_points=args.block_point)
    print(f"Route table: {route_csv}")
    print(f"Route GeoJSON: {route_geojson}")


if __name__ == "__main__":
    main()
