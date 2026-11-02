"""Unit and integration tests for Facility Inventory, Scenarios, and Admin Override."""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from resq.api import create_app
from resq.auth import create_access_token, reset_rate_limiter


@pytest.fixture(autouse=True)
def _reset():
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def operator_token():
    return create_access_token("operator", "operator")


@pytest.fixture
def viewer_token():
    return create_access_token("viewer", "viewer")


def test_facilities_list(client):
    resp = client.get("/facilities")
    assert resp.status_code == 200
    facilities = resp.json()
    assert len(facilities) >= 17
    assert any(f["id"] == "svs_kannada_medium_school_bantwal" for f in facilities)
    assert any(f["geometry_verified"] is False for f in facilities)


def test_stock_summary(client):
    resp = client.get("/stock/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "pooled_inventory" in data
    assert "unroutable_pooled_stock" in data
    assert "status_chip" in data


def test_facility_stock_update_role_guard(client, viewer_token):
    # Viewer should be blocked from updating stock (403)
    resp = client.put(
        "/facilities/svs_kannada_medium_school_bantwal/stock",
        json={"stock": [{"resource": "food_rations", "quantity": 500, "unit": "rations"}]},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


def test_facility_stock_update_validation(client, operator_token):
    # Negative quantity rejected
    resp = client.put(
        "/facilities/svs_kannada_medium_school_bantwal/stock",
        json={"stock": [{"resource": "food_rations", "quantity": -50, "unit": "rations"}]},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert resp.status_code in (422, 400)

    # Exceeding upper bound limit rejected
    resp = client.put(
        "/facilities/svs_kannada_medium_school_bantwal/stock",
        json={"stock": [{"resource": "food_rations", "quantity": 999_999_999, "unit": "rations"}]},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert resp.status_code == 422

    # Valid update
    resp = client.put(
        "/facilities/svs_kannada_medium_school_bantwal/stock",
        json={"stock": [{"resource": "food_rations", "quantity": 2500, "unit": "rations", "note": "Verified field count"}]},
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


def test_simulate_entered_stock_mode(client, viewer_token):
    resp = client.post(
        "/simulate",
        json={"event": "2024-07-31", "engine": "MILP", "stock_mode": "entered"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["stock_mode"] == "entered"
    assert data["status_chip"] == "ENTERED, UNVERIFIED"
    assert "unroutable_facilities" in data


def test_scenarios_list_and_run(client, viewer_token):
    # List scenarios
    resp = client.get("/scenarios")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert len(scenarios) >= 7
    assert any(s["id"] == "scarcity_ladder" for s in scenarios)

    # Run scarcity ladder
    resp = client.post(
        "/scenarios/run",
        json={"scenario_id": "scarcity_ladder", "seed": 42},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["scenario_id"] == "scarcity_ladder"
    assert "ladder_results" in res
    assert len(res["ladder_results"]) == 6


def test_admin_override_donor_floor_and_inventory(client, operator_token, viewer_token):
    # First create a run
    sim_resp = client.post(
        "/simulate",
        json={"event": "2024-07-31", "engine": "MILP", "stock_mode": "assumed_configured"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert sim_resp.status_code == 201
    run_id = sim_resp.json()["run_id"]

    # 1. Test violation of donor fairness floor (trying to reduce zone allocation below 40% floor)
    override_resp = client.post(
        "/admin/override",
        json={
            "run_id": run_id,
            "overrides": [{"zone_id": "bantwal_grid_01", "resource": "food_rations", "new_allocated": 10}],
            "donor_floor_pct": 40.0,
        },
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert override_resp.status_code == 422
    assert "violates the donor fairness floor" in override_resp.json()["detail"]["message"]

    # 2. Test violation of inventory cap
    override_resp2 = client.post(
        "/admin/override",
        json={
            "run_id": run_id,
            "overrides": [{"zone_id": "bantwal_grid_01", "resource": "food_rations", "new_allocated": 999_999}],
            "donor_floor_pct": 40.0,
        },
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert override_resp2.status_code == 422
    assert "exceeds available district inventory" in override_resp2.json()["detail"]["message"]

    # 3. Test successful valid override
    override_resp3 = client.post(
        "/admin/override",
        json={
            "run_id": run_id,
            "overrides": [{"zone_id": "bantwal_grid_01", "resource": "food_rations", "new_allocated": 700}],
            "donor_floor_pct": 40.0,
            "reason": "Relief camp priority adjustment",
        },
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert override_resp3.status_code == 200
    out = override_resp3.json()
    assert out["label"] == "manual override, not an optimization result"
    assert "coverage_changes" in out
