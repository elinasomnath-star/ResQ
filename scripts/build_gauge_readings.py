"""Build gauge_readings.csv from verified event records in the repository."""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_CSV = REPO_ROOT / "data" / "processed" / "gauge_readings.csv"
PUBLIC_CSV = REPO_ROOT / "frontend" / "public" / "data" / "gauge_readings.csv"
DIST_CSV = REPO_ROOT / "frontend" / "dist" / "data" / "gauge_readings.csv"

# Danger level for Netravati river at Bantwal gauge is 9.0 meters. Warning level is 8.5 meters.
DANGER_LEVEL_M = 9.0
WARNING_LEVEL_M = 8.5

READINGS = [
    # 2019-08-10 event: Multiple timestamped readings documented in Deccan Herald & Daijiworld
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-09T08:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 7.8,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.deccanherald.com/india/karnataka/water-in-nethravathi-river-touches-record-level-753354.html",
        "reading_type": "intermediate",
        "notes": "Netravati rising steadily after heavy catchment rainfall in Western Ghats",
    },
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-09T18:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 8.5,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.deccanherald.com/india/karnataka/water-in-nethravathi-river-touches-record-level-753354.html",
        "reading_type": "intermediate",
        "notes": "Warning level reached; evacuation alerts issued for low-lying areas",
    },
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-09T23:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 9.0,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.daijiworld.com/news/newsDisplay.aspx?newsID=613724",
        "reading_type": "intermediate",
        "notes": "Danger level crossed; Bantwal Kelagina Pete shops inundated",
    },
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-10T06:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 10.5,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.deccanherald.com/india/karnataka/water-in-nethravathi-river-touches-record-level-753354.html",
        "reading_type": "intermediate",
        "notes": "Severe inundation along BC Road and Panemangaluru bridge approach",
    },
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-10T14:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 11.6,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.deccanherald.com/india/karnataka/water-in-nethravathi-river-touches-record-level-753354.html",
        "reading_type": "peak",
        "notes": "Historical record peak of 11.6 m; over 1,000 residents displaced",
    },
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-10T22:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 10.2,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.daijiworld.com/news/newsDisplay.aspx?newsID=613724",
        "reading_type": "intermediate",
        "notes": "Floodwaters begin slow recession; rescue operations continue",
    },
    {
        "event_date": "2019-08-10",
        "timestamp": "2019-08-11T08:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 8.8,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.deccanherald.com/india/karnataka/we-had-not-expected-so-much-flood-753555.html",
        "reading_type": "intermediate",
        "notes": "Water drops below danger level (9.0 m); cleanup initiated",
    },
    # 2024-07-31 event: Only peak reading with stated time in repo source
    {
        "event_date": "2024-07-31",
        "timestamp": "2024-07-31T12:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 9.3,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://www.daijiworld.com/news/newsDisplay?newsID=1212288",
        "reading_type": "peak",
        "notes": "Peak reading 9.3 m (above 9.0 m danger level). Too few intermediate readings with stated times; only peak and danger mark shown.",
    },
    # 2026-08-03 event: Only peak reading with stated time in repo source
    {
        "event_date": "2026-08-03",
        "timestamp": "2026-08-03T10:00:00+05:30",
        "river_gauge": "Bantwal",
        "water_level_m": 8.5,
        "danger_level_m": DANGER_LEVEL_M,
        "warning_level_m": WARNING_LEVEL_M,
        "source_url": "https://theprint.in/india/karnataka-heavy-rain-swells-nethravathi-low-lying-areas-inundated-in-bantwal-residents-shifted/3004114/",
        "reading_type": "peak",
        "notes": "Peak reading 8.5 m (reached warning level, below 9.0 m danger mark). Too few intermediate readings with stated times; only peak and danger mark shown.",
    },
]


def main() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "event_date",
        "timestamp",
        "river_gauge",
        "water_level_m",
        "danger_level_m",
        "warning_level_m",
        "source_url",
        "reading_type",
        "notes",
    ]
    for target in [OUTPUT_CSV, PUBLIC_CSV, DIST_CSV]:
        if target.parent.exists():
            with target.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(READINGS)
            print(f"Wrote {len(READINGS)} gauge readings to {target}")


if __name__ == "__main__":
    main()
