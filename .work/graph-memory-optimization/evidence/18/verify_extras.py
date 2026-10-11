"""Validate final ownership, inspection, census and bounded resolution diagnostics."""

# ruff: noqa: S101
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE


def check(row, policy, field):
    for name, expected in row[field].items():
        source = HERE / "sources" / policy / (name.replace(".", "/") + ".py")
        if not source.exists():
            source = source.with_suffix(".py.txt")
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, (policy, name)


def stats(values):
    return {"median": statistics.median(values), "minimum": min(values), "maximum": max(values), "samples": values}


summary: dict[str, Any] = {
    "status": "PASS",
    "census": {},
    "escaped": {},
    "inspection": {},
    "resolution_gc": {},
    "analysis_stage14": {},
}
for variant in ("run", "rich-run", "analysis"):
    pair = {p: json.loads((OUTPUT / f"census-{p}-{variant}.json").read_text()) for p in ("before", "after")}
    for policy, row in pair.items():
        check(row, policy, "source")
        assert all(item["live"] == 0 for item in row["counts_after_teardown"].values())
        phase = json.loads((OUTPUT / f"phases-{policy}-{variant}.json").read_text())
        check(phase, policy, "source")
        assert phase["phases"][-1]["phase"] == ("validation_report:end" if variant == "analysis" else "build:collected")
    summary["census"][variant] = {
        p: {key: r[key] for key in ("population", "counts_after_teardown", "retained")} for p, r in pair.items()
    }
rows = json.loads((OUTPUT / "escaped.json").read_text())
assert len(rows) == 24
for row in rows:
    check(row, row["policy"], "source")
    assert row["remaining"] == {"graphs": 0, "records": 0}
    assert {k: row["counts"][k] for k in ("saved_views", "graphs", "records")} == {
        "saved_views": 193,
        "graphs": 129,
        "records": 194,
    }
    assert row["counts"]["calls"] == {"source": 1, "when": 64, "position": 64}
for mode in ("run", "analysis"):
    summary["escaped"][mode] = {}
    for policy in ("before", "after"):
        selected = [r for r in rows if r["mode"] == mode and r["policy"] == policy and r["kind"] == "heap"]
        summary["escaped"][mode][policy] = {
            key: stats([r[key]["retained"] for r in selected])
            for key in ("prepared", "first_inspection", "second_inspection", "only_saved", "released")
        }
for filename in ("inspection", "inspection-full"):
    rows = json.loads((OUTPUT / f"{filename}.json").read_text())
    assert len(rows) == 6
    for row in rows:
        check(row, row["policy"], "loaded")
        if filename == "inspection-full":
            assert row["before"] == row["after"]
        else:
            assert all(r["before"] == r["after"] for r in row["inspection"])
    if filename == "inspection-full":
        fingerprints = {r["inspection"]["passes"][0]["manifest_fingerprint"] for r in rows}
        assert len(fingerprints) == 1
    summary["inspection"][filename] = {}
    for policy in ("before", "after"):
        selected = [r for r in rows if r["policy"] == policy]
        passes = [
            r["inspection"]["passes"] if filename == "inspection-full" else r["inspection"][0]["passes"]
            for r in selected
        ]
        summary["inspection"][filename][policy] = {
            label: {
                metric: stats([r[index][metric] for r in passes])
                for metric in (
                    ("explain_seconds", "census_seconds", "traversal_seconds", "manifest_seconds")
                    if filename == "inspection-full"
                    else ("seconds", "retained_bytes", "peak_bytes")
                )
            }
            for index, label in enumerate(("first", "repeated"))
        }
for filename, key, policy_field, policies in (
    ("resolution-gc", "resolution_gc", "control", ("before", "after")),
    ("analysis-stage14", "analysis_stage14", "control", ("stage14", "after")),
):
    rows = json.loads((OUTPUT / f"{filename}.json").read_text())
    assert len(rows) == (14 if filename == "resolution-gc" else 12)
    for row in rows:
        check(row, row["policy"], "executed_source")
        assert row["validated"] == rows[0]["validated"]
    for control in sorted({r[policy_field] for r in rows}):
        summary[key][control] = {}
        for policy in policies:
            selected = [r for r in rows if r[policy_field] == control and r["policy"] == policy]
            if control == "events":
                summary[key][control][policy] = [
                    dict(Counter(e["generation"] for e in item["events"] if e["phase"] == "stop"))
                    for item in selected[0]["gc_events"]
                ]
            else:
                summary[key][control][policy] = {
                    metric: stats([r[metric] for r in selected])
                    for metric in (
                        "cold_seconds",
                        "steady_median_seconds",
                        "cold_cpu_seconds",
                        "steady_median_cpu_seconds",
                    )
                }
(OUTPUT / "extras-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print("PASS: executed source, six census/phase pairs, snapshot release, inspection, and resolution controls")
