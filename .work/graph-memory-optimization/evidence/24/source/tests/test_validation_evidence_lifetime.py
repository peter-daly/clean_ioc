"""Public mode contracts for captured validation views and minimal failures."""

import gc
import json
import weakref

import pytest

from clean_ioc import (
    BuilderAlreadyBuiltError,
    BuildIssue,
    CompilationBudget,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    IssueSeverity,
    ResolutionProfiler,
    ScopeBuilder,
    WarmupPlan,
    WarmupTarget,
    select,
)
from clean_ioc.tooling import CompiledGraph


class Leaf:
    pass


class Service:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


def composition():
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Leaf, lifespan="singleton")
    builder.register(Service)
    boundary = builder.create_boundary("commands")
    boundary.register(Leaf)
    boundary.register(Service)
    return builder, boundary


def capture(graph):
    manifest = graph.manifest(all_roots=True)
    graph.ownership_report()
    graph.analysis_index()
    graph.selection_census(all_roots=True)
    return graph, graph.manifest, manifest


def assert_readable(saved):
    for graph, method, manifest in saved:
        assert graph.explain_metadata_enabled
        assert method().fingerprint == manifest.fingerprint
        assert graph.ownership_report().records


@pytest.mark.parametrize("mode", ["run", "analysis"])
@pytest.mark.parametrize("budget", [None, CompilationBudget()])
@pytest.mark.parametrize("warmup", [False, True])
def test_all_saved_root_and_boundary_views_share_finalization(mode, budget, warmup, monkeypatch):
    builder, boundary = composition()
    saved = []
    calls = []

    def rule(context):
        calls.append(context.boundary)
        saved.append(capture(context.graph))
        return ()

    def forbidden(*args):
        pytest.fail("Lifetime tracking compared or hashed an inspection graph")

    monkeypatch.setattr(CompiledGraph, "__hash__", forbidden)
    monkeypatch.setattr(CompiledGraph, "__eq__", forbidden)
    builder.add_validation_rule(rule)
    boundary.add_validation_rule(rule)
    if warmup:
        builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Leaf)]))
    result = builder.analyse(budget=budget) if mode == "analysis" else None
    runtime = (
        result.create_runtime(instrumentation=Instrumentation(ResolutionProfiler()))
        if result
        else builder.build(budget=budget, instrumentation=Instrumentation(ResolutionProfiler()))
    )
    with runtime:
        assert calls == ([None, "commands"] if result else [])
        assert isinstance(runtime.resolve(Service).leaf, Leaf)
        assert {item.implementation_type for item in runtime.selected_registrations} == {Leaf, Service}
        if warmup:
            assert runtime.warmup("startup").is_valid
        if mode == "run":
            assert saved == []
        else:
            assert all(graph.explain_metadata_enabled and method().fingerprint for graph, method, _ in saved)


@pytest.mark.parametrize("budget", [None, CompilationBudget()])
def test_rule_failure_keeps_original_facts_and_consumes_attempt(budget):
    saved, calls = [], []
    reject = True

    def rule(context):
        calls.append(context.boundary)
        saved.append(capture(context.graph))
        return [next(context.graph.walk()).issue("command-policy", "Rejected command")] if reject else ()

    def configured():
        builder, boundary = composition()
        builder.add_validation_rule(rule)
        boundary.add_validation_rule(rule)
        return builder

    builder = configured()
    result = builder.analyse(budget=budget)
    assert not result.report.is_valid
    assert calls == [None, "commands"]
    assert result.report.errors[0].code == "command-policy"
    assert result.report.errors[0].path
    fact = result.report._evidence[0]
    assert fact is not None and fact.source_location is not None
    assert fact.source_location.path.endswith("test_validation_evidence_lifetime.py")
    assert "test_validation_evidence_lifetime.py" in result.report.to_sarif()
    assert result.graph.manifest(all_roots=True).fingerprint
    assert_readable(saved)
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.build()
    reject = False
    with configured().analyse() as repaired, repaired.create_runtime() as runtime:
        assert repaired.report.is_valid
        assert isinstance(runtime.resolve(Service), Service)
    assert calls == [None, "commands", None, "commands"]


def test_budget_interruption_expires_saved_views_and_keeps_prior_rule_findings():
    builder, boundary = composition()
    saved = []
    calls = []

    def finite(context):
        calls.append("root")
        saved.append(capture(context.graph))
        return ()

    def exhausted(context):
        calls.append("boundary")
        saved.append(capture(context.graph))
        yield next(context.graph.walk()).issue("prior-policy", "Prior finding")
        while True:
            yield BuildIssue("repeated", IssueSeverity.warning, "Deliberate budget workload")

    builder.add_validation_rule(finite)
    boundary.add_validation_rule(exhausted)
    caught_analysis = builder.analyse(budget=CompilationBudget(preparation_operations=100))
    assert not caught_analysis.report.is_valid
    error = caught_analysis
    assert error.report is not None
    assert error.report._evidence[0] is not None
    assert error.report.errors[-1].budget is not None
    assert calls == ["root", "boundary"]
    assert error.report.errors[-1].code == "compilation-budget-exceeded"
    assert error.report.errors[0].code == "prior-policy"
    assert error.report._evidence[0].source_location is not None
    assert error.report.errors[-1].budget.phase == "analysis rules"
    assert error.graph is error.report._graph
    assert error.graph is not None
    assert not error.report.complete
    assert_readable(saved)


def test_warmup_failure_expires_pre_warmup_views_without_replaying_rules():
    builder, boundary = composition()
    saved = []

    def rule(context):
        saved.append(capture(context.graph))
        return ()

    builder.add_validation_rule(rule)
    boundary.add_validation_rule(rule)
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Service)]))
    caught_analysis = builder.analyse()
    assert not caught_analysis.report.is_valid
    assert caught_analysis.report.errors[0].code == "warmup-non-singleton-target"
    assert caught_analysis.report._evidence[0] is not None
    assert caught_analysis.report._evidence[0].source_location is not None
    assert len(saved) == 2
    assert_readable(saved)
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.remove_warmup_plan("startup")
    builder, _ = composition()
    with builder.build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)


def test_failed_run_overlay_does_not_expire_parent_or_inherited_rule_views():
    builder, boundary = composition()
    saved = []

    def inherited(context):
        saved.append(capture(context.graph))
        return ()

    boundary.add_validation_rule(inherited)
    with builder.analyse() as parent_analysis, parent_analysis.create_runtime() as parent:
        parent_fingerprint = parent_analysis.graph.manifest(all_roots=True).fingerprint
        child = ScopeBuilder(parent, composition=parent_analysis.composition)
        child.add_validation_rule(lambda _: [BuildIssue("child-policy", IssueSeverity.error, "Rejected child")])
        caught_analysis = child.analyse()
        assert not caught_analysis.report.is_valid
        assert caught_analysis.graph is not None
        assert saved[0][0].manifest(all_roots=True).fingerprint
        assert_readable(saved[1:])
        assert parent_analysis.graph.manifest(all_roots=True).fingerprint == parent_fingerprint


def test_saved_foreign_analysis_error_is_never_mutated_by_run_cleanup():
    builder, _ = composition()
    builder.add_validation_rule(lambda _: [BuildIssue("foreign", IssueSeverity.error, "Saved analysis error")])
    old_analysis = builder.analyse()
    assert not old_analysis.report.is_valid
    foreign = old_analysis
    graph = foreign.graph
    assert graph is not None
    report = foreign.report
    fingerprint = graph.manifest(all_roots=True).fingerprint

    def fail(component):
        raise ContainerBuildError(report=foreign.report)

    current = ContainerBuilder().set_provider_roots(())
    current.register(Leaf)
    current.register(Service, arguments={"leaf": select(fail)})
    caught_analysis = current.analyse()
    assert not caught_analysis.report.is_valid
    assert caught_analysis is not foreign
    assert caught_analysis.report is not None
    assert caught_analysis.graph is caught_analysis.report._graph is None
    assert foreign.report is report
    assert foreign.graph is graph
    assert foreign.graph.explain_metadata_enabled
    assert graph.manifest(all_roots=True).fingerprint == fingerprint


def test_foreign_occurrence_numbers_never_invent_current_provenance():
    foreign_builder, _ = composition()
    with foreign_builder.analyse() as foreign_analysis, foreign_analysis.create_runtime() as _foreign:
        issue = next(foreign_analysis.graph.walk()).issue("foreign-visit", "A saved issue from another graph")
        current, _ = composition()

        def rule(context):
            assert issue._occurrence_path == next(context.graph.walk()).issue("test", "test")._occurrence_path
            return [issue]

        current.add_validation_rule(rule)
        caught_analysis = current.analyse()
        assert not caught_analysis.report.is_valid
        fact = caught_analysis.report._evidence[0]
        assert fact is not None and fact.source_location is not None and fact.source_location.symbol is not None
        assert fact.source_location != foreign_analysis.graph._occurrence_origins[issue._occurrence_path[-1]].location
        assert fact.source_location.symbol.endswith("test_foreign_occurrence_numbers_never_invent_current_provenance")
        assert json.loads(caught_analysis.report.to_sarif())["runs"][0]["results"][0]["locations"]


def test_repeated_analysis_validation_does_not_retain_dead_boundary_graphs():
    builder, boundary = composition()
    references = []
    boundary.add_validation_rule(lambda c: references.append(weakref.ref(c.graph)) or ())
    with builder.analyse() as runtime_analysis, runtime_analysis.create_runtime() as _runtime:
        for _ in range(40):
            assert runtime_analysis.report.is_valid
        gc.collect()
        assert all(reference() is None for reference in references)
        assert len(runtime_analysis.graph._inspection_lifetime.views) == 1


def test_missing_filtered_dependency_retains_one_original_rejection_witness():
    calls = []
    builder = ContainerBuilder().set_provider_roots(())
    registration = builder.register(Leaf, root_policy="dependency_only")

    def reject(component):
        calls.append(component.id)
        return False

    builder.register(Service, arguments={"leaf": select(reject)})
    caught_analysis = builder.analyse()
    assert not caught_analysis.report.is_valid
    error = caught_analysis
    assert calls == [registration, registration]
    fact = error.report._evidence[0]
    assert fact is not None and fact.selection_witness is not None
    assert fact.reason == "rejected candidates"
    assert fact.selection_witness.component_id == registration
    assert fact.selection_witness.reason_codes == ("rejected-filter",)
    assert fact.selection_witness.origin.location is not None
    assert fact.witness == error.report.errors[0].path
    before = len(calls)
    assert error.triage_report().attempt_history_available
    assert error.triage_report().to_text()
    assert len(calls) == before


def test_profiler_can_observe_independent_execution_plans_without_analysis_views():
    profiler = ResolutionProfiler()
    first, _ = composition()
    second, boundary = composition()
    saved = []
    second.add_validation_rule(lambda context: saved.append(capture(context.graph)) or ())
    boundary.add_validation_rule(lambda context: saved.append(capture(context.graph)) or ())
    with (
        first.build(instrumentation=Instrumentation(profiler)) as first_runtime,
        second.build(instrumentation=Instrumentation(profiler)) as second_runtime,
    ):
        assert isinstance(first_runtime.resolve(Service), Service)
        assert isinstance(second_runtime.resolve(Service), Service)
    assert saved == []
    assert len(profiler.report().executions) == 2


def test_foreign_failure_during_exhaustion_does_not_override_budget(monkeypatch):
    foreign = ContainerBuildError("Saved failure", code="foreign")
    builder, _ = composition()

    def interrupted_snapshot(build_args, state):
        try:
            state.admit("preparation_operations", "discovery and blueprint preparation")
        except BaseException:
            raise foreign

    monkeypatch.setattr(builder, "_compilation_snapshot", interrupted_snapshot)
    caught_analysis = builder.analyse(budget=CompilationBudget(preparation_operations=0))
    assert not caught_analysis.report.is_valid
    assert caught_analysis.report.errors[-1].code == "compilation-budget-exceeded"
    assert caught_analysis.report is not None
    assert {issue.code for issue in caught_analysis.report.errors} == {"foreign", "compilation-budget-exceeded"}
    assert foreign.code == "foreign"
    assert foreign.report is None
    assert foreign.diagnostics_enabled


@pytest.mark.parametrize("failure", ["raise", "malformed", "async"])
def test_rule_callback_failures_capture_rule_origin_without_replay(failure):
    builder, _ = composition()
    saved = []
    calls = []

    async def asynchronous_result():
        return ()

    def rule(context):
        calls.append("rule")
        saved.append(capture(context.graph))
        if failure == "raise":
            raise ValueError("Deliberate callback error")
        if failure == "async":
            return asynchronous_result()
        return [object()]

    builder.add_validation_rule(rule)
    caught_analysis = builder.analyse()
    assert not caught_analysis.report.is_valid
    error = caught_analysis
    assert error.report.errors[0].code == "validation-rule-error"
    assert error.report._evidence[0] is not None and error.report._evidence[0].source_location is not None
    assert calls == ["rule"]
    assert_readable(saved)


def test_selection_callback_failure_retains_actual_origin_and_candidate_without_replay():
    calls = []
    builder = ContainerBuilder().set_provider_roots(())
    registration = builder.register(Leaf, root_policy="dependency_only")

    def fail(component):
        calls.append(component.id)
        raise ValueError("Deliberate selection failure")

    builder.register(Service, arguments={"leaf": select(fail)})
    caught_analysis = builder.analyse()
    assert not caught_analysis.report.is_valid
    error = caught_analysis
    assert calls == [registration, registration]
    fact = error.report._evidence[0]
    assert fact is not None and fact.selection_witness is not None
    assert fact.source_location is not None
    assert fact.selection_witness.component_id == registration
    assert fact.selection_witness.reason_codes == ("selection-callback-error",)
    assert fact.witness == error.report.errors[0].path
