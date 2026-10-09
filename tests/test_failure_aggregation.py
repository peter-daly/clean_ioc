"""Diagnostic retries are optional; validation and original evidence are mandatory."""

import json
from typing import Any, Iterator, cast

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    BuildIssue,
    BuildMatrix,
    BuildVariant,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    IssueSeverity,
    WarmupPlan,
    WarmupTarget,
)
from clean_ioc.cli import main


class Missing:
    pass


class First:
    def __init__(self, missing: Missing):
        self.missing = missing


class Second:
    def __init__(self, missing: Missing):
        self.missing = missing


def broken_builder():
    result = ContainerBuilder()
    result.register(First)
    result.register(Second)
    return result


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("overlay", [False, True])
def test_no_retry_preserves_original_failure_evidence_and_failed_builder_reuse(diagnostics, overlay):
    parent = ContainerBuilder().build(provider_roots=())
    result = parent.new_scope_builder() if overlay else ContainerBuilder()
    calls = []
    result.register(First, when=lambda component: calls.append(component.service_type) or True)
    result.register(Second)
    profile = CompilationProfiler()
    with pytest.raises(ContainerBuildError) as caught:
        result.build(
            diagnostics=diagnostics,
            aggregate_errors=False,
            provider_roots=(),
            allow_scope_builders=False,
            check_unreachable=False,
            budget=CompilationBudget(diagnostic_attempts=0),
            profile=profile,
        )
    error = caught.value
    assert calls == []  # Eligibility runs only after dependencies compile successfully.
    assert error.report is not None
    assert len(error.report.errors) == 1
    issue = error.report.errors[0]
    assert error.code == issue.code == "missing-component"
    assert error.path == issue.path
    assert issue.root == issue.path[0]
    assert issue.path[0].endswith(".First") and issue.path[-1].endswith(".Missing")
    assert error.evidence and error.evidence[0] is not None
    assert error.evidence[0].attempt_ref == "attempt:1"
    assert error.report._evidence == error.evidence
    assert error.triage_report().groups
    if diagnostics:
        assert error.partial_graph is not None
        assert error.partial_graph.total_attempts == 1
        assert len(error.partial_graph.attempts) == 1
        assert error.partial_graph.total_roots == 0  # No independent diagnostic roots were attempted.
        assert not error.partial_graph.inconsistent_retries
        assert error.partial_graph.attempts[0].witness_path == issue.path
        assert error.selection_census()
    else:
        assert error.partial_graph is None
        assert error.explanations == ()
    measured = profile.report()
    assert measured.state == "failed"
    assert measured.budget_exhaustion is None
    assert measured.budget_usage is not None and dict(measured.budget_usage)["diagnostic_attempts"] == 0
    assert not any(span.phase == "diagnostic root retries" for span in measured.spans)
    assert measured.counters.to_dict().get("diagnostic root attempts", 0) == 0
    assert not result._built
    result.register(Missing)
    with result.build(aggregate_errors=False, provider_roots=(), allow_scope_builders=False) as scope:
        assert isinstance(scope.resolve(First).missing, Missing)
        assert isinstance(scope.resolve(Second).missing, Missing)
        assert not scope.allow_scope_builders
    parent.__exit__()


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
def test_compatibility_default_and_explicit_aggregation_collect_independent_roots(diagnostics, explicit):
    profile = CompilationProfiler()
    kwargs = {"aggregate_errors": True} if explicit else {}
    with pytest.raises(ContainerBuildError) as caught:
        broken_builder().build(diagnostics=diagnostics, provider_roots=(), profile=profile, **kwargs)
    assert caught.value.report is not None
    assert len(caught.value.report.errors) == 2
    assert profile.report().counters.to_dict()["diagnostic root attempts"] == 2
    if diagnostics:
        assert caught.value.partial_graph is not None
        assert caught.value.partial_graph.total_attempts == 3


@pytest.mark.parametrize("diagnostics", [False, True])
def test_arbitrary_callback_failure_is_not_replayed_and_exception_text_is_redacted(diagnostics):
    calls = []

    class UnsafeError(Exception):
        def __str__(self):
            pytest.fail("User exception text must never be inspected")

    def reject(component):
        calls.append(component.service_type)
        raise UnsafeError("private token")

    result = ContainerBuilder()
    result.register(Missing, when=reject)
    with pytest.raises(ContainerBuildError) as caught:
        result.build(diagnostics=diagnostics, aggregate_errors=False, provider_roots=())
    assert calls == [Missing]
    error = caught.value
    assert error.report is not None
    assert error.code == error.report.errors[0].code == "compile-error"
    assert error.report.errors[0].message == "Compilation failed [compile-error]."
    assert error.path == error.report.errors[0].path
    assert error.report.errors[0].root == error.path[0]
    assert error.path[0].endswith(".Missing")
    assert "private token" not in json.dumps(error.triage_report().to_dict())
    if diagnostics:
        assert error.partial_graph is not None and error.partial_graph.total_attempts == 1
    assert not result._built


@pytest.mark.parametrize("diagnostics", [False, True])
def test_no_retry_retains_boundary_failure_identity(diagnostics):
    result = ContainerBuilder()
    result.create_boundary("a").register(First)
    result.create_boundary("b").register(First)
    with pytest.raises(ContainerBuildError) as caught:
        result.build(diagnostics=diagnostics, aggregate_errors=False, provider_roots=())
    error = caught.value
    assert error.report is not None and len(error.report.errors) == 1
    assert error.issue_boundaries == ("a",)
    assert error.evidence[0] is not None and error.evidence[0].boundary == "a"
    assert error.triage_report().groups[0].boundary == "a"
    if diagnostics:
        assert error.partial_graph is not None and error.partial_graph.attempts[0].boundary == "a"


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_invalid_flag_rejected_before_profile_discovery_or_builder_consumption(value):
    calls = []
    result = ContainerBuilder()
    result.register_subclasses(Missing, subclass_type_filter=lambda cls: calls.append(cls) or True)
    profile = CompilationProfiler()
    with pytest.raises(TypeError, match="aggregate_errors must be a bool"):
        result.build(aggregate_errors=cast(Any, value), profile=profile)
    assert calls == [] and profile.report().spans == ()
    with result.build(provider_roots=()) as scope:
        overlay = scope.new_scope_builder()
        with pytest.raises(TypeError, match="aggregate_errors must be a bool"):
            overlay.build(aggregate_errors=cast(Any, value), profile=profile)
        with overlay.build(provider_roots=()):
            pass


@pytest.mark.parametrize("diagnostics", [False, True])
def test_build_rule_reports_keep_all_findings_and_do_not_replay_callbacks(diagnostics):
    result = ContainerBuilder()
    result.register(Missing)
    findings = (
        BuildIssue("application-a", IssueSeverity.error, "Required A"),
        BuildIssue("application-b", IssueSeverity.error, "Required B"),
    )
    calls = []
    result.add_validation_rule(lambda _: calls.append("rule") or findings)
    result.mark_entrypoint(First)
    with pytest.raises(ContainerBuildError) as caught:
        result.build(aggregate_errors=False, diagnostics=diagnostics, check_unreachable=False, provider_roots=())
    assert calls == ["rule"]
    assert caught.value.report is not None
    assert [issue.code for issue in caught.value.report.errors] == [
        "missing-entrypoint",
        "application-a",
        "application-b",
    ]
    assert caught.value.compiled_graph is not None
    assert not result._built


@pytest.mark.parametrize("diagnostics", [False, True])
def test_warmup_invalid_target_remains_a_build_failure(diagnostics):
    result = ContainerBuilder()
    result.register(Missing, lifespan="singleton")
    result.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(First)]))
    with pytest.raises(ContainerBuildError) as caught:
        result.build(aggregate_errors=False, diagnostics=diagnostics, provider_roots=())
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "warmup-missing-component"
    assert not result._built


def test_alias_preparation_findings_remain_aggregated():
    first = TypeAliasType("first", 1)  # ty: ignore[invalid-type-form]
    second = TypeAliasType("second", "MissingAliasTarget")  # ty: ignore[unresolved-reference]
    result = ContainerBuilder()
    result.register(first, instance=object())
    result.register(second, instance=object())
    with pytest.raises(ContainerBuildError) as caught:
        result.build(aggregate_errors=False)
    assert caught.value.report is not None and len(caught.value.report.errors) == 2
    assert {issue.code for issue in caught.value.report.errors} == {"type-alias-invalid", "type-alias-unresolved"}


def test_cli_and_matrix_keep_aggregate_diagnosis(monkeypatch, capsys):
    import clean_ioc.cli as cli

    monkeypatch.setattr(cli, "_load_object", lambda _: broken_builder())
    assert main(["check", "test:builder", "--format", "json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert len(report["issues"]) == 2
    matrix = BuildMatrix([BuildVariant("broken", broken_builder)], reference="broken").check()
    assert matrix.variants[0].build_report is not None
    assert len(matrix.variants[0].build_report.errors) == 2


@pytest.mark.parametrize("diagnostics", [False, True])
def test_valid_manifest_execution_and_cleanup_are_identical(diagnostics):
    def run(aggregate_errors):
        events = []
        result = ContainerBuilder()

        def acquire() -> Iterator[Missing]:
            events.append("open")
            yield Missing()
            events.append("close")

        result.register(Missing, factory=acquire, lifespan="singleton")
        result.register(First)
        result.register(Second)
        result.mark_entrypoint(list[First])
        with result.build(
            diagnostics=diagnostics,
            aggregate_errors=aggregate_errors,
            provider_roots=(),
            check_unreachable=False,
            allow_scope_builders=False,
        ) as scope:
            assert events == []
            assert scope.resolve(First).missing is scope.resolve(Second).missing
            manifest = scope.graph.manifest(all_roots=True).fingerprint
            catalogue = [(item.service_type, item.implementation_type) for item in scope.selected_registrations]
            findings = scope.validation_report().issues
        assert events == ["open", "close"]
        return manifest, catalogue, findings

    assert run(False) == run(True)


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("selection_filter", [False, True])
def test_nested_callback_failure_retains_request_path_without_replay(diagnostics, selection_filter):
    from clean_ioc import select

    calls = []

    def broken(component):
        calls.append(component.service_type)
        raise ValueError("private")

    result = ContainerBuilder()
    if selection_filter:
        result.register(Missing, root_policy="dependency_only")
    else:
        result.register(Missing, root_policy="dependency_only", when=broken)
    result.register(First, arguments={"missing": select(broken)} if selection_filter else {})
    with pytest.raises(ContainerBuildError) as caught:
        result.build(aggregate_errors=False, diagnostics=diagnostics, provider_roots=())
    error = caught.value
    assert calls == [Missing]
    assert error.report is not None
    path = error.report.errors[0].path
    assert len(path) == 2 and path[0].endswith(".First") and path[1].endswith(".Missing")
    assert error.report.errors[0].root == path[0]
    assert error.evidence == ()
    assert error.triage_report().incomplete
    assert error.triage_report().report == error.report
    if diagnostics:
        assert error.partial_graph is not None and error.partial_graph.attempts[0].witness_path == path


@pytest.mark.parametrize("diagnostics", [False, True])
def test_callback_allowance_remains_enforced_with_no_retry(diagnostics):
    result = ContainerBuilder()
    calls = []
    result.register(Missing, when=lambda _: calls.append("called") or True)
    with pytest.raises(ContainerBuildError) as caught:
        result.build(
            aggregate_errors=False, diagnostics=diagnostics, budget=CompilationBudget(preparation_operations=0)
        )
    assert calls == []
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "compilation-budget-exceeded"
    assert caught.value.report.errors[0].budget is not None
    assert not result._built


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("kind", ["ambiguous", "captive", "cycle", "template"])
def test_structural_safety_errors_still_fail_without_retry(diagnostics, kind):
    result = ContainerBuilder()
    if kind == "ambiguous":
        result.register(Missing)
        result.register(Missing)
        from clean_ioc import Provider

        def provider_root(handle: Provider[Missing]) -> First:
            return First(handle())

        result.register(First, factory=provider_root)
        expected = "provider-ambiguous-component"
    elif kind == "captive":
        result.register(Missing, lifespan="scoped")
        result.register(First, lifespan="singleton")
        expected = "captive-dependency"
    elif kind == "cycle":

        class Cyclic:
            pass

        def cycle(child):
            return child

        cycle.__annotations__ = {"child": Cyclic, "return": Cyclic}
        result.register(Cyclic, factory=cycle)
        expected = "circular-dependency"
    else:
        from clean_ioc import RegistrationTemplate

        result.register(Missing)
        calls = []

        def template(source):
            calls.append(source.service_type)
            return RegistrationTemplate(Second, arguments={"unknown": 1})

        result.register_registration_template(for_each=Missing, template=template)
        expected = "invalid-argument"
    with pytest.raises(ContainerBuildError) as caught:
        result.build(aggregate_errors=False, diagnostics=diagnostics, provider_roots=())
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == expected
    assert not result._built
    if kind == "template":
        assert calls == [Missing]


def test_long_original_error_path_is_not_replaced_by_bounded_partial_witness():
    result = ContainerBuilder()
    dependency = Missing
    for index in range(40):
        component = type(f"Node{index}", (), {})

        def factory(child):
            return child

        factory.__annotations__ = {"child": dependency, "return": component}
        result.register(component, factory=factory, root_policy="dependency_only" if index < 39 else "resolvable")
        dependency = component
    with pytest.raises(ContainerBuildError) as caught:
        result.build(aggregate_errors=False, diagnostics=True, provider_roots=())
    error = caught.value
    assert error.report is not None and len(error.report.errors[0].path) == 41
    assert error.path == error.report.errors[0].path
    assert isinstance(error.__cause__, ContainerBuildError) and error.__cause__.path == error.path
    assert error.partial_graph is not None
    attempt = error.partial_graph.attempts[0]
    assert attempt.witness_total == 41 and attempt.witness_omitted == 9
    assert attempt.truncated and len(attempt.witness_path) == 33
