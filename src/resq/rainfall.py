"""Download and aggregate observed CHIRPS v2 daily rainfall for event windows."""

from __future__ import annotations

import csv
import gzip
import json
import tempfile
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import shape

from .config import configured_path, load_config


BASE_URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_daily/tifs/p05"


def _get_daily_raster(day: date, config: dict[str, Any]) -> Path:
    raw = configured_path(config["data"]["raw_dir"]) / "chirps"
    raw.mkdir(parents=True, exist_ok=True)
    stem = f"chirps-v2.0.{day:%Y.%m.%d}"
    gz_path = raw / f"{stem}.tif.gz"
    if gz_path.exists(): return gz_path
    url = f"{BASE_URL}/{day.year}/{stem}.tif.gz"
    request = urllib.request.Request(url, headers={"User-Agent": "ResQ-disaster-allocation/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, gz_path.open("wb") as stream:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk: break
            stream.write(chunk)
    return gz_path


def aggregate_event_rainfall(event_date: date, zones: list[dict[str, Any]],
                             config: dict[str, Any] | None = None, days: int = 7) -> dict[str, float]:
    """Return zone mean of antecedent precipitation sum (mm), ending event day."""
    config = config or load_config()
    sums = {str(z["properties"]["zone_id"]): 0.0 for z in zones}
    counts = {key: 0 for key in sums}
    for lag in range(days):
        day = event_date - timedelta(days=lag)
        compressed_path = _get_daily_raster(day, config)
        with tempfile.TemporaryDirectory(prefix="resq-chirps-") as temp_dir:
            raster = Path(temp_dir) / f"{day.isoformat()}.tif"
            with gzip.open(compressed_path, "rb") as compressed, raster.open("wb") as decompressed:
                while True:
                    chunk = compressed.read(1024 * 1024)
                    if not chunk: break
                    decompressed.write(chunk)
            with rasterio.open(raster) as src:
                for zone in zones:
                    key = str(zone["properties"]["zone_id"])
                    value = None
                    try:
                        values, _ = mask(src, [zone["geometry"]], crop=True, filled=False, indexes=1)
                    except ValueError:
                        values = np.ma.array([], dtype=float)
                    valid = values.compressed()
                    valid = valid[np.isfinite(valid) & (valid >= 0)]
                    if valid.size:
                        # Daily mean per zone, then sum daily means; this avoids
                        # interpreting the raster nodata sentinel as rainfall.
                        value = float(valid.mean())
                    else:
                        # CHIRPS is much coarser than the analysis grid. Some
                        # clipped edge cells contain no pixel centre at all;
                        # sample the cell's representative point so small cells
                        # get a documented coarse-grid estimate instead of NaN.
                        point = shape(zone["geometry"]).representative_point()
                        sampled = next(src.sample([(point.x, point.y)], masked=True))[0]
                        if np.isfinite(sampled) and sampled >= 0:
                            value = float(sampled)
                    if value is not None:
                        sums[key] += value
                        counts[key] += 1
    return {key: (sums[key] / counts[key] * days if counts[key] else float("nan"))
            for key in sums}


def write_event_rainfall(event_date: date, zones: list[dict[str, Any]],
                         config: dict[str, Any] | None = None, days: int = 7) -> Path:
    config = config or load_config()
    totals = aggregate_event_rainfall(event_date, zones, config, days)
    path = configured_path(config["data"]["processed_dir"]) / f"zone_rainfall_{event_date.isoformat()}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["event_date", "zone_id", "antecedent_days", "rainfall_mm", "source"])
        for zone in zones:
            key = str(zone["properties"]["zone_id"])
            writer.writerow([event_date.isoformat(), key, days, totals[key],
                             "CHIRPS v2 daily global 0.05-degree"])
    return path

