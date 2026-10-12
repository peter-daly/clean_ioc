"""Summarize normal/traced groups separately, and verify graph equivalence."""

import json
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
result: dict[str, Any] = {}
for suite in ("build", "full", "diagnostics", "failure", "artifact"):
    path = HERE / f"08-{suite}-runs.json"
    if not path.exists():
        continue
    raw = json.loads(path.read_text())
    groups = {}
    for run in raw["runs"]:
        key = (run["probe"], run.get("mode", "failure"), run.get("full", run.get("explain_metadata", False)))
        groups.setdefault(key, []).append(run)
    summary = {}
    for key, runs in groups.items():
        normal = [run for run in runs if run["instrumentation"] == "none"]
        traced = [run for run in runs if run["instrumentation"] == "tracemalloc"]
        row: dict[str, Any] = {
            "normal_processes": len(normal),
            "traced_processes": len(traced),
            "median": {},
            "normal_ranges": {},
        }
        for field in (
            "build_seconds",
            "resolve_seconds",
            "prepare_seconds",
            "export_seconds",
            "inspection_seconds",
            "artifact_bytes",
            "serialized_objects",
        ):
            samples = [run[field] for run in normal if field in run]
            if samples:
                row["median"][field] = statistics.median(samples)
                row["normal_ranges"][field] = [min(samples), max(samples)]
        for stage in ("before", "prepared", "resolved", "exported", "failed"):
            row["median"][stage] = {}
            row["normal_ranges"][stage] = {}
            for group, fields in (
                (normal, ("rss_bytes", "peak_rss_bytes")),
                (traced, ("traced_retained_bytes", "traced_peak_bytes")),
            ):
                for field in fields:
                    samples = [run[stage][field] for run in group if stage in run and field in run[stage]]
                    if samples:
                        row["median"][stage][field] = statistics.median(samples)
                        if group is normal:
                            row["normal_ranges"][stage][field] = [min(samples), max(samples)]
        if "graph" in runs[0]:
            row["graph"] = {
                field: sorted({run["graph"][field] for run in runs}, key=str)
                for field in ("physical_records", "logical_graph_visits", "unique_execution_steps")
            }
        summary["/".join(map(str, key))] = row
    result[suite] = summary
    signatures = {}
    for run in raw["runs"]:
        key = run.get("full", run.get("explain_metadata", False))
        if "graph" in run:
            signature = (
                run["graph"]["physical_records"],
                run["graph"]["unique_execution_steps"],
                json.dumps(run.get("validated"), sort_keys=True),
            )
            signatures.setdefault(key, set()).add(signature)
        if suite == "artifact" and run.get("manifest"):
            signatures.setdefault("manifest", set()).add(run["manifest"])
        if suite == "failure":
            signature = (run["roots"], run["manifest"], tuple(run["issues"]), run["decorator_selected"])
            signatures.setdefault("failure", set()).add(signature)
    if any(len(values) != 1 for values in signatures.values()):
        raise AssertionError(f"{suite} semantic signature mismatch: {signatures}")
    result[suite + "_equivalence"] = True
(HERE / "08-summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print(json.dumps(result, indent=2, sort_keys=True))
