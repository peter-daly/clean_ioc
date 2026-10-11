"""Direct execution finalization, detached analysis projection and owner lifetimes."""

import gc
import weakref
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import fields
from typing import Generic, TypeVar

import pytest

import clean_ioc.container as compiler
from clean_ioc import (
    AnalysisRuntimeUnavailableError,
    BuilderAlreadyBuiltError,
    CompilationBudget,
    CompilationProfiler,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    Provider,
    ProviderMapGroup,
    ScopeBuilder,
    ScopeClosedError,
    Tag,
    WarmupPlan,
    WarmupTarget,
)


class Leaf:
    pass


class Service:
    def __init__(self, leaf: Leaf):
        self.leaf = leaf


def builder():
    result = ContainerBuilder().set_provider_roots(())
    result.register(Leaf, lifespan="singleton", root_policy="dependency_only")
    result.register(Service)
    return result


def forbid(*args, **kwargs):
    raise AssertionError("An analysis owner or finalizer was constructed during execution")


@pytest.mark.parametrize("rules", [False, True])
@pytest.mark.parametrize("profile", [False, True])
def test_ordinary_build_does_not_construct_rich_plan_graph_report_or_finalize(monkeypatch, rules, profile):
    source = builder()
    source.create_boundary("private").register(bytes, instance=b"private")
    if rules:
        source.add_validation_rule(forbid)
    for cls in (compiler._PlanSet, compiler.CompiledGraph, compiler.AnalysisReport):
        monkeypatch.setattr(cls, "__init__", forbid)
    for name in ("_finalize_plan", "_compile_with_report", "_graph_roots", "_census_inventory"):
        monkeypatch.setattr(compiler, name, forbid)
    with source.build(profile=CompilationProfiler() if profile else None) as runtime:
        assert type(runtime._plan) is compiler._ExecutionPlan
        assert isinstance(runtime.resolve(Service).leaf, Leaf)
        with runtime.new_scope() as scope:
            assert scope._plan is runtime._plan
            assert scope.resolve(Service).leaf is runtime.resolve(Service).leaf
        assert not {"compiled_graph", "build_report", "_blueprint", "validation_rules", "root_candidates"} & {
            field.name for field in fields(runtime._plan)
        }


def test_selected_catalogue_includes_private_map_decorator_and_deferred_targets():
    item = TypeVar("item")

    class Handler:
        pass

    class ClosedHandler(Handler, Generic[item]):
        pass

    class Wrapper:
        def __init__(self, inner: Handler, leaf: Leaf):
            self.inner, self.leaf = inner, leaf

    class Dispatcher:
        def __init__(self, handlers: Mapping[str, Provider[Handler]]):
            self.handlers = handlers

    group = ProviderMapGroup("handlers", str, Handler)
    source = ContainerBuilder().set_provider_roots(())
    boundary = source.create_boundary("private", exposes=(Expose(Dispatcher),))
    selected = boundary.register(
        Handler,
        ClosedHandler[int],
        name="chosen",
        tags=[Tag("kind", "selected")],
        root_policy="dependency_only",
        contributes={group: "chosen"},
    )
    unused = boundary.register(Handler, ClosedHandler[str], root_policy="dependency_only")
    leaf = boundary.register(Leaf, root_policy="dependency_only")
    wrapper = boundary.register_decorator(Handler, Wrapper, decorated_arg="inner")
    boundary.register_provider_map(group, root_policy="dependency_only")
    boundary.register(Dispatcher)
    with source.build() as runtime:
        catalogue = runtime.selected_registrations
        ids = {record.id for record in catalogue}
        assert {selected, leaf, wrapper} <= ids
        assert unused not in ids
        info = next(record for record in catalogue if record.id == selected)
        assert info.implementation_type == ClosedHandler[int]
        assert info.name == "chosen"
        assert info.tags == (Tag("kind", "selected"),)
        assert not runtime.has_component(Handler)
        target = runtime.resolve(Dispatcher).handlers["chosen"]()
        assert isinstance(target, Wrapper)
        assert isinstance(target.inner, ClosedHandler)
        assert isinstance(target.leaf, Leaf)


def test_warmup_binding_needs_no_rich_graph_and_never_activates_implicitly(monkeypatch):
    calls = []
    source = builder()
    source.pre_configure(Service, lambda: calls.append("configure"))
    source.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service), WarmupTarget(Service)]))
    monkeypatch.setattr(compiler.CompiledGraph, "__init__", forbid)
    monkeypatch.setattr(compiler, "_finalize_plan", forbid)
    with source.build() as runtime:
        assert calls == []
        report = runtime.warmup("start")
        assert report.is_valid
        assert calls == ["configure"]


def test_analysis_projection_outlives_rich_result_without_retaining_it():
    source = builder()
    result = source.analyse()
    graph = weakref.ref(result.graph)
    result_ref = weakref.ref(result)
    runtime = result.create_runtime()
    assert runtime._plan.graph is not result.graph.roots[0].component._graph
    assert runtime.components[0].dependencies[0].parent.occurrence_id == runtime.components[0].occurrence_id
    assert runtime.components[0].dependencies[0].parent._graph is runtime._plan.graph
    del result
    gc.collect()
    assert result_ref() is None
    assert graph() is None
    assert isinstance(runtime.resolve(Service).leaf, Leaf)
    runtime.__exit__(None, None, None)


def test_each_analysis_runtime_has_independent_singleton_and_shared_local_preconfiguration_state():
    calls = []

    class Other:
        pass

    source = builder()
    source.register(Other)
    source.pre_configure((Service, Other), lambda: calls.append("configure"))
    with source.analyse() as result:
        first, second = result.create_runtime(), result.create_runtime()
        assert calls == []
        assert first.resolve(Service).leaf is not second.resolve(Service).leaf
        assert calls == ["configure", "configure"]
        first.resolve(Other)
        second.resolve(Other)
        with first.new_scope() as child:
            child.resolve(Service)
            child.resolve(Other)
        assert calls == ["configure", "configure"]
        assert first._plan.graph is second._plan.graph is result._plan.graph


def test_scope_analysis_borrows_actual_parent_owners_and_keeps_child_state_independent():
    calls, closed = [], []

    class Child:
        def __init__(self, leaf: Leaf):
            self.leaf = leaf

    @contextmanager
    def leaf():
        try:
            yield Leaf()
        finally:
            closed.append("parent")

    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, factory=leaf, lifespan="singleton")
    source.pre_configure(Leaf, lambda: calls.append("parent"))
    with source.analyse() as parent_result:
        parent = parent_result.create_runtime()
        overlay = ScopeBuilder(parent, composition=parent_result.composition)
        overlay.set_provider_roots(())
        overlay.register(Child, lifespan="scoped")
        overlay.pre_configure(Child, lambda: calls.append("child"))
        with overlay.analyse() as result:
            assert calls == []
            first, second = result.create_runtime(), result.create_runtime()
            one, two = first.resolve(Child), second.resolve(Child)
            assert one is not two
            assert one.leaf is two.leaf is parent.resolve(Leaf)
            assert calls == ["child", "parent", "child"]
            assert closed == []
        assert not parent._closed
        assert closed == []
    assert closed == ["parent"]


def test_completed_execution_survives_inspection_only_boundary_failure():
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            pass

    source = builder()
    source.create_boundary("private").register(Broken)
    source.add_validation_rule(forbid)
    with source.analyse() as result:
        assert result.emission_complete
        assert not result.report.complete
        assert result.graph is None
        assert result.partial_graph is not None
        assert [outcome.status for outcome in result.report.rule_outcomes] == ["unavailable"]
        assert Broken not in {entry.service_type for entry in result.selected_registrations}
        with result.create_runtime() as runtime:
            assert isinstance(runtime.resolve(Service).leaf, Leaf)
            assert not runtime.has_component(Broken)


def test_primary_emission_failure_cannot_be_replaced_by_diagnostic_retry():
    calls = []

    def select(component):
        calls.append(component)
        if len(calls) == 1:
            raise ValueError("first attempt")
        return True

    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, when=select)
    result = source.analyse()
    assert not result.emission_complete
    assert result.partial_graph.inconsistent_retries
    with pytest.raises(AnalysisRuntimeUnavailableError):
        result.create_runtime()


def test_runtime_creation_and_report_reads_do_not_replay_selection_or_warmup_filters():
    calls = []
    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, when=lambda component: calls.append("selection") or True)
    source.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Leaf, filter=lambda c: calls.append("warmup") or True)]))
    result = source.analyse()
    captured = tuple(calls)
    assert captured.count("warmup") == 1
    for _ in range(2):
        result.report.to_json()
        result.report.to_text()
        with result.create_runtime() as runtime:
            runtime.resolve(Leaf)
    assert tuple(calls) == captured
    result.close()


@pytest.mark.parametrize("operation", ["build", "analyse"])
def test_consumed_builder_and_retained_boundary_release_declaration_callbacks(operation):
    class Rule:
        def __call__(self, context):
            return ()

    source = builder()
    boundary = source.create_boundary("private")
    rule = Rule()
    reference = weakref.ref(rule)
    source.add_validation_rule(rule)
    boundary.add_validation_rule(rule)
    del rule
    result = getattr(source, operation)()
    if operation == "analyse":
        result.close()
        del result
    gc.collect()
    assert reference() is None
    assert source._composition is None
    assert boundary._composition is None
    assert source._boundaries == []
    with pytest.raises(BuilderAlreadyBuiltError):
        boundary.register(bytes)


@pytest.mark.parametrize("failure", ["wiring", "budget", "cancel"])
def test_failed_admitted_build_releases_declarations_and_never_allocates_a_report(monkeypatch, failure):
    class Payload:
        pass

    source = builder()
    boundary = source.create_boundary("private")
    payload = Payload()
    reference = weakref.ref(payload)
    boundary.register(Payload, instance=payload)
    del payload
    monkeypatch.setattr(compiler.CompiledGraph, "__init__", forbid)
    monkeypatch.setattr(compiler.AnalysisReport, "__init__", forbid)
    if failure == "wiring":

        class Missing:
            pass

        class Broken:
            def __init__(self, missing: Missing):
                pass

        source.register(Broken)
        expected, options = ContainerBuildError, {}
    elif failure == "budget":
        expected, options = ContainerBuildError, {"budget": CompilationBudget(graph_occurrences=0)}
    else:

        def cancel(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(compiler._Compiler, "compile_execution", cancel)
        expected, options = KeyboardInterrupt, {}
    with pytest.raises(expected) as caught:
        source.build(**options)
    if isinstance(caught.value, ContainerBuildError):
        assert caught.value.report is None
        assert caught.value.compiled_graph is None
    # Tracebacks are legitimate independent owners; release that test-owned error.
    del caught
    gc.collect()
    assert reference() is None
    assert source._composition is boundary._composition is None
    with pytest.raises(BuilderAlreadyBuiltError):
        source.analyse()


def test_build_wraps_foreign_rich_error_without_mutating_it():
    foreign = builder().analyse()
    error = ContainerBuildError(report=foreign.report, compiled_graph=foreign.graph)
    original_report = error.report

    def fail(component):
        raise error

    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, when=fail)
    with pytest.raises(ContainerBuildError) as caught:
        source.build()
    assert caught.value is not error
    assert caught.value.report is None
    assert error.report is original_report
    assert error.compiled_graph is foreign.graph


def test_opaque_instance_and_derived_value_identity_survive_builder_release():
    instance, payload = Leaf(), {"opaque": object()}
    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, instance=instance)
    source.register(Service, arguments={"leaf": payload})
    with source.analyse() as result:
        for _ in range(2):
            runtime = result.create_runtime()
            assert runtime.resolve(Leaf) is instance
            assert runtime.resolve(Service).leaf is payload


def test_closed_parent_is_pre_admission_and_scope_failure_consumes_once():
    with builder().analyse() as result:
        parent = result.create_runtime()
        source = ScopeBuilder(parent, composition=result.composition)
        source.set_provider_roots(())
        parent.__exit__(None, None, None)
        with pytest.raises(ScopeClosedError):
            source.build()
        assert not source._built


def test_result_cleanup_preserves_one_failure_identity_and_reverse_runtime_order():
    events = []
    error = ValueError("cleanup")
    result = builder().analyse()
    first, second = result.create_runtime(), result.create_runtime()
    first._add_finalizer(lambda: events.append("first"))

    def close_second():
        events.append("second")
        raise error

    second._add_finalizer(close_second)
    with pytest.raises(ValueError) as caught:
        result.close()
    assert caught.value is error
    assert events == ["second", "first"]
    result.close()
    with pytest.raises(RuntimeError, match="closed"):
        result.create_runtime()


@pytest.mark.asyncio
async def test_result_async_cleanup_and_fatal_error_aggregation():
    events = []
    result = builder().analyse()
    first, second = result.create_runtime(), result.create_runtime()

    async def close_first():
        events.append("first")
        raise ValueError("first")

    async def close_second():
        events.append("second")
        raise KeyboardInterrupt("second")

    first._add_finalizer(close_first)
    second._add_finalizer(close_second)
    with pytest.raises(BaseExceptionGroup) as caught:
        await result.aclose()
    assert events == ["second", "first"]
    assert [type(error) for error in caught.value.exceptions] == [KeyboardInterrupt, ValueError]


@pytest.mark.asyncio
async def test_result_sync_close_preserves_async_cleanup_error():
    @asynccontextmanager
    async def resource():
        yield Leaf()

    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, factory=resource, lifespan="singleton")
    result = source.analyse()
    await result.create_runtime().resolve_async(Leaf)
    with pytest.raises(RuntimeError, match="Async finalizer"):
        result.close()


def test_projection_preserves_provider_map_key_table_without_hashing_opaque_keys():
    hashing_allowed = True

    class Key:
        def __hash__(self):
            assert hashing_allowed, "Runtime projection must not rebuild the frozen key table"
            return 17

    class Dispatcher:
        def __init__(self, handlers: Mapping[Key, Provider[Leaf]]):
            self.handlers = handlers

    key = Key()
    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, root_policy="dependency_only")
    source.register_provider_map(Leaf, key=lambda component: key, key_type=Key, root_policy="dependency_only")
    source.register(Dispatcher)
    with source.analyse() as result:
        hashing_allowed = False
        for _ in range(2):
            runtime = result.create_runtime()
            handlers = runtime.resolve(Dispatcher).handlers
            assert next(iter(handlers)) is key


def test_scope_failure_consumes_builder_and_retained_boundary_and_preserves_parent():
    class Missing:
        pass

    class Broken:
        def __init__(self, missing: Missing):
            pass

    with builder().analyse() as result:
        parent = result.create_runtime()
        source = ScopeBuilder(parent, composition=result.composition)
        boundary = source.create_boundary("child")
        source.register(Broken)
        with pytest.raises(ContainerBuildError):
            source.build()
        assert source._composition is boundary._composition is None
        with pytest.raises(BuilderAlreadyBuiltError):
            source.build()
        with pytest.raises(BuilderAlreadyBuiltError):
            boundary.register(Leaf)
        assert isinstance(parent.resolve(Service).leaf, Leaf)


def test_caller_owned_component_snapshot_preserves_opaque_identity_and_relationships():
    saved = []
    source = builder()

    def observe(component):
        saved.append(compiler._undecorated_component_view(component))
        return True

    source.register(Service, when=observe)
    with source.build() as runtime:
        assert source._composition is None
        for component in saved:
            dependency = component.dependencies[0]
            assert dependency.parent.occurrence_id == component.occurrence_id
            assert dependency.implementation is Leaf
            assert dependency.parent._graph is component._graph
        assert isinstance(runtime.resolve(Service).leaf, Leaf)


@pytest.mark.parametrize("operation", ["build", "analyse"])
def test_optional_observer_preserves_execution_without_rich_runtime_ownership(operation):
    from clean_ioc import Instrumentation, ResolutionProfiler

    source = builder()
    source.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service)]))
    profiler = ResolutionProfiler(sample_durations=0)
    instrumentation = Instrumentation(profiler)
    if operation == "build":
        result = None
        runtime = source.build(instrumentation=instrumentation)
    else:
        result = source.analyse()
        runtime = result.create_runtime(instrumentation=instrumentation)
    with runtime:
        assert type(runtime._plan) is compiler._ExecutionPlan
        assert runtime.warmup("start").is_valid
        assert isinstance(runtime.resolve(Service).leaf, Leaf)
        assert any(record.attempts for record in profiler.report().records)
    if result is not None:
        result.close()


def test_local_failure_does_not_freeze_discarded_graph_or_retry_callbacks(monkeypatch):
    calls = []

    def fail(component):
        calls.append(component)
        raise ValueError("failed once")

    source = ContainerBuilder().set_provider_roots(())
    source.register(Leaf, when=fail)
    monkeypatch.setattr(compiler._ComponentGraph, "freeze", forbid)
    monkeypatch.setattr(compiler, "_error_report", forbid)
    with pytest.raises(ContainerBuildError) as caught:
        source.build()
    assert len(calls) == 1
    assert caught.value.report is None
    assert caught.value.partial_graph is None


def test_concurrent_pre_admission_callers_cannot_start_two_compilations(monkeypatch):
    import threading

    source = builder()
    ready = threading.Barrier(2)
    compiling = threading.Event()
    other_finished = threading.Event()
    original_inputs = source._effective_build_args
    original_compile = compiler._Compiler.compile_execution
    outcomes = []
    calls = []

    def inputs(values):
        result = original_inputs(values)
        if not source._compiling:
            ready.wait(timeout=3)
        return result

    def compile_once(self):
        calls.append("compile")
        compiling.set()
        assert other_finished.wait(timeout=3)
        return original_compile(self)

    def run():
        try:
            outcomes.append(source.build())
        except BuilderAlreadyBuiltError as error:
            outcomes.append(error)
            other_finished.set()

    monkeypatch.setattr(source, "_effective_build_args", inputs)
    monkeypatch.setattr(compiler._Compiler, "compile_execution", compile_once)
    first, second = threading.Thread(target=run), threading.Thread(target=run)
    first.start()
    second.start()
    assert compiling.wait(timeout=3)
    first.join(timeout=3)
    second.join(timeout=3)
    assert not first.is_alive() and not second.is_alive()
    assert calls == ["compile"]
    assert sum(isinstance(outcome, BuilderAlreadyBuiltError) for outcome in outcomes) == 1
    runtime = next(outcome for outcome in outcomes if not isinstance(outcome, BuilderAlreadyBuiltError))
    assert isinstance(runtime.resolve(Service).leaf, Leaf)
    runtime.__exit__(None, None, None)
