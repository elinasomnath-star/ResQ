"""Build multi-threshold Sentinel-1 flood likelihood maps with a HAND prior.

Sentinel-1 scenes are queried from the public Microsoft Planetary Computer STAC
catalog. The HAND prior is the public ASF GLO-30 HAND COG product. We retain
source item IDs, acquisition dates, thresholds, and any date-window fallback in
the event manifest so generated products remain auditable.
"""

from __future__ import annotations

import csv
import io
import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_geom

from ..config import configured_path, load_config
from ..events import FloodEvent, load_events


PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_DATA_API = "https://planetarycomputer.microsoft.com/api/data/v1"
HAND_BASE = "https://glo-30-hand.s3.us-west-2.amazonaws.com/v1/2021"
THRESHOLDS_DB = (-1.0, -1.25, -1.5, -1.75)
HAND_THRESHOLD_M = 15.0


def _json_request(url: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={
        "User-Agent": "ResQ-disaster-allocation/0.1",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def search_scenes(config: dict[str, Any], start: date, end: date) -> list[dict[str, Any]]:
    region = config["region"]
    bbox = ",".join(str(v) for v in region["bbox_wgs84"])
    params = urllib.parse.urlencode({
        "collections": "sentinel-1-rtc", "bbox": bbox,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": 100, "sortby": "datetime",
    })
    result = _json_request(f"{PC_STAC}/search?{params}")
    return [item for item in result.get("features", []) if "vh" in item.get("assets", {})]


def _acquired(item: dict[str, Any]) -> date:
    return datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00")).date()


def select_event_scenes(config: dict[str, Any], event: FloodEvent) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Select a pre-event image and closest during-event image, preferring same orbit."""
    event_day = event.event_date
    event_end = date.fromisoformat(config.get("sar", {}).get("event_window_end_dates", {}).get(event_day.isoformat(), event_day.isoformat()))
    if event_end < event_day:
        raise ValueError(f"Event window end precedes its start for {event_day}")
    items = search_scenes(config, event_day - timedelta(days=35), event_end + timedelta(days=7))
    before_items = [i for i in items if 14 <= (event_day - _acquired(i)).days <= 21]
    during_items = [i for i in items if event_day <= _acquired(i) <= event_end + timedelta(days=3)]
    before_fallback = False
    during_fallback = False
    if not before_items:
        candidates = [i for i in items if 0 < (event_day - _acquired(i)).days <= 35]
        if not candidates:
            raise RuntimeError(f"No pre-event Sentinel-1 VH scene found within 35 days of {event_day}")
        before_items = [min(candidates, key=lambda i: (event_day - _acquired(i)).days)]
        before_fallback = True
    if not during_items:
        candidates = [i for i in items if (_acquired(i) - event_day).days >= 0]
        if not candidates:
            raise RuntimeError(f"No during-event Sentinel-1 VH scene found near {event_day}")
        during_items = [min(candidates, key=lambda i: abs((_acquired(i) - event_end).days))]
        during_fallback = True

    # Retain every pre-event acquisition in the requested interval for a median
    # composite. If the interval is empty, retain only the nearest available day.
    before_dates = sorted({_acquired(i) for i in before_items})
    before_day = min(before_dates, key=lambda d: abs((event_day - d).days))
    during_day = min((_acquired(i) for i in during_items), key=lambda d: abs((event_end - d).days))
    if before_fallback:
        before_items = [i for i in before_items if _acquired(i) == before_day]
    during_items = [i for i in during_items if _acquired(i) == during_day]
    return before_items, during_items, {
        "event_date": event_day.isoformat(),
        "event_window_end_date": event_end.isoformat(),
        "before_date": before_day.isoformat(),
        "before_composite_dates": [d.isoformat() for d in before_dates],
        "during_date": during_day.isoformat(),
        "during_days_after_event_end": (during_day - event_end).days,
        "during_window_fallback": during_fallback,
        "before_days_before_event": (event_day - before_day).days,
        "before_window_fallback": before_fallback,
        "before_items": [i["id"] for i in before_items],
        "during_items": [i["id"] for i in during_items],
        "source": "Microsoft Planetary Computer Sentinel-1 RTC (VH)",
    }


def _target_crs(config: dict[str, Any]) -> str:
    configured = config["region"].get("metric_crs")
    if configured: return str(configured)
    west, south, east, north = config["region"]["bbox_wgs84"]
    lon, lat = (float(west) + float(east)) / 2, (float(south) + float(north)) / 2
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{32600 + zone if lat >= 0 else 32700 + zone}"


def _scene_array(item: dict[str, Any], shape: dict[str, Any], target_crs: str, asset_name: str = "vh") -> tuple[np.ndarray, np.ndarray, Any, Any, str]:
    """Ask the public Data API to crop and average a RTC asset to HAND's 30 m grid."""
    asset_name = asset_name.lower()
    if asset_name not in {"vv", "vh"}:
        raise ValueError(f"Unsupported Sentinel-1 RTC asset: {asset_name}")
    if asset_name not in item.get("assets", {}):
        raise ValueError(f"Scene {item.get('id')} has no {asset_name.upper()} asset")
    projected = transform_geom("EPSG:4326", target_crs, shape)
    from shapely.geometry import shape as make_shape
    min_x, min_y, max_x, max_y = make_shape(projected).bounds
    width = max(1, int(math.ceil((max_x - min_x) / 30.0)))
    height = max(1, int(math.ceil((max_y - min_y) / 30.0)))
    if max(width, height) > 4096:
        factor = max(width, height) / 4096
        width, height = max(1, int(width / factor)), max(1, int(height / factor))
    params = urllib.parse.urlencode({
        "collection": "sentinel-1-rtc", "item": item["id"],
        "coord_crs": "EPSG:4326", "dst_crs": target_crs,
        "assets": asset_name, "resampling": "average", "return_mask": "true",
    })
    url = f"{PC_DATA_API}/item/feature/{width}x{height}.tif?{params}"
    body = json.dumps({"type": "Feature", "geometry": shape, "properties": {}}).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={
        "User-Agent": "ResQ-disaster-allocation/0.1", "Content-Type": "application/json",
        "Accept": "image/tiff; application=geotiff",
    })
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = response.read()
    with rasterio.MemoryFile(payload) as memory_file:
        with memory_file.open() as source:
            values = source.read(1).astype("float32")
            invalid = source.read(2) == 0 if source.count > 1 else ~np.isfinite(values)
            values[invalid] = np.nan
            return values, invalid, source.transform, source.crs, source.nodata


def _to_db(values: np.ndarray, invalid: np.ndarray, nodata: float | None) -> tuple[np.ndarray, np.ndarray]:
    valid = ~invalid & np.isfinite(values)
    if nodata is not None:
        valid &= values != nodata
    # Sentinel-1 RTC VH is delivered as linear gamma0 power. Convert to dB.
    valid &= values > 0
    db = np.full(values.shape, np.nan, dtype="float32")
    db[valid] = 10.0 * np.log10(values[valid])
    return db, valid


def _align(source: np.ndarray, source_valid: np.ndarray, src_transform: Any, src_crs: Any,
           dst_shape: tuple[int, int], dst_transform: Any, dst_crs: Any) -> tuple[np.ndarray, np.ndarray]:
    if source.shape == dst_shape and src_transform == dst_transform and src_crs == dst_crs:
        return source, source_valid
    out = np.full(dst_shape, np.nan, dtype="float32")
    valid_out = np.zeros(dst_shape, dtype="uint8")
    reproject(source, out, src_transform=src_transform, src_crs=src_crs,
              dst_transform=dst_transform, dst_crs=dst_crs, src_nodata=np.nan,
              dst_nodata=np.nan, resampling=Resampling.bilinear)
    reproject(source_valid.astype("uint8"), valid_out, src_transform=src_transform, src_crs=src_crs,
              dst_transform=dst_transform, dst_crs=dst_crs, resampling=Resampling.nearest)
    return out, valid_out.astype(bool) & np.isfinite(out)


def _hand_href(tile_id: str) -> str:
    return f"{HAND_BASE}/{tile_id}.tif"


def _hand_array(shape: dict[str, Any], reference_transform: Any, reference_crs: Any,
                reference_shape: tuple[int, int], tile_ids: list[str]) -> np.ndarray:
    """Read and mosaic the ASF public HAND tiles into the Sentinel grid."""
    hand = np.full(reference_shape, -9999, dtype="float32")
    for tile_id in tile_ids:
        print(f"    HAND tile {tile_id.rsplit('_', 3)[-3:]}", flush=True)
        with rasterio.open(_hand_href(tile_id)) as source:
            reproject(
                source=rasterio.band(source, 1), destination=hand,
                src_transform=source.transform, src_crs=source.crs,
                dst_transform=reference_transform, dst_crs=reference_crs,
                src_nodata=source.nodata, dst_nodata=-9999,
                resampling=Resampling.bilinear, init_dest_nodata=False,
            )
    return hand


def _tile_ids_for_shape(shape: dict[str, Any]) -> list[str]:
    # Study-area polygons fall within the configured region bbox; expand by 1°
    # because ASF tiles use 1° integer degree naming.
    coords = []
    def visit(obj: Any) -> None:
        if isinstance(obj, (list, tuple)) and len(obj) >= 2 and isinstance(obj[0], (int, float)):
            coords.append((float(obj[0]), float(obj[1])))
        elif isinstance(obj, (list, tuple)):
            for child in obj: visit(child)
    visit(shape["coordinates"])
    minx, maxx = math.floor(min(p[0] for p in coords)), math.floor(max(p[0] for p in coords))
    miny, maxy = math.floor(min(p[1] for p in coords)), math.floor(max(p[1] for p in coords))
    result = []
    for lat in range(miny, maxy + 1):
        for lon in range(minx, maxx + 1):
            ns = f"N{lat:02d}" if lat >= 0 else f"S{abs(lat):02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{abs(lon):03d}"
            result.append(f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_HAND")
    return result


def _write_likelihood(path: Path, likelihood: np.ndarray, valid: np.ndarray,
                      hand_ok: np.ndarray, transform: Any, crs: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = np.full(likelihood.shape, -9999, dtype="float32")
    output[valid] = likelihood[valid]
    # Preserve likelihood in HAND valid pixels even if not flood-prone so the
    # paired naive-vs-HAND validation can quantify area removed by the prior.
    profile = {"driver": "GTiff", "height": output.shape[0], "width": output.shape[1],
               "count": 1, "dtype": "float32", "crs": crs, "transform": transform,
               "nodata": -9999.0, "compress": "deflate", "predictor": 3}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(output, 1)
        dst.set_band_description(1, "multi-threshold flood likelihood (0-1)")
        dst.update_tags(hand_threshold_m=HAND_THRESHOLD_M, thresholds_db=",".join(map(str, THRESHOLDS_DB)))


def _process_zone(zone: dict[str, Any], before: list[dict[str, Any]], during: list[dict[str, Any]],
                  target_crs: str, hand_tiles: list[str]) -> tuple[float, float, float, dict[str, Any] | None]:
    shape = zone["geometry"]
    # Choose best intersecting slice for each pass using footprint intersection
    # via the centroid; STAC strip slices overlap the region independently.
    centroid = (zone["properties"]["centroid_lon"], zone["properties"]["centroid_lat"])
    def covering(items: list[dict[str, Any]], all_matches: bool = False) -> Any:
        from shapely.geometry import shape as as_shape, Point
        point = Point(*centroid)
        available = [i for i in items if as_shape(i["geometry"]).covers(point)]
        if not available: available = items
        if all_matches: return available
        return available[0] if available else None
    pre_items, during_item = covering(before, all_matches=True), covering(during)
    if not pre_items or not during_item:
        return float("nan"), float("nan"), 0.0, None
    pre_images = []
    pre_reference = None
    for pre_item in pre_items:
        print(f"    requesting pre-event VH crop {pre_item['id']}", flush=True)
        values, bad, transform, crs, nodata = _scene_array(pre_item, shape, target_crs)
        if pre_reference is None:
            pre_reference = (transform, crs)
            pre_images.append(np.where(bad, np.nan, values))
        else:
            values, valid = _align(values, ~bad, transform, crs,
                                   pre_images[0].shape, pre_reference[0], pre_reference[1])
            pre_images.append(np.where(valid, values, np.nan))
    pre_stack = np.stack(pre_images, axis=0)
    pre_valid = np.isfinite(pre_stack)
    pre_db = np.full(pre_stack.shape[1:], np.nan, dtype="float32")
    valid_count = np.sum(pre_valid, axis=0)
    np.divide(np.nansum(pre_stack, axis=0), valid_count, out=pre_db, where=valid_count > 0)
    # For one acquisition this is identical to the single-scene composite;
    # overlapping available slices are combined using the requested median.
    if len(pre_images) > 1:
        median = np.ma.median(np.ma.masked_invalid(pre_stack), axis=0).filled(np.nan)
        pre_db[valid_count > 0] = median[valid_count > 0]
    pre_bad = ~np.isfinite(pre_db)
    pre_transform, pre_crs = pre_reference
    print(f"    requesting during-event VH crop {during_item['id']}", flush=True)
    during_values, during_bad, out_transform, out_crs, during_nodata = _scene_array(during_item, shape, target_crs)
    pre_db, pre_valid = _to_db(pre_db, pre_bad, None)
    during_db, during_valid = _to_db(during_values, during_bad, during_nodata)
    pre_db, pre_valid = _align(pre_db, pre_valid, pre_transform, pre_crs, during_db.shape, out_transform, out_crs)
    valid = pre_valid & during_valid
    if not np.any(valid):
        return float("nan"), float("nan"), 0.0, None
    delta = during_db - pre_db
    raw_likelihood = np.zeros(delta.shape, dtype="float32")
    for threshold in THRESHOLDS_DB:
        raw_likelihood += (delta <= threshold).astype("float32")
    raw_likelihood /= len(THRESHOLDS_DB)
    print(f"    aligning HAND to 30 m SAR crop ({delta.shape[1]}x{delta.shape[0]})", flush=True)
    hand = _hand_array(shape, out_transform, out_crs, delta.shape, hand_tiles)
    hand_available = np.isfinite(hand) & (hand != -9999) & (hand >= 0)
    hand_valid = hand_available & (hand <= HAND_THRESHOLD_M)
    constrained = valid & hand_valid
    if not np.any(valid): return float("nan"), float("nan"), 0.0, None
    naive_area = float(np.count_nonzero((raw_likelihood > 0) & valid)) / int(np.count_nonzero(valid))
    hand_area = float(np.count_nonzero((raw_likelihood > 0) & constrained)) / int(np.count_nonzero(valid))
    mean_likelihood = float(np.mean(raw_likelihood[constrained])) if np.any(constrained) else 0.0
    raw_likelihood[hand_available & ~hand_valid] = 0
    raw_likelihood[~hand_available] = 0
    return mean_likelihood, naive_area, hand_area, {
        "likelihood": raw_likelihood, "valid": valid & hand_available, "hand_ok": hand_valid,
        "transform": out_transform, "crs": out_crs,
        "delta_mean_db": float(np.mean(delta[valid])),
        "valid_pixels": int(np.count_nonzero(valid)),
        "hand_eligible_pixels": int(np.count_nonzero(constrained)),
        "scene_before": pre_item["id"], "scene_during": during_item["id"],
    }


def process_event(event: FloodEvent, config: dict[str, Any] | None = None) -> tuple[Path, Path, dict[str, Any]]:
    config = config or load_config()
    zones_path = configured_path(config["data"]["zones_path"])
    zones = json.loads(zones_path.read_text(encoding="utf-8"))["features"]
    print(f"[{event.event_date}] querying Sentinel-1 acquisition pairs", flush=True)
    before, during, manifest = select_event_scenes(config, event)
    print(f"[{event.event_date}] selected {manifest['before_date']} -> {manifest['during_date']}; using public crop service", flush=True)
    manifest["hand_source"] = "ASF GLO-30 HAND v1 (2021), public S3 COG, CC0"
    manifest["hand_threshold_m"] = HAND_THRESHOLD_M
    manifest["thresholds_db"] = list(THRESHOLDS_DB)
    manifest["likelihood_rule"] = "fraction of thresholds where VH during-minus-before dB change <= threshold"
    manifest["before_composite_method"] = "median of valid selected Sentinel-1 VH image(s); single image where only one pass is available"
    target_crs = _target_crs(config)
    table_rows = []
    primary = None
    primary_details = None
    tile_cache: dict[str, list[str]] = {}
    for zone in zones:
        localities = zone["properties"].get("matched_localities", [])
        is_event_zone = bool(localities)
        key = zone["properties"]["zone_id"]
        tile_ids = tile_cache.setdefault(key, _tile_ids_for_shape(zone["geometry"]))
        try:
            print(f"[{event.event_date}] processing zone {zone['properties']['name']} ({len(tile_ids)} HAND tiles)", flush=True)
            mean_likelihood, naive_area, hand_area, details = _process_zone(zone, before, during, target_crs, tile_ids)
            status = "computed" if details else "no_common_valid_pixels"
            print(f"[{event.event_date}] zone {zone['properties']['name']}: {status}", flush=True)
        except Exception as exc:
            mean_likelihood, naive_area, hand_area, details = float("nan"), float("nan"), 0.0, None
            status = f"unavailable: {type(exc).__name__}: {exc}"
        if is_event_zone and details is not None and primary is None:
            primary, primary_details = zone, details
        table_rows.append({
            "event_date": event.event_date.isoformat(), "zone_id": key,
            "zone_name": zone["properties"]["name"],
            "matched_localities": ";".join(localities),
            "mean_hand_restricted_flood_likelihood": mean_likelihood,
            "naive_flood_candidate_fraction": naive_area,
            "hand_restricted_flood_candidate_fraction": hand_area,
            "hand_rejected_candidate_fraction": max(0.0, naive_area - hand_area),
            "population_estimate": zone["properties"].get("population_estimate"),
            "population_year": zone["properties"].get("population_year"),
            "valid_pixels": details["valid_pixels"] if details else 0,
            "hand_eligible_pixels": details["hand_eligible_pixels"] if details else 0,
            "status": status,
        })
    if primary is None or primary_details is None:
        raise RuntimeError(f"No zone with event localities could be processed for {event.event_date}; see manifest")
    processed = configured_path(config["data"]["processed_dir"])
    tif_path = processed / f"flood_likelihood_{event.event_date.isoformat()}.tif"
    _write_likelihood(tif_path, primary_details["likelihood"], primary_details["valid"],
                      primary_details["hand_ok"], primary_details["transform"], primary_details["crs"])
    csv_path = processed / f"zone_severity_{event.event_date.isoformat()}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table_rows[0]))
        writer.writeheader(); writer.writerows(table_rows)
    manifest["primary_zone"] = primary["properties"]["zone_id"]
    manifest["primary_zone_delta_mean_db"] = primary_details["delta_mean_db"]
    manifest["primary_zone_valid_pixels"] = primary_details["valid_pixels"]
    manifest["primary_zone_hand_eligible_pixels"] = primary_details["hand_eligible_pixels"]
    manifest["generated_outputs"] = [str(tif_path), str(csv_path)]
    manifest_path = processed / f"sar_manifest_{event.event_date.isoformat()}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    from .plot import write_heatmap_svg
    svg_path = write_heatmap_svg(event.event_date.isoformat(), config)
    manifest["generated_outputs"].append(str(svg_path))
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return tif_path, csv_path, manifest


def run_sar(event_dates: list[str] | None = None) -> list[tuple[Path, Path, dict[str, Any]]]:
    events = load_events()
    wanted = set(event_dates or [])
    return [process_event(event) for event in events if not wanted or event.event_date.isoformat() in wanted]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-date", action="append", help="event date to process; may be repeated")
    args = parser.parse_args()
    for tif, table, manifest in run_sar(args.event_date):
        print(f"Raster: {tif}\nZone table: {table}\nAcquisitions: {manifest['before_date']} -> {manifest['during_date']}")
        print(f"Heatmap: {manifest['generated_outputs'][-1]}")
