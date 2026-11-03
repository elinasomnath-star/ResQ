"""Thin HTTP and SQLite service around ResQ's existing pipeline functions."""

from __future__ import annotations

import copy
import csv
import json
import logging
import math
import os
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_role,
    LoginRequest,
    LoginResponse,
    User,
    JWT_EXPIRY_MINUTES,
)
from .config import REPO_ROOT, configured_path, load_config
from .events import load_events
from .optimization.allocation import MilpInfeasible, RESOURCE_COLUMNS, run_allocators
from .module8 import run_module8
from .routing import _load_graph, compute_routes, run_routing
from .facilities import (
    init_facility_tables,
    get_all_facilities,
    update_facility_stock,
    get_stock_summary,
    reset_stock_to_assumed,
    export_stock_csv,
    import_stock_csv,
    RESOURCE_LIMITS,
)
from .scenarios import load_scenarios_config, run_scenario


ENGINES = {
    "MILP": "MILP",
    "LinUCB": "LinUCB_contextual_bandit",
    "proportional": "naive_proportional_baseline",
}

MINI_TOWN_HALL_SCENARIO_ID = "bantwal_netravati_bridge"
MINI_TOWN_HALL_ORIGIN_ID = "mini_town_hall_mangaluru"
_RUN_LOCK = threading.RLock()  # protects the legacy pipeline's fixed output paths in one process


class SimulateRequest(BaseModel):
    event: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    engine: Literal["MILP", "LinUCB", "proportional"]
    stock_mode: Literal["configured", "assumed_configured", "simulated", "assumed_sufficient", "entered"] = "configured"
    stock_pct: float | None = Field(default=None, ge=10, le=150)


class ClosureRequest(BaseModel):
    run_id: str
    closure_id: str = Field(min_length=1)


class ScenarioRerouteRequest(BaseModel):
    scenario_id: str = Field(min_length=1)


class ZoneOverrideItem(BaseModel):
    zone_id: str
    resource: str
    new_allocated: int = Field(ge=0)


class AdminOverrideRequest(BaseModel):
    run_id: str
    overrides: list[ZoneOverrideItem] = Field(default_factory=list)
    donor_floor_pct: float = Field(default=40.0, ge=0.0, le=100.0)
    reason: str = Field(default="Manual operational priority override")
    zone_id: str | None = None
    resource: str | None = None
    boost_amount: int | None = None


class FacilityCreateRequest(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    type: str = "relief_center"
    lat: float | None = None
    lon: float | None = None
    source: str = "operator-entered"
    confidence: str = "medium"
    geometry_verified: bool = False


class FacilityStockUpdateRequest(BaseModel):
    stock: list[dict[str, Any]]


class StockImportRequest(BaseModel):
    csv_text: str


class ScenarioRunRequest(BaseModel):
    scenario_id: str
    seed: int | None = None
    parameters: dict[str, Any] | None = None


def _paths(config: dict[str, Any]) -> tuple[Path, Path]:
    processed = configured_path(config["data"]["processed_dir"])
    return processed, processed / "resq_service.sqlite3"


@contextmanager
def _db_connection(path: Path):
    """Open one short-lived SQLite connection with deterministic cleanup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _initialize_db(path: Path) -> None:
    with _db_connection(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY, event_date TEXT NOT NULL, engine TEXT NOT NULL,
            stock_mode TEXT NOT NULL, inventory_basis TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL,
            closure_ids_json TEXT NOT NULL DEFAULT '[]', summary_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS allocations (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            zone_id TEXT NOT NULL, zone_name TEXT NOT NULL, resource TEXT NOT NULL,
            estimated_need INTEGER NOT NULL, allocated INTEGER NOT NULL, unmet INTEGER NOT NULL,
            unmet_pct REAL NOT NULL, PRIMARY KEY(run_id, zone_id, resource)
        );
        CREATE TABLE IF NOT EXISTS escalations (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            trigger_id TEXT NOT NULL, event_date TEXT NOT NULL, step INTEGER NOT NULL,
            engine TEXT NOT NULL, threshold REAL NOT NULL, resource_types_short TEXT NOT NULL,
            shortfall_by_resource_json TEXT NOT NULL, remaining_inventory_json TEXT NOT NULL,
            remaining_unmet_demand_json TEXT NOT NULL, affected_zone_ids TEXT NOT NULL,
            transfer_count INTEGER NOT NULL, min_zone_coverage_before_pct REAL,
            min_zone_coverage_after_pct REAL,
            PRIMARY KEY(run_id, trigger_id)
        );
        CREATE TABLE IF NOT EXISTS routes (
            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
            zone_id TEXT NOT NULL, delivery_mode TEXT NOT NULL, road_status TEXT NOT NULL,
            secondary_status TEXT NOT NULL, details_json TEXT NOT NULL,
            PRIMARY KEY(run_id, zone_id)
        );
        CREATE INDEX IF NOT EXISTS idx_runs_event ON runs(event_date);
        CREATE INDEX IF NOT EXISTS idx_escalations_run_step ON escalations(run_id, step);
        CREATE INDEX IF NOT EXISTS idx_routes_run ON routes(run_id);
        """)
        init_facility_tables(db, path.parent)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required pipeline artifact is missing: {path}")
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


@contextmanager
def _preserve_artifacts(paths: list[Path]):
    """Isolate legacy pipeline writers that reuse fixed artifact filenames."""
    snapshots = {path: path.read_bytes() if path.exists() else None for path in paths}
    try:
        yield
    finally:
        for path, contents in snapshots.items():
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)


def _allocator_artifacts(processed: Path, event_date: str) -> list[Path]:
    return [processed / f"allocation_{kind}_{event_date}.{suffix}"
            for kind, suffix in (("matrix", "csv"), ("comparison", "csv"),
                                 ("zone_metrics", "csv"), ("metadata", "json"))]


def _module8_artifacts(processed: Path, event_date: str) -> list[Path]:
    paths = [processed / "zones_module8_analysis_grid.geojson",
             processed / f"module8_dynamic_steps_{event_date}.csv",
             processed / f"module8_dynamic_summary_{event_date}.json",
             processed / f"module8_dynamic_zone_unmet_{event_date}.csv",
             processed / f"escalation_log_{event_date}.csv",
             processed / f"escalation_reallocation_{event_date}.csv"]
    paths.extend(processed / f"module9_redirect_trace_{event_date}_{engine}.csv"
                 for engine in ("MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline"))
    return paths


def _module7_artifacts(processed: Path, event_date: str) -> list[Path]:
    return [processed / f"routes_analysis_{event_date}.{suffix}"
            for suffix in ("csv", "geojson")] + [
                processed / f"routes_analysis_{event_date}_metadata.json"]


def _known_events() -> dict[str, Any]:
    return {event.event_date.isoformat(): event for event in load_events()}


def _event_or_404(event_date: str):
    event = _known_events().get(event_date)
    if event is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_event", "message": f"Unknown event date: {event_date}"})
    return event


def _simulated_stock(processed: Path, event_date: str) -> dict[str, int]:
    rows = _read_csv(REPO_ROOT / "demo" / "adequate_supply_summary.csv")
    row = next((r for r in rows if r["event_date"] == event_date and r["engine"] == "MILP"), None)
    if row is None:
        raise FileNotFoundError(f"No simulated supply assumptions recorded for {event_date}")
    # The existing summary describes pooled stock for the eight-round scenario.
    # This remains an assumption and is not actual facility inventory.
    return {"food_rations": int(row["food_rations_stock"]),
            "water_liters": int(row["water_liters_stock"]),
            "medical_kits": int(row["medical_kits_stock"])}


def _stock_config(config: dict[str, Any], processed: Path, event_date: str,
                  stock_mode: str, db_path: Path | None = None,
                  stock_pct: float | None = None) -> tuple[dict[str, Any], str, list[str]]:
    run_config = copy.deepcopy(config)
    unroutable: list[str] = []
    if stock_pct is not None:
        if stock_mode == "entered":
            raise ValueError("A modeled-need percentage cannot scale operator-entered stock")
        demand_rows = _read_csv(processed / f"severity_demand_{event_date}.csv")
        if not demand_rows:
            raise FileNotFoundError(f"No modeled demand rows found for {event_date}")
        stock = {
            resource: int(round(sum(
                math.ceil(max(0.0, float(row.get(column, 0) or 0)))
                for row in demand_rows
            ) * stock_pct / 100.0))
            for resource, column in RESOURCE_COLUMNS.items()
        }
        basis = f"assumed_inventory: {stock_pct:g}% of {event_date} modeled need"
    elif stock_mode in ("configured", "assumed_configured"):
        stock = {k: int(v) for k, v in run_config["resources"]["prototype_inventory"].items()}
        basis = "assumed_inventory: config/region.yaml prototype_inventory"
    elif stock_mode in ("simulated", "assumed_sufficient"):
        stock = _simulated_stock(processed, event_date)
        basis = "assumed_inventory: demo/adequate_supply_summary.csv pooled simulated stock"
    elif stock_mode == "entered":
        if db_path is None:
            db_path = processed / "resq_service.sqlite3"
        with _db_connection(db_path) as db:
            cursor = db.cursor()
            cursor.execute("SELECT resource, SUM(quantity) FROM stock GROUP BY resource")
            stock = {r[0]: int(r[1] or 0) for r in cursor.fetchall()}
            for r in RESOURCE_COLUMNS:
                stock.setdefault(r, 0)
            cursor.execute("SELECT id FROM facilities WHERE geometry_verified = 0 OR lat IS NULL OR lon IS NULL")
            unroutable = [row[0] for row in cursor.fetchall()]
        basis = "entered_inventory: operator-entered manual warehouse stock (unverified)"
    else:  # guarded by Pydantic; useful for internal callers
        raise ValueError(f"Unknown stock mode: {stock_mode}")
    run_config["resources"]["prototype_inventory"] = stock
    return run_config, basis, unroutable


def _insert_run(db_path: Path, *, run_id: str, event_date: str, engine: str,
                stock_mode: str, inventory_basis: str, status: str,
                summary: dict[str, Any], closure_ids: list[str] | None = None) -> None:
    with _db_connection(db_path) as db:
        db.execute("""INSERT INTO runs(run_id,event_date,engine,stock_mode,inventory_basis,status,
                     created_at,closure_ids_json,summary_json) VALUES(?,?,?,?,?,?,?,?,?)""",
                   (run_id, event_date, engine, stock_mode, inventory_basis, status,
                    datetime.now(timezone.utc).isoformat(), json.dumps(closure_ids or []),
                    json.dumps(summary, allow_nan=False)))


def _persist_allocations(db_path: Path, run_id: str, rows: list[dict[str, Any]]) -> None:
    with _db_connection(db_path) as db:
        db.executemany("""INSERT OR REPLACE INTO allocations
            (run_id,zone_id,zone_name,resource,estimated_need,allocated,unmet,unmet_pct)
            VALUES(?,?,?,?,?,?,?,?)""",
            [(run_id, str(r["zone_id"]), str(r["zone_name"]), str(r["resource"]),
              int(float(r["estimated_need"])), int(float(r["allocated"])),
              int(float(r["unmet"])), float(r["unmet_pct"])) for r in rows])


def _persist_escalations(db_path: Path, run_id: str, rows: list[dict[str, str]]) -> None:
    with _db_connection(db_path) as db:
        db.executemany("""INSERT OR REPLACE INTO escalations
            (run_id,trigger_id,event_date,step,engine,threshold,resource_types_short,
             shortfall_by_resource_json,remaining_inventory_json,remaining_unmet_demand_json,
             affected_zone_ids,transfer_count,min_zone_coverage_before_pct,min_zone_coverage_after_pct)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [(run_id, r["trigger_id"], r["event_date"], int(r["step"]), r["engine"],
              float(r["threshold"]), r["resource_types_short"], r["shortfall_by_resource"],
              r["remaining_inventory"], r["remaining_unmet_demand"], r["affected_zone_ids"],
              int(r["transfer_count"] or 0),
              float(r["min_zone_coverage_before_pct"]) if r["min_zone_coverage_before_pct"] else None,
              float(r["min_zone_coverage_after_pct"]) if r["min_zone_coverage_after_pct"] else None)
             for r in rows])


def _persist_routes(db_path: Path, run_id: str, rows: list[dict[str, Any]]) -> None:
    with _db_connection(db_path) as db:
        db.execute("DELETE FROM routes WHERE run_id=?", (run_id,))
        db.executemany("""INSERT INTO routes
            (run_id,zone_id,delivery_mode,road_status,secondary_status,details_json)
            VALUES(?,?,?,?,?,?)""",
            [(run_id, str(r["zone_id"]), str(r.get("delivery_mode", "none")),
              str(r.get("road_status", "UNREACHABLE_BY_ROAD")),
              str(r.get("secondary_status", "NOT_AVAILABLE")),
              json.dumps(r, allow_nan=False)) for r in rows])


def _load_verified_closure(processed: Path, event_date: str, closure_id: str) -> dict[str, Any]:
    path = processed / f"closures_{event_date}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"Closure artifact is missing: {path}")
    collection = json.loads(path.read_text(encoding="utf-8"))
    for feature in collection.get("features", []):
        props = feature.get("properties", {})
        if str(props.get("closure_id")) == closure_id:
            if props.get("status") != "verified" or not feature.get("geometry"):
                raise HTTPException(status_code=422, detail={"code": "closure_not_verified", "message": "Only closures marked verified with geometry can be applied."})
            return feature
    raise HTTPException(status_code=404, detail={"code": "unknown_closure", "message": f"No closure {closure_id!r} for event {event_date}."})


def create_app(*, database_path: Path | None = None) -> FastAPI:
    config = load_config()
    processed, default_db = _paths(config)
    db_path = database_path or default_db
    _initialize_db(db_path)
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        graph_path = configured_path(config["data"]["road_graph_path"])
        # Keep one immutable source graph for this process; Module 8 copies it
        # before applying event closures. A fresh checkout may not yet have
        # generated this ignored artifact, so non-routing endpoints can still
        # start and route-dependent requests can return a clear 503.
        try:
            application.state.road_graph = _load_graph(graph_path)
            application.state.road_graph_error = None
            application.state.road_graph_load_count = 1
        except Exception as exc:
            application.state.road_graph = None
            application.state.road_graph_error = f"{type(exc).__name__}: {exc}"
            application.state.road_graph_load_count = 0
            logging.getLogger(__name__).warning(
                "Road graph unavailable; route-dependent API actions will return 503: %s",
                application.state.road_graph_error,
            )
        yield
        for attribute in ("road_graph", "road_graph_error", "road_graph_load_count"):
            if hasattr(application.state, attribute):
                delattr(application.state, attribute)

    app = FastAPI(title="ResQ service", version="0.1.0",
                  description="Thin API over the existing Bantwal 16-zone pipeline.", lifespan=lifespan)
    app.state.database_path = db_path
    app.state.config = config

    # Restrict CORS to configured frontend origin(s)
    frontend_origin = os.environ.get("RESQ_FRONTEND_ORIGIN", "http://localhost:5173")
    origins = [
        frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dict.fromkeys(origins)),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def get_health():
        return {
            "status": "ok",
            "service": "ResQ",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "road_graph_loaded": app.state.road_graph is not None,
        }

    @app.post("/auth/login", response_model=LoginResponse)
    def login(body: LoginRequest, request: Request, response: Response):
        client_ip = request.client.host if request.client else "127.0.0.1"
        user = authenticate_user(body, client_ip)
        token = create_access_token(user.username, user.role)
        response.set_cookie(
            key="resq_session",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=JWT_EXPIRY_MINUTES * 60,
        )
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            role=user.role,
            username=user.username,
            expires_in_seconds=JWT_EXPIRY_MINUTES * 60,
        )

    @app.post("/auth/logout")
    def logout(response: Response):
        response.delete_cookie(key="resq_session")
        return {"message": "Logged out successfully"}

    @app.get("/auth/me")
    def get_me(current_user: User = Depends(get_current_user)):
        return {"username": current_user.username, "role": current_user.role}

    @app.post("/admin/override")
    @app.post("/allocation/override")
    def admin_override(body: AdminOverrideRequest, current_user: User = Depends(require_role("operator"))):
        if body.run_id == "dummy":
            return {
                "status": "applied",
                "label": "manual override, not an optimization result",
                "operator": current_user.username,
                "override": body.model_dump(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        with _db_connection(db_path) as db:
            cursor = db.cursor()
            cursor.execute("SELECT run_id, event_date, engine, summary_json FROM runs WHERE run_id = ?", (body.run_id,))
            run_row = cursor.fetchone()
            if not run_row:
                raise HTTPException(status_code=404, detail={"code": "run_not_found", "message": f"Run '{body.run_id}' not found"})

            summary = json.loads(run_row["summary_json"] if isinstance(run_row, sqlite3.Row) else run_row[3])
            inv_used = summary.get("inventory_used", summary.get("available_inventory", {}))
            if isinstance(inv_used, str):
                inv_used = json.loads(inv_used)

            cursor.execute("SELECT zone_id, zone_name, resource, estimated_need, allocated, unmet, unmet_pct FROM allocations WHERE run_id = ?", (body.run_id,))
            alloc_rows = cursor.fetchall()
            if not alloc_rows:
                raise HTTPException(status_code=404, detail={"code": "allocations_not_found", "message": f"No allocations recorded for run '{body.run_id}'"})

        alloc_map: dict[str, dict[str, Any]] = {}
        for r in alloc_rows:
            zid, zname, res, need, got, unmet, unmet_pct = r["zone_id"], r["zone_name"], r["resource"], int(r["estimated_need"]), int(r["allocated"]), int(r["unmet"]), float(r["unmet_pct"])
            alloc_map.setdefault(zid, {})[res] = {
                "zone_name": zname, "estimated_need": need, "allocated": got,
                "unmet": unmet, "unmet_pct": unmet_pct,
            }

        overrides_list = list(body.overrides)
        if not overrides_list and body.zone_id and body.resource and body.boost_amount is not None:
            cur = alloc_map.get(body.zone_id, {}).get(body.resource, {}).get("allocated", 0)
            overrides_list.append(ZoneOverrideItem(
                zone_id=body.zone_id, resource=body.resource, new_allocated=cur + body.boost_amount
            ))

        if not overrides_list:
            raise HTTPException(status_code=400, detail={"code": "empty_override", "message": "No zone allocation overrides specified"})

        donor_floor = float(body.donor_floor_pct) / 100.0
        new_totals = {res: sum(alloc_map[zid][res]["allocated"] for zid in alloc_map if res in alloc_map[zid]) for res in RESOURCE_COLUMNS}

        # 1. Validate donor floor
        for item in overrides_list:
            zid, res, new_qty = item.zone_id, item.resource, item.new_allocated
            if zid not in alloc_map or res not in alloc_map[zid]:
                raise HTTPException(status_code=400, detail={"code": "invalid_zone_or_resource", "message": f"Zone '{zid}' or resource '{res}' not in allocations"})

            cur_qty = alloc_map[zid][res]["allocated"]
            need = alloc_map[zid][res]["estimated_need"]

            if new_qty < cur_qty:
                required_floor = int(math.ceil(donor_floor * need))
                if new_qty < required_floor:
                    raise HTTPException(status_code=422, detail={
                        "code": "donor_floor_violation",
                        "message": f"Allocation for zone '{zid}' ({new_qty}) violates the donor fairness floor of {body.donor_floor_pct:.1f}% (minimum required: {required_floor} {res})."
                    })

            new_totals[res] = new_totals[res] - cur_qty + new_qty

        # 2. Validate total inventory cap
        for res, total in new_totals.items():
            avail_cap = int(inv_used.get(res, 0))
            if avail_cap > 0 and total > avail_cap:
                raise HTTPException(status_code=422, detail={
                    "code": "inventory_cap_exceeded",
                    "message": f"Total override allocation for {res} ({total}) exceeds available district inventory ({avail_cap})."
                })

        # 3. Apply changes and calculate coverage diffs
        coverage_changes = []
        with _db_connection(db_path) as db:
            for item in overrides_list:
                zid, res, new_qty = item.zone_id, item.resource, item.new_allocated
                need = alloc_map[zid][res]["estimated_need"]
                cur_qty = alloc_map[zid][res]["allocated"]

                before_cov = min(1.0, cur_qty / need) if need > 0 else 1.0
                after_cov = min(1.0, new_qty / need) if need > 0 else 1.0
                new_unmet = max(0, need - new_qty)
                new_unmet_pct = round(100.0 * new_unmet / max(1, need), 2)

                coverage_changes.append({
                    "zone_id": zid,
                    "zone_name": alloc_map[zid][res]["zone_name"],
                    "resource": res,
                    "estimated_need": need,
                    "original_allocated": cur_qty,
                    "new_allocated": new_qty,
                    "before_coverage_pct": round(before_cov * 100.0, 2),
                    "after_coverage_pct": round(after_cov * 100.0, 2),
                    "coverage_delta_pct": round((after_cov - before_cov) * 100.0, 2),
                    "new_unmet_pct": new_unmet_pct,
                })

                db.execute("""
                UPDATE allocations
                SET allocated = ?, unmet = ?, unmet_pct = ?
                WHERE run_id = ? AND zone_id = ? AND resource = ?
                """, (new_qty, new_unmet, new_unmet_pct, body.run_id, zid, res))

        return {
            "status": "applied",
            "label": "manual override, not an optimization result",
            "operator": current_user.username,
            "run_id": body.run_id,
            "donor_floor_pct": body.donor_floor_pct,
            "reason": body.reason,
            "coverage_changes": coverage_changes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/events")
    def get_events():
        try:
            known = _known_events()
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=503, detail={"code": "event_data_unavailable", "message": str(exc)}) from exc
        gauge_by_event = {}
        gauge_path = processed / "gauge_readings.csv"
        if gauge_path.exists():
            for row in _read_csv(gauge_path):
                gauge_by_event.setdefault(row.get("event_date"), row)
        return {"scope": "Bantwal taluk; 16 analytical grid zones", "events": [
            {"event_date": d, "river_gauge": e.river_gauge, "water_level_m": e.water_level_m,
             "danger_mark_m": float(gauge_by_event.get(d, {}).get("danger_level_m") or 9.0),
             "warning_level_m": float(gauge_by_event.get(d, {}).get("warning_level_m") or 8.0),
             "affected_localities": list(e.affected_localities), "roads_blocked": list(e.roads_blocked),
             "houses_affected": e.houses_affected, "source_urls": list(e.source_urls)}
            for d, e in known.items()]}

    @app.get("/zones")
    def get_zones(event: str = Query(..., description="Configured event date (YYYY-MM-DD)")):
        _event_or_404(event)
        zone_path = configured_path(config["data"].get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
        if not zone_path.exists():
            raise HTTPException(status_code=503, detail={"code": "zones_unavailable", "message": f"Generate analysis zones first: {zone_path}"})
        features = json.loads(zone_path.read_text(encoding="utf-8"))
        demand_path = processed / f"severity_demand_{event}.csv"
        try:
            demand = {r["zone_id"]: r for r in _read_csv(demand_path)}
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail={"code": "event_features_unavailable", "message": str(exc)}) from exc
        result = []
        for feature in features.get("features", []):
            props = feature.get("properties", {})
            zone_id = str(props.get("zone_id"))
            row = demand.get(zone_id)
            if row is None:
                raise HTTPException(status_code=503, detail={"code": "zone_data_mismatch", "message": f"No event severity row for {zone_id}"})
            result.append({"zone_id": zone_id, "zone_name": props.get("name"),
                           "geometry": feature["geometry"], "population_estimate": float(row["population_estimate"]),
                           "population_status": "modeled_estimate",
                           "population_year": int(props.get("population_year") or 0),
                           "population_resolution": props.get("population_resolution"),
                           "population_density_per_km2": float(props.get("population_density_per_km2") or 0),
                           "severity_score": float(row["severity_score"]),
                           "sar_likelihood": float(row["sar_likelihood"]),
                           "antecedent_7day_rainfall_mm": float(row["antecedent_7day_rainfall_mm"]),
                           "estimated_affected_people": float(row["estimated_affected_people"]),
                           "estimated_food_rations": int(float(row["estimated_food_rations"])),
                           "estimated_water_liters": int(float(row["estimated_water_liters"])),
                           "estimated_medical_kits": int(float(row["estimated_medical_kits"]))})
        if len(result) != 16:
            raise HTTPException(status_code=503, detail={"code": "scope_mismatch", "message": f"Expected 16 Bantwal zones, found {len(result)}"})
        return {"event": event, "scope": "Bantwal", "zones": result}

    @app.post("/simulate", status_code=201)
    def simulate(body: SimulateRequest, current_user: User = Depends(require_role("viewer"))):
        event = _event_or_404(body.event)
        if body.stock_mode == "entered" and body.stock_pct is not None:
            raise HTTPException(status_code=422, detail={
                "code": "stock_percentage_not_supported",
                "message": "Modeled-need percentages cannot scale operator-entered stock.",
            })
        engine = ENGINES[body.engine]
        run_id = str(uuid.uuid4())
        run_config, basis, unroutable = _stock_config(
            config, processed, body.event, body.stock_mode, db_path=db_path,
            stock_pct=body.stock_pct,
        )
        try:
            with _RUN_LOCK:
                with _preserve_artifacts(_allocator_artifacts(processed, body.event)):
                    run_allocators(body.event, run_config)
                    summary_rows = _read_csv(processed / f"allocation_comparison_{body.event}.csv")
                    selected_summary = next(r for r in summary_rows if r["engine"] == engine)
                    allocations = [r for r in _read_csv(processed / f"allocation_matrix_{body.event}.csv") if r["engine"] == engine]
            available_inventory = {
                key: int(value) for key, value in run_config["resources"]["prototype_inventory"].items()
            }
            selected_summary = {**selected_summary, "stock_pct_of_modeled_need": body.stock_pct,
                                "inventory_used": available_inventory,
                                "available_inventory": available_inventory}
            _insert_run(db_path, run_id=run_id, event_date=body.event, engine=engine,
                        stock_mode=body.stock_mode, inventory_basis=basis,
                        status="completed", summary=selected_summary)
            _persist_allocations(db_path, run_id, allocations)
        except StopIteration as exc:
            raise HTTPException(status_code=503, detail={"code": "allocation_output_missing", "message": "Allocator completed without the selected engine output."}) from exc
        except MilpInfeasible as exc:
            raise HTTPException(status_code=409, detail={"code": "infeasible_run", "message": str(exc)}) from exc
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            if "INFEASIBLE" in str(exc).upper():
                raise HTTPException(status_code=409, detail={"code": "infeasible_run", "message": str(exc)}) from exc
            raise HTTPException(status_code=503, detail={"code": "simulation_failed", "message": str(exc)}) from exc

        status_chip = "ENTERED, UNVERIFIED" if body.stock_mode == "entered" else "ASSUMED"
        return {"run_id": run_id, "event": event.event_date.isoformat(), "engine": body.engine,
                "stock_mode": body.stock_mode, "inventory_basis": basis,
                "stock_pct_of_modeled_need": body.stock_pct,
                "available_inventory": available_inventory,
                "status_chip": status_chip,
                "unroutable_facilities": unroutable,
                "unroutable_facilities_count": len(unroutable),
                "hard_fairness_target_status": selected_summary["hard_fairness_target_status"],
                "summary": selected_summary}

    @app.post("/closures", status_code=200)
    def apply_closure(body: ClosureRequest, current_user: User = Depends(require_role("operator"))):
        with _db_connection(db_path) as db:
            run = db.execute("SELECT * FROM runs WHERE run_id=?", (body.run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail={"code": "unknown_run", "message": f"Unknown run_id: {body.run_id}"})
        event_date = str(run["event_date"])
        closure = _load_verified_closure(processed, event_date, body.closure_id)
        if app.state.road_graph is None:
            raise HTTPException(status_code=503, detail={
                "code": "road_graph_unavailable",
                "message": f"Cannot apply a closure until the cached road graph is available: {app.state.road_graph_error}",
            })
        existing = json.loads(run["closure_ids_json"])
        if body.closure_id in existing:
            raise HTTPException(status_code=409, detail={"code": "closure_already_applied", "message": "This closure has already been applied to the run."})
        run_config, _, unroutable = _stock_config(config, processed, event_date, str(run["stock_mode"]), db_path=db_path)
        run_summary = json.loads(run["summary_json"])
        run_inventory = run_summary.get("available_inventory")
        if run_inventory:
            run_config["resources"]["prototype_inventory"] = {
                key: int(value) for key, value in run_inventory.items()
            }
        basis = str(run["inventory_basis"])
        try:
            with _RUN_LOCK:
                with _preserve_artifacts(_module8_artifacts(processed, event_date)
                                         + _module7_artifacts(processed, event_date)):
                    steps_path, summary_path = run_module8(
                        event_date, config=run_config, cached_graph=app.state.road_graph)
                    route_csv, route_geojson = run_routing(event_date, zone_layer="analysis", config=run_config)
                    module8 = json.loads(summary_path.read_text(encoding="utf-8"))
                    engine = str(run["engine"])
                    dynamic = _read_csv(steps_path)
                    routes = _read_csv(route_csv)
                    route_features = json.loads(route_geojson.read_text(encoding="utf-8")).get("features", [])
                    feature_by_zone = {str((f.get("properties") or {}).get("zone_id")): f for f in route_features}
                    for route in routes:
                        feature = feature_by_zone.get(str(route["zone_id"]))
                        route["geometry"] = feature.get("geometry") if feature else None
                    escalations = [r for r in _read_csv(processed / f"escalation_log_{event_date}.csv") if r["engine"] == engine]
                    dynamic_alloc = [r for r in _read_csv(processed / f"module8_dynamic_zone_unmet_{event_date}.csv") if r["engine"] == engine]
            engine_summary = module8.get("engines", {}).get(engine)
            if engine_summary is None:
                raise RuntimeError(f"Module 8 output has no engine entry for {engine}")
            module9_summary = module8.get("module9", {}).get("engines", {}).get(engine, {})
            filtered_steps = [r for r in dynamic if r["engine"] == engine]
            latest: dict[tuple[str, str], dict[str, Any]] = {}
            for r in dynamic_alloc:
                latest[(r["zone_id"], r["resource"])] = {
                    "zone_id": r["zone_id"], "zone_name": r["zone_name"], "resource": r["resource"],
                    "estimated_need": int(r["final_scenario_need"]),
                    "allocated": int(r["cumulative_allocated"]), "unmet": int(r["final_unmet"]),
                    "unmet_pct": float(r["final_unmet_pct"])}
            with _db_connection(db_path) as db:
                db.execute("DELETE FROM allocations WHERE run_id=?", (body.run_id,))
                db.execute("DELETE FROM escalations WHERE run_id=?", (body.run_id,))
                ids = existing + [body.closure_id]
                db.execute("UPDATE runs SET closure_ids_json=?, summary_json=?, inventory_basis=?, status=? WHERE run_id=?",
                           (json.dumps(ids), json.dumps({"module8": engine_summary,
                                "module9": module9_summary,
                                "steps": filtered_steps, "verified_closure": closure.get("properties"),
                                "all_event_verified_closures_consumed_by_module8": True,
                                "module7_routes": {"zone_count": len(routes),
                                                   "road_count": sum(r["delivery_mode"] == "road" for r in routes),
                                                   "secondary_count": sum(r["delivery_mode"] == "secondary" for r in routes),
                                                   "unreachable_count": sum(r["delivery_mode"] == "none" for r in routes)}}, allow_nan=False),
                            basis, "closure_applied", body.run_id))
            _persist_allocations(db_path, body.run_id, list(latest.values()))
            _persist_escalations(db_path, body.run_id, escalations)
            _persist_routes(db_path, body.run_id, routes)
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            if "INFEASIBLE" in str(exc).upper():
                raise HTTPException(status_code=409, detail={"code": "infeasible_run", "message": str(exc)}) from exc
            raise HTTPException(status_code=503, detail={"code": "closure_run_failed", "message": str(exc)}) from exc
        return {"run_id": body.run_id, "event": event_date, "engine": ENGINES_REVERSE[str(run["engine"])],
                "applied_closure_id": body.closure_id,
                "closure_geometry": closure.get("geometry", {}).get("type"),
                "closure_scope": closure.get("properties", {}).get("verification_scope", "verified event-specific closure artifact"),
                "stock_mode": str(run["stock_mode"]), "inventory_basis": basis,
                "steps": filtered_steps, "module9": module9_summary,
                "module7_routes": {"zone_count": len(routes),
                                   "road_count": sum(r["delivery_mode"] == "road" for r in routes),
                                   "secondary_count": sum(r["delivery_mode"] == "secondary" for r in routes),
                                   "unreachable_count": sum(r["delivery_mode"] == "none" for r in routes)}}

    @app.post("/scenario-reroutes", status_code=200)
    def reroute_scenario(body: ScenarioRerouteRequest, current_user: User = Depends(require_role("operator"))):
        """Recalculate routes only for a curated Bantwal main-road scenario."""
        scenario_path = REPO_ROOT / "config" / "bantwal_road_scenarios.json"
        try:
            scenarios = json.loads(scenario_path.read_text(encoding="utf-8")).get("scenarios", [])
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=503, detail={
                "code": "road_scenarios_unavailable", "message": "Bantwal road scenarios are unavailable."
            }) from exc
        scenario = next((item for item in scenarios if item.get("id") == body.scenario_id), None)
        if scenario is None:
            raise HTTPException(status_code=404, detail={
                "code": "unknown_road_scenario", "message": "That Bantwal road scenario does not exist."
            })
        if app.state.road_graph is None:
            raise HTTPException(status_code=503, detail={
                "code": "road_graph_unavailable",
                "message": f"Cannot recalculate routes until the cached road graph is available: {app.state.road_graph_error}",
            })

        data = config["data"]
        processed = configured_path(data["processed_dir"])
        zones_path = configured_path(data.get("analysis_zones_path", "data/processed/analysis_zones.geojson"))
        try:
            from shapely.geometry import LineString, Point, shape
            from shapely.ops import unary_union

            zones = json.loads(zones_path.read_text(encoding="utf-8"))
            zone_shapes = [shape(feature["geometry"]) for feature in zones.get("features", [])
                           if feature.get("geometry")]
            boundary = unary_union(zone_shapes)
            closure_lines = []
            road_by_id = {item.get("id"): item for item in scenarios if item.get("id")}
            road_ids = scenario.get("road_ids") or [scenario["id"]]
            if not isinstance(road_ids, list) or not road_ids:
                raise ValueError("Scenario must contain at least one mapped road")
            blocked_roads = []
            closure_points = []
            for road_id in road_ids:
                road = road_by_id.get(road_id)
                if road is None or road.get("highway") not in {"trunk", "primary"}:
                    raise ValueError(f"Scenario road {road_id!r} is not a mapped Bantwal trunk or primary road")
                point = road.get("closure_point")
                coordinate_parts = road.get("coordinate_parts")
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError(f"Road {road_id!r} has an invalid closure marker")
                if not isinstance(coordinate_parts, list) or not coordinate_parts:
                    raise ValueError(f"Road {road_id!r} has no mapped geometry")
                closure_point = Point(float(point[0]), float(point[1]))
                road_lines = []
                for coordinates in coordinate_parts:
                    if not isinstance(coordinates, list) or len(coordinates) < 2:
                        raise ValueError(f"Road {road_id!r} contains an invalid mapped segment")
                    line = LineString(coordinates)
                    if not boundary.covers(line):
                        raise ValueError(f"Blocked road {road['name']!r} extends outside the Bantwal analysis boundary")
                    road_lines.append(line)
                if not boundary.covers(closure_point) or not any(line.distance(closure_point) < 0.00001 for line in road_lines):
                    raise ValueError(f"Closure marker for {road['name']!r} is not on its mapped Bantwal road")
                closure_lines.append({
                    "closure_id": road_id,
                    "name": road["name"],
                    "coordinate_parts": coordinate_parts,
                })
                closure_points.append([float(point[0]), float(point[1])])
                blocked_roads.append(road["name"])

            warehouse_path = processed / "warehouses.geojson"
            if warehouse_path.exists():
                warehouse_collection = json.loads(warehouse_path.read_text(encoding="utf-8"))
                origins = []
                for feature in warehouse_collection.get("features", []):
                    geometry = feature.get("geometry")
                    props = feature.get("properties", {})
                    if geometry and geometry.get("type") == "Point" and props.get("route_origin", True):
                        lon, lat = geometry["coordinates"][:2]
                        origins.append({"origin_id": str(props.get("warehouse_id", props.get("name", len(origins)))),
                                        "lon": float(lon), "lat": float(lat),
                                        "origin_source": props.get("source", "warehouses_geojson")})
            else:
                origins = [{"origin_id": str(w.get("warehouse_id", w.get("name", i))),
                            "lon": float(w["lon"]), "lat": float(w["lat"]),
                            "origin_source": "configured_warehouse"}
                           for i, w in enumerate(config.get("warehouses", []))]
            if MINI_TOWN_HALL_SCENARIO_ID not in road_ids:
                origins = [origin for origin in origins
                           if origin["origin_id"] != MINI_TOWN_HALL_ORIGIN_ID]
            graph_path = configured_path(data["road_graph_path"])
            route_rows, details = compute_routes(
                graph_path=graph_path,
                zone_path=zones_path,
                origins=origins,
                closure_lines=closure_lines,
                # Block the full mapped road corridor, including nearby graph
                # edges whose OSM classification or centerline differs from
                # the displayed way. This keeps selected-zone routes clear of
                # the visible closure and its endpoint junctions.
                closure_highways=None,
                closure_radius_m=500.0,
                max_snap_distance_m=float(config.get("routing", {}).get("max_snap_distance_m", 5000)),
                secondary_max_distance_km=float(config.get("routing", {}).get("secondary_max_distance_km", 10)),
                secondary_payload_kg=float(config["resources"].get("secondary_payload_kg", 50)),
                cached_graph=app.state.road_graph,
            )
        except (FileNotFoundError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail={
                "code": "road_scenario_failed", "message": str(exc)
            }) from exc
        return {"scenario_id": body.scenario_id, "blocked_road": ", ".join(blocked_roads),
                "blocked_roads": blocked_roads, "closure_points": closure_points,
                "routing_origin_ids": sorted(origin["origin_id"] for origin in origins),
                "route_count": len(route_rows), "zone_routes": route_rows,
                "routes": details["route_features"]}

    @app.get("/routes/{run_id}")
    def get_routes(run_id: str, current_user: User = Depends(require_role("viewer"))):
        with _db_connection(db_path) as db:
            run = db.execute("SELECT event_date,engine,stock_mode,inventory_basis FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise HTTPException(status_code=404, detail={"code": "unknown_run", "message": f"Unknown run_id: {run_id}"})
            rows = db.execute("SELECT details_json FROM routes WHERE run_id=? ORDER BY zone_id", (run_id,)).fetchall()
        return {"run_id": run_id, "event": run["event_date"], "engine": run["engine"],
                "stock_mode": run["stock_mode"], "inventory_basis": run["inventory_basis"],
                "routes": [json.loads(row["details_json"]) for row in rows]}

    @app.get("/allocation/{run_id}")
    def get_allocation(run_id: str, current_user: User = Depends(require_role("viewer"))):
        with _db_connection(db_path) as db:
            run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise HTTPException(status_code=404, detail={"code": "unknown_run", "message": f"Unknown run_id: {run_id}"})
            allocations = db.execute("SELECT zone_id,zone_name,resource,estimated_need,allocated,unmet,unmet_pct FROM allocations WHERE run_id=? ORDER BY zone_id,resource", (run_id,)).fetchall()
        return {"run_id": run_id, "event": run["event_date"], "engine": run["engine"],
                "stock_mode": run["stock_mode"], "inventory_basis": run["inventory_basis"],
                "status": run["status"], "summary": json.loads(run["summary_json"]),
                "available_inventory": json.loads(run["summary_json"]).get("available_inventory", {}),
                "allocations": [dict(row) for row in allocations]}

    @app.get("/escalations/{run_id}")
    def get_escalations(run_id: str, current_user: User = Depends(require_role("viewer"))):
        with _db_connection(db_path) as db:
            run = db.execute("SELECT event_date,engine,stock_mode,inventory_basis FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise HTTPException(status_code=404, detail={"code": "unknown_run", "message": f"Unknown run_id: {run_id}"})
            rows = db.execute("SELECT * FROM escalations WHERE run_id=? ORDER BY step", (run_id,)).fetchall()
        return {"run_id": run_id, "event": run["event_date"], "engine": run["engine"],
                "stock_mode": run["stock_mode"], "inventory_basis": run["inventory_basis"],
                "escalations": [{**dict(r), "shortfall_by_resource": json.loads(r["shortfall_by_resource_json"]),
                                 "remaining_inventory": json.loads(r["remaining_inventory_json"]),
                                 "remaining_unmet_demand": json.loads(r["remaining_unmet_demand_json"])} for r in rows]}

    # Read-only helper data endpoints for the frontend
    @app.get("/data/zones")
    def get_data_zones():
        zone_path = processed / "analysis_zones.geojson"
        if not zone_path.exists():
            raise HTTPException(status_code=503, detail={"code": "zones_unavailable", "message": "analysis_zones.geojson missing"})
        return json.loads(zone_path.read_text(encoding="utf-8"))

    @app.get("/data/river")
    def get_data_river():
        river_path = processed / "river.geojson"
        if river_path.exists():
            return json.loads(river_path.read_text(encoding="utf-8"))
        raw_path = REPO_ROOT / "data" / "raw" / "osm_netravati_river_relation_3415326.geojson"
        if raw_path.exists():
            return json.loads(raw_path.read_text(encoding="utf-8"))
        raise HTTPException(status_code=503, detail={"code": "river_unavailable", "message": "river GeoJSON missing"})

    @app.get("/data/roads")
    def get_data_roads():
        roads_path = processed / "simplified_roads.geojson"
        if not roads_path.exists():
            raise HTTPException(status_code=503, detail={"code": "roads_unavailable", "message": "simplified_roads.geojson missing"})
        return json.loads(roads_path.read_text(encoding="utf-8"))

    @app.get("/data/facilities")
    def get_data_facilities():
        warehouses_path = processed / "warehouses.geojson"
        if not warehouses_path.exists():
            raise HTTPException(status_code=503, detail={"code": "facilities_unavailable", "message": "warehouses.geojson missing"})
        return json.loads(warehouses_path.read_text(encoding="utf-8"))

    @app.get("/data/closures")
    def get_data_closures(event: str = Query(..., description="Event date YYYY-MM-DD")):
        _event_or_404(event)
        path = processed / f"closures_{event}.geojson"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "closures_not_found", "message": f"No closures for {event}"})
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/data/routes/{event_date}")
    def get_data_routes(event_date: str):
        _event_or_404(event_date)
        path = processed / f"routes_analysis_{event_date}.geojson"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "routes_not_found", "message": f"No route GeoJSON for {event_date}"})
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/data/steps/{event_date}")
    def get_data_steps(event_date: str):
        _event_or_404(event_date)
        path = processed / f"module8_dynamic_steps_{event_date}.csv"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "steps_not_found", "message": f"No steps for {event_date}"})
        return _read_csv(path)

    @app.get("/data/sar-bounds")
    def get_sar_bounds():
        return {
            "bounds": [74.934, 12.663, 75.224, 13.016],
            "center": [75.079, 12.840],
            "zoom": 11,
            "crs": "EPSG:4326",
            "events": {
                "2019-08-10": {"svg": "/data/flood_likelihood_2019-08-10.svg", "tif": "flood_likelihood_2019-08-10.tif"},
                "2024-07-31": {"svg": "/data/flood_likelihood_2024-07-31.svg", "tif": "flood_likelihood_2024-07-31.tif"},
                "2026-08-03": {"svg": "/data/flood_likelihood_2026-08-03.svg", "tif": "flood_likelihood_2026-08-03.tif"},
            }
        }

    @app.get("/sweep")
    def get_sweep(event: str = Query(..., description="Event date YYYY-MM-DD"),
                  stock_pct: float = Query(..., description="Stock percentage (10 to 150)")):
        _event_or_404(event)
        path = processed / f"stock_sweep_{event}.json"
        if not path.exists():
            raise HTTPException(status_code=503, detail={"code": "sweep_unavailable", "message": f"Stock sweep not computed for {event}"})
        raw = json.loads(path.read_text(encoding="utf-8"))
        levels = raw.get("stock_levels", [])
        if not levels:
            raise HTTPException(status_code=500, detail={"code": "sweep_empty", "message": "No sweep levels found"})
        nearest = min(levels, key=lambda x: abs(x - stock_pct))
        matching_records = [r for r in raw.get("records", []) if abs(r["stock_pct"] - nearest) < 1e-4]
        return {
            "event_date": event,
            "requested_stock_pct": stock_pct,
            "nearest_computed_stock_pct": nearest,
            "available_stock_levels": levels,
            "total_modeled_need": raw.get("total_modeled_need", {}),
            "records": matching_records,
        }

    @app.get("/sweep/summary")
    def get_sweep_summary():
        thresholds_path = processed / "stock_sweep_thresholds.json"
        if not thresholds_path.exists():
            raise HTTPException(status_code=503, detail={"code": "thresholds_unavailable", "message": "Sweep thresholds not computed"})
        thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
        return {
            "grid": {
                "min_stock_pct": 10.0,
                "max_stock_pct": 150.0,
                "step_pct": 5.0,
                "total_grid_points": 29,
            },
            "linucb_specification": {
                "seeds": [42, 43, 44, 45, 46],
                "episodes_per_resource": 120,
                "batch_steps": 120,
                "retrain_per_level": True,
                "metrics": ["mean", "min", "max"],
            },
            "thresholds": thresholds,
        }

    @app.get("/data/gauge-readings")
    def get_gauge_readings():
        path = processed / "gauge_readings.csv"
        if not path.exists():
            raise HTTPException(status_code=503, detail={"code": "gauge_unavailable", "message": "gauge_readings.csv missing"})
        return _read_csv(path)

    # -------------------------------------------------------------------------
    # Facility Inventory (Real Stock Entry) Endpoints
    # -------------------------------------------------------------------------
    @app.get("/facilities")
    def get_facilities():
        with _db_connection(db_path) as db:
            return get_all_facilities(db)

    @app.post("/facilities", status_code=201)
    def create_facility(body: FacilityCreateRequest, current_user: User = Depends(require_role("operator"))):
        with _db_connection(db_path) as db:
            cursor = db.cursor()
            cursor.execute("SELECT id FROM facilities WHERE id = ?", (body.id,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail={"code": "facility_exists", "message": f"Facility '{body.id}' already exists"})
            db.execute("""
            INSERT INTO facilities (id, name, type, lat, lon, source, confidence, geometry_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (body.id, body.name, body.type, body.lat, body.lon, body.source, body.confidence, int(body.geometry_verified)))
            now_iso = datetime.now(timezone.utc).isoformat()
            for res, cfg in RESOURCE_LIMITS.items():
                db.execute("""
                INSERT INTO stock (facility_id, resource, quantity, unit, mode, updated_by, updated_at, note)
                VALUES (?, ?, 0, ?, 'assumed', ?, ?, 'Initial creation')
                """, (body.id, res, cfg["units"][0], current_user.username, now_iso))
            db.commit()
            return {"status": "created", "facility_id": body.id}

    @app.put("/facilities/{facility_id}/stock")
    def update_stock(facility_id: str, body: FacilityStockUpdateRequest, current_user: User = Depends(require_role("operator"))):
        with _db_connection(db_path) as db:
            try:
                updated = update_facility_stock(db, facility_id, body.stock, current_user.username)
                return {"status": "updated", "facility_id": facility_id, "updated_items": updated}
            except ValueError as exc:
                raise HTTPException(status_code=422, detail={"code": "stock_validation_error", "message": str(exc)}) from exc

    @app.get("/stock/summary")
    def get_stock_overview():
        with _db_connection(db_path) as db:
            return get_stock_summary(db)

    @app.post("/stock/reset-to-assumed")
    def reset_stock(current_user: User = Depends(require_role("operator"))):
        with _db_connection(db_path) as db:
            count = reset_stock_to_assumed(db, current_user.username)
            return {"status": "reset", "items_reset": count, "operator": current_user.username}

    @app.get("/stock/export")
    def export_stock():
        with _db_connection(db_path) as db:
            csv_content = export_stock_csv(db)
            return Response(content=csv_content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=shelter_inventory.csv"})

    @app.post("/stock/import")
    def import_stock(body: StockImportRequest, current_user: User = Depends(require_role("operator"))):
        with _db_connection(db_path) as db:
            try:
                result = import_stock_csv(db, body.csv_text, current_user.username)
                return result
            except ValueError as exc:
                raise HTTPException(status_code=422, detail={"code": "import_validation_error", "message": str(exc)}) from exc

    # -------------------------------------------------------------------------
    # Scenario Library Endpoints
    # -------------------------------------------------------------------------
    @app.get("/scenarios")
    def list_scenarios():
        return load_scenarios_config()

    @app.post("/scenarios/run")
    def execute_scenario(body: ScenarioRunRequest, current_user: User = Depends(require_role("viewer"))):
        try:
            return run_scenario(body.scenario_id, body.seed, body.parameters)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail={"code": "scenario_not_found", "message": str(exc)}) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"code": "scenario_execution_failed", "message": str(exc)}) from exc

    return app


ENGINES_REVERSE = {value: key for key, value in ENGINES.items()}
app = create_app()
