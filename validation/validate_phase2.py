"""Validate real-input Phase II artifacts for all configured flood events."""

from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date

import rasterio

from resq.config import REPO_ROOT, configured_path, load_config
from resq.events import load_events


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    expected = {event.event_date.isoformat() for event in load_events()}
    for day in sorted(expected):
        manifest_path = processed / f"sar_manifest_{day}.json"
        raster_path = processed / f"flood_likelihood_{day}.tif"
        severity_path = processed / f"zone_severity_{day}.csv"
        demand_path = processed / f"severity_demand_{day}.csv"
        comparison_path = processed / f"allocation_comparison_{day}.csv"
        matrix_path = processed / f"allocation_matrix_{day}.csv"
        zone_metrics_path = processed / f"allocation_zone_metrics_{day}.csv"
        heatmap_path = processed / f"flood_likelihood_{day}.svg"
        for path in (manifest_path, raster_path, severity_path, demand_path, comparison_path, matrix_path, zone_metrics_path, heatmap_path):
            assert path.exists() and path.stat().st_size > 0, f"Missing Phase II output: {path}"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["before_items"] and manifest["during_items"]
        assert manifest["hand_threshold_m"] > 0 and len(manifest["thresholds_db"]) >= 3
        assert manifest["before_composite_method"].startswith("median")
        assert str(heatmap_path) in manifest["generated_outputs"]
        before_days = int(manifest["before_days_before_event"])
        assert (14 <= before_days <= 21) if not manifest["before_window_fallback"] else (21 < before_days <= 35)
        window_end = date.fromisoformat(manifest.get("event_window_end_date", day))
        during_days_after_end = (date.fromisoformat(manifest["during_date"]) - window_end).days
        if manifest.get("during_window_fallback"):
            assert during_days_after_end > 3
        else:
            assert during_days_after_end <= 3
        with rasterio.open(raster_path) as src:
            image = src.read(1, masked=True)
            assert src.count == 1 and src.crs is not None and image.count() > 0
            assert float(image.min()) >= 0 and float(image.max()) <= 1
        svg = heatmap_path.read_text(encoding="utf-8")
        assert "<svg" in svg and "HAND" in svg and "linearGradient" in svg and "stroke=\"#f05a28\"" in svg
        ET.parse(heatmap_path)
        severity = rows(severity_path)
        analysis_path = configured_path(config["data"].get("analysis_zones_path", config["data"]["zones_path"]))
        analysis_features = json.loads(analysis_path.read_text(encoding="utf-8"))["features"]
        expected_zone_ids = {f["properties"]["zone_id"] for f in analysis_features}
        assert len(analysis_features) == 16
        assert len(severity) == 16 and {r["zone_id"] for r in severity} == expected_zone_ids
        assert all(int(r.get("valid_pixels", 0)) > 0 for r in severity)
        assert all(int(r.get("hand_eligible_pixels", 0)) <= int(r.get("valid_pixels", 0)) for r in severity)
        assert all(float(r["mean_hand_restricted_flood_likelihood"]) >= 0 for r in severity if r["status"] == "computed")
        for row in severity:
            for field in ("mean_hand_restricted_flood_likelihood", "naive_flood_candidate_fraction",
                          "hand_restricted_flood_candidate_fraction", "population_estimate"):
                assert math.isfinite(float(row[field])), f"Non-finite {field} for {day} {row['zone_id']}"
        assert all(float(r["naive_flood_candidate_fraction"]) + 1e-9 >=
                   float(r["hand_restricted_flood_candidate_fraction"])
                   for r in severity if r["status"] == "computed"), "HAND restriction should not add candidate pixels."
        demand = rows(demand_path)
        assert len(demand) == 16 and {r["zone_id"] for r in demand} == expected_zone_ids
        assert all(math.isfinite(float(r["severity_score"])) and float(r["severity_score"]) >= 0 for r in demand)
        for row in demand:
            for field in ("sar_likelihood", "gauge_hand_inundated_fraction",
                          "antecedent_7day_rainfall_mm", "population_estimate"):
                assert math.isfinite(float(row[field])), f"Non-finite {field} for {day} {row['zone_id']}"
        model_metadata = json.loads((processed / f"severity_model_{day}.json").read_text(encoding="utf-8"))
        assert model_metadata["synthetic_training_rows"] == 600
        if day != "2019-08-10":
            assert model_metadata["validation_event"] == day
            assert model_metadata["validation_gauge_proxy"] is not None
        comparison = rows(comparison_path)
        assert {"MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline"}.issubset({r["engine"] for r in comparison})
        assert all(0 <= float(r["aggregate_unmet_demand_pct"]) <= 100 for r in comparison)
        assert all(float(r["requested_fairness_target_pct"]) == 40 for r in comparison)
        assert all(r["hard_fairness_target_status"] == "INFEASIBLE" for r in comparison)
        allocations = rows(matrix_path)
        assert allocations and all(int(r["allocated"]) <= int(r["estimated_need"]) for r in allocations)
        zone_metrics = rows(zone_metrics_path)
        assert len(zone_metrics) == 16 * 3
        assert all(0 <= float(r["minimum_resource_coverage_pct"]) <= 100 for r in zone_metrics)
        inventory = config["resources"]["prototype_inventory"]
        for engine in {r["engine"] for r in allocations}:
            for resource, stock in inventory.items():
                used = sum(int(r["allocated"]) for r in allocations
                           if r["engine"] == engine and r["resource"] == resource)
                assert used <= int(stock), f"{engine} exceeded {resource} inventory."
        for engine in {r["engine"] for r in allocations}:
            assert min(float(r["minimum_zone_fairness_pct"]) for r in comparison if r["engine"] == engine) >= 0
        print(f"Validated Phase II artifacts for {day}: SAR, HAND, demand, MILP, bandit and baseline.")


if __name__ == "__main__":
    main()
