"""Facility Inventory and Real Stock Entry Management for ResQ.

Manages facilities, warehouse stock, audit logging, CSV import/export,
staleness tracking (>24h), and pooled 'entered' inventory mode.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

RESOURCE_LIMITS = {
    "food_rations": {"max": 500_000, "units": ["rations", "units", "pkts"]},
    "water_liters": {"max": 2_000_000, "units": ["liters", "l"]},
    "medical_kits": {"max": 50_000, "units": ["kits", "boxes"]},
}

STALE_HOURS_THRESHOLD = 24.0


def init_facility_tables(db: sqlite3.Connection, processed_dir: Path) -> None:
    """Create facilities, stock, and stock_audit tables and seed initial facilities."""
    db.executescript("""
    CREATE TABLE IF NOT EXISTS facilities (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'relief_center',
        lat REAL,
        lon REAL,
        source TEXT NOT NULL,
        confidence TEXT NOT NULL DEFAULT 'medium',
        geometry_verified INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS stock (
        facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
        resource TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity >= 0),
        unit TEXT NOT NULL,
        mode TEXT NOT NULL DEFAULT 'assumed',
        updated_by TEXT NOT NULL DEFAULT 'system',
        updated_at TEXT NOT NULL,
        note TEXT,
        PRIMARY KEY (facility_id, resource)
    );

    CREATE TABLE IF NOT EXISTS stock_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id TEXT NOT NULL,
        resource TEXT NOT NULL,
        old_quantity INTEGER,
        new_quantity INTEGER NOT NULL,
        unit TEXT NOT NULL,
        changed_by TEXT NOT NULL,
        changed_at TEXT NOT NULL,
        note TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_stock_audit_facility ON stock_audit(facility_id);
    """)

    # Keep seeded event-confirmed inventory aligned with the authoritative
    # warehouses file so removed sites and their old stock cannot reappear
    # from the persistent service database.
    cursor = db.cursor()
    warehouses_path = processed_dir / "warehouses.geojson"
    warehouse_data = None
    if warehouses_path.exists():
        warehouse_data = json.loads(warehouses_path.read_text(encoding="utf-8"))
        current_event_ids = {
            str(feature.get("properties", {}).get("warehouse_id") or feature.get("properties", {}).get("id") or feature.get("properties", {}).get("name"))
            for feature in warehouse_data.get("features", [])
            if feature.get("properties", {}).get("source") == "event-confirmed"
        }
        cursor.execute("SELECT id FROM facilities WHERE source = 'event-confirmed'")
        stale_event_ids = [row[0] for row in cursor.fetchall() if row[0] not in current_event_ids]
        for facility_id in stale_event_ids:
            db.execute("DELETE FROM stock_audit WHERE facility_id = ?", (facility_id,))
            db.execute("DELETE FROM stock WHERE facility_id = ?", (facility_id,))
            db.execute("DELETE FROM facilities WHERE id = ?", (facility_id,))

    # Seed facilities from warehouses.geojson if empty
    cursor.execute("SELECT COUNT(*) FROM facilities")
    count = cursor.fetchone()[0]
    if count == 0 and warehouse_data is not None:
        data = warehouse_data
        now_iso = datetime.now(timezone.utc).isoformat()
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry")
            f_id = props.get("warehouse_id") or props.get("id") or props.get("name")
            f_name = props.get("name", "Unnamed Facility")
            f_source = props.get("source", "ddmp-designated")
            f_confidence = props.get("confidence", "medium")
            lat, lon = None, None
            geom_verified = 0
            if geom and geom.get("type") == "Point" and geom.get("coordinates"):
                coords = geom["coordinates"]
                lon, lat = float(coords[0]), float(coords[1])
                geom_verified = 1 if props.get("route_origin") or props.get("confidence") == "high" else 0

            db.execute("""
            INSERT OR IGNORE INTO facilities (id, name, type, lat, lon, source, confidence, geometry_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (f_id, f_name, "relief_center", lat, lon, f_source, f_confidence, geom_verified))

            # Baseline stock seed
            for res, cfg in RESOURCE_LIMITS.items():
                default_qty = 5000 if res == "water_liters" else (1000 if res == "food_rations" else 20)
                default_unit = cfg["units"][0]
                db.execute("""
                INSERT OR IGNORE INTO stock (facility_id, resource, quantity, unit, mode, updated_by, updated_at, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (f_id, res, default_qty, default_unit, "assumed", "system_seed", now_iso, "Baseline assumed inventory"))
        db.commit()


def get_all_facilities(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """Retrieve all facilities with their current stock and staleness flags."""
    cursor = db.cursor()
    cursor.execute("SELECT id, name, type, lat, lon, source, confidence, geometry_verified FROM facilities ORDER BY name")
    facilities_rows = cursor.fetchall()

    cursor.execute("SELECT facility_id, resource, quantity, unit, mode, updated_by, updated_at, note FROM stock")
    stock_rows = cursor.fetchall()

    now = datetime.now(timezone.utc)
    stock_by_facility: dict[str, list[dict[str, Any]]] = {}
    for r in stock_rows:
        f_id, res, qty, unit, mode, updated_by, updated_at, note = r
        try:
            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            is_stale = (now - dt).total_seconds() > (STALE_HOURS_THRESHOLD * 3600.0)
        except Exception:
            is_stale = True

        item = {
            "resource": res,
            "quantity": qty,
            "unit": unit,
            "mode": mode,
            "updated_by": updated_by,
            "updated_at": updated_at,
            "is_stale": is_stale,
            "note": note,
        }
        stock_by_facility.setdefault(f_id, []).append(item)

    result = []
    for f in facilities_rows:
        f_id, name, f_type, lat, lon, source, confidence, geom_verified = f
        f_stock = stock_by_facility.get(f_id, [])
        any_stale = any(s["is_stale"] for s in f_stock)
        is_routable = bool(geom_verified and lat is not None and lon is not None)
        result.append({
            "id": f_id,
            "name": name,
            "type": f_type,
            "lat": lat,
            "lon": lon,
            "source": source,
            "confidence": confidence,
            "geometry_verified": bool(geom_verified),
            "is_routable": is_routable,
            "routing_flag": "routable" if is_routable else "unroutable",
            "stock": f_stock,
            "has_stale_stock": any_stale,
        })
    return result


def update_facility_stock(db: sqlite3.Connection, facility_id: str, updates: list[dict[str, Any]],
                          operator_user: str) -> list[dict[str, Any]]:
    """Validate and update stock items for a facility and record audit log."""
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = db.cursor()

    # Verify facility exists
    cursor.execute("SELECT id, name FROM facilities WHERE id = ?", (facility_id,))
    fac = cursor.fetchone()
    if not fac:
        raise ValueError(f"Facility '{facility_id}' not found")

    updated_items = []
    for up in updates:
        res = str(up.get("resource", "")).strip()
        if res not in RESOURCE_LIMITS:
            raise ValueError(f"Invalid resource '{res}'. Valid options: {list(RESOURCE_LIMITS.keys())}")

        qty_raw = up.get("quantity")
        if qty_raw is None or not isinstance(qty_raw, (int, float)) or int(qty_raw) < 0:
            raise ValueError(f"Quantity must be a non-negative whole number for '{res}'")
        qty = int(qty_raw)

        max_limit = RESOURCE_LIMITS[res]["max"]
        if qty > max_limit:
            raise ValueError(f"Quantity {qty} exceeds upper bound limit of {max_limit} for '{res}'")

        unit = str(up.get("unit") or RESOURCE_LIMITS[res]["units"][0]).strip().lower()
        note = str(up.get("note") or "").strip()

        # Fetch old quantity
        cursor.execute("SELECT quantity, unit FROM stock WHERE facility_id = ? AND resource = ?", (facility_id, res))
        old_row = cursor.fetchone()
        old_qty = old_row[0] if old_row else None

        # Upsert stock
        cursor.execute("""
        INSERT INTO stock (facility_id, resource, quantity, unit, mode, updated_by, updated_at, note)
        VALUES (?, ?, ?, ?, 'entered', ?, ?, ?)
        ON CONFLICT(facility_id, resource) DO UPDATE SET
            quantity = excluded.quantity,
            unit = excluded.unit,
            mode = 'entered',
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at,
            note = excluded.note
        """, (facility_id, res, qty, unit, operator_user, now_iso, note))

        # Record audit log
        cursor.execute("""
        INSERT INTO stock_audit (facility_id, resource, old_quantity, new_quantity, unit, changed_by, changed_at, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (facility_id, res, old_qty, qty, unit, operator_user, now_iso, note or f"Manual stock entry by {operator_user}"))

        updated_items.append({
            "resource": res, "quantity": qty, "unit": unit, "mode": "entered",
            "updated_by": operator_user, "updated_at": now_iso, "note": note,
        })

    db.commit()
    return updated_items


def get_stock_summary(db: sqlite3.Connection) -> dict[str, Any]:
    """Aggregate pooled inventory across all facilities, highlighting entered vs assumed."""
    cursor = db.cursor()
    cursor.execute("""
    SELECT s.resource, s.mode, SUM(s.quantity), COUNT(DISTINCT s.facility_id)
    FROM stock s
    JOIN facilities f ON s.facility_id = f.id
    GROUP BY s.resource, s.mode
    """)
    rows = cursor.fetchall()

    cursor.execute("""
    SELECT s.resource, SUM(s.quantity)
    FROM stock s
    JOIN facilities f ON s.facility_id = f.id
    WHERE f.geometry_verified = 0 OR f.lat IS NULL OR f.lon IS NULL
    GROUP BY s.resource
    """)
    unroutable_sums = {r[0]: int(r[1]) for r in cursor.fetchall()}

    cursor.execute("""
    SELECT id, name, geometry_verified
    FROM facilities
    WHERE geometry_verified = 0 OR lat IS NULL OR lon IS NULL
    """)
    unroutable_facilities = [{"id": r[0], "name": r[1]} for r in cursor.fetchall()]

    pooled_by_resource: dict[str, int] = {}
    breakdown_by_resource: dict[str, dict[str, int]] = {}
    modes_seen = set()

    for r in rows:
        res, mode, total_qty, fac_count = r
        total_qty = int(total_qty or 0)
        pooled_by_resource[res] = pooled_by_resource.get(res, 0) + total_qty
        breakdown_by_resource.setdefault(res, {})[mode] = total_qty
        modes_seen.add(mode)

    overall_mode = "entered" if "entered" in modes_seen else "assumed"

    return {
        "overall_mode": overall_mode,
        "pooled_inventory": pooled_by_resource,
        "mode_breakdown": breakdown_by_resource,
        "unroutable_pooled_stock": unroutable_sums,
        "unroutable_facilities_count": len(unroutable_facilities),
        "unroutable_facilities": unroutable_facilities,
        "honesty_label": "Operator-entered stock, unverified, no live sync" if overall_mode == "entered" else "Baseline assumed district inventory",
        "status_chip": "ENTERED, UNVERIFIED" if overall_mode == "entered" else "ASSUMED",
    }


def reset_stock_to_assumed(db: sqlite3.Connection, operator_user: str) -> int:
    """Reset all facilities to baseline assumed stock and log audit trail."""
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = db.cursor()
    cursor.execute("SELECT facility_id, resource, quantity, unit FROM stock")
    existing = cursor.fetchall()

    count = 0
    for f_id, res, old_qty, unit in existing:
        cfg = RESOURCE_LIMITS.get(res, {"max": 50000, "units": ["units"]})
        default_qty = 5000 if res == "water_liters" else (1000 if res == "food_rations" else 20)
        default_unit = cfg["units"][0]

        cursor.execute("""
        UPDATE stock
        SET quantity = ?, unit = ?, mode = 'assumed', updated_by = ?, updated_at = ?, note = 'Reset to assumed baseline'
        WHERE facility_id = ? AND resource = ?
        """, (default_qty, default_unit, operator_user, now_iso, f_id, res))

        cursor.execute("""
        INSERT INTO stock_audit (facility_id, resource, old_quantity, new_quantity, unit, changed_by, changed_at, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (f_id, res, old_qty, default_qty, default_unit, operator_user, now_iso, f"Reset to assumed by {operator_user}"))
        count += 1

    db.commit()
    return count


def export_stock_csv(db: sqlite3.Connection) -> str:
    """Export facility stock table to CSV string."""
    cursor = db.cursor()
    cursor.execute("""
    SELECT f.id, f.name, f.source, f.geometry_verified, s.resource, s.quantity, s.unit, s.mode, s.updated_by, s.updated_at, s.note
    FROM stock s
    JOIN facilities f ON s.facility_id = f.id
    ORDER BY f.name, s.resource
    """)
    rows = cursor.fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["facility_id", "facility_name", "source", "geometry_verified", "resource", "quantity", "unit", "mode", "updated_by", "updated_at", "note"])
    for r in rows:
        writer.writerow(r)
    return output.getvalue()


def import_stock_csv(db: sqlite3.Connection, csv_text: str, operator_user: str) -> dict[str, Any]:
    """Parse and validate imported CSV, updating stock and recording audit."""
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {"facility_id", "resource", "quantity"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError(f"CSV must contain headers: {', '.join(sorted(required))}")

    by_facility: dict[str, list[dict[str, Any]]] = {}
    for row in reader:
        f_id = row.get("facility_id", "").strip()
        res = row.get("resource", "").strip()
        qty = row.get("quantity", "").strip()
        unit = row.get("unit", "").strip()
        note = row.get("note", "").strip()
        if not f_id or not res or not qty:
            continue
        by_facility.setdefault(f_id, []).append({
            "resource": res, "quantity": int(qty), "unit": unit, "note": note,
        })

    updated_count = 0
    for f_id, items in by_facility.items():
        res_items = update_facility_stock(db, f_id, items, operator_user)
        updated_count += len(res_items)

    return {"status": "success", "facilities_updated": len(by_facility), "stock_items_updated": updated_count}
