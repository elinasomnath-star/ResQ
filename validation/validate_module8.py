"""Validate Module 8 artifacts for all three event scenarios."""

from __future__ import annotations

import csv
import json

from resq.config import configured_path, load_config
from resq.events import load_events


def main() -> None:
    processed = configured_path(load_config()["data"]["processed_dir"])
    expected_engines = {"MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline"}
    for event in load_events():
        day = event.event_date.isoformat()
        summary_path = processed / f"module8_dynamic_summary_{day}.json"
        steps_path = processed / f"module8_dynamic_steps_{day}.csv"
        zone_shortfall_path = processed / f"module8_dynamic_zone_unmet_{day}.csv"
        zones_path = processed / "zones_module8_analysis_grid.geojson"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["steps"] in range(5, 11)
        zones = json.loads(zones_path.read_text(encoding="utf-8"))["features"]
        assert summary["zone_metadata"]["mangaluru_ward_count"] == 0
        assert summary["zone_metadata"]["zone_count"] == len(zones) == 16
        assert all(z["properties"].get("zone_type") == "analysis_grid" for z in zones)
        assert all(str(z["properties"].get("parent_name", "")).casefold() == "bantwal taluk" for z in zones)
        assert {z["properties"].get("zone_id") for z in zones} == {f"bantwal_grid_{i:02d}" for i in range(1, 17)}
        assert set(summary["engines"]) == expected_engines
        closure = summary["module7_closure_impact"]
        assert closure["verified_closures"], f"{day}: Module 8 did not consume verified Module 7 closure geometry"
        assert int(closure["removed_directed_edges"]) > 0, f"{day}: verified closure removed no graph edges"
        assert "verified module 7 closure geometry" in summary["disruption_model"].casefold()
        assert summary["module9"]["integrated"] is True
        assert 0 <= float(summary["shortage_threshold"]) <= 1
        with steps_path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == summary["steps"] * len(expected_engines)
        assert {r["engine"] for r in rows} == expected_engines
        activation = int(summary["closure_activation_step"])
        for row in rows:
            assert row["closure_active"].casefold() == ("true" if int(row["step"]) >= activation else "false")
            if int(row["step"]) == activation:
                assert int(row["closure_edges_removed"]) == int(closure["removed_directed_edges"])
            assert 0 <= float(row["minimum_zone_coverage_before_escalation_pct"]) <= 100
            assert 0 <= float(row["minimum_zone_coverage_after_escalation_pct"]) <= 100
            assert int(row["stopgap_transfer_count"]) >= 0
        for engine in expected_engines:
            records = [r for r in rows if r["engine"] == engine]
            assert len(records) == summary["steps"]
            assert all(float(r["step_inference_or_solve_seconds"]) >= 0 for r in records)
            assert float(summary["engines"][engine]["cumulative_solve_or_inference_seconds"]) >= 0
            assert len(summary["engines"][engine]["final_per_zone_unmet"]) == summary["zone_metadata"]["zone_count"]
        with zone_shortfall_path.open(newline="", encoding="utf-8") as stream:
            zone_rows = list(csv.DictReader(stream))
        assert len(zone_rows) == summary["zone_metadata"]["zone_count"] * len(expected_engines) * 3
        assert {r["engine"] for r in zone_rows} == expected_engines
        assert all(float(z["properties"].get("population_estimate", -1)) >= 0 for z in zones)
        print(f"[{day}] Module 8 artifacts pass (16 Bantwal analysis-grid zones, {summary['steps']} steps, 3 engines)")


if __name__ == "__main__":
    main()
