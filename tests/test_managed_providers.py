"""Managed providers acquire precompiled targets under an explicit lifetime boundary."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from typing import Generic, TypeVar

import pytest
from typing_extensions import TypeAliasType

from clean_ioc import (
    AsyncManagedProvider,
    ComponentKind,
    ContainerBuilder,
    ContainerBuildError,
    Instrumentation,
    ManagedProvider,
    Provider,
    ProviderScopeClosedError,
    ResolutionProfiler,
    ScopeProvisionError,
    select,
)
from clean_ioc import component_filters as cf


class Resource:
    def __init__(self):
        self.closed = False


class Product:
    def __init__(self, left: Resource, right: Resource):
        self.left = left
        self.right = right


class Runner:
    def __init__(self, products: ManagedProvider[Product]):
        self.products = products


@pytest.fixture
def composition():
    created = []

    def resource() -> Iterator[Resource]:
        value = Resource()
        created.append(value)
        try:
            yield value
        finally:
            value.closed = True

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(Product, lifespan="scoped")
    builder.register(Runner, lifespan="singleton")
    return builder, created


def codes(error):
    return {issue.code for issue in error.report.errors}


def test_lazy_isolated_nested_acquisitions_and_single_use(composition, monkeypatch):
    builder, created = composition
    with builder.build() as container:
        warmed = container.resolve(Resource)
        with container.new_scope() as child:
            runner = child.resolve(Runner)
        manager = runner.products()
        assert created == [warmed]
        monkeypatch.setattr(ContainerBuilder, "build", lambda *a, **kw: pytest.fail("compiled during acquisition"))
        with manager as first:
            assert first.left is first.right and first.left is not warmed
            with runner.products() as second:
                assert second.left is not first.left
            assert second.left.closed and not first.left.closed
            with pytest.raises(RuntimeError, match="single-use"):
                manager.__enter__()
        assert first.left.closed and not warmed.closed
        manager.__exit__()  # Closing twice never finalizes twice.
        with pytest.raises(RuntimeError, match="single-use"):
            manager.__enter__()
        with runner.products() as third:
            assert third.left not in (warmed, first.left, second.left)
    assert all(value.closed for value in created)


def test_concurrent_sync_acquisitions_are_independent(composition):
    builder, created = composition
    with builder.build() as container:
        handle = container.resolve(ManagedProvider[Product])

        def acquire(_):
            with handle() as product:
                assert product.left is product.right
                return product.left

        with ThreadPoolExecutor(max_workers=4) as executor:
            values = list(executor.map(acquire, range(12)))
        assert len(set(values)) == 12
        assert all(value.closed for value in values)
    assert len(created) == 12


def test_owner_closed_before_entry_and_parent_closed_inside_block(composition):
    builder, created = composition
    container = builder.build()
    handle = container.resolve(ManagedProvider[Product])
    never_entered = handle()
    with handle() as product:
        container.__exit__()
        assert not product.left.closed
    assert product.left.closed
    with pytest.raises(ProviderScopeClosedError):
        never_entered.__enter__()
    with pytest.raises(ProviderScopeClosedError):
        handle().__enter__()
    assert len(created) == 1


def test_scoped_handle_binds_resolving_scope(composition):
    builder, _ = composition
    with builder.build() as container:
        with container.new_scope() as child:
            handle = child.resolve(ManagedProvider[Product])
        with pytest.raises(ProviderScopeClosedError):
            handle().__enter__()


def test_singleton_target_keeps_parent_ownership():
    created = []

    def resource() -> Iterator[Resource]:
        value = Resource()
        created.append(value)
        try:
            yield value
        finally:
            value.closed = True

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="singleton")
    with builder.build() as container:
        handle = container.resolve(ManagedProvider[Resource])
        with handle() as first, handle() as second:
            assert first is second
        assert not first.closed
    assert first.closed and len(created) == 1


def test_provisions_use_bound_owner_not_first_child_values():
    class Slot:
        pass

    class UsesSlot:
        def __init__(self, slot: Slot):
            self.slot = slot

    class Consumer:
        def __init__(self, target: ManagedProvider[UsesSlot]):
            self.target = target

    builder = ContainerBuilder()
    builder.declare_scope_slot(Slot)
    builder.register(UsesSlot, lifespan="scoped")
    builder.register(Consumer, lifespan="singleton")
    with builder.build() as container:
        root_value, child_value = Slot(), Slot()
        container.provide(Slot, root_value)
        with container.new_scope() as child:
            child.provide(Slot, child_value)
            consumer = child.resolve(Consumer)
            local = child.resolve(ManagedProvider[UsesSlot])
            with local() as value:
                assert value.slot is child_value
        with consumer.target() as value:
            assert value.slot is root_value


def test_missing_provision_and_activation_failure_clean_up(composition):
    builder, created = composition

    class Slot:
        pass

    class Fails:
        def __init__(self, resource: Resource, slot: Slot):
            pass

    builder.declare_scope_slot(Slot)
    builder.register(Fails)
    with builder.build() as container:
        handle = container.resolve(ManagedProvider[Fails])
        with pytest.raises(ScopeProvisionError):
            with handle():
                pass
        assert created[0].closed


def test_activation_and_body_exceptions_preserved_with_cleanup_group():
    class Left:
        pass

    class Right:
        pass

    def left() -> Iterator[Left]:
        yield Left()
        raise ValueError("left cleanup")

    def right() -> Iterator[Right]:
        yield Right()
        raise LookupError("right cleanup")

    class Target:
        def __init__(self, left: Left, right: Right):
            pass

    builder = ContainerBuilder()
    builder.register(Left, factory=left, lifespan="scoped")
    builder.register(Right, factory=right, lifespan="scoped")
    builder.register(Target)
    with builder.build() as container:
        with pytest.raises(ExceptionGroup) as caught:
            with container.resolve(ManagedProvider[Target])():
                raise RuntimeError("body")
        assert isinstance(caught.value.__context__, RuntimeError)
        assert [str(error) for error in caught.value.exceptions] == ["right cleanup", "left cleanup"]


@pytest.mark.parametrize("provider", [Provider, ManagedProvider])
def test_ordinary_provider_retention_restriction_is_preserved(provider, composition):
    builder, _ = composition

    class Consumer:
        def __init__(self, resource: provider[Resource]):
            self.resource = resource

    builder.register(Consumer, lifespan="singleton")
    if provider is Provider:
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert "provider-captive-scope" in codes(caught.value)
    else:
        with builder.build() as container:
            with container.resolve(Consumer).resource() as resource:
                assert not resource.closed


def test_target_internal_captive_dependency_still_fails():
    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Product, lifespan="singleton")
    builder.register(Runner, lifespan="singleton")
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "captive-dependency" in codes(caught.value)


@pytest.mark.parametrize("mode", ["constructor", "factory", "generator", "contextmanager"])
def test_sync_registration_shapes(mode):
    def ordinary() -> Resource:
        return Resource()

    def generator() -> Iterator[Resource]:
        value = Resource()
        try:
            yield value
        finally:
            value.closed = True

    builder = ContainerBuilder()
    if mode == "constructor":
        builder.register(Resource, lifespan="scoped")
    else:
        factory = {"factory": ordinary, "generator": generator, "contextmanager": contextmanager(generator)}[mode]
        builder.register(Resource, factory=factory, lifespan="scoped")
    with builder.build() as container:
        with container.resolve(ManagedProvider[Resource])() as resource:
            assert not resource.closed
        assert resource.closed == (mode in ("generator", "contextmanager"))


@pytest.mark.parametrize("kind", ["factory", "generator", "contextmanager"])
async def test_async_plans_rejected_for_sync_and_supported_for_async(kind):
    async def factory() -> Resource:
        return Resource()

    async def generator() -> AsyncIterator[Resource]:
        value = Resource()
        try:
            yield value
        finally:
            await asyncio.sleep(0)
            value.closed = True

    create = {"factory": factory, "generator": generator, "contextmanager": asynccontextmanager(generator)}[kind]
    builder = ContainerBuilder()
    builder.register(Resource, factory=create, lifespan="scoped")

    class Consumer:
        def __init__(self, resource: ManagedProvider[Resource]):
            pass

    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "managed-provider-requires-async" in codes(caught.value)
    assert "use AsyncManagedProvider[" in str(caught.value)
    builder = ContainerBuilder()
    builder.register(Resource, factory=create, lifespan="scoped")
    async with builder.build() as container:
        handle = container.resolve(AsyncManagedProvider[Resource])
        async with handle() as resource:
            assert not resource.closed
        assert resource.closed == (kind != "factory")


async def test_async_handle_acquires_sync_plan_and_is_single_use(composition):
    builder, _ = composition
    async with builder.build() as container:
        manager = container.resolve(AsyncManagedProvider[Product])()
        async with manager as product:
            assert product.left is product.right
        assert product.left.closed
        with pytest.raises(RuntimeError, match="single-use"):
            await manager.__aenter__()


async def test_async_concurrency_and_cancellation():
    created = []

    async def resource() -> AsyncIterator[Resource]:
        value = Resource()
        created.append(value)
        try:
            yield value
        finally:
            await asyncio.sleep(0)
            value.closed = True

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    ready = asyncio.Event()
    release = asyncio.Event()
    async with builder.build() as container:
        handle = container.resolve(AsyncManagedProvider[Resource])

        async def run():
            async with handle() as value:
                ready.set()
                await release.wait()
                return value

        task = asyncio.create_task(run())
        await ready.wait()
        async with handle() as other:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert created[0].closed and not other.closed
        assert other.closed and len(created) == 2


@pytest.mark.parametrize("shape", [list, set, tuple])
def test_selected_collections_and_aliases(shape):
    resource_alias = TypeAliasType("resource_alias", Resource)
    target = tuple[resource_alias, ...] if shape is tuple else shape[resource_alias]

    class Consumer:
        def __init__(self, values: ManagedProvider[target]):
            self.values = values

    builder = ContainerBuilder()
    builder.register(Resource, name="one")
    builder.register(Resource, name="two")
    builder.register(Consumer, arguments={"values": select(cf.with_name("one"))})
    with builder.build() as container:
        with container.resolve(Consumer).values() as values:
            assert isinstance(values, shape) and len(values) == 1
        with container.resolve(ManagedProvider[target])() as values:
            assert not values
        with container.resolve(ManagedProvider[Resource], filter=cf.with_name("two"))() as value:
            assert isinstance(value, Resource)


@pytest.mark.parametrize("pattern", [False, True])
def test_closed_generic_pattern_and_decorator(pattern):
    T = TypeVar("T")

    class Service(Generic[T]):
        pass

    class Wrapped(Generic[T]):
        def __init__(self, inner: Service[T]):
            self.inner = inner

    class Consumer:
        def __init__(self, value: ManagedProvider[Service[int]]):
            self.value = value

    builder = ContainerBuilder()
    if pattern:
        builder.register_pattern(Service[T], factory=Service)
    else:
        builder.register(Service)
    builder.register_decorator(Service[T], Wrapped[T])
    builder.register(Consumer)
    with builder.build() as container:
        with container.resolve(Consumer).value() as value:
            assert isinstance(value, Wrapped)
            assert isinstance(value.inner, Service)


def test_managed_marked_entrypoint_and_deferred_graph(composition):
    builder, _ = composition
    builder.mark_entrypoint(ManagedProvider[Product])
    with builder.build() as container:
        root = container.graph.entrypoints[0].component
        assert root.kind is ComponentKind.managed_provider
        manifest = container.graph.manifest().to_json()
        assert '"scope_policy": "per_call"' in manifest
        analysis = container.graph.activation_report(ManagedProvider[Product])
        assert not any(item.service.endswith("Resource") for item in analysis.immediate_obligations)
        assert any(item.service.endswith("Resource") for item in analysis.deferred_obligations)
        assert manifest == container.graph.manifest().to_json()


def test_profile_counts_acquisition_cleanup_and_excludes_body_time(composition, monkeypatch):
    builder, _ = composition
    now = [0.0]
    monkeypatch.setattr("clean_ioc.instrumentation.time.perf_counter_ns", lambda: int(now[0]))
    profiler = ResolutionProfiler()
    with builder.build(instrumentation=Instrumentation(profiler)) as container:
        handle = container.resolve(ManagedProvider[Product])
        handle()
        with handle() as value:
            now[0] += 10_000
            assert value.left is value.right
        report = profiler.report()
        requests = [
            record for record in report.records if record.path.startswith("managed acquisition ") and record.attempts
        ]
        assert len(requests) == 1 and requests[0].attempts == requests[0].completed == 1
        assert all(summary.sampled_total_ns == 0 for _, summary in requests[0].durations)
        assert any(record.kind == "cleanup" and record.completed for record in report.records)


def test_overlay_singleton_handles_keep_their_declaring_composition(composition):
    builder, created = composition

    class OverlayRunner:
        def __init__(self, products: ManagedProvider[Product]):
            self.products = products

    class OverlayResource(Resource):
        pass

    def overlay_resource() -> Iterator[Resource]:
        resource = OverlayResource()
        try:
            yield resource
        finally:
            resource.closed = True

    with builder.build() as container:
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Resource, factory=overlay_resource, lifespan="scoped")
        overlay_builder.register(OverlayRunner, lifespan="singleton")
        with overlay_builder.build() as overlay:
            inherited = overlay.resolve(Runner)
            own = overlay.resolve(OverlayRunner)
            with inherited.products() as root_product:
                assert type(root_product.left) is Resource
            with own.products() as overlay_product:
                assert isinstance(overlay_product.left, OverlayResource)
        with inherited.products() as value:
            assert type(value.left) is Resource
        with pytest.raises(ProviderScopeClosedError):
            own.products().__enter__()
    assert all(value.closed for value in created)


def test_selection_fallback_and_preconfiguration_are_frozen():
    calls = []
    configured = []

    def chosen(component):
        calls.append(component.name)
        return component.name == "fallback"

    class Consumer:
        def __init__(self, resource: ManagedProvider[Resource]):
            self.resource = resource

    def configure() -> None:
        configured.append(True)

    builder = ContainerBuilder()
    builder.register(Resource, name="ordinary")
    builder.register_fallback(Resource, name="fallback", lifespan="scoped")
    builder.pre_configure(Resource, configure)
    builder.register(Consumer, arguments={"resource": select(chosen)})
    with builder.build() as container:
        after_build = list(calls)
        consumer = container.resolve(Consumer)
        assert not configured
        with consumer.resource() as first:
            assert isinstance(first, Resource)
        with consumer.resource() as second:
            assert second is not first
        assert calls == after_build and configured == [True]


def test_boundary_exposure_and_private_target_diagnostics():
    from clean_ioc import Expose

    class Consumer:
        def __init__(self, resource: ManagedProvider[Resource]):
            self.resource = resource

    builder = ContainerBuilder()
    boundary = builder.create_boundary("resources", exposes=(Expose(Resource),))
    boundary.register(Resource, lifespan="scoped")
    builder.register(Consumer)
    with builder.build() as container:
        with container.resolve(Consumer).resource() as resource:
            assert isinstance(resource, Resource)
    builder = ContainerBuilder()
    builder.create_boundary("resources").register(Resource)
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "boundary-private-component" in codes(caught.value)


def test_real_target_cycle_is_rejected():
    class Cyclic:
        def __init__(self, dependency):
            pass

    Cyclic.__init__.__annotations__["dependency"] = Cyclic

    class Consumer:
        def __init__(self, target: ManagedProvider[Cyclic]):
            pass

    builder = ContainerBuilder()
    builder.register(Cyclic)
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "circular-dependency" in codes(caught.value)


def test_scoped_target_sharing_groups_are_separate_from_ordinary_scope(composition):
    builder, _ = composition
    builder.mark_entrypoint(Runner)
    builder.mark_entrypoint(Product)
    with builder.build() as container:
        report = container.graph.sharing_report()
        scoped = [group for group in report.groups if group.service.endswith("Resource")]
        assert any("managed acquisition" in " ".join(group.conditions) for group in scoped)
        assert any("inherited scoped values" in " ".join(group.conditions) for group in scoped)
        assert all(
            not (
                any("Runner" in path for path in group.occurrence_paths)
                and any(path.startswith("root:") and "Product" in path for path in group.occurrence_paths)
            )
            for group in scoped
        )


def test_direct_policy_sarif_and_semantic_diff_traverse_managed_boundary(composition):
    from clean_ioc.policies import forbid_dependency

    builder, _ = composition
    builder.add_validation_rule(forbid_dependency(cf.service_type_is(Runner), cf.service_type_is(Product)))
    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "policy-forbidden-dependency" in codes(caught.value)
    assert caught.value.report is not None
    sarif = caught.value.report.to_sarif()
    assert "Product" in sarif and "Runner" in sarif

    class Consumer:
        def __init__(self, target):
            self.target = target

    def build(provider):
        Consumer.__init__.__annotations__["target"] = provider[Resource]
        result = ContainerBuilder()
        result.register(Resource, lifespan="scoped")
        result.register(Consumer)
        result.mark_entrypoint(Consumer)
        return result

    with build(Provider).build() as ordinary, build(ManagedProvider).build() as managed:
        diff = managed.graph.manifest().diff(ordinary.graph.manifest())
        assert not diff.is_empty
        assert any("activation" in str(change.kind) for change in diff.semantic_changes)


def test_matrix_and_public_reports_do_not_activate_or_expose_values():
    from clean_ioc.matrix import BuildMatrix, BuildVariant

    def definition():
        builder = ContainerBuilder()
        builder.register(Resource, factory=lambda: pytest.fail("tooling activated a resource"))
        builder.register(Product)
        builder.register(Runner, lifespan="singleton")
        builder.mark_entrypoint(Runner)
        return builder

    report = BuildMatrix((BuildVariant("one", definition), BuildVariant("two", definition)), reference="one").check()
    assert report.is_valid
    assert report.to_json() == report.to_json()
    assert "managed_provider" in report.to_json()
    with definition().build(build_args={"secret-input-name": "secret-input-value"}) as container:
        public = container.graph.manifest().to_json() + container.graph.ownership_report().to_json()
        public += container.graph.sharing_report().to_json() + container.graph.activation_report(Runner).to_json()
        assert "secret-input" not in public
        assert public == (
            container.graph.manifest().to_json()
            + container.graph.ownership_report().to_json()
            + container.graph.sharing_report().to_json()
            + container.graph.activation_report(Runner).to_json()
        )


async def test_async_manager_rejects_sync_protocol(composition):
    builder, _ = composition
    async with builder.build() as container:
        manager = container.resolve(AsyncManagedProvider[Product])()
        with pytest.raises(TypeError, match="async with"):
            with manager:
                pass
        async with manager as product:
            assert product.left is product.right


def test_managed_root_explanations_and_census_match_provider_semantics(composition):
    builder, _ = composition
    builder.mark_entrypoint(Runner)
    with builder.build(diagnostics=True) as container:
        assert container.graph.explain(ManagedProvider[Resource]).selected
        arguments = container.graph.explain_arguments(container.graph.entrypoints[0].component)
        assert arguments[0].result_category == "managed_provider"
        census = container.graph.selection_census()
        resource = next(item for item in census.definitions if item.definition.implementation.endswith(".Product"))
        assert resource.deferred_target_uses > 0
        assert resource.dependency_requests == 0
    builder = ContainerBuilder()
    builder.register(Resource)
    builder.mark_entrypoint(ManagedProvider[Resource])
    with builder.build(diagnostics=True) as container:
        resource = next(
            item
            for item in container.graph.selection_census().definitions
            if item.definition.implementation.endswith(".Resource")
        )
        assert resource.root_requests == 1


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("nested", [False, True])
async def test_failed_async_collection_closes_entered_members_before_propagating_error(observed, nested):
    started = asyncio.Event()
    release = asyncio.Event()
    events = []

    @asynccontextmanager
    async def slow() -> AsyncIterator[Resource]:
        events.append("slow starting")
        started.set()
        try:
            await asyncio.sleep(0)
            yield Resource()
        finally:
            events.append("slow closed")

    async def fail() -> Resource:
        await started.wait()
        raise ValueError("activation failed")

    class Target:
        def __init__(self, resources: list[Resource]):
            self.resources = resources

    builder = ContainerBuilder()
    builder.register(Resource, factory=fail, lifespan="scoped")
    builder.register(Resource, factory=slow, lifespan="scoped")
    if nested:
        builder.register(Target)
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        handle = (
            container.resolve(AsyncManagedProvider[Target])
            if nested
            else container.resolve(AsyncManagedProvider[list[Resource]])
        )
        with pytest.raises(ValueError, match="activation failed"):
            async with handle():
                pytest.fail("failed acquisition entered body")
        assert events == ["slow starting", "slow closed"]
        release.set()
        await asyncio.sleep(0)
        assert events == ["slow starting", "slow closed"]


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("nested", [False, True])
async def test_failed_resolution_context_root_lookup_cleans_managed_variants(observed, nested):
    from clean_ioc import ResolutionContext

    started = asyncio.Event()
    events = []

    @asynccontextmanager
    async def slow() -> AsyncIterator[Resource]:
        started.set()
        try:
            await asyncio.sleep(0)
            yield Resource()
        finally:
            await asyncio.sleep(0)
            events.append("closed")

    async def fail() -> Resource:
        await started.wait()
        raise ValueError("lookup failure")

    class Target:
        def __init__(self, resources: list[Resource]):
            pass

    async def factory(context: ResolutionContext) -> object:
        return await context.resolve_async(Target if nested else list[Resource])

    builder = ContainerBuilder()
    builder.register(Resource, factory=fail, lifespan="scoped")
    builder.register(Resource, factory=slow, lifespan="scoped")
    builder.register(Target)
    builder.register(object, factory=factory)
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        with pytest.raises(ValueError, match="lookup failure"):
            async with container.resolve(AsyncManagedProvider[object])():
                pass
        assert events == ["closed"]


@pytest.mark.parametrize("observed", [False, True])
async def test_entry_cancellation_does_not_cancel_resource_finalization_twice(observed):
    ready = [asyncio.Event(), asyncio.Event()]
    events = []

    def create(index):
        @asynccontextmanager
        async def resource() -> AsyncIterator[Resource]:
            ready[index].set()
            try:
                if index:
                    await asyncio.Event().wait()
                yield Resource()
            finally:
                events.append(("closing", index))
                await asyncio.sleep(0.01 if index else 0)
                events.append(("closed", index))

        return resource

    builder = ContainerBuilder()
    builder.register(Resource, factory=create(1), lifespan="scoped")
    builder.register(Resource, factory=create(0), lifespan="scoped")
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        manager = container.resolve(AsyncManagedProvider[list[Resource]])()
        task = asyncio.create_task(manager.__aenter__())
        await asyncio.gather(*(item.wait() for item in ready))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sorted(events) == [("closed", 0), ("closed", 1), ("closing", 0), ("closing", 1)]


@pytest.mark.parametrize("observed", [False, True])
async def test_failed_entry_cleanup_failure_retains_initial_activation_failure(observed):
    started = asyncio.Event()

    @asynccontextmanager
    async def slow() -> AsyncIterator[Resource]:
        started.set()
        try:
            await asyncio.sleep(0)
            yield Resource()
        finally:
            raise RuntimeError("cleanup failed")

    async def fail() -> Resource:
        await started.wait()
        raise ValueError("activation failed")

    builder = ContainerBuilder()
    builder.register(Resource, factory=fail, lifespan="scoped")
    builder.register(Resource, factory=slow, lifespan="scoped")
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        with pytest.raises(RuntimeError, match="cleanup failed") as caught:
            async with container.resolve(AsyncManagedProvider[list[Resource]])():
                pass
        assert isinstance(caught.value.__context__, ValueError)
        assert str(caught.value.__context__) == "activation failed"


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("lookup_async", [False, True])
async def test_ordinary_provider_from_managed_context_uses_safe_frozen_targets(observed, lookup_async):
    from clean_ioc import AsyncProvider, ResolutionContext

    started = asyncio.Event()
    events = []

    @asynccontextmanager
    async def slow() -> AsyncIterator[Resource]:
        started.set()
        try:
            await asyncio.sleep(0)
            yield Resource()
        finally:
            events.append("closed")

    async def fail() -> Resource:
        await started.wait()
        raise ValueError("provider failure")

    async def factory(context: ResolutionContext) -> object:
        provider = (
            await context.resolve_async(AsyncProvider[list[Resource]])
            if lookup_async
            else context.resolve(AsyncProvider[list[Resource]])
        )
        return await provider()

    builder = ContainerBuilder()
    builder.register(Resource, factory=fail, lifespan="scoped")
    builder.register(Resource, factory=slow, lifespan="scoped")
    builder.register(object, factory=factory)
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        with pytest.raises(ValueError, match="provider failure"):
            async with container.resolve(AsyncManagedProvider[object])():
                pass
        assert events == ["closed"]


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
async def test_collection_shared_dependency_edges_preserve_lifespans_without_false_cycles(observed, lifespan):
    created = []

    class Dependency:
        pass

    async def dependency() -> Dependency:
        await asyncio.sleep(0)
        value = Dependency()
        created.append(value)
        return value

    class Left(Resource):
        def __init__(self, value: Dependency):
            self.value = value

    class Right(Resource):
        def __init__(self, value: Dependency):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Dependency, factory=dependency, lifespan=lifespan)
    builder.register(Resource, Left, lifespan="transient")
    builder.register(Resource, Right, lifespan="transient")
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        handle = container.resolve(AsyncManagedProvider[list[Resource]])
        async with handle() as first:
            assert isinstance(first[0], (Left, Right)) and isinstance(first[1], (Left, Right))
            assert (first[0].value is first[1].value) == (lifespan != "transient")
        async with handle() as second:
            assert isinstance(second[0], (Left, Right)) and isinstance(first[0], (Left, Right))
            assert (second[0].value is first[0].value) == (lifespan == "singleton")
        assert len(created) == (4 if lifespan == "transient" else 1 if lifespan == "singleton" else 2)


def test_managed_registration_and_decorator_template_callbacks_do_not_replay():
    from clean_ioc import DecoratorTemplate, RegistrationTemplate, ServiceGroup

    class Source:
        pass

    class Wrapped(Resource):
        def __init__(self, inner: Resource):
            self.inner = inner

    calls = []
    group = ServiceGroup("managed-resources", service_type=Resource)

    def registration(source):
        calls.append("registration")
        return RegistrationTemplate(Resource, lifespan="scoped", groups=[group])

    def decorator(source):
        calls.append("decorator")
        return DecoratorTemplate(group, Wrapped)

    builder = ContainerBuilder()
    builder.register(Source)
    builder.register_registration_template(for_each=Source, template=registration)
    builder.register_decorator_template(for_each=Source, template=decorator)
    builder.register(Runner)
    # Runner's Product graph also provides a constructor composition check.
    builder.register(Product, lifespan="scoped")
    with builder.build() as container:
        built_calls = list(calls)
        assert "registration" in calls and "decorator" in calls
        with container.resolve(ManagedProvider[Resource])() as first:
            assert isinstance(first, Wrapped)
        with container.resolve(ManagedProvider[Resource])() as second:
            assert isinstance(second, Wrapped) and second.inner is not first.inner
        assert calls == built_calls


def test_nested_isolated_boundaries_use_nearest_scope_for_sharing_and_ownership():
    from typing import Protocol

    class Operation(Protocol):
        def run(self) -> None: ...

    class Implementation:
        def __init__(self, resource: Resource):
            self.resource = resource

        def run(self) -> None:
            pass

    class Target:
        def __init__(self, left: Operation, right: Operation):
            pass

    builder = ContainerBuilder()
    builder.register(Resource, lifespan="scoped")
    builder.register(Operation, Implementation, scope="per_call")
    builder.register(Target)
    builder.mark_entrypoint(ManagedProvider[Target])
    with builder.build() as container:
        groups = [group for group in container.graph.sharing_report().groups if group.service.endswith(".Resource")]
        groups = [group for group in groups if any("ManagedProvider[" in path for path in group.occurrence_paths)]
        assert len(groups) == 2
        assert all("method invocation" in " ".join(group.conditions) for group in groups)
        records = [
            record for record in container.graph.ownership_report().records if record.component.service_type is Resource
        ]
        assert all("managed acquisition" not in record.reason for record in records)


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("lookup_async", [False, True])
async def test_resolution_context_collection_of_provider_handles_preserves_public_shape(observed, lookup_async):
    from clean_ioc import AsyncProvider, ResolutionContext

    async def target(context: ResolutionContext) -> object:
        handles = (
            await context.resolve_async(list[AsyncProvider[Resource]], filter=cf.with_name("one"))
            if lookup_async
            else context.resolve(list[AsyncProvider[Resource]], filter=cf.with_name("one"))
        )
        assert len(handles) == 1
        return await handles[0]()

    builder = ContainerBuilder()
    builder.register(Resource, name="one", lifespan="scoped")
    builder.register(object, factory=target)
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        async with container.resolve(AsyncManagedProvider[object])() as value:
            assert isinstance(value, Resource)


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("request_kind", ["injected", "marked"])
def test_sync_managed_plan_rejects_scoped_async_cleanup_behind_ordinary_provider(observed, request_kind):
    from clean_ioc import AsyncProvider

    async def resource() -> AsyncIterator[Resource]:
        yield Resource()

    class Target:
        def __init__(self, resource: AsyncProvider[Resource]):
            self.resource = resource

    class Consumer:
        def __init__(self, target: ManagedProvider[Target]):
            pass

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(Target)
    if request_kind == "injected":
        builder.register(Consumer)
    else:
        builder.mark_entrypoint(ManagedProvider[Target])
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    with pytest.raises(ContainerBuildError) as caught:
        builder.build(instrumentation=instrumentation)
    assert "managed-provider-requires-async" in codes(caught.value)


@pytest.mark.parametrize("observed", [False, True])
async def test_unmarked_sync_managed_root_rejects_known_deferred_async_cleanup_before_activation(observed):
    from clean_ioc import AsyncProvider

    activated = []

    async def resource() -> AsyncIterator[Resource]:
        activated.append("resource")
        yield Resource()

    class Target:
        def __init__(self, resource: AsyncProvider[Resource]):
            activated.append("target")

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(Target)
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        with pytest.raises(RuntimeError, match="AsyncManagedProvider"):
            with container.resolve(ManagedProvider[Target])():
                pass
        assert not activated


@pytest.mark.parametrize("observed", [False, True])
@pytest.mark.parametrize("scenario", ["resource-free", "singleton", "nested-managed"])
async def test_sync_managed_cleanup_proof_preserves_independent_and_parent_owners(observed, scenario):
    from clean_ioc import AsyncProvider

    created = []

    async def ordinary() -> Resource:
        value = Resource()
        created.append(value)
        return value

    async def resource() -> AsyncIterator[Resource]:
        value = Resource()
        created.append(value)
        try:
            yield value
        finally:
            await asyncio.sleep(0)
            value.closed = True

    annotation = AsyncManagedProvider[Resource] if scenario == "nested-managed" else AsyncProvider[Resource]

    class Target:
        def __init__(self, resources: annotation):
            self.resources = resources

    builder = ContainerBuilder()
    builder.register(
        Resource,
        factory=ordinary if scenario == "resource-free" else resource,
        lifespan="singleton" if scenario == "singleton" else "scoped",
    )
    builder.register(Target)
    builder.mark_entrypoint(ManagedProvider[Target])
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        with container.resolve(ManagedProvider[Target])() as target:
            if scenario == "nested-managed":
                from typing import cast

                nested = cast(AsyncManagedProvider[Resource], target.resources)
                async with nested() as value:
                    assert not value.closed
                assert value.closed
            else:
                from typing import cast

                ordinary_handle = cast(AsyncProvider[Resource], target.resources)
                value = await ordinary_handle()
                assert not value.closed
        assert value.closed == (scenario == "nested-managed")
    assert value.closed == (scenario != "resource-free")


@pytest.mark.parametrize("observed", [False, True])
async def test_sync_managed_cleanup_proof_stops_at_independent_per_call_boundary(observed):
    from typing import Protocol

    created = []

    async def resource() -> AsyncIterator[Resource]:
        value = Resource()
        created.append(value)
        try:
            yield value
        finally:
            value.closed = True

    class Operation(Protocol):
        async def run(self) -> None: ...

    class Implementation:
        def __init__(self, resource: Resource):
            self.resource = resource

        async def run(self) -> None:
            assert not self.resource.closed

    class Target:
        def __init__(self, operation: Operation):
            self.operation = operation

    builder = ContainerBuilder()
    builder.register(Resource, factory=resource, lifespan="scoped")
    builder.register(Operation, Implementation, scope="per_call")
    builder.register(Target)
    builder.mark_entrypoint(ManagedProvider[Target])
    instrumentation = Instrumentation(ResolutionProfiler()) if observed else None
    async with builder.build(instrumentation=instrumentation) as container:
        with container.resolve(ManagedProvider[Target])() as target:
            await target.operation.run()
            assert created[0].closed
