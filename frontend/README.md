# ResQ Frontend

The React, TypeScript and Vite interface is a local decision-support dashboard for the Bantwal 16-zone study area. It uses MapLibre for cached road, river, zone, facility and route layers, plus React Bits components for visual interactions.

## Local development

From the repository root, prepare frontend snapshots when needed:

```powershell
python scripts/export_frontend_data.py
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Start the API separately at `http://127.0.0.1:8000` for simulations, closure rerouting, facility stock edits and manual allocation overrides. CORS allows the local Vite and static-preview origins on ports 5173 and 3000.

## Static build and Docker

```powershell
cd frontend
npm run build
npm run preview
```

Vite writes the static site to `frontend/dist`. Files in `frontend/public/data` are included under `dist/data` for read-only replay without the API. Allocation edits/reruns, stock updates, overrides, and live road rerouting require the API. This is not a PWA or an installable offline package; serve the static build locally. Google Fonts are remote and fall back to system fonts without internet access.

From the repository root, run both services with `docker compose up --build`. The frontend image serves the built static assets on port 3000, and the API listens on port 8000. The browser calls `http://127.0.0.1:8000`, so Compose is intended for a browser on the same host; it has no remote-host/TLS setup. The API mounts host `data/processed`; generate the spatial artifacts before using live maps, allocation, or route operations. The Compose health check checks `/events` only, not those artifacts or live routing. The frontend image builds from source and does not require a host `frontend/dist`.

## Browser checks and screenshots

With the API and cached Bantwal road graph running, use `npx playwright test` from this directory to run the browser checks. The `Refresh current ResQ interface screenshots` test updates the UI captures in `../demo/`; run it with `npx playwright test e2e/screenshots.spec.ts -g "Refresh current ResQ interface screenshots"`.

The road scenario deck data and map geometry come from `config/bantwal_road_scenarios.json`. After editing these road definitions, regenerate the frontend data with `python scripts/export_bantwal_road_scenarios.py` from the repository root. The deck currently contains three single-road cases plus two simultaneous multi-road cases (two roads and three roads).

## Interface notes

- Stock-sensitivity graphs and map coverage previews use precomputed sweep data and are labeled as assumed stock.
- In online mode, the selected 10–150% stock-sensitivity value is applied to each resource's event-specific modeled need when an allocation is run; the returned pool totals are used by the console. Offline snapshots and operator-entered stock remain fixed, so the percentage control is disabled in those modes.
- Manual allocation edits are checked against inventory caps and the donor floor and labeled "manual override, not an optimization result".
- Operator-entered inventory is marked unverified and represents pooled stock, not per-shelter routing constraints.
- Map and chart exports are available as PNG; the allocation table can be exported as CSV.
- Login presets are for demonstration only, not production authentication.
