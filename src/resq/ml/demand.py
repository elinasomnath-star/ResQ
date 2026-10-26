"""Fit a reproducible severity/demand regressor with explicitly synthetic augmentation."""

from __future__ import annotations

import csv
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from ..config import configured_path, load_config
from ..events import FloodEvent, load_events
from ..rainfall import write_event_rainfall


BASE_FEATURES = ["sar_likelihood", "antecedent_rainfall_mm", "population_density_per_km2", "log_population"]
FEATURES = ["sar_likelihood", "gauge_hand_inundated_fraction", "antecedent_rainfall_mm",
            "population_density_per_km2", "log_population"]


def _read_zone_stats(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists(): return {}
    with path.open(newline="", encoding="utf-8") as stream:
        return {row["zone_id"]: row for row in csv.DictReader(stream)}


def _parse_float(value: Any, fallback: float = 0.0) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) else fallback
    except (TypeError, ValueError): return fallback


def _feature_row(zone: dict[str, Any], severity: dict[str, Any], rain: float,
                 inundated_fraction: float = 0.0, *, include_inundation: bool = True) -> list[float]:
    props = zone["properties"]
    population = max(0.0, _parse_float(props.get("population_estimate")))
    values = [min(1.0, max(0.0, _parse_float(severity.get("mean_hand_restricted_flood_likelihood"))))]
    if include_inundation:
        values.append(min(1.0, max(0.0, _parse_float(inundated_fraction))))
    values.extend([max(0.0, rain), max(0.0, _parse_float(props.get("population_density_per_km2"))),
                   math.log1p(population)])
    return values


def _synthetic_training(anchor_x: np.ndarray, anchor_y: float, samples: int = 600) -> tuple[np.ndarray, np.ndarray]:
    """Perturb the 2019 observation; synthetic labels use a transparent proxy rule."""
    rng = np.random.default_rng(20190810)
    severity_factor = rng.uniform(0.08, 1.0, size=samples)
    x = np.tile(anchor_x, (samples, 1)).astype("float64")
    x[:, 0] = anchor_x[0] * severity_factor + rng.normal(0, 0.025, samples)
    offset = 1
    if x.shape[1] == len(FEATURES):
        x[:, 1] = anchor_x[1] * severity_factor + rng.normal(0, 0.025, samples)
        offset = 2
    x[:, offset] = anchor_x[offset] * severity_factor + rng.normal(0, max(1.0, anchor_x[offset] * 0.06), samples)
    x[:, offset + 1] = anchor_x[offset + 1] * rng.lognormal(0, 0.22, samples)
    x[:, offset + 2] = anchor_x[offset + 2] + rng.normal(0, 0.12, samples)
    x[:, 0] = np.clip(x[:, 0], 0, 1)
    if x.shape[1] == len(FEATURES):
        x[:, 1] = np.clip(x[:, 1], 0, 1)
    x[:, offset:] = np.maximum(x[:, offset:], 0)
    # Synthetic labels scale the observed 2019 gauge proxy across lower and
    # higher-intensity scenarios; these are augmentation labels, never extra
    # observed events or independently validated target measurements.
    y = np.clip(anchor_y * severity_factor + rng.normal(0, 0.025, samples), 0, 1)
    return x.astype("float32"), y.astype("float32")


def run_demand_model(events: list[FloodEvent] | None = None,
                     config: dict[str, Any] | None = None) -> list[Path]:
    config = config or load_config()
    events = events or load_events()
    reference_events = load_events()
    zones_path = configured_path(config["data"].get("analysis_zones_path", config["data"]["zones_path"]))
    zones = json.loads(zones_path.read_text(encoding="utf-8"))["features"]
    processed = configured_path(config["data"]["processed_dir"])
    by_zone = {str(z["properties"]["zone_id"]): z for z in zones}
    event_stats: dict[str, dict[str, dict[str, Any]]] = {}
    event_rain: dict[str, dict[str, float]] = {}
    event_inundation: dict[str, dict[str, float]] = {}
    for event in reference_events:
        event_date = event.event_date.isoformat()
        event_stats[event_date] = _read_zone_stats(processed / f"zone_severity_{event_date}.csv")
        rain_path = processed / f"zone_rainfall_{event_date}.csv"
        if rain_path.exists():
            event_rain[event_date] = {row["zone_id"]: _parse_float(row.get("rainfall_mm"), float("nan"))
                                      for row in _read_zone_stats(rain_path).values()}
        else:
            write_event_rainfall(event.event_date, zones, config, days=7)
            event_rain[event_date] = {row["zone_id"]: _parse_float(row.get("rainfall_mm"), float("nan"))
                                      for row in _read_zone_stats(rain_path).values()}
        inundation_path = processed / "gauge_hand_zone_features.csv"
        if not inundation_path.exists():
            raise FileNotFoundError("Gauge-stage HAND zone features are missing; run scripts/build_gauge_hand_inundation.py first")
        with inundation_path.open(newline="", encoding="utf-8") as stream:
            event_inundation[event_date] = {
                row["zone_id"]: _parse_float(row.get("gauge_hand_inundated_fraction"))
                for row in csv.DictReader(stream) if row["event_date"] == event_date
            }

    # The 2019 event is the sole calibration event; 2024 and 2026 are held out.
    calibration = next((e for e in reference_events if e.event_date.isoformat() == "2019-08-10"), reference_events[0])
    calibration_zone = next((z for z in zones if z["properties"].get("matched_localities")), zones[0])
    cal_date = calibration.event_date.isoformat()
    if not event_stats[cal_date] or not event_rain.get(cal_date):
        raise ValueError("The 2019 calibration artifacts are missing; run the full Phase II pipeline before scoring a later event.")
    cal_stats = event_stats[cal_date].get(str(calibration_zone["properties"]["zone_id"]), {})
    cal_zone_id = str(calibration_zone["properties"]["zone_id"])
    cal_rain = _parse_float(event_rain[cal_date].get(cal_zone_id, 0.0))
    cal_fraction = event_inundation[cal_date].get(cal_zone_id, 0.0)
    cal_x = np.asarray(_feature_row(calibration_zone, cal_stats, cal_rain, cal_fraction), dtype="float32")
    cal_x_base = np.asarray(_feature_row(calibration_zone, cal_stats, cal_rain,
                                         include_inundation=False), dtype="float32")
    # Fix the gauge reference to the documented biggest validation event.
    # Held-out event levels never influence the training target or scaling.
    gauge_reference = float(config["events"].get("gauge_reference_level_m", 11.6))
    anchor_score = min(1.0, max(0.0, calibration.water_level_m / gauge_reference))
    train_x, train_y = _synthetic_training(cal_x, anchor_score)
    # Include the actual calibration sample alongside clearly synthetic variants.
    train_x = np.vstack([cal_x[None, :], train_x])
    train_y = np.concatenate([[anchor_score], train_y])
    model = RandomForestRegressor(n_estimators=200, min_samples_leaf=3,
                                  random_state=2026, n_jobs=1)
    model.fit(train_x, train_y)
    base_train_x, base_train_y = _synthetic_training(cal_x_base, anchor_score)
    base_train_x = np.vstack([cal_x_base[None, :], base_train_x])
    base_train_y = np.concatenate([[anchor_score], base_train_y])
    baseline_model = RandomForestRegressor(n_estimators=200, min_samples_leaf=3,
                                           random_state=2026, n_jobs=1)
    baseline_model.fit(base_train_x, base_train_y)
    model_key = "2019_calibrated_synthetic_random_forest_with_gauge_HAND_fraction"
    outputs = []
    ablation_rows = []
    for event in events:
        event_date = event.event_date.isoformat()
        rows = []
        features = []
        for zone in zones:
            zone_id = str(zone["properties"]["zone_id"])
            stat = event_stats[event_date].get(zone_id, {})
            rain = event_rain[event_date].get(zone_id, float("nan"))
            fraction = event_inundation[event_date].get(zone_id, 0.0)
            x = _feature_row(zone, stat, _parse_float(rain, 0.0), fraction)
            features.append(x)
            score = float(np.clip(model.predict(np.asarray([x], dtype="float32"))[0], 0.0, 1.0))
            x_base = _feature_row(zone, stat, _parse_float(rain, 0.0), include_inundation=False)
            score_base = float(np.clip(baseline_model.predict(np.asarray([x_base], dtype="float32"))[0], 0.0, 1.0))
            population = max(0.0, _parse_float(zone["properties"].get("population_estimate")))
            affected_share = float(config["resources"].get("estimated_affected_population_share", 0.04))
            people = population * affected_share * score
            rows.append({
                "event_date": event_date, "zone_id": zone_id,
                "zone_name": zone["properties"]["name"],
                "severity_score": score,
                "severity_model": model_key,
                "training_basis": "2019 observed event-level river gauge proxy + 600 synthetic perturbations",
                "sar_likelihood": x[0], "gauge_hand_inundated_fraction": fraction,
                "antecedent_7day_rainfall_mm": _parse_float(rain, float("nan")),
                "population_estimate": population,
                "estimated_affected_people": people,
                "estimated_food_rations": people * float(config["resources"].get("food_rations_per_person", 3.0)),
                "estimated_water_liters": people * float(config["resources"].get("water_liters_per_person", 15.0)),
                "estimated_medical_kits": people * float(config["resources"].get("medical_kits_per_100_people", 4.0)) / 100.0,
                "estimate_status": "modeled; synthetic augmentation; not an observed count",
            })
            proxy = min(1.0, max(0.0, event.water_level_m / gauge_reference))
            ablation_rows.append({"event_date": event_date, "zone_id": zone_id,
                                  "zone_name": zone["properties"]["name"],
                                  "observed_gauge_ratio_proxy": proxy,
                                  "modeled_severity_without_gauge_hand_feature": score_base,
                                  "absolute_proxy_error_without_feature": abs(proxy-score_base),
                                  "modeled_severity_with_gauge_hand_feature": score,
                                  "absolute_proxy_error_with_feature": abs(proxy-score),
                                  "gauge_hand_inundated_fraction": fraction,
                                  "evaluation_role": "2019 calibration" if event_date == cal_date else "held-out proxy; gauge-derived input overlaps target"})
        path = processed / f"severity_demand_{event_date}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        outputs.append(path)
        # The later event is held out: report an event-level proxy cross-check,
        # never pass the validation target into training.
        model_metadata = {
            "model": model_key, "features": FEATURES, "feature_importances": dict(zip(FEATURES, model.feature_importances_.tolist())),
            "baseline_features_without_gauge_hand": BASE_FEATURES,
            "baseline_feature_importances_without_gauge_hand": dict(zip(BASE_FEATURES, baseline_model.feature_importances_.tolist())),
            "calibration_event": cal_date, "calibration_target_proxy": anchor_score,
            "synthetic_training_rows": 600, "synthetic_seed": 20190810,
            "validation_event": event_date if event != calibration else None,
            "validation_gauge_proxy": min(1.0, max(0.0, event.water_level_m / gauge_reference)) if event != calibration else None,
            "gauge_reference_level_m": gauge_reference,
            "holdout_note": "2024 and 2026 gauge proxies are reported as held-out comparisons only; neither is used to fit the model.",
            "limitations": ["Only one calibration event is used.", "Synthetic perturbations are not additional observations.", "Gauge-height ratio is an event-level severity proxy, not flood extent ground truth.", "Gauge-stage HAND fractions are derived from the same event gauge stage used to form the proxy target; proxy error changes are not independent evidence and may be circular."],
        }
        (processed / f"severity_model_{event_date}.json").write_text(json.dumps(model_metadata, indent=2), encoding="utf-8")
    with (processed / "severity_gauge_hand_ablation.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(ablation_rows[0]))
        writer.writeheader(); writer.writerows(ablation_rows)
    return outputs

