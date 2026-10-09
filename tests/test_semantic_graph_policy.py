import json
import subprocess
import sys
from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from clean_ioc import ContainerBuilder, Provider, build_arg
from clean_ioc.cli import main
from clean_ioc.tooling import (
    ChangeAllowance,
    ChangeRisk,
    DiffPolicy,
    GraphChangeKind,
    GraphManifest,
    SemanticGraphChange,
)
from tests.tooling_targets import changed_builder, valid_builder

ROOT = "root:app.Application:default:0"
CHILD = f"{ROOT}/dependency:repository:0"


def node(path=ROOT, **updates):
    result = {
        "path": path,
        "service": "app.Repository",
        "implementation": "app.SqlRepository",
        "implementation_type": "app.SqlRepository",
        "kind": "registration",
        "activation": "constructor",
        "lifespan": "scoped",
        "requires_async": False,
        "manages_cleanup": False,
        "name": None,
        "position": None,
        "order": 0,
        "argument": None,
        "tags": [],
        "boundary": None,
        "source_boundary": None,
        "cache_owner": "scope",
        "cleanup_owner": "none",
        "owner_path": None,
        "dependencies": [],
        "decorators": [],
        "pre_configurations": [],
    }
    result.update(updates)
    return result


def manifest(*roots, view="entrypoints"):
    return GraphManifest({"view": view, "roots": list(roots), "boundaries": []})


@pytest.mark.parametrize(
    ("field", "value", "kind", "risk"),
    [
        ("implementation", "app.RedisRepository", "implementation-changed", "high"),
        ("implementation_type", "app.RedisRepository", "implementation-changed", "high"),
        ("activation", "factory", "activation-changed", "high"),
        ("kind", "provider", "activation-changed", "high"),
        ("provider_mode", "async", "activation-changed", "high"),
        ("deferred_target", "app.Other", "activation-changed", "high"),
        ("scope_policy", "per_call", "activation-changed", "high"),
        ("lifespan", "singleton", "lifespan-changed", "high"),
        ("cache_owner", "root", "lifespan-changed", "high"),
        ("requires_async", True, "async-requirement-changed", "high"),
        ("manages_cleanup", True, "cleanup-changed", "high"),
        ("cleanup_owner", "scope", "cleanup-changed", "high"),
        ("owner_path", ROOT, "cleanup-changed", "high"),
        ("service", "app.Other", "selection-metadata-changed", "high"),
        ("requested_type", "app.Other", "selection-metadata-changed", "high"),
        ("name", "primary", "selection-metadata-changed", "medium"),
        ("argument", "other", "selection-metadata-changed", "medium"),
        ("key_type", "str", "selection-metadata-changed", "medium"),
        ("position", 1, "order-changed", "medium"),
        ("order", 1, "order-changed", "medium"),
        ("boundary", "storage", "boundary-component-moved", "high"),
        ("source_boundary", "storage", "boundary-component-moved", "high"),
    ],
)
def test_classifies_each_manifest_concern(field, value, kind, risk):
    baseline = manifest(node())
    current = manifest(node(**{field: value}))
    changes = current.diff(baseline).semantic_changes
    assert len(changes) == 1
    change = changes[0]
    assert isinstance(change, SemanticGraphChange)
    assert (change.kind, change.risk, change.fields) == (kind, risk, (field,))
    assert change.affected_roots == change.affected_entrypoints == (ROOT,)
    assert change.entrypoint_status == "known"


def test_splits_independent_fields_and_capability_tags_without_duplicating_concerns():
    before = node(tags=[{"name": "capability", "value": "disk"}, {"name": "team", "value": "orders"}])
    after = node(
        lifespan="singleton",
        cache_owner="root",
        requires_async=True,
        tags=[{"name": "capability", "value": "network"}, {"name": "team", "value": "payments"}],
    )
    diff = manifest(after).diff(manifest(before))
    by_kind = {change.kind: change for change in diff.semantic_changes}
    assert set(by_kind) == {
        GraphChangeKind.lifespan_changed,
        GraphChangeKind.async_requirement_changed,
        GraphChangeKind.capability_changed,
        GraphChangeKind.selection_metadata_changed,
    }
    assert by_kind[GraphChangeKind.lifespan_changed].fields == ("cache_owner", "lifespan")
    assert by_kind[GraphChangeKind.capability_changed].risk is ChangeRisk.high
    assert by_kind[GraphChangeKind.selection_metadata_changed].after == {
        "tags": [{"name": "team", "value": "payments"}]
    }
    assert diff.semantic_changes == manifest(after).diff(manifest(before)).semantic_changes


@pytest.mark.parametrize(
    ("collection", "path", "kind"),
    [
        ("dependencies", CHILD, "dependency-added"),
        ("decorators", f"{ROOT}/decorator:0", "decorator-changed"),
        ("pre_configurations", f"{ROOT}/pre_configuration:0", "pre-configuration-changed"),
    ],
)
def test_additions_removals_and_pipeline_replacements(collection, path, kind):
    baseline = manifest(node())
    with_child = manifest(node(**{collection: [node(path)]}))
    addition = with_child.diff(baseline).semantic_changes[0]
    assert (addition.kind, addition.risk, addition.before) == (kind, "medium", None)
    removal = baseline.diff(with_child).semantic_changes[0]
    expected = "dependency-removed" if collection == "dependencies" else kind
    assert (removal.kind, removal.risk, removal.after) == (expected, "high", None)
    replaced = manifest(node(**{collection: [node(path, implementation="app.Other")]})).diff(with_child)
    replacement_kind = "implementation-changed" if collection == "dependencies" else kind
    assert replaced.semantic_changes[0].kind == replacement_kind
    assert replaced.semantic_changes[0].risk is ChangeRisk.high


def test_parameter_path_replacement_retains_raw_paths_and_aligns_descendants():
    old_child = node(CHILD, argument="repository", dependencies=[node(f"{CHILD}/dependency:config:0")])
    new_path = f"{ROOT}/dependency:storage:0"
    new_child = node(
        new_path, argument="storage", implementation="app.Other", dependencies=[node(f"{new_path}/dependency:config:0")]
    )
    diff = manifest(node(dependencies=[new_child])).diff(manifest(node(dependencies=[old_child])))
    assert CHILD in diff.removed and new_path in diff.added
    assert {change.kind for change in diff.semantic_changes} == {
        GraphChangeKind.implementation_changed,
        GraphChangeKind.selection_metadata_changed,
    }
    assert all(change.path == new_path for change in diff.semantic_changes)


def test_added_capability_is_high_risk_even_on_a_new_root():
    current = manifest(node(tags=[{"name": "capability", "value": "network"}]))
    diff = current.diff(manifest())
    assert {change.kind for change in diff.evaluate(DiffPolicy(fail_at=ChangeRisk.high)).violations} == {
        GraphChangeKind.capability_changed
    }


def test_unknown_metadata_is_conservative_and_does_not_copy_unknown_values():
    diff = manifest(node(new_field={"configured": "private-value"})).diff(manifest(node()))
    assert diff.semantic_changes[0].kind is GraphChangeKind.unknown_metadata_changed
    assert diff.semantic_changes[0].risk is ChangeRisk.medium
    assert diff.semantic_changes[0].fields == ("new_field",)
    assert "private-value" not in diff.to_semantic_json()
    assert "private-value" in diff.to_json()  # The existing raw diff remains lossless.
    assert not diff.evaluate(DiffPolicy()).is_valid


def test_raw_serialization_and_fingerprints_keep_their_existing_shape():
    before, after = node(), node(lifespan="singleton")
    diff = manifest(after).diff(manifest(before))
    flat_before = {
        key: value for key, value in before.items() if key not in ("dependencies", "decorators", "pre_configurations")
    }
    flat_after = {
        key: value for key, value in after.items() if key not in ("dependencies", "decorators", "pre_configurations")
    }
    assert diff.to_dict() == {
        "same": False,
        "added": [],
        "removed": [],
        "semantic_changes": [],
        "changed": [
            {
                "path": ROOT,
                "before": flat_before,
                "after": flat_after,
                "category": "component-changed",
                "risk": "unknown",
            }
        ],
    }
    assert diff.to_text() == f"Dependency graph changed:\n~ {ROOT}"
    assert json.loads(diff.to_semantic_json()) == diff.to_semantic_dict()
    graph = changed_builder().build().graph
    saved = graph.manifest(all_roots=True).to_json()
    graph.diff(valid_builder().build().graph.manifest(all_roots=True), all_roots=True)
    assert graph.manifest(all_roots=True).to_json() == saved
    assert GraphManifest.from_json(saved).fingerprint == graph.manifest(all_roots=True).fingerprint


def test_entrypoints_and_low_risk_unreachable_roots_use_compiled_context():
    class App:
        pass

    class Unused:
        pass

    before = ContainerBuilder()
    before.register(App, root_policy="entrypoint")
    baseline = before.build().graph.manifest(all_roots=True)
    after = ContainerBuilder()
    after.register(App, root_policy="entrypoint")
    after.register(Unused)
    graph = after.build().graph
    changes = graph.diff(baseline, all_roots=True).semantic_changes
    addition = next(change for change in changes if change.kind is GraphChangeKind.root_added)
    assert addition.risk is ChangeRisk.low
    assert addition.affected_entrypoints == () and addition.entrypoint_status == "known"
    assert graph.diff(baseline, all_roots=True).evaluate(DiffPolicy()).is_valid
    plain = graph.manifest(all_roots=True).diff(baseline).semantic_changes
    assert next(change for change in plain if change.kind is GraphChangeKind.root_added).risk is ChangeRisk.medium


def test_removed_all_roots_membership_is_unknown_but_default_view_is_known():
    removed = manifest().diff(manifest(node(), view="all_roots")).semantic_changes[0]
    assert removed.affected_roots == (ROOT,) and removed.affected_entrypoints == ()
    assert removed.entrypoint_status == "unknown"
    assert "unknown membership" in manifest().diff(manifest(node(), view="all_roots")).to_semantic_text()
    known = manifest().diff(manifest(node())).semantic_changes[0]
    assert known.affected_entrypoints == (ROOT,) and known.entrypoint_status == "known"


def test_all_roots_comparison_identifies_current_marked_entrypoints_only():
    baseline = valid_builder().build().graph.manifest(all_roots=True)
    graph = changed_builder().build().graph
    replacements = [
        change
        for change in graph.diff(baseline, all_roots=True).semantic_changes
        if change.kind is GraphChangeKind.implementation_changed
    ]
    assert len(replacements) == 2  # Public dependency root and its application occurrence.
    application_change = next(change for change in replacements if "/dependency:" in change.path)
    dependency_change = next(change for change in replacements if "/dependency:" not in change.path)
    assert application_change.affected_entrypoints == ("root:tests.tooling_targets.Application:default:0",)
    assert application_change.entrypoint_status == "known"
    assert dependency_change.affected_entrypoints == () and dependency_change.entrypoint_status == "known"


def test_added_public_root_for_an_existing_entrypoint_dependency_is_medium_risk():
    class Repository:
        pass

    class App:
        def __init__(self, repository: Repository):
            self.repository = repository

    def build(root_policy):
        builder = ContainerBuilder()
        builder.register(Repository, root_policy=root_policy)
        builder.register(App, root_policy="entrypoint")
        return builder.build().graph

    diff = build("resolvable").diff(build("dependency_only").manifest(all_roots=True), all_roots=True)
    addition = next(change for change in diff.semantic_changes if change.kind is GraphChangeKind.root_added)
    assert addition.risk is ChangeRisk.medium


def test_unknown_relationships_are_classified_conservatively():
    diff = manifest(node(dependencies=[node(f"{ROOT}/future:0")])).diff(manifest(node()))
    assert diff.semantic_changes[0].kind is GraphChangeKind.unknown_metadata_changed
    assert diff.semantic_changes[0].risk is ChangeRisk.medium


def test_all_roots_preserves_named_collection_entrypoint_requests():
    class Handler:
        pass

    class FirstHandler(Handler):
        pass

    class SecondHandler(Handler):
        pass

    class ReplacementHandler(Handler):
        pass

    def build(second):
        builder = ContainerBuilder()
        builder.register(Handler, FirstHandler, name="first")
        builder.register(Handler, second, name="second")
        builder.mark_entrypoint(list[Handler], filter=lambda _: True)
        return builder.build().graph

    graph = build(ReplacementHandler)
    changes = graph.diff(build(SecondHandler).manifest(all_roots=True), all_roots=True).semantic_changes
    changed = next(change for change in changes if change.kind is GraphChangeKind.implementation_changed)
    assert changed.path.endswith(":second:0")
    assert len(changed.affected_entrypoints) == 1
    assert changed.affected_entrypoints[0].startswith("root:list[")
    assert changed.affected_entrypoints[0].endswith(":second:0")
    assert changed.affected_roots != changed.affected_entrypoints


def test_groups_repeated_changes_in_text_and_preserves_occurrences_in_json():
    other = "root:app.Other:default:0"
    first = manifest(
        node(dependencies=[node(CHILD)]), node(other, dependencies=[node(f"{other}/dependency:repository:0")])
    )
    second = manifest(
        node(dependencies=[node(CHILD, lifespan="singleton")]),
        node(other, dependencies=[node(f"{other}/dependency:repository:0", lifespan="singleton")]),
    )
    diff = second.diff(first)
    assert len(diff.semantic_changes) == 2
    text = diff.to_semantic_text()
    assert text.count("lifespan-changed") == 1
    assert ROOT in text and other in text
    assert len(json.loads(diff.to_semantic_json())["changes"]) == 2


@pytest.mark.parametrize(("threshold", "expected"), [(ChangeRisk.low, 1), (ChangeRisk.medium, 1), (ChangeRisk.high, 0)])
def test_policy_risk_thresholds(threshold, expected):
    diff = manifest(node(name="preferred")).diff(manifest(node()))
    report = diff.evaluate(DiffPolicy(fail_at=threshold))
    assert len(report.violations) == expected
    assert report.changes == diff.semantic_changes
    assert json.loads(report.to_json())["valid"] == report.is_valid
    assert ("passed" if report.is_valid else "failed") in report.to_text()


def test_denied_kind_wins_over_an_allowance_and_an_ordinary_low_risk_threshold():
    diff = manifest(node(name="preferred")).diff(manifest(node()))
    policy = DiffPolicy(
        fail_at=ChangeRisk.high,
        deny_kinds=cast(Any, {GraphChangeKind.selection_metadata_changed}),
        allowances=cast(Any, [ChangeAllowance()]),
    )
    assert not diff.evaluate(policy).is_valid
    assert isinstance(policy.deny_kinds, frozenset) and isinstance(policy.allowances, tuple)
    with pytest.raises(FrozenInstanceError):
        setattr(policy, "fail_at", ChangeRisk.low)


def test_allowance_specificity_ties_kinds_and_maximum_risks():
    diff = manifest(node(lifespan="singleton", name="preferred")).diff(manifest(node()))
    assert diff.evaluate(DiffPolicy(allowances=(ChangeAllowance(),))).is_valid
    broad = ChangeAllowance(path_glob="root:*", maximum_risk=ChangeRisk.high)
    narrow = ChangeAllowance(kind=GraphChangeKind.lifespan_changed, path_glob=ROOT, maximum_risk=ChangeRisk.medium)
    report = diff.evaluate(DiffPolicy(allowances=(broad, narrow)))
    assert [change.kind for change in report.violations] == [GraphChangeKind.lifespan_changed]
    assert not diff.evaluate(DiffPolicy(allowances=(narrow, ChangeAllowance(path_glob=ROOT)))).is_valid
    assert diff.evaluate(DiffPolicy(allowances=(ChangeAllowance(path_glob=ROOT), narrow))).is_valid
    assert not diff.evaluate(DiffPolicy(allowances=(ChangeAllowance(path_glob=ROOT.lower()),))).is_valid


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (DiffPolicy, {"fail_at": "high"}),
        (DiffPolicy, {"deny_kinds": {"lifespan-changed"}}),
        (DiffPolicy, {"allowances": (object(),)}),
        (DiffPolicy, {"deny_kinds": None}),
        (ChangeAllowance, {"kind": "root-added"}),
        (ChangeAllowance, {"maximum_risk": "high"}),
        (ChangeAllowance, {"path_glob": ""}),
        (ChangeAllowance, {"path_glob": "root:[unclosed"}),
        (ChangeAllowance, {"path_glob": object()}),
    ],
)
def test_invalid_policy_definitions_have_a_stable_error(factory, kwargs):
    with pytest.raises(ValueError, match="diff-policy-invalid"):
        factory(**kwargs)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"roots": {}},
        {"roots": [None]},
        {"roots": [{"path": ""}]},
        {"roots": [{"path": ROOT}]},
        {"roots": [node(), node()]},
        {"roots": [node(dependencies={})]},
        {"roots": [node(dependencies=[node("not-a-descendant")])]},
        {"roots": [node(requires_async="yes")]},
        {"roots": [node(tags=[{"value": "network"}])]},
        {"roots": [], "view": "invalid"},
        {"roots": [], "boundaries": [{"name": "a", "uses": [1]}]},
    ],
)
def test_malformed_manifests_are_rejected(data):
    with pytest.raises(ValueError, match="Invalid graph manifest"):
        GraphManifest.from_json(json.dumps(data))


def test_diff_does_not_activate_or_repeat_build_callbacks_and_redacts_inputs():
    calls = []

    class Service:
        def __init__(self, configured: str):
            raise AssertionError("must not activate")

    class App:
        def __init__(self, service: Provider[Service]):
            raise AssertionError("must not activate")

    def make_graph(lifespan):
        builder = ContainerBuilder()
        builder.register(
            Service,
            lifespan=lifespan,
            arguments={"configured": build_arg("private-key")},
            when=lambda _: calls.append("filter") or True,
        )
        builder.register(App, root_policy="entrypoint")
        return builder.build(build_args={"private-key": "private-value"}).graph

    baseline, graph = make_graph("scoped"), make_graph("singleton")
    called = list(calls)
    diff = graph.diff(baseline.manifest())
    report = diff.evaluate(DiffPolicy())
    assert not report.is_valid and calls == called
    for rendered in (diff.to_json(), diff.to_semantic_json(), diff.to_semantic_text(), report.to_json()):
        assert "private-key" not in rendered and "private-value" not in rendered
        assert "occurrence_id" not in rendered and "build_args" not in rendered


def test_cli_raw_classified_policy_and_output_file(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(valid_builder().build().graph.manifest().to_json())
    target = "tests.tooling_targets:changed_builder"
    assert main(["diff", target, str(baseline), "--format", "json"]) == 1
    raw = json.loads(capsys.readouterr().out)
    assert raw["semantic_changes"] == [] and raw["changed"]
    assert main(["diff", target, str(baseline), "--classify", "--format", "json"]) == 1
    classified = json.loads(capsys.readouterr().out)
    assert classified["changes"][0]["kind"] == "implementation-changed"
    assert classified["changes"][0]["affected_entrypoints"]
    output = tmp_path / "report.json"
    assert main(["diff", target, str(baseline), "--fail-on", "high", "--format", "json", "-o", str(output)]) == 1
    assert json.loads(output.read_text())["valid"] is False
    assert capsys.readouterr().out == ""
    assert main(["diff", target, str(baseline), "--policy", "tests.tooling_targets:permissive_diff_policy"]) == 0
    assert "policy passed" in capsys.readouterr().out
    assert main(["diff", "tests.tooling_targets:valid_builder", str(baseline), "--fail-on", "low"]) == 0
    assert "unchanged" in capsys.readouterr().out


def test_cli_errors_leave_baseline_and_existing_output_untouched(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(valid_builder().build().graph.manifest().to_json())
    initial = baseline.read_text()
    output = tmp_path / "report.json"
    output.write_text("existing-report")
    base = ["diff", "tests.tooling_targets:valid_builder", str(baseline)]
    assert main([*base, "--policy", "tests.tooling_targets:valid_builder", "-o", str(output)]) == 2
    assert "diff-policy-invalid" in capsys.readouterr().err
    assert output.read_text() == "existing-report"
    with pytest.raises(SystemExit) as raised:
        main([*base, "--fail-on", "high", "--policy", "tests.tooling_targets:permissive_diff_policy"])
    assert raised.value.code == 2
    capsys.readouterr()
    assert main(["diff", "tests.tooling_targets:invalid_builder", str(baseline), "--classify", "--format", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["valid"] is False
    assert main([*base, "-o", str(tmp_path)]) == 2
    assert capsys.readouterr().err
    assert baseline.read_text() == initial
    baseline.write_text('{"roots": [{}]}')
    assert main([*base, "--classify"]) == 2
    assert "Invalid graph manifest" in capsys.readouterr().err


def test_classified_cli_is_deterministic_across_processes(tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(valid_builder().build().graph.manifest().to_json())
    command = [
        sys.executable,
        "-m",
        "clean_ioc.cli",
        "diff",
        "tests.tooling_targets:changed_builder",
        str(baseline),
        "--classify",
        "--format",
        "json",
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    second = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    assert first.returncode == second.returncode == 1
    assert first.stdout == second.stdout
