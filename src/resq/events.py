"""Read and validate manually compiled historical event records."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import REPO_ROOT, load_config


@dataclass(frozen=True)
class FloodEvent:
    event_date: date
    river_gauge: str
    water_level_m: float
    affected_localities: tuple[str, ...]
    roads_blocked: tuple[str, ...]
    houses_affected: str
    source_urls: tuple[str, ...]


def load_events(path: str | Path | None = None) -> list[FloodEvent]:
    """Load CSV event records and reject missing or malformed required fields."""
    if path is None:
        config = load_config()
        path = REPO_ROOT / config["events"]["csv_path"]
    event_path = Path(path)
    if not event_path.is_absolute():
        event_path = REPO_ROOT / event_path

    events: list[FloodEvent] = []
    with event_path.open("r", newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        required = {
            "event_date", "river_gauge", "water_level_m", "affected_localities",
            "roads_blocked", "houses_affected", "source_url",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Event CSV must include columns: {', '.join(sorted(required))}")
        for line, row in enumerate(reader, start=2):
            try:
                urls = tuple(part.strip() for part in row["source_url"].split(";") if part.strip())
                localities = tuple(part.strip() for part in row["affected_localities"].split(";") if part.strip())
                roads = tuple(part.strip() for part in row["roads_blocked"].split(";") if part.strip())
                if not urls or any(not url.startswith(("https://", "http://")) for url in urls):
                    raise ValueError("source_url must contain one or more HTTP(S) URLs")
                if not localities:
                    raise ValueError("affected_localities cannot be empty")
                events.append(FloodEvent(
                    event_date=date.fromisoformat(row["event_date"]),
                    river_gauge=row["river_gauge"].strip(),
                    water_level_m=float(row["water_level_m"]),
                    affected_localities=localities,
                    roads_blocked=roads,
                    houses_affected=row["houses_affected"].strip(),
                    source_urls=urls,
                ))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid event row at {event_path}:{line}: {exc}") from exc
    if not events:
        raise ValueError(f"No event records found in {event_path}")
    return events
