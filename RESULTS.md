# ResQ results - Bantwal

ResQ uses Sentinel-1 SAR context, rainfall, terrain, and population estimates to score severity in 16 Bantwal analysis zones and compare relief-allocation policies. The focus is Bantwal taluk only.

## Zones and population

The analysis uses exactly 16 regular grid cells clipped to the Bantwal taluk polygon. Every cell contains valid SAR pixels on all three event dates. These are analytical zones, not official village or ward boundaries; the six maps show the same zone layer.
Zone population values are area-weighted shares of the Bantwal parent estimate (682,789), assuming uniform density within the taluk. They are a spatial proxy, not measured population counts for the individual zones.

## Event and allocation results

| Event | Gauge stage | SAR before → during | Module 6 configured unmet | Module 8 configured unmet after 8 rounds | Module 8 simulated-stock unmet |
|---|---:|---|---:|---:|---:|
| 2019-08-10 | 11.6 m | 2019-07-22 to 2019-08-10 | 49.05% | 54.00% | 1.50% (static sensitivity 2.02%) |
| 2024-07-31 | 9.3 m | 2024-07-13 to 2024-08-06 | 40.61% | 44.49% | 8.01% (static sensitivity 8.73%) |
| 2026-08-03 | 8.5 m | 2026-07-10 to 2026-08-03 | 42.85% | 47.47% | 8.01% (static sensitivity 8.66%) |

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

## Modules 0–9 validation

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
- The Bantwal parent population estimate is split by zone area because a sub-taluk population raster is not available. Density variation within Bantwal is not represented.
- SAR is shown as a candidate VH-change signal for severity context, not a verified flood outline.
- Resource demand and inventory are simulated/modelled. The system does not connect to live shelter inventory or dispatch facilities.
- Some road closures are corridor-level matches and do not confirm exact flood location or road passability.

For full per-zone data, see [`demo/zone_severity_scores.csv`](demo/zone_severity_scores.csv), [`demo/adequate_supply_summary.csv`](demo/adequate_supply_summary.csv), and [`demo/sar_zone_coverage.csv`](demo/sar_zone_coverage.csv).
