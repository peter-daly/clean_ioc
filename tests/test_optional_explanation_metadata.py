"""Reduced runtimes retain execution relationships and explicitly expire inspection."""

import gc
from typing import Generic, TypeVar

import pytest

from benchmarks.graph_artifact import dump_graph
from benchmarks.graph_memory_fixture import build, resolve_workload, validate
from benchmarks.graph_reachability_audit import audit
from clean_ioc import (
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    Provider,
    ResolutionProfiler,
    WarmupPlan,
    WarmupTarget,
)
from clean_ioc import component_filters as cf
from clean_ioc.components import ComponentKind


class Leaf:
    pass


class Consumer:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


class IntConsumer:
    def __init__(self, value: int):
        self.value = value


class Wrapper(Consumer):
    def __init__(self, inner: Consumer):
        self.inner = inner


def composition():
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    builder.register(Consumer)
    builder.register_decorator(Consumer, Wrapper)
    return builder


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("explain_metadata", [False, True])
async def test_rich_runtime_preserves_templates_providers_maps_identity_and_cleanup(diagnostics, explain_metadata):
    fixture = build(2, diagnostics=diagnostics, explain_metadata=explain_metadata)
    async with fixture.runtime:
        held = await resolve_workload(fixture)
        try:
            assert validate(fixture, held)
            assert not audit(fixture.runtime._plan)["missing_graph_qualified_links"]
            assert fixture.runtime.explain_metadata_enabled is explain_metadata
            if not explain_metadata:
                plan = fixture.runtime._plan
                assert plan.compiled_graph is None
                assert plan.build_report._graph is None
                assert not plan.occurrence_origins
                assert not plan.decorator_explanations
                assert not plan.root_candidates
                assert not plan.census_definitions
                assert plan.selected_registrations is fixture.runtime.selected_registrations
                assert plan.selected_registrations
                assert not plan.architecture_roots
                assert len(plan.graph._records or {}) == 1278
        finally:
            await held.scope.__aexit__(None, None, None)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_runtime_filters_keep_full_root_relationships(diagnostics):
    with composition().build(explain_metadata=False, diagnostics=diagnostics) as runtime:
        roots = runtime.components
        root = next(component for component in roots if component.service_type is Consumer)
        assert root.dependencies[0].parent.id == root.id
        assert root.dependencies[0].cache_owner.value == "singleton"
        assert root.decorators[0].decorated.id == root.id
        assert root.decorators[0].parent is None
        assert root.dependencies[0].kind is ComponentKind.registration
        captured = []

        def predicate(component):
            captured.append(component)
            return component.has_descendant(cf.implementation_type_is(Leaf))

        assert runtime.has_component(Consumer, predicate)
        result = runtime.resolve(Consumer, predicate)
        assert isinstance(result, Wrapper)
        assert result.inner.leaf is runtime.resolve(Leaf)
        assert isinstance(runtime.resolve(Provider[Consumer], predicate)(), Wrapper)
        assert captured
        assert all(component.dependencies for component in captured)
        assert runtime.resolve(list[Consumer], predicate)


def test_disabled_apis_raise_without_reconstruction_or_new_caches():
    with composition().build(explain_metadata=False, check_unreachable=False) as runtime:
        before = (len(runtime._plan.graph._records), len(gc.get_objects()))
        for _ in range(2):
            for operation in (lambda: runtime.graph, runtime.validation_report):
                with pytest.raises(RuntimeError, match="explain-metadata-disabled"):
                    operation()
        assert len(runtime._plan.graph._records) == before[0]
        assert runtime._plan.compiled_graph is None
        assert runtime.build_report.is_valid
        assert runtime.build_report.to_dict()["valid"]
        assert runtime.build_report.to_sarif()


@pytest.mark.parametrize("value", [None, 0, 1, "false", []])
def test_build_option_is_a_strict_boolean_on_both_entry_points(value):
    with pytest.raises(TypeError, match="explain_metadata must be a bool"):
        composition().build(explain_metadata=value)
    with composition().build() as parent:
        with pytest.raises(TypeError, match="explain_metadata must be a bool"):
            parent.new_scope_builder().build(explain_metadata=value)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_build_rules_run_before_reduction_and_saved_graphs_expire(diagnostics):
    builder = composition()
    captured = []

    def safety(context):
        graph = context.graph
        root = next(root.component for root in graph.roots if root.requested_type is Consumer)
        assert graph.explain_decorators(root).selected
        assert graph.ownership_report().records
        graph.manifest(all_roots=True)
        captured.append((graph, root))
        return ()

    builder.add_validation_rule(safety)
    with builder.build(explain_metadata=False, diagnostics=diagnostics) as runtime:
        graph, root = captured[0]
        assert graph.explain_metadata_enabled is False
        for operation in (
            lambda: graph.roots,
            lambda: graph.manifest(),
            lambda: list(graph.walk()),
            lambda: graph.explain(root),
        ):
            with pytest.raises(RuntimeError, match="explain-metadata-disabled"):
                operation()
        assert not graph._manifest_cache
        assert not graph._decorator_explanations
        assert root.dependencies[0].implementation_type is Leaf
        assert isinstance(runtime.resolve(Consumer), Wrapper)


def test_validation_only_rules_explicitly_require_metadata_and_do_not_consume_builder():
    builder = composition()
    builder.add_validation_rule(lambda context: (), mode="validation")
    with pytest.raises(ValueError, match="validation-only rules require explain_metadata=True"):
        builder.build(explain_metadata=False)
    assert not builder._built
    with builder.build() as runtime:
        assert runtime.validation_report().is_valid


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("explain_metadata", [False, True])
def test_failed_builds_preserve_requested_diagnostics(diagnostics, explain_metadata):
    builder = ContainerBuilder()
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(diagnostics=diagnostics, explain_metadata=explain_metadata)
    error = caught.value
    assert error.diagnostics_enabled is diagnostics
    assert error.report is not None
    assert error.report.errors[0].code == "missing-component"
    assert (error.partial_graph is not None) is diagnostics
    assert not builder._built
    builder.register(Leaf)
    with builder.build(explain_metadata=explain_metadata) as runtime:
        assert isinstance(runtime.resolve(Consumer).leaf, Leaf)


@pytest.mark.parametrize("explain_metadata", [False, True])
def test_escaped_predicate_views_have_deliberate_lifetimes(monkeypatch, explain_metadata):
    captured = []
    original = cf.with_name

    def recording(name):
        predicate = original(name)

        def capture(component):
            captured.append(component)
            return predicate(component)

        return capture

    monkeypatch.setattr(cf, "with_name", recording)
    fixture = build(2, explain_metadata=explain_metadata)
    with fixture.runtime:
        expired = 0
        snapshots = 0
        for component in captured:
            try:
                component.service_type
                if component.parent is not None:
                    component.parent.dependencies
                tuple(component.descendants())
            except RuntimeError as error:
                assert "explain-metadata-disabled" in str(error)
                assert component._graph is fixture.runtime._plan.graph
                expired += 1
            else:
                if component._graph is not fixture.runtime._plan.graph:
                    snapshots += 1
        assert bool(expired) is (not explain_metadata)
        assert snapshots > 0  # Caller-owned, separate source inspection snapshots.
        assert not audit(fixture.runtime._plan)["missing_graph_qualified_links"]


@pytest.mark.parametrize("parent_metadata,child_metadata", [(True, True), (True, False), (False, False)])
@pytest.mark.parametrize("lifespan", ["singleton", "scoped", "transient", "per_resolution"])
def test_overlays_preserve_owners_and_never_mutate_parent_graph(parent_metadata, child_metadata, lifespan):
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    builder.register(Consumer, lifespan=lifespan)
    with builder.build(explain_metadata=parent_metadata) as parent:
        parent_count = len(parent._plan.graph._records or {})
        original = parent.resolve(Consumer)
        child_builder = parent.new_scope_builder()
        child_builder.register(str, instance="overlay")
        with child_builder.build(explain_metadata=child_metadata, diagnostics=True) as overlay:
            assert overlay.resolve(str) == "overlay"
            result = overlay.resolve(Consumer)
            assert result.leaf is original.leaf
            assert (result is original) is (lifespan == "singleton")
            assert len(parent._plan.graph._records or {}) == parent_count
            assert not audit(overlay._plan)["missing_graph_qualified_links"]
            with overlay.new_scope() as ordinary:
                assert ordinary.explain_metadata_enabled is child_metadata
                assert ordinary.resolve(Consumer).leaf is original.leaf
            if not child_metadata:
                assert not overlay._plan.blueprint.template_selections
                assert not overlay._plan.blueprint.generated_decorators


def test_full_overlay_of_reduced_parent_is_explicitly_rejected():
    with composition().build(explain_metadata=False) as parent:
        child_builder = parent.new_scope_builder()
        with pytest.raises(ValueError, match="overlay of a reduced parent requires explain_metadata=False"):
            child_builder.build()
        with child_builder.build(explain_metadata=False) as child:
            assert isinstance(child.resolve(Consumer), Wrapper)


def test_scope_builder_composition_and_private_architecture_anchors_are_optional():
    builder = ContainerBuilder()
    builder.create_boundary("private").register(Leaf, lifespan="singleton")
    with builder.build(explain_metadata=False) as parent:
        assert parent._plan.architecture_roots
        with parent.new_scope_builder().build(explain_metadata=False) as child:
            assert not child.has_component(Leaf)
            assert not audit(child._plan)["missing_graph_qualified_links"]
    builder = ContainerBuilder()
    builder.create_boundary("private").register(Leaf, lifespan="singleton")
    with builder.build(explain_metadata=False, allow_scope_builders=False) as parent:
        assert not parent._plan.architecture_roots
        assert parent._plan.graph._records == {}
        with pytest.raises(RuntimeError, match="Scope builders are disabled"):
            parent.new_scope_builder()


def test_warmups_provisions_and_inherited_instrumentation_survive_reduction():
    profiler = ResolutionProfiler()
    compiler = CompilationProfiler()
    builder = composition()
    builder.declare_scope_slot(int)
    builder.register(IntConsumer)
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Leaf)]))
    with builder.build(explain_metadata=False, profile=compiler, instrumentation=Instrumentation(profiler)) as parent:
        assert parent.warmup("startup").is_valid
        assert parent.warmup_plans
        assert parent.has_scope_slot(int)
        with parent.new_scope() as ordinary:
            ordinary.provide(int, 42)
            assert ordinary.resolve(IntConsumer).value == 42
            assert ordinary.has_provision(int)
        with parent.new_scope_builder().build(explain_metadata=False) as child:
            assert child.resolve(Leaf) is parent.resolve(Leaf)
            assert child._profiler is profiler
        assert profiler.report().records
        assert compiler.report().counters


T = TypeVar("T")


class GenericLeaf(Generic[T]):
    pass


class GenericConsumer(Generic[T]):
    def __init__(self, leaf: GenericLeaf[T]):
        self.leaf = leaf


def test_specialized_generic_component_bindings_remain_runtime_filter_facts():
    builder = ContainerBuilder()
    builder.register(GenericLeaf[int])
    builder.register(GenericConsumer[int])
    with builder.build(explain_metadata=False) as runtime:

        def predicate(component):
            return component.generic_mapping[T] is int and bool(component.dependencies)

        assert isinstance(runtime.resolve(GenericConsumer[int], predicate).leaf, GenericLeaf)
        assert runtime.has_component(GenericConsumer[int], predicate)


def test_artifact_experiment_rejects_reduced_plans_with_future_composition_before_writing(tmp_path):
    with composition().build(explain_metadata=False, allow_scope_builders=True) as runtime:
        target = tmp_path / "artifact.jsonl"
        with pytest.raises(ValueError, match="allow_scope_builders=False"):
            dump_graph(runtime, target)
        assert not target.exists()


def test_reduced_execution_releases_build_callbacks_and_dependency_settings():
    import weakref

    from clean_ioc.container import _iter_registration_steps, _RuntimeRegistration

    class Predicate:
        def __init__(self):
            self.saved = []

        def __call__(self, component):
            self.saved.append(component)
            return True

    predicate = Predicate()
    reference = weakref.ref(predicate)
    builder = ContainerBuilder()
    builder.register(Leaf)
    builder.register(Consumer)
    builder.register_decorator(Consumer, Wrapper, when=predicate)
    runtime = builder.build(explain_metadata=False, allow_scope_builders=False)
    del builder, predicate
    gc.collect()
    with runtime:
        assert reference() is None
        for roots in runtime._plan.roots.values():
            for root in roots:
                for step in _iter_registration_steps(root.step):
                    assert isinstance(step.registration, _RuntimeRegistration)
                    assert not hasattr(step.registration, "dependencies")
                    for decorator in step.decorators:
                        assert decorator.source.definition is None
                        assert not decorator.source.dependencies
        assert isinstance(runtime.resolve(Consumer), Wrapper)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_failed_final_validation_keeps_complete_frozen_graph_and_callback_views(diagnostics):
    builder = composition()
    saved = []

    def reject(context):
        saved.append(context.graph)
        return [context.issue("refused", "intentional build refusal")]

    builder.add_validation_rule(reject)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(explain_metadata=False, diagnostics=diagnostics)
    error = caught.value
    assert error.compiled_graph is not None
    assert error.compiled_graph.explain_metadata_enabled
    root = next(root.component for root in error.compiled_graph.roots if root.requested_type is Consumer)
    assert root._graph._records is not None
    assert root.decorators
    assert saved[0].manifest(all_roots=True).fingerprint
    assert error.diagnostics_enabled is diagnostics
    assert not builder._built


def test_escaped_build_graph_bound_methods_do_not_resurrect_removed_metadata():
    builder = composition()
    methods = []

    def safety(context):
        graph = context.graph
        methods.extend((graph.manifest, graph.explain_template_sources, graph.walk))
        return ()

    builder.add_validation_rule(safety)
    with builder.build(explain_metadata=False):
        for method in methods:
            with pytest.raises(RuntimeError, match="explain-metadata-disabled"):
                value = method()
                if hasattr(value, "__next__"):
                    next(value)


@pytest.mark.parametrize("allow_scope_builders", [False, True])
def test_instrumentation_prepares_private_architecture_before_optional_pruning(allow_scope_builders):
    builder = composition()
    builder.create_boundary("private").register(int, instance=17)
    profiler = ResolutionProfiler()
    with builder.build(
        explain_metadata=False,
        allow_scope_builders=allow_scope_builders,
        instrumentation=Instrumentation(profiler),
    ) as runtime:
        assert isinstance(runtime.resolve(Consumer), Wrapper)
        assert not runtime.has_component(int)
        assert profiler.report().records
        assert bool(runtime._plan.architecture_roots) is allow_scope_builders
        assert not audit(runtime._plan)["missing_graph_qualified_links"]


@pytest.mark.parametrize("explain_metadata", [False, True])
def test_success_finalization_never_probes_arbitrary_runtime_values(explain_metadata):
    sealed = False

    class Value:
        @property
        def __class__(self):
            if sealed:
                raise AssertionError("Finalization probed an application object's __class__")
            return type(self)

    class Holder:
        def __init__(self, payload: object):
            self.payload = payload

    value = Value()
    builder = ContainerBuilder()
    builder.register(Value, instance=value)
    builder.register(Holder, arguments={"payload": value})

    def finish(context):
        nonlocal sealed
        sealed = True
        return ()

    builder.add_validation_rule(finish)
    with builder.build(explain_metadata=explain_metadata, allow_scope_builders=False) as runtime:
        sealed = False
        assert runtime.resolve(Value) is value
        assert runtime.resolve(Holder).payload is value


def test_literal_application_values_are_opaque_even_when_they_resemble_executable_helpers():
    from clean_ioc.container import _Step

    class Holder:
        def __init__(self, value: object):
            self.value = value

    value = _Step()
    builder = ContainerBuilder()
    builder.register(Holder, arguments={"value": value})
    with builder.build(explain_metadata=False) as runtime:
        assert runtime.resolve(Holder).value is value


def test_audit_distinguishes_expired_callback_views_from_broken_runtime_links():
    from dataclasses import replace

    with composition().build(explain_metadata=False) as runtime:
        graph = runtime._plan.graph
        records = graph._records
        assert records is not None
        root = next(component for component in runtime.components if component.service_type is Consumer)
        missing = max(records) + 100
        records[root.occurrence_id] = replace(records[root.occurrence_id], owner_id=missing)
        result = audit(runtime._plan)
        assert [id(graph), missing] in [list(value) for value in result["missing_graph_qualified_links"]]
