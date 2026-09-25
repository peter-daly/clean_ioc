"""Runtime profiling exercises the actual compiled execution path."""

import asyncio
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Generic, Protocol, TypeVar

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    CompilationProfiler,
    ContainerBuilder,
    Instrumentation,
    Provider,
    ProviderMapGroup,
    ResolutionContext,
    ResolutionProfiler,
    Scope,
)
from clean_ioc import component_filters as cf
from clean_ioc.container import _ResolutionRequest, default_component_filter


def _record(profile, kind, suffix):
    return next(record for record in profile.records if record.kind == kind and record.path.endswith(suffix))


def test_exact_singleton_cache_counts_and_sampled_request_time():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    profiler = ResolutionProfiler(sample_durations=0.5)
    container = builder.build(instrumentation=Instrumentation(profiler))
    fingerprint = container.graph.manifest(all_roots=True).fingerprint
    first = container.resolve(Service)
    assert container.resolve(Service) is first
    assert container.new_scope().resolve(Service) is first

    report = profiler.report()
    assert report.graphs == (fingerprint,)
    assert report.in_flight == 0 and not report.incomplete
    request = _record(report, "request", "Service")
    registration = next(record for record in report.records if record.registration and record.attempts)
    assert (request.attempts, request.completed, request.failed) == (3, 3, 0)
    assert (registration.attempts, registration.completed, registration.cache_misses, registration.cache_hits) == (
        1,
        1,
        1,
        2,
    )
    assert dict(request.durations)["request"].samples == 1
    assert report.to_json() == report.to_json()


def test_runtime_instrumentation_is_independent_of_compilation_profile_and_fingerprint():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    compiler = CompilationProfiler()
    profiler = ResolutionProfiler()
    container = builder.build(profile=compiler, instrumentation=Instrumentation(profiler))
    assert compiler.report().state == "completed"
    assert isinstance(container.resolve(Service), Service)
    assert profiler.report().graphs == (container.graph.manifest(all_roots=True).fingerprint,)
    plain_builder = ContainerBuilder()
    plain_builder.register(Service)
    plain = plain_builder.build()
    assert plain.graph.manifest(all_roots=True).to_json() == container.graph.manifest(all_roots=True).to_json()
    assert not hasattr(plain._plan.default_roots[Service].step, "_profile_key")
    assert "_profiler" not in Scope.resolve.__code__.co_names
    assert "_profiler" not in Scope.resolve_async.__code__.co_names
    assert "_profiler" not in Scope.new_scope.__code__.co_names


def test_profiler_rejects_equivalent_second_runtime_without_mixing_catalogs():
    class Service:
        pass

    profiler = ResolutionProfiler()
    first_builder = ContainerBuilder()
    first_builder.register(Service, lifespan="singleton")
    first = first_builder.build(instrumentation=Instrumentation(profiler))
    first.resolve(Service)
    baseline = profiler.report()
    second_builder = ContainerBuilder()
    second_builder.register(Service, lifespan="singleton")
    with pytest.raises(ValueError, match="already bound to a different runtime"):
        second_builder.build(instrumentation=Instrumentation(profiler))
    assert profiler.report().records == baseline.records


def test_same_fingerprint_overlay_reuses_parent_profiler_and_catalog():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    overlay = container.new_scope_builder().build()
    assert overlay.resolve(Service) is container.resolve(Service)
    report = profiler.report()
    assert len(report.graphs) == 1
    assert not report.incomplete


def test_declared_resolution_context_request_has_graph_activation_owner_and_call_edge():
    class Shared:
        pass

    class Root:
        def __init__(self, context: ResolutionContext):
            self.shared = context.resolve(Shared)

    setattr(Root, "__clean_ioc_resolution_requests__", (_ResolutionRequest(Shared, default_component_filter, False),))
    builder = ContainerBuilder()
    builder.register(Shared, lifespan="singleton")
    builder.register(Root)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    assert isinstance(container.resolve(Root).shared, Shared)
    records = profiler.report().records
    edge = next(record for record in records
                if record.kind == "registration" and "dependency:resolution" in record.path)
    assert (edge.attempts, edge.cache_misses) == (1, 1)
    assert not any(record.path == "<unresolved request>" and record.kind == "registration" and record.attempts
                   for record in records)


def test_nested_factory_time_excludes_dependency_and_provider_calls():
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Service)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    provider = container.resolve(Provider[Service])
    assert isinstance(provider(), Service)
    assert isinstance(provider(), Service)
    report = profiler.report()
    service = next(
        record
        for record in report.records
        if record.registration and record.path.endswith("Service:default:0") and record.attempts
    )
    assert service.attempts == 2
    durations = dict(service.durations)
    assert durations["body"].samples == 2
    assert durations["dependencies"].samples == 2
    assert any(
        record.kind == "request" and record.path.startswith("provider request ") and record.attempts == 2
        for record in report.records
    )


def test_async_singleton_waiter_and_retry_after_failure():
    class Service:
        pass

    gate = asyncio.Event()
    calls = 0

    async def factory() -> Service:
        nonlocal calls
        calls += 1
        if calls == 1:
            await gate.wait()
            raise ValueError("secret failure")
        return Service()

    async def exercise():
        builder = ContainerBuilder()
        builder.register(Service, factory=factory, lifespan="singleton")
        profiler = ResolutionProfiler(sample_durations=0)
        container = builder.build(instrumentation=Instrumentation(profiler))
        first = asyncio.create_task(container.resolve_async(Service))
        await asyncio.sleep(0)
        second = asyncio.create_task(container.resolve_async(Service))
        await asyncio.sleep(0)
        gate.set()
        results = await asyncio.gather(first, second, return_exceptions=True)
        assert all(isinstance(item, ValueError) for item in results)
        assert isinstance(await container.resolve_async(Service), Service)
        return profiler.report()

    report = asyncio.run(exercise())
    registration = next(record for record in report.records if record.registration and record.attempts)
    assert (registration.attempts, registration.completed, registration.failed) == (2, 1, 1)
    assert registration.cache_waits == 1
    assert all(summary.samples == 0 for _, summary in registration.durations)
    assert "secret failure" not in report.to_json()


def test_concurrent_parents_keep_cache_wait_on_actual_call_edge():
    class Shared:
        pass

    class First:
        def __init__(self, shared: Shared):
            self.shared = shared

    class Second:
        def __init__(self, shared: Shared):
            self.shared = shared

    entered = asyncio.Event()
    release = asyncio.Event()

    async def factory() -> Shared:
        entered.set()
        await release.wait()
        return Shared()

    async def exercise():
        builder = ContainerBuilder()
        builder.register(Shared, factory=factory, lifespan="singleton")
        builder.register(First)
        builder.register(Second)
        profiler = ResolutionProfiler()
        container = builder.build(instrumentation=Instrumentation(profiler))
        first = asyncio.create_task(container.resolve_async(First))
        await entered.wait()
        second = asyncio.create_task(container.resolve_async(Second))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        return profiler.report()

    report = asyncio.run(exercise())
    first_edge = next(record for record in report.records
                      if record.kind == "registration" and "First:default" in record.path
                      and "dependency:shared" in record.path)
    second_edge = next(record for record in report.records
                       if record.kind == "registration" and "Second:default" in record.path
                       and "dependency:shared" in record.path)
    assert (first_edge.cache_misses, first_edge.cache_waits) == (1, 0)
    assert (second_edge.cache_misses, second_edge.cache_waits) == (1, 1)
    assert sum(record.attempts for record in (first_edge, second_edge)) == 1


def test_text_report_ranks_sampled_requests_waits_and_exact_activations():
    class Service:
        pass

    entered = asyncio.Event()
    release = asyncio.Event()

    async def factory() -> Service:
        entered.set()
        await release.wait()
        return Service()

    async def exercise():
        builder = ContainerBuilder()
        builder.register(Service, factory=factory, lifespan="singleton")
        profiler = ResolutionProfiler()
        container = builder.build(instrumentation=Instrumentation(profiler))
        first = asyncio.create_task(container.resolve_async(Service))
        await entered.wait()
        second = asyncio.create_task(container.resolve_async(Service))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        return profiler.report().to_text()

    report_text = asyncio.run(exercise())
    assert "Most frequent activations (exact counts)" in report_text
    assert "Slowest sampled requests (maximum measured inclusive duration)" in report_text
    assert "Largest measured cache-wait totals (timed samples only; wait counts exact)" in report_text


def test_resource_cleanup_and_live_snapshot_are_separate_operations():
    class Resource:
        pass

    calls = []

    @contextmanager
    def factory():
        calls.append("acquire")
        try:
            yield Resource()
        finally:
            calls.append("release")

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory, lifespan="scoped")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    scope = container.new_scope()
    assert isinstance(scope.resolve(Resource), Resource)
    assert calls == ["acquire"]
    before = profiler.report()
    assert not any(record.kind == "cleanup" and record.attempts for record in before.records)
    scope._close()
    assert calls == ["acquire", "release"]
    after = profiler.report()
    assert any(record.kind == "cleanup" and record.attempts == 1 and record.completed == 1 for record in after.records)


def test_provider_map_and_overlay_use_same_profiler():
    class Service:
        pass

    group = ProviderMapGroup("services", str, Service)
    builder = ContainerBuilder()
    builder.register(Service, contributes={group: "private-key"})
    builder.register_provider_map(group)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    overlay_builder = container.new_scope_builder()

    class Extra:
        pass

    overlay_builder.register(Extra)
    overlay = overlay_builder.build()
    mapping = overlay.resolve(Mapping[str, Provider[Service]])
    assert isinstance(mapping["private-key"](), Service)
    assert isinstance(overlay.resolve(Extra), Extra)
    report = profiler.report()
    assert len(report.graphs) == 2
    assert "private-key" not in report.to_json()
    assert any(
        record.kind == "request" and record.path.startswith("provider request ") and record.attempts
        for record in report.records
    )


def test_overlay_rejects_different_profiler_before_build():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    container = builder.build(instrumentation=Instrumentation(ResolutionProfiler()))
    with pytest.raises(ValueError, match="must match"):
        container.new_scope_builder().build(instrumentation=Instrumentation(ResolutionProfiler()))


def test_anchored_singleton_activation_stays_with_parent_and_hit_uses_overlay_path():
    class Service:
        pass

    class Extra:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    instance = container.resolve(Service)
    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Extra)
    overlay = overlay_builder.build()
    assert overlay.resolve(Service) is instance
    report = profiler.report()
    parent_fingerprint = container.graph.manifest(all_roots=True).fingerprint
    overlay_fingerprint = overlay.graph.manifest(all_roots=True).fingerprint
    assert parent_fingerprint != overlay_fingerprint
    assert any(
        record.graph_fingerprint == parent_fingerprint and record.registration and record.attempts == 1
        for record in report.records
    )
    assert any(
        record.graph_fingerprint == overlay_fingerprint and record.registration and record.cache_hits == 1
        for record in report.records
    )


def test_overlay_first_activation_keeps_parent_owner_and_overlay_cache_edge():
    class Service:
        pass

    class Extra:
        pass

    configured = []

    def configure() -> None:
        configured.append(True)

    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    builder.pre_configure(Service, configure)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Extra)
    overlay = overlay_builder.build()
    assert isinstance(overlay.resolve(Service), Service)
    assert configured == [True]
    parent_graph = container.graph.manifest(all_roots=True).fingerprint
    overlay_graph = overlay.graph.manifest(all_roots=True).fingerprint
    records = profiler.report().records
    assert any(record.graph_fingerprint == parent_graph and record.kind == "registration"
               and "Service:default" in record.path and record.attempts == 1 for record in records)
    assert any(record.graph_fingerprint == parent_graph and record.kind == "pre_configuration"
               and record.attempts == 1 for record in records)
    assert any(record.graph_fingerprint == overlay_graph and record.kind == "registration"
               and "Service:default" in record.path and record.cache_misses == 1 for record in records)
    assert any(record.graph_fingerprint == overlay_graph and record.kind == "pre_configuration"
               and record.cache_misses == 1 for record in records)
    assert not any(record.kind == "registration" and "Extra:default" in record.path and record.attempts
                   for record in records)


def test_named_registrations_and_closed_generic_have_separate_paths():
    class Service:
        pass

    class First(Service):
        pass

    class Second(Service):
        pass

    T = TypeVar("T")

    class Box(Generic[T]):
        def __init__(self, value: T):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Service, First, name="first")
    builder.register(Service, Second, name="second")
    builder.register(Box[int], factory=lambda: Box(42))
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    assert isinstance(container.resolve(Service, cf.with_name("first")), First)
    assert isinstance(container.resolve(Service, cf.with_name("second")), Second)
    assert container.resolve(Box[int]).value == 42
    active = [record for record in profiler.report().records if record.registration and record.attempts]
    assert len(active) == 3
    assert len({record.path for record in active}) == 3


def test_shared_nested_cache_consumer_uses_exact_parent_occurrence():
    class Shared:
        pass

    class First:
        def __init__(self, shared: Shared):
            self.shared = shared

    class Second:
        def __init__(self, shared: Shared):
            self.shared = shared

    builder = ContainerBuilder()
    builder.register(Shared, lifespan="singleton")
    builder.register(First)
    builder.register(Second)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    first = container.resolve(First)
    assert container.resolve(Second).shared is first.shared
    report = profiler.report()
    assert not any(record.path.endswith("[cache caller unresolved]") and record.cache_hits
                   for record in report.records)
    first_edge = next(record for record in report.records
                      if record.kind == "registration" and "First:default" in record.path
                      and "dependency:shared" in record.path)
    second_edge = next(record for record in report.records
                       if record.kind == "registration" and "Second:default" in record.path
                       and "dependency:shared" in record.path)
    assert (first_edge.cache_misses, first_edge.cache_hits) == (1, 0)
    assert (second_edge.cache_misses, second_edge.cache_hits) == (0, 1)
    assert (
        sum(
            record.attempts
            for record in report.records
            if record.registration == first_edge.registration and record.kind == "registration"
        )
        == 1
    )
    assert any(group.cache_hits == 1 and group.cache_misses == 1 for group in report.sharing_groups)


def test_collection_and_deferred_provider_cache_edges_keep_compiled_paths():
    class Shared:
        pass

    class Holder:
        def __init__(self, items: list[Shared], deferred: Provider[Shared]):
            self.items = items
            self.deferred = deferred

    builder = ContainerBuilder()
    builder.register(Shared, lifespan="singleton")
    builder.register(Holder)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    holder = container.resolve(Holder)
    assert len(holder.items) == 1
    assert holder.deferred() is holder.deferred()
    records = profiler.report().records
    collection_edge = next(record for record in records
                           if record.kind == "registration" and "dependency:items" in record.path
                           and record.cache_misses)
    provider_edge = next(record for record in records
                         if record.kind == "registration" and "Holder:default" in record.path
                         and "dependency:deferred" in record.path
                         and record.cache_hits)
    assert collection_edge.cache_misses == 1
    assert provider_edge.cache_hits == 2
    assert not any(record.path.endswith("[cache caller unresolved]") and record.cache_hits for record in records)


def test_collection_and_alias_requests_have_safe_distinct_labels():
    class First:
        pass

    class Second:
        pass

    alias = TypeAliasType("alias", First)
    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    assert isinstance(container.resolve(alias), First)
    assert len(container.resolve(list[First])) == 1
    assert len(container.resolve(list[Second])) == 1
    requests = [record for record in profiler.report().records if record.kind == "request" and record.attempts]
    assert len(requests) == 3
    assert len({record.path for record in requests}) == 3
    assert all(record.path != "<unresolved request>" for record in requests)


def test_pre_configuration_and_decorator_are_distinct_activations():
    class Service:
        pass

    class Decorator(Service):
        def __init__(self, child: Service):
            self.child = child

    calls = []

    def configure() -> None:
        calls.append("configured")

    builder = ContainerBuilder()
    builder.register(Service)
    builder.pre_configure(Service, configure)
    builder.register_decorator(Service, Decorator, decorated_arg="child")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    assert isinstance(container.resolve(Service), Decorator)
    assert isinstance(container.resolve(Service), Decorator)
    assert calls == ["configured"]
    report = profiler.report()
    assert any(
        record.kind == "pre_configuration" and record.attempts == 1 and record.cache_hits == 1
        for record in report.records
    )
    assert any(
        record.kind == "decorator" and record.attempts == 2 and dict(record.durations)["body"].samples == 2
        for record in report.records
    )


def test_shared_pre_configuration_cache_outcomes_use_triggering_paths():
    class First:
        pass

    class Second:
        pass

    calls = []

    def configure() -> None:
        calls.append(True)

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    builder.pre_configure((First, Second), configure)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    container.resolve(Second)
    container.resolve(First)
    assert calls == [True]
    records = [record for record in profiler.report().records if record.kind == "pre_configuration"]
    first = next(record for record in records if "First:default" in record.path)
    second = next(record for record in records if "Second:default" in record.path)
    assert (first.cache_hits, first.cache_misses) == (1, 0)
    assert (second.cache_hits, second.cache_misses) == (0, 1)
    assert sum(record.attempts for record in records) == 1


def test_concurrent_shared_pre_configuration_wait_is_a_miss_on_waiting_path():
    class First:
        pass

    class Second:
        pass

    entered = asyncio.Event()
    release = asyncio.Event()

    async def configure() -> None:
        entered.set()
        await release.wait()

    async def exercise():
        builder = ContainerBuilder()
        builder.register(First)
        builder.register(Second)
        builder.pre_configure((First, Second), configure)
        profiler = ResolutionProfiler()
        container = builder.build(instrumentation=Instrumentation(profiler))
        first = asyncio.create_task(container.resolve_async(First))
        await entered.wait()
        second = asyncio.create_task(container.resolve_async(Second))
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, second)
        return profiler.report()

    records = [record for record in asyncio.run(exercise()).records if record.kind == "pre_configuration"]
    first = next(record for record in records if "First:default" in record.path)
    second = next(record for record in records if "Second:default" in record.path)
    assert (first.cache_misses, first.cache_waits) == (1, 0)
    assert (second.cache_misses, second.cache_waits) == (1, 1)
    assert sum(record.attempts for record in records) == 1


def test_per_call_profiles_di_work_but_excludes_service_method():
    class Service(Protocol):
        def run(self) -> str: ...

    class Impl:
        def run(self) -> str:
            return "business result"

    builder = ContainerBuilder()
    builder.register(Service, Impl, scope="per_call")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    handle = container.resolve(Service)
    assert handle.run() == handle.run() == "business result"
    report = profiler.report()
    assert any(
        record.kind == "request" and record.path.startswith("per-call request ") and record.attempts == 2
        for record in report.records
    )
    assert any(record.kind == "registration" and record.attempts == 2 for record in report.records)
    assert any(record.kind == "registration" and "dependency:per_call_target" in record.path
               and record.attempts == 2 for record in report.records)
    assert not any(record.path.endswith("[cache caller unresolved]") and record.cache_misses
                   for record in report.records)
    assert "business result" not in report.to_json()


def test_cleanup_failure_is_reported_without_changing_exception():
    class Resource:
        pass

    @contextmanager
    def factory():
        yield Resource()
        raise RuntimeError("secret cleanup text")

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    container.resolve(Resource)
    with pytest.raises(RuntimeError, match="secret cleanup text"):
        container._close()
    report = profiler.report()
    assert any(record.kind == "cleanup" and record.failed == 1 for record in report.records)
    assert "secret cleanup text" not in report.to_json()


def test_async_resource_cleanup():
    class Resource:
        pass

    closed = []

    @asynccontextmanager
    async def factory():
        try:
            yield Resource()
        finally:
            closed.append(True)

    async def exercise():
        builder = ContainerBuilder()
        builder.register(Resource, factory=factory, lifespan="scoped")
        profiler = ResolutionProfiler()
        container = builder.build(instrumentation=Instrumentation(profiler))
        scope = container.new_scope()
        assert isinstance(await scope.resolve_async(Resource), Resource)
        await scope._close_async()
        return profiler.report()

    report = asyncio.run(exercise())
    assert closed == [True]
    assert any(record.kind == "cleanup" and record.completed == 1 for record in report.records)


def test_sync_close_of_async_resource_balances_failed_cleanup_record():
    class Resource:
        pass

    @asynccontextmanager
    async def factory():
        yield Resource()

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory, lifespan="scoped")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    scope = container.new_scope()
    asyncio.run(scope.resolve_async(Resource))
    with pytest.raises(RuntimeError, match="Async finalizer requires async context management"):
        scope._close()
    cleanup = [record for record in profiler.report().records if record.kind == "cleanup" and record.attempts]
    assert any((record.attempts, record.completed, record.failed, record.cancelled) == (1, 0, 1, 0)
               for record in cleanup)


def test_cancelled_async_activation_is_counted_and_can_retry():
    class Service:
        pass

    entered = asyncio.Event()
    gate = asyncio.Event()
    calls = 0

    async def factory() -> Service:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await gate.wait()
        return Service()

    async def exercise():
        builder = ContainerBuilder()
        builder.register(Service, factory=factory, lifespan="singleton")
        profiler = ResolutionProfiler()
        container = builder.build(instrumentation=Instrumentation(profiler))
        task = asyncio.create_task(container.resolve_async(Service))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert isinstance(await container.resolve_async(Service), Service)
        return profiler.report()

    report = asyncio.run(exercise())
    assert any(
        record.kind == "request" and record.cancelled == 1 and record.completed == 1 for record in report.records
    )
    assert any(
        record.kind == "registration" and record.cancelled == 1 and record.completed == 1 for record in report.records
    )


def test_failed_build_does_not_bind_profile():
    class Missing:
        pass

    class Service:
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Service)
    profiler = ResolutionProfiler()
    with pytest.raises(Exception):
        builder.build(instrumentation=Instrumentation(profiler))
    with pytest.raises(RuntimeError, match="not bound"):
        profiler.report()


def test_clock_failure_disables_timing_without_changing_resolution(monkeypatch):
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))

    def broken_clock():
        raise RuntimeError("clock failed")

    monkeypatch.setattr("clean_ioc.instrumentation.time.perf_counter_ns", broken_clock)
    assert isinstance(container.resolve(Service), Service)
    assert profiler.report().incomplete


@pytest.mark.parametrize("failing_method", ["_choose_timing", "_record"])
def test_injected_collector_failure_cannot_change_resolve_cache_or_cleanup(monkeypatch, failing_method):
    class Service:
        pass

    events = []

    @contextmanager
    def factory():
        try:
            yield Service()
        finally:
            events.append("closed")

    builder = ContainerBuilder()
    builder.register(Service, factory=factory, lifespan="singleton")
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))
    instance = container.resolve(Service)

    def broken(*_args):
        raise RuntimeError("collector failed")

    monkeypatch.setattr(profiler, failing_method, broken)
    assert container.resolve(Service) is instance
    container._close()
    assert events == ["closed"]
    assert profiler.report().incomplete


def test_injected_recorder_failure_does_not_replace_application_exception(monkeypatch):
    class Service:
        pass

    def factory() -> Service:
        raise ValueError("application exception")

    builder = ContainerBuilder()
    builder.register(Service, factory=factory)
    profiler = ResolutionProfiler()
    container = builder.build(instrumentation=Instrumentation(profiler))

    def broken(*_args):
        raise RuntimeError("collector failed")

    monkeypatch.setattr(profiler, "_record", broken)
    with pytest.raises(ValueError, match="application exception"):
        container.resolve(Service)
    assert profiler.report().incomplete
