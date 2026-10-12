"""Default builds retain executable/safety facts without optional compiler history."""

import gc
import weakref
from typing import Any, cast

import pytest

from clean_ioc import (
    BuilderAlreadyBuiltError,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    Instrumentation,
    Provider,
    ResolutionProfiler,
    ScopeBuilder,
    ServiceGroup,
)
from clean_ioc import component_filters as cf
from clean_ioc.cli import _load_analysis
from clean_ioc.container import _Compiler
from clean_ioc.matrix import BuildMatrix, BuildVariant


class Leaf:
    pass


class Service:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class Wrapper(Service):
    def __init__(self, inner: Service):
        self.inner = inner


def builder():
    result = ContainerBuilder()
    result.register(Leaf)
    result.register(Service)
    return result


@pytest.mark.parametrize("operation", ["build", "analyse"])
def test_graph_runtime_profiles_and_rules_follow_the_named_operation(operation):
    callbacks = []
    result = ContainerBuilder()
    result.register_fallback(Leaf)
    result.register(Service)
    result.register_decorator(Service, Wrapper)

    def safety(context):
        root = next(root for root in context.graph.roots if root.requested_type is Service)
        selection = context.graph.explain(root.component.dependencies[0]).selected
        callbacks.append((selection[0].origin.layer, selection[0].reason_codes))
        assert "selected-fallback" in selection[0].reason_codes
        assert context.graph.explain_decorators(root.component).selected
        assert context.graph.ownership_report().records
        return ()

    result.add_validation_rule(safety)
    compiler, runtime = CompilationProfiler(), ResolutionProfiler()
    if operation == "analyse":
        analysis = result.analyse(profile=compiler)
        assert analysis.graph.diagnostics_enabled
        assert analysis.report.is_valid
        scope = analysis.create_runtime(instrumentation=Instrumentation(runtime))
    else:
        scope = result.build(profile=compiler, instrumentation=Instrumentation(runtime))
    with scope:
        assert isinstance(cast(Wrapper, scope.resolve(Service)).inner.leaf, Leaf)
        assert isinstance(cast(Wrapper, scope.resolve(Provider[Service])()).inner.leaf, Leaf)
        assert scope.components
        assert runtime.report().records
        assert compiler.report().counters
    if operation == "analyse":
        assert callbacks[0][0] == "root"
        analysis.close()
    else:
        assert callbacks == []


def test_execution_has_no_diagnostics_and_analysis_has_completed_inspection():
    with builder().build() as runtime:
        assert not hasattr(runtime, "graph")
        assert not hasattr(runtime, "validation_report")
    with builder().analyse() as result:
        root = next(root.component for root in result.graph.roots if root.requested_type is Service)
        facts = result.graph.explain(root)
        assert facts.selected[0].origin.layer == "root"
        assert facts == result.graph.explain(root)
        assert facts.to_json()
        assert result.graph.explain(Service).selected
        assert result.graph.explain_arguments(root)
        assert result.selection_census()
    composition = builder()
    composition.add_validation_rule(lambda context: pytest.fail("Build ran a rule"))
    with composition.build() as runtime:
        assert isinstance(runtime.resolve(Service), Service)
    with pytest.raises(BuilderAlreadyBuiltError):
        composition.build()


def test_failed_analysis_aggregates_independent_roots_and_fresh_composition_can_repair():
    class Missing:
        pass

    class First:
        def __init__(self, missing: Missing):
            pass

    class Second:
        def __init__(self, missing: Missing):
            pass

    def composition():
        result = ContainerBuilder()
        result.register(First)
        result.register(Second)
        return result

    failed = composition()
    result = failed.analyse()
    assert len(result.report.errors) == result.report.checked_roots == 2
    assert all(issue.code == "missing-component" for issue in result.report.errors)
    assert result.partial_graph is not None
    assert result.selection_census()
    with pytest.raises(BuilderAlreadyBuiltError):
        failed.register(Missing)
    repaired = composition()
    repaired.register(Missing)
    with repaired.build() as scope:
        assert isinstance(scope.resolve(First), First)


@pytest.mark.parametrize("parent_operation", ["build", "analyse"])
def test_overlay_preserves_parent_selection_origins_ownership_and_local_diagnostic_mode(parent_operation):
    result = ContainerBuilder()
    result.register(Leaf, lifespan="singleton")
    result.register(Service, lifespan="singleton")
    parent_composition = result.retain_composition()
    output = getattr(result, parent_operation)()
    parent = output.create_runtime() if parent_operation == "analyse" else output
    with parent:
        original = parent.resolve(Service)
        child_builder = ScopeBuilder(parent, composition=parent_composition)
        child_builder.register(str, instance="child")
        with child_builder.analyse() as child_analysis, child_analysis.create_runtime() as child:
            assert child.resolve(Service) is original
            assert child.resolve(str) == "child"
            root = next(root.component for root in child_analysis.graph.roots if root.requested_type is Service)
            assert child_analysis.graph.explain(root).selected[0].origin.layer == "root"
            assert child_analysis.graph.ownership_report().records
            assert child_analysis.graph.diagnostics_enabled
            with pytest.raises(ValueError, match="explain-arguments-not-recorded"):
                child_analysis.graph.explain_arguments(root)


def test_template_decorator_source_safety_facts_do_not_require_diagnostic_history():
    class Source:
        pass

    result = ContainerBuilder()
    result.register(Source)
    group = ServiceGroup("services", service_type=Service)
    result.register(Leaf)
    result.register(Service, groups=[group])
    calls = []

    def template(source):
        calls.append(source.id)
        return DecoratorTemplate(group, Wrapper)

    template_id = result.register_decorator_template(for_each=Source, template=template)
    with result.analyse() as scope_analysis, scope_analysis.create_runtime() as scope:
        before = tuple(calls)
        root = next(root.component for root in scope_analysis.graph.roots if root.requested_type is Service)
        assert scope_analysis.graph.explain_template_sources(template_id)[0].selected
        fact = scope_analysis.graph.explain_decorators(root).selected[0].template
        assert fact is not None and fact.template_id == template_id
        assert isinstance(cast(Wrapper, scope.resolve(Service)).inner.leaf, Leaf)
        assert tuple(calls) == before


def test_validation_entrypoints_analyse_once_and_never_recompile_reports(monkeypatch):
    calls = []
    original = ContainerBuilder.analyse

    def capture(self, **kwargs):
        calls.append("analyse")
        return original(self, **kwargs)

    monkeypatch.setattr(ContainerBuilder, "analyse", capture)
    with _load_analysis("tests.tooling_targets:valid_builder") as result:
        assert result.graph.diagnostics_enabled
        result.report.to_json()
        result.report.to_sarif()
    report = BuildMatrix((BuildVariant("one", builder),), reference="one").check()
    assert report.is_valid
    assert calls == ["analyse", "analyse"]


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_diagnostic_flag_rejects_non_bool_before_consuming_builder(value):
    result = builder()
    with pytest.raises(TypeError, match="diagnostics"):
        result.build(diagnostics=value)
    scope_composition = result.retain_composition()
    with result.build() as scope:
        child = ScopeBuilder(scope, composition=scope_composition)
        with pytest.raises(TypeError, match="diagnostics"):
            child.build(diagnostics=value)  # ty: ignore[unknown-argument]  # Deliberately invalid input.
        child.build().__exit__()


def wide_builder():
    result = ContainerBuilder()
    previous = Leaf
    result.register(Leaf, root_policy="dependency_only")
    for index in range(8):

        def init(self, dependency):
            self.dependency = dependency

        init.__annotations__ = {"dependency": previous}
        previous = type(f"Middle{index}", (), {"__init__": init})
        result.register(previous, root_policy="dependency_only")
    for index in range(80):

        def init(self, dependency):
            self.dependency = dependency

        init.__annotations__ = {"dependency": previous}
        result.register(type(f"Root{index}", (), {"__init__": init}))
    return result


def test_wide_execution_has_no_analysis_owners_and_same_selected_catalogue():
    # Relative memory comparisons belong to task25; this is a structural assertion.
    with wide_builder().build() as execution, wide_builder().analyse() as result:
        assert not hasattr(execution._plan, "compiled_graph")
        assert not hasattr(execution._plan, "occurrence_explanations")
        assert not hasattr(execution._plan, "_blueprint")
        assert [
            (r.service_type.__qualname__, r.implementation_type.__qualname__) for r in execution.selected_registrations
        ] == [(r.service_type.__qualname__, r.implementation_type.__qualname__) for r in result.selected_registrations]
        assert len(result.graph.roots) >= 80


@pytest.mark.parametrize("diagnostics", [False, True])
def test_frozen_plans_do_not_retain_compilers(diagnostics, monkeypatch):
    references = []
    original = _Compiler.__init__

    def capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        references.append(weakref.ref(self))

    monkeypatch.setattr(_Compiler, "__init__", capture)
    with builder().build() as scope:
        assert isinstance(scope.resolve(Service), Service)
        gc.collect()
        assert references and all(reference() is None for reference in references)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_early_excluded_roots_keep_empty_automatic_provider_collections(diagnostics):
    from clean_ioc import AsyncManagedProvider, AsyncProvider, ManagedProvider

    result = ContainerBuilder()
    result.register(Service, candidate_when=cf.with_name("excluded"))
    with result.analyse() as scope_analysis, scope_analysis.create_runtime() as scope:
        assert not scope._plan.roots[Service]
        assert scope.resolve(Provider[list[Service]])() == []
        for family in (Provider, AsyncProvider, ManagedProvider, AsyncManagedProvider):
            assert scope._plan.provider_roots[family[Service]] == ()
            for form in (list[Service], tuple[Service, ...], set[Service]):
                assert len(scope._plan.provider_roots[family[form]]) == 1
        assert len(scope._plan.graph._records or ()) == 24
        if diagnostics:
            assert scope_analysis.graph.explain(list[Service]).rejected[0].reason_codes == ("rejected-candidate-when",)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_early_rejected_contextual_alternative_still_prevents_unsafe_subplan_reuse(diagnostics):
    class Alternative(Leaf):
        pass

    class First:
        def __init__(self, service: Service):
            self.service = service

    class Second(First):
        pass

    result = ContainerBuilder()
    result.register(Leaf, root_policy="dependency_only")
    result.register(Service, root_policy="dependency_only")
    result.register(First)
    second_id = result.register(Second)
    result.register(
        Leaf,
        Alternative,
        root_policy="dependency_only",
        candidate_when=cf.parent(cf.parent(cf.with_id(second_id))),
    )
    with result.build() as scope:
        assert type(scope.resolve(First).service.leaf) is Leaf
        assert type(scope.resolve(Second).service.leaf) is Alternative


@pytest.mark.parametrize("operation", ["build", "analyse"])
def test_late_rejected_components_escaped_from_callbacks_have_operation_lifetimes(operation):
    escaped = []

    def reject(component):
        escaped.append(component)
        return False

    result = ContainerBuilder()
    result.register(Leaf, root_policy="dependency_only")
    result.register(Service, when=reject)
    with getattr(result, operation)() as output:
        scope = output.create_runtime() if operation == "analyse" else output
        assert not scope._plan.roots[Service]
        component = escaped[0]
        if operation == "build":
            with pytest.raises(RuntimeError, match="expired"):
                _ = component.service_type
            return
        assert component.service_type is Service
        assert component.dependencies[0].service_type is Leaf
        assert component.dependencies[0].parent.occurrence_id == component.occurrence_id


@pytest.mark.parametrize("diagnostics", [False, True])
def test_failed_build_early_exclusions_retain_full_evidence_only_when_requested(diagnostics):
    result = ContainerBuilder()
    result.register(Leaf, candidate_when=cf.with_name("excluded"), root_policy="dependency_only")
    result.register(Service)
    if not diagnostics:
        with pytest.raises(ContainerBuildError) as raised:
            result.build()
        assert raised.value.report is raised.value.partial_graph is None
        assert raised.value.code == "missing-component"
        return
    caught_analysis = result.analyse()
    assert not caught_analysis.report.is_valid
    assert caught_analysis.report is not None
    assert caught_analysis.report.errors[0].code == "missing-component"
    if diagnostics:
        assert caught_analysis.partial_graph is not None
        assert any(
            node.state.value == "rejected" and node.issue_code == "rejected-candidate-when"
            for attempt in caught_analysis.partial_graph.attempts
            for node in attempt.nodes
        )
        assert any(
            "rejected-candidate-when" in decision.reason_codes
            for explanation in caught_analysis.report._explanations
            for decision in explanation.rejected
        )


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("factory", [False, True])
@pytest.mark.parametrize("boundary", [False, True])
def test_specialized_fallback_facts_survive_aliases_boundaries_and_overlay_anchors(diagnostics, factory, boundary):
    from typing import Generic, TypeVar

    from typing_extensions import TypeAliasType

    from clean_ioc import Expose

    item = TypeVar("item")

    class Contract(Generic[item]):
        pass

    class Default(Contract[item]):
        def __init__(self, value: item):
            self.value = value

    def make(value: item) -> Contract[item]:
        return Default(value)

    alias = TypeAliasType("alias", Contract[int])

    class Consumer:
        def __init__(self, value):
            self.value = value

    Consumer.__init__.__annotations__ = {"value": alias}
    result = ContainerBuilder()
    result.register(int, instance=5)
    source = result.create_boundary("fallback", exposes=[Expose(Contract[int]), Expose(int)]) if boundary else result
    if boundary:
        source.register(int, instance=5)
    if factory:
        source.register_fallback(
            Contract[int] if boundary else Contract,
            factory=make,
            lifespan="singleton",
            factory_specialization=Contract[int] if boundary else None,
        )
    else:
        source.register_fallback(cast(Any, Contract[int] if boundary else Contract), Default, lifespan="singleton")
    result.register(Consumer)
    with result.analyse() as parent_analysis:
        parent = parent_analysis.create_runtime()
        original = parent.resolve(Consumer).value
        with ScopeBuilder(parent, composition=parent_analysis.composition).analyse() as child_analysis:
            child = child_analysis.create_runtime()
            for analysis, runtime in ((parent_analysis, parent), (child_analysis, child)):
                root = next(root.component for root in analysis.graph.roots if root.requested_type is Consumer)
                dependency = root.dependencies[0]
                decision = analysis.graph.explain(dependency).selected[0]
                assert "selected-fallback" in decision.reason_codes
                assert decision.origin.layer == "root"
                assert runtime.resolve(Consumer).value is original


def test_default_and_enabled_preference_callbacks_follow_identical_reached_stages():
    from clean_ioc import prefer, select

    def run(diagnostics):
        calls = []
        result = ContainerBuilder()
        result.register(Leaf, name="first")
        result.register(Leaf, name="second")

        def stage(component):
            calls.append(component.name)
            return component.name == "first"

        result.register(Service, arguments={"leaf": select(cf.all_components, prefer=prefer(stage))})
        with result.analyse() as scope_analysis, scope_analysis.create_runtime() as scope:
            root = next(root.component for root in scope_analysis.graph.roots if root.requested_type is Service)
            assert root.dependencies[0].name == "first"
            assert isinstance(scope.resolve(Service).leaf, Leaf)
        return calls

    assert run(False) == run(True) == ["second", "first"]


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("phase", ["preparation", "compilation", "recovery"])
def test_budget_failures_preserve_requested_mode_before_during_and_after_compilation(diagnostics, phase):
    from clean_ioc import CompilationBudget

    result = builder()
    if phase == "preparation":
        result = ContainerBuilder()
        result.register_subclasses(Leaf, ensure_import_modules="this_module_must_not_be_imported")
        budget = CompilationBudget(preparation_operations=0)
        expected = "discovery imports"
    elif phase == "compilation":
        budget = CompilationBudget(graph_occurrences=0)
        expected = "primary compilation"
    else:
        result = ContainerBuilder()
        result.register(Service)
        budget = CompilationBudget(diagnostic_attempts=0)
        expected = "diagnostic root retries"
    if not diagnostics:
        with pytest.raises(ContainerBuildError) as raised:
            result.build(budget=budget)
        assert raised.value.report is raised.value.partial_graph is None
        assert raised.value.code == ("missing-component" if phase == "recovery" else "compilation-budget-exceeded")
        return
    caught_analysis = result.analyse(budget=budget)
    assert not caught_analysis.report.is_valid
    error = caught_analysis
    assert error.partial_graph is not None
    assert error.report is not None
    finding = next(issue for issue in error.report.errors if issue.code == "compilation-budget-exceeded")
    assert finding.budget is not None and finding.budget.phase == expected
    assert error.report._evidence
    if phase == "recovery":
        assert any(issue.code == "missing-component" for issue in error.report.errors)
    assert error.selection_census()


@pytest.mark.parametrize("diagnostics", [False, True])
def test_precompiler_failure_reports_requested_mode(diagnostics):
    from clean_ioc import WarmupPlan

    result = builder()
    result.add_warmup_plan(WarmupPlan("start", [cast(Any, Service)]))
    if not diagnostics:
        with pytest.raises(ContainerBuildError) as raised:
            result.build()
        assert raised.value.report is raised.value.partial_graph is None
        return
    caught_analysis = result.analyse()
    assert not caught_analysis.report.is_valid
    assert "warmup" in str(caught_analysis.report)


def test_default_selection_membership_rejects_foreign_and_reduced_graphs_without_path_capture():
    from dataclasses import replace

    with builder().analyse() as scope_analysis, scope_analysis.create_runtime() as _scope:
        graph = scope_analysis.graph
        root = next(root.component for root in graph.roots if root.requested_type is Service)
        assert graph.explain(root).selected
        reduced = replace(
            graph, roots=tuple(candidate for candidate in graph.roots if candidate.requested_type is Leaf)
        )
        # Captured occurrence evidence remains available even when a display
        # projection omits a root; foreign graphs still fail membership below.
        assert reduced.explain(root).selected
        assert graph.explain(root).selected
        with builder().analyse() as other_analysis, other_analysis.create_runtime() as _other:
            foreign = next(
                candidate.component for candidate in other_analysis.graph.roots if candidate.requested_type is Service
            )
            with pytest.raises(ValueError, match="different compiled graph"):
                graph.explain(foreign)
        assert graph.explain(root).selected


def test_builder_previews_keep_structural_filter_parent_facts_without_capturing_history(monkeypatch):
    modes = []
    original = _Compiler.__init__

    def capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        modes.append(self._diagnostics)

    def structural(component):
        if component.service_type is not Service:
            return False
        assert len(component.dependencies) == 1
        child = component.dependencies[0]
        assert child.service_type is Leaf and child.parent.occurrence_id == component.occurrence_id
        return True

    monkeypatch.setattr(_Compiler, "__init__", capture)
    result = builder()
    assert result.has_component(Service, filter=structural)
    service_id = result.get_component_id(Service, filter=structural)
    assert service_id is not None
    result.patch_component(Service, service_id, lifespan="transient")
    scope_composition = result.retain_composition()
    with result.build() as scope:
        assert isinstance(scope.resolve(Service).leaf, Leaf)
        child = ScopeBuilder(scope, composition=scope_composition)
        assert child.has_component(Service, filter=structural)
        with child.build() as overlay:
            assert isinstance(overlay.resolve(Service).leaf, Leaf)
    assert modes and not any(modes)


@pytest.mark.parametrize("operation", ["build", "analyse"])
def test_cli_profile_selects_the_named_operation(operation, monkeypatch, capsys):
    from clean_ioc.cli import main

    calls = []
    original = getattr(ContainerBuilder, operation)

    def capture(self, **kwargs):
        calls.append(operation)
        return original(self, **kwargs)

    monkeypatch.setattr(ContainerBuilder, operation, capture)
    assert main(["profile", "tests.tooling_targets:valid_builder", "--format", "json", "--operation", operation]) == 0
    assert calls == [operation]
    assert '"state": "completed"' in capsys.readouterr().out
