# ResQ: Bantwal relief allocation prototype

ResQ combines Sentinel-1 SAR change context, rainfall, terrain, and population estimates to score response severity and compare simulated relief allocations. The project focuses only on **Bantwal taluk**, split into exactly **16 analytical grid zones**. Every cell is clipped to the Bantwal boundary and checked for valid SAR pixels for all three event dates.

The cells are a regular 4×4 analysis grid, not official village boundaries. Population is a modeled estimate computed by summing WorldPop 2025 constrained 1 km raster pixels inside each cell. The 2011 Census total is kept as a comparison reference only; it does not scale the raster values.

## Six map figures

Each map numbers the 16 grid zones and uses kilometre axes with a 10 km scale bar. Relief-centre names are kept in the legend to avoid covering cell numbers.

The first map for each event shows the SAR candidate signal, all 16 zones, and the Netravati river without roads. The companion map adds cached OpenStreetMap roads and mapped relief-centre locations.

### SAR context, zones, and river

![Bantwal SAR signal, zones, and river - 2019](demo/sar_flood_likelihood_2019-08-10.png)

![Bantwal SAR signal, zones, and river - 2024](demo/sar_flood_likelihood_2024-07-31.png)

![Bantwal SAR signal, zones, and river - 2026](demo/sar_flood_likelihood_2026-08-03.png)

### Roads and mapped relief centres

![Bantwal roads and mapped relief centres - 2019](demo/sar_roads_relief_sites_2019-08-10.png)

![Bantwal roads and mapped relief centres - 2024](demo/sar_roads_relief_sites_2024-07-31.png)

![Bantwal roads and mapped relief centres - 2026](demo/sar_roads_relief_sites_2026-08-03.png)

Only mapped points inside Bantwal appear. The markers show reported locations, not current facility status, capacity, or inventory.

## Severity and allocation

![Severity across the 16 Bantwal zones](demo/zone_severity_scores.png)

![Allocation engine coverage comparison](demo/allocation_engine_coverage.png)

With configured prototype stock, unmet demand is **49.23%, 40.84%, and 42.93%** for the Module 6 static benchmark and **55.49%, 44.69%, and 47.99%** after eight Module 8 rounds, for 2019, 2024, and 2026. These totals are driven by shared inventory caps; the engines can still distribute allocations differently across zones.

A separate simulated-supply scenario yields **1.51%, 7.99%, and 8.01%** unmet demand after eight rounds (and **2.01%, 8.69%, and 8.65%** in its static sensitivity run). These results depend on assumed pooled stock and a 55% minimum service floor; they are not measured inventory or operational outcomes.

See the [zone severity table](demo/zone_severity_scores.csv), [SAR coverage table](demo/sar_zone_coverage.csv), [simulated supply results](demo/adequate_supply_summary.csv), [results](RESULTS.md), [limitations](LIMITATIONS.md), and [demo notes](demo/DEMO_NOTES.md).

## Run the project

Use Python 3.11 or later in PowerShell. Install dependencies, download the official WorldPop raster, then generate the Bantwal boundary and population, run Phase II, and build the demo outputs:

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
python -m resq.zones
python scripts/download_worldpop_raster.py
python -m resq.population
python -m resq.roads
python -m resq.phase2
python -m resq.routing --event-date 2019-08-10
python -m resq.routing --event-date 2024-07-31
python -m resq.routing --event-date 2026-08-03
python -m resq.module8
python scripts/run_supply_target_scenario.py
python demo/build_assets.py
python validation/validate_modules0_9.py
python validation/validate_module11.py
```

The configured raster is WorldPop Global2 R2025A v1 for India, 2025, constrained, 1 km (`1km_ua`). Population pixels are summed by cell without census normalization. The Bantwal polygon sum is 677,985.36 over 674.38 km² (1,005.35 people/km²), or 1.715× the Census 2011 reference of 395,380. This comparison is reported as-is; the result is a modeled estimate, not an updated census count. See [`RESULTS.md`](RESULTS.md) and [`LIMITATIONS.md`](LIMITATIONS.md).

The grid builder fails if any of its 16 cells has no valid SAR pixels in one of the event rasters. Phase II may download Sentinel-1 and CHIRPS inputs when they are not cached. Shelter stock and resource demand are modeled; the project has no live shelter inventory or dispatch service. The future interface could let authorized shelter officials enter actual stock for allocation.

## Run the API

The FastAPI prototype wraps the static allocator, Module 7 routing, and Module 8/9 closure benchmark. Its routes cover events, zones, simulation, applying a verified closure, allocations, routes, and escalations. It serves Bantwal's 16 zones and three configured historical event records. `/events` works without the spatial cache; zones, allocation, and closure operations need generated artifacts from the pipeline commands above. Most `data/processed` files are intentionally git-ignored. It is a local research backend, not a complete operational service: authentication, a frontend, live shelter inventory, dispatch integration, and multi-worker job isolation are not implemented.

```powershell
python -m pip install -e ".[phase2,geo]"
uvicorn resq.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the interactive API schema. Example requests:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/events
Invoke-RestMethod "http://127.0.0.1:8000/zones?event=2019-08-10"
Invoke-RestMethod -Method Post http://127.0.0.1:8000/simulate `
  -ContentType "application/json" `
  -Body '{"event":"2019-08-10","engine":"MILP","stock_mode":"configured"}'
```

Use `stock_mode: "simulated"` only to run the separately labeled pooled-stock assumption. All stock modes are assumed inventory, never live facility stock. `/closures` accepts a verified closure ID from that event's closure GeoJSON, runs Module 8 and reroutes all 16 zones with Module 7. Module 8 and Module 7 consume all verified closures in that event file. Run, selected-engine allocations/escalations, and per-zone route outputs are persisted in `data/processed/resq_service.sqlite3`; fetch the routes with `GET /routes/{run_id}`.

Docker Compose can run the same API against a locally generated data cache. Generate the ignored road graph, analysis zones, event features, and closure files with the pipeline commands above first; mount them at `data/processed` as the Compose file does. Then run:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

Stop the service with `docker compose down`. The simulated-stock scenario CSV is included in the image; generated spatial artifacts and the SQLite database stay in the host `data/processed` folder. If the road graph is absent, the API still starts and `/events` responds, while closure/routing work returns `503 road_graph_unavailable` until the cache is generated. Docker Compose was built and smoke-tested locally: `/events` returned all three events, `/zones` returned 16 zones, and a simulated allocation followed by a verified-closure request returned eight steps and 16 Module 7 route rows. Architecture and API contracts: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### System design diagrams

![ResQ layered architecture](demo/architecture_layers.png)

![ResQ data flow](demo/data_flow.png)

![Verified closure response sequence](demo/closure_sequence.png)

To run API tests after installing the development extra:

```powershell
python -m pip install -e ".[dev]"
python -m pytest --basetemp=.pytest-tmp tests
```

On the current checked-out data, the API suite passes all 6 tests and the Modules 0-9 validator suite passes for the three event dates. Module 7 computes a road route or secondary-distance candidate for all 16 zones in each event; its event-data status remains partial because some reported closure labels are unresolved.

The scaling benchmark uses generated workload rows and is not a disaster outcome:

![Allocator runtime benchmark](demo/scaling_benchmark.png)

```powershell
python validation/scaling_benchmark.py
```
