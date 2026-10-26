"""Build a gauge-stage HAND screening model using Copernicus GLO-30.

This is a relative-water-level terrain screen, not hydraulic simulation or a
verified flood map. DEM conditioning and the drainage-area threshold are fixed
before fitting h0. Only the 2019 GFM comparison is used to choose h0.
"""
from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pyflwdir
import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.warp import reproject, transform_geom
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import transform as geom_transform
from pyproj import Transformer
from resq.config import load_config

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "dem"
DEM_PATH = RAW / "copernicus_glo30_taluk_union_30m.tif"
HAND_PATH = PROC / "hand_glo30_flowacc50km2.tif"
GRID = "EPSG:32643"
NODATA = -9999.0
FLOW_THRESHOLD_KM2 = 50.0
BUFFER_M = 12000.0
GFM_2019 = "2019-08-10"
STAGES = {"2019-08-10": 11.6, "2024-07-31": 9.3, "2026-08-03": 8.5}
H0_VALUES = np.round(np.arange(0.0, 11.5001, 0.25), 2)
STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/elevationeuwest/copernicus-dem"


def request_json(url: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def make_grid() -> tuple[Affine, int, int, dict, dict[str, np.ndarray]]:
    zones = json.loads((PROC / "zones.geojson").read_text(encoding="utf-8"))["features"]
    transformer = Transformer.from_crs("EPSG:4326", GRID, always_xy=True)
    geoms = [geom_transform(transformer.transform, shape(f["geometry"])) for f in zones]
    xmin = min(g.bounds[0] for g in geoms) - BUFFER_M
    ymin = min(g.bounds[1] for g in geoms) - BUFFER_M
    xmax = max(g.bounds[2] for g in geoms) + BUFFER_M
    ymax = max(g.bounds[3] for g in geoms) + BUFFER_M
    with rasterio.open(PROC / "hand_aligned_bantwal_2019-08-10.tif") as template:
        t = template.transform
        resx, resy = t.a, abs(t.e)
        x0, y0 = t.c, t.f
        xmin = x0 + math.floor((xmin - x0) / resx) * resx
        xmax = x0 + math.ceil((xmax - x0) / resx) * resx
        ymax = y0 - math.floor((y0 - ymax) / resy) * resy
        ymin = y0 - math.ceil((y0 - ymin) / resy) * resy
    width, height = int(round((xmax - xmin) / resx)), int(round((ymax - ymin) / resy))
    transform = Affine(resx, 0, xmin, 0, -resy, ymax)
    profile = {"driver": "GTiff", "height": height, "width": width, "count": 1,
               "dtype": "float32", "crs": GRID, "transform": transform,
               "nodata": NODATA, "compress": "deflate", "predictor": 3, "tiled": True}
    zone_masks = {}
    for feature, geom in zip(zones, geoms):
        zone_masks[str(feature["properties"]["zone_id"])] = geometry_mask(
            [geom.__geo_interface__], out_shape=(height, width), transform=transform, invert=True)
    return transform, width, height, profile, zone_masks


def fetch_dem(transform: Affine, width: int, height: int, profile: dict) -> np.ndarray:
    RAW.mkdir(parents=True, exist_ok=True)
    if DEM_PATH.exists():
        with rasterio.open(DEM_PATH) as src:
            return src.read(1).astype("float32")
    body = {"collections": ["cop-dem-glo-30"],
            "bbox": [74.65, 12.40, 75.75, 13.30], "limit": 30}
    items = request_json(STAC_SEARCH, body).get("features", [])
    by_id = {item["id"]: item for item in items}
    ids = ["Copernicus_DSM_COG_10_N12_00_E074_00_DEM",
           "Copernicus_DSM_COG_10_N12_00_E075_00_DEM",
           "Copernicus_DSM_COG_10_N13_00_E074_00_DEM",
           "Copernicus_DSM_COG_10_N13_00_E075_00_DEM"]
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise RuntimeError(f"Copernicus DEM catalog did not return expected tiles: {missing}")
    sas = request_json(SAS_TOKEN).get("token", "")
    if not sas:
        raise RuntimeError("Planetary Computer returned no SAS token for Copernicus DEM storage")
    dem = np.full((height, width), NODATA, dtype="float32")
    for item_id in ids:
        item = by_id[item_id]
        href = item["assets"]["data"]["href"] + "?" + sas
        print(f"Reading public DEM tile {item_id}", flush=True)
        with rasterio.open(href) as src:
            warped = rasterio.vrt.WarpedVRT(src, crs=GRID, transform=transform,
                                            width=width, height=height,
                                            resampling=Resampling.bilinear,
                                            src_nodata=src.nodata, nodata=NODATA)
            data = warped.read(1, out_dtype="float32")
            valid = np.isfinite(data) & (data != NODATA)
            dem[valid] = data[valid]
            warped.close()
    if np.mean(dem == NODATA) > 0.15:
        raise RuntimeError(f"DEM has excessive nodata in processing grid: {np.mean(dem == NODATA):.1%}")
    with rasterio.open(DEM_PATH, "w", **profile) as dst:
        dst.write(dem, 1)
        dst.set_band_description(1, "Copernicus DEM GLO-30 DSM, projected to the aligned 30 m study grid")
    (RAW / "copernicus_glo30_manifest.json").write_text(json.dumps({
        "source": "Copernicus DEM GLO-30 via Microsoft Planetary Computer STAC",
        "collection": "cop-dem-glo-30", "items": ids, "crs": GRID,
        "resolution_m": 30, "derived_from": "Copernicus WorldDEM-30 DSM",
        "source_url": "https://planetarycomputer.microsoft.com/dataset/group/copernicus-dem",
        "tile_buffer_m": BUFFER_M,
    }, indent=2), encoding="utf-8")
    return dem


def derive_hand(dem: np.ndarray, transform: Affine, profile: dict) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(dem) & (dem != NODATA)
    if valid.mean() < 0.8:
        raise RuntimeError(f"Too little valid DEM coverage for flow routing: {valid.mean():.1%}")
    # PyFlwDir fills topographic depressions and routes D8 flow toward edge outlets.
    dem_for_flow = np.where(valid, dem, NODATA).astype("float32")
    flow = pyflwdir.from_dem(dem_for_flow, nodata=NODATA, transform=transform,
                             latlon=False, outlets="edge")
    drainage_area = flow.upstream_area(unit="km2")
    river = valid & (drainage_area >= FLOW_THRESHOLD_KM2)
    if not river.any():
        raise RuntimeError("Flow-accumulation threshold produced no drainage cells")
    hand = flow.hand(river, np.where(valid, dem, NODATA).astype("float32"))
    hand = np.asarray(hand, dtype="float32")
    # Negative HAND indicates a local depression relative to its routed drain;
    # do not treat it as a below-stage flooded plain.
    hand[(~valid) | ~np.isfinite(hand) | (hand < 0)] = NODATA
    out_profile = profile.copy()
    with rasterio.open(HAND_PATH, "w", **out_profile) as dst:
        dst.write(hand, 1)
        dst.set_band_description(1, "HAND above nearest D8 drainage cell with upstream area >=50 km2")
        dst.update_tags(DEM="Copernicus GLO-30", flow_routing="PyFlwDir D8; depression-filled",
                        flow_accumulation_threshold_km2=FLOW_THRESHOLD_KM2,
                        buffer_m=BUFFER_M, nodata_depressions="negative HAND excluded")
    np.savez_compressed(PROC / "gauge_hand_flow_diagnostics.npz",
                        flow_accumulation_km2=drainage_area.astype("float32"),
                        river_network=river.astype("uint8"))
    return hand, river


def aligned_gfm(day: str, shape_: tuple[int, int], transform: Affine, crs: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    folder = ROOT / "data" / "raw" / "gfm" / day
    flood = np.full(shape_, 255, dtype="uint8")
    exclusion = np.ones(shape_, dtype="uint8")
    permanent = np.ones(shape_, dtype="uint8")
    for name, output in [("ensemble_flood_extent.tif", flood), ("exclusion_mask.tif", exclusion),
                         ("reference_water_mask.tif", permanent)]:
        path = folder / name
        if not path.exists():
            continue
        with rasterio.open(path) as src:
            reproject(src.read(1), output, src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata, dst_transform=transform, dst_crs=crs,
                      dst_nodata=255 if name.startswith("ensemble") else 1,
                      resampling=Resampling.nearest)
    return flood, exclusion, permanent


def connected_inundation(hand: np.ndarray, river: np.ndarray, stage: float, h0: float) -> np.ndarray:
    depth = stage - h0
    if depth <= 0:
        return np.zeros(hand.shape, dtype=bool)
    eligible = (hand >= 0) & (hand <= depth)
    seeds = eligible & river
    return ndimage.binary_propagation(seeds, structure=np.ones((3, 3), dtype=bool), mask=eligible)


def scores(pred: np.ndarray, truth: np.ndarray, valid: np.ndarray) -> dict[str, float | int]:
    p, t = pred[valid], truth[valid]
    tp = int(np.count_nonzero(p & t)); fp = int(np.count_nonzero(p & ~t)); fn = int(np.count_nonzero(~p & t))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    iou = tp / (tp + fp + fn) if tp + fp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision,
            "recall": recall, "f1": f1, "iou": iou, "evaluation_pixels": int(valid.sum())}


def main() -> None:
    settings = load_config().get("gauge_hand", {})
    global FLOW_THRESHOLD_KM2, BUFFER_M, H0_VALUES
    FLOW_THRESHOLD_KM2 = float(settings.get("flow_accumulation_threshold_km2", FLOW_THRESHOLD_KM2))
    BUFFER_M = float(settings.get("processing_buffer_m", BUFFER_M))
    h0_min = float(settings.get("h0_search_min_m", 0.0))
    h0_max = float(settings.get("h0_search_max_m", 11.5))
    h0_step = float(settings.get("h0_search_step_m", 0.25))
    H0_VALUES = np.round(np.arange(h0_min, h0_max + h0_step / 2, h0_step), 2)
    transform, width, height, profile, zone_masks = make_grid()
    in_zones = np.logical_or.reduce(list(zone_masks.values()))
    dem = fetch_dem(transform, width, height, profile)
    print(f"DEM grid: {width}x{height}; valid {np.mean(dem != NODATA):.1%}", flush=True)
    if HAND_PATH.exists():
        with rasterio.open(HAND_PATH) as src:
            hand = src.read(1)
        diagnostics = np.load(PROC / "gauge_hand_flow_diagnostics.npz")
        river = diagnostics["river_network"].astype(bool)
    else:
        hand, river = derive_hand(dem, transform, profile)
    events = json.loads((PROC / "events.json").read_text(encoding="utf-8")) if (PROC / "events.json").exists() else None
    zones = json.loads((PROC / "zones.geojson").read_text(encoding="utf-8"))["features"]
    cell_area_km2 = abs(transform.a * transform.e - transform.b * transform.d) / 1e6
    h0_rows = []
    flood19, exclusion19, permanent19 = aligned_gfm(GFM_2019, hand.shape, transform, GRID)
    bantwal_feature = next(f for f in zones if f["properties"]["name"] == "Bantwal taluk")
    bantwal_mask = zone_masks[str(bantwal_feature["properties"]["zone_id"])]
    ref_valid = (flood19 != 255) & (exclusion19 == 0) & (permanent19 == 0) & bantwal_mask
    truth19 = flood19 == 1
    if not ref_valid.any() or not truth19[ref_valid].any():
        raise RuntimeError("2019 GFM has no usable positive flood pixels on the model grid")
    for h0 in H0_VALUES:
        pred = connected_inundation(hand, river, STAGES[GFM_2019], float(h0))
        row = {"h0_m": float(h0), **scores(pred, truth19, ref_valid),
               "inundated_area_km2_bantwal": float((pred & bantwal_mask).sum() * cell_area_km2)}
        h0_rows.append(row)
    best = max(h0_rows, key=lambda r: (r["iou"], r["f1"], -r["inundated_area_km2_bantwal"]))
    h0 = float(best["h0_m"])
    write_csv(PROC / "gauge_hand_h0_sensitivity_2019.csv", h0_rows)
    (PROC / "gauge_hand_model.json").write_text(json.dumps({
        "model": "gauge_stage_minus_calibrated_h0_hand_screen",
        "dem": "Copernicus DEM GLO-30 DSM", "flow_algorithm": "PyFlwDir D8 with depression filling",
        "flow_accumulation_threshold_km2": FLOW_THRESHOLD_KM2,
        "channel_definition": "drainage cells with upstream contributing area >= threshold",
        "processing_buffer_m": BUFFER_M, "output_grid": {"crs": GRID, "transform": list(transform),
            "width": width, "height": height, "cell_area_km2": cell_area_km2},
        "gauges": STAGES, "danger_level_m": 9.0, "normal_monsoon_stage_m": 7.0,
        "h0_m": h0, "h0_selection": "maximum 2019 Bantwal GFM IoU on non-nodata, non-excluded, non-permanent-water pixels; ties by F1 then smaller Bantwal area",
        "calibration_metrics_2019": best,
        "gfm_score_support": "GFM observed labels reprojected nearest-neighbor to aligned 30m model grid; only 2019 used to fit h0",
        "limitations": ["Copernicus GLO-30 is a DSM including buildings and vegetation.",
                        "D8 terrain routing and a static stage threshold are a screening model, not hydraulic simulation.",
                        "HAND/stage vertical datum and gauge zero are not physically harmonized; h0 is empirical.",
                        "GFM labels are an algorithmic comparison product, not independent ground truth."]
    }, indent=2), encoding="utf-8")

    gauge_rows = []
    area_rows = []
    metric_rows = []
    zone_rows = []
    local_rows = []
    locality_log = list(csv.DictReader((PROC / "locality_geocoding_log.csv").open(encoding="utf-8-sig")))
    transformer = Transformer.from_crs("EPSG:4326", GRID, always_xy=True)
    localities = []
    for row in locality_log:
        if not (row.get("method", "").startswith("automatic_osm") or row.get("method") == "manual") or not row.get("coordinates"):
            continue
        try:
            lon, lat = (float(x.strip()) for x in row["coordinates"].split(","))
            localities.append((row["locality"], transformer.transform(lon, lat), row["method"], row["source"]))
        except (ValueError, TypeError):
            continue
    for day, stage in STAGES.items():
        depth = stage - h0
        predicted = connected_inundation(hand, river, stage, h0)
        out_path = PROC / f"gauge_hand_inundation_{day}.tif"
        mask_profile = profile.copy()
        mask_profile.update(dtype="uint8", nodata=255, predictor=2)
        with rasterio.open(out_path, "w", **mask_profile) as dst:
            dst.write(np.where(predicted, 1, np.where(hand != NODATA, 0, 255)).astype("uint8"), 1)
            dst.set_band_description(1, "0/1 candidate inundation screen; 255 nodata")
            dst.update_tags(stage_m=stage, h0_m=h0, water_depth_m=depth,
                            method="HAND <= stage-h0 and 8-connected to flowacc drainage network")
        gauge_rows.append({"event_date": day, "gauge_stage_m": stage, "danger_level_m": 9.0,
                           "normal_monsoon_stage_m": 7.0, "reference_stage_h0_m": h0,
                           "relative_water_depth_m": depth,
                           "stage_source": "CWC 2021 flood bulletin; event-specific media sources in event_sources",
                           "normal_stage_source": "CWC 2021 bulletin: Bantwal Netravathi normal 7.0 m, danger 9.0 m",
                           "cwc_source_url": "https://cwc.gov.in/sites/default/files/dfbcwc23072021_3.pdf",
                           "event_sources": "https://www.deccanherald.com/india/karnataka/water-in-nethravathi-river-touches-record-level-753354.html; https://www.daijiworld.com/news/newsDisplay?newsID=1212288; https://www.daijiworld.com/news/newsDisplay?newsID=1321707"})
        for feature in zones:
            props = feature["properties"]
            mask = zone_masks[str(props["zone_id"])] & (hand != NODATA)
            flooded = mask & predicted
            area = float(flooded.sum() * cell_area_km2)
            fraction = float(flooded.sum() / mask.sum()) if mask.any() else 0.0
            area_rows.append({"event_date": day, "zone_id": props["zone_id"], "zone_name": props["name"],
                              "gauge_stage_m": stage, "h0_m": h0, "relative_water_depth_m": depth,
                              "valid_zone_pixels": int(mask.sum()), "candidate_inundation_pixels": int(flooded.sum()),
                              "candidate_inundation_area_km2": area, "candidate_inundation_fraction": fraction,
                              "interpretation": "HAND screening area; not validated flood extent"})
            zone_rows.append({"event_date": day, "zone_id": props["zone_id"], "zone_name": props["name"],
                              "gauge_hand_inundated_fraction": fraction,
                              "gauge_hand_inundated_area_km2": area,
                              "feature_source": "2019-calibrated h0; stage-only event update"})
        if day in {"2019-08-10", "2026-08-03"}:
            flood, exclusion, permanent = aligned_gfm(day, hand.shape, transform, GRID)
            valid = (flood != 255) & (exclusion == 0) & (permanent == 0) & in_zones
            metric_rows.append({"event_date": day, "scope": "all taluks", "gauge_stage_m": stage, "h0_m_frozen_2019": h0,
                                **scores(predicted, flood == 1, valid),
                                "comparison_scope": "GFM-valid non-excluded, non-permanent-water pixels only"})
            for feature in zones:
                zid = str(feature["properties"]["zone_id"])
                zone_valid = (flood != 255) & (exclusion == 0) & (permanent == 0) & zone_masks[zid]
                metric_rows.append({"event_date": day, "scope": feature["properties"]["name"],
                                    "gauge_stage_m": stage, "h0_m_frozen_2019": h0,
                                    **scores(predicted, flood == 1, zone_valid),
                                    "comparison_scope": "GFM-valid non-excluded, non-permanent-water pixels only"})
        for name, xy, method, source in localities:
            col, row = ~transform * xy
            ir, ic = int(row), int(col)
            if not (0 <= ir < hand.shape[0] and 0 <= ic < hand.shape[1]) or not in_zones[ir, ic]:
                continue
            h = float(hand[ir, ic])
            local_rows.append({"event_date": day, "locality": name, "geocoding_method": method,
                               "source": source, "hand_m": h if h != NODATA else "",
                               "stage_minus_h0_m": depth,
                               "depth_margin_m": depth - h if h != NODATA else "",
                               "screen_marks_flooded": bool(predicted[ir, ic]),
                               "interpretation": "descriptive point check; not accuracy evidence"})
    write_csv(PROC / "gauge_stage.csv", gauge_rows)
    write_csv(PROC / "gauge_hand_area_by_zone.csv", area_rows)
    write_csv(PROC / "gauge_hand_zone_features.csv", zone_rows)
    write_csv(PROC / "gauge_hand_scores.csv", metric_rows)
    write_csv(PROC / "gauge_hand_verified_locality_checks.csv", local_rows)
    print(f"HAND raster: {HAND_PATH}")
    print(f"2019-calibrated h0: {h0:.2f} m; depth at 2019 gauge peak: {STAGES[GFM_2019]-h0:.2f} m")
    print(f"2019 fit: IoU={best['iou']:.4f}, F1={best['f1']:.4f}; h0 curve has {len(h0_rows)} values")
    for row in metric_rows:
        print(f"{row['event_date']}: precision={row['precision']:.4f}, recall={row['recall']:.4f}, F1={row['f1']:.4f}, IoU={row['iou']:.4f}")
    print(f"Wrote gauge-stage, area, per-zone feature, score and locality tables under {PROC}")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
