"""Subset cached zone-keyed Module 4 inputs to the configured focus zones."""

from __future__ import annotations

import csv
from pathlib import Path

from resq.config import configured_path, load_config
from resq.events import load_events


def main() -> None:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    import json
    zones = json.loads(configured_path(config["data"]["zones_path"]).read_text(encoding="utf-8"))["features"]
    zone_ids = {str(feature["properties"]["zone_id"]) for feature in zones}
    if not zone_ids:
        raise ValueError("Configured focus-zone file is empty")
    paths = [processed / f"zone_severity_{event.event_date.isoformat()}.csv" for event in load_events()]
    paths += [processed / f"zone_rainfall_{event.event_date.isoformat()}.csv" for event in load_events()]
    paths += [processed / "gauge_hand_area_by_zone.csv", processed / "gauge_hand_zone_features.csv"]
    for path in paths:
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            rows = [row for row in reader if str(row.get("zone_id", "")) in zone_ids]
        if not rows:
            raise ValueError(f"No configured focus-zone rows found in {path}")
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[{path.name}] retained {len(rows)} focus-zone row(s)")


if __name__ == "__main__":
    main()
