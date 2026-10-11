"""Evidence identity, public output agreement and paired median/range summaries."""

# ruff: noqa: S101
import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.resolve().parents[3]
expected = json.loads((HERE / "measurement-source.json").read_text())
for file, digest in expected.items():
    assert hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == digest, file
before = json.loads((HERE.parent / "14/after.json").read_text())
after = json.loads((HERE / "after.json").read_text())
summary = {}
checks = []
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
        ):
            assert row[key] == control[key], (variant, key)
        for file, digest in row["source"]["source_sha256"].items():
            assert digest == expected.get(file, control["source"]["source_sha256"][file]), file
        # Census inspects/promotes private sidecars after measured boundaries.
        comparison = json.loads(json.dumps(row["graph"]))
        if variant == "analysis":
            for name in ("occurrence_origins", "decorator_explanations"):
                assert comparison["retained_plan_fields"][name]["shallow_bytes"] == 72
                comparison["retained_plan_fields"][name]["shallow_bytes"] = control["graph"]["retained_plan_fields"][
                    name
                ]["shallow_bytes"]
            assert comparison["shallow_storage_bytes"]["origin_indexes"] == 72
            comparison["shallow_storage_bytes"]["origin_indexes"] = control["graph"]["shallow_storage_bytes"][
                "origin_indexes"
            ]
        assert comparison == control["graph"], variant
        assert row["retained_graph_inventory"] == control["retained_graph_inventory"]
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
    checks.append(variant)
(HERE / "comparison-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
(HERE / "evidence-validation.json").write_text(
    json.dumps(
        {"source_identity": True, "public_outputs": checks, "processes": 18, "baseline": "Verified task14 AFTER"},
        indent=2,
    )
    + "\n"
)
print(json.dumps(summary, indent=2))
