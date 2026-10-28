"""Thin HTTP and SQLite service around ResQ's existing pipeline functions."""

from __future__ import annotations

import copy
import csv
import json
import logging
import sqlite3
import threading
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from .config import REPO_ROOT, configured_path, load_config
from .events import load_events
from .optimization.allocation import MilpInfeasible, run_allocators
from .module8 import run_module8
from .routing import _load_graph, run_routing


ENGINES = {
    "MILP": "MILP",
    "LinUCB": "LinUCB_contextual_bandit",
    "proportional": "naive_proportional_baseline",
}
_RUN_LOCK = threading.RLock()  # protects the legacy pipeline's fixed output paths in one process


class SimulateRequest(BaseModel):
    event: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    engine: Literal["MILP", "LinUCB", "proportional"]
    stock_mode: Literal["configured", "simulated"] = "configured"


class ClosureRequest(BaseModel):
    run_id: str
    closure_id: str = Field(min_length=1)


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
                  stock_mode: str) -> tuple[dict[str, Any], str]:
    run_config = copy.deepcopy(config)
    if stock_mode == "configured":
        stock = {k: int(v) for k, v in run_config["resources"]["prototype_inventory"].items()}
        basis = "assumed_inventory: config/region.yaml prototype_inventory"
    elif stock_mode == "simulated":
        stock = _simulated_stock(processed, event_date)
        basis = "assumed_inventory: demo/adequate_supply_summary.csv pooled simulated stock"
    else:  # guarded by Pydantic; useful for internal callers
        raise ValueError(f"Unknown stock mode: {stock_mode}")
    run_config["resources"]["prototype_inventory"] = stock
    return run_config, basis


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

    @app.get("/events")
    def get_events():
        try:
            known = _known_events()
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=503, detail={"code": "event_data_unavailable", "message": str(exc)}) from exc
        return {"scope": "Bantwal taluk; 16 analytical grid zones", "events": [
            {"event_date": d, "river_gauge": e.river_gauge, "water_level_m": e.water_level_m,
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
    def simulate(body: SimulateRequest):
        event = _event_or_404(body.event)
        engine = ENGINES[body.engine]
        run_id = str(uuid.uuid4())
        run_config, basis = _stock_config(config, processed, body.event, body.stock_mode)
        try:
            with _RUN_LOCK:
                with _preserve_artifacts(_allocator_artifacts(processed, body.event)):
                    run_allocators(body.event, run_config)
                    summary_rows = _read_csv(processed / f"allocation_comparison_{body.event}.csv")
                    selected_summary = next(r for r in summary_rows if r["engine"] == engine)
                    allocations = [r for r in _read_csv(processed / f"allocation_matrix_{body.event}.csv") if r["engine"] == engine]
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
        return {"run_id": run_id, "event": event.event_date.isoformat(), "engine": body.engine,
                "stock_mode": body.stock_mode, "inventory_basis": basis,
                "hard_fairness_target_status": selected_summary["hard_fairness_target_status"],
                "summary": selected_summary}

    @app.post("/closures", status_code=200)
    def apply_closure(body: ClosureRequest):
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
        run_config, basis = _stock_config(config, processed, event_date, str(run["stock_mode"]))
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

    @app.get("/routes/{run_id}")
    def get_routes(run_id: str):
        with _db_connection(db_path) as db:
            run = db.execute("SELECT event_date,engine,stock_mode,inventory_basis FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise HTTPException(status_code=404, detail={"code": "unknown_run", "message": f"Unknown run_id: {run_id}"})
            rows = db.execute("SELECT details_json FROM routes WHERE run_id=? ORDER BY zone_id", (run_id,)).fetchall()
        return {"run_id": run_id, "event": run["event_date"], "engine": run["engine"],
                "stock_mode": run["stock_mode"], "inventory_basis": run["inventory_basis"],
                "routes": [json.loads(row["details_json"]) for row in rows]}

    @app.get("/allocation/{run_id}")
    def get_allocation(run_id: str):
        with _db_connection(db_path) as db:
            run = db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None:
                raise HTTPException(status_code=404, detail={"code": "unknown_run", "message": f"Unknown run_id: {run_id}"})
            allocations = db.execute("SELECT zone_id,zone_name,resource,estimated_need,allocated,unmet,unmet_pct FROM allocations WHERE run_id=? ORDER BY zone_id,resource", (run_id,)).fetchall()
        return {"run_id": run_id, "event": run["event_date"], "engine": run["engine"],
                "stock_mode": run["stock_mode"], "inventory_basis": run["inventory_basis"],
                "status": run["status"], "summary": json.loads(run["summary_json"]),
                "allocations": [dict(row) for row in allocations]}

    @app.get("/escalations/{run_id}")
    def get_escalations(run_id: str):
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

    return app


ENGINES_REVERSE = {value: key for key, value in ENGINES.items()}
app = create_app()
