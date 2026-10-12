"""Reduced runtimes retain execution relationships and explicitly expire inspection."""

import gc
from typing import Generic, TypeVar

import pytest

from benchmarks.graph_artifact import dump_graph
from benchmarks.graph_memory_fixture import build, resolve_workload, validate
from benchmarks.graph_reachability_audit import audit
from clean_ioc import (
    BuilderAlreadyBuiltError,
    BuildIssue,
    CompilationProfiler,
    ContainerBuilder,
    Instrumentation,
    IssueSeverity,
    Provider,
    ResolutionProfiler,
    ScopeBuilder,
    WarmupPlan,
    WarmupTarget,
)
from clean_ioc import component_filters as cf
from clean_ioc.components import ComponentKind
from tests.verification_helpers import present


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


@pytest.mark.parametrize("operation", ["build", "verify"])
async def test_rich_runtime_preserves_templates_providers_maps_identity_and_cleanup(operation):
    fixture = build(2, operation=operation)
    async with fixture.runtime:
        held = await resolve_workload(fixture)
        try:
            assert validate(fixture, held)
            assert not audit(fixture.runtime._plan)["missing_graph_qualified_links"]
            plan = fixture.runtime._plan
            for name in (
                "compiled_graph",
                "build_report",
                "occurrence_origins",
                "decorator_explanations",
                "root_candidates",
                "census_definitions",
                "architecture_roots",
            ):
                assert not hasattr(plan, name)
            assert plan.selected_registrations is fixture.runtime.selected_registrations
            assert plan.selected_registrations
            assert plan.graph._records
            if fixture.analysis:
                assert present(fixture.analysis.graph).roots
        finally:
            await held.scope.__aexit__(None, None, None)


@pytest.mark.parametrize("diagnostics", [False, True])
def test_runtime_filters_keep_full_root_relationships(diagnostics):
    with composition().build() as runtime:
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


def test_analysis_reads_never_add_metadata_to_runtime(monkeypatch):
    with composition().verify() as result, result.create_runtime() as runtime:
        before = len(runtime._plan.graph._records)
        monkeypatch.setattr(ContainerBuilder, "verify", lambda *args: pytest.fail("recompiled"))
        for _ in range(2):
            assert result.graph.manifest().fingerprint
            assert result.is_valid
            assert result.to_dict()["valid"]
            assert result.to_sarif()
        assert len(runtime._plan.graph._records) == before
        for name in ("graph", "validation_report", "build_report", "explain_metadata_enabled"):
            assert not hasattr(runtime, name)


@pytest.mark.parametrize("value", [None, 0, 1, "false", [], True, False])
def test_removed_metadata_option_rejected_before_admission(value):
    builder = composition()
    with pytest.raises(TypeError, match="explain_metadata"):
        builder.build(explain_metadata=value)
    handle = builder.retain_composition()
    with builder.build() as parent:
        child = ScopeBuilder(parent, composition=handle)
        with pytest.raises(TypeError, match="explain_metadata"):
            child.build(explain_metadata=value)  # ty: ignore[unknown-argument]  # Deliberately invalid input.
        with child.build() as runtime:
            assert isinstance(runtime.resolve(Consumer), Wrapper)


def test_analysis_callback_views_remain_inspectable_without_runtime_ownership():
    builder = composition()
    captured = []

    def rule(context):
        graph = context.graph
        root = next(root.component for root in graph.roots if root.requested_type is Consumer)
        assert graph.explain_decorators(root).selected
        assert graph.ownership_report().records
        captured.append((graph, root))
        return ()

    builder.add_validation_rule(rule)
    with builder.verify() as result, result.create_runtime() as runtime:
        graph, root = captured[0]
        assert graph.manifest().fingerprint
        assert list(graph.walk())
        assert graph.explain(root)
        assert root.dependencies[0].implementation_type is Leaf
        assert isinstance(runtime.resolve(Consumer), Wrapper)
        assert not hasattr(runtime._plan, "compiled_graph")


@pytest.mark.parametrize("boundary", [False, True])
def test_all_rules_are_completed_once_only_by_analysis(boundary, monkeypatch):
    calls = []
    warning = BuildIssue("startup-warning", IssueSeverity.warning, "Startup advisory")
    error = BuildIssue("validation-policy", IssueSeverity.error, "Validation policy failed")

    def create_builder():
        builder = composition()
        target = builder.create_boundary("private") if boundary else builder
        if boundary:
            target.register(Leaf)
        target.add_validation_rule(lambda context: calls.append("warning") or (warning,))
        target.add_validation_rule(lambda context: calls.append("error") or (error,))
        return builder

    with create_builder().build() as runtime:
        assert isinstance(runtime.resolve(Consumer), Wrapper)
        assert calls == []
        with runtime.new_scope() as scope:
            assert not hasattr(scope, "validation_report")
    with create_builder().verify() as result, result.create_runtime() as runtime:
        assert calls == ["warning", "error"]
        assert result.issues == (warning, error)
        assert not result.is_valid
        monkeypatch.setattr("clean_ioc.container._run_validation_rules", lambda *args: pytest.fail("replayed"))
        for _ in range(2):
            assert result.issues == (warning, error)
            assert result.graph.manifest().fingerprint
            assert result.triage_report().to_dict()
        assert calls == ["warning", "error"]
        assert isinstance(runtime.resolve(Consumer), Wrapper)


def test_policy_failure_consumes_attempt_and_new_builder_can_apply_changed_policy():
    calls = []
    reject = True

    def policy(context):
        calls.append("policy")
        return (BuildIssue("required-policy", IssueSeverity.error, "Startup policy failed"),) if reject else ()

    def make_builder():
        builder = composition()
        builder.add_validation_rule(policy)
        builder.add_validation_rule(lambda context: calls.append("second") or ())
        return builder

    builder = make_builder()
    result = builder.verify()
    assert [issue.code for issue in result.errors] == ["required-policy"]
    assert calls == ["policy", "second"]
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.build()
    reject = False
    with make_builder().verify() as result, result.create_runtime() as runtime:
        assert result.is_valid
        assert isinstance(runtime.resolve(Consumer), Wrapper)
    assert calls == ["policy", "second", "policy", "second"]


def test_overlay_analysis_completes_inherited_and_local_rules_once():
    calls = []
    builder = composition()
    builder.add_validation_rule(lambda context: calls.append("parent") or ())
    with builder.verify() as parent_result, parent_result.create_runtime() as parent:
        assert calls == ["parent"]
        child_builder = ScopeBuilder(parent, composition=parent_result.composition)
        child_builder.add_validation_rule(lambda context: calls.append("child") or ())
        with child_builder.verify() as result, result.create_runtime() as child:
            assert calls == ["parent", "parent", "child"]
            assert isinstance(child.resolve(Consumer), Wrapper)
            assert not hasattr(child._plan, "validation_rules")
            assert result.is_valid
            assert parent_result.is_valid
        assert calls == ["parent", "parent", "child"]


def test_failed_analysis_captures_diagnostics_and_consumes_builder():
    builder = ContainerBuilder()
    builder.register(Consumer)
    calls = []
    builder.add_validation_rule(lambda context: calls.append("validation") or ())
    result = builder.verify()
    assert result.errors[0].code == "missing-component"
    assert result.partial_graph is not None
    assert not result.emission_complete
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.register(Leaf)
    with composition().build() as runtime:
        assert isinstance(runtime.resolve(Consumer).inner.leaf, Leaf)
    assert calls == []


@pytest.mark.parametrize("operation", ["build", "verify"])
def test_escaped_predicate_views_have_deliberate_lifetimes(monkeypatch, operation):
    captured = []
    original = cf.with_name

    def recording(name):
        predicate = original(name)

        def capture(component):
            captured.append(component)
            return predicate(component)

        return capture

    monkeypatch.setattr(cf, "with_name", recording)
    fixture = build(2, operation=operation)
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
        assert bool(expired) is (operation == "build")
        assert snapshots > 0  # Caller-owned, separate source inspection snapshots.
        assert not audit(fixture.runtime._plan)["missing_graph_qualified_links"]


@pytest.mark.parametrize("parent_metadata,child_metadata", [(True, True), (True, False), (False, False)])
@pytest.mark.parametrize("lifespan", ["singleton", "scoped", "transient", "per_resolution"])
def test_overlays_preserve_owners_and_never_mutate_parent_graph(parent_metadata, child_metadata, lifespan):
    builder = ContainerBuilder()
    builder.register(Leaf, lifespan="singleton")
    builder.register(Consumer, lifespan=lifespan)
    parent_composition = builder.retain_composition()
    with builder.build() as parent:
        parent_count = len(parent._plan.graph._records or {})
        original = parent.resolve(Consumer)
        child_builder = ScopeBuilder(parent, composition=parent_composition)
        child_builder.register(str, instance="overlay")
        overlay_composition = child_builder.retain_composition()
        with child_builder.build() as overlay:
            assert overlay.resolve(str) == "overlay"
            result = overlay.resolve(Consumer)
            assert result.leaf is original.leaf
            assert (result is original) is (lifespan == "singleton")
            assert len(parent._plan.graph._records or {}) == parent_count
            assert not audit(overlay._plan)["missing_graph_qualified_links"]
            with overlay.new_scope() as ordinary:
                assert not hasattr(ordinary, "explain_metadata_enabled")
                assert ordinary.resolve(Consumer).leaf is original.leaf
            if not child_metadata:
                assert not overlay_composition._for_parent(overlay).template_selections
                assert not overlay_composition._for_parent(overlay).generated_decorators


def test_overlay_analysis_uses_external_composition_from_execution_parent():
    builder = composition()
    handle = builder.retain_composition()
    with builder.build() as parent:
        with ScopeBuilder(parent, composition=handle).verify() as result, result.create_runtime() as child:
            assert result.is_valid
            assert present(result.graph).roots
            assert isinstance(child.resolve(Consumer), Wrapper)


def test_private_unbound_declarations_are_external_to_runtime():
    builder = ContainerBuilder()
    builder.create_boundary("private").register(Leaf, lifespan="singleton")
    handle = builder.retain_composition()
    with builder.build() as parent:
        assert not hasattr(parent._plan, "architecture_roots")
        assert parent._plan.graph._records == {}
        with ScopeBuilder(parent, composition=handle).build() as child:
            assert not child.has_component(Leaf)
            assert not audit(child._plan)["missing_graph_qualified_links"]


def test_warmups_provisions_and_inherited_instrumentation_survive_reduction():
    profiler = ResolutionProfiler()
    compiler = CompilationProfiler()
    builder = composition()
    builder.declare_scope_slot(int)
    builder.register(IntConsumer)
    builder.add_warmup_plan(WarmupPlan("startup", [WarmupTarget(Leaf)]))
    parent_composition = builder.retain_composition()
    with builder.build(profile=compiler, instrumentation=Instrumentation(profiler)) as parent:
        assert parent.warmup("startup").is_valid
        assert parent.warmup_plans
        assert parent.has_scope_slot(int)
        with parent.new_scope() as ordinary:
            ordinary.provide(int, 42)
            assert ordinary.resolve(IntConsumer).value == 42
            assert ordinary.has_provision(int)
        with ScopeBuilder(parent, composition=parent_composition).build() as child:
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
    with builder.build() as runtime:

        def predicate(component):
            return component.generic_mapping[T] is int and bool(component.dependencies)

        assert isinstance(runtime.resolve(GenericConsumer[int], predicate).leaf, GenericLeaf)
        assert runtime.has_component(GenericConsumer[int], predicate)


def test_experimental_artifact_contains_execution_and_excludes_external_composition(tmp_path):
    builder = composition()
    builder.set_provider_roots(())
    handle = builder.retain_composition()
    with builder.build() as runtime:
        target = tmp_path / "artifact.jsonl"
        dump_graph(runtime, target)
        assert target.exists()
        assert handle.is_ready
        assert not hasattr(runtime._plan, "_blueprint")


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
    runtime = builder.build()
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
        return [next(context.graph.walk()).issue("refused", "intentional build refusal")]

    builder.add_validation_rule(reject)
    caught_analysis = builder.verify()
    assert not caught_analysis.is_valid
    error = caught_analysis
    assert error.graph is not None
    assert error.graph.explain_metadata_enabled
    root = next(root.component for root in error.graph.roots if root.requested_type is Consumer)
    assert root._graph._records is not None
    assert root.decorators
    assert saved[0].manifest(all_roots=True).fingerprint
    assert builder._built
    assert error.complete


def test_execution_build_never_provides_graph_methods_to_rules():
    builder = composition()
    methods = []

    def rule(context):
        methods.extend((context.graph.manifest, context.graph.explain_template_sources, context.graph.walk))
        return ()

    builder.add_validation_rule(rule)
    with builder.build() as runtime:
        assert isinstance(runtime.resolve(Consumer), Wrapper)
        assert methods == []


@pytest.mark.parametrize("allow_scope_builders", [False, True])
def test_instrumentation_prepares_private_architecture_before_optional_pruning(allow_scope_builders):
    builder = composition()
    builder.create_boundary("private").register(int, instance=17)
    profiler = ResolutionProfiler()
    with builder.build(instrumentation=Instrumentation(profiler)) as runtime:
        assert isinstance(runtime.resolve(Consumer), Wrapper)
        assert not runtime.has_component(int)
        assert profiler.report().records
        assert not hasattr(runtime._plan, "architecture_roots")
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
    with builder.build() as runtime:
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
    with builder.build() as runtime:
        assert runtime.resolve(Holder).value is value


def test_audit_distinguishes_expired_callback_views_from_broken_runtime_links():
    from dataclasses import replace

    with composition().build() as runtime:
        graph = runtime._plan.graph
        records = graph._records
        assert records is not None
        root = next(component for component in runtime.components if component.service_type is Consumer)
        missing = max(records) + 100
        records[root.occurrence_id] = replace(records[root.occurrence_id], owner_id=missing)
        result = audit(runtime._plan)
        assert [id(graph), missing] in [list(value) for value in result["missing_graph_qualified_links"]]
