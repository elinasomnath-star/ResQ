"""Measure current allocator kernels on synthetic zone counts and cached graph.

Synthetic rows are generated only as a repeatable computational workload. They
are not event outcomes or operational performance claims. Peak memory is Python
heap tracked by tracemalloc (native-library allocations may not be included).
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resq.config import configured_path, load_config  # noqa: E402
from resq.optimization.allocation import (  # noqa: E402
    RESOURCE_COLUMNS, _bandit_allocate, _proportional, _solve_milp,
    _train_contextual_bandit,
)
from resq.routing import _load_graph  # noqa: E402


SIZES = (8, 16, 32, 62, 128)
ENGINES = ("MILP", "LinUCB", "proportional")


def _workload(n: int) -> tuple[list[dict[str, str]], dict[str, int], np.ndarray, np.ndarray]:
    rng = np.random.default_rng(20261028 + n)
    rows = []
    for index in range(n):
        rows.append({"zone_id": f"bench_{index:03d}", "zone_name": f"Synthetic zone {index + 1}",
                     "severity_score": str(float(rng.uniform(0.05, 0.95))),
                     "population_estimate": str(float(rng.integers(1000, 30000))),
                     "estimated_food_rations": str(int(rng.integers(300, 3000))),
                     "estimated_water_liters": str(int(rng.integers(1500, 15000))),
                     "estimated_medical_kits": str(int(rng.integers(10, 180)))} )
    stocks = {resource: int(sum(int(row[column]) for row in rows) * 0.55)
              for resource, column in RESOURCE_COLUMNS.items()}
    severity = np.asarray([float(row["severity_score"]) for row in rows])
    population = np.asarray([float(row["population_estimate"]) for row in rows])
    return rows, stocks, severity, population


def _measure(callable_):
    tracemalloc.start()
    started = time.perf_counter()
    try:
        value = callable_()
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        return value, elapsed, peak / (1024 * 1024), ""
    except Exception as exc:  # persist failures so a benchmark is still complete
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        return None, elapsed, peak / (1024 * 1024), f"{type(exc).__name__}: {exc}"
    finally:
        tracemalloc.stop()


def run() -> Path:
    config = load_config()
    processed = configured_path(config["data"]["processed_dir"])
    output = processed / "scaling_benchmark.csv"
    rows_out: list[dict[str, object]] = []
    for n in SIZES:
        rows, stock, severity, population = _workload(n)
        for engine in ENGINES:
            training_seconds: float | str = ""
            if engine == "MILP":
                call = lambda: _solve_milp(rows, stock, 0.40, severity)
            elif engine == "LinUCB":
                # Train one real policy per resource on the synthetic workload;
                # record training separately from inference.
                policies = {}
                training_start = time.perf_counter()
                for resource, column in RESOURCE_COLUMNS.items():
                    demand = np.asarray([int(row[column]) for row in rows], dtype=int)
                    policy, _, _ = _train_contextual_bandit(
                        [demand], severity, population, stock[resource], 0.40, 20261028 + n)
                    policies[resource] = policy
                training_seconds = time.perf_counter() - training_start
                # Inference time excludes the above policy training.
                def infer_all_resources():
                    outputs = {}
                    for resource in RESOURCE_COLUMNS:
                        allocation, _ = _bandit_allocate(policies[resource], rows,
                            {resource: stock[resource]}, 0.40, severity, population)
                        outputs[resource] = allocation[resource]
                    return outputs
                call = infer_all_resources
            else:
                call = lambda: _proportional(rows, stock)
            result, seconds, memory, error = _measure(call)
            if engine == "MILP" and result is not None:
                seconds = float(result[1])  # solver-reported solve time
            rows_out.append({"component": "allocator", "zone_count": n, "engine": engine,
                             "elapsed_seconds": seconds, "peak_python_heap_mb": memory,
                             "training_seconds": training_seconds,
                             "status": "pass" if not error else "fail", "error": error,
                             "workload": "synthetic benchmark inputs; 55% pooled inventory ratio"})
    graph_path = configured_path(config["data"]["road_graph_path"])
    if graph_path.exists():
        _, seconds, memory, error = _measure(lambda: _load_graph(graph_path))
        rows_out.append({"component": "road_graph_load", "zone_count": "", "engine": "cached OSM graph",
                         "elapsed_seconds": seconds, "peak_python_heap_mb": memory,
                         "training_seconds": "",
                         "status": "pass" if not error else "fail", "error": error,
                         "workload": str(graph_path.relative_to(ROOT))})
    else:
        rows_out.append({"component": "road_graph_load", "zone_count": "", "engine": "cached OSM graph",
                         "elapsed_seconds": "", "peak_python_heap_mb": "", "status": "fail",
                         "training_seconds": "", "error": f"missing {graph_path}",
                         "workload": str(graph_path.relative_to(ROOT))})
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows_out[0])
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows_out)
    _plot(rows_out, ROOT / "demo" / "scaling_benchmark.png")
    for row in rows_out:
        print(" | ".join(f"{k}={row[k]}" for k in fields))
    return output


def _plot(rows: list[dict[str, object]], path: Path) -> None:
    cache = tempfile.TemporaryDirectory(prefix="resq-benchmark-mpl-")
    os.environ["MPLCONFIGDIR"] = cache.name
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 5.2), constrained_layout=True)
    for engine in ENGINES:
        points = [r for r in rows if r["component"] == "allocator" and r["engine"] == engine and r["status"] == "pass"]
        ax.plot([int(r["zone_count"]) for r in points], [float(r["elapsed_seconds"]) for r in points],
                marker="o", linewidth=2, label=engine)
    ax.set_xscale("log", base=2)
    ax.set_xticks(SIZES, [str(s) for s in SIZES])
    ax.set_xlabel("Zone count (synthetic benchmark workload)")
    ax.set_ylabel("Solve / inference seconds")
    ax.set_title("ResQ allocator runtime scaling")
    ax.grid(True, alpha=.25)
    ax.legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)
    cache.cleanup()


if __name__ == "__main__":
    print(f"Wrote {run()}")
