# ResQ results - Bantwal

ResQ uses Sentinel-1 SAR context, rainfall, terrain, and population estimates to score severity in 16 Bantwal analysis zones and compare relief-allocation policies. The focus is Bantwal taluk only.

## Zones and population

The analysis uses exactly 16 regular grid cells clipped to the Bantwal taluk polygon. Every cell contains valid SAR pixels on all three event dates. These are analytical zones, not official village or ward boundaries; the six maps show the same zone layer.
Zone population is a modeled estimate from WorldPop Global2 R2025A v1 India (2025, constrained, 1 km), computed by summing native population-count pixels per cell without Census scaling. The Bantwal polygon sum is 677,985.36 across 674.38 km² (1,005.35 people/km²). The Census 2011 reference is 395,380; the raster estimate is 1.715× that value. The difference is reported without adjustment.

## Event and allocation results

| Event | Gauge stage | SAR before → during | Module 6 configured unmet | Module 8 configured unmet after 8 rounds | Module 8 simulated-stock unmet |
|---|---:|---|---:|---:|---:|
| 2019-08-10 | 11.6 m | 2019-07-22 to 2019-08-10 | 49.23% | 55.49% | 1.51% (static sensitivity 2.01%) |
| 2024-07-31 | 9.3 m | 2024-07-13 to 2024-08-06 | 40.84% | 44.69% | 7.99% (static sensitivity 8.69%) |
| 2026-08-03 | 8.5 m | 2026-07-10 to 2026-08-03 | 42.93% | 47.99% | 8.01% (static sensitivity 8.65%) |

### Minimum zone coverage by engine

| Event | Module 6 static floor (MILP / LinUCB / Proportional) | Module 8 final floor (MILP) | Module 8 final floor (LinUCB) | Module 8 final floor (Proportional) |
|---|---:|---:|---:|---:|
| 2019-08-10 | 19.61% / 19.61% / 19.61% | 13.35% | 0.09% | 13.35% |
| 2024-07-31 | 29.05% / 29.05% / 29.05% | 24.72% | 0.30% | 24.72% |
| 2026-08-03 | 26.71% / 26.71% / 26.71% | 18.18% | 0.94% | 18.18% |

The static 40% fairness target is infeasible under configured stock, so Module 6 uses the maximum feasible common floor and the three engines tie on minimum coverage. During Module 8, LinUCB's learned reward allocation leaves a zone near zero coverage, while MILP and Proportional retain a higher floor. This is a distribution/equity effect under modeled scarcity; aggregate unmet demand remains similar because stocks are shared.

The configured-stock results show how the current prototype inventory limits service. The separate simulated-stock sensitivity assumes a larger pooled supply and a 55% minimum zone-service floor; it is a scenario, not measured shelter inventory or an observed outcome.
All engines use the same total demand and inventory caps, so aggregate unmet demand can be similar even when the distribution across zones differs. Compare the per-zone Module 6 charts and Module 8 minimum-coverage traces; equal totals do not mean identical allocations.

## Demo figures

The six maps show the candidate SAR signal, 16 Bantwal grid boundaries, and Netravathi river; three companion maps add cached OSM roads and mapped relief-centre locations.

| Figure | Description |
|---|---|
| [`zone_severity_scores.png`](demo/zone_severity_scores.png) | Zone severity by event |
| [`allocation_engine_coverage.png`](demo/allocation_engine_coverage.png) | Mean zone/resource coverage by engine |
| [`supply_sensitivity_unmet_demand.png`](demo/supply_sensitivity_unmet_demand.png) | Configured stock and simulated-stock scenario |
| [`module6_static_zone_coverage_2024-07-31.png`](demo/module6_static_zone_coverage_2024-07-31.png) | Static per-zone coverage example |
| [`module8_minimum_coverage_steps_2024-07-31.png`](demo/module8_minimum_coverage_steps_2024-07-31.png) | Eight-step minimum-coverage example |

## Module 7 routing coverage

Module 7 computes a route or explicitly marked secondary-distance candidate for each of the 16 Bantwal grid zones after applying verified event closure geometries. PARTIAL PASS means some closure labels remain unresolved; it does not mean zone routes are missing. Secondary distance is straight-line context only, not evidence of a navigable water or air route.

| Event | Zones | Road routes | Secondary candidates | No eligible mode | Directed edges removed | Unresolved closure labels |
|---|---:|---:|---:|---:|---:|---:|
| 2019-08-10 | 16 | 15 | 1 | 0 | 35 | 2 |
| 2024-07-31 | 16 | 15 | 1 | 0 | 35 | 2 |
| 2026-08-03 | 16 | 15 | 1 | 0 | 35 | 2 |

## Modules 0-9 validator status

Global input checks (Modules 0-3) are repeated across event columns; event-level outputs are validated independently.

| Module | 2019-08-10 | 2024-07-31 | 2026-08-03 |
|---|---|---|---|
| Module 0 | PASS (global) | PASS (global) | PASS (global) |
| Module 1 | PASS (global) | PASS (global) | PASS (global) |
| Module 2 | PASS (global) | PASS (global) | PASS (global) |
| Module 3 | PASS (global) | PASS (global) | PASS (global) |
| Module 4 | PASS | PASS | PASS |
| Module 5 | PASS | PASS | PASS |
| Module 6 | PASS | PASS | PASS |
| Module 7 | PASS (partial) | PASS (partial) | PASS (partial) |
| Module 8 | PASS | PASS | PASS |
| Module 9 | PASS | PASS | PASS |

Module 10 is not implemented in the checked-in source or validators. Module 11 is the report-generation/big-three validation script.

Machine-readable details: `data/processed/validation_modules0_9.csv`.

## Sources and limits

- The 16 analytical zones are regular grid cells clipped to the cached Bantwal taluk polygon; they are not administrative units.
- Bantwal population is estimated using unadjusted WorldPop 2025 constrained 1 km raster pixel sums: 677,985.36 across 674.38 km² (1,005.35 people/km²). The Census 2011 total (395,380) remains config-only as a labeled reference; the ratio is 1.715×.
- SAR is shown as a candidate VH-change signal for severity context, not a verified flood outline.
- Resource demand and inventory are simulated/modelled. The system does not connect to live shelter inventory or dispatch facilities.
- Some road closures are corridor-level matches and do not confirm exact flood location or road passability.

For full per-zone data, see [`demo/zone_severity_scores.csv`](demo/zone_severity_scores.csv), [`demo/adequate_supply_summary.csv`](demo/adequate_supply_summary.csv), and [`demo/sar_zone_coverage.csv`](demo/sar_zone_coverage.csv).
