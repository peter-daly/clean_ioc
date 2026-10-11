# ruff: noqa: S101
"""Validate symmetric source execution, retained populations and bounded summaries."""

import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).parent
sources = {
    "before": hashlib.sha256((HERE / "clean_ioc__components.py.before.txt").read_bytes()).hexdigest(),
    "after": hashlib.sha256((HERE / "components.py.measured.txt").read_bytes()).hexdigest(),
}
rows = json.loads((HERE / "escaped.json").read_text())
assert len(rows) == 24 and len({r["pid"] for r in rows}) == 24
counts = rows[0]["counts"]
for row in rows:
    assert row["counts"] == counts
    assert row["remaining"] == {"graphs": 0, "records": 0}
    assert row["source"]["clean_ioc.components"] == sources[row["policy"]]
summary = {}
for mode in ("run", "analysis"):
    summary[mode] = {}
    for policy in ("before", "after"):
        normal = [r for r in rows if r["mode"] == mode and r["policy"] == policy and r["kind"] == "normal"]
        heap = [r for r in rows if r["mode"] == mode and r["policy"] == policy and r["kind"] == "heap"]
        stats = {}
        for name in ("build_seconds", "first_inspection_seconds", "second_inspection_seconds"):
            values = [r[name] for r in normal]
            stats[name] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
        for phase in ("prepared", "first_inspection", "second_inspection", "only_saved", "released"):
            stats[phase] = {}
            for metric in ("retained", "peak", "peak_rss"):
                values = [r[phase][metric] for r in (normal if metric == "peak_rss" else heap)]
                stats[phase][metric] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
        summary[mode][policy] = stats
(HERE / "escaped-summary.json").write_text(json.dumps({"counts": counts, "summary": summary}, indent=2) + "\n")
censuses = {}
for variant in ("run", "rich-run", "analysis"):
    before = json.loads((HERE / f"census-before-{variant}.json").read_text())
    after = json.loads((HERE / f"census-after-{variant}.json").read_text())
    assert before["graph"] == after["graph"]
    for policy, row in (("before", before), ("after", after)):
        assert row["source"]["clean_ioc.components"] == sources[policy]
        assert all(v["live"] == 0 for v in row["counts_after_teardown"].values())
        assert row["snapshots_after_teardown"]["live"] == 0
    censuses[variant] = {policy: row["retained"] for policy, row in (("before", before), ("after", after))}
(HERE / "census-summary.json").write_text(json.dumps(censuses, indent=2) + "\n")
print(
    json.dumps(
        {
            "escaped_processes": 24,
            "counts": counts,
            "all_released": True,
            "census_variants": list(censuses),
            "executed_sources_verified": True,
        },
        indent=2,
    )
)
