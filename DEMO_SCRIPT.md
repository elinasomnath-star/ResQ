# ResQ presenter demo

This walkthrough describes the current Bantwal dashboard. The interface replays three documented flood events and uses modeled demand and assumed inventory; it is a decision-support prototype, not a live dispatch system.

## Before the demo

1. Build and serve the frontend from `frontend` with `npm ci`, `npm run build`, then `npm run preview`.
2. For live simulation and routing, start the API from the repository root with `python -m uvicorn resq.api:app --host 127.0.0.1 --port 8000`.
3. Without the API, the frontend uses checked-in read-only snapshots and local Bantwal map data. Allocation changes, stock edits, overrides, and live road-blockage rerouting require the API and generated spatial artifacts. The static app is not an installable offline package; Google Fonts fall back when internet access is unavailable.
4. Use the demo Operator preset only for features that modify state; Viewer is sufficient for inspection.

## Walkthrough

1. **Introduce the map.** ResQ focuses on Bantwal Taluk, represented by 16 analytical grid zones. These are not administrative ward boundaries. The gauge uses an 8.0 m warning level and a 9.0 m danger level.
2. **Explain the map layers.** Zone colors show modeled relative priority. SAR is a candidate VH-change signal, not a confirmed flood outline. Roads, river, and facility points come from cached datasets.
3. **Inspect a zone.** Select a zone marker to open its details and inspect modeled needs, allocation, and route. A road route uses A* on the cached road graph; a secondary-distance candidate is labeled separately.
4. **Compare allocation engines.** Use Compare to view MILP, LinUCB, and Proportional results. They share the event demand and selected stock pool but use different allocation methods. In online configured-stock mode, the stock percentage sets each resource pool as a percentage of that event's modeled need. Offline snapshots and entered inventory do not use that slider.
5. **Show the road scenarios.** As Operator, open Scenarios. The deck includes three single-road scenarios plus simultaneous two-road and three-road failures, all using mapped trunk or primary roads inside Bantwal. Every failed road appears in red with its closure marker, and the live API recalculates routes for all 16 zones against the cached graph. Scenarios that block the Netravati Bridge include Mini Town Hall, Mangaluru, as a visible routing origin. This is route-only and does not recalculate allocations. Click zones after recalculation to inspect their route results.
6. **Distinguish verified closure data.** The backend also supports documented event closures for replay workflows. The frontend Scenario Deck exposes five controlled road-blockage what-if scenarios; they are not presented as observed event closures and do not alter allocation results.
7. **Review inventory and constraints.** Shelter stocks are assumed or operator-entered, unverified values. Manual allocation changes are explicitly labeled as overrides rather than optimizer results. The About panel summarizes sources and limitations.

## Key points for comparison

- The three allocation engines are intentionally different algorithms, not interchangeable labels. Compare their zone-level coverage, unmet demand, and fairness under the same event and stock pool.
- The road-blockage scenarios use one blocked corridor per run and route around it where the graph provides an alternate path. The blocked road is excluded from the route search, including nearby graph edges in the closure buffer.
- All routes and road layers rely on the cached OSM graph; the app does not request live OSM routing data.
- The gauge and event data are historical replays. No live gauge, facility telemetry, or dispatch integration is implied.
