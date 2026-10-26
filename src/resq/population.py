"""Fetch recent WorldPop polygon totals and retain the 2011 census comparison."""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import configured_path, load_config


def _worldpop_request(url: str, *, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "ResQ-disaster-relief-prototype/0.1"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"WorldPop request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("WorldPop returned an unexpected response")
    return result


def _submit(api_base: str, feature: dict[str, Any], year: int, resolution: str) -> tuple[str, dict[str, Any] | None]:
    response = _worldpop_request(
        f"{api_base.rstrip('/')}/population",
        payload={"geojson": feature["geometry"], "year": year, "resolution": resolution},
    )
    task_id = response.get("task_id")
    if not task_id:
        result = response.get("result") or response.get("data")
        if result and result.get("total_population") is not None:
            return "", result
        raise RuntimeError(f"WorldPop did not return a task ID: {response}")
    return str(task_id), None


def _poll(api_base: str, task_id: str, *, timeout_s: int = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        response = _worldpop_request(f"{api_base.rstrip('/')}/tasks/{task_id}")
        status = str(response.get("status", "")).casefold()
        if status in {"success", "finished", "completed"}:
            result = response.get("result") or response.get("data") or {}
            if result.get("total_population") is None:
                raise RuntimeError(f"WorldPop task succeeded without total_population: {response}")
            return {"task_id": task_id, "status": status, "response": response, "result": result}
        if status in {"failure", "failed", "error"} or response.get("error") is True:
            raise RuntimeError(f"WorldPop task failed: {response}")
        time.sleep(2)
    raise TimeoutError(f"WorldPop task {task_id} did not finish within {timeout_s} seconds")


def estimate_zone_populations(
    path: str | Path | None = None,
    *,
    year: int | None = None,
    config: dict[str, Any] | None = None,
    control_total: float | None = None,
) -> tuple[Path, Path]:
    """Call WorldPop's polygon statistics API and update zone properties/CSV."""
    config = config or load_config()
    region = config["region"]
    year = int(year if year is not None else region["population_model_year"])
    resolution = str(region["population_resolution"])
    api_base = str(region["population_api_base"])
    zone_path = Path(path) if path is not None else configured_path(config["data"]["zones_path"])
    if not zone_path.is_absolute():
        zone_path = configured_path(zone_path)
    collection = json.loads(zone_path.read_text(encoding="utf-8"))
    features = collection.get("features", [])
    if not features:
        raise ValueError(f"No zone polygons found in {zone_path}")

    submissions: list[tuple[dict[str, Any], str, dict[str, Any] | None]] = []
    for feature in features:
        task_id, immediate_result = _submit(api_base, feature, year, resolution)
        submissions.append((feature, task_id, immediate_result))

    raw_results: list[dict[str, Any]] = []
    completed: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for feature, task_id, immediate_result in submissions:
        result_record = (
            {"task_id": "", "status": "success", "response": immediate_result, "result": immediate_result}
            if immediate_result is not None else _poll(api_base, task_id)
        )
        raw_results.append({"zone_id": feature["properties"].get("zone_id"), **result_record})
        completed.append((feature, result_record["result"], result_record["task_id"]))

    raw_total = sum(float(result["total_population"]) for _, result, _ in completed)
    if raw_total <= 0:
        raise ValueError("WorldPop returned a non-positive total for Bantwal village zones")
    target_total = float(control_total) if control_total is not None else raw_total
    if target_total <= 0:
        raise ValueError("Population control total must be positive")
    normalization_factor = target_total / raw_total
    rows: list[dict[str, Any]] = []
    for feature, result, task_id in completed:
        properties = feature["properties"]
        raw_estimate = float(result["total_population"])
        total = raw_estimate * normalization_factor
        properties["population_estimate"] = round(total, 2)
        properties["population_source"] = region["population_model_source_url"]
        properties["population_model"] = str(region["population_model"])
        properties["population_year"] = year
        properties["population_basis"] = (f"WorldPop {year} {resolution} village estimates, normalized to the Bantwal parent-zone total"
                                           if control_total is not None else
                                           f"WorldPop {year} {resolution} modeled total within this polygon")
        properties["population_resolution"] = resolution
        properties["population_task_id"] = task_id
        properties["population_area_km2"] = result.get("area_km2")
        properties["population_worldpop_raw_estimate"] = round(raw_estimate, 2)
        properties["population_normalization_factor"] = normalization_factor
        properties["population_density_per_km2"] = round(total / max(float(result.get("area_km2") or 0), 1e-9), 2)
        properties["population_api_dataset"] = result.get("data_source")
        properties["population_census_2011_reference"] = properties.get("population_census_2011")
        rows.append({
            "zone_id": properties.get("zone_id"),
            "zone_name": properties.get("name"),
            "population_estimate": round(total, 2),
            "population_worldpop_raw_estimate": round(raw_estimate, 2),
            "population_normalization_factor": normalization_factor,
            "population_year": year,
            "population_model": "WorldPop Global2 R2025A v1",
            "population_source": region["population_model_source_url"],
            "population_resolution": resolution,
            "population_area_km2": result.get("area_km2"),
            "population_density_per_km2": properties["population_density_per_km2"],
            "population_api_dataset": result.get("data_source"),
            "population_census_2011": properties.get("population_census_2011"),
            "population_census_code_match": properties.get("population_census_code_match"),
            "population_census_reference_year": properties.get("population_census_reference_year"),
            "population_census_source": properties.get("population_census_source"),
            "population_task_id": task_id,
        })

    zone_path.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    raw_dir = configured_path(config["data"]["raw_dir"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"population_worldpop_{year}.json"
    raw_path.write_text(json.dumps({"year": year, "resolution": resolution, "control_total": control_total,
                                    "normalization_factor": normalization_factor,
                                    "results": raw_results}, indent=2), encoding="utf-8")
    csv_path = configured_path(config["data"]["processed_dir"]) / f"zone_population_{year}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return zone_path, csv_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch WorldPop population estimates for the configured zones.")
    parser.add_argument("--year", type=int, help="WorldPop year (default: config/region.yaml)")
    args = parser.parse_args()
    config = load_config()
    analysis_path = configured_path(config["data"].get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
    if analysis_path.exists():
        collection = json.loads(analysis_path.read_text(encoding="utf-8"))
        if collection.get("features") and all(
            f.get("properties", {}).get("zone_type") == "admin_village_boundary"
            for f in collection["features"]
        ):
            parent_collection = json.loads(configured_path(config["data"]["zones_path"]).read_text(encoding="utf-8"))
            parent = next((f for f in parent_collection.get("features", [])
                           if str(f.get("properties", {}).get("name", "")).casefold().startswith("bantwal")), None)
            total = float((parent or {}).get("properties", {}).get("population_estimate") or 0)
            if total <= 0:
                raise ValueError("Bantwal parent WorldPop estimate is missing; run python -m resq.population after building the taluk zones")
            zones, table = estimate_zone_populations(path=analysis_path, year=args.year,
                                                     config=config, control_total=total)
            print(f"Village estimates normalized to Bantwal parent WorldPop total: {total:,.0f}")
        else:
            zones, table = estimate_zone_populations(year=args.year, config=config)
    else:
        zones, table = estimate_zone_populations(year=args.year, config=config)
    print(f"Updated zone estimates: {zones}")
    print(f"Population table: {table}")
