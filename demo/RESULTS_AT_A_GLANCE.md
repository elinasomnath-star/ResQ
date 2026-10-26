# ResQ at a glance

ResQ models severity and relief allocation for three Netravati flood events. The analysis is restricted to Bantwal taluk, split into 16 regular grid zones clipped within the taluk boundary.

## Configured-stock benchmark

| Event | Module 6 unmet demand | Module 8 unmet demand after 8 steps |
|---|---:|---:|
| 2019-08-10 | 49.05% | 54.00% |
| 2024-07-31 | 40.61% | 44.49% |
| 2026-08-03 | 42.85% | 47.47% |

All engines share the same aggregate inventory caps, so aggregate unmet demand can match. Their allocation patterns and minimum zone coverage differ; the zone charts show those differences.

## Simulated near-adequate supply sensitivity

This separate scenario assumes larger synthetic stocks and a 55% minimum service floor. It results in about 1.50% unmet demand for 2019 and 8.01% for 2024 and 2026. These values are scenario outputs, not actual inventory or real-world results.

![Bantwal zones, candidate SAR signal, and Netravati river](sar_flood_likelihood_2024-07-31.png)

![Bantwal roads and mapped relief centres](sar_roads_relief_sites_2024-07-31.png)

![Modeled severity by Bantwal zone](zone_severity_scores.png)

![Per-zone allocation coverage](allocation_engine_coverage.png)

For complete numbers, see [results](../RESULTS.md) and [limitations](../LIMITATIONS.md).
