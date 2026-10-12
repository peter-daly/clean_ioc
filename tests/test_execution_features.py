"""Compact optional execution features and external composition ownership."""

import gc
import weakref
from dataclasses import FrozenInstanceError
from typing import Generic, TypeVar

import pytest

import clean_ioc.container as compiler
import clean_ioc.graph_analysis as graph_analysis
from clean_ioc import (
    BuilderAlreadyBuiltError,
    CompilationProfiler,
    Composition,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    RegistrationTemplate,
    ResolutionProfiler,
    ScopeBuilder,
    ScopeClosedError,
    WarmupPlan,
    WarmupTarget,
)
from clean_ioc import component_filters as cf


class Service:
    pass


class Missing:
    pass


def forbidden(*args, **kwargs):
    raise AssertionError("Execution allocated an analysis owner")


def forbid_analysis(monkeypatch):
    for cls in (compiler._PlanSet, compiler.CompiledGraph, compiler.VerificationReport, compiler.ValidationContext):
        monkeypatch.setattr(cls, "__init__", forbidden)
    for name in ("_compile_with_report", "_finalize_plan", "_census_inventory"):
        monkeypatch.setattr(compiler, name, forbidden)
    monkeypatch.setattr(graph_analysis, "graph_index", forbidden)
    monkeypatch.setattr(compiler.CompiledGraph, "manifest", forbidden)
    monkeypatch.setattr(compiler.CompiledGraph, "sharing_report", forbidden)


@pytest.mark.parametrize("warmup,observed", [(True, False), (False, True), (True, True)])
@pytest.mark.parametrize("overlay", [False, True])
def test_optional_features_never_allocate_analysis_even_with_retained_composition(
    monkeypatch, warmup, observed, overlay
):
    events = []
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service, factory=lambda: events.append("activated") or Service(), lifespan="singleton")
    builder.add_validation_rule(forbidden)
    if warmup:
        builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service), WarmupTarget(Service)]))
    composition = builder.retain_composition()
    profiler = ResolutionProfiler(sample_durations=0)
    forbid_analysis(monkeypatch)
    with builder.build(
        instrumentation=Instrumentation(profiler) if observed else None, profile=CompilationProfiler()
    ) as parent:
        assert events == []
        if overlay:
            child_builder = ScopeBuilder(parent.new_scope(), composition=composition)
            child_builder.retain_composition()
            runtime = child_builder.build(profile=CompilationProfiler())
        else:
            runtime = parent.new_scope()
        with runtime:
            if warmup:
                assert runtime.warmup("start").is_valid
                assert runtime.warmup("start").plan_id == runtime._plan.identity
            assert runtime.resolve(Service) is parent.resolve(Service)
        assert events == ["activated"]
        if observed:
            report = profiler.report()
            assert not report.incomplete
            assert sum(record.attempts for record in report.records if record.kind == "registration") == 1


def test_pending_handle_identity_and_admission():
    builder = ContainerBuilder().set_provider_roots(())
    handle = builder.retain_composition()
    assert isinstance(handle, Composition)
    assert builder.retain_composition() is handle
    assert not handle.is_ready
    with ContainerBuilder().build() as foreign:
        with pytest.raises(RuntimeError, match="complete emitted"):
            ScopeBuilder(foreign, composition=handle)
    with pytest.raises(TypeError):
        builder.build(instrumentation=object())  # ty: ignore[invalid-argument-type]
    assert builder.retain_composition() is handle
    builder.register(Service)
    with builder.build() as parent:
        assert handle.is_ready
        with pytest.raises(BuilderAlreadyBuiltError):
            builder.retain_composition()
        with ScopeBuilder(parent, composition=handle).build() as child:
            assert isinstance(child.resolve(Service), Service)
    for name in ("close", "aclose", "__enter__", "__exit__", "__aenter__", "__aexit__"):
        assert not hasattr(handle, name)
    assert not hasattr(parent, "new_scope_builder")


@pytest.mark.parametrize("operation", ["build", "verify"])
def test_failed_emission_leaves_requested_handle_unusable(operation):
    class Root:
        def __init__(self, missing: Missing):
            pass

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Root)
    handle = builder.retain_composition()
    if operation == "build":
        with pytest.raises(ContainerBuildError):
            builder.build()
    else:
        result = builder.verify()
        assert not result.emission_complete
        assert result.composition is None
    assert not handle.is_ready
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.register(Service)


def test_matching_parent_and_ordinary_descendants_and_new_overlay_handle():
    first = ContainerBuilder().set_provider_roots(())
    first.register(Service, lifespan="singleton")
    first_handle = first.retain_composition()
    second = ContainerBuilder().set_provider_roots(())
    second.register(Service, lifespan="singleton")
    with first.build() as parent, second.build() as foreign:
        with pytest.raises(ValueError, match="owner lineage"):
            ScopeBuilder(foreign, composition=first_handle)
        with parent.new_scope() as ordinary:
            child_builder = ScopeBuilder(ordinary, composition=first_handle)
            child_builder.register(Missing)
            child_handle = child_builder.retain_composition()
            with child_builder.build() as child:
                with pytest.raises(ValueError, match="owner lineage"):
                    ScopeBuilder(child, composition=first_handle)
                with child.new_scope() as ordinary_child:
                    with ScopeBuilder(ordinary_child, composition=child_handle).build() as grandchild:
                        assert grandchild.resolve(Service) is parent.resolve(Service)
                        assert isinstance(grandchild.resolve(Missing), Missing)
    with pytest.raises(ScopeClosedError):
        ScopeBuilder(parent, composition=first_handle)


def test_sealed_declaration_structure_is_immutable_and_opaque_values_keep_identity():
    fixed = {"opaque": []}
    instance = Service()

    class Root:
        def __init__(self, value: dict, service: Service):
            self.value, self.service = value, service

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service, instance=instance)
    builder.register(Root, arguments={"value": fixed})
    handle = builder.retain_composition()
    with builder.build(build_args={"opaque": fixed}) as parent:
        with pytest.raises(FrozenInstanceError):
            setattr(handle, "_identity", "changed")
        snapshot = handle._snapshot
        assert snapshot is not None
        assert snapshot.build_args["opaque"] is fixed
        with pytest.raises(TypeError):
            snapshot.build_args["changed"] = fixed  # ty: ignore[invalid-assignment]
        with pytest.raises(FrozenInstanceError):
            setattr(snapshot, "layers", ())
        layer = snapshot.layers[0]
        with pytest.raises(TypeError):
            dict(layer.values)["registration_when"]["changed"] = lambda _: True
        registration = next(source for _, sources in layer.registrations for source in sources)
        with pytest.raises(FrozenInstanceError):
            setattr(registration, "dependencies", ())
        with ScopeBuilder(parent, composition=handle).build() as child:
            value = child.resolve(Root)
            assert value.value is fixed
            assert value.service is instance
        assert parent.resolve(Root).value is fixed


def test_consumed_builder_and_runtime_do_not_retain_handle_or_unselected_source():
    class Rule:
        def __call__(self, context):
            return ()

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service)
    rule = Rule()
    rule_ref = weakref.ref(rule)
    builder.add_validation_rule(rule)
    del rule
    handle = builder.retain_composition()
    handle_ref = weakref.ref(handle)
    with builder.build() as parent:
        assert rule_ref() is not None
        active = ScopeBuilder(parent, composition=handle)
        del handle
        gc.collect()
        assert handle_ref() is None
        assert rule_ref() is not None  # the active builder owns its reconstructed source
        with active.build() as child:
            gc.collect()
            assert rule_ref() is None
            assert isinstance(child.resolve(Service), Service)
            assert isinstance(parent.resolve(Service), Service)


def test_analysis_composition_is_independent_of_result_and_multiple_test_runtime_states():
    calls = []
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service, lifespan="singleton")
    builder.pre_configure(Service, lambda: calls.append("configure"))
    handle = builder.retain_composition()
    result = builder.verify()
    assert result.composition is handle
    profiler = ResolutionProfiler(sample_durations=0)
    first = result.create_runtime(instrumentation=Instrumentation(profiler))
    second = result.create_runtime(instrumentation=Instrumentation(profiler))
    assert first.resolve(Service) is not second.resolve(Service)
    assert calls == ["configure", "configure"]
    assert len(profiler.report().executions) == 2
    for runtime in (first, second):
        with ScopeBuilder(runtime, composition=handle).build() as child:
            assert child.resolve(Service) is runtime.resolve(Service)
    result.close()
    assert handle.is_ready
    assert result.composition is handle
    with pytest.raises(ScopeClosedError):
        ScopeBuilder(first, composition=handle)


def test_capture_does_not_replay_discovery_or_realized_registration_templates():
    class Base:
        pass

    class Original(Base):
        pass

    class Generated:
        def __init__(self, value):
            self.value = value

    calls = []
    builder = ContainerBuilder().set_provider_roots(())
    builder.register_subclasses(Base)

    def template(source):
        calls.append(source.id)
        return RegistrationTemplate(Generated, factory=lambda: Generated(source.id), name=source.id)

    builder.register_registration_template(for_each=Base, template=template)
    handle = builder.retain_composition()
    assert calls == []
    with builder.build() as parent:
        before = list(calls)
        assert len(before) == 1

        class Later(Base):
            pass

        child_builder = ScopeBuilder(parent, composition=handle)
        assert calls == before
        with child_builder.build() as child:
            assert calls == before  # existing generated registration is reused
            assert [info.implementation_type for info in child.selected_registrations if info.service_type is Base] == [
                Original
            ]
            assert child.resolve(Generated, cf.with_name(before[0])).value == before[0]


def test_closed_generic_cache_groups_use_specialized_executable_keys():
    item = TypeVar("item")

    class Box(Generic[item]):
        def __init__(self, value: item):
            self.value = value

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(int, instance=1)
    builder.register(str, instance="text")

    def factory(value: item) -> Box[item]:
        return Box(value)

    declaration_id = builder.register_pattern(Box[item], factory=factory, lifespan="singleton")
    builder.register(Service, arguments={})
    builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Box[int]), WarmupTarget(Box[str])]))
    profiler = ResolutionProfiler(sample_durations=0)
    with builder.build(instrumentation=Instrumentation(profiler)) as runtime:
        runtime.warmup("start").assert_valid()
        assert runtime.resolve(Box[int]) is not runtime.resolve(Box[str])
        paths = {target.path for target in runtime.warmup_plans[0].targets}
        records = [record for record in profiler.report().records if record.path in paths]
        assert len(records) == 2
        assert declaration_id not in {record.registration for record in records}
        group_ids = {record.cache_group for record in records}
        groups = [group for group in profiler.report().cache_groups if group.cache_group in group_ids]
        assert len(groups) == 2
        assert all(group.cache_misses == 1 and group.cache_hits == 1 for group in groups)


@pytest.mark.parametrize("lifespan,expected", [("transient", 4), ("per_resolution", 4), ("scoped", 1)])
def test_repeated_warmups_keep_order_and_declared_cache_and_cleanup(lifespan, expected):
    events = []

    def factory():
        events.append("acquire")
        try:
            yield Service()
        finally:
            events.append("release")

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service, factory=factory, lifespan=lifespan)
    builder.add_warmup_plan(WarmupPlan("repeat", [WarmupTarget(Service), WarmupTarget(Service)]))
    profiler = ResolutionProfiler(sample_durations=0)
    with builder.build(instrumentation=Instrumentation(profiler)) as runtime:
        assert events == []
        for _ in range(2):
            report = runtime.warmup("repeat")
            assert [value.status for value in report.results] == ["succeeded", "succeeded"]
            assert report.plan_id == runtime._plan.identity
            assert "graph_fingerprint" not in report.to_json()
        assert events == ["acquire"] * expected
        assert sum(record.attempts for record in profiler.report().records if record.kind == "registration") == expected
    assert events == ["acquire"] * expected + ["release"] * expected


@pytest.mark.parametrize("missing", [False, True])
def test_warmup_unbindable_target_raises_minimal_error_without_analysis(monkeypatch, missing):
    builder = ContainerBuilder().set_provider_roots(())
    if not missing:
        builder.register(Service)
        builder.register(Service)
    builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service)]))
    handle = builder.retain_composition()
    forbid_analysis(monkeypatch)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(instrumentation=Instrumentation(ResolutionProfiler(sample_durations=0)))
    assert caught.value.code == ("warmup-missing-component" if missing else "warmup-ambiguous-component")
    assert caught.value.report is None
    assert not handle.is_ready


@pytest.mark.asyncio
async def test_async_warmup_guard_failure_aggregation_and_overlay_cleanup(monkeypatch):
    import json

    events = []

    async def resource():
        events.append("acquire")
        try:
            yield Service()
        finally:
            events.append("release")

    def fail():
        raise ValueError("private application text")

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service, factory=resource, lifespan="transient")
    builder.register(Missing, factory=fail)
    builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service), WarmupTarget(Missing)]))
    composition = builder.retain_composition()
    profiler = ResolutionProfiler(sample_durations=0)
    forbid_analysis(monkeypatch)
    async with builder.build(instrumentation=Instrumentation(profiler)) as parent:
        async with ScopeBuilder(parent, composition=composition).build() as child:
            report = child.warmup("start")
            assert [item.status for item in report.results] == ["not_executed", "not_executed"]
            assert events == []
            report = await child.warmup_async("start")
            assert [item.status for item in report.results] == ["succeeded", "failed"]
            assert events == ["acquire"]
            assert "private application text" not in report.to_json()
        assert events == ["acquire", "release"]
        assert not parent._closed
        assert not profiler.report().incomplete
    # Export intentionally constructs a report; compilation and execution did not.
    monkeypatch.undo()
    sarif = json.loads(report.to_sarif())
    assert sarif["runs"][0]["properties"]["executionPlanId"] == report.plan_id
    assert "graphFingerprint" not in sarif["runs"][0]["properties"]


def test_instrumented_overlay_slots_maps_managed_and_per_call_cleanup(monkeypatch):
    from collections.abc import Mapping
    from typing import Protocol

    from clean_ioc import ManagedProvider, Provider, ProviderMapGroup

    class Request:
        pass

    class Resource:
        def __init__(self, request: Request):
            self.request = request

    class Call(Protocol):
        def run(self) -> Request: ...

    class Target:
        def __init__(self, resource: Resource):
            self.resource = resource

        def run(self):
            return self.resource.request

    events = []

    def resource(request: Request):
        events.append("acquire")
        try:
            yield Resource(request)
        finally:
            events.append("release")

    group = ProviderMapGroup("resources", str, Resource)
    builder = ContainerBuilder().set_provider_roots((ManagedProvider[Resource],))
    builder.declare_scope_slot(Request)
    builder.register(Resource, factory=resource, lifespan="scoped", contributes={group: "resource"})
    builder.register_provider_map(group)
    builder.register(Call, Target, scope="per_call")
    composition = builder.retain_composition()
    profiler = ResolutionProfiler(sample_durations=0)
    forbid_analysis(monkeypatch)
    with builder.build(instrumentation=Instrumentation(profiler)) as parent:
        ordinary = parent.new_scope()
        request = Request()
        ordinary.provide(Request, request)
        with ScopeBuilder(ordinary, composition=composition).build() as child:
            assert child.resolve(Mapping[str, Provider[Resource]])["resource"]().request is request
            managed = child.resolve(ManagedProvider[Resource])
            with managed() as acquired:
                assert acquired.request is request
            call = child.resolve(Call)
            assert call.run() is request
            assert call.run() is request
            assert events.count("acquire") == 4
            assert events.count("release") == 3
        assert events.count("release") == 4
        assert not profiler.report().incomplete
        ordinary._close()


def test_unrequested_composition_is_not_allocated_and_plain_scopes_still_work(monkeypatch):
    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service)
    builder.add_warmup_plan(WarmupPlan("start", [WarmupTarget(Service)]))
    monkeypatch.setattr(Composition, "__init__", forbidden)
    monkeypatch.setattr(compiler._CapturedComposition, "capture", forbidden)
    with builder.build(instrumentation=Instrumentation(ResolutionProfiler(sample_durations=0))) as runtime:
        with runtime.new_scope() as child:
            assert child.warmup("start").is_valid
            assert isinstance(child.resolve(Service), Service)


def test_analysis_only_failure_still_exposes_completed_execution_composition():
    class Broken:
        def __init__(self, missing: Missing):
            pass

    builder = ContainerBuilder().set_provider_roots(())
    builder.register(Service)
    builder.create_boundary("unused").register(Broken)
    result = builder.verify()
    assert not result.complete
    assert result.emission_complete
    assert result.composition is not None and result.composition.is_ready
    with result:
        parent = result.create_runtime()
        assert result.composition is not None
        with ScopeBuilder(parent, composition=result.composition).build() as child:
            assert isinstance(child.resolve(Service), Service)
