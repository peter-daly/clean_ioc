"""Validate fixed-fixture results and source consistency without timing work."""

# ruff: noqa: S101
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
before = json.loads((HERE.parent / "12" / "after.json").read_text())
after = json.loads((HERE / "after.json").read_text())
checks = []
for variant in ("run", "rich-run", "analysis"):
    old, new = before[variant]["runs"], after[variant]["runs"]
    assert len(old) == len(new) == 6
    assert sum(row["instrumentation"] == "none" for row in new) == 3
    assert sum(row["instrumentation"] == "tracemalloc" for row in new) == 3
    assert len({row["pid"] for row in new}) == 6
    for row in new:
        for field in (
            "validated",
            "template_calls",
            "lazy_activations",
            "activations",
            "graph",
            "retained_graph_inventory",
        ):
            assert row[field] == old[0][field], (variant, field)
        for name, digest in row["source"]["source_sha256"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        for name in ("python", "platform", "machine", "routes", "build_mode", "ownership"):
            assert row[name] == old[0][name], (variant, name)
    checks.append(
        {
            "variant": variant,
            "before_samples": len(old),
            "after_samples": len(new),
            "same_fixture_results_graph_inventory_callbacks": True,
            "final_source_matches": True,
        }
    )
resolution = json.loads((HERE / "resolution.json").read_text())
assert len(resolution) == 18
for variant in ("run", "rich-run", "analysis"):
    rows = [row for row in resolution if row["variant"] == variant]
    assert len(rows) == 6
    assert all(len(row["wall_seconds"]) == len(row["cpu_seconds"]) == 8 for row in rows)
    assert all(row["validated"] == rows[0]["validated"] for row in rows)
print(json.dumps({"checks": checks, "resolution_samples": len(resolution), "valid": True}, indent=2))
