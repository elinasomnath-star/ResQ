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
    assert "totals" in data
    assert "unroutable_pooled_stock" in data
    assert "status_chip" in data


def test_field_log_csv_import_becomes_the_entered_allocation_pool(tmp_path):
    app = create_app(database_path=tmp_path / "field-logs.sqlite3")
    csv_text = """facility_id,resource,quantity,unit,note
svs_kannada_medium_school_bantwal,food_rations,20000,rations,demo
svs_kannada_medium_school_bantwal,water_liters,100000,liters,demo
svs_kannada_medium_school_bantwal,medical_kits,260,kits,demo
mini_town_hall_mangaluru,food_rations,16000,rations,demo
mini_town_hall_mangaluru,water_liters,80000,liters,demo
mini_town_hall_mangaluru,medical_kits,210,kits,demo
panemangaluru_sharada_relief_centre,food_rations,14000,rations,demo
panemangaluru_sharada_relief_centre,water_liters,70000,liters,demo
panemangaluru_sharada_relief_centre,medical_kits,190,kits,demo
"""

    with TestClient(app) as test_client:
        login = test_client.post("/auth/login", json={"username": "operator", "password": "operator2026"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        imported = test_client.post("/stock/import", json={"csv_text": csv_text}, headers=headers)
        assert imported.status_code == 200, imported.text
        assert imported.json()["facilities_updated"] == 3
        assert imported.json()["stock_items_updated"] == 9

        summary = test_client.get("/stock/summary").json()
        assert summary["overall_mode"] == "entered"
        assert summary["pooled_inventory"] == {
            "food_rations": 50000,
            "water_liters": 250000,
            "medical_kits": 660,
        }
        assert summary["totals"]["food_rations"]["quantity"] == 25000

        run = test_client.post("/simulate", json={
            "event": "2024-07-31", "engine": "MILP", "stock_mode": "entered",
        }, headers=headers)
        assert run.status_code == 201, run.text
        assert run.json()["available_inventory"] == summary["pooled_inventory"]
        allocation = test_client.get(f"/allocation/{run.json()['run_id']}", headers=headers)
        assert allocation.status_code == 200, allocation.text
        zone_coverage: dict[str, list[float]] = {}
        for row in allocation.json()["allocations"]:
            need = row["estimated_need"]
            coverage = 100 * row["allocated"] / need if need else 100.0
            zone_coverage.setdefault(row["zone_id"], []).append(coverage)
        minimum_by_zone = [min(values) for values in zone_coverage.values()]
        assert any(60 <= coverage <= 90 for coverage in minimum_by_zone)
        assert any(coverage == 100 for coverage in minimum_by_zone)


def test_field_log_csv_import_rejects_bad_file_without_partial_updates(tmp_path):
    app = create_app(database_path=tmp_path / "invalid-field-logs.sqlite3")
    csv_text = """facility_id,resource,quantity,unit,note
svs_kannada_medium_school_bantwal,food_rations,100,rations,demo
unknown_site,water_liters,200,liters,demo
"""

    with TestClient(app) as test_client:
        login = test_client.post("/auth/login", json={"username": "operator", "password": "operator2026"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        imported = test_client.post("/stock/import", json={"csv_text": csv_text}, headers=headers)
        assert imported.status_code == 422
        summary = test_client.get("/stock/summary").json()
        assert summary["overall_mode"] == "assumed"


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
