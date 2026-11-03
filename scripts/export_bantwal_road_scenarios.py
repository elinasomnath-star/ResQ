"""Build frontend road-scenario cards and blocked-road map geometry from config."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "bantwal_road_scenarios.json"
PUBLIC_DATA = ROOT / "frontend" / "public" / "data"


def export() -> None:
    configured = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))["scenarios"]
    roads = {item["id"]: item for item in configured if item.get("coordinate_parts")}
    scenarios = [item for item in configured if item.get("title")]
    frontend_scenarios = []
    closure_features = []

    for scenario in scenarios:
        road_ids = scenario.get("road_ids") or [scenario["id"]]
        blocked = [roads[road_id] for road_id in road_ids]
        names = [road["name"] for road in blocked]
        parts = [part for road in blocked for part in road["coordinate_parts"]]
        points = [road["closure_point"] for road in blocked]
        highway = " + ".join(dict.fromkeys(road["highway"] for road in blocked))
        title = scenario["title"]
        description = scenario["description"]

        frontend_scenarios.append({
            "id": scenario["id"],
            "title": title,
            "description": description,
            "type": "road_closure",
            "event_date": "2024-07-31",
            "closure_id": scenario["id"],
            "parameters": {
                "blocked_roads": names,
                "road_count": len(names),
                "highway": highway,
                "boundary": "Bantwal analysis zones",
            },
            "assumptions_statement": scenario.get(
                "assumptions_statement",
                "Mapped Bantwal main-road corridors are blocked together; routes are recalculated against the remaining cached road graph."
                if len(names) > 1 else
                "A mapped Bantwal main-road corridor is blocked; routes are recalculated against the remaining cached road graph.",
            ),
        })

        closure_features.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": parts},
            "properties": {
                "closure_id": scenario["id"],
                "name": ", ".join(names),
                "highway": highway,
                "closure_points": points,
                **({"closure_point": points[0]} if len(points) == 1 else {}),
            },
        })

    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DATA / "scenarios.json").write_text(
        json.dumps({"scenarios": frontend_scenarios}, indent=2) + "\n", encoding="utf-8"
    )
    (PUBLIC_DATA / "bantwal_scenario_closures.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": closure_features}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(frontend_scenarios)} Bantwal road-blockage scenarios")


if __name__ == "__main__":
    export()
