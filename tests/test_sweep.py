"""Unit and integration tests for stock sweep, thresholds bisection, and gauge readings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from resq.api import create_app
from resq.auth import reset_rate_limiter
from resq.config import REPO_ROOT


@pytest.fixture(autouse=True)
def _reset():
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_sweep_processed_files_exist():
    proc = REPO_ROOT / "data" / "processed"
    events = ["2019-08-10", "2024-07-31", "2026-08-03"]
    for event in events:
        json_path = proc / f"stock_sweep_{event}.json"
        csv_path = proc / f"stock_sweep_{event}.csv"
        assert json_path.exists(), f"Missing {json_path}"
        assert csv_path.exists(), f"Missing {csv_path}"

        raw = json.loads(json_path.read_text(encoding="utf-8"))
        assert raw["event_date"] == event
        assert len(raw["stock_levels"]) == 29
        assert raw["stock_levels"][0] == 10.0
        assert raw["stock_levels"][-1] == 150.0

        records = raw["records"]
        # 29 levels * 3 engines = 87 records
        assert len(records) == 87

        # Check LinUCB records have 5-seed bounds
        linucb_records = [r for r in records if r["engine"] == "LinUCB_contextual_bandit"]
        assert len(linucb_records) == 29
        for r in linucb_records:
            assert "aggregate_unmet_demand_min" in r
            assert "aggregate_unmet_demand_max" in r
            assert "minimum_zone_coverage_min" in r
            assert "minimum_zone_coverage_max" in r
            assert len(r["zone_coverage_vector"]) == 16


def test_sweep_thresholds_bisection():
    proc = REPO_ROOT / "data" / "processed"
    thresholds_file = proc / "stock_sweep_thresholds.json"
    assert thresholds_file.exists()
    data = json.loads(thresholds_file.read_text(encoding="utf-8"))
    for event in ["2019-08-10", "2024-07-31", "2026-08-03"]:
        assert event in data
        t = data[event]
        assert 40.0 <= t["smallest_stock_pct_for_40pct_floor_feasible"] <= 45.0
        assert 85.0 <= t["stock_pct_unmet_demand_below_10pct"] <= 95.0
        assert 0.0 <= t["stock_pct_linucb_collapse_below_1pct"] <= 15.0


def test_gauge_readings_csv():
    proc = REPO_ROOT / "data" / "processed"
    gauge_file = proc / "gauge_readings.csv"
    assert gauge_file.exists()
    content = gauge_file.read_text(encoding="utf-8")
    assert "event_date,timestamp,river_gauge,water_level_m,danger_level_m" in content
    assert "9.0" in content  # Danger level
    assert "11.6" in content  # 2019 peak
    assert "9.3" in content  # 2024 peak
    assert "8.5" in content  # 2026 peak


def test_api_sweep_endpoint(client):
    # Test valid grid snap
    resp = client.get("/sweep?event=2024-07-31&stock_pct=52.3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["event_date"] == "2024-07-31"
    assert data["requested_stock_pct"] == 52.3
    assert data["nearest_computed_stock_pct"] == 50.0
    assert len(data["records"]) == 3  # MILP, Proportional, LinUCB


def test_api_sweep_summary(client):
    resp = client.get("/sweep/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["grid"]["total_grid_points"] == 29
    assert len(data["linucb_specification"]["seeds"]) == 5
    assert "2024-07-31" in data["thresholds"]


def test_api_gauge_readings(client):
    resp = client.get("/data/gauge-readings")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 9
    assert any(r["event_date"] == "2019-08-10" and float(r["water_level_m"]) == 11.6 for r in rows)
