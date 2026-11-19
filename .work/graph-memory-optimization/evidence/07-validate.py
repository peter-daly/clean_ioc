"""Check repeated evidence, exact facts, lifetime outcomes and source preservation."""

# ruff: noqa: S101
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).parent
comparison = json.loads((root / "07-extended-comparison.json").read_text())
reference = comparison["runs"]["baseline"][0]
for name, runs in comparison["runs"].items():
    assert len([run for run in runs if run["instrumentation"] == "none"]) == 5
    assert len([run for run in runs if run["instrumentation"] == "tracemalloc"]) == 3
    for run in runs:
        assert run["source"]["revision"] == reference["source"]["revision"]
        assert run["source"]["source_sha256"] == reference["source"]["source_sha256"]
        assert run["probe_source_sha256"] == hashlib.sha256((root / "07-probe.py").read_bytes()).hexdigest()
        assert run["graph"]["physical_records"] == 8982
        assert run["graph"]["unique_execution_steps"] == 1765
        for key in ("template_calls", "activations", "validated", "lazy_activations"):
            assert run[key] == reference[key]
    lifetime = json.loads((root / f"07-lifetimes-{name}.json").read_text())
    base_lifetime = json.loads((root / "07-lifetimes-baseline.json").read_text())
    assert lifetime["cases"] == base_lifetime["cases"]
    assert len(lifetime["cases"]) == 16
    assert all(case["resolved_argument"] for case in lifetime["cases"])
    for mode in ("full", "reduced"):
        baseline = json.loads((root / f"07-semantics-baseline-{mode}.json").read_text())
        candidate = json.loads((root / f"07-semantics-{name}-{mode}.json").read_text())
        keys = ["source_attribution", "physical_records", "template_calls", "failed_finalization_decorator_facts"]
        if mode == "full":
            keys += ["manifest_fingerprint", "decorator_facts_sha256", "decorator_facts_count"]
        assert all(candidate[key] == baseline[key] for key in keys)
layout = json.loads((root / "07-inventory-slots.json").read_text())["layout_inventory"]
assert all(
    row["dict_offset"] == 0 and row["weakref_offset"] != 0 for row in layout["classes"] if row["name"].endswith("Step")
)
assert layout["weakref_value_step"]
source = json.loads((root / "07-source-check.json").read_text())
assert not source["changed"]
assert all(
    hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest for name, digest in source["source_hashes"].items()
)
subprocess.run(["git", "diff", "HEAD", "--exit-code", "--", "clean_ioc", "tests", "benchmarks"], check=True)  # noqa: S603,S607
result = {
    "checks": "passed",
    "probes": list(comparison["runs"]),
    "normal_processes_per_probe": 5,
    "traced_processes_per_probe": 3,
    "lifetime_cases_per_probe": 16,
    "unchanged_source_files": len(source["source_hashes"]),
    "index_compatibility": "eight artifact failures and numeric-equivalent non-int lookup limitation remain",
}
(root / "07-validation.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
