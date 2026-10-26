"""Run the available Module 0-9 validators and publish a per-event status matrix."""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from pathlib import Path

from resq.config import REPO_ROOT, load_config, configured_path
from resq.events import load_events


def run_validator(filename: str) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(REPO_ROOT / "validation" / filename)],
                            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
    output = result.stdout + result.stderr
    if output.strip():
        print(f"--- {filename} (exit {result.returncode}) ---\n{output.rstrip()}")
    return result.returncode, output


def main() -> None:
    dates = [event.event_date.isoformat() for event in load_events()]
    statuses = {(module, day): "NOT RUN" for module in range(10) for day in dates}
    details: dict[tuple[int, str], str] = {}

    # Module 0 is project/configuration preflight; Modules 1-3 are global inputs.
    config = load_config()
    assert config.get("project", {}).get("name") and config.get("data", {}).get("processed_dir")
    assert (REPO_ROOT / "pyproject.toml").is_file() and (REPO_ROOT / "requirements.txt").is_file()
    for day in dates:
        statuses[(0, day)] = "PASS (global)"
    scripts = [(1, "validate_events.py"), (2, "validate_roads.py"), (3, "validate_zones.py")]
    for module, script in scripts:
        code, output = run_validator(script)
        for day in dates:
            statuses[(module, day)] = "PASS (global)" if code == 0 else "FAIL"
            details[(module, day)] = output.strip().splitlines()[-1] if output.strip() else f"exit {code}, no output"

    # validate_phase2 covers Modules 4 (SAR/HAND), 5 (rain/severity/demand),
    # and the artifact portion of Module 6 for every event.
    phase_code, phase_output = run_validator("validate_phase2.py")
    phase_days = set(re.findall(r"Validated Phase II artifacts for (\d{4}-\d{2}-\d{2})", phase_output))
    for day in dates:
        for module in (4, 5):
            ok = phase_code == 0 and day in phase_days
            statuses[(module, day)] = "PASS" if ok else "FAIL"
            details[(module, day)] = "SAR/HAND artifacts pass" if ok else "Phase II validator did not report this event"
        ok = phase_code == 0 and day in phase_days
        statuses[(6, day)] = "PASS" if ok else "FAIL"
        details[(6, day)] = "allocation artifacts pass" if ok else "Phase II validator did not report this event"
    fairness_code, fairness_output = run_validator("validate_module6.py")
    if fairness_code != 0:
        for day in dates:
            statuses[(6, day)] = "FAIL"
            details[(6, day)] = "Module 6 fairness validator failed"

    # Module 7 reports partial closure coverage as a validated route pass.
    route_code, route_output = run_validator("validate_module7.py")
    route_results = {day: status for status, day in re.findall(
        r"Module 7 real-event (PARTIAL PASS|PASS|BLOCKED|FAILED) \[(\d{4}-\d{2}-\d{2})\]", route_output)}
    for day in dates:
        result = route_results.get(day)
        passed = route_code == 0 and result in {"PARTIAL PASS", "PASS"}
        statuses[(7, day)] = "PASS (partial)" if passed and result == "PARTIAL PASS" else "PASS" if passed else "FAIL"
        details[(7, day)] = f"real-event status: {result or 'missing'}"

    for module, script, pattern in [
        (8, "validate_module8.py", r"\[(\d{4}-\d{2}-\d{2})\] Module 8 artifacts pass"),
        (9, "validate_module9.py", r"\[(\d{4}-\d{2}-\d{2})\] Module 9 pass"),
    ]:
        code, output = run_validator(script)
        passed_days = set(re.findall(pattern, output))
        for day in dates:
            passed = code == 0 and day in passed_days
            statuses[(module, day)] = "PASS" if passed else "FAIL"
            details[(module, day)] = "validator reported pass" if passed else "validator did not report pass"

    processed = configured_path(config["data"]["processed_dir"])
    rows = [{"module": module, "event_date": day, "status": statuses[(module, day)],
             "detail": details.get((module, day), "global project/configuration check")}
            for module in range(10) for day in dates]
    csv_path = processed / "validation_modules0_9.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["module", "event_date", "status", "detail"])
        writer.writeheader(); writer.writerows(rows)

    table = ["## Modules 0-9 validator status", "",
             "Global input checks (Modules 0-3) are repeated across event columns; event-level outputs are validated independently.", "",
             "| Module | 2019-08-10 | 2024-07-31 | 2026-08-03 |",
             "|---|---|---|---|"]
    for module in range(10):
        table.append("| Module " + str(module) + " | " + " | ".join(statuses[(module, day)] for day in dates) + " |")
    table += ["", "Module 10 is not implemented in the checked-in source or validators. Module 11 is the report-generation/big-three validation script.",
              "", f"Machine-readable details: `data/processed/{csv_path.name}`."]
    results_path = REPO_ROOT / "RESULTS.md"
    if results_path.exists():
        report = results_path.read_text(encoding="utf-8")
        heading = "## Modules 0-9 validator status"
        if heading in report:
            start = report.index(heading)
            after = start + len(heading)
            next_section = re.search(r"(?m)^## (?!Modules 0-9 validator status).+", report[after:])
            end = after + next_section.start() if next_section else len(report)
            report = report[:start] + "\n".join(table) + "\n\n" + report[end:]
        else:
            next_section = re.search(r"(?m)^## .+", report)
            at = next_section.start() if next_section else len(report)
            report = report[:at] + "\n".join(table) + "\n\n" + report[at:]
        results_path.write_text(report, encoding="utf-8")

    print("\n".join(table))
    print(f"Wrote per-event validator matrix to {csv_path} and RESULTS.md")
    if any(status == "FAIL" for status in statuses.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
