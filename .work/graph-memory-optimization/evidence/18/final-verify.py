"""Verify accepted source, measured archives, byte-identical captures and final task patch."""

# ruff: noqa: S101, S603, S607
import ast
import difflib
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


previous = json.loads((HERE.parent / "17/accepted-source.json").read_text())
for path, expected in previous["sha256"].items():
    assert digest(ROOT / path) == expected, path
measurement = json.loads((HERE / "measurement-source.json").read_text())
for path, expected in measurement["sha256"].items():
    actual = ROOT / path
    if "sources/" in path:
        actual = actual.with_suffix(".py.txt")
    elif actual.name in ("grid.py", "source_loader.py"):
        actual = actual.with_suffix(".py.measured.txt")
    assert digest(actual) == expected, path
for manifest in ("observer-source.json", "resolution-gc-source.json", "analysis-stage14-harness.json"):
    for name, expected in json.loads((HERE / manifest).read_text()).items():
        assert digest(HERE / (name + ".measured.txt")) == expected, (manifest, name)
for path, expected in json.loads((HERE / "stage14-source.json").read_text()).items():
    assert digest((ROOT / path).with_suffix(".py.txt")) == expected, path
for captured in (HERE / "sources/after").rglob("*.py.txt"):
    original = ROOT / str(captured.relative_to(HERE / "sources/after"))[:-4]
    assert digest(captured) == digest(original), str(original)
loader = (HERE / "source_loader.py.measured.txt").read_text()
assert loader.replace(' + ".py")', ' + ".py.txt")') == (HERE / "source_loader.py").read_text()
for filename, names in {
    "grid.py": {"rich_rule", "prepare", "sample"},
    "resolution_gc.py": {"sample"},
    "analysis_stage14.py": {"sample"},
}.items():

    def functions(path):
        tree = ast.parse(path.read_text())
        return {
            node.name: ast.dump(node, include_attributes=False)
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
        }

    assert functions(HERE / filename) == functions(HERE / (filename + ".measured.txt")), filename
for filename in ("census.py", "escaped.py", "inspection.py", "inspection-full.py", "phases.py"):
    assert digest(HERE / filename) == digest(HERE / (filename + ".measured.txt")), filename
assert (
    digest(ROOT / "clean_ioc/_compact_index.py")
    == json.loads((HERE.parent / "15/accepted-source.json").read_text())["sha256"]["clean_ioc/_compact_index.py"]
)
assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == measurement["revision"]
assert subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() == measurement["branch"]
patch = ""
changed = ("README.md", "V1_TO_V2_UPGRADE.md", "docs/graph-memory-fixture.md", "tests/test_combined_mode_acceptance.py")
for path in changed:
    before = HERE / (path.replace("/", "__") + ".before.txt")
    old = before.read_text().splitlines(keepends=True) if before.exists() else []
    patch += "".join(
        difflib.unified_diff(
            old,
            (ROOT / path).read_text().splitlines(keepends=True),
            fromfile="a/" + path if old else "/dev/null",
            tofile="b/" + path,
        )
    )
(HERE / "task18-source.patch").write_text(patch)
checks = {
    name: (HERE / name).read_text()
    for name in ("make-ci.txt", "focused.txt", "docs-strict.txt", "python3.11.txt", "python3.12.txt", "python3.13.txt")
}
assert "2409 passed" in checks["make-ci.txt"]
assert "739 passed" in checks["focused.txt"]
assert "Documentation built" in checks["docs-strict.txt"]
assert "735 passed, 4 skipped" in checks["python3.11.txt"]
assert "736 passed, 3 skipped" in checks["python3.12.txt"]
assert "739 passed" in checks["python3.13.txt"]
paths = {ROOT / path for path in previous["sha256"]} | {ROOT / path for path in changed}
paths.update((ROOT / "clean_ioc").rglob("*.py"))
paths.update(HERE.glob("*.py"))
paths.update(HERE.glob("*.sh"))
paths.update(HERE.glob("*.measured.txt"))
paths.update((HERE / "sources").rglob("*.txt"))
paths.update(
    path for path in HERE.glob("*.json") if path.name not in {"accepted-source.json", "final-verification.json"}
)
paths.add(HERE / "task18-source.patch")
accepted = {
    "revision": measurement["revision"],
    "branch": measurement["branch"],
    "version": "2.0.0rc4",
    "python": platform.python_version(),
    "platform": platform.platform(),
    "executable": sys.executable,
    "decision": "Qualified KEEP; implementation work complete, coordinating acceptance pending",
    "sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)},
}
(HERE / "accepted-source.json").write_text(json.dumps(accepted, indent=2) + "\n")
verification = {
    "status": "PASS",
    "previous_source_hashes_unchanged": len(previous["sha256"]),
    "runtime_source_changed_in_task18": False,
    "measured_sample_function_asts_unchanged": True,
    "source_archival_change": "Byte-identical .py captures renamed .py.txt; original filenames passed to compile",
    "reproduction_changes": "Explicit output directory and overwrite guard; formatting/type comments only otherwise",
    "final_manifest_entries": len(accepted["sha256"]),
    "python314_full_tests": 2409,
    "focused_314_313": 739,
    "focused_312": {"passed": 736, "skipped": 3},
    "focused_311": {"passed": 735, "skipped": 4},
    "strict_docs": True,
    "main_build_processes": 36,
    "resolution_processes": 18,
    "diversity_processes": 36,
    "census_processes": 6,
    "phase_processes": 6,
    "snapshot_processes": 24,
    "inspection_processes": 12,
    "rich_gc_diagnostic_processes": 12,
    "separate_gc_observer_processes": 2,
    "analysis_stage14_processes": 12,
    "exclusive_measurement_interval": "ended",
    "downstream_application_verification": "not run",
    "source_patch_sha256": digest(HERE / "task18-source.patch"),
}
(HERE / "final-verification.json").write_text(json.dumps(verification, indent=2) + "\n")
print(json.dumps(verification, indent=2))
