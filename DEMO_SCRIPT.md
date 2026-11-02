# ResQ: Presenter Demo Script (Module 10)

This script outlines the ordered click path and spoken talking points for presenting the ResQ Bantwal flood response dashboard.

---

## Pre-Flight Checklist
1. Ensure frontend dependencies are built (`npm run build` in `/frontend`).
2. Run preview or dev server (`npm run preview` on port 5173).
3. If running live, start FastAPI server (`python -m uvicorn resq.api:app --port 8000`). If backend is offline, the dashboard automatically transitions to the precomputed **Offline Demo Mode**.
4. Screen resolution recommended: 1920×1080 or 1366×768.

---

## Presentation Walkthrough (Step-by-Step)

### Step 1: Landing Page & Analytical Context
- **Action**: Open [http://localhost:5173](http://localhost:5173).
- **Visuals**: Observe the dark ink command-centre aesthetics (`#060A12`), ambient `Aurora` fluid background, staggered `BlurText` title, and flowing `GradientText` tagline.
- **Talking Points**:
  - *"Welcome to ResQ. Notice right away that this app is labeled 'Replay of three documented flood events'—there are no fake 'LIVE' badges or fabricated real-time figures."*
  - *"Observe the violet chip in the header: 'Assumed inventory, replay only'. Every inventory figure and allocation outcome derives from transparently documented assumptions."*
  - Point out the 5 `SpotlightCard` stat chips: 3 Flood Events (2019, 2024, 2026), 16 Analytical Grid Zones, 3 Allocation Engines, 8 Disruption Steps, and 100% Routed Grid (15 road + 1 secondary candidate).

---

### Step 2: Role-Based Access Control (Authentication Gate)
- **Action**: Click the glowing **"Launch Command Console"** `StarBorder` button.
- **Visuals**: The glass login card appears with demo role presets.
- **Talking Points**:
  - *"ResQ implements demo-level authentication with two roles: viewer and operator. As clearly disclosed on the card, this is presentation-level security, not production infrastructure."*
- **Click**: Click the **"Viewer"** preset button (`viewer` / `viewer2026`), then click **"Enter Command Console"**.
- **Visuals**: The console loads. Note the header user chip shows `Viewer` (read-only).
- **Highlight**: Hover over the **"Trigger Closure"** button in the timeline—notice it is disabled with the tooltip: *"Operator role required to trigger corridor closures"*.

---

### Step 3: Main Command Console & Hydrological Context
- **Visuals**: Full-screen dark map (`MapLibre GL` with `deck.gl`), left event selector rail, bottom step timeline, and top-right inventory meters.
- **Talking Points**:
  - *"On the left rail, we can select between the three documented monsoon events: August 2019, July 2024, and August 2026."*
  - *"Notice the vertical river water-level gauge: it visualizes the recorded gauge peak against the official Central Water Commission (CWC) 9.0-metre danger mark. In the 2024 event, flood waters peaked at 9.30 m, crossing into danger territory."*

---

### Step 4: 16 Analytical Grid Cells & Map Layers
- **Action**: Hover and pan over the 16 grid cells on the map.
- **Visuals**: Cell polygons filled by modeled relative priority using the map severity ramp:
  - Teal (`#2DD4BF`) = Low priority
  - Yellow (`#FDE047`) = Medium priority
  - Coral (`#FB7185`) = High priority
- **Talking Points**:
  - *"Bantwal Taluk is divided into exactly 16 analytical grid cells. Cell boundaries are analytical units, not municipal administrative wards."*
  - *"Severity is designated as 'modeled relative priority'—a multi-criteria synthesis of candidate SAR signals, 7-day antecedent rainfall, terrain HAND context, and population estimates."*
- **Action**: In the bottom `Dock` layer bar, toggle the **"SAR Signal"** button.
- **Talking Points**:
  - *"Honesty rule: Copernicus Sentinel-1 RTC backscatter change is designated as 'candidate VH-change signal', never 'flood extent'. This accounts for backscatter variations from saturated soils and vegetation."*

---

### Step 5: Zone Deep-Dive (Right Drawer)
- **Action**: Click on high-severity cell **`Zone 12`** (`Bantwal_Z12`) or **`Zone 10`**.
- **Visuals**: The right drawer slides open with frosted glass elevation.
- **Talking Points**:
  - *"Clicking a zone reveals its severity ring and population. Notice the population label: 'WorldPop modeled estimate' (sum of 2025 building-constrained 1 km raster pixels)."*
  - *"Resource need is broken down by Food rations, Water liters, and Medical kits. We can inspect the allocation per engine and the route distance from the designated base depot."*
  - *"Notice the administrative boost section: for the viewer role, it explains that operator privileges are required to override allocations."*

---

### Step 6: Assumed Inventory & Critical Threshold Meter
- **Action**: Direct attention to the top-right **Inventory Panel**.
- **Visuals**: Capsule meters for Food, Water, and Medical supplies with animated numeric `CountUp`.
- **Talking Points**:
  - *"Every inventory meter displays the violet ASSUMED chip. A distinct marker is placed at the 20% stock-to-unmet-demand threshold."*
  - *"As supplies deplete across operational rounds, dropping below 20% triggers a pulsing alert state to signal imminent regional exhaustion."*

---

### Step 7: Step Timeline, Road Closures & Route Morphing
- **Action**: Look at the bottom **Step Timeline** (Module 8 benchmark).
- **Visuals**: 8 sequential disruption steps with Play/Pause, Step Next/Prev, and 0.5x/1x/2x playback speed. A distinct red marker sits at Step 2 indicating where the road closure applies.
- **Talking Points**:
  - *"Module 8 evaluates allocation resilience across 8 progressive operational steps under simulated demand evolution."*
  - *"At step 2, a verified corridor-level closure occurs along the critical BC Road - Jakribettu highway corridor."*
- **Action**: Click **Step 2** or click **Play**.
- **Visuals**: The closure alert activates (`CLOSURE ACTIVE`). On the map, the closed highway flashes red, and delivery routes dynamically morph into detour paths.
- **Talking Points**:
  - *"Normal routes flow with glowing cyan particles (`#22D3EE`). Recomputed detours shift routes to safe corridors. For isolated zones without verified road access, an unverified secondary route candidate is rendered as a dotted violet arc labeled 'unverified'."*

---

### Step 8: Comparative Multi-Engine Evaluation (Compare View)
- **Action**: Click the **"Compare"** button in the top navigation bar.
- **Visuals**: The full-screen Compare drawer opens featuring:
  1. **Interactive Swipe Slider Map**: Drag left/right to compare OR-Tools MILP vs. LinUCB allocations.
  2. **16-Zone Small Multiples**: Side-by-side coverage bars across all 16 cells.
  3. **Minimum Zone Coverage Chart**: Animated line drawing comparing MILP (`#60A5FA`), LinUCB (`#FB923C`), and Proportional (`#4ADE80`).
  4. **Bento Grid**: Aggregate unmet demand, Gini fairness coefficient, and solver solve times.
- **Talking Points**:
  - *"The OR-Tools MILP engine guarantees hard minimum-zone coverage floors, preventing any single zone from being abandoned. In contrast, greedy or proportional baselines exhibit severe coverage collapse under supply stress."*
- **Action**: Click **Close** or press **Esc**.

---

### Step 9: Module 9 Shortage Escalations & Transfer Arcs
- **Action**: Click the **"Alerts"** button in the top navigation bar.
- **Visuals**: The `EscalationModal` opens with animated `DecryptedText` decoding header and `AnimatedList` feed.
- **Talking Points**:
  - *"When local stock cannot meet urgent demand, Module 9 triggers shortage alerts and computes donor-to-recipient reallocations."*
  - Point to the animated reallocation cards showing donor zones transferring surplus rations to recipient zones.
- **Action**: Close the modal.

---

### Step 10: System Architecture & Guided Walkthrough Mode
- **Action**: Click the **"Projector"** button in the header.
  - *"Notice the high-contrast projector mode with enhanced text contrast (exceeding 7:1) and scaled typography for conference room displays."*
- **Action**: Click the **"Guided Walkthrough"** button.
  - *"For presentations, the built-in Stepper mode can be advanced with the Left and Right arrow keys on the presenter's keyboard."*
- **Action**: Click the **"About"** (info) button.
  - *"Here we clearly document all primary data sources (Sentinel-1 SAR, CHIRPS, WorldPop, OSM, CWC), methodological limitations, the Implemented vs. Planned matrix, and React Bits component attribution."*

---

## End of Presentation Click Path
```
Landing -> Launch Console -> Viewer Login -> Map & River Gauge -> Zone 12 Click ->
Timeline Step 2 (Closure) -> Compare Swipe Slider -> Escalations Feed -> Projector Mode -> Logout
```
