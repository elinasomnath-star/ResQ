"""Build Bantwal-only frontend map assets from the checked-in project data.

This is a presentation/export step: it clips cached OSM lines and display-only
SAR images to the union of the 16 analytical grid zones. Source data is not
modified.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.features import geometry_mask
from shapely.geometry import mapping, shape
from shapely.ops import transform as project_geometry, unary_union

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public" / "data"
PROCESSED = ROOT / "data" / "processed"
EVENTS = ("2019-08-10", "2024-07-31", "2026-08-03")


def read_geojson(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_geojson(path: Path, features: list[dict]) -> None:
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")


def clipped_features(source: dict, area, keep_points: bool = False) -> list[dict]:
    result = []
    for feature in source.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        geom = shape(geometry)
        if keep_points:
            if geom.geom_type != "Point" or not area.covers(geom):
                continue
            clipped = geom
        else:
            clipped = geom.intersection(area)
            if clipped.is_empty or clipped.geom_type not in {"LineString", "MultiLineString"}:
                continue
            if clipped.length <= 1e-8:
                continue
        result.append({"type": "Feature", "properties": feature.get("properties", {}), "geometry": mapping(clipped)})
    return result


def render_sar_png(event_date: str, area) -> list[list[float]]:
    source = PROCESSED / f"flood_likelihood_{event_date}.tif"
    output = PUBLIC / f"sar_bantwal_{event_date}.png"
    with rasterio.open(source) as dataset:
        to_raster = Transformer.from_crs("EPSG:4326", dataset.crs, always_xy=True).transform
        projected_area = project_geometry(to_raster, area)
        window = rasterio.windows.from_bounds(*projected_area.bounds, transform=dataset.transform)
        window = window.round_offsets().round_lengths()
        window = window.intersection(rasterio.windows.Window(0, 0, dataset.width, dataset.height))
        values = dataset.read(1, window=window)
        window_transform = dataset.window_transform(window)
        inside = geometry_mask([mapping(projected_area)], out_shape=values.shape, transform=window_transform, invert=True)
        valid = inside & np.isfinite(values) & (values != dataset.nodata)
        score = np.clip(values, 0.0, 1.0)

        # Muted sea-glass ramp with opacity tied to the source signal score.
        low = np.array([113, 195, 190], dtype=np.float32)
        high = np.array([244, 189, 103], dtype=np.float32)
        rgb = low[None, None, :] * (1.0 - score[..., None]) + high[None, None, :] * score[..., None]
        rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
        rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
        rgba[..., 3] = np.where(valid, np.clip(36 + score * 150, 0, 190), 0).astype(np.uint8)
        Image.fromarray(rgba, mode="RGBA").save(output, optimize=True)

        left, bottom, right, top = rasterio.windows.bounds(window, dataset.transform)
        to_wgs84 = Transformer.from_crs(dataset.crs, "EPSG:4326", always_xy=True)
        west, south = to_wgs84.transform(left, bottom)
        east, north = to_wgs84.transform(right, top)
        return [[west, north], [east, north], [east, south], [west, south]]


def svg_path(geometry, project) -> str:
    paths = []
    geoms = list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]
    for geom in geoms:
        if geom.geom_type == "Polygon":
            rings = [geom.exterior, *geom.interiors]
            for ring in rings:
                points = [project(x, y) for x, y in ring.coords]
                if points:
                    paths.append("M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points) + " Z")
        elif geom.geom_type == "LineString":
            points = [project(x, y) for x, y in geom.coords]
            if points:
                paths.append("M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points))
    return " ".join(paths)


def render_hero_map(area, zones, roads, river, routes, facilities) -> None:
    minx, miny, maxx, maxy = area.bounds
    width, height, pad = 860, 660, 24
    aspect = (maxx - minx) / (maxy - miny)
    draw_h = height - 2 * pad
    draw_w = draw_h * aspect
    offset_x = (width - draw_w) / 2

    def project(lon: float, lat: float) -> tuple[float, float]:
        return offset_x + (lon - minx) / (maxx - minx) * draw_w, pad + (maxy - lat) / (maxy - miny) * draw_h

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" rx="22" fill="#0c1716"/>']
    for feature in roads:
        d = svg_path(shape(feature["geometry"]), project)
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="#42615a" stroke-width="1.15" opacity=".72"/>')
    for feature in zones.get("features", []):
        geom = shape(feature["geometry"])
        d = svg_path(geom, project)
        parts.append(f'<path d="{d}" fill="#17332b" fill-opacity=".37" stroke="#8ba999" stroke-width="1.7"/>')
        props = feature.get("properties", {})
        x, y = project(float(props["centroid_lon"]), float(props["centroid_lat"]))
        label = str(props.get("grid_row", ""))
        col = str(props.get("grid_column", ""))
        number = (int(label) - 1) * 4 + int(col) if label and col else 0
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="#12221f" stroke="#c1d7cb" stroke-width="1.2"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + 4:.1f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="10" font-weight="700" fill="#f0f6ef">{number:02}</text>')
    for feature in river:
        d = svg_path(shape(feature["geometry"]), project)
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="#59d3c4" stroke-width="5" stroke-linecap="round" opacity=".96"/>')
    for feature in routes:
        d = svg_path(shape(feature["geometry"]), project)
        if d:
            parts.append(f'<path d="{d}" fill="none" stroke="#f4c36a" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity=".95"/>')
    for feature in facilities:
        geom = shape(feature["geometry"])
        x, y = project(*geom.coords[0])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="#f4c36a" stroke="#fff4d8" stroke-width="2"/>')
    parts.extend([
        '<g font-family="Arial,sans-serif" fill="#cbd9d1"><circle cx="48" cy="620" r="5" fill="#59d3c4"/><text x="61" y="624" font-size="13">Netravati</text><path d="M 175 620 L 203 620" stroke="#f4c36a" stroke-width="4"/><text x="212" y="624" font-size="13">Delivery route</text><circle cx="342" cy="620" r="5" fill="#f4c36a"/><text x="354" y="624" font-size="13">Relief centre</text></g>',
        '</svg>',
    ])
    (PUBLIC / "bantwal_hero_map.svg").write_text("\n".join(parts), encoding="utf-8")


def build() -> None:
    zones = read_geojson(PUBLIC / "analysis_zones.geojson")
    area = unary_union([shape(f["geometry"]) for f in zones["features"]])
    roads = clipped_features(read_geojson(PUBLIC / "simplified_roads.geojson"), area)
    river = clipped_features(read_geojson(PUBLIC / "river.geojson"), area)
    facilities = clipped_features(read_geojson(PUBLIC / "warehouses.geojson"), area, keep_points=True)
    write_geojson(PUBLIC / "bantwal_roads.geojson", roads)
    write_geojson(PUBLIC / "bantwal_river.geojson", river)
    write_geojson(PUBLIC / "bantwal_facilities.geojson", facilities)

    first_event_routes = []
    verified_closure_shapes = []
    for event in EVENTS:
        closure_path = PUBLIC / f"closures_{event}.geojson"
        if closure_path.exists():
            closure_doc = read_geojson(closure_path)
            # Keep verified closure geometry even when a reported corridor lies
            # just outside the clipped zone boundary; unresolved rows stay out.
            verified = [f for f in closure_doc.get("features", [])
                        if (f.get("properties") or {}).get("status") == "verified" and f.get("geometry")]
            verified_closure_shapes.extend(shape(f["geometry"]) for f in verified)
            write_geojson(PUBLIC / f"bantwal_closures_{event}.geojson", verified)
        route_path = PUBLIC / f"routes_analysis_{event}.geojson"
        routes = clipped_features(read_geojson(route_path), area)
        write_geojson(PUBLIC / f"bantwal_routes_{event}.geojson", routes)
        if event == "2026-08-03":
            first_event_routes = routes[:1]

    # Keep all analytical zones in Bantwal, while extending only the dark map
    # canvas far enough to show each verified event closure corridor.
    map_extent = unary_union([area, *verified_closure_shapes]) if verified_closure_shapes else area
    (PUBLIC / "bantwal_map_bounds.json").write_text(json.dumps(map_extent.bounds), encoding="utf-8")

    sar_bounds = {}
    for event in EVENTS:
        sar_bounds[event] = render_sar_png(event, area)
    (PUBLIC / "bantwal_sar_bounds.json").write_text(json.dumps(sar_bounds, indent=2), encoding="utf-8")
    render_hero_map(area, zones, roads, river, first_event_routes, facilities)
    print(f"Bantwal map assets ready: {len(zones['features'])} grid zones, {len(roads)} clipped roads, {len(river)} clipped river features, {len(facilities)} facilities")


if __name__ == "__main__":
    build()
