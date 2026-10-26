"""Render a dependency-light SVG heatmap from a flood-likelihood GeoTIFF."""

from __future__ import annotations

import base64
import binascii
import json
import struct
import zlib
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

import numpy as np
import rasterio
from rasterio.warp import transform_geom

from ..config import configured_path, load_config


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF))


def _rgba_png(values: np.ndarray, invalid: np.ndarray) -> bytes:
    likelihood = np.clip(np.nan_to_num(values, nan=0.0), 0.0, 1.0)
    pixels = np.empty((*likelihood.shape, 4), dtype=np.uint8)
    pixels[..., 0] = (239 - 202 * likelihood).astype(np.uint8)
    pixels[..., 1] = (248 - 157 * likelihood).astype(np.uint8)
    pixels[..., 2] = (250 - 107 * likelihood).astype(np.uint8)
    pixels[..., 3] = np.where(invalid | (likelihood <= 0), 0, 45 + 210 * likelihood).astype(np.uint8)
    scanlines = b"".join(b"\x00" + pixels[row].tobytes() for row in range(pixels.shape[0]))
    height, width = likelihood.shape
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(scanlines, 6)) + _png_chunk(b"IEND", b"")


def _rings(geometry: dict[str, Any]) -> Iterable[list[list[float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if kind == "Polygon":
        yield from coordinates
    elif kind == "MultiPolygon":
        for polygon in coordinates:
            yield from polygon


def write_heatmap_svg(event_date: str, config: dict[str, Any] | None = None) -> Path:
    config = config or load_config()
    processed = configured_path(config["data"]["processed_dir"])
    raster_path = processed / f"flood_likelihood_{event_date}.tif"
    manifest = json.loads((processed / f"sar_manifest_{event_date}.json").read_text(encoding="utf-8"))
    zones = json.loads(configured_path(config["data"]["zones_path"]).read_text(encoding="utf-8"))["features"]
    primary = next(z for z in zones if z["properties"]["zone_id"] == manifest["primary_zone"])
    with rasterio.open(raster_path) as source:
        values = source.read(1, masked=True)
        image = _rgba_png(np.asarray(values.data), np.ma.getmaskarray(values))
        height, width = values.shape
        affine_inverse = ~source.transform
        projected = transform_geom("EPSG:4326", source.crs, primary["geometry"])

    map_width = 900.0
    scale = map_width / width
    map_height = height * scale
    left, top = 30.0, 100.0
    footer_y = top + map_height + 74.0
    paths = []
    for ring in _rings(projected):
        if not ring: continue
        points = []
        for x, y, *_ in ring:
            col, row = affine_inverse * (x, y)
            points.append((left + col * scale, top + row * scale))
        if points:
            commands = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
            commands.extend(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
            commands.append("Z")
            paths.append(f'<path d="{" ".join(commands)}" fill="none" stroke="#f05a28" stroke-width="2.4" vector-effect="non-scaling-stroke"/>')

    encoded = base64.b64encode(image).decode("ascii")
    before = manifest["before_date"]
    zone_name = escape(str(primary["properties"]["name"]))
    event_label = escape(event_date)
    mean_likelihood = float(manifest.get("primary_zone_mean_likelihood", 0.0))
    # Re-read the zone table for the primary zone mean.
    with (processed / f"zone_severity_{event_date}.csv").open(encoding="utf-8") as stream:
        import csv
        for row in csv.DictReader(stream):
            if row["zone_id"] == manifest["primary_zone"]:
                mean_likelihood = float(row["mean_hand_restricted_flood_likelihood"])
                break
    svg_height = footer_y + 55
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{svg_height:.0f}" viewBox="0 0 960 {svg_height:.0f}">
<defs>
  <linearGradient id="likelihood" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#eff8fa"/><stop offset="100%" stop-color="#256b8a"/></linearGradient>
  <clipPath id="map-clip"><rect x="{left}" y="{top}" width="{map_width}" height="{map_height:.2f}"/></clipPath>
</defs>
<rect width="100%" height="100%" fill="#f7fafc"/>
<text x="30" y="38" font-family="Arial,sans-serif" font-size="24" font-weight="700" fill="#172b3a">Flood-likelihood surface · {event_label}</text>
<text x="30" y="66" font-family="Arial,sans-serif" font-size="14" fill="#526574">Sentinel-1 RTC VH · before {escape(before)} → during {event_label} · HAND ≤ {manifest['hand_threshold_m']:.0f} m</text>
<image x="{left}" y="{top}" width="{map_width}" height="{map_height:.2f}" preserveAspectRatio="none" href="data:image/png;base64,{encoded}" clip-path="url(#map-clip)"/>
<g clip-path="url(#map-clip)">{''.join(paths)}</g>
<text x="{left + 10}" y="{top + 22}" font-family="Arial,sans-serif" font-size="15" font-weight="700" fill="#172b3a" stroke="#ffffff" stroke-width="4" paint-order="stroke">{zone_name} boundary · coarse OSM taluk zone</text>
<text x="30" y="{top + map_height + 30:.2f}" font-family="Arial,sans-serif" font-size="13" fill="#526574">Relative flood-likelihood score</text>
<rect x="230" y="{top + map_height + 14:.2f}" width="250" height="16" rx="3" fill="url(#likelihood)" stroke="#7b8b94" stroke-width="0.6"/>
<text x="230" y="{top + map_height + 47:.2f}" font-family="Arial,sans-serif" font-size="11" fill="#526574">0</text>
<text x="470" y="{top + map_height + 47:.2f}" text-anchor="end" font-family="Arial,sans-serif" font-size="11" fill="#526574">1</text>
<text x="520" y="{top + map_height + 28:.2f}" font-family="Arial,sans-serif" font-size="13" fill="#526574">Zone mean: {mean_likelihood:.3f} · orange outline: primary event zone</text>
<text x="30" y="{footer_y:.2f}" font-family="Arial,sans-serif" font-size="12" fill="#526574">Likelihood is the fraction of four VH change thresholds flagged; it is a candidate-confidence surface, not a calibrated flood probability.</text>
</svg>'''
    out = processed / f"flood_likelihood_{event_date}.svg"
    out.write_text(svg, encoding="utf-8")
    return out

