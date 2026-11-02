from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from resq.api import create_app
from resq.auth import create_access_token, _FAILED_LOGINS


@pytest.fixture
def auth_client(tmp_path: Path):
    _FAILED_LOGINS.clear()
    with TestClient(create_app(database_path=tmp_path / "auth-test.sqlite3")) as client:
        yield client


def test_health_public_endpoint(auth_client):
    res = auth_client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert "service" in res.json()


def test_login_success_both_roles(auth_client):
    # Viewer login
    res_viewer = auth_client.post("/auth/login", json={"username": "viewer", "password": "viewer2026"})
    assert res_viewer.status_code == 200
    data_v = res_viewer.json()
    assert data_v["role"] == "viewer"
    assert data_v["username"] == "viewer"
    assert "access_token" in data_v

    # Operator login
    res_operator = auth_client.post("/auth/login", json={"username": "operator", "password": "operator2026"})
    assert res_operator.status_code == 200
    data_o = res_operator.json()
    assert data_o["role"] == "operator"
    assert data_o["username"] == "operator"
    assert "access_token" in data_o


def test_login_failure_generic_message(auth_client):
    # Wrong password
    res1 = auth_client.post("/auth/login", json={"username": "viewer", "password": "wrongpassword"})
    assert res1.status_code == 401
    assert res1.json()["detail"]["code"] == "invalid_credentials"
    assert res1.json()["detail"]["message"] == "Invalid username or password."

    # Non-existent user
    res2 = auth_client.post("/auth/login", json={"username": "nonexistent", "password": "somepassword"})
    assert res2.status_code == 401
    assert res2.json()["detail"]["code"] == "invalid_credentials"
    # Same generic message - does not reveal if username or password was wrong
    assert res2.json()["detail"]["message"] == "Invalid username or password."


def test_missing_token_returns_401(auth_client):
    # No auth cookie or bearer header
    res = auth_client.post("/simulate", json={"event": "2019-08-10", "engine": "MILP"})
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "unauthorized"

    res_closures = auth_client.post("/closures", json={"run_id": "dummy", "closure_id": "dummy"})
    assert res_closures.status_code == 401
    assert res_closures.json()["detail"]["code"] == "unauthorized"


def test_viewer_hitting_operator_endpoint_returns_403(auth_client):
    # Log in as viewer
    auth_client.post("/auth/login", json={"username": "viewer", "password": "viewer2026"})
    
    # Viewer trying operator-only closures endpoint
    res_closure = auth_client.post("/closures", json={"run_id": "dummy", "closure_id": "dummy"})
    assert res_closure.status_code == 403
    assert res_closure.json()["detail"]["code"] == "forbidden"
    assert "Operator role required" in res_closure.json()["detail"]["message"]

    # Viewer trying operator-only admin override endpoint
    res_override = auth_client.post("/admin/override", json={
        "run_id": "dummy",
        "zone_id": "bantwal_grid_01",
        "resource": "food_rations",
        "boost_amount": 50,
        "reason": "Emergency shelter supplement"
    })
    assert res_override.status_code == 403
    assert res_override.json()["detail"]["code"] == "forbidden"


def test_operator_allowed_on_admin_override(auth_client):
    auth_client.post("/auth/login", json={"username": "operator", "password": "operator2026"})
    res = auth_client.post("/admin/override", json={
        "run_id": "dummy",
        "zone_id": "bantwal_grid_01",
        "resource": "food_rations",
        "boost_amount": 100,
        "reason": "Manual operator relief injection"
    })
    assert res.status_code == 200
    assert res.json()["status"] == "applied"
    assert res.json()["operator"] == "operator"


def test_token_expiry_returns_401(auth_client):
    # Create a token that expired 10 minutes ago
    expired_token = create_access_token("viewer", "viewer", expiry_minutes=-10)
    res = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "token_expired"


def test_rate_limiting_returns_429(auth_client):
    _FAILED_LOGINS.clear()
    # 5 failed attempts allowed
    for _ in range(5):
        res = auth_client.post("/auth/login", json={"username": "viewer", "password": "badpassword"})
        assert res.status_code == 401

    # 6th attempt triggers 429
    res_rate_limited = auth_client.post("/auth/login", json={"username": "viewer", "password": "badpassword"})
    assert res_rate_limited.status_code == 429
    assert res_rate_limited.json()["detail"]["code"] == "rate_limited"
    _FAILED_LOGINS.clear()
