"""Download the configured WorldPop raster from its public GeoTIFF URL."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.request import urlopen


URL = "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/IND/v1/1km_ua/constrained/ind_pop_2025_CN_1km_R2025A_UA_v1.tif"
DESTINATION = Path("data/raw/ind_pop_2025_CN_1km_R2025A_UA_v1.tif")


def main() -> None:
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    partial = DESTINATION.with_suffix(DESTINATION.suffix + ".part")
    total = 0
    try:
        with urlopen(URL, timeout=120) as response, partial.open("wb") as output:
            expected = int(response.headers.get("Content-Length", "0"))
            while block := response.read(8 * 1024 * 1024):
                output.write(block)
                total += len(block)
                print(f"Downloaded {total / 1024**2:.0f} MiB" +
                      (f" / {expected / 1024**2:.0f} MiB" if expected else ""), flush=True)
        if expected and total != expected:
            raise IOError(f"Incomplete WorldPop download: expected {expected} bytes, got {total}")
        partial.replace(DESTINATION)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    print(f"Saved WorldPop raster to {DESTINATION} ({total:,} bytes)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"WorldPop download failed: {exc}", file=sys.stderr)
        raise
