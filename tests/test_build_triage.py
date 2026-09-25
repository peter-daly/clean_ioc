"""Build triage tests exercise compiler evidence, not message similarity."""

import json
from dataclasses import FrozenInstanceError, replace
from typing import Generic, TypeVar

import pytest

from clean_ioc import (
    Boundary,
    BuildIssue,
    BuildReport,
    BuildTriage,
    ContainerBuilder,
    ContainerBuildError,
    FailureEvidence,
    IssueSeverity,
    select,
)
from clean_ioc import component_filters as cf
from clean_ioc.cli import main
from clean_ioc.factories import use_component


def test_shared_missing_request_groups_roots_and_retains_attempts_and_original_report():
    class Missing:
        pass

    class First:
        def __init__(self, dependency: Missing):
            pass

    class Second:
        def __init__(self, dependency: Missing):
            pass

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    builder.mark_entrypoint(First)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    error = raised.value
    assert error.report is not None
    original_json = error.report.to_json()
    triage = error.triage_report()
    assert len(triage.groups) == 1
    group = triage.groups[0]
    assert group.issue_refs == ("issue:1", "issue:2")
    assert len(group.affected_roots) == 2
    assert len(group.entry_points) == 1
    assert group.attempt_refs == ("attempt:2", "attempt:3")
    assert group.provenance
    assert triage.attempt_count == 3
    assert triage.to_dict()["report"] == error.report.to_dict()
    assert error.report.to_json() == original_json
    assert error.triage_report().to_json() == triage.to_json()
    with pytest.raises(FrozenInstanceError):
        setattr(group, "ref", "mutated")
    builder.register(Missing)
    assert builder.build().build_report.is_valid


def test_same_display_name_different_type_identity_stays_separate():
    missing_a = type("Missing", (), {})
    missing_b = type("Missing", (), {})

    class First:
        def __init__(self, dependency: missing_a):
            pass

    class Second:
        def __init__(self, dependency: missing_b):
            pass

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    assert len(triage.groups) == 2
    assert all(len(group.issue_refs) == 1 for group in triage.groups)


def test_boundary_and_named_selection_contexts_do_not_merge():
    class Missing:
        pass

    class Root:
        def __init__(self, missing: Missing):
            pass

    class BoundaryRoot:
        def __init__(self, missing: Missing):
            pass

    def install_feature(builder):
        builder.register(BoundaryRoot)

    builder = ContainerBuilder()
    builder.register(Root)
    builder.install_boundary(Boundary("feature", install_feature))
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    groups = raised.value.triage_report().groups
    assert len(groups) == 2
    assert {fact.boundary for fact in raised.value.evidence if fact is not None} == {None, "feature"}

    class Candidate:
        pass

    class First:
        def __init__(self, candidate: Candidate):
            pass

    class Second:
        def __init__(self, candidate: Candidate):
            pass

    named = ContainerBuilder()
    named.register(Candidate, name="available")
    named.register(First, arguments={"candidate": select(cf.with_name("first"))})
    named.register(Second, arguments={"candidate": select(cf.with_name("second"))})
    with pytest.raises(ContainerBuildError) as named_failure:
        named.build()
    named_groups = named_failure.value.triage_report().groups
    assert len(named_groups) == 2
    assert all("rejected candidates" in group.reason for group in named_groups)


def test_same_root_failure_in_two_boundaries_keeps_both_issues_and_entrypoint_context():
    class Missing:
        pass

    class Root:
        def __init__(self, missing: Missing):
            pass

    def install_a(builder):
        builder.register(Root)

    def install_b(builder):
        builder.register(Root)

    builder = ContainerBuilder()
    builder.install_boundary(Boundary("a", install_a))
    builder.install_boundary(Boundary("b", install_b))
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    error = raised.value
    assert error.report is not None
    assert len(error.report.issues) == 2
    assert error.partial_graph is not None
    assert len(error.partial_graph.attempts) == 3
    triage = error.triage_report()
    assert len(triage.groups) == 2
    by_boundary = {group.boundary: group for group in triage.groups}
    assert by_boundary["a"].issue_refs != by_boundary["b"].issue_refs
    assert by_boundary["a"].entry_point_count == 0
    assert by_boundary["b"].entry_point_count == 0
    assert triage.to_dict()["affected_root_count"] == 2


def test_successful_same_named_root_in_other_boundary_does_not_clear_failed_evidence():
    class Missing:
        pass

    class Root:
        def __init__(self, missing: Missing):
            pass

    def install_valid(builder):
        builder.register(Missing)
        builder.register(Root)
        builder.mark_entrypoint(Root)

    def install_invalid(builder):
        builder.register(Root)

    builder = ContainerBuilder()
    builder.install_boundary(Boundary("a", install_valid))
    builder.install_boundary(Boundary("b", install_invalid))
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    assert not triage.inconsistent_retries
    assert len(triage.groups) == 1
    assert triage.groups[0].boundary == "b"
    assert triage.groups[0].entry_point_count == 0
    assert not triage.ungrouped_issue_refs


def test_unrelated_successful_retry_does_not_mark_inconsistent():
    class Missing:
        pass

    class Good:
        pass

    class Bad:
        def __init__(self, missing: Missing):
            pass

    builder = ContainerBuilder()
    builder.register(Good)
    builder.register(Bad)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    assert not triage.inconsistent_retries
    assert len(triage.groups) == 1


def test_unsupported_callback_failures_keep_distinct_boundary_root_counts():
    class Service:
        pass

    class Root:
        def __init__(self, service: Service):
            pass

    def failing_filter(_):
        raise ValueError("private callback state")

    def install(builder):
        builder.register(Service)
        builder.register(Root, arguments={"service": select(failing_filter)})

    builder = ContainerBuilder()
    builder.install_boundary(Boundary("a", install))
    builder.install_boundary(Boundary("b", install))
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    error = raised.value
    assert error.report is not None
    original_report = error.report.to_json()
    triage = error.triage_report()
    assert len(triage.report.issues) == 2
    assert len(triage.ungrouped_issue_refs) == 2
    assert not triage.groups
    payload = json.loads(triage.to_json())
    assert payload["affected_root_count"] == 2
    assert payload["affected_root_count_status"] == "exact_for_reported_issues"
    assert [item["boundary"] for item in payload["findings"]] == ["a", "b"]
    assert all(item["boundary_known"] for item in payload["findings"])
    assert "private callback state" not in triage.to_json()
    assert error.report.to_json() == original_report
    detached = BuildTriage.from_report(error.report)
    assert detached.to_dict()["affected_root_count_status"] == "lower_bound"
    assert detached.to_text().startswith("Build failed: at least 1 root failure")
    assert triage.to_text().startswith("Build failed: 2 root failures")


def test_rejected_scope_slot_is_distinct_from_missing_declaration():
    class Request:
        pass

    class Root:
        def __init__(self, request: Request):
            pass

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Root, arguments={"request": select(cf.with_name("unavailable"))})
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    assert len(triage.groups) == 1
    assert triage.evidence[0] is not None
    assert triage.evidence[0].reason == "rejected scope slot"


def test_captive_ancestors_are_distinct_and_cycles_use_directed_identity():
    class Scoped:
        pass

    class One:
        def __init__(self, item: Scoped):
            pass

    class Two:
        def __init__(self, item: Scoped):
            pass

    builder = ContainerBuilder()
    builder.register(Scoped, lifespan="scoped")
    builder.register(One, lifespan="singleton")
    builder.register(Two, lifespan="singleton")
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    captive = [group for group in triage.groups if "retains" in group.reason]
    assert len(captive) == 2

    class CycleA:
        pass

    class CycleB:
        pass

    cycle_builder = ContainerBuilder()
    cycle_builder.register(CycleA, factory=use_component(CycleB))
    cycle_builder.register(CycleB, factory=use_component(CycleA))
    with pytest.raises(ContainerBuildError) as raised_cycle:
        cycle_builder.build()
    cycle = raised_cycle.value.triage_report()
    assert any(group.reason.startswith("Cycle:") for group in cycle.groups)


def test_failed_closed_generic_retains_template_and_request():
    item_t = TypeVar("item_t")

    class Service(Generic[item_t]):
        pass

    def invalid() -> Service[dict[str, item_t]]:
        return Service()

    class Root:
        def __init__(self, service: Service[list[int]]):
            pass

    class OtherRoot:
        def __init__(self, service: Service[list[str]]):
            pass

    builder = ContainerBuilder()
    builder.register_pattern(Service[list[item_t]], factory=invalid)
    builder.register(Root)
    builder.register(OtherRoot)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    generic = [fact for fact in triage.evidence if fact is not None and fact.kind == "generic"]
    assert generic
    assert generic[0].requested_service.endswith("Service[list[int]]")
    assert generic[0].template is not None and "Service" in generic[0].template
    assert len({fact.requested_service for fact in generic}) == 2
    assert len([group for group in triage.groups if "specialization" in group.reason or "binding" in group.reason]) == 2


def test_validation_only_and_unsupported_findings_stay_individual():
    issues = (
        BuildIssue("custom", IssueSeverity.error, "identical"),
        BuildIssue("custom", IssueSeverity.error, "identical"),
    )
    report = BuildReport(issues)
    triage = BuildTriage.from_report(report)
    assert not triage.groups
    assert triage.ungrouped_issue_refs == ("issue:1", "issue:2")
    assert len(json.loads(triage.to_json())["findings"]) == 2
    assert triage.incomplete


def test_evidence_identity_is_never_serialized_and_no_repr_is_called():
    class Secret:
        def __repr__(self):
            raise AssertionError("secret was inspected")

    evidence = FailureEvidence(
        "missing",
        "app.Missing",
        "missing declaration",
        identity=(Secret(),),
    )
    report = BuildReport((BuildIssue("missing-component", IssueSeverity.error, "Safe", root="app.Root"),))
    triage = BuildTriage.from_report(report, evidence=(evidence,))
    assert "Secret" not in triage.to_json()
    assert "identity" not in triage.to_json()
    clipped = FailureEvidence("missing", "app.Missing", "missing declaration", witness=tuple(map(str, range(40))))
    copied = replace(clipped, attempt_ref="attempt:2")
    assert len(copied.witness) == 32
    assert copied.witness_total == 40
    assert copied.witness_omitted == 8


def test_changed_filter_result_marks_retry_inconsistent_without_reexecuting_on_render():
    class Service:
        pass

    class Root:
        def __init__(self, service: Service):
            pass

    calls = 0

    def varying_filter(_):
        nonlocal calls
        calls += 1
        return calls > 1

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register(Root, arguments={"service": select(varying_filter)})
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    calls_after_build = calls
    triage = raised.value.triage_report()
    assert triage.inconsistent_retries
    assert triage.ungrouped_issue_refs == ("issue:1",)
    triage.to_text(detailed=True)
    triage.to_json()
    raised.value.triage_report()
    assert calls == calls_after_build


def test_wide_failed_report_bounds_group_details_and_accounts_for_every_issue():
    class Missing:
        pass

    builder = ContainerBuilder()
    for number in range(105):

        def initialize(self, missing: Missing):
            pass

        builder.register(type(f"Root{number}", (), {"__init__": initialize}))
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    triage = raised.value.triage_report()
    assert len(triage.report.issues) == 105
    assert len(triage.groups) == 1
    group = triage.groups[0]
    assert len(group.issue_refs) == 105
    assert group.affected_root_count == 105
    assert len(group.affected_roots) == 32
    assert group.affected_roots_omitted == 73
    assert group.attempt_count == 105
    assert len(group.attempt_refs) == 16
    assert group.attempt_refs_omitted == 89
    assert triage.attempt_count == 106
    assert triage.omitted_attempt_count == 5
    assert triage.incomplete
    payload = json.loads(triage.to_json())
    assert payload["issue_count_status"] == "exact"
    assert payload["attempt_count_status"] == "exact"
    assert payload["partial_graph_truncated"] is True
    assert payload["groups"][0]["witness_count_status"] == "lower_bound"
    assert payload["groups"][0]["retained_witness_count"] <= 8


def test_cli_triage_failed_build_validation_and_exit_policy(capsys, tmp_path):
    assert main(["check", "tests.tooling_targets:invalid_builder", "--triage", "--format", "json"]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["groups"][0]["issue_refs"] == ["issue:1"]
    assert failed["report"]["issues"][0]["code"] == "missing-component"

    target = "tests.tooling_targets:valid_builder"
    assert main(["check", target, "--triage", "--no-strict"]) == 0
    capsys.readouterr()
    assert main(["check", target, "--triage"]) == 1
    capsys.readouterr()
    assert main(["check", target, "--triage", "--ignore", "unreachable-component"]) == 0
    capsys.readouterr()
    destination = tmp_path / "triage.json"
    assert main(["check", target, "--triage", "--format", "json", "-o", str(destination), "--no-strict"]) == 0
    assert "groups" in json.loads(destination.read_text())
