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

Vite writes the static site to `frontend/dist`. Files in `frontend/public/data` are included under `dist/data` for offline replay. Offline mode is read-only: allocation edits, stock updates, overrides and closure reruns require the API.

From the repository root, run both services with `docker compose up --build`. The frontend image serves the built static assets on port 3000, and the API listens on port 8000. The compose setup uses the image build output and does not require a pre-existing host `frontend/dist` directory.

## Interface notes

- Stock-sensitivity graphs and map coverage previews use precomputed sweep data and are labeled as assumed stock.
- Manual allocation edits are checked against inventory caps and the donor floor and labeled "manual override, not an optimization result".
- Operator-entered inventory is marked unverified and represents pooled stock, not per-shelter routing constraints.
- Map and chart exports are available as PNG; the allocation table can be exported as CSV.
- Login presets are for demonstration only, not production authentication.
