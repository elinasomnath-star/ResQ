# Demo notes

The maps cover Bantwal taluk, divided into exactly 16 analytical grid zones clipped to its boundary. Each is checked for valid SAR pixels for the three events. Sentinel-1 is shown as a candidate VH-change signal used for severity context.

## Six map figures

### SAR, zones, and river (no road overlay)

- [2019-08-10](sar_flood_likelihood_2019-08-10.png): Shows the candidate SAR signal and the 16 clipped zones, with the Netravati river for geographic context.
- [2024-07-31](sar_flood_likelihood_2024-07-31.png): Uses the same Bantwal extent and zone boundaries for the mid-size event; the river helps locate the zones relative to the main drainage.
- [2026-08-03](sar_flood_likelihood_2026-08-03.png): Shows the latest event's candidate signal within the same fixed focus boundary for comparison.

### OSM roads and relief centres

- [2019-08-10](sar_roads_relief_sites_2019-08-10.png): Adds the cached local and major OSM roads to the 2019 map, plus mapped relief-centre points inside Bantwal.
- [2024-07-31](sar_roads_relief_sites_2024-07-31.png): Shows how the same road network and in-taluk facilities relate to the 2024 signal and analysis zones.
- [2026-08-03](sar_roads_relief_sites_2026-08-03.png): Provides the equivalent network context for the 2026 event. Road lines are OSM geometry, not verified passability during the flood.

Only mapped facilities inside Bantwal are drawn. Mini Town Hall is in Mangaluru, outside the map focus; the SVS and Panemangaluru markers are mapped location candidates, not proof of available stock or capacity.

## Severity and allocation figures

- [Zone severity table](zone_severity_scores.png) and [CSV](zone_severity_scores.csv): Lists each analytical zone's modeled severity for the three events. SAR, rainfall, HAND, population, and demand are inputs or estimates, not measured impacts.
- [Per-zone coverage comparison](allocation_engine_coverage.png): Compares mean resource coverage for Module 6 static and Module 8 eight-round allocation under an explicitly simulated near-adequate stock scenario. The aggregate unmet percentages can be the same because engines share stock caps; the per-zone distribution and minimum coverage show policy differences.
- [Module 6 per-zone bars](module6_static_zone_coverage_2024-07-31.png): Shows the three engines' resource coverage across individual Bantwal zones for the 2024 event.
- [Module 8 minimum coverage trace](module8_minimum_coverage_steps_2024-07-31.png): Shows how the least-served zone changes over eight simulated steps for the 2024 case.
- [Supply sensitivity](supply_sensitivity_unmet_demand.png) and [scenario CSV](adequate_supply_summary.csv): Separates configured prototype stock from a simulated near-adequate supply assumption with a 55% minimum service floor.
- [Simulated relief-centre stock](simulated_relief_centre_inventory.csv): Illustrative stock split only; the allocators use a pooled inventory and do not enforce depot capacity or travel limits.

## Four main limitations to mention

1. The zones are 16 analytical grid cells, and population is apportioned by area because sub-taluk population counts are unavailable.
2. SAR is candidate change context, not a validated flood outline.
3. Shelter stocks and demand are simulated/modelled; no live facility inventory is connected.
4. OSM roads and closure matches have coverage gaps; closure corridors do not prove real-time road access.

For the cached route walkthrough, run `python demo/run_demo.py 2024-07-31` from the project root.
