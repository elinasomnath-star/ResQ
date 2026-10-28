"""Create presentation PNGs and a summary CSV from cached Phase II outputs."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "resq-matplotlib-cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import networkx as nx
import rasterio
from shapely import transform as shapely_transform
from rasterio.errors import WindowError
from rasterio.features import geometry_mask, geometry_window
from rasterio.windows import transform as window_transform
from rasterio.warp import transform_geom
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
SIMULATED = PROCESSED / "simulated_coverage_scenario"
OUT = ROOT / "demo"
EVENTS = ["2019-08-10", "2024-07-31", "2026-08-03"]
ENGINES = ["MILP", "LinUCB_contextual_bandit", "naive_proportional_baseline"]
ENGINE_LABELS = {
    "MILP": "MILP",
    "LinUCB_contextual_bandit": "LinUCB",
    "naive_proportional_baseline": "Proportional",
}
COLORS = {"MILP": "#2463a6", "LinUCB": "#e1812c", "Proportional": "#3a9d74"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def full_zone_bounds(zones: list[dict], crs: str) -> tuple[float, float, float, float]:
    projected = [shape(transform_geom("EPSG:4326", crs, feature["geometry"])) for feature in zones]
    bounds = [geometry.bounds for geometry in projected]
    return (min(item[0] for item in bounds), min(item[1] for item in bounds),
            max(item[2] for item in bounds), max(item[3] for item in bounds))


def build_sar_zone_coverage() -> dict[str, dict[str, dict[str, object]]]:
    """Count valid SAR pixels within each Bantwal grid zone."""
    zones = json.loads((PROCESSED / "analysis_zones.geojson").read_text(encoding="utf-8"))["features"]
    rows = []
    coverage: dict[str, dict[str, dict[str, object]]] = {}
    for day in EVENTS:
        coverage[day] = {}
        with rasterio.open(PROCESSED / f"flood_likelihood_{day}.tif") as ds:
            for feature in zones:
                props = feature.get("properties", {})
                zone_id = str(props.get("zone_id", ""))
                name = str(props.get("name", zone_id))
                geom = transform_geom("EPSG:4326", ds.crs, feature["geometry"])
                zone_pixels = valid_pixels = 0
                try:
                    window = geometry_window(ds, [geom])
                    inside = geometry_mask([geom], out_shape=(int(window.height), int(window.width)),
                                           transform=window_transform(window, ds.transform),
                                           invert=True, all_touched=False)
                    valid = ds.read_masks(1, window=window) > 0
                    zone_pixels = int(inside.sum())
                    valid_pixels = int((inside & valid).sum())
                except WindowError:
                    pass
                pixel_pct = 100.0 * valid_pixels / zone_pixels if zone_pixels else 0.0
                status = "covered" if valid_pixels else "no_valid_sar_pixels"
                item = {"event_date": day, "zone_id": zone_id, "zone_name": name,
                        "zone_type": str(props.get("zone_type", "")),
                        "raster_pixel_count_in_zone": zone_pixels,
                        "valid_sar_pixel_count": valid_pixels,
                        "zone_pixels_with_valid_sar_pct": round(pixel_pct, 4),
                        "coverage_status": status}
                rows.append(item)
                coverage[day][zone_id] = item
    with (OUT / "sar_zone_coverage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return coverage


def draw_module8_zone_boundaries(ax: plt.Axes, zones: list[dict], crs: str,
                                 coverage_by_id: dict[str, dict[str, object]]) -> None:
    for feature in zones:
        props = feature.get("properties", {})
        zone_id = str(props.get("zone_id", ""))
        zone_coverage = coverage_by_id.get(zone_id, {})
        has_data = int(zone_coverage.get("valid_sar_pixel_count", 0)) > 0
        geom = transform_geom("EPSG:4326", crs, feature["geometry"])
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for polygon in polygons:
            for ring in polygon[:1]:
                xy = np.asarray(ring)
                ax.plot(xy[:, 0], xy[:, 1], color="#15806c" if has_data else "#bd486b",
                        linewidth=0.65 if has_data else 0.75,
                        linestyle="-" if has_data else "--", alpha=0.9, zorder=6)


def render_heatmap(day: str, sar_coverage: dict[str, dict[str, object]]) -> None:
    render_bantwal_map(day, sar_coverage, with_roads=False)


def _line_parts(geometry: object) -> list[list[tuple[float, float]]]:
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [[(float(x), float(y)) for x, y in geometry.coords]]
    if geometry.geom_type in {"MultiLineString", "GeometryCollection"}:
        return [part for child in geometry.geoms for part in _line_parts(child)]
    return []


def _road_segments(parent_wgs: object, crs: str) -> tuple[list[list[tuple[float, float]]], list[list[tuple[float, float]]]]:
    graph = nx.read_graphml(PROCESSED / "road_graph.graphml")
    minx, miny, maxx, maxy = parent_wgs.bounds
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    local, major = [], []
    seen: set[tuple[str, str]] = set()
    for u, v, data in graph.edges(data=True):
        edge_key = tuple(sorted((str(u), str(v))))
        if edge_key in seen:
            continue
        seen.add(edge_key)
        raw = data.get("geometry")
        try:
            coords = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            coords = None
        if not coords:
            first, second = graph.nodes[u], graph.nodes[v]
            coords = [[float(first["lon"]), float(first["lat"])],
                      [float(second["lon"]), float(second["lat"])]]
        if len(coords) < 2:
            continue
        xs = [float(point[0]) for point in coords]
        ys = [float(point[1]) for point in coords]
        if max(xs) < minx or min(xs) > maxx or max(ys) < miny or min(ys) > maxy:
            continue
        clipped = LineString(coords).intersection(parent_wgs)
        for part in _line_parts(clipped):
            px, py = transformer.transform([p[0] for p in part], [p[1] for p in part])
            (major if any(kind in str(data.get("highway", "")).casefold()
                          for kind in ("primary", "secondary", "trunk")) else local).append(list(zip(px, py)))
    return local, major


def render_bantwal_map(day: str, sar_coverage: dict[str, dict[str, object]], *, with_roads: bool) -> None:
    parent_features = json.loads((PROCESSED / "zones.geojson").read_text(encoding="utf-8"))["features"]
    zones = json.loads((PROCESSED / "analysis_zones.geojson").read_text(encoding="utf-8"))["features"]
    parent_wgs = shape(parent_features[0]["geometry"])
    river_doc = json.loads((ROOT / "data" / "raw" / "osm_netravati_river_relation_3415326.geojson").read_text(encoding="utf-8"))
    river = shape(river_doc["features"][0]["geometry"]).intersection(parent_wgs)
    with rasterio.open(PROCESSED / f"flood_likelihood_{day}.tif") as ds:
        focus_geometry = transform_geom("EPSG:4326", ds.crs, parent_features[0]["geometry"])
        in_zone = geometry_mask([focus_geometry], out_shape=(ds.height, ds.width),
                                transform=ds.transform, invert=True, all_touched=False)
        source = ds.read(1, masked=True)
        image = np.ma.array(source.data, mask=np.ma.getmaskarray(source) | ~in_zone)
        bounds = ds.bounds
        raster_extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
        crs = str(ds.crs)
    left, bottom, right, top = full_zone_bounds(parent_features, crs)
    fig, ax = plt.subplots(figsize=(10.5, 8.5))
    shown = ax.imshow(image, cmap="Blues", vmin=0, vmax=1, extent=raster_extent, origin="upper", zorder=1)
    river_projected = shapely_transform(
        river, Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform, interleaved=False
    )
    river_handles = []
    for part in _line_parts(river_projected):
        ax.plot([p[0] for p in part], [p[1] for p in part], color="#0c7894", linewidth=1.4,
                alpha=0.95, zorder=5)
    river_handles.append(Line2D([0], [0], color="#0c7894", lw=1.6, label="Netravati river (OSM)"))
    facilities = json.loads((PROCESSED / "warehouses.geojson").read_text(encoding="utf-8"))["features"]
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    mapped_sites = []
    for feature in facilities:
        geom = feature.get("geometry") or {}
        props = feature.get("properties", {})
        if geom.get("type") != "Point" or props.get("source") != "event-confirmed":
            continue
        lon, lat = map(float, geom["coordinates"][:2])
        if parent_wgs.covers(Point(lon, lat)):
            x, y = transformer.transform(lon, lat)
            facility_id = str(props.get("warehouse_id", ""))
            marker, color = (("o", "#f59e0b") if facility_id == "svs_kannada_medium_school_bantwal"
                             else ("*", "#e34a33"))
            mapped_sites.append((feature, x, y, marker, color))
    if with_roads:
        local, major = _road_segments(parent_wgs, crs)
        if local:
            ax.add_collection(LineCollection(local, colors="#495563", linewidths=0.38, alpha=0.68, zorder=3))
        if major:
            ax.add_collection(LineCollection(major, colors="#202b35", linewidths=0.95, alpha=0.9, zorder=4))
        site_handles = []
        for feature, x, y, marker, color in mapped_sites:
            props = feature.get("properties", {})
            ax.scatter([x], [y], marker=marker, s=140 if marker == "*" else 92,
                       color=color, edgecolors="white", linewidths=1.0, zorder=8)
            label = str(props.get("name", "Relief centre"))
            label = label.replace(", Bantwal", "").replace(" (Sharada High School)", "")
            site_handles.append(Line2D([0], [0], marker=marker, color="none", markerfacecolor=color,
                                       markeredgecolor="white", markersize=10, label=label))
        road_handles = [Line2D([0], [0], color="#495563", lw=0.7, label="OSM local roads"),
                        Line2D([0], [0], color="#202b35", lw=1.3, label="OSM major roads")]
        handles = river_handles + road_handles + site_handles
    else:
        handles = river_handles
    for zone_number, feature in enumerate(zones, start=1):
        geom = transform_geom("EPSG:4326", crs, feature["geometry"])
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for polygon in polygons:
            for ring in polygon:
                xy = np.asarray(ring)
                ax.plot(xy[:, 0], xy[:, 1], color="white", linewidth=1.6, alpha=0.95, zorder=6)
                ax.plot(xy[:, 0], xy[:, 1], color="#173b57", linewidth=0.62, alpha=0.94, zorder=7)
        zone_shape = shape(transform_geom("EPSG:4326", crs, feature["geometry"]))
        point = zone_shape.representative_point()
        if mapped_sites and min(point.distance(Point(x, y)) for _, x, y, _, _ in mapped_sites) < 1_500:
            minx, miny, maxx, maxy = zone_shape.bounds
            candidates = [Point(minx + (maxx - minx) * i / 12,
                                miny + (maxy - miny) * j / 12)
                          for i in range(1, 12) for j in range(1, 12)]
            candidates = [candidate for candidate in candidates if zone_shape.contains(candidate)]
            if candidates:
                point = max(candidates, key=lambda candidate:
                            min(candidate.distance(Point(x, y)) for _, x, y, _, _ in mapped_sites)
                            + 0.35 * candidate.distance(zone_shape.boundary))
        ax.text(point.x, point.y, str(zone_number), ha="center", va="center", fontsize=7,
                weight="bold", color="#102a43", zorder=10,
                bbox={"boxstyle": "circle,pad=0.22", "fc": "white", "ec": "#173b57",
                      "lw": 0.55, "alpha": 0.92})
    parent_projected = transform_geom("EPSG:4326", crs, parent_features[0]["geometry"])
    parent_coords = parent_projected["coordinates"] if parent_projected["type"] == "MultiPolygon" else [parent_projected["coordinates"]]
    for polygon in parent_coords:
        xy = np.asarray(polygon[0])
        ax.plot(xy[:, 0], xy[:, 1], color="#e76f32", linewidth=2.0, zorder=7)
    ax.set_xlim(left, right); ax.set_ylim(bottom, top)
    fig.colorbar(shown, ax=ax, label="Relative candidate VH-change signal", shrink=0.78)
    suffix = "with OSM roads and mapped relief centres" if with_roads else "with Netravati river; no road overlay"
    ax.set_title(f"Bantwal grid zones and Sentinel-1 SAR context — {day}\n{suffix}", pad=13)
    ax.set_xlabel("Easting (km)"); ax.set_ylabel("Northing (km)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value / 1000:.0f}"))
    # A 10 km scale bar in the projected UTM coordinate system.
    bar_x = left + (right - left) * 0.045
    bar_y = bottom + (top - bottom) * 0.055
    bar_len = 10_000
    ax.plot([bar_x, bar_x + bar_len], [bar_y, bar_y], color="black", linewidth=3,
            solid_capstyle="butt", zorder=12)
    ax.text(bar_x + bar_len / 2, bar_y + (top - bottom) * 0.012, "10 km", ha="center", va="bottom",
            fontsize=8, weight="bold", color="black", zorder=12,
            bbox={"fc": "white", "ec": "none", "alpha": 0.8, "pad": 1.5})
    ax.tick_params(labelsize=9)
    ax.legend(handles=handles, frameon=True, loc="upper center", bbox_to_anchor=(0.5, -0.16),
              fontsize=8, ncols=min(4, len(handles)), columnspacing=1.2, handlelength=1.8)
    out_name = f"sar_roads_relief_sites_{day}.png" if with_roads else f"sar_flood_likelihood_{day}.png"
    fig.subplots_adjust(bottom=0.25, top=0.88, right=0.88)
    save(fig, out_name)


def render_static_coverage(day: str) -> None:
    rows = read_csv(SIMULATED / f"module6_allocation_zone_metrics_{day}.csv")
    zone_names = list(dict.fromkeys(row["zone_name"] for row in rows))
    zone_names.sort(key=lambda name: name.casefold())
    zones = [name.replace("Bantwal zone", "Grid zone") for name in zone_names]
    y = np.arange(len(zones))
    fig, ax = plt.subplots(figsize=(11.5, max(11, len(zones) * 0.22)))
    height = 0.23
    for index, engine in enumerate(ENGINES):
        subset = [row for row in rows if row["engine"] == engine]
        values = [float(next(row for row in subset if row["zone_name"] == zone)["mean_resource_coverage_pct"])
                  for zone in zone_names]
        label = ENGINE_LABELS[engine]
        ax.barh(y + (index - 1) * height, values, height * 0.92, label=label, color=COLORS[label])
    ax.set_yticks(y, zones)
    ax.set_xlabel("Mean resource coverage across food, water, and medical (%)")
    ax.set_ylabel("Grid zone")
    target = next(row for row in read_csv(OUT / "adequate_supply_summary.csv") if row["event_date"] == day)
    target_pct = float(target["scenario_target_unmet_pct"])
    ax.set_title("")
    ax.axvline(50, color="#64748b", linestyle="--", linewidth=1, alpha=0.75)
    ax.set_xlim(0, 105)
    ax.tick_params(axis="y", labelsize=6.6)
    ax.grid(axis="x", alpha=0.25)
    handles, labels = ax.get_legend_handles_labels()
    fig.suptitle(f"Mean coverage by grid zone — {day} — assumed inventory ({target_pct:g}% unmet target)",
                 y=0.99, weight="bold")
    fig.legend(handles, labels, frameon=False, ncols=3, loc="upper center", bbox_to_anchor=(0.5, 0.94))
    fig.subplots_adjust(top=0.89, bottom=0.06, left=0.23, right=0.98)
    save(fig, f"module6_static_zone_coverage_{day}.png")


def render_dynamic_minimum(day: str) -> None:
    rows = read_csv(SIMULATED / f"module8_dynamic_steps_{day}.csv")
    fig, ax = plt.subplots(figsize=(9, 5.4))
    styles = {
        "MILP": {"linestyle": "-", "marker": "o", "markersize": 9},
        "LinUCB_contextual_bandit": {"linestyle": "--", "marker": "s", "markersize": 6},
        "naive_proportional_baseline": {"linestyle": ":", "marker": "^", "markersize": 4},
    }
    for engine in ENGINES:
        subset = sorted((row for row in rows if row["engine"] == engine), key=lambda row: int(row["step"]))
        label = ENGINE_LABELS[engine]
        ax.plot([int(row["step"]) for row in subset],
                [float(row["step_minimum_zone_coverage_pct"]) for row in subset],
                linewidth=2.3, label=label, color=COLORS[label], **styles[engine])
    ax.set_xticks(range(1, 9))
    ax.set_xlabel("Disruption / reallocation step")
    ax.set_ylabel("Minimum zone coverage (%)")
    target = next(row for row in read_csv(OUT / "adequate_supply_summary.csv") if row["event_date"] == day)
    ax.set_title(f"Module 8 minimum zone coverage — assumed inventory — {day} ({float(target['scenario_target_unmet_pct']):g}% unmet target)", pad=12)
    ax.axhline(50, color="#64748b", linestyle="--", linewidth=1, alpha=0.75)
    ax.set_ylim(0, 105)
    ax.grid(alpha=0.25)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncols=3, loc="upper center", bbox_to_anchor=(0.5, 0.96))
    fig.subplots_adjust(top=0.82, bottom=0.14)
    save(fig, f"module8_minimum_coverage_steps_{day}.png")


def build_severity_scores() -> None:
    rows = []
    for day in EVENTS:
        for row in read_csv(PROCESSED / f"severity_demand_{day}.csv"):
            rows.append({
                "event_date": day,
                "zone": row["zone_name"],
                "severity_score_0_to_1": f"{float(row['severity_score']):.4f}",
                "SAR_context_score": f"{float(row.get('sar_likelihood') or 0):.4f}",
                "HAND_screen_fraction": f"{float(row.get('gauge_hand_inundated_fraction') or 0):.4f}",
                "7_day_rainfall_mm": f"{float(row.get('antecedent_7day_rainfall_mm') or 0):.1f}",
                "modeled_population": f"{float(row.get('population_estimate') or 0):.0f}",
                "estimated_affected_people": f"{float(row.get('estimated_affected_people') or 0):.0f}",
                "estimated_food_rations": f"{float(row.get('estimated_food_rations') or 0):.0f}",
                "estimated_water_liters": f"{float(row.get('estimated_water_liters') or 0):.0f}",
                "estimated_medical_kits": f"{float(row.get('estimated_medical_kits') or 0):.0f}",
                "estimate_note": "modeled severity and demand; not observed zone impact",
            })
    path = OUT / "zone_severity_scores.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    event_scores = {day: {row["zone"]: row["severity_score_0_to_1"] for row in rows if row["event_date"] == day}
                    for day in EVENTS}
    zone_names = sorted({row["zone"] for row in rows})
    zone_index = {str(feature.get("properties", {}).get("name", "")): index
                  for index, feature in enumerate(
                      json.loads((PROCESSED / "analysis_zones.geojson").read_text(encoding="utf-8"))["features"],
                      start=1)}
    display = [[zone, event_scores[EVENTS[0]].get(zone, ""),
                event_scores[EVENTS[1]].get(zone, ""), event_scores[EVENTS[2]].get(zone, "")]
               for zone in zone_names]
    zone_names = [row[0] for row in display]
    zone_labels = [f"Grid zone {zone_index.get(name, index + 1):02d}"
                   for index, name in enumerate(zone_names)]
    matrix = np.asarray([[float(row[index]) for index in range(1, 4)] for row in display], dtype=float)
    fig, ax = plt.subplots(figsize=(9, max(12, len(zone_names) * 0.22)), constrained_layout=True)
    image = ax.imshow(matrix, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1, interpolation="nearest")
    ax.set_yticks(np.arange(len(zone_names)), zone_labels, fontsize=7.2)
    ax.set_xticks(np.arange(3), ["2019", "2024", "2026"])
    ax.set_xlabel("Flood event")
    ax.set_ylabel("Grid zone")
    ax.set_title("Modeled severity by grid zone", fontsize=14, weight="bold", pad=12)
    ax.set_xticks(np.arange(-0.5, 3, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(zone_names), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.2)
    ax.tick_params(which="minor", bottom=False, left=False)
    for i in range(len(zone_names)):
        for j in range(3):
            ax.text(j, i, f"{matrix[i,j]:.2f}", ha="center", va="center", fontsize=6.2,
                    color="white" if matrix[i,j] > 0.68 else "#202b35")
    fig.colorbar(image, ax=ax, label="Modeled severity (0–1)", shrink=0.7)
    fig.savefig(OUT / "zone_severity_scores.png", dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_adequate_supply_summary() -> None:
    path = OUT / "adequate_supply_summary.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.2), sharey=True)
    engines = [("MILP", "MILP"), ("LinUCB_contextual_bandit", "LinUCB"),
               ("naive_proportional_baseline", "Proportional")]
    for ax, day in zip(axes, EVENTS):
        selected = [row for row in rows if row["event_date"] == day]
        baseline = float(selected[0]["configured_baseline_unmet_pct"])
        ax.bar(-0.55, baseline, width=0.62, color="#7b8794")
        ax.text(-0.55, baseline + 1.2, f"{baseline:.1f}%", ha="center", fontsize=9, weight="bold")
        simulated = [float(next(item for item in selected if item["engine"] == engine)["simulated_unmet_pct"])
                     for engine, _ in engines]
        value = float(np.mean(simulated))
        ax.bar(0.85, value, width=0.72, color="#3a9d74")
        ax.text(0.85, value + 0.6, f"{value:.2f}%", ha="center", fontsize=9, weight="bold")
        ax.axhline(10, color="#c0392b", linestyle="--", linewidth=1.3)
        ax.set_xticks([-0.55, 0.85], ["Baseline", "Simulated\n(assumed inventory)"])
        ax.set_title(day)
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Modeled unmet demand (%)")
    legend_handles = [Patch(facecolor="#7b8794", label="Configured baseline"),
                      Patch(facecolor="#3a9d74", label="Simulated supply (assumed inventory; shared across engines)")]
    fig.legend(handles=legend_handles, frameon=False, loc="upper center", ncols=2,
               bbox_to_anchor=(0.5, 0.88), fontsize=9)
    fig.suptitle("Supply sensitivity, not an allocator performance comparison",
                 fontsize=14, weight="bold", y=0.99)
    fig.subplots_adjust(top=0.78, bottom=0.1, wspace=0.04)
    save(fig, "supply_sensitivity_unmet_demand.png")


def render_allocation_policy_comparison() -> None:
    """Compare mean zone/resource coverage by engine for static and dynamic runs."""
    rows = read_csv(OUT / "adequate_supply_summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    x = np.arange(len(EVENTS))
    width = 0.24
    for ax, field, title in zip(axes,
                                ("static_mean_zone_coverage_pct", "mean_zone_resource_coverage_pct"),
                                ("Module 6 static", "Module 8 eight rounds")):
        for index, engine in enumerate(ENGINES):
            values = []
            for day in EVENTS:
                selected = next(row for row in rows if row["event_date"] == day and row["engine"] == engine)
                values.append(float(selected[field]))
            label = ENGINE_LABELS[engine]
            bars = ax.bar(x + (index - 1) * width, values, width, label=label, color=COLORS[label])
            for bar, value in zip(bars, values):
                ax.annotate(f"{value:.1f}", (bar.get_x() + bar.get_width() / 2, value),
                            xytext=(0, 4), textcoords="offset points", ha="center", fontsize=7)
        ax.set_xticks(x, EVENTS, rotation=18)
        ax.set_title(title, weight="bold")
        ax.set_ylim(0, 105)
        ax.grid(axis="y", alpha=0.23); ax.set_axisbelow(True)
    axes[0].set_ylabel("Mean zone/resource coverage (%)")
    axes[1].legend(frameon=False, ncols=3, loc="upper center", bbox_to_anchor=(0.5, 1.17))
    fig.suptitle("Mean coverage", weight="bold", y=0.98)
    fig.text(0.5, 0.925, "Simulated runs use assumed inventory", ha="center", fontsize=10, color="#4d5966")
    axes[0].set_title("Module 6 static — assumed inventory", weight="bold", pad=9)
    axes[1].set_title("Module 8 eight rounds — assumed inventory", weight="bold", pad=9)
    fig.subplots_adjust(top=0.78, bottom=0.13, left=0.09, right=0.98, wspace=0.16)
    save(fig, "allocation_engine_coverage.png")


def render_simulated_site_inventory() -> None:
    path = OUT / "simulated_relief_centre_inventory.csv"
    if not path.exists():
        return
    rows = read_csv(path)
    resources = [("food_rations", "Food rations", "#2878b5"),
                 ("water_liters", "Water (litres)", "#18a6a6"),
                 ("medical_kits", "Medical kits", "#e1812c")]
    sites = list(dict.fromkeys(row["facility_id"] for row in rows))
    site_names = {row["facility_id"]: row["facility_name"] for row in rows}
    site_colors = ["#355c7d", "#6c5b7b", "#c06c84"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.7))
    for ax, (resource, title, accent) in zip(axes, resources):
        events = list(dict.fromkeys(row["event_date"] for row in rows))
        left = np.zeros(len(events))
        for index, site in enumerate(sites):
            values = [int(next(r["simulated_quantity"] for r in rows
                               if r["event_date"] == day and r["resource"] == resource
                               and r["facility_id"] == site)) for day in events]
            bars = ax.barh(events, values, left=left, color=site_colors[index % len(site_colors)],
                           label=site_names[site], edgecolor="white", linewidth=0.8)
            for bar, value in zip(bars, values):
                if value:
                    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + bar.get_height() / 2,
                            f"{value:,}", ha="center", va="center", color="white", fontsize=7, weight="bold")
            left += np.asarray(values)
        ax.set_title(title, color=accent, weight="bold")
        ax.set_xlabel("Simulated quantity")
        ax.grid(axis="x", alpha=0.18)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", labelsize=8)
    legend_handles = [Patch(facecolor=site_colors[index % len(site_colors)], label=site_names[site])
                      for index, site in enumerate(sites)]
    fig.legend(handles=legend_handles, frameon=False, loc="upper center", ncols=3,
               bbox_to_anchor=(0.5, 0.87), fontsize=8)
    fig.suptitle("Illustrative simulated stock by relief centre (assumed inventory)",
                 fontsize=14, weight="bold", y=0.99)
    fig.text(0.5, 0.04,
             "Synthetic planning quantities only. Module 8 uses the combined pool; facility-level stock limits are not modeled.",
             ha="center", fontsize=9, color="#4d5966")
    fig.subplots_adjust(top=0.79, bottom=0.18, wspace=0.25)
    save(fig, "simulated_relief_centre_inventory.png")


def render_redirects() -> None:
    summaries = {day: json.loads((PROCESSED / f"module8_dynamic_summary_{day}.json").read_text(encoding="utf-8"))
                 for day in EVENTS}
    x = np.arange(len(EVENTS))
    all_values = [int(summaries[day]["module9"]["engines"][engine]["transfer_count"])
                  for day in EVENTS for engine in ENGINES]
    fig, ax = plt.subplots(figsize=(10, 5.6), constrained_layout=True)
    width = 0.24
    for index, engine in enumerate(ENGINES):
        label = ENGINE_LABELS[engine]
        values = [int(summaries[day]["module9"]["engines"][engine]["transfer_count"]) for day in EVENTS]
        ax.bar(x + (index - 1) * width, values, width, label=label, color=COLORS[label])
    ax.set_xticks(x, EVENTS)
    ax.set_ylabel("Redirected resource transfers")
    ax.set_title("Module 9 Escalation Redirects by Event and Engine", pad=12)
    ax.set_ylim(bottom=0)
    ax.set_ylim(top=max(1.0, max(all_values, default=0) * 1.15))
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False, ncols=3)
    save(fig, "module9_redirects_by_engine_event.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sar_coverage = build_sar_zone_coverage()
    for day in EVENTS:
        render_heatmap(day, sar_coverage[day])
        render_bantwal_map(day, sar_coverage[day], with_roads=True)
        render_static_coverage(day)
        render_dynamic_minimum(day)
    render_redirects()
    build_severity_scores()
    render_adequate_supply_summary()
    render_allocation_policy_comparison()
    render_simulated_site_inventory()
    print(f"Wrote presentation maps, allocation charts, severity table, and summary assets to {OUT}")


if __name__ == "__main__":
    main()
