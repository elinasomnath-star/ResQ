from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import resq.api as api
from resq.api import create_app
from resq.auth import reset_rate_limiter
from resq.config import configured_path, load_config


@pytest.fixture
def client(tmp_path: Path):
    reset_rate_limiter()
    with TestClient(create_app(database_path=tmp_path / "api-test.sqlite3")) as test_client:
        login_res = test_client.post("/auth/login", json={"username": "operator", "password": "operator2026"})
        assert login_res.status_code == 200
        test_client.headers["Authorization"] = f"Bearer {login_res.json()['access_token']}"
        yield test_client


def test_get_events_and_zones_and_unknown_event(client):
    events = client.get("/events")
    assert events.status_code == 200
    assert len(events.json()["events"]) == 3
    zones = client.get("/zones", params={"event": "2019-08-10"})
    assert zones.status_code == 200
    assert len(zones.json()["zones"]) == 16
    assert {z["population_status"] for z in zones.json()["zones"]} == {"modeled_estimate"}
    assert {z["population_year"] for z in zones.json()["zones"]} == {2025}
    assert {z["population_resolution"] for z in zones.json()["zones"]} == {"1km"}
    assert client.get("/zones", params={"event": "1900-01-01"}).status_code == 404


def test_events_reports_missing_input_as_service_unavailable(client, monkeypatch):
    def missing_events():
        raise FileNotFoundError("events.csv missing")
    monkeypatch.setattr(api, "load_events", missing_events)
    response = client.get("/events")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "event_data_unavailable"


def test_api_starts_without_cached_graph_and_reports_routing_unavailable(tmp_path, monkeypatch):
    def missing_graph(_path):
        raise FileNotFoundError("road_graph.graphml missing")

    monkeypatch.setattr(api, "_load_graph", missing_graph)
    app = create_app(database_path=tmp_path / "no-graph.sqlite3")
    with TestClient(app) as test_client:
        login_res = test_client.post("/auth/login", json={"username": "operator", "password": "operator2026"})
        assert login_res.status_code == 200
        test_client.headers["Authorization"] = f"Bearer {login_res.json()['access_token']}"
        assert test_client.get("/events").status_code == 200
        assert test_client.get("/zones", params={"event": "2019-08-10"}).status_code == 200
        simulated = test_client.post("/simulate", json={
            "event": "2019-08-10", "engine": "MILP", "stock_mode": "configured"
        })
        assert simulated.status_code == 201, simulated.text
        closures = json.loads((configured_path(load_config()["data"]["processed_dir"])
                               / "closures_2019-08-10.geojson").read_text(encoding="utf-8"))
        verified = next(f for f in closures["features"]
                        if f.get("properties", {}).get("status") == "verified")
        response = test_client.post("/closures", json={
            "run_id": simulated.json()["run_id"],
            "closure_id": verified["properties"]["closure_id"],
        })
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "road_graph_unavailable"


def test_simulate_closure_get_allocation_and_escalations(tmp_path, client):
    simulated = client.post("/simulate", json={"event": "2019-08-10", "engine": "MILP", "stock_mode": "configured"})
    assert simulated.status_code == 201, simulated.text
    run_id = simulated.json()["run_id"]
    assert simulated.json()["summary"]["engine"] == "MILP"
    assert len(client.get(f"/allocation/{run_id}").json()["allocations"]) == 48
    assert client.get(f"/escalations/{run_id}").json()["escalations"] == []

    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    previous_dynamic_summary = (processed / "module8_dynamic_summary_2019-08-10.json").read_bytes()
    previous_allocation_comparison = (processed / "allocation_comparison_2024-07-31.csv").read_bytes()
    previous_allocation_matrix = (processed / "allocation_matrix_2024-07-31.csv").read_bytes()
    closure_collection = json.loads((processed / "closures_2019-08-10.geojson").read_text(encoding="utf-8"))
    verified = next(f for f in closure_collection["features"]
                    if f.get("properties", {}).get("status") == "verified")
    closure_id = verified["properties"]["closure_id"]
    applied = client.post("/closures", json={"run_id": run_id, "closure_id": closure_id})
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied_closure_id"] == closure_id
    assert len(applied.json()["steps"]) == 8
    assert "trigger_count" in applied.json()["module9"]
    assert applied.json()["module7_routes"]["zone_count"] == 16
    assert (processed / "module8_dynamic_summary_2019-08-10.json").read_bytes() == previous_dynamic_summary
    assert client.get(f"/allocation/{run_id}").json()["status"] == "closure_applied"
    assert client.get(f"/escalations/{run_id}").status_code == 200
    routes = client.get(f"/routes/{run_id}")
    assert routes.status_code == 200
    assert len(routes.json()["routes"]) == 16
    assert routes.json()["inventory_basis"].startswith("assumed_inventory:")
    assert {r["road_status"] for r in routes.json()["routes"]} <= {"ROUTED", "UNREACHABLE_BY_ROAD"}

    assumed = client.post("/simulate", json={"event": "2024-07-31", "engine": "proportional", "stock_mode": "simulated"})
    assert assumed.status_code == 201, assumed.text
    assert assumed.json()["inventory_basis"].startswith("assumed_inventory:")
    assert (processed / "allocation_comparison_2024-07-31.csv").read_bytes() == previous_allocation_comparison
    assert (processed / "allocation_matrix_2024-07-31.csv").read_bytes() == previous_allocation_matrix
    allocation = client.get(f"/allocation/{assumed.json()['run_id']}").json()
    assert allocation["inventory_basis"].startswith("assumed_inventory:")
    assert allocation["stock_mode"] == "simulated"


def test_simulate_validation_errors(client):
    assert client.post("/simulate", json={"event": "1900-01-01", "engine": "MILP"}).status_code == 404
    assert client.post("/simulate", json={"event": "2019-08-10", "engine": "bogus"}).status_code == 422
    assert client.post("/simulate", json={"event": "2019-08-10", "engine": "MILP", "stock_mode": "real"}).status_code == 422


def test_closure_and_result_not_found_errors(tmp_path, client):
    assert client.post("/closures", json={"run_id": "missing", "closure_id": "none"}).status_code == 404
    assert client.get("/allocation/missing").status_code == 404
    assert client.get("/escalations/missing").status_code == 404
    assert client.get("/routes/missing").status_code == 404

    processed = configured_path(load_config()["data"]["processed_dir"])
    closures = json.loads((processed / "closures_2019-08-10.geojson").read_text(encoding="utf-8"))
    unresolved = next(f for f in closures["features"] if f.get("properties", {}).get("status") != "verified")
    # Build a persisted run through the real service before checking closure validation.
    result = client.post("/simulate", json={"event": "2019-08-10", "engine": "proportional"})
    assert result.status_code == 201, result.text
    invalid = client.post("/closures", json={"run_id": result.json()["run_id"],
                                              "closure_id": unresolved["properties"]["closure_id"]})
    assert invalid.status_code == 422

