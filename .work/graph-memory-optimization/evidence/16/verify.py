# ruff: noqa: S101
"""Verify identical public output and report medians/ranges, without summed gains."""

import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.resolve().parents[3]
expected = json.loads((HERE / "measurement-source.json").read_text())
for path, digest in expected.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
before = json.loads((HERE.parent / "15/after.json").read_text())
after = json.loads((HERE / "after.json").read_text())
summary = {}
for variant in before:
    control = before[variant]["runs"][0]
    rows = after[variant]["runs"]
    assert len(rows) == 6 and len({row["pid"] for row in rows}) == 6
    for row in rows:
        for key in (
            "build_mode",
            "routes",
            "ownership",
            "python",
            "machine",
            "platform",
            "validated",
            "activations",
            "lazy_activations",
            "template_calls",
            "graph",
            "retained_graph_inventory",
        ):
            assert row[key] == control[key], (variant, key)
        for path, digest in row["source"]["source_sha256"].items():
            assert digest == expected.get(path, control["source"]["source_sha256"][path]), path
    metrics = {}
    for key in (
        "build_seconds",
        "resolve_seconds",
        "rss_bytes",
        "peak_rss_bytes",
        "traced_retained_bytes",
        "traced_peak_bytes",
    ):
        metrics[key] = {}
        for policy, samples in (("before", before[variant]["runs"]), ("after", rows)):
            group = [
                r for r in samples if r["instrumentation"] == ("tracemalloc" if key.startswith("traced") else "none")
            ]
            values = [r[key] if key.endswith("seconds") else r["prepared"][key] for r in group]
            metrics[key][policy] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
    summary[variant] = metrics
(HERE / "comparison-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
(HERE / "evidence-validation.json").write_text(
    json.dumps(
        {"source_identity": True, "public_outputs": list(before), "processes": 18, "baseline": "Verified task15 AFTER"},
        indent=2,
    )
    + "\n"
)
print(json.dumps(summary, indent=2))
