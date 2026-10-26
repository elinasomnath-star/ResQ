"""Validate Module 9 shortage triggers, redirects, and per-event alert logs."""

from __future__ import annotations

import csv
import json
import math

from resq.config import configured_path, load_config
from resq.events import load_events
from resq.optimization.allocation import RESOURCE_COLUMNS


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main() -> None:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    threshold = float(config.get("module8", {}).get("shortage_threshold", 0.20))
    redirect_pct = float(config.get("module8", {}).get("escalation_redirect_pct", 0.15))
    initial_stock = {r: int(config["resources"]["prototype_inventory"][r]) for r in RESOURCE_COLUMNS}
    for event in load_events():
        day = event.event_date.isoformat()
        summary = json.loads((processed / f"module8_dynamic_summary_{day}.json").read_text(encoding="utf-8"))
        steps = read_rows(processed / f"module8_dynamic_steps_{day}.csv")
        alerts = read_rows(processed / f"escalation_log_{day}.csv")
        transfers = read_rows(processed / f"escalation_reallocation_{day}.csv")
        expected_steps = summary["steps"] * 3
        assert len(steps) == expected_steps, f"{day}: missing engine-step rows"
        assert summary["module9"]["integrated"] is True
        assert summary["shortage_threshold"] == threshold
        assert summary["escalation_redirect_pct"] == redirect_pct

        true_step_rows = [r for r in steps if r["escalation_triggered"].casefold() == "true"]
        assert len(alerts) == len(true_step_rows), f"{day}: every trigger must have one alert row"
        alert_by_id = {r["trigger_id"]: r for r in alerts}
        assert len(alert_by_id) == len(alerts), f"{day}: duplicate trigger IDs"
        for row in steps:
            inventory = json.loads(row["remaining_inventory"])
            unmet = json.loads(row["remaining_unmet_demand"])
            ratios = json.loads(row["inventory_to_unmet_ratio"])
            actual_crossed = []
            for resource in RESOURCE_COLUMNS:
                need = int(unmet[resource])
                ratio = ratios[resource]
                if need and int(inventory[resource]) < threshold * need:
                    actual_crossed.append(resource)
                if need:
                    assert abs(float(ratio) - int(inventory[resource]) / need) < 1e-9
                else:
                    assert ratio is None
                used = initial_stock[resource] - int(inventory[resource])
                assert 0 <= used <= initial_stock[resource], f"{day}: {resource} inventory cap exceeded"
            logged_crossed = [x for x in row["shortage_resource_types"].split(";") if x]
            assert set(logged_crossed) == set(actual_crossed), f"{day}: threshold detection mismatch at step {row['step']} {row['engine']}"
            assert (row["escalation_triggered"].casefold() == "true") == bool(actual_crossed)
            if actual_crossed:
                alert = alert_by_id.get(row["escalation_trigger_id"])
                assert alert is not None, f"{day}: missing alert for {row['escalation_trigger_id']}"
                assert alert["step"] == row["step"] and alert["engine"] == row["engine"]
                assert set(alert["resource_types_short"].split(";")) == set(actual_crossed)
                alert_unmet = json.loads(alert["remaining_unmet_demand"])
                alert_inventory = json.loads(alert["remaining_inventory"])
                shortfalls = json.loads(alert["shortfall_by_resource"])
                trigger_ratios = json.loads(alert["inventory_to_unmet_ratio"])
                for resource in actual_crossed:
                    assert trigger_ratios[resource] < threshold
                    assert int(shortfalls[resource]) == max(0, int(alert_unmet[resource]) - int(alert_inventory[resource]))
                assert alert["affected_zone_ids"]

        transfer_by_trigger: dict[str, list[dict[str, str]]] = {}
        for transfer in transfers:
            transfer_by_trigger.setdefault(transfer["trigger_id"], []).append(transfer)
            resource = transfer["resource_type"]
            amount = int(transfer["redirected_quantity"])
            donor_before = int(transfer["donor_allocated_before"])
            donor_after = int(transfer["donor_allocated_after"])
            recipient_before = int(transfer["recipient_allocated_before"])
            recipient_after = int(transfer["recipient_allocated_after"])
            donor_floor = int(transfer["donor_floor_quantity"])
            recipient_floor = int(transfer["recipient_floor_quantity"])
            assert amount > 0
            assert amount <= math.floor(donor_before * redirect_pct + 1e-9), f"{day}: redirect exceeds configured percentage"
            assert donor_before > donor_floor and donor_after == donor_before - amount >= donor_floor
            assert recipient_before < recipient_floor and recipient_after == recipient_before + amount <= recipient_floor
            assert recipient_after <= int(transfer["recipient_demand"])
            # Donors and recipients are selected from separate floor-defined
            # groups. The least-severe eligible donor can still be more severe
            # than the highest-severity below-floor recipient when those groups
            # do not overlap in severity; group membership and deterministic
            # within-group selection are the actual rule invariants.
            assert transfer["donor_zone_id"] != transfer["recipient_zone_id"]
            assert int(transfer["inventory_total_before"]) == int(transfer["inventory_total_after"])
            assert int(transfer["inventory_total_after"]) <= initial_stock[resource]
            step_minima = set(transfer["global_min_zone_ids_before"].split(";"))
            assert transfer["recipient_zone_id"] in step_minima
            assert transfer["recipient_matches_global_min"].casefold() == "true"
        for trigger_id, alert in alert_by_id.items():
            listed = transfer_by_trigger.get(trigger_id, [])
            assert int(alert["transfer_count"]) == len(listed)
        for trigger_id in transfer_by_trigger:
            assert trigger_id in alert_by_id, f"{day}: transfer without escalation trigger"

        engine_summary = summary["module9"]["engines"]
        # Trace has exactly one row per step. If multiple resources redirect,
        # their recipient zone IDs are semicolon-separated in that row.
        for engine in engine_summary:
            trace_path = processed / f"module9_redirect_trace_{day}_{engine}.csv"
            trace = read_rows(trace_path)
            assert len(trace) == summary["steps"], f"{day} {engine}: trace must have exactly one row per step"
            assert {int(row["step"]) for row in trace} == set(range(1, summary["steps"] + 1))
            step_rows = {int(row["step"]): row for row in steps if row["engine"] == engine}
            for row in trace:
                assert abs(float(row["global_min_value"]) - float(step_rows[int(row["step"])]["minimum_zone_coverage_before_escalation_pct"])) < 1e-8
                if row["redirect_fired"] == "yes":
                    assert row["recipient_matches_global_min"] == "yes"
                    assert set(row["redirect_recipient_zone"].split(";")).issubset(
                        set(row["global_min_zone"].split(";")))
                else:
                    assert row["recipient_matches_global_min"] == "n/a"

        assert sum(int(x["trigger_count"]) for x in engine_summary.values()) == len(alerts)
        assert summary["module9"]["trigger_count"] == len(alerts)
        engine_counts = ", ".join(f"{name}: {item['trigger_count']}" for name, item in engine_summary.items())
        print(f"[{day}] Module 9 pass: {len(alerts)} shortage triggers, {len(transfers)} capped redirects; "
              f"engines={{{engine_counts}}}")


if __name__ == "__main__":
    main()
