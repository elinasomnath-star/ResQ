"""Fetch and cache a simplified OSM drive graph without native GIS dependencies."""

from __future__ import annotations

import json
import math
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .config import REPO_ROOT, configured_path, load_config
from .osm import geometry_centroid, nominatim_search, overpass_query, utm_project


HIGHWAY_FILTER = "^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|service|track|road)$"
GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"


def _set_graphml_keys(root: ET.Element) -> dict[str, str]:
    definitions = [
        ("graph", "crs", "string"), ("graph", "utm_zone", "int"),
        ("graph", "hemisphere", "string"), ("graph", "network_type", "string"),
        ("graph", "simplified", "boolean"), ("graph", "source", "string"),
        ("node", "osmid", "string"), ("node", "x", "double"), ("node", "y", "double"),
        ("node", "lat", "double"), ("node", "lon", "double"),
        ("edge", "length", "double"), ("edge", "highway", "string"),
        ("edge", "name", "string"), ("edge", "geometry", "string"),
    ]
    ids: dict[str, str] = {}
    for index, (scope, name, value_type) in enumerate(definitions):
        key_id = f"d{index}"
        ids[f"{scope}:{name}"] = key_id
        ET.SubElement(root, f"{{{GRAPHML_NS}}}key", {
            "id": key_id, "for": scope, "attr.name": name, "attr.type": value_type,
        })
    return ids


def _data(parent: ET.Element, key: str, value: Any) -> None:
    child = ET.SubElement(parent, f"{{{GRAPHML_NS}}}data", {"key": key})
    child.text = str(value)


def _area_id(place: dict[str, Any]) -> int:
    if place.get("osm_type") != "relation":
        raise ValueError("The configured OSM study region must resolve to a relation boundary")
    return 3_600_000_000 + int(place["osm_id"])


def _osm_elements(config: dict[str, Any], place: dict[str, Any]) -> dict[str, Any]:
    area_id = _area_id(place)
    query = (
        "[out:json][timeout:180];"
        f"area({area_id})->.study;"
        f"way[\"highway\"~\"{HIGHWAY_FILTER}\"](area.study);"
        "(._;>;);out body;"
    )
    endpoints = config["data"].get("overpass_endpoints", ["https://overpass-api.de/api/interpreter"])
    errors: list[str] = []
    for endpoint in endpoints:
        try:
            result = overpass_query(endpoint, query)
            if not result["elements"]:
                raise ValueError("Overpass returned no road elements for the configured region")
            return result
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    raise RuntimeError("All Overpass endpoints failed: " + " | ".join(errors))


def _projected_graph_elements(elements: list[dict[str, Any]], region_geometry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], int, str]:
    nodes: dict[str, dict[str, Any]] = {}
    ways: list[dict[str, Any]] = []
    for element in elements:
        if element.get("type") == "node":
            nodes[str(element["id"])] = {
                "lat": float(element["lat"]), "lon": float(element["lon"]),
                "tags": element.get("tags", {}),
            }
        elif element.get("type") == "way":
            tags = element.get("tags", {})
            if tags.get("access") == "private" or tags.get("motor_vehicle") == "no" or tags.get("vehicle") == "no":
                continue
            ways.append({"id": str(element["id"]), "nodes": [str(node) for node in element.get("nodes", [])], "tags": tags})
    if not nodes or not ways:
        raise ValueError("OSM data did not contain both road ways and their nodes")

    center_lon, center_lat = geometry_centroid(region_geometry)
    _, _, zone, hemisphere = utm_project(center_lon, center_lat)
    for node in nodes.values():
        node["x"], node["y"], _, _ = utm_project(node["lon"], node["lat"], zone)

    neighbors: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    node_ways: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    way_endpoints: set[str] = set()
    for way in ways:
        ids = [node_id for node_id in way["nodes"] if node_id in nodes]
        if ids:
            way_endpoints.update((ids[0], ids[-1]))
        for node_id in ids:
            node_ways[node_id].add(way["id"])
        for first, second in zip(ids, ids[1:]):
            neighbors[first].add(second)
            neighbors[second].add(first)
    anchors = {
        node_id for node_id, adjacent in neighbors.items()
        if len(adjacent) != 2 or bool(nodes[node_id]["tags"]) or node_id in way_endpoints or len(node_ways[node_id]) > 1
    }

    graph_nodes: set[str] = set()
    graph_edges: list[dict[str, Any]] = []
    for way in ways:
        node_ids = [node_id for node_id in way["nodes"] if node_id in nodes]
        if way["tags"].get("oneway") == "-1":
            node_ids.reverse()
        if len(node_ids) < 2:
            continue
        start_index = 0
        for index in range(1, len(node_ids)):
            if node_ids[index] not in anchors and index != len(node_ids) - 1:
                continue
            piece = node_ids[start_index:index + 1]
            start_index = index
            if len(piece) < 2:
                continue
            graph_nodes.update((piece[0], piece[-1]))
            length = sum(
                math.hypot(nodes[b]["x"] - nodes[a]["x"], nodes[b]["y"] - nodes[a]["y"])
                for a, b in zip(piece, piece[1:])
            )
            points = [[nodes[node_id]["lon"], nodes[node_id]["lat"]] for node_id in piece]
            tags = way["tags"]
            graph_edges.append({
                "source": piece[0], "target": piece[-1], "length": length,
                "highway": str(tags.get("highway", "road")),
                "name": str(tags.get("name", "")),
                "geometry": json.dumps(points, separators=(",", ":")),
                "oneway": tags.get("oneway") in {"yes", "true", "1"}
                or tags.get("junction") in {"roundabout", "circular"}
                or tags.get("highway") in {"motorway", "motorway_link"},
                "reverse": tags.get("oneway") == "-1",
            })

    if not graph_nodes or not graph_edges:
        raise ValueError("Road simplification produced an empty graph")
    output_nodes = {node_id: nodes[node_id] for node_id in graph_nodes}
    return output_nodes, graph_edges, zone, hemisphere


def _write_graphml(path: Path, nodes: dict[str, dict[str, Any]], edges: list[dict[str, Any]], zone: int, hemisphere: str) -> None:
    ET.register_namespace("", GRAPHML_NS)
    root = ET.Element(f"{{{GRAPHML_NS}}}graphml")
    keys = _set_graphml_keys(root)
    graph = ET.SubElement(root, f"{{{GRAPHML_NS}}}graph", {"id": "G", "edgedefault": "directed"})
    crs = f"EPSG:{32600 + zone if hemisphere == 'N' else 32700 + zone}"
    for key, value in (("crs", crs), ("utm_zone", zone), ("hemisphere", hemisphere), ("network_type", "drive"), ("simplified", "true"), ("source", "OpenStreetMap Overpass API")):
        _data(graph, keys[f"graph:{key}"], value)
    for node_id, node in nodes.items():
        element = ET.SubElement(graph, f"{{{GRAPHML_NS}}}node", {"id": node_id})
        for key, value in (("osmid", node_id), ("x", node["x"]), ("y", node["y"]), ("lat", node["lat"]), ("lon", node["lon"])):
            _data(element, keys[f"node:{key}"], value)
    edge_index = 0
    for edge in edges:
        directed = [(edge["source"], edge["target"])]
        if not edge["oneway"]:
            directed.append((edge["target"], edge["source"]))
        for source, target in directed:
            element = ET.SubElement(graph, f"{{{GRAPHML_NS}}}edge", {"id": str(edge_index), "source": source, "target": target})
            edge_index += 1
            for key, value in (("length", edge["length"]), ("highway", edge["highway"]), ("name", edge["name"]), ("geometry", edge["geometry"])):
                _data(element, keys[f"edge:{key}"], value)
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def fetch_road_graph(config: dict[str, Any] | None = None, *, force: bool = False) -> Path:
    """Download OSM roads for the configured boundary and cache a metric GraphML graph."""
    config = config or load_config()
    output_path = configured_path(config["data"]["road_graph_path"])
    if output_path.exists() and not force:
        return output_path
    region = config["region"]
    place = nominatim_search(region["osm_place_query"])
    geometry = place.get("geojson")
    if not geometry or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        place = nominatim_search(region["osm_place_query"], polygon=True)
        geometry = place.get("geojson")
    if not geometry:
        raise ValueError("Nominatim did not return the study-region boundary geometry")
    road_data = _osm_elements(config, place)
    raw_path = configured_path(config["data"]["raw_dir"]) / f"osm_roads_{place.get('osm_id', 'region')}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(road_data, separators=(",", ":")), encoding="utf-8")
    nodes, edges, zone, hemisphere = _projected_graph_elements(road_data["elements"], geometry)
    _write_graphml(output_path, nodes, edges, zone, hemisphere)
    return output_path


def _read_graph_nodes(graph_path: Path) -> tuple[list[dict[str, Any]], int, str]:
    root = ET.parse(graph_path).getroot()
    ns = {"g": GRAPHML_NS}
    graph = root.find("g:graph", ns)
    if graph is None:
        raise ValueError(f"Invalid GraphML file: {graph_path}")
    graph_values = {element.attrib["key"]: element.text or "" for element in graph.findall("g:data", ns)}
    key_names = {key.attrib["id"]: key.attrib.get("attr.name") for key in root.findall("g:key", ns)}
    metadata = {key_names.get(key): value for key, value in graph_values.items()}
    nodes: list[dict[str, Any]] = []
    for element in graph.findall("g:node", ns):
        values = {key_names.get(item.attrib["key"]): item.text or "" for item in element.findall("g:data", ns)}
        nodes.append({"node_id": element.attrib["id"], **{key: float(values[key]) for key in ("x", "y", "lat", "lon")}})
    return nodes, int(metadata["utm_zone"]), metadata["hemisphere"]


def _load_zone_points(path: Path) -> list[dict[str, Any]]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    points = []
    for feature in collection.get("features", []):
        properties = feature.get("properties", {})
        points.append({
            "id": str(properties["zone_id"]), "kind": "zone",
            "lat": float(properties["centroid_lat"]), "lon": float(properties["centroid_lon"]),
        })
    return points


def snap_locations(config: dict[str, Any] | None = None) -> Path:
    """Snap zone centroids and configured warehouses to nearest projected graph nodes."""
    config = config or load_config()
    graph_path = configured_path(config["data"]["road_graph_path"])
    if not graph_path.exists():
        raise FileNotFoundError(f"Road graph not found; fetch it first: {graph_path}")
    graph_nodes, zone, _hemisphere = _read_graph_nodes(graph_path)
    locations = [
        {"id": str(warehouse.get("warehouse_id", warehouse.get("name", index))), "kind": "warehouse", "lat": float(warehouse["lat"]), "lon": float(warehouse["lon"])}
        for index, warehouse in enumerate(config.get("warehouses", []))
    ]
    zones_path = configured_path(config["data"]["zones_path"])
    if zones_path.exists():
        locations.extend(_load_zone_points(zones_path))
    if not locations:
        raise ValueError("No warehouse or zone locations exist to snap")
    mapping: dict[str, dict[str, Any]] = {}
    for location in locations:
        x, y, _, _ = utm_project(location["lon"], location["lat"], zone)
        nearest = min(graph_nodes, key=lambda node: (node["x"] - x) ** 2 + (node["y"] - y) ** 2)
        mapping[f"{location['kind']}:{location['id']}"] = {
            "node_id": nearest["node_id"], "lat": location["lat"], "lon": location["lon"],
            "road_node_lat": nearest["lat"], "road_node_lon": nearest["lon"],
        }
    output_path = configured_path(config["data"]["node_mapping_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    return output_path


def ingest_roads(config: dict[str, Any] | None = None, *, force: bool = False) -> tuple[Path, Path | None]:
    config = config or load_config()
    graph_path = fetch_road_graph(config, force=force)
    zones_path = configured_path(config["data"]["zones_path"])
    mapping_path = snap_locations(config) if config.get("warehouses") or zones_path.exists() else None
    return graph_path, mapping_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch/cache the configured OSM drive graph.")
    parser.add_argument("--force", action="store_true", help="re-download the road graph even when a cached file exists")
    args = parser.parse_args()
    graph_result, mapping_result = ingest_roads(force=args.force)
    print(f"Road graph: {graph_result.relative_to(REPO_ROOT)}")
    print(f"Node mapping: {mapping_result.relative_to(REPO_ROOT) if mapping_result else 'pending zones/warehouses'}")
