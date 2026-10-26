# Limitations

- The 16 zones are regular analytical grid cells clipped to Bantwal, not official village boundaries. Population is split by cell area, assuming uniform density within the taluk.
- Sentinel-1 is used as candidate VH-change context for severity. The project does not establish a validated flood outline.
- Severity, affected population, and resource demand are estimates. Historical event reports and synthetic model augmentation do not provide observed demand for each grid cell.
- Relief-centre locations come from cached public map or event-report sources. Facility stock, capacity, and operational status are simulated or unknown.
- The road graph is from OpenStreetMap. Some closure matches are broad highway corridors rather than exact flood points; a routed path does not establish that a road was passable during an event.
- Allocation and disruption results depend on assumed inventory and demand. The near-adequate stock example is a sensitivity scenario with a 55% minimum service floor, not a real-world performance claim.
- Each event is one dated input followed by eight simulated disruption steps. This is not an operational timeline; the 2024 impact peaks are not separate model runs.
