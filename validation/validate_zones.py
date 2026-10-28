"""Validate generated OSM zone GeoJSON without third-party GIS packages."""

import csv
import json

from resq.config import configured_path, load_config
from resq.events import load_events


def main() -> None:
    config = load_config()
    path = configured_path(config["data"]["zones_path"])
    if not path.exists():
        raise SystemExit(f"Zones are not generated yet: {path}")
    collection = json.loads(path.read_text(encoding="utf-8"))
    features = collection.get("features", [])
    if collection.get("type") != "FeatureCollection" or not features:
        raise SystemExit("Zone output must be a non-empty GeoJSON FeatureCollection.")
    required = {"zone_id", "name", "zone_type", "centroid_lat", "centroid_lon", "population_estimate", "population_source", "population_year", "boundary_source"}
    names: set[str] = set()
    ids: set[str] = set()
    for index, feature in enumerate(features):
        properties = feature.get("properties", {})
        missing = required.difference(properties)
        if missing:
            raise SystemExit(f"Feature {index} is missing fields: {', '.join(sorted(missing))}")
        geometry = feature.get("geometry") or {}
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise SystemExit(f"Feature {index} is not a polygon boundary.")
        zone_id, name = str(properties["zone_id"]), str(properties["name"])
        if zone_id in ids:
            raise SystemExit(f"Duplicate zone ID: {zone_id}")
        ids.add(zone_id)
        names.add(name.casefold())
        names.update(str(alias).casefold() for alias in properties.get("matched_localities", []))
        if properties["population_estimate"] is not None and float(properties["population_estimate"]) < 0:
            raise SystemExit(f"Negative population estimate for {name}")
        if properties["population_estimate"] is not None and not properties.get("population_source"):
            raise SystemExit(f"Population value for {name} has no source.")
    expected = {name.casefold() for event in load_events() for name in event.affected_localities}
    missing_names = expected.difference(names)
    if missing_names:
        raise SystemExit(f"Event localities missing from zones: {', '.join(sorted(missing_names))}")
    unresolved_path = path.with_name("unresolved_zones.csv")
    if unresolved_path.exists():
        with unresolved_path.open("r", newline="", encoding="utf-8") as stream:
            unresolved = list(csv.DictReader(stream))
        if unresolved:
            raise SystemExit(f"{len(unresolved)} place boundaries unresolved; see {unresolved_path}.")
    modeled = sum(f["properties"].get("population_year") == 2025 and f["properties"].get("population_estimate") is not None for f in features)
    census_reference = config["region"]["population_census_2011_reference_by_taluk_name"]["Bantwal taluk"]
    print(f"Validated {len(features)} polygon zones; {modeled} WorldPop modeled estimates present; Census 2011 reference ({census_reference}) remains config-only.")

    analysis_path = configured_path(config["data"].get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
    if not analysis_path.exists():
        raise SystemExit(f"Bantwal analysis grid has not been generated: {analysis_path}")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    cells = analysis.get("features", [])
    expected_ids = {f"bantwal_grid_{index:02d}" for index in range(1, 17)}
    if len(cells) != 16 or {f.get("properties", {}).get("zone_id") for f in cells} != expected_ids:
        raise SystemExit("Analysis zone layer must contain exactly the 16 configured Bantwal grid cells.")
    for cell in cells:
        props = cell.get("properties", {})
        if props.get("zone_type") != "analysis_grid" or props.get("parent_name") != "Bantwal taluk":
            raise SystemExit(f"Analysis zone is outside the Bantwal 16-cell scope: {props.get('zone_id')}")
        if props.get("population_estimate") is None or float(props["population_estimate"]) < 0:
            raise SystemExit(f"Analysis zone lacks a nonnegative WorldPop raster sum: {props.get('zone_id')}")
    coverage = configured_path(config["data"]["processed_dir"]) / "bantwal_grid_sar_coverage.csv"
    if not coverage.exists():
        raise SystemExit(f"Per-zone SAR coverage table is missing: {coverage}")
    with coverage.open(newline="", encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))
    event_dates = {event.event_date.isoformat() for event in load_events()}
    if len(records) != 16 * len(event_dates):
        raise SystemExit("SAR coverage table must contain one record per grid zone and event.")
    if any(int(record["valid_sar_pixels"]) <= 0 for record in records):
        raise SystemExit("Every Bantwal grid zone must contain valid SAR pixels for each event.")
    print("Validated exactly 16 clipped Bantwal analysis zones and SAR coverage for all events.")


if __name__ == "__main__":
    main()
