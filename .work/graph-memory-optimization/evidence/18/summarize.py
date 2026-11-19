"""Verify executed source and behavior, then summarize all raw samples and ranges."""

# ruff: noqa: S101
import hashlib
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(policy, name):
    path = HERE / "sources" / policy / (name.replace(".", "/") + ".py")
    return path if path.exists() else path.with_suffix(".py.txt")


def check_source(row, policy, field="executed_source"):
    for name, value in row[field].items():
        assert digest(source(policy, name)) == value, (policy, name)
    assert "clean_ioc.container" in row[field]
    assert "clean_ioc.components" in row[field]


def stats(values):
    return {"median": statistics.median(values), "minimum": min(values), "maximum": max(values), "samples": values}


def pair(before, after):
    return {
        "before": stats(before),
        "after": stats(after),
        "median_percent_change": 100 * (statistics.median(after) / statistics.median(before) - 1),
    }


summary = {}
for workload in ("build", "resolution", "diversity"):
    rows = json.loads((OUTPUT / f"{workload}.json").read_text())
    assert len(rows) == (18 if workload == "resolution" else 36)
    output = {}
    for variant in ("run", "rich-run", "analysis"):
        policies = {
            policy: [r for r in rows if r["variant"] == variant and r["policy"] == policy]
            for policy in ("before", "after")
        }
        for policy, samples in policies.items():
            for row in samples:
                check_source(row, policy)
            if workload == "build":
                for row in samples:
                    reference = policies["before"][0]
                    for field in (
                        "validated",
                        "activations",
                        "lazy_activations",
                        "template_calls",
                        "retained_graph_inventory",
                    ):
                        assert row[field] == reference[field], (variant, field)
                    for field in (
                        "physical_records",
                        "logical_graph_visits",
                        "selected_registrations",
                        "unique_execution_steps",
                        "execution_step_kinds",
                        "record_kinds",
                    ):
                        assert row["graph"][field] == reference["graph"][field], (variant, field)
            if workload == "resolution":
                assert all(r["validated"] == policies["before"][0]["validated"] for r in samples)
        if workload == "resolution":
            metrics = ("cold_seconds", "steady_median_seconds", "cold_cpu_seconds", "steady_median_cpu_seconds")
            output[variant] = {
                metric: pair(*[[r[metric] for r in policies[p]] for p in ("before", "after")]) for metric in metrics
            }
        else:
            normal = {p: [r for r in samples if r["kind"] == "normal"] for p, samples in policies.items()}
            heap = {p: [r for r in samples if r["kind"] == "heap"] for p, samples in policies.items()}
            assert all(len(r) == 3 for r in [*normal.values(), *heap.values()])
            output[variant] = {}
            for metric in ("build_seconds", "resolve_seconds"):
                output[variant][metric] = pair(*[[r[metric] for r in normal[p]] for p in ("before", "after")])
            for metric in ("rss_bytes", "peak_rss_bytes", "traced_retained_bytes", "traced_peak_bytes"):
                group = heap if metric.startswith("traced") else normal
                output[variant][metric] = pair(
                    *[[r["prepared"][metric] for r in group[p]] for p in ("before", "after")]
                )
    summary[workload] = output
(OUTPUT / "comparison-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
