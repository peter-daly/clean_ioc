"""Early reuse skips invariant dependency compilation, retaining occurrence evidence."""

import gc
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Generic, TypeVar

import pytest

from clean_ioc import (
    BuildIssue,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    IssueSeverity,
    ResolutionContext,
    ResolutionProfiler,
    derive,
)
from clean_ioc.container import _Compiler, _RegistrationStep


class Leaf:
    pass


class Infrastructure:
    def __init__(self, first: Leaf, second: Leaf):
        self.first, self.second = first, second


def shared_builder(
    count, *, leaf_options: dict[str, Any] | None = None, infrastructure_options: dict[str, Any] | None = None
):
    builder = ContainerBuilder()
    builder.register(
        Leaf, root_policy="dependency_only", **dict[str, Any]({"lifespan": "transient"} | (leaf_options or {}))
    )
    builder.register(
        Infrastructure,
        root_policy="dependency_only",
        **dict[str, Any]({"lifespan": "transient"} | (infrastructure_options or {})),
    )
    routes: list[Any] = []
    for index in range(count):

        def init(self, infrastructure):
            self.infrastructure = infrastructure

        init.__annotations__ = {"infrastructure": Infrastructure}
        route = type(f"Route{index}", (), {"__init__": init})
        builder.register(route)
        routes.append(route)
    return builder, routes


@pytest.mark.parametrize("count", [2, 8, 32])
def test_shared_infrastructure_compiles_its_dependencies_once_with_distinct_paths(count, monkeypatch):
    dependency_calls = []
    original = _Compiler._compile_dependencies

    def record(self, dependencies, parent):
        dependency_calls.append(parent.service_type)
        return original(self, dependencies, parent)

    monkeypatch.setattr(_Compiler, "_compile_dependencies", record)
    builder, routes = shared_builder(count)
    profile = CompilationProfiler(max_records=0)
    runtime = ResolutionProfiler()
    with builder.build(profile=profile, instrumentation=Instrumentation(runtime), diagnostics=True) as owner:
        assert dependency_calls.count(Infrastructure) == 1
        assert dependency_calls.count(Leaf) == 1
        leaves = []
        for route in routes:
            component = owner._plan.roots[route][0].component.dependencies[0]
            assert component.parent.service_type is route
            assert component.argument == "infrastructure"
            assert component.dependencies[0].argument == "first"
            assert component.dependencies[0].parent.occurrence_id == component.occurrence_id
            explanation = owner.graph.explain(component.dependencies[0])
            assert route.__name__ in explanation.path[0]
            arguments = owner.graph.explain_arguments(component)
            assert "dependency:first" in arguments[0].selected_components[0]
            assert "dependency:second" in arguments[1].selected_components[0]
            value = owner.resolve(route)
            leaves += [value.infrastructure.first, value.infrastructure.second]
        assert len({id(leaf) for leaf in leaves}) == count * 2
        assert owner.graph.manifest(all_roots=True).to_json()
        runtime_paths = [record.path for record in runtime.report().records if record.attempts]
        assert all(
            any(route.__name__ in path and "dependency:first" in path for path in runtime_paths) for route in routes
        )
    counters = profile.report().counters.to_dict()
    assert counters["registration subplans compiled"] == count + 2
    assert counters["parameter processing attempts"] == count + 2
    assert counters["invariant subplan cache hits"] == count
    assert counters["physical component records"] == count * 32


def test_contextual_descendant_and_opaque_selection_are_never_skipped():
    seen = []

    def contextual(component):
        seen.append(component.parent.parent.service_type)
        return True

    # A user callable that has a built-in-looking name must still run.
    contextual.__name__ = "default_component_filter"
    builder, routes = shared_builder(3, leaf_options={"when": contextual})
    with builder.build() as owner:
        assert seen == [route for route in routes for _ in range(2)]
        assert all(isinstance(owner.resolve(route).infrastructure.first, Leaf) for route in routes)


def test_registration_own_callback_still_runs_for_every_reused_occurrence():
    seen = []
    builder, routes = shared_builder(
        4, infrastructure_options={"when": lambda component: seen.append(component.parent.service_type) or True}
    )
    profile = CompilationProfiler(max_records=0)
    with builder.build(profile=profile):
        assert seen == routes
    assert profile.report().counters.to_dict()["invariant subplan cache hits"] == len(routes)


@pytest.mark.parametrize("policy", ["derive", "context", "slot"])
def test_contextual_descendant_argument_paths_do_not_reuse_the_parent(policy):
    seen = []
    annotation = str if policy == "derive" else ResolutionContext if policy == "context" else Leaf

    def init(self, value):
        self.value = value

    init.__annotations__ = {"value": annotation}
    contextual = type("Contextual", (), {"__init__": init})
    builder = ContainerBuilder()

    def derived_value(context):
        assert context.component.parent is not None
        parent = context.component.parent.service_type
        seen.append(parent)
        return parent.__name__

    arguments = {"value": derive(derived_value)} if policy == "derive" else None
    builder.register(contextual, arguments=arguments, root_policy="dependency_only")
    if policy == "slot":
        builder.declare_scope_slot(Leaf)
    routes: list[Any] = []
    for index in range(3):

        def route_init(self, dependency):
            self.dependency = dependency

        route_init.__annotations__ = {"dependency": contextual}
        route = type(f"ContextRoute{index}", (), {"__init__": route_init})
        routes.append(route)
        builder.register(route)
    profile = CompilationProfiler(max_records=0)
    with builder.build(profile=profile) as owner:
        if policy == "derive":
            assert seen == routes
            assert [owner.resolve(route).dependency.value for route in routes] == [route.__name__ for route in routes]
        elif policy == "slot":
            supplied = Leaf()
            with owner.new_scope() as scope:
                scope.provide(Leaf, supplied)
                assert all(scope.resolve(route).dependency.value is supplied for route in routes)
        else:
            assert all(isinstance(owner.resolve(route).dependency.value, ResolutionContext) for route in routes)
    assert profile.report().counters.to_dict().get("invariant subplan cache hits", 0) == 0


def test_same_display_name_closed_generic_bindings_keep_real_identity():
    T = TypeVar("T")

    class Box(Generic[T]):
        pass

    first = type("Identical", (), {})
    second = type("Identical", (), {})
    builder = ContainerBuilder()
    builder.register(Box)
    builder.register(Box[first])
    builder.register(Box[second])
    for index, annotation in enumerate((Box[first], Box[second], Box[first], Box[second])):

        def init(self, box):
            self.box = box

        init.__annotations__ = {"box": annotation}
        route = type(f"GenericRoute{index}", (), {"__init__": init})
        builder.register(route)
    with builder.build() as owner:
        first_step = owner._plan.roots[Box[first]][0].step
        second_step = owner._plan.roots[Box[second]][0].step
        assert first_step is not second_step
        assert isinstance(first_step, _RegistrationStep)
        assert isinstance(second_step, _RegistrationStep)
        assert first_step.source_service_type == Box[first]
        assert second_step.source_service_type == Box[second]


def test_cached_safe_transient_subtree_cannot_bypass_ancestor_captive_validation():
    class Bad:
        def __init__(self, infrastructure: Infrastructure):
            pass

    builder, _ = shared_builder(2, leaf_options={"lifespan": "per_resolution"})
    builder.register(Bad, lifespan="singleton")
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert caught.value.report is not None
    assert any(issue.code == "captive-dependency" for issue in caught.value.report.errors)
    assert any("Bad" in item and "Leaf" in str(caught.value) for item in caught.value.report.errors[0].path)


@pytest.mark.asyncio
async def test_async_cleanup_reuse_keeps_scope_and_overlay_identity():
    closed = []

    @asynccontextmanager
    async def resource() -> AsyncIterator[Leaf]:
        value = Leaf()
        try:
            yield value
        finally:
            closed.append(value)

    builder, routes = shared_builder(3, leaf_options={"factory": resource, "lifespan": "scoped"})
    profile = CompilationProfiler(max_records=0)
    async with builder.build(profile=profile) as owner:
        async with owner.new_scope() as scope:
            values = [await scope.resolve_async(route) for route in routes]
            shared = values[0].infrastructure.first
            assert all(
                value.infrastructure.first is shared and value.infrastructure.second is shared for value in values
            )
        assert closed == [shared]
        async with owner.new_scope_builder().build() as overlay:
            value = await overlay.resolve_async(routes[0])
            assert value.infrastructure.first is not shared
    assert len(closed) == 2
    assert profile.report().counters.to_dict()["invariant subplan cache hits"] > 0


def test_failed_validation_and_partial_edges_use_the_reused_occurrence_path():
    builder, routes = shared_builder(2)

    def findings(context):
        for visit in context.graph.walk():
            if visit.component.service_type is Leaf and routes[1].__name__ in visit.path[0]:
                yield BuildIssue(code="reject-second", severity=IssueSeverity.error, message="second", path=visit.path)
                break

    builder.add_validation_rule(findings)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(diagnostics=True)
    assert caught.value.report is not None
    assert caught.value.partial_graph is not None
    issue = next(issue for issue in caught.value.report.errors if issue.code == "reject-second")
    assert routes[1].__name__ in issue.path[0]
    assert any(
        routes[1].__name__ in explanation.path[0] and "Infrastructure" in explanation.path[-1]
        for explanation in caught.value.explanations
    )
    attempts = caught.value.partial_graph.attempts
    assert any(edge.label == "first" for attempt in attempts for edge in attempt.edges)


def test_reused_subtree_checks_full_depth_and_physical_occurrence_budget():
    builder, _ = shared_builder(3)
    profile = CompilationProfiler(max_records=0)
    with builder.build(profile=profile, budget=CompilationBudget(graph_occurrences=144)):
        pass
    assert profile.report().counters.to_dict()["physical component records"] == 96
    assert dict(profile.report().budget_usage or ())["graph_occurrences"] == 144
    assert dict(profile.report().budget_usage or ())["active_dependency_depth"] == 5
    builder, _ = shared_builder(3)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(budget=CompilationBudget(graph_occurrences=143))
    assert caught.value.report is not None
    assert caught.value.report.errors[-1].code == "compilation-budget-exceeded"


def test_successful_cache_does_not_retain_compiler_with_gc_disabled(monkeypatch):
    compilers = []
    original = _Compiler.__init__

    def record(self, *args, **kwargs):
        original(self, *args, **kwargs)
        compilers.append(weakref.ref(self))

    monkeypatch.setattr(_Compiler, "__init__", record)
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        builder, _ = shared_builder(8)
        with builder.build():
            assert compilers and all(reference() is None for reference in compilers)
    finally:
        if was_enabled:
            gc.enable()


@pytest.mark.parametrize("declaration", ["decorator", "pre_configuration"])
def test_even_rejected_pipeline_callbacks_run_for_every_occurrence(declaration):
    calls = []
    builder, routes = shared_builder(3)

    def callback(component):
        calls.append(component.parent.service_type)
        return False

    def pipeline():
        raise AssertionError("Build invoked an activation callback")

    if declaration == "decorator":
        builder.register_decorator(Infrastructure, pipeline, when=callback)
    else:
        builder.pre_configure(Infrastructure, pipeline, when=callback)
    with builder.build():
        assert calls == routes


def test_cached_registration_footprint_does_not_hide_a_descendant_stack_cycle():
    builder, _ = shared_builder(0)
    blueprint, _ = builder._compilation_snapshot(None)
    compiler = _Compiler(blueprint)
    compiler._compile_candidates(Infrastructure, parent=None, argument=None)
    registration, _ = blueprint.registrations(Leaf)[0]
    # Simulate entry from an ancestor already compiling the cached descendant.
    # A registration-local cache key would otherwise reuse Infrastructure and
    # never reach the Leaf cycle check.
    compiler._stack.append(registration)
    with pytest.raises(ContainerBuildError) as caught:
        compiler._compile_candidates(Infrastructure, parent=None, argument=None)
    assert caught.value.code == "circular-dependency"
    assert "Leaf" in str(caught.value)


def test_reused_alias_dependencies_keep_each_declared_annotation():
    from typing_extensions import TypeAliasType

    first_alias = TypeAliasType("first_alias", Infrastructure)
    second_alias = TypeAliasType("second_alias", Infrastructure)
    builder, _ = shared_builder(0)
    routes = []
    for index, alias in enumerate((first_alias, second_alias)):

        def init(self, infrastructure):
            self.infrastructure = infrastructure

        init.__annotations__ = {"infrastructure": alias}
        route = type(f"AliasRoute{index}", (), {"__init__": init})
        routes.append(route)
        builder.register(route)
    profile = CompilationProfiler(max_records=0)
    with builder.build(profile=profile, diagnostics=True) as owner:
        for route, alias in zip(routes, (first_alias, second_alias), strict=True):
            root = owner._plan.roots[route][0].component
            evidence = owner.graph.explain_arguments(root)[0]
            assert alias.__name__ in evidence.declared_annotation
            assert "Infrastructure" in evidence.canonical_annotation
            assert route.__name__ in evidence.selected_components[0]
            target = root.dependencies[0]
            assert target.service_type is Infrastructure
            assert target.declared_service_type is Infrastructure
            assert route.__name__ in owner.graph.explain(target).path[0]
    assert profile.report().counters.to_dict()["invariant subplan cache hits"] == 2


def test_failed_build_retry_gets_a_new_cache_and_revalidates_required_roots(monkeypatch):
    dependency_calls = []
    original = _Compiler._compile_dependencies

    def record(self, dependencies, parent):
        if parent.service_type is Infrastructure:
            dependency_calls.append(parent.service_type)
        return original(self, dependencies, parent)

    monkeypatch.setattr(_Compiler, "_compile_dependencies", record)
    builder, routes = shared_builder(2)

    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            pass

    builder.register(Broken)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "Missing" in str(caught.value)
    before = len(dependency_calls)
    builder.register(Missing)
    with builder.build() as owner:
        assert len(dependency_calls) > before
        assert all(isinstance(owner.resolve(route).infrastructure, Infrastructure) for route in routes)
