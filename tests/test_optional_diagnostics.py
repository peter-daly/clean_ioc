"""Default builds retain executable/safety facts without optional compiler history."""

import gc
import tracemalloc
import weakref
from typing import Any, cast

import pytest

from clean_ioc import (
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    DecoratorTemplate,
    Instrumentation,
    Provider,
    ResolutionProfiler,
    ServiceGroup,
)
from clean_ioc import component_filters as cf
from clean_ioc.cli import _load_scope
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


@pytest.mark.parametrize("diagnostics", [False, True])
def test_graph_runtime_profiles_and_safety_rules_survive_both_modes(diagnostics):
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
    compiler = CompilationProfiler()
    runtime = ResolutionProfiler()
    with result.build(diagnostics=diagnostics, profile=compiler, instrumentation=Instrumentation(runtime)) as scope:
        assert scope.graph.diagnostics_enabled is diagnostics
        assert isinstance(cast(Wrapper, scope.resolve(Service)).inner.leaf, Leaf)
        assert isinstance(cast(Wrapper, scope.resolve(Provider[Service])()).inner.leaf, Leaf)
        assert scope.components
        assert scope.validation_report().is_valid
        assert runtime.report().records
        assert compiler.report().counters
    assert callbacks[0][0] == "root"


def test_default_diagnostics_are_explicitly_unavailable_and_builder_is_reusable():
    result = builder()
    with result.build() as scope:
        root = next(root.component for root in scope.graph.roots if root.requested_type is Service)
        facts = scope.graph.explain(root)
        assert facts.selected[0].origin.layer == "root"
        assert "diagnostics=True" in repr(facts)
        assert facts == facts
        assert not scope.graph._occurrence_paths_cache
        for operation in (
            lambda: scope.graph.explain(root).rejected,
            lambda: scope.graph.explain(root).path,
            lambda: scope.graph.explain(root).selected[0].preferences,
            lambda: scope.graph.explain(root).selected[0].parent_precedence,
            lambda: scope.graph.explain(root).selected[0].template,
            lambda: scope.graph.explain(root).to_json(),
            lambda: scope.graph.explain(Service),
            lambda: scope.graph.explain_arguments(root),
            lambda: scope.graph.explain_specialization(root),
            scope.graph.selection_census,
        ):
            with pytest.raises(ValueError, match="diagnostics-disabled.*diagnostics=True"):
                operation()
    result = builder()
    result.add_validation_rule(lambda context: context.graph.explain_arguments(context.graph.roots[0].component))
    with pytest.raises(ContainerBuildError, match="diagnostics=True"):
        result.build()
    assert not result._built


@pytest.mark.parametrize("diagnostics", [False, True])
def test_failed_builds_still_aggregate_independent_roots_and_can_be_repaired(diagnostics):
    class Missing:
        pass

    class First:
        def __init__(self, missing: Missing):
            pass

    class Second:
        def __init__(self, missing: Missing):
            pass

    result = ContainerBuilder()
    result.register(First)
    result.register(Second)
    with pytest.raises(ContainerBuildError) as caught:
        result.build(diagnostics=diagnostics)
    error = caught.value
    assert error.report is not None
    assert len(error.report.errors) == 2
    assert error.report.checked_roots == 2
    assert all(issue.code == "missing-component" for issue in error.report.errors)
    assert error.diagnostics_enabled is diagnostics
    assert (error.partial_graph is not None) is diagnostics
    if not diagnostics:
        with pytest.raises(ValueError, match="diagnostics=True"):
            error.selection_census()
    result.register(Missing)
    with result.build(diagnostics=diagnostics) as scope:
        assert isinstance(scope.resolve(First), First)


@pytest.mark.parametrize("parent_diagnostics", [False, True])
@pytest.mark.parametrize("child_diagnostics", [False, True])
def test_overlay_preserves_parent_selection_origins_ownership_and_local_diagnostic_mode(
    parent_diagnostics, child_diagnostics
):
    result = ContainerBuilder()
    result.register(Leaf, lifespan="singleton")
    result.register(Service, lifespan="singleton")
    with result.build(diagnostics=parent_diagnostics) as parent:
        original = parent.resolve(Service)
        child_builder = parent.new_scope_builder()
        child_builder.register(str, instance="child")
        with child_builder.build(diagnostics=child_diagnostics) as child:
            assert child.resolve(Service) is original
            assert child.resolve(str) == "child"
            root = next(root.component for root in child.graph.roots if root.requested_type is Service)
            assert child.graph.explain(root).selected[0].origin.layer == "root"
            assert child.graph.ownership_report().records
            assert child.graph.diagnostics_enabled is child_diagnostics
            if not child_diagnostics:
                with pytest.raises(ValueError, match="diagnostics=True"):
                    child.graph.explain_arguments(root)


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
    with result.build() as scope:
        before = tuple(calls)
        root = next(root.component for root in scope.graph.roots if root.requested_type is Service)
        assert scope.graph.explain_template_sources(template_id)[0].selected
        fact = scope.graph.explain_decorators(root).selected[0].template
        assert fact is not None and fact.template_id == template_id
        assert isinstance(cast(Wrapper, scope.resolve(Service)).inner.leaf, Leaf)
        assert tuple(calls) == before


def test_validation_entrypoints_request_diagnostics_without_recompiling_existing_scopes(monkeypatch):
    flags = []
    original = ContainerBuilder.build

    def capture(self, **kwargs):
        flags.append(kwargs.get("diagnostics", False))
        return original(self, **kwargs)

    monkeypatch.setattr(ContainerBuilder, "build", capture)
    with _load_scope("tests.tooling_targets:valid_builder") as scope:
        assert scope.graph.diagnostics_enabled
    report = BuildMatrix((BuildVariant("one", builder),), reference="one").check()
    assert report.is_valid
    assert flags == [True, True]
    with builder().build() as scope:
        scope.validation_report()
        assert flags == [True, True, False]
        assert not scope.graph.diagnostics_enabled


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_diagnostic_flag_rejects_non_bool_before_consuming_builder(value):
    result = builder()
    with pytest.raises(TypeError, match="diagnostics must be a bool"):
        result.build(diagnostics=cast(Any, value))
    with result.build() as scope:
        child = scope.new_scope_builder()
        with pytest.raises(TypeError, match="diagnostics must be a bool"):
            child.build(diagnostics=cast(Any, value))
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


def test_default_build_allocations_drop_without_changing_the_compiled_graph():
    def measure(diagnostics):
        result = wide_builder()
        gc.collect()
        tracemalloc.start()
        try:
            scope = result.build(diagnostics=diagnostics)
            gc.collect()
            retained, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        fingerprint = scope.graph.manifest(all_roots=True).fingerprint
        scope.__exit__()
        return retained, peak, fingerprint

    # Warm reflection caches before comparing compiler allocations.
    wide_builder().build().__exit__()
    plain, rich = measure(False), measure(True)
    assert plain[2] == rich[2]
    assert plain[0] < rich[0] * 0.8
    assert plain[1] < rich[1] * 0.9


@pytest.mark.parametrize("diagnostics", [False, True])
def test_frozen_plans_do_not_retain_compilers(diagnostics, monkeypatch):
    references = []
    original = _Compiler.__init__

    def capture(self, *args, **kwargs):
        original(self, *args, **kwargs)
        references.append(weakref.ref(self))

    monkeypatch.setattr(_Compiler, "__init__", capture)
    with builder().build(diagnostics=diagnostics) as scope:
        assert isinstance(scope.resolve(Service), Service)
        gc.collect()
        assert references and all(reference() is None for reference in references)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_early_excluded_roots_keep_empty_automatic_provider_collections(diagnostics):
    from clean_ioc import AsyncManagedProvider, AsyncProvider, ManagedProvider

    result = ContainerBuilder()
    result.register(Service, candidate_when=cf.with_name("excluded"))
    with result.build(diagnostics=diagnostics) as scope:
        assert not scope._plan.roots[Service]
        assert scope.resolve(Provider[list[Service]])() == []
        for family in (Provider, AsyncProvider, ManagedProvider, AsyncManagedProvider):
            assert scope._plan.provider_roots[family[Service]] == ()
            for form in (list[Service], tuple[Service, ...], set[Service]):
                assert len(scope._plan.provider_roots[family[form]]) == 1
        assert len(scope._plan.graph._records or ()) == 24 + int(diagnostics)
        if diagnostics:
            assert scope.graph.explain(list[Service]).rejected[0].reason_codes == ("rejected-candidate-when",)


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
    with result.build(diagnostics=diagnostics) as scope:
        assert type(scope.resolve(First).service.leaf) is Leaf
        assert type(scope.resolve(Second).service.leaf) is Alternative


def test_late_rejected_components_escaped_from_callbacks_remain_readable():
    escaped = []

    def reject(component):
        escaped.append(component)
        return False

    result = ContainerBuilder()
    result.register(Leaf, root_policy="dependency_only")
    result.register(Service, when=reject)
    with result.build() as scope:
        assert not scope._plan.roots[Service]
        component = escaped[0]
        assert component.service_type is Service
        assert component.dependencies[0].service_type is Leaf
        assert component.dependencies[0].parent.occurrence_id == component.occurrence_id


@pytest.mark.parametrize("diagnostics", [False, True])
def test_failed_build_early_exclusions_retain_full_evidence_only_when_requested(diagnostics):
    result = ContainerBuilder()
    result.register(Leaf, candidate_when=cf.with_name("excluded"), root_policy="dependency_only")
    result.register(Service)
    with pytest.raises(ContainerBuildError) as caught:
        result.build(diagnostics=diagnostics)
    assert caught.value.report is not None
    assert caught.value.report.errors[0].code == "missing-component"
    if diagnostics:
        assert caught.value.partial_graph is not None
        assert any(
            node.state.value == "rejected" and node.issue_code == "rejected-candidate-when"
            for attempt in caught.value.partial_graph.attempts
            for node in attempt.nodes
        )
        assert any(
            "rejected-candidate-when" in decision.reason_codes
            for explanation in caught.value.explanations
            for decision in explanation.rejected
        )
    else:
        assert caught.value.partial_graph is None


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
    with result.build(diagnostics=diagnostics) as parent:
        original = parent.resolve(Consumer).value
        for scope in (parent, parent.new_scope_builder().build(diagnostics=diagnostics)):
            root = next(root.component for root in scope.graph.roots if root.requested_type is Consumer)
            dependency = root.dependencies[0]
            decision = scope.graph.explain(dependency).selected[0]
            assert "selected-fallback" in decision.reason_codes
            assert decision.origin.layer == "root"
            assert scope.resolve(Consumer).value is original
            if scope is not parent:
                scope.__exit__()


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
        with result.build(diagnostics=diagnostics) as scope:
            root = next(root.component for root in scope.graph.roots if root.requested_type is Service)
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
    with pytest.raises(ContainerBuildError) as caught:
        result.build(diagnostics=diagnostics, budget=budget)
    error = caught.value
    assert error.diagnostics_enabled is diagnostics
    assert (error.partial_graph is not None) is diagnostics
    assert error.report is not None
    finding = next(issue for issue in error.report.errors if issue.code == "compilation-budget-exceeded")
    assert finding.budget is not None and finding.budget.phase == expected
    assert error.evidence
    if phase == "recovery":
        assert any(issue.code == "missing-component" for issue in error.report.errors)
    if not diagnostics:
        with pytest.raises(ValueError, match="diagnostics=True"):
            error.selection_census()


@pytest.mark.parametrize("diagnostics", [False, True])
def test_precompiler_failure_reports_requested_mode(diagnostics):
    from clean_ioc import WarmupPlan

    result = builder()
    result.add_warmup_plan(WarmupPlan("start", [cast(Any, Service)]))
    with pytest.raises(ContainerBuildError) as caught:
        result.build(diagnostics=diagnostics)
    assert caught.value.diagnostics_enabled is diagnostics
    assert "warmup" in str(caught.value)


def test_default_selection_membership_rejects_foreign_and_reduced_graphs_without_path_capture():
    from dataclasses import replace

    with builder().build() as scope:
        graph = scope.graph
        root = next(root.component for root in graph.roots if root.requested_type is Service)
        assert graph.explain(root).selected
        reduced = replace(
            graph, roots=tuple(candidate for candidate in graph.roots if candidate.requested_type is Leaf)
        )
        with pytest.raises(ValueError, match="does not belong to this compiled graph"):
            reduced.explain(root)
        assert graph.explain(root).selected
        with builder().build() as other:
            foreign = next(
                candidate.component for candidate in other.graph.roots if candidate.requested_type is Service
            )
            with pytest.raises(ValueError, match="different compiled graph"):
                graph.explain(foreign)
        assert not graph._occurrence_paths_cache


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
    with result.build() as scope:
        assert isinstance(scope.resolve(Service).leaf, Leaf)
        child = scope.new_scope_builder()
        assert child.has_component(Service, filter=structural)
        with child.build() as overlay:
            assert isinstance(overlay.resolve(Service).leaf, Leaf)
    assert modes and not any(modes)


@pytest.mark.parametrize("arguments, enabled", [([], False), (["--diagnostics"], True)])
def test_cli_profile_measures_requested_diagnostic_mode(arguments, enabled, monkeypatch, capsys):
    from clean_ioc.cli import main

    modes = []
    original = ContainerBuilder.build

    def capture(self, **kwargs):
        scope = original(self, **kwargs)
        modes.append(scope.graph.diagnostics_enabled)
        scope.__exit__()
        return scope

    monkeypatch.setattr(ContainerBuilder, "build", capture)
    assert main(["profile", "tests.tooling_targets:valid_builder", "--format", "json", *arguments]) == 0
    assert modes == [enabled]
    assert '"state": "completed"' in capsys.readouterr().out
