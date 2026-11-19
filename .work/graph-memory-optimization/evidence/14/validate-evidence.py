"""Validate fixed-fixture results and source consistency without timing work."""

# ruff: noqa: S101
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
before = json.loads((HERE.parent / "13" / "after.json").read_text())
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
            "retained_graph_inventory",
        ):
            assert row[field] == old[0][field], (variant, field)
        graph = json.loads(json.dumps(row["graph"]))
        metadata = graph["component_metadata"]
        assert (
            metadata["shared_definition_bytes"]
            == old[0]["graph"]["component_metadata"]["shared_definition_bytes"]
            + 16 * metadata["shared_definition_objects"]
        )
        metadata["shared_definition_bytes"] -= 16 * metadata["shared_definition_objects"]
        graph["retained_plan_fields"]["graph"]["shallow_bytes"] -= 8
        assert graph == old[0]["graph"], variant
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
print(
    json.dumps(
        {
            "checks": checks,
            "valid": True,
            "allowed_representation_sizes": "16 bytes per weakref-capable definition; 8 per graph",
        },
        indent=2,
    )
)
