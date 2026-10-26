"""Dependency-free clients and geometry helpers for public OSM APIs."""

from __future__ import annotations

import json
import math
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USER_AGENT = "ResQ-disaster-relief-prototype/0.1 (open-data research project)"


def _request(url: str, *, data: bytes | None = None, timeout: int = 90) -> Any:
    request = Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"OSM request failed: {exc}") from exc


def nominatim_search(query: str, *, polygon: bool = False, viewbox: str | None = None) -> dict[str, Any]:
    """Return the first Nominatim result for a configured place query."""
    params: dict[str, str] = {"q": query, "format": "jsonv2", "limit": "1", "addressdetails": "1"}
    if polygon:
        params["polygon_geojson"] = "1"
    if viewbox:
        params["viewbox"] = viewbox
        params["bounded"] = "1"
    result = _request("https://nominatim.openstreetmap.org/search?" + urlencode(params))
    time.sleep(1.1)
    if not result:
        raise ValueError(f"Nominatim returned no result for {query!r}")
    return result[0]


def overpass_query(endpoint: str, query: str, *, timeout: int = 240) -> dict[str, Any]:
    payload = urlencode({"data": query}).encode("utf-8")
    result = _request(endpoint, data=payload, timeout=timeout)
    if not isinstance(result, dict) or "elements" not in result:
        raise ValueError("Overpass response did not contain an elements array")
    return result


def geometry_coordinates(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon":
        return [coordinates]
    if geometry_type == "MultiPolygon":
        return coordinates
    raise ValueError(f"Expected Polygon or MultiPolygon; got {geometry_type!r}")


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        cross = (lon - x1) * (y2 - y1) - (lat - y1) * (x2 - x1)
        if abs(cross) <= 1e-10 and min(x1, x2) - 1e-10 <= lon <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= lat <= max(y1, y2) + 1e-10:
            return True
        if (y1 > lat) != (y2 > lat):
            crossing_lon = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < crossing_lon:
                inside = not inside
        previous = current
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    for polygon in geometry_coordinates(geometry):
        if not polygon or not point_in_ring(lon, lat, polygon[0]):
            continue
        if not any(point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            return True
    return False


def all_vertices_inside(inner: dict[str, Any], outer: dict[str, Any]) -> bool:
    """Conservatively reject locality geometries crossing the study-area boundary."""
    for polygon in geometry_coordinates(inner):
        for ring in polygon:
            for lon, lat, *_ in ring:
                if not point_in_geometry(float(lon), float(lat), outer):
                    return False
    return True


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float, float]:
    twice_area = cx = cy = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = float(ring[index][0]), float(ring[index][1])
        x2, y2 = float(ring[index + 1][0]), float(ring[index + 1][1])
        cross = x1 * y2 - x2 * y1
        twice_area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(twice_area) < 1e-15:
        return sum(float(point[0]) for point in ring) / len(ring), sum(float(point[1]) for point in ring) / len(ring), 0.0
    return cx / (3.0 * twice_area), cy / (3.0 * twice_area), abs(twice_area) / 2.0


def geometry_centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    """Compute an area-weighted planar longitude/latitude centroid."""
    weighted_x = weighted_y = total_area = 0.0
    for polygon in geometry_coordinates(geometry):
        for ring_index, ring in enumerate(polygon):
            x, y, area = _ring_centroid(ring)
            weight = area if ring_index == 0 else -area
            weighted_x += x * weight
            weighted_y += y * weight
            total_area += weight
    if total_area <= 0:
        raise ValueError("Cannot calculate centroid for an empty or invalid polygon")
    return weighted_x / total_area, weighted_y / total_area


def _stitch_rings(segments: list[list[list[float]]]) -> list[list[list[float]]]:
    remaining = [segment[:] for segment in segments if len(segment) >= 2]
    rings: list[list[list[float]]] = []
    while remaining:
        ring = remaining.pop(0)
        changed = True
        while changed and ring[0][:2] != ring[-1][:2]:
            changed = False
            for index, segment in enumerate(remaining):
                if segment[0][:2] == ring[-1][:2]:
                    ring.extend(segment[1:])
                elif segment[-1][:2] == ring[-1][:2]:
                    ring.extend(reversed(segment[:-1]))
                elif segment[-1][:2] == ring[0][:2]:
                    ring = segment[:-1] + ring
                elif segment[0][:2] == ring[0][:2]:
                    ring = list(reversed(segment[1:])) + ring
                else:
                    continue
                remaining.pop(index)
                changed = True
                break
        if len(ring) >= 4 and ring[0][:2] == ring[-1][:2]:
            rings.append(ring)
    return rings


def administrative_element_geometry(element: dict[str, Any]) -> dict[str, Any] | None:
    """Construct Polygon/MultiPolygon GeoJSON from an Overpass admin way/relation."""
    if element.get("type") == "way":
        geometry = element.get("geometry", [])
        ring = [[point["lon"], point["lat"]] for point in geometry]
        if len(ring) >= 4 and ring[0] == ring[-1]:
            return {"type": "Polygon", "coordinates": [ring]}
        return None
    if element.get("type") != "relation":
        return None
    outer_segments: list[list[list[float]]] = []
    inner_segments: list[list[list[float]]] = []
    for member in element.get("members", []):
        if member.get("type") != "way":
            continue
        coordinates = [[point["lon"], point["lat"]] for point in member.get("geometry", [])]
        if len(coordinates) < 2:
            continue
        (inner_segments if member.get("role") == "inner" else outer_segments).append(coordinates)
    outers = _stitch_rings(outer_segments)
    if not outers:
        return None
    polygons = [[outer] for outer in outers]
    for hole in _stitch_rings(inner_segments):
        for polygon in polygons:
            if point_in_ring(float(hole[0][0]), float(hole[0][1]), polygon[0]):
                polygon.append(hole)
                break
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def utm_project(lon: float, lat: float, zone: int | None = None) -> tuple[float, float, int, str]:
    """Project WGS84 to UTM using the standard Transverse Mercator series."""
    a, e2, k0 = 6378137.0, 0.00669437999014, 0.9996
    if zone is None:
        zone = max(1, min(60, int((lon + 180.0) // 6.0) + 1))
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    phi, lam = math.radians(lat), math.radians(lon)
    ep2 = e2 / (1 - e2)
    n = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    t, c = math.tan(phi) ** 2, ep2 * math.cos(phi) ** 2
    aa = math.cos(phi) * (lam - lon0)
    m = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * phi)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
        - 35 * e2**3 / 3072 * math.sin(6 * phi)
    )
    x = k0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * ep2) * aa**5 / 120) + 500000
    y = k0 * (m + n * math.tan(phi) * (aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24 + (61 - 58 * t + t**2 + 600 * c - 330 * ep2) * aa**6 / 720))
    hemisphere = "N" if lat >= 0 else "S"
    if lat < 0:
        y += 10000000
    return x, y, zone, hemisphere


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371008.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))
