"""Resolve locality zones from mapped OSM polygons and admin boundaries."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .config import configured_path, load_config
from .events import load_events
from .osm import (
    administrative_element_geometry,
    all_vertices_inside,
    geometry_centroid,
    geometry_coordinates,
    nominatim_search,
    overpass_query,
    point_in_geometry,
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_") or "zone"


def _area_for_region(region_place: dict[str, Any]) -> int:
    if region_place.get("osm_type") != "relation":
        raise ValueError("Study region must be an OSM relation to query its admin areas")
    return 3_600_000_000 + int(region_place["osm_id"])


def _fetch_admin_boundaries(config: dict[str, Any], region_place: dict[str, Any], region_geometry: dict[str, Any]) -> list[dict[str, Any]]:
    area_id = _area_for_region(region_place)
    levels = [str(int(level)) for level in config["region"].get("osm_admin_fallback_levels", [6, 5])]
    level_pattern = "|".join(levels)
    query = (
        "[out:json][timeout:180];"
        f"area({area_id})->.study;"
        f"(relation[\"boundary\"=\"administrative\"][\"admin_level\"~\"^({level_pattern})$\"](area.study);"
        f"way[\"boundary\"=\"administrative\"][\"admin_level\"~\"^({level_pattern})$\"](area.study););"
        "out geom;"
    )
    cache_path = configured_path(config["data"]["raw_dir"]) / f"osm_admin_boundaries_{region_place['osm_id']}.json"
    if cache_path.exists():
        response = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        failures = []
        response = None
        for endpoint in config["data"].get("overpass_endpoints", []):
            try:
                response = overpass_query(endpoint, query, timeout=240)
                break
            except Exception as exc:
                failures.append(f"{endpoint}: {exc}")
        if response is None:
            raise RuntimeError("Could not retrieve OSM admin boundaries: " + " | ".join(failures))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(response, separators=(",", ":")), encoding="utf-8")

    boundaries = []
    seen: set[tuple[str, str]] = set()
    diagnostics: list[str] = []
    matched_admin_tags = 0
    for element in response["elements"]:
        tags = element.get("tags", {})
        if tags.get("boundary") != "administrative" or tags.get("admin_level") not in set(levels):
            continue
        matched_admin_tags += 1
        geometry = administrative_element_geometry(element)
        if not geometry:
            diagnostics.append(f"{element.get('type')}:{element.get('id')} could not be assembled")
            continue
        try:
            if not all_vertices_inside(geometry, region_geometry):
                diagnostics.append(f"{element.get('type')}:{element.get('id')} extends beyond study area")
                continue
            center = geometry_centroid(geometry)
        except ValueError as exc:
            diagnostics.append(f"{element.get('type')}:{element.get('id')} invalid geometry: {exc}")
            continue
        osm_key = (element.get("type", ""), str(element.get("id", "")))
        if osm_key in seen:
            continue
        seen.add(osm_key)
        boundaries.append({
            "osm_type": osm_key[0], "osm_id": osm_key[1], "name": str(tags.get("name", "")),
            "admin_level": int(tags["admin_level"]), "geometry": geometry,
            "centroid_lon": center[0], "centroid_lat": center[1],
        })
    if not boundaries:
        raise RuntimeError(
            f"Overpass returned {len(response['elements'])} elements, {matched_admin_tags} matching admin tags, "
            f"but no usable polygons. Examples: {'; '.join(diagnostics[:8])}"
        )
    return boundaries


def _fetch_named_place_points(names: list[str], config: dict[str, Any], region_place: dict[str, Any]) -> dict[str, list[tuple[float, float]]]:
    if not names:
        return {}
    import re

    pattern = "^(?:" + "|".join(re.escape(name) for name in sorted(set(names), key=len, reverse=True)) + ")$"
    area_id = _area_for_region(region_place)
    query = (
        "[out:json][timeout:120];"
        f"area({area_id})->.study;"
        f"nwr[\"name\"~\"{pattern}\",i](area.study);out center tags;"
    )
    cache_path = configured_path(config["data"]["raw_dir"]) / f"osm_place_candidates_{region_place['osm_id']}.json"
    if cache_path.exists():
        response = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        failures = []
        response = None
        for endpoint in config["data"].get("overpass_endpoints", []):
            try:
                response = overpass_query(endpoint, query, timeout=180)
                break
            except Exception as exc:
                failures.append(f"{endpoint}: {exc}")
        if response is None:
            raise RuntimeError("Could not query OSM place names: " + " | ".join(failures))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(response, separators=(",", ":")), encoding="utf-8")
    found: dict[str, list[tuple[float, float]]] = {}
    expected = {name.casefold() for name in names}
    for element in response.get("elements", []):
        name = str(element.get("tags", {}).get("name", ""))
        if name.casefold() not in expected:
            continue
        if element.get("type") == "node":
            lat, lon = element.get("lat"), element.get("lon")
        else:
            center = element.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
        if lat is not None and lon is not None:
            found.setdefault(name.casefold(), []).append((float(lon), float(lat)))
    return found


def _geometry_area(geometry: dict[str, Any]) -> float:
    total = 0.0
    for polygon in geometry_coordinates(geometry):
        for index, ring in enumerate(polygon):
            twice_area = sum(
                float(ring[i][0]) * float(ring[i + 1][1]) - float(ring[i + 1][0]) * float(ring[i][1])
                for i in range(len(ring) - 1)
            )
            total += abs(twice_area) / 2 * (1 if index == 0 else -1)
    return max(total, 0.0)


def _lookup_place(name: str, kind: str, region: dict[str, Any], viewbox: str | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if kind == "event_locality":
        queries = [
            f"{name}, {region['default_taluk']}, {region['district']}, {region['state']}, {region['country']}",
            f"{name}, {region['district']}, {region['state']}, {region['country']}",
        ]
    else:
        queries = [f"{name}, {region['district']}, {region['state']}, {region['country']}"]
    errors: list[str] = []
    for query in queries:
        try:
            result = nominatim_search(query, polygon=True, viewbox=viewbox)
            geojson = result.get("geojson")
            if geojson and geojson.get("type") in {"Polygon", "MultiPolygon"}:
                return result, geojson
            return result, None
        except Exception as exc:
            errors.append(str(exc))
    raise ValueError("; ".join(errors) or "No Nominatim match")


def _viewbox(place: dict[str, Any]) -> str | None:
    bounds = place.get("boundingbox")
    if not bounds or len(bounds) != 4:
        return None
    south, north, west, east = (float(value) for value in bounds)
    return f"{west},{north},{east},{south}"


def _population_properties(boundary_name: str, config: dict[str, Any]) -> dict[str, Any]:
    region = config["region"]
    census_table = {name.casefold(): int(value) for name, value in region.get("population_by_taluk_name", {}).items()}
    population = census_table.get(boundary_name.casefold())
    return {
        "population_estimate": None,
        "population_source": None,
        "population_year": None,
        "population_basis": None,
        "population_census_2011_reference": population,
        "population_census_reference_year": int(region["population_census_year"]) if population is not None else None,
        "population_census_source": region["population_source_url"] if population is not None else None,
    }


def enrich_existing_zone_population(path: str | Path | None = None, config: dict[str, Any] | None = None) -> int:
    """Apply configured official taluk census counts to already-generated polygons."""
    config = config or load_config()
    zone_path = Path(path) if path is not None else configured_path(config["data"]["zones_path"])
    if not zone_path.is_absolute():
        zone_path = configured_path(zone_path)
    collection = json.loads(zone_path.read_text(encoding="utf-8"))
    enriched = 0
    for feature in collection.get("features", []):
        properties = feature.get("properties", {})
        if properties.get("admin_level") is None:
            continue
        values = _population_properties(str(properties.get("name", "")), config)
        properties.pop("population_census_2011", None)
        properties.update(values)
        if values["population_census_2011_reference"] is not None:
            enriched += 1
    zone_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return enriched


def ensure_event_locality_assignments(path: str | Path | None = None,
                                      config: dict[str, Any] | None = None) -> int:
    """Add newly compiled event names to the configured taluk fallback zone.

    Zone GeoJSON is cached and may predate a later event-table update. This
    keeps its event-locality index synchronized without changing geometries or
    population estimates. Names without a cached, more precise assignment are
    explicitly marked as configured-taluk fallbacks.
    """
    config = config or load_config()
    zone_path = Path(path) if path is not None else configured_path(config["data"]["zones_path"])
    if not zone_path.is_absolute():
        zone_path = configured_path(zone_path)
    collection = json.loads(zone_path.read_text(encoding="utf-8"))
    features = collection.get("features", [])
    if not features:
        raise ValueError(f"No zone polygons found in {zone_path}")
    wanted = [name for event in load_events() for name in event.affected_localities]
    mapped = {str(name).casefold().strip() for feature in features
              for name in feature.get("properties", {}).get("matched_localities", [])}
    missing = []
    seen = set()
    for name in wanted:
        key = name.casefold().strip()
        if key not in mapped and key not in seen:
            missing.append(name)
            seen.add(key)
    if not missing:
        return 0
    default_taluk = str(config["region"]["default_taluk"]).casefold()
    candidates = [feature for feature in features
                  if feature.get("properties", {}).get("zone_type") == "admin_boundary_fallback"
                  and str(feature.get("properties", {}).get("name", "")).casefold().startswith(default_taluk)]
    if not candidates:
        raise ValueError(f"No cached polygon zone found for configured fallback taluk {config['region']['default_taluk']!r}")
    taluk = candidates[0]
    properties = taluk["properties"]
    assigned = properties.setdefault("matched_localities", [])
    fallback = properties.setdefault("fallback_localities", [])
    methods = properties.setdefault("locality_assignment_methods", {})
    for name in missing:
        assigned.append(name)
        fallback.append(name)
        methods[name] = "configured_event_taluk_fallback_added_after_zone_cache"
    zone_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    return len(missing)


def build_zones(config: dict[str, Any] | None = None) -> tuple[Path, Path]:
    """Write zones using exact OSM locality polygons or containing admin boundaries.

    Localities without their own polygon are assigned to the smallest mapped
    administrative boundary that contains their OSM place point. The fallback is
    recorded per feature; no circles or synthetic geometries are created.
    """
    config = config or load_config()
    region = config["region"]
    output_path = configured_path(config["data"]["zones_path"])
    focus_names = [str(name).casefold().strip() for name in region.get("analysis_zone_names", [])]
    # Reuse the already validated local OSM polygons when applying a documented
    # study-area subset. This keeps a focused rebuild reproducible offline.
    if focus_names and output_path.exists():
        cached = json.loads(output_path.read_text(encoding="utf-8"))
        cached_features = cached.get("features", [])
        selected = [feature for feature in cached_features
                    if any(str(feature.get("properties", {}).get("name", "")).casefold().strip() == name
                           or str(feature.get("properties", {}).get("name", "")).casefold().strip().startswith(name)
                           for name in focus_names)]
        if selected:
            output_path.write_text(json.dumps({"type": "FeatureCollection", "features": selected},
                                              ensure_ascii=False), encoding="utf-8")
            ensure_event_locality_assignments(output_path, config)
            unresolved_path = output_path.with_name("unresolved_zones.csv")
            if not unresolved_path.exists():
                unresolved_path.write_text("name,zone_type,reason\n", encoding="utf-8")
            print(f"Wrote {len(selected)} configured focus zone(s) from cached OSM boundaries.")
            return output_path, unresolved_path
    try:
        region_place = nominatim_search(region["osm_place_query"], polygon=True)
        region_geometry = region_place.get("geojson")
        if not region_geometry:
            raise ValueError("Nominatim did not return the district polygon")
        boundaries = _fetch_admin_boundaries(config, region_place, region_geometry)
    except Exception as exc:
        raise RuntimeError(f"Could not load OSM study/admin boundaries: {exc}") from exc
    viewbox = _viewbox(region_place)

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for kind, values in (
        ("event_locality", [name for event in load_events() for name in event.affected_localities]),
        ("coverage_area", region.get("coverage_places", [])),
    ):
        for name in values:
            normalized = name.casefold().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append((name.strip(), kind))

    # Group locality aliases by the real administrative polygon they fall inside.
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    direct_features: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    for name, kind in candidates:
        try:
            result, direct_geometry = _lookup_place(name, kind, region, viewbox)
            if result.get("lat") is None or result.get("lon") is None:
                raise ValueError("Nominatim result did not include a place point")
            lon, lat = float(result["lon"]), float(result["lat"])
            if not point_in_geometry(lon, lat, region_geometry):
                raise ValueError("Nominatim place point is outside the configured study area")
            if direct_geometry and all_vertices_inside(direct_geometry, region_geometry):
                osm_type = str(result.get("osm_type", ""))
                osm_id = str(result.get("osm_id", ""))
                direct_features.append({
                    "type": "Feature", "geometry": direct_geometry,
                    "properties": {
                        "zone_id": f"osm_{osm_type}_{osm_id}", "name": name, "zone_type": kind,
                        "matched_localities": [name] if kind == "event_locality" else [],
                        "locality_assignment_methods": {name: "direct_osm_polygon"} if kind == "event_locality" else {},
                        "centroid_lat": float(result.get("lat")), "centroid_lon": float(result.get("lon")),
                        "population_estimate": None, "population_source": None,
                        "population_year": None, "population_basis": None,
                        "boundary_source": "OpenStreetMap Nominatim polygon",
                        "osm_type": osm_type, "osm_id": osm_id,
                        "boundary_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
                    },
                })
                continue

            containing = [
                boundary for boundary in boundaries
                if point_in_geometry(lon, lat, boundary["geometry"])
            ]
            if not containing:
                raise ValueError("No mapped OSM administrative polygon contains the locality point")
            containing.sort(key=lambda boundary: (-boundary["admin_level"], _geometry_area(boundary["geometry"])))
            boundary = containing[0]
            key = (boundary["osm_type"], boundary["osm_id"])
            if key not in grouped:
                grouped[key] = {**boundary, "aliases": [], "alias_kinds": set(), "alias_methods": {}}
            grouped[key]["aliases"].append(name)
            grouped[key]["alias_kinds"].add(kind)
            grouped[key]["alias_methods"][name] = "point_containment"
        except Exception as exc:
            # Event rows are explicitly for Bantwal. When OSM has no place point
            # for a reported locality, retain it under the configured Bantwal
            # taluk boundary and expose that low-resolution assignment.
            taluk = next((
                boundary for boundary in boundaries
                if boundary["name"].casefold().startswith(region["default_taluk"].casefold())
                and boundary["admin_level"] == max(int(level) for level in config["region"].get("osm_admin_fallback_levels", [6, 5]))
            ), None)
            if kind == "event_locality" and taluk is not None:
                key = (taluk["osm_type"], taluk["osm_id"])
                if key not in grouped:
                    grouped[key] = {**taluk, "aliases": [], "alias_kinds": set(), "alias_methods": {}}
                grouped[key]["aliases"].append(name)
                grouped[key]["alias_kinds"].add(kind)
                grouped[key]["alias_methods"][name] = "configured_event_taluk_fallback"
            else:
                unresolved.append({"name": name, "zone_type": kind, "reason": str(exc)})

    features = direct_features
    for boundary in grouped.values():
        aliases = boundary["aliases"]
        zone_name = boundary["name"] or aliases[0]
        population = _population_properties(zone_name, config)
        features.append({
            "type": "Feature", "geometry": boundary["geometry"],
            "properties": {
                "zone_id": f"osm_{boundary['osm_type']}_{boundary['osm_id']}",
                "name": zone_name,
                "zone_type": "admin_boundary_fallback",
                "matched_localities": [name for name in aliases if name in {n for n, k in candidates if k == "event_locality"}],
                "fallback_localities": [name for name in aliases if boundary["alias_methods"].get(name) == "configured_event_taluk_fallback"],
                "locality_assignment_methods": {name: boundary["alias_methods"].get(name, "point_containment")
                                                for name in aliases if name in {n for n, k in candidates if k == "event_locality"}},
                "coverage_aliases": [name for name in aliases if name in {n for n, k in candidates if k == "coverage_area"}],
                "centroid_lat": boundary["centroid_lat"], "centroid_lon": boundary["centroid_lon"],
                **population,
                "boundary_source": "OpenStreetMap administrative boundary",
                "admin_level": boundary["admin_level"], "osm_type": boundary["osm_type"],
                "osm_id": boundary["osm_id"],
                "boundary_url": f"https://www.openstreetmap.org/{boundary['osm_type']}/{boundary['osm_id']}",
            },
        })

    if focus_names:
        features = [feature for feature in features
                    if any(str(feature.get("properties", {}).get("name", "")).casefold().strip() == name
                           or str(feature.get("properties", {}).get("name", "")).casefold().strip().startswith(name)
                           for name in focus_names)]
        if not features:
            raise RuntimeError(f"No generated zone matched configured focus names: {focus_names}")
    output_path = configured_path(config["data"]["zones_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    unresolved_path = output_path.with_name("unresolved_zones.csv")
    with unresolved_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["name", "zone_type", "reason"])
        writer.writeheader()
        writer.writerows(unresolved)
    if not features:
        raise RuntimeError(f"No zone polygons resolved; see {unresolved_path}")
    output_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(features)} OSM polygon zones; {len(unresolved)} names unresolved.")
    return output_path, unresolved_path


if __name__ == "__main__":
    zones_file, unresolved_file = build_zones()
    print(f"Zones: {zones_file}")
    print(f"Unresolved-place report: {unresolved_file}")
