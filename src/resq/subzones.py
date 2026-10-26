"""Build and summarize the 16-cell Bantwal analysis grid."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from shapely import transform as shapely_transform
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from shapely.geometry import Point, box, mapping, shape

from .config import configured_path, load_config
from .events import load_events
from .rainfall import write_event_rainfall


def _transformer(source: str, target: str):
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return lambda x, y, z=None: transformer.transform(x, y)


def build_grid(config: dict[str, Any] | None = None) -> Path:
    """Build exactly 16 regular cells clipped to the Bantwal taluk polygon.

    Every cell must contain valid SAR pixels for every configured event. The
    function fails rather than silently dropping a cell and changing scope.
    """
    config = config or load_config()
    processed = configured_path(config["data"]["processed_dir"])
    source_path = configured_path(config["data"]["zones_path"])
    source = json.loads(source_path.read_text(encoding="utf-8"))
    parents = [feature for feature in source.get("features", [])
               if str(feature.get("properties", {}).get("name", "")).casefold().startswith("bantwal")
               and feature.get("geometry")]
    if len(parents) != 1:
        raise ValueError(f"Expected one Bantwal parent polygon in {source_path}; found {len(parents)}")
    parent = parents[0]
    parent_props = parent["properties"]
    metric_crs = str(config["region"].get("metric_crs", "EPSG:32643"))
    to_metric = _transformer("EPSG:4326", metric_crs)
    to_wgs = _transformer(metric_crs, "EPSG:4326")
    parent_metric = shapely_transform(shape(parent["geometry"]), to_metric, interleaved=False)

    grid = config["region"].get("analysis_grid", {})
    rows, columns = int(grid.get("rows", 4)), int(grid.get("columns", 4))
    if rows <= 0 or columns <= 0 or rows * columns != 16:
        raise ValueError(f"Bantwal analysis grid must contain exactly 16 cells; got {rows}x{columns}")
    minx, miny, maxx, maxy = parent_metric.bounds
    width, height = (maxx - minx) / columns, (maxy - miny) / rows
    cells: list[tuple[dict[str, Any], Any]] = []
    for row in range(rows):
        for column in range(columns):
            index = row * columns + column + 1
            y_top = maxy - row * height
            rectangle = box(minx + column * width, y_top - height,
                            minx + (column + 1) * width, y_top)
            clipped = rectangle.intersection(parent_metric)
            if clipped.is_empty or clipped.area <= 0:
                raise ValueError(f"Grid cell {index:02d} does not intersect the Bantwal polygon")
            point = clipped.representative_point()
            lon, lat = to_wgs(point.x, point.y)
            area_km2 = clipped.area / 1_000_000
            props = {
                "zone_id": f"bantwal_grid_{index:02d}",
                "name": f"Bantwal zone {index:02d}",
                "zone_type": "analysis_grid",
                "parent_zone_id": parent_props.get("zone_id", "bantwal_taluk"),
                "parent_name": "Bantwal taluk",
                "grid_row": row + 1,
                "grid_column": column + 1,
                "centroid_lat": lat,
                "centroid_lon": lon,
                "population_area_km2": area_km2,
                "population_year": int(config["region"].get("population_model_year", 2025)),
                "population_model": "Bantwal parent population apportioned by clipped grid-cell area",
                "population_basis": "area-weighted taluk proxy; assumes uniform density within Bantwal",
                "boundary_source": "regular analytical grid clipped to the Bantwal taluk polygon",
            }
            cells.append(({"type": "Feature", "geometry": mapping(shapely_transform(clipped, to_wgs, interleaved=False)),
                          "properties": props}, clipped))

    parent_population = float(parent_props.get("population_estimate") or
                              config["region"].get("population_by_taluk_name", {}).get("Bantwal taluk", 0))
    if parent_population <= 0:
        raise ValueError("Bantwal population control total is missing or nonpositive")
    total_area = sum(geom.area for _, geom in cells)
    for feature, geom in cells:
        props = feature["properties"]
        props["population_estimate"] = parent_population * geom.area / total_area
        props["population_density_per_km2"] = props["population_estimate"] / props["population_area_km2"]

    coverage_rows: list[dict[str, Any]] = []
    coverage: dict[str, dict[str, int]] = {f["properties"]["zone_id"]: {} for f, _ in cells}
    for event in load_events():
        day = event.event_date.isoformat()
        raster_path = processed / f"flood_likelihood_{day}.tif"
        if not raster_path.exists():
            raise FileNotFoundError(f"Cached Bantwal SAR raster is missing: {raster_path}")
        with rasterio.open(raster_path) as dataset:
            valid = dataset.read_masks(1) > 0
            for feature, geom in cells:
                raster_geom = transform_geom(metric_crs, dataset.crs, mapping(geom))
                inside = geometry_mask([raster_geom], out_shape=(dataset.height, dataset.width),
                                       transform=dataset.transform, invert=True, all_touched=False)
                count = int((inside & valid).sum())
                zone_id = feature["properties"]["zone_id"]
                coverage[zone_id][day] = count
                coverage_rows.append({"event_date": day, "zone_id": zone_id,
                                      "zone_name": feature["properties"]["name"],
                                      "valid_sar_pixels": count})
    invalid = {zone_id: counts for zone_id, counts in coverage.items()
               if len(counts) != len(load_events()) or any(value == 0 for value in counts.values())}
    if invalid:
        raise ValueError(f"Some of the 16 Bantwal grid zones lack SAR coverage: {invalid}")

    # Attach only verified automatic OSM points to the containing analytical cell.
    log_path = processed / "locality_geocoding_log.csv"
    if log_path.exists():
        with log_path.open(newline="", encoding="utf-8-sig") as stream:
            for record in csv.DictReader(stream):
                if not record.get("coordinates") or record.get("method") != "automatic_osm_nominatim":
                    continue
                try:
                    lon, lat = (float(part) for part in record["coordinates"].split(","))
                except (ValueError, TypeError):
                    continue
                point = Point(lon, lat)
                for feature, _ in cells:
                    if shape(feature["geometry"]).covers(point):
                        feature["properties"].setdefault("matched_localities", []).append(record["locality"])
                        break

    out_path = configured_path(config["data"].get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"type": "FeatureCollection",
                                    "features": [feature for feature, _ in cells]}, ensure_ascii=False),
                        encoding="utf-8")
    with (processed / "bantwal_grid_sar_coverage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(coverage_rows[0]))
        writer.writeheader()
        writer.writerows(coverage_rows)
    return out_path


def _raster_stats(path: Path, zones: list[dict[str, Any]], *, binary: bool = False) -> list[dict[str, Any]]:
    with rasterio.open(path) as dataset:
        data = dataset.read(1)
        valid = (dataset.read_masks(1) > 0) & np.isfinite(data)
        result = []
        pixel_area_km2 = abs(dataset.transform.a * dataset.transform.e) / 1_000_000
        for feature in zones:
            geom = transform_geom("EPSG:4326", dataset.crs, feature["geometry"])
            inside = geometry_mask([geom], out_shape=data.shape, transform=dataset.transform,
                                   invert=True, all_touched=False)
            values = data[inside & valid]
            if binary:
                selected = values > 0
                value = float(selected.mean()) if values.size else 0.0
                area_km2 = float(np.count_nonzero(selected) * pixel_area_km2)
            else:
                value = float(values.mean()) if values.size else 0.0
                area_km2 = 0.0
            result.append({"value": value, "area_km2": area_km2,
                           "valid_pixels": int(values.size),
                           "positive_pixels": int(np.count_nonzero(values > 0))})
        return result


def summarize_cached_inputs(config: dict[str, Any] | None = None) -> None:
    """Refresh SAR, rainfall, and gauge-HAND summaries for the 16 grid cells."""
    config = config or load_config()
    processed = configured_path(config["data"]["processed_dir"])
    zones_path = configured_path(config["data"].get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
    zones = json.loads(zones_path.read_text(encoding="utf-8"))["features"]
    if len(zones) != 16 or any(z["properties"].get("zone_type") != "analysis_grid" for z in zones):
        raise ValueError(f"Expected the configured 16-cell Bantwal analysis grid at {zones_path}")
    sar_fields = ["event_date", "zone_id", "zone_name", "matched_localities",
                  "mean_hand_restricted_flood_likelihood", "naive_flood_candidate_fraction",
                  "hand_restricted_flood_candidate_fraction", "hand_rejected_candidate_fraction",
                  "population_estimate", "population_year", "valid_pixels", "hand_eligible_pixels",
                  "status", "processing_note"]
    hand_rows, hand_area_rows = [], []
    for event in load_events():
        day = event.event_date.isoformat()
        sar_path = processed / f"flood_likelihood_{day}.tif"
        if not sar_path.exists():
            raise FileNotFoundError(f"Cached Bantwal SAR raster missing: {sar_path}")
        sar_stats = _raster_stats(sar_path, zones)
        sar_rows = []
        for feature, stats in zip(zones, sar_stats):
            props = feature["properties"]
            fraction = stats["positive_pixels"] / stats["valid_pixels"] if stats["valid_pixels"] else 0.0
            sar_rows.append({
                "event_date": day, "zone_id": props["zone_id"], "zone_name": props["name"],
                "matched_localities": ";".join(props.get("matched_localities", [])),
                "mean_hand_restricted_flood_likelihood": stats["value"],
                "naive_flood_candidate_fraction": fraction,
                "hand_restricted_flood_candidate_fraction": fraction,
                "hand_rejected_candidate_fraction": 0.0,
                "population_estimate": props["population_estimate"],
                "population_year": props["population_year"],
                "valid_pixels": stats["valid_pixels"], "hand_eligible_pixels": stats["valid_pixels"],
                "status": "computed",
                "processing_note": "Bantwal grid summary from cached SAR raster; candidate signal only",
            })
        with (processed / f"zone_severity_{day}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=sar_fields)
            writer.writeheader()
            writer.writerows(sar_rows)
        write_event_rainfall(event.event_date, zones, config, days=7)

        gauge_path = processed / f"gauge_hand_inundation_{day}.tif"
        hand_stats = (_raster_stats(gauge_path, zones, binary=True) if gauge_path.exists() else
                      [{"value": 0.0, "area_km2": 0.0, "valid_pixels": 0} for _ in zones])
        for feature, stats in zip(zones, hand_stats):
            props = feature["properties"]
            hand_rows.append({"event_date": day, "zone_id": props["zone_id"],
                              "zone_name": props["name"], "gauge_hand_inundated_fraction": stats["value"],
                              "gauge_hand_inundated_area_km2": stats["area_km2"],
                              "feature_source": "2019-calibrated h0; stage-only event update"})
            hand_area_rows.append({"event_date": day, "zone_id": props["zone_id"],
                                   "zone_name": props["name"],
                                   "gauge_hand_inundated_area_km2": stats["area_km2"],
                                   "valid_pixels": stats["valid_pixels"]})
    for filename, records in (("gauge_hand_zone_features.csv", hand_rows),
                              ("gauge_hand_area_by_zone.csv", hand_area_rows)):
        with (processed / filename).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)


def main() -> None:
    path = build_grid()
    summarize_cached_inputs()
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    print(f"Built {len(features)} Bantwal analysis grid zones and refreshed cached SAR/HAND/rainfall features")


if __name__ == "__main__":
    main()
