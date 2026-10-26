"""Validate the downloaded road GraphML structure without NetworkX/OSMnx."""

import json
import xml.etree.ElementTree as ET

from resq.config import configured_path, load_config


NS = {"g": "http://graphml.graphdrawing.org/xmlns"}


def main() -> None:
    config = load_config()
    path = configured_path(config["data"]["road_graph_path"])
    if not path.exists():
        raise SystemExit(f"Road graph is not generated yet: {path}")
    root = ET.parse(path).getroot()
    graph = root.find("g:graph", NS)
    if graph is None:
        raise SystemExit("GraphML has no graph element.")
    keys = {key.attrib["id"]: key.attrib.get("attr.name") for key in root.findall("g:key", NS)}
    graph_data = {keys[data.attrib["key"]]: data.text for data in graph.findall("g:data", NS)}
    if not str(graph_data.get("crs", "")).startswith(("EPSG:326", "EPSG:327")):
        raise SystemExit(f"Road graph must use a metric UTM CRS; got {graph_data.get('crs')!r}.")
    nodes = {node.attrib["id"] for node in graph.findall("g:node", NS)}
    edges = graph.findall("g:edge", NS)
    if not nodes or not edges:
        raise SystemExit("Road graph must contain nodes and edges.")
    if any(edge.attrib.get("source") not in nodes or edge.attrib.get("target") not in nodes for edge in edges):
        raise SystemExit("Road graph contains an edge with a missing endpoint.")
    mapping_path = configured_path(config["data"]["node_mapping_path"])
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        missing_nodes = [key for key, item in mapping.items() if str(item["node_id"]) not in nodes]
        if missing_nodes:
            raise SystemExit(f"Node mapping references missing graph nodes: {', '.join(missing_nodes)}")
        zones_path = configured_path(config["data"]["zones_path"])
        if zones_path.exists():
            zones = json.loads(zones_path.read_text(encoding="utf-8"))
            required_zones = {f"zone:{feature['properties']['zone_id']}" for feature in zones.get("features", [])}
            if not required_zones.issubset(mapping):
                raise SystemExit(f"Missing snapped nodes for zones: {', '.join(sorted(required_zones.difference(mapping)))}")
    print(f"Validated {len(nodes)} nodes and {len(edges)} directed road edges ({graph_data['crs']}).")


if __name__ == "__main__":
    main()
