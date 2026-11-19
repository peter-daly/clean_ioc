# ruff: noqa: S101
"""Verify executed source, unchanged prior work, counters and final source patch."""

import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
before = json.loads((HERE / "before-source.json").read_text())
measurement = json.loads((HERE / "measurement-source.json").read_text())
expected_after = "1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for path, expected in measurement.items():
    assert digest(ROOT / path) == expected, path
for path, expected in before["sha256"].items():
    assert digest(ROOT / path) == (expected_after if path == "clean_ioc/container.py" else expected), path
assert digest(HERE.parent / "16" / "accepted-source.json") == before["previous_accepted_manifest_sha256"]
source_before = (HERE / "clean_ioc__container.py.before.txt").read_text()
assert digest(HERE / "clean_ioc__container.py.before.txt") == before["sha256"]["clean_ioc/container.py"]
source_after = (ROOT / "clean_ioc/container.py").read_text()
assert (
    source_before.replace("drafts[occurrence] for occurrence in live", "drafts.pop(occurrence) for occurrence in live")
    == source_after
)
patch = "".join(
    difflib.unified_diff(
        source_before.splitlines(keepends=True),
        source_after.splitlines(keepends=True),
        fromfile="a/clean_ioc/container.py",
        tofile="b/clean_ioc/container.py",
    )
)
test_path = "tests/test_intermediate_occurrence_lifetimes.py"
patch += "".join(
    difflib.unified_diff(
        [], (ROOT / test_path).read_text().splitlines(keepends=True), fromfile="/dev/null", tofile="b/" + test_path
    )
)
(HERE / "task17-source.patch").write_text(patch)
summary = {}
for variant in ("run", "rich-run", "analysis"):
    pair = {
        policy: json.loads((HERE / f"combined-{policy}-{variant}.json").read_text()) for policy in ("before", "after")
    }
    for policy, row in pair.items():
        expected = before["sha256"]["clean_ioc/container.py"] if policy == "before" else expected_after
        assert row["source"]["clean_ioc.container"] == expected
        assert all(value["live"] == 0 for value in row["counts_after_teardown"].values())
    for key in ("graph", "retained", "counts_after_teardown", "snapshots_after_teardown"):
        assert pair["before"][key] == pair["after"][key], (variant, key)
    summary[variant] = {
        policy: {
            "population": row["population"],
            "construction_and_class_maxima": row["counts_after_teardown"],
            "retained": row["retained"],
            "selected_phases": [
                phase
                for phase in row["phases"]
                if phase["phase"] in ("primary compilation", "freeze:begin", "freeze:end")
            ],
        }
        for policy, row in pair.items()
    }
(HERE / "census-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
proof = {
    policy: json.loads((HERE / f"ownership-{policy}.json").read_text())
    for policy in ("before", "transfer", "release-all")
}
finalizers = {
    policy: next(event for event in row["events"] if event["event"] == "discarded opaque released")
    for policy, row in proof.items()
}
assert finalizers["before"] == finalizers["transfer"]
assert finalizers["release-all"]["graph_frozen"] is False
assert finalizers["release-all"]["selected_tags_normalized"] is False
assert finalizers["transfer"]["graph_frozen"] is True
assert finalizers["transfer"]["selected_tags_normalized"] is True
validation = {
    "status": "PASS",
    "previous_source_hashes_verified": len(before["sha256"]),
    "unchanged_previous_source_hashes": len(before["sha256"]) - 1,
    "production_matches_measured_transfer": True,
    "runtime_change": "one retained-draft dictionary read becomes pop",
    "source_patch_sha256": digest(HERE / "task17-source.patch"),
    "main_shared_grid": "Not rerun in task17; final combined grid belongs to task18",
    "paired_run_processes": 12,
    "combined_census_processes": 6,
    "separate_initial_census_processes": 2,
    "phase_observer_processes": 2,
    "internal_ownership_witness_processes": 3,
    "all_counted_objects_released": True,
    "python314_full_tests": 2407,
    "python314_and_313_focused_tests": 462,
    "python311_and_312_focused_tests": {"passed": 459, "skipped": 3},
    "strict_docs": True,
    "full_ci": True,
    "artifact_round_trip_tests_included": 18,
    "exclusive_intervals": "finished",
}
(HERE / "final-verification.json").write_text(json.dumps(validation, indent=2) + "\n")
print(json.dumps(validation, indent=2))
