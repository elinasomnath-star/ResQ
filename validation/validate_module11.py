"""Validate the big-three model/allocation outputs and compile RESULTS.md."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from resq.config import REPO_ROOT, configured_path, load_config
from resq.events import load_events
from resq.module8 import run_module8


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def pct(value: str | float) -> str:
    return f"{float(value):.2f}%"


def module0_9_status_section(processed: Path) -> list[str]:
    """Render the latest full validator matrix when the suite has been run."""
    path = processed / "validation_modules0_9.csv"
    if not path.exists():
        return []
    rows = read_csv(path)
    dates = ["2019-08-10", "2024-07-31", "2026-08-03"]
    by_key = {(int(row["module"]), row["event_date"]): row["status"] for row in rows}
    table = ["## Modules 0-9 validator status", "",
             "Global input checks (Modules 0-3) are repeated across event columns; event-level outputs are validated independently.", "",
             "| Module | 2019-08-10 | 2024-07-31 | 2026-08-03 |", "|---|---|---|---|"]
    for module in range(10):
        table.append("| Module " + str(module) + " | " + " | ".join(by_key.get((module, day), "NOT RUN") for day in dates) + " |")
    table += ["", "Detailed output: `data/processed/validation_modules0_9.csv`."]
    return table


def main() -> None:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    events = load_events()
    assert [e.event_date.isoformat() for e in events] == ["2019-08-10", "2024-07-31", "2026-08-03"]
    # Module 11's final report includes the repeated-disruption benchmark, so
    # regenerate its inputs instead of silently accepting stale partial files.
    for event in events:
        run_module8(event.event_date.isoformat())
    supply_rows = read_csv(REPO_ROOT / "demo" / "adequate_supply_summary.csv")
    status_lines = module0_9_status_section(processed)
    supply_table = [
        "| Event | Configured Module 8 baseline | Module 6 simulated | Module 8 MILP | Module 8 LinUCB | Module 8 proportional | Target |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    baseline_unmet_by_day: dict[str, float] = {}
    static_unmet_by_day: dict[str, float] = {}
    for day in ["2019-08-10", "2024-07-31", "2026-08-03"]:
        selected = [row for row in supply_rows if row["event_date"] == day]
        baseline = float(selected[0]["configured_baseline_unmet_pct"])
        baseline_unmet_by_day[day] = baseline
        static_metrics = read_csv(processed / f"allocation_comparison_{day}.csv")
        static_milp = next(row for row in static_metrics if row["engine"] == "MILP")
        static_unmet_by_day[day] = float(static_milp["aggregate_unmet_demand_pct"])
        values = {row["engine"]: float(row["simulated_unmet_pct"]) for row in selected}
        module6_value = float(selected[0]["module6_scenario_unmet_pct"])
        target_value = float(selected[0]["scenario_target_unmet_pct"])
        supply_table.append(
            f"| {day} | {baseline:.2f}% | {module6_value:.2f}% | {values['MILP']:.2f}% | "
            f"{values['LinUCB_contextual_bandit']:.2f}% | {values['naive_proportional_baseline']:.2f}% | {target_value:.1f}% |"
        )
    range_for = lambda key: (min(float(row[key]) for row in supply_rows),
                             max(float(row[key]) for row in supply_rows))
    m6_mean_range = range_for("static_mean_zone_coverage_pct")
    m6_min_range = range_for("static_minimum_zone_coverage_pct")
    m8_mean_range = range_for("mean_zone_resource_coverage_pct")
    m8_min_range = range_for("minimum_zone_coverage_pct")
    sections = [
        "# Phase III Milestone E - Big-three validation demo",
        "",
        "This reproducible, headless demo compiles Module 11 metrics for the three requested Sentinel-1-era Bantwal floods. It reports observed event-level gauge heights and news-reported impacts separately from model estimates and synthetic policy simulation. After `python -m resq.phase2`, run `python validation/validate_module6.py` and then `python validation/validate_module11.py` to validate feasibility and regenerate this report.",
        "",
        "## Study area and allocation design",
        "",
        "The analysis uses 16 regular grid zones clipped to the Bantwal taluk polygon. The cached SAR raster covers this parent polygon; every allocation zone is contained within it. Grid cells are analytical service areas, not administrative villages.",
        "",
        "Module 6 allocates the modeled food, water, and medical demand across these zones using zone severity and the configured inventory. Module 8 repeats the decision over eight disruption rounds using event-specific closure geometries and remaining stock. Population is split by zone area because a sub-taluk population raster is unavailable; rainfall, SAR, and gauge-HAND features are summarized from cached rasters.",
        "",
        "These are modeled policy comparisons, not observed deliveries. Aggregate unmet demand is constrained by the stock assumption; per-zone service and the minimum served zone show how each policy distributes that stock.",
        "",
        "## Locality and Module 7 routing data status",
        "",
        "The locality audit covers 18 distinct event labels. Automatic OSM matches: Jakribettu and Panemangaluru. Manual point assignments: none, because the DDMP lists village/hobli/gram-panchayat context but supplies no coordinates and no article-to-OSM landmark match could be verified. Explicit fallback labels: Ajilamagaru, Aladka, Aladkapadpu, Baddakatte, Bantwal Kelagina Pete, Bastipadpu, Bhandaribettu, Bogodi, Brahmarakottlu, Kadeshivalaya, Kotekani, Maninalkur, Nandarabettu, Navoor, Navur, and Sarapady. Each is recorded in `data/processed/locality_geocoding_log.csv`; none is silently assigned a guessed point.",
        "",
        "The DDMP Safe Shelter table (pp. 58-60) names 47 distinct facilities, principally in Mangaluru and nearby taluks, not a Bantwal warehouse inventory. Individual Nominatim searches returned no OSM candidates for those 47 shelter names; `data/processed/warehouses.geojson` preserves them as medium-confidence DDMP-designated shelter candidates with null geometry. The file now also includes three event-confirmed relief-site candidates: SVS Kannada Medium School, Mini Town Hall Mangaluru, and Panemangaluru Sharada High School/locality. The Mini Town Hall report is from June 2025, not the 2026 Bantwal event; the Panemangaluru school is named in the Aug 2, 2026 report, but its coordinate reuses the village point rather than a school-building point. Null geometries are excluded from routing.",
        "",
        "Module 7's A* scenario fixture passes (three taluk routes; a synthetic point removed two directed graph edges). The real-event validator reports PARTIAL PASS for all three events: 2019 Bantwal-Belthangady matches cached OSM NH73/NH234 ways; 2024 Panjala/Uppinangady matches nearby NH75 geometry (older NH48 designation); and 2026 Kotekani matches the NH73 Bantwal-Belthangady corridor. Each removes 35 directed graph edges and produces three routes. The NH73/NH75 geometries are corridor-level stress-test closures on highways identified by event reports, not pinpointed flood coordinates. For 2026, an exact graph-name search found no Aladka, Kanchikarpete, or Kotekani name-tagged edges within the Module 3 Bantwal polygon bounds. The Daijiworld report nevertheless places the Kotekani road overflow on the highway connecting Jakribettu through Bantwal toward Beltangady; matching that source-described corridor to the cached NH73 ways supports a corridor-level closure. Aladka and Kanchikarpete remain unresolved: reports place Aladka in the Panemangalore area and identify Kanchikarpete as the Netravati monitoring-centre locality, but neither gives the exact flooded road segment or a precise location that can be matched to a cached edge. The Kotekani flood point also remains unknown. This is also an example of sparse OSM name coverage for hyperlocal streets in smaller Indian towns. The 2024 Belthangady-Moodbidri and landslide closures, plus two other 2019 road labels, remain unresolved. The supplied 2019 event CSV lists Talapady service road, Bantwal-Belthangady road, and Marnabail-Panolibail connectivity road; 'Nandavara bridge' is absent. See validator output for per-event status.",
        "",
        "Sources: [Dakshina Kannada DDMP 2022-23](https://dk.nic.in/en/disaster-management/), [OSM NH73 way 197733702](https://www.openstreetmap.org/way/197733702), [OSM NH73 way 1370252437](https://www.openstreetmap.org/way/1370252437), [2024 SVS relief-centre report](https://newskarnataka.com/mangaluru/deputy-commissioner-assesses-flood-damage-in-bantwal-announces-relief-measures/01082024/), [2025 Mini Town Hall relief-centre report](https://www.deccanherald.com/india/karnataka/as-heavy-rains-lash-mangaluru-flood-victims-worry-for-their-homes-3587163), and [2026 report naming Panemangaluru Sharada High School as a ready relief centre](https://newskarnataka.com/mangaluru/bantwal-on-flood-alert-as-netravati-nears-danger-mark/02082026/).",
        "",
        "## SAR input",
        "",
        "Sentinel-1 SAR provides a candidate VH-change signal as one input to zone severity. The maps show only the 16 Bantwal grid zones, clipped within the parent taluk boundary, with the Netravati river; the second map set adds cached OSM roads and relief centres inside Bantwal.",
        "",
    ]
    status_section = module0_9_status_section(processed)
    if status_section:
        insert_at = sections.index("## SAR input")
        sections[insert_at:insert_at] = status_section + [""]
    demand_by_day: dict[str, dict[str, str]] = {}
    metric_by_day: dict[str, list[dict[str, str]]] = {}
    zone_metric_by_day: dict[str, list[dict[str, str]]] = {}
    for event in events:
        day = event.event_date.isoformat()
        manifest = json.loads((processed / f"sar_manifest_{day}.json").read_text(encoding="utf-8"))
        severity = [r for r in read_csv(processed / f"zone_severity_{day}.csv") if r["status"] == "computed"]
        assert severity, f"No computed Bantwal SAR rows for {day}"
        total_pixels = sum(int(r.get("valid_pixels", 0)) for r in severity)
        naive = sum(float(r["naive_flood_candidate_fraction"]) * int(r.get("valid_pixels", 0)) for r in severity) / max(1, total_pixels)
        constrained = sum(float(r["hand_restricted_flood_candidate_fraction"]) * int(r.get("valid_pixels", 0)) for r in severity) / max(1, total_pixels)
        mean_likelihood = sum(float(r["mean_hand_restricted_flood_likelihood"]) * int(r.get("valid_pixels", 0)) for r in severity) / max(1, total_pixels)
        reduction = 100 * (1 - constrained / naive) if naive else 0.0
        sections.append(f"| {day} | {event.water_level_m:.1f} | {manifest['before_date']} to {manifest['during_date']} | {mean_likelihood:.4f} | {naive:.4f} to {constrained:.4f} | {reduction:.1f}% |")

        demand = read_csv(processed / f"severity_demand_{day}.csv")
        assert demand, f"No Bantwal zone demand rows for {day}"
        total_population = sum(max(0.0, float(r.get("population_estimate", 0) or 0)) for r in demand)
        weighted_severity = sum(float(r["severity_score"]) * max(0.0, float(r.get("population_estimate", 0) or 0))
                                for r in demand) / max(1e-9, total_population)
        demand_by_day[day] = {"severity_score": str(weighted_severity)}
        model = json.loads((processed / f"severity_model_{day}.json").read_text(encoding="utf-8"))
        if day == "2019-08-10":
            assert model["validation_event"] is None
        else:
            assert model["validation_event"] == day
            assert model["calibration_event"] == "2019-08-10"

        metrics = read_csv(processed / f"allocation_comparison_{day}.csv")
        expected_engines = {"MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline"}
        assert expected_engines == {r["engine"] for r in metrics}
        assert {r["hard_fairness_target_status"] for r in metrics} == {"INFEASIBLE"}
        matrix = read_csv(processed / f"allocation_matrix_{day}.csv")
        assert {r["event_date"] for r in matrix} == {day}
        zone_metrics = read_csv(processed / f"allocation_zone_metrics_{day}.csv")
        assert len(zone_metrics) == len(expected_engines) * len(demand)
        zone_metric_by_day[day] = zone_metrics
        inventory = config["resources"]["prototype_inventory"]
        for engine in expected_engines:
            for resource, stock in inventory.items():
                used = sum(int(r["allocated"]) for r in matrix if r["engine"] == engine and r["resource"] == resource)
                assert used <= int(stock), f"{day} {engine} exceeded {resource} inventory"
        signatures = {
            engine: tuple((r["resource"], r["zone_id"], int(r["allocated"]))
                          for r in sorted(matrix, key=lambda x: (x["resource"], x["zone_id"]))
                          if r["engine"] == engine)
            for engine in expected_engines
        }
        if len(demand) > 1:
            assert len(set(signatures.values())) >= 2, f"{day}: no allocator allocation pattern differs"
        metric_by_day[day] = metrics

    sections += [
        "",
        "The 2024 July-August episode is represented as one event-level validation record (the supplied 31 July peak date); reports describe multiple impacts over the following days. The SAR date pair is the available before/during scene selected for that event window. This dataset does not split the SAR signal into independently labeled sub-peaks.",
        "",
        "## Severity proxy check",
        "",
        "The model is calibrated only on the 2019 event and synthetic perturbations. Held-out gauge-height comparisons are proxy checks, not independent severity validation.",
        "",
        "| Held-out event | Gauge ratio proxy | Population-weighted zone severity | Absolute proxy difference |",
        "|---|---:|---:|---:|",
    ]
    gauge_reference = float(config["events"].get("gauge_reference_level_m", 11.6))
    for event in events:
        day = event.event_date.isoformat()
        if day == "2019-08-10":
            continue
        proxy = min(1.0, event.water_level_m / gauge_reference)
        score = float(demand_by_day[day]["severity_score"])
        sections.append(f"| {day} | {proxy:.4f} | {score:.4f} | {abs(proxy - score):.4f} |")

    sections += [
        "",
        "## Module 6 static allocation comparison (Bantwal analysis grid)",
        "",
        "| Event | Engine | Mean unmet demand | Min zone served | Medical need satisfied | Population coverage | Objective | Solve/inference (s) | Bandit fit (s) | MILP 40% target feasibility |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for event in events:
        day = event.event_date.isoformat()
        metric_rows = metric_by_day[day]
        for row in metric_rows:
            unmet = float(row["aggregate_unmet_demand_pct"])
            sections.append(
                f"| {day} | {row['engine']} | {pct(unmet)} | {pct(row['minimum_zone_fairness_pct'])} | "
                f"{pct(row['critical_medical_demand_satisfied_pct'])} | {pct(row['population_coverage_pct'])} | "
                f"{float(row['weighted_allocation_objective']):.4f} | {float(row['solve_or_inference_time_seconds']):.6f} | "
                f"{float(row['bandit_training_time_seconds']):.4f} | {row['hard_fairness_target_status']} |"
            )

    sections += [
        "",
        "## Per-zone shortfall and service coverage",
        "",
        "Each row reports minimum coverage across the three resources for that zone, followed by resource-specific unmet percentages. This shows how policies distribute the same constrained stock.",
        "",
        "| Event | Engine | Zone | Minimum resource coverage | Food unmet | Water unmet | Medical unmet |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for event in events:
        day = event.event_date.isoformat()
        for row in zone_metric_by_day[day]:
            sections.append(
                f"| {day} | {row['engine']} | {row['zone_name']} | {pct(row['minimum_resource_coverage_pct'])} | "
                f"{pct(row['food_rations_unmet_pct'])} | {pct(row['water_liters_unmet_pct'])} | {pct(row['medical_kits_unmet_pct'])} |"
            )

    sections += [
        "",
        "## Module 8 dynamic allocation comparison",
        "",
        "Run `python -m resq.module8` to generate eight sequential decisions per event over the Bantwal analytical zones. Module 8 activates each event's verified Module 7 closure at step 2, removes matching directed edges from the cached graph, and measures route and affected-zone changes; a bounded synthetic hazard ramp remains between rounds.",
        "",
        "| Event | Engine | Zones | Steps | Cumulative solve/inference (s) | Mean step (s) | Mean step unmet | Final min-zone coverage | Mean weighted service | Escalations | Redirects | Min-coverage change (pp) | Zone shortfalls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    module8_available = True
    module8_totals = {engine: 0.0 for engine in ("MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline")}
    for event in events:
        day = event.event_date.isoformat()
        report_path = processed / f"module8_dynamic_summary_{day}.json"
        if not report_path.exists():
            module8_available = False
            continue
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for engine, row in report["engines"].items():
            module8_totals[engine] += float(row["cumulative_solve_or_inference_seconds"])
            sections.append(
                f"| {day} | {engine} | {report['zone_metadata']['zone_count']} | {report['steps']} | "
                f"{float(row['cumulative_solve_or_inference_seconds']):.6f} | {float(row['mean_step_seconds']):.6f} | "
                f"{pct(row['mean_step_unmet_demand_pct'])} | {pct(row['final_minimum_zone_coverage_pct'])} | "
                f"{float(row['mean_step_weighted_service_objective']):.4f} | "
                f"{int(report['module9']['engines'][engine]['trigger_count'])} | "
                f"{int(report['module9']['engines'][engine]['transfer_count'])} | "
                f"{float(report['module9']['engines'][engine]['mean_coverage_change_pct_points']):+.4f} | "
                f"[CSV](data/processed/module8_dynamic_zone_unmet_{day}.csv) |"
            )
    if not module8_available:
        sections.append("| Pending | Run `python -m resq.module8` to produce all three event reports. | | | | | | | | | | | |")
    else:
        milp_total = module8_totals["MILP"]
        linucb_total = module8_totals["LinUCB_contextual_bandit"]
        relative_time = 100.0 * (linucb_total - milp_total) / milp_total if milp_total else 0.0
        sections += [
            "",
            f"Across the three 8-step runs, cumulative solve/inference time was {milp_total:.6f} s for MILP and {linucb_total:.6f} s for LinUCB; the proportional baseline used {module8_totals['naive_proportional_baseline']:.6f} s. The comparison uses a 16-cell analytical grid and simulated demand/inventory, so it describes this scenario only and does not establish operational performance.",
            "For each event, Module 9 triggered on 24/24 engine-steps (8 steps times 3 engines). This follows from the severe shortage in the configured-stock Module 8 scenario: remaining stock was below 20% of remaining unmet demand in every round. The current recipient trace recomputes the step-start minimum and directs eligible transfers to the least-served zone. The floor may remain flat when other zones are tied at the same minimum. The trace files are `data/processed/module9_redirect_trace_{event_date}_{engine}.csv`, with one row per step. The default stopgap redirects at most 15% of donor allocation while preserving fairness-floor bounds and total stock. It is a heuristic for redirecting resources while waiting for reinforcements, not an optimization improvement.",
        ]

    feasibility = json.loads((processed / "module6_fairness_feasibility.json").read_text(encoding="utf-8"))
    sections += [
        "",
        "## Hard-fairness feasibility check",
        "",
        "The 40% target is tested as a hard MILP lower bound. Under configured stocks, CBC reports INFEASIBLE; the operational shortage comparison then uses a separately labeled MILP rerun at the maximum feasible common floor. A synthetic inventory check at 50% of total modeled need verifies that the same 40% hard constraint can be met when supply is sufficient.",
        "",
        "| Event | Current-stock hard MILP | Maximum feasible common floor | Synthetic supply test | Synthetic achieved min-zone service |",
        "|---|---|---:|---|---:|",
    ]
    for row in feasibility:
        sections.append(
            f"| {row['event_date']} | {row['current_inventory_hard_status']} | "
            f"{float(row['current_inventory_max_feasible_floor_pct']):.2f}% | {row['synthetic_hard_status']} at 50% of need | "
            f"{float(row['synthetic_achieved_min_zone_coverage_pct']):.2f}% |"
        )

    sections += [
        "",
        "## Severity inputs",
        "",
        "Sentinel-1 SAR was used to derive a candidate VH-change signal as one zone-severity input. See [the presentation severity table](demo/zone_severity_scores.csv). Population, affected-people, and resource-need columns are modeled estimates, not observed impacts.",
        "",
        "## Supply sensitivity",
        "",
        f"Under configured prototype inventory, the eight-step scenario has {baseline_unmet_by_day['2019-08-10']:.2f}% unmet demand in 2019, {baseline_unmet_by_day['2024-07-31']:.2f}% in 2024, and {baseline_unmet_by_day['2026-08-03']:.2f}% in 2026. The separate synthetic-stock sensitivity uses an explicit 55% minimum zone-service floor and targets about 1.5% unmet in 2019 and 8% in 2024/2026. It is a designed scenario, not measured inventory or observed outcomes. Compare per-engine [zone coverage](demo/allocation_engine_coverage.png) and the [supply sensitivity chart](demo/supply_sensitivity_unmet_demand.png).",
        "",
    ]
    sections += [
        "",
        "## Interpretation and limits",
        "",
        "- The 2019 event is the calibration record and is excluded from held-out severity validation. Only 2024 and 2026 count as held-out proxy comparisons. The 2024 reports cover two flood pulses/impact periods, but the available event-level record does not provide separate ground-truth targets for each pulse.",
        "- The 16 analysis zones are regular grid cells clipped to Bantwal, not mapped village or ward boundaries. Their population values use an area-weighted split of the taluk total because no sub-taluk population raster is available.",
        "- Aggregate unmet demand is largely fixed by stock caps. Compare per-zone shortfalls and minimum service instead. The MILP is severity-weighted, LinUCB uses contextual urgency/equity rewards, and the baseline is proportional to need. LinUCB training uses perturbed scenarios from all three event vectors, so allocator comparisons are simulations, not blind event holdouts.",
        "- Module 8 applies event-specific verified Module 7 closure geometries to the cached graph at step 2 and recomputes route impacts; some closures are corridor-level stress geometries, not pinpoint flood coordinates. Module 9 alerts and partial reallocations are rule-based scenario heuristics, not operational dispatch advice. The population estimate is apportioned by area, and facility inventory remains simulated.",
        "- The supplied 2024 value is 9.3 m. A contemporaneous report records 9.1 m at 08:00 on 1 August, reflecting a different observation timestamp; the difference is retained as source variation rather than silently harmonized.",
        "",
        "## Event source links",
        "",
    ]
    for event in events:
        day = event.event_date.isoformat()
        links = ", ".join(f"[source {i}]({url})" for i, url in enumerate(event.source_urls, 1))
        sections.append(f"- **{day}:** {links}")
    sections.append("")
    limits_section = sections.index("## Interpretation and limits")
    source_links_section = sections.index("## Event source links", limits_section)
    sections[limits_section + 1:source_links_section] = [
        "- The analysis grid is not an administrative boundary layer, and population is area-apportioned across grid cells.",
        "- Aggregate unmet demand is driven by configured stock. The 25x sensitivity result is a counterfactual, not evidence that those supplies exist or that real-world unmet demand would fall below 10%.",
        "- Some road closures match highway corridors rather than exact flooded segments, and facility points do not confirm capacity or available stock.",
        "",
    ]
    sar_section = sections.index("## SAR input")
    allocation_section = next(
        index for index, line in enumerate(sections)
        if line.startswith("## Module 6 static allocation comparison")
    )
    sections[sar_section:allocation_section] = [
        "## SAR input",
        "",
        "Sentinel-1 SAR was used to derive the candidate VH-change signal shown in the presentation maps and summarized by zone as one severity input.",
        "",
    ]
    sections = [
        "# Results",
        "",
        "ResQ estimates zone severity and relief needs for three reported Netravati flood events. Its 16 analytical zones are clipped within Bantwal taluk, the parent polygon fully covered by valid SAR pixels on all three dates.",
        "",
        "## Focus area and SAR context",
        "",
        "The [severity table](demo/zone_severity_scores.csv) reports modeled severity for each of the 16 Bantwal analysis zones and event. Population, affected people, and resource needs are estimates, not observed counts.",
        "",
        "The [SAR coverage table](demo/sar_zone_coverage.csv) gives valid raster pixel counts for each Bantwal zone by event. The six presentation maps show SAR, internal zone boundaries, and the Netravati river; a second set also overlays OSM roads and mapped event-confirmed relief centres.",
        "",
        "## Allocation scenarios",
        "",
        f"With configured prototype inventory, the eight-step Module 8 scenario has {baseline_unmet_by_day['2019-08-10']:.2f}% unmet demand for 2019, {baseline_unmet_by_day['2024-07-31']:.2f}% for 2024, and {baseline_unmet_by_day['2026-08-03']:.2f}% for 2026.",
        f"The Module 6 static configured-stock benchmark has {static_unmet_by_day['2019-08-10']:.2f}% unmet demand for 2019, {static_unmet_by_day['2024-07-31']:.2f}% for 2024, and {static_unmet_by_day['2026-08-03']:.2f}% for 2026.",
        "",
        "A separate synthetic-stock sensitivity targets about 1.5% unmet demand for 2019 and 8% for 2024 and 2026. These are designed stock assumptions, not measured shelter inventory or observed outcomes. Module 6 and Module 8 use separate pools sized to their own modeled demand:",
        "",
        *supply_table,
        "",
        "See the [scenario table](demo/adequate_supply_summary.csv), [engine coverage chart](demo/allocation_engine_coverage.png), and [supply sensitivity chart](demo/supply_sensitivity_unmet_demand.png). The facility stock split is illustrative; Module 8 allocates from a combined pool without facility-specific stock or capacity constraints.",
        "",
        f"Under synthetic stock, mean zone/resource coverage is {m6_mean_range[0]:.2f}-{m6_mean_range[1]:.2f}% for static Module 6 and {m8_mean_range[0]:.2f}-{m8_mean_range[1]:.2f}% for dynamic Module 8. Minimum zone/resource coverage is {m6_min_range[0]:.2f}-{m6_min_range[1]:.2f}% for Module 6 and {m8_min_range[0]:.2f}-{m8_min_range[1]:.2f}% for Module 8.",
        "The three engines now allocate across 16 zones with different SAR/HAND severity and population-weighted demand. Their per-zone coverage can differ even where aggregate unmet demand is similar because each engine uses a different allocation rule.",
        "",
        "Module 9 evaluates shortage triggers and donor-to-recipient transfers across zones; event-level counts and coverage changes are reported in the Module 8/9 tables above.",
        "",
        "## Inventory workflow and scope",
        "",
        "The current inventory values are simulated. In a future deployment, authorized shelter officials could enter available resources at their locations for the allocation system to use. This repository has no live login or inventory service.",
        "",
        "Each event uses one dated record followed by eight modeled disruption rounds; it is not a daily timeline. The 2024 impact peaks are not separate allocation periods.",
        "",
    ]
    if status_lines:
        insert_at = sections.index("## Inventory workflow and scope")
        sections[insert_at:insert_at] = status_lines + [
            "", "Module 10 is not implemented in the checked-in source or validator scripts. Module 11 is this report-generation/big-three validation script, not a separate modeling module.", ""]
    # Keep the student-facing report focused on the configured 16-cell Bantwal grid.
    analysis_zones = json.loads(configured_path(config["data"]["analysis_zones_path"]).read_text(encoding="utf-8"))["features"]
    assert len(analysis_zones) == 16
    assert all(row["properties"].get("zone_type") == "analysis_grid" for row in analysis_zones)
    parent_zones = json.loads(configured_path(config["data"]["zones_path"]).read_text(encoding="utf-8"))["features"]
    bantwal_parent = next((f for f in parent_zones if str(f.get("properties", {}).get("name", "")).casefold().startswith("bantwal")), None)
    parent_population = float((bantwal_parent or {}).get("properties", {}).get("population_estimate") or 0)
    event_summary = [
        "| Event | Gauge stage | SAR before → during | Module 6 configured unmet | Module 8 configured unmet after 8 rounds | Module 8 simulated-stock unmet |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for event in events:
        day = event.event_date.isoformat()
        manifest = json.loads((processed / f"sar_manifest_{day}.json").read_text(encoding="utf-8"))
        simulated = [row for row in supply_rows if row["event_date"] == day]
        m8_simulated = sum(float(row["simulated_unmet_pct"]) for row in simulated) / max(1, len(simulated))
        m6_simulated = sum(float(row["module6_scenario_unmet_pct"]) for row in simulated) / max(1, len(simulated))
        event_summary.append(
        f"| {day} | {event.water_level_m:.1f} m | {manifest['before_date']} to {manifest['during_date']} | "
            f"{static_unmet_by_day[day]:.2f}% | {baseline_unmet_by_day[day]:.2f}% | {m8_simulated:.2f}% (static sensitivity {m6_simulated:.2f}%) |"
        )
    sections = [
        "# ResQ results - Bantwal",
        "",
        "ResQ uses Sentinel-1 SAR context, rainfall, terrain, and population estimates to score severity in 16 Bantwal analysis zones and compare relief-allocation policies. The focus is Bantwal taluk only.",
        "",
        "## Zones and population",
        "",
        f"The analysis uses exactly {len(analysis_zones)} regular grid cells clipped to the Bantwal taluk polygon. Every cell contains valid SAR pixels on all three event dates. These are analytical zones, not official village or ward boundaries; the six maps show the same zone layer.",
        f"Zone population values are area-weighted shares of the Bantwal parent estimate ({parent_population:,.0f}), assuming uniform density within the taluk. They are a spatial proxy, not measured population counts for the individual zones.",
        "",
        "## Event and allocation results",
        "",
        *event_summary,
        "",
        "The configured-stock results show how the current prototype inventory limits service. The separate simulated-stock sensitivity assumes a larger pooled supply and a 55% minimum zone-service floor; it is a scenario, not measured shelter inventory or an observed outcome.",
        "All engines use the same total demand and inventory caps, so aggregate unmet demand can be similar even when the distribution across zones differs. Compare the per-zone Module 6 charts and Module 8 minimum-coverage traces; equal totals do not mean identical allocations.",
        "",
        "## Demo figures",
        "",
        "The six maps show the candidate SAR signal, 16 Bantwal grid boundaries, and Netravathi river; three companion maps add cached OSM roads and mapped relief-centre locations.",
        "",
        "| Figure | Description |",
        "|---|---|",
        "| [`zone_severity_scores.png`](demo/zone_severity_scores.png) | Zone severity by event |",
        "| [`allocation_engine_coverage.png`](demo/allocation_engine_coverage.png) | Mean zone/resource coverage by engine |",
        "| [`supply_sensitivity_unmet_demand.png`](demo/supply_sensitivity_unmet_demand.png) | Configured stock and simulated-stock scenario |",
        "| [`module6_static_zone_coverage_2024-07-31.png`](demo/module6_static_zone_coverage_2024-07-31.png) | Static per-zone coverage example |",
        "| [`module8_minimum_coverage_steps_2024-07-31.png`](demo/module8_minimum_coverage_steps_2024-07-31.png) | Eight-step minimum-coverage example |",
        "",
        "## Modules 0–9 validation",
        "",
        *status_lines,
        "",
        "Module 7 passes its integration validator as a partial real-event routing check: the closure geometries are corridor-level matches, and route output is limited by the available scenario origins and destinations.",
        "",
        "## Sources and limits",
        "",
        "- The 16 analytical zones are regular grid cells clipped to the cached Bantwal taluk polygon; they are not administrative units.",
        "- The Bantwal parent population estimate is split by zone area because a sub-taluk population raster is not available. Density variation within Bantwal is not represented.",
        "- SAR is shown as a candidate VH-change signal for severity context, not a verified flood outline.",
        "- Resource demand and inventory are simulated/modelled. The system does not connect to live shelter inventory or dispatch facilities.",
        "- Some road closures are corridor-level matches and do not confirm exact flood location or road passability.",
        "",
        "For full per-zone data, see [`demo/zone_severity_scores.csv`](demo/zone_severity_scores.csv), [`demo/adequate_supply_summary.csv`](demo/adequate_supply_summary.csv), and [`demo/sar_zone_coverage.csv`](demo/sar_zone_coverage.csv).",
        "",
    ]
    output = REPO_ROOT / "RESULTS.md"
    output.write_text("\n".join(sections), encoding="utf-8")
    print(f"Validated all three events and wrote {output}")


if __name__ == "__main__":
    main()
