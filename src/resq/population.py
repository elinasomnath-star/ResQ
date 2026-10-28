"""Sum WorldPop raster population-count pixels inside Bantwal polygons."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from shapely import transform as shapely_transform
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep
from pyproj import Transformer

from .config import configured_path, load_config


def population_raster_path(config: dict[str, Any] | None = None) -> Path:
    config = config or load_config()
    return configured_path(config["region"]["population_raster_path"])


def raster_population_sums(features: list[dict[str, Any]], *,
                           config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return native WorldPop pixel sums for features; no normalization or areal split."""
    config = config or load_config()
    region = config["region"]
    raster_path = population_raster_path(config)
    if not raster_path.is_file():
        raise FileNotFoundError(
            f"WorldPop population raster is missing: {raster_path}. "
            "Download the configured official GeoTIFF before building zones."
        )
    to_metric = Transformer.from_crs("EPSG:4326", region.get("metric_crs", "EPSG:32643"), always_xy=True)
    results: list[dict[str, Any]] = []
    with rasterio.open(raster_path) as dataset:
        if dataset.count != 1:
            raise ValueError(f"Expected a single-band WorldPop count raster: {raster_path}")
        geometries = []
        for feature in features:
            if not feature.get("geometry"):
                raise ValueError(f"Feature has no geometry: {feature.get('properties', {}).get('zone_id')}")
            geometries.append(shape(transform_geom("EPSG:4326", dataset.crs, feature["geometry"])))
        union = unary_union(geometries)
        window = from_bounds(*union.bounds, transform=dataset.transform).round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
        if window.width <= 0 or window.height <= 0:
            raise ValueError("Bantwal polygons lie outside the configured WorldPop raster")
        values = dataset.read(1, window=window, masked=True).astype("float64")
        valid = ~np.ma.getmaskarray(values) & np.isfinite(values.filled(np.nan))
        totals = np.zeros(len(features), dtype=np.float64)
        counts = np.zeros(len(features), dtype=np.int64)
        prepared = [prep(geometry) for geometry in geometries]
        rows, columns = np.nonzero(valid)
        for row, column in zip(rows.tolist(), columns.tolist()):
            x, y = dataset.xy(int(window.row_off) + row, int(window.col_off) + column)
            point = Point(x, y)
            for index, geometry in enumerate(prepared):
                if geometry.covers(point):
                    totals[index] += float(values.data[row, column])
                    counts[index] += 1
                    break  # shared boundary pixels are counted once, deterministically
        for feature, population, count in zip(features, totals.tolist(), counts.tolist()):
            geom_wgs84 = shape(feature["geometry"])
            metric_geom = shapely_transform(
                geom_wgs84, lambda x, y: to_metric.transform(x, y), interleaved=False
            )
            area_m2 = float(metric_geom.area)
            area_km2 = area_m2 / 1_000_000
            if population < 0 or not np.isfinite(population):
                raise ValueError(f"Invalid WorldPop sum for {feature.get('properties', {}).get('zone_id')}")
            results.append({
                "population_estimate": round(population, 6),
                "population_worldpop_raw_estimate": round(population, 6),
                "population_year": int(region["population_model_year"]),
                "population_model": str(region["population_model"]),
                "population_resolution": str(region["population_resolution"]),
                "population_constrained": bool(region["population_constrained"]),
                "population_source": str(region["population_raster_source_url"]),
                "population_basis": "sum of WorldPop population-count raster pixels whose centers fall inside polygon; unadjusted",
                "population_area_km2": area_km2,
                "population_density_per_km2": population / area_km2 if area_km2 else 0.0,
                "population_valid_pixel_count": int(count),
            })
    return results


def estimate_zone_populations(path: str | Path | None = None, *, year: int | None = None,
                              config: dict[str, Any] | None = None) -> tuple[Path, Path]:
    """Refresh polygon properties/table using raw WorldPop pixel sums."""
    config = config or load_config()
    region = config["region"]
    if year is not None and int(year) != int(region["population_model_year"]):
        raise ValueError("Requested year differs from the single configured WorldPop raster year")
    zone_path = Path(path) if path is not None else configured_path(config["data"]["zones_path"])
    if not zone_path.is_absolute():
        zone_path = configured_path(zone_path)
    collection = json.loads(zone_path.read_text(encoding="utf-8"))
    features = collection.get("features", [])
    if not features:
        raise ValueError(f"No polygon features found in {zone_path}")
    values = raster_population_sums(features, config=config)
    rows: list[dict[str, Any]] = []
    for feature, estimate in zip(features, values):
        props = feature.setdefault("properties", {})
        for legacy_key in ("population_census_2011", "population_census_2011_reference",
                           "population_census_reference_year", "population_census_source"):
            props.pop(legacy_key, None)
        props.update(estimate)
        rows.append({"zone_id": props.get("zone_id"), "zone_name": props.get("name"), **estimate})
    zone_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    csv_path = configured_path(config["data"]["processed_dir"]) / "population_parent_summary_2025.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return zone_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, help="Must match the configured raster year")
    args = parser.parse_args()
    config = load_config()
    zones, table = estimate_zone_populations(year=args.year, config=config)
    print(f"WorldPop raster sums written to {zones}")
    print(f"Population table written to {table}")


if __name__ == "__main__":
    main()
