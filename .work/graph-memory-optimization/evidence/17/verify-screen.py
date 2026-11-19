# ruff: noqa: S101
"""Check the bounded peak gate and preserve medians/ranges independently of census."""

import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).parent
rows = json.loads((HERE / "screen.json").read_text())
assert len(rows) == 12
assert len({row["result"]["pid"] for row in rows}) == 12
sources = {
    policy: json.loads((HERE / f"ownership-{policy}.json").read_text())["source"]["clean_ioc.container"]
    for policy in ("before", "transfer")
}
reference = rows[0]["result"]
for row in rows:
    value = row["result"]
    assert value["executed_source"]["clean_ioc.container"] == sources[row["policy"]]
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
        assert value[key] == reference[key], (row["policy"], key)
summary = {}
for metric in (
    "build_seconds",
    "resolve_seconds",
    "rss_bytes",
    "peak_rss_bytes",
    "traced_retained_bytes",
    "traced_peak_bytes",
):
    summary[metric] = {}
    for policy in ("before", "transfer"):
        kind = "heap" if metric.startswith("traced") else "normal"
        samples = [row["result"] for row in rows if row["policy"] == policy and row["kind"] == kind]
        assert len(samples) == 3
        values = [row[metric] if metric.endswith("seconds") else row["prepared"][metric] for row in samples]
        summary[metric][policy] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
(HERE / "screen-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
for name, digest in json.loads((HERE / "screen-identity.json").read_text()).items():
    path = HERE.parent / "12" / name if name == "measure.py" else HERE / (name + ".measured.txt")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
print(json.dumps(summary, indent=2))
