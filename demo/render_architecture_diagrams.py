"""Render slide-ready architecture diagrams without external Mermaid tooling."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _setup():
    cache = tempfile.TemporaryDirectory(prefix="resq-mpl-")
    os.environ["MPLCONFIGDIR"] = cache.name
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    return cache, plt, FancyBboxPatch


def _box(ax, patch, xy, width, height, title, subtitle, color="#eaf2f8"):
    x, y = xy
    ax.add_patch(patch((x, y), width, height, boxstyle="round,pad=0.012,rounding_size=0.02",
                       facecolor=color, edgecolor="#34526f", linewidth=1.4))
    ax.text(x + width / 2, y + height * .64, title, ha="center", va="center",
            fontsize=11, weight="bold", color="#18344d")
    ax.text(x + width / 2, y + height * .31, subtitle, ha="center", va="center",
            fontsize=6.8, color="#34526f", linespacing=1.25)


def _arrow(ax, start, end, label=None, curve=0):
    ax.annotate("", xy=end, xytext=start,
                arrowprops={"arrowstyle": "-|>", "lw": 1.4, "color": "#58748e",
                            "connectionstyle": f"arc3,rad={curve}"})
    if label:
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + .02,
                label, ha="center", va="bottom", fontsize=7, color="#34495e")


def render_layers(plt, Box, out):
    fig, ax = plt.subplots(figsize=(13, 7.2))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    ax.set_title("ResQ layered architecture - Bantwal, 16 analytical zones", fontsize=17, weight="bold", pad=18)
    items = [
        ("Ingestion", "Sentinel-1 / CHIRPS\nOSM / WorldPop\nImplemented; cached inputs", "#e8f1fb"),
        ("Processing", "SAR/HAND / rainfall\nzone features\nImplemented", "#e7f4ed"),
        ("Decision", "MILP / LinUCB\nproportional / Modules 8-9\nImplemented", "#fff2d9"),
        ("Serving", "FastAPI / request checks\nSQLite-backed runs\nImplemented", "#eee9f7"),
        ("Presentation", "16-zone maps / tables\ncharts / API docs\nPartial", "#f8e8eb"),
    ]
    x0, gap, width, y, height = .025, .025, .17, .62, .22
    centers = []
    for i, (title, subtitle, color) in enumerate(items):
        x = x0 + i * (width + gap)
        _box(ax, Box, (x, y), width, height, title, subtitle, color)
        centers.append((x + width / 2, y + height / 2))
    for a, b in zip(centers, centers[1:]):
        _arrow(ax, (a[0] + width / 2, a[1]), (b[0] - width / 2, b[1]))
    _box(ax, Box, (.035, .36), .93, .13, "Storage - cross-cutting",
         "CSV / GeoJSON / GeoTIFF / GraphML / SQLite implemented", "#e7f5f5")
    for center in centers:
        ax.plot([center[0], center[0]], [.49, y], color="#8aa0b3", lw=.9,
                linestyle=(0, (2, 2)), zorder=0)
    _box(ax, Box, (.24, .10), .52, .17, "Planned operational components",
         "Authentication / live facility stock / dispatch integration / frontend",
         "#f1f1f1")
    ax.text(.5, .05, "All reported stock is configured or simulated assumption; no live warehouse inventory is connected.",
            ha="center", fontsize=9, color="#52616b")
    fig.savefig(out / "architecture_layers.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def render_flow(plt, Box, out):
    fig, ax = plt.subplots(figsize=(13, 7.2))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    ax.set_title("ResQ data flow to the zone allocation table", fontsize=17, weight="bold", pad=18)
    _box(ax, Box, (.04, .73), .21, .16, "Sentinel-1 RTC", "VH change + HAND context", "#e8f1fb")
    _box(ax, Box, (.04, .48), .21, .16, "CHIRPS", "7-day zone rainfall", "#e7f4ed")
    _box(ax, Box, (.04, .23), .21, .16, "OSM + WorldPop", "Bantwal boundary, roads,\nfacilities; 2025 constrained 1 km raster", "#fff2d9")
    _box(ax, Box, (.36, .48), .23, .22, "16 Bantwal grid cells", "Clipped to taluk polygon;\nall-event valid SAR required", "#e7f5f5")
    _box(ax, Box, (.68, .48), .25, .22, "Module 5 severity / demand", "severity_score + needs per zone\nSAR, rainfall, population, HAND", "#eee9f7")
    _box(ax, Box, (.68, .13), .25, .22, "Module 6 allocation table", "engine · zone · resource · need\nallocated · unmet", "#f8e8eb")
    for start, end in [((.25,.81),(.36,.63)),((.25,.56),(.36,.58)),((.25,.31),(.36,.53)),((.59,.59),(.68,.59)),((.805,.48),(.805,.35))]:
        _arrow(ax, start, end)
    ax.text(.5, .05, "Bantwal only. Population is a WorldPop raster-sum estimate; stocks and demand are modeled.",
            ha="center", fontsize=9, color="#52616b")
    fig.savefig(out / "data_flow.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def render_sequence(plt, Box, out):
    fig, ax = plt.subplots(figsize=(13, 7.2))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
    ax.set_title("Verified road-closure response sequence", fontsize=17, weight="bold", pad=18)
    actors = ["Operator", "FastAPI", "Closure\nGeoJSON", "Module 8", "OSM graph", "Allocators", "Module 9", "SQLite"]
    xs = [.06,.19,.32,.45,.58,.71,.84,.96]
    for x, name in zip(xs, actors):
        ax.text(x, .9, name, ha="center", va="center", fontsize=9, weight="bold",
                bbox={"boxstyle":"round,pad=.4", "fc":"#eaf2f8", "ec":"#34526f"})
        ax.plot([x,x],[.12,.84],linestyle="--",color="#aab7c4",lw=.8)
    messages = [
        (.06,.19,.78,"POST closure: run_id + closure_id"),
        (.19,.32,.68,"Verify status and geometry"),
        (.19,.45,.58,"Start existing 8-step benchmark"),
        (.45,.58,.48,"Remove matching directed edges"),
        (.45,.71,.38,"Re-solve each engine per step"),
        (.71,.84,.28,"Check shortage; heuristic transfer"),
        (.45,.19,.18,"Return step + selected-engine results"),
        (.19,.96,.10,"Persist allocations and alerts"),
    ]
    for x1,x2,y,label in messages:
        _arrow(ax,(x1,y),(x2,y))
        ax.text((x1+x2)/2,y+.018,label,ha="center",va="bottom",fontsize=7.2,color="#34495e")
    ax.text(.5,.035,"Module 8 consumes every verified closure in the event file; Module 9 remains rule-based.",
            ha="center",fontsize=9,color="#52616b")
    fig.savefig(out / "closure_sequence.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    out = ROOT / "demo"
    cache, plt, Box = _setup()
    try:
        render_layers(plt, Box, out)
        render_flow(plt, Box, out)
        render_sequence(plt, Box, out)
    finally:
        cache.cleanup()
    print("Wrote architecture_layers.png, data_flow.png, closure_sequence.png")


if __name__ == "__main__":
    main()
