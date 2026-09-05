import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, TypeVar

import pytest

import clean_ioc.component_filters as cf
from clean_ioc import (
    AsyncProvider,
    ComponentActivation,
    ComponentKind,
    ContainerBuilder,
    ContainerBuildError,
    Provider,
    ProviderScopeClosedError,
    build_arg,
    select,
)


def issue_codes(error: ContainerBuildError) -> set[str]:
    assert error.report is not None
    return {issue.code for issue in error.report.errors}


def test_provider_is_injected_and_root_resolved_from_frozen_transient_plan():
    class Service:
        created = 0

        def __init__(self):
            Service.created += 1
            self.number = Service.created

    class Consumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    builder = ContainerBuilder()
    builder.register(Service, lifespan="transient")
    builder.register(Consumer)
    container = builder.build()

    consumer = container.resolve(Consumer)
    assert [consumer.service().number, consumer.service().number] == [1, 2]
    assert container.resolve(Provider[Service])().number == 3


@pytest.mark.asyncio
async def test_async_provider_accepts_sync_and_async_targets():
    class SyncService:
        pass

    class AsyncService:
        pass

    async def create_async() -> AsyncService:
        await asyncio.sleep(0)
        return AsyncService()

    class Consumer:
        def __init__(
            self,
            sync_service: AsyncProvider[SyncService],
            async_service: AsyncProvider[AsyncService],
        ):
            self.sync_service = sync_service
            self.async_service = async_service

    builder = ContainerBuilder()
    builder.register(SyncService)
    builder.register(AsyncService, factory=create_async)
    builder.register(Consumer)
    container = builder.build()
    consumer = container.resolve(Consumer)

    assert isinstance(await consumer.sync_service(), SyncService)
    assert isinstance(await consumer.async_service(), AsyncService)
    root_provider = await container.resolve_async(AsyncProvider[AsyncService])
    assert isinstance(await root_provider(), AsyncService)


def test_sync_provider_rejects_an_async_target_at_build_time():
    class Service:
        pass

    async def create_service() -> Service:
        return Service()

    class Consumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    builder = ContainerBuilder()
    builder.register(Service, factory=create_service)
    builder.register(Consumer)

    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "provider-requires-async" in issue_codes(caught.value)


def test_provider_collection_and_named_selection_are_frozen_during_build():
    class Service:
        def __init__(self, value: str):
            self.value = value

    class Consumer:
        def __init__(self, primary: Provider[Service], services: Provider[list[Service]]):
            self.primary = primary
            self.services = services

    calls = 0

    def primary(component):
        nonlocal calls
        calls += 1
        return component.name == "primary"

    builder = ContainerBuilder()
    builder.register(Service, instance=Service("default"))
    builder.register(Service, instance=Service("primary"), name="primary")
    builder.register(
        Consumer,
        arguments={"primary": select(primary)},
    )
    container = builder.build()
    calls_after_build = calls
    consumer = container.resolve(Consumer)

    assert consumer.primary().value == "primary"
    assert [service.value for service in consumer.services()] == ["default"]
    assert [service.value for service in container.resolve(Provider[list[Service]])()] == ["default"]
    assert calls == calls_after_build


def test_provider_preserves_once_scoped_and_singleton_caching_per_call_and_scope():
    class Once:
        pass

    class Scoped:
        pass

    class Singleton:
        pass

    class Pair:
        def __init__(self, left: Once, right: Once):
            self.left = left
            self.right = right

    class Consumer:
        def __init__(
            self,
            pair: Provider[Pair],
            scoped: Provider[Scoped],
            singleton: Provider[Singleton],
        ):
            self.pair = pair
            self.scoped = scoped
            self.singleton = singleton

    builder = ContainerBuilder()
    builder.register(Once, lifespan="once_per_graph")
    builder.register(Pair, lifespan="transient")
    builder.register(Scoped, lifespan="scoped")
    builder.register(Singleton, lifespan="singleton")
    builder.register(Consumer, lifespan="transient")
    container = builder.build()
    scope = container.new_scope()
    consumer = scope.resolve(Consumer)

    first_pair, second_pair = consumer.pair(), consumer.pair()
    assert first_pair.left is first_pair.right
    assert first_pair.left is not second_pair.left
    assert consumer.scoped() is consumer.scoped()
    assert consumer.singleton() is container.resolve(Singleton)


def test_provider_rejects_invalid_target_policy_missing_and_ambiguity():
    class Service:
        pass

    class InvalidPolicy:
        def __init__(self, service: Provider[Service]):
            self.service = service

    policy_builder = ContainerBuilder()
    policy_builder.register(Service)
    policy_builder.register(InvalidPolicy, arguments={"service": build_arg("service")})
    with pytest.raises(ContainerBuildError) as policy_error:
        policy_builder.build(build_args={"service": object()})
    assert "provider-invalid-argument-policy" in issue_codes(policy_error.value)

    class Missing:
        def __init__(self, service: Provider[Service]):
            self.service = service

    missing_builder = ContainerBuilder()
    missing_builder.register(Missing)
    with pytest.raises(ContainerBuildError) as missing_error:
        missing_builder.build()
    assert "provider-missing-component" in issue_codes(missing_error.value)

    ambiguous_builder = ContainerBuilder()
    ambiguous_builder.register(Service)
    ambiguous_builder.register(Service)
    ambiguous_builder.register(InvalidPolicy)
    with pytest.raises(ContainerBuildError) as ambiguous_error:
        ambiguous_builder.build()
    assert "provider-ambiguous-component" in issue_codes(ambiguous_error.value)


def test_bare_nested_open_and_unsupported_collection_provider_targets_are_invalid():
    T = TypeVar("T")

    class GenericService(Generic[T]):
        pass

    invalid_annotations = (
        Provider,
        Provider[Provider[int]],
        Provider[GenericService],
        Provider[tuple[int, str]],
    )
    for annotation in invalid_annotations:

        def create(value):
            return value

        create.__annotations__ = {"value": annotation, "return": object}
        builder = ContainerBuilder()
        builder.register(object, factory=create)
        with pytest.raises(ContainerBuildError) as caught:
            builder.build()
        assert "provider-invalid-target" in issue_codes(caught.value)


def test_singleton_provider_rejects_scope_state_but_binds_safe_provider_to_singleton_owner():
    class Scoped:
        pass

    class UnsafeConsumer:
        def __init__(self, service: Provider[Scoped]):
            self.service = service

    unsafe = ContainerBuilder()
    unsafe.register(Scoped, lifespan="scoped")
    unsafe.register(UnsafeConsumer, lifespan="singleton")
    with pytest.raises(ContainerBuildError) as caught:
        unsafe.build()
    assert "provider-captive-scope" in issue_codes(caught.value)

    class Transient:
        pass

    class SafeConsumer:
        def __init__(self, service: Provider[Transient]):
            self.service = service

    safe = ContainerBuilder()
    safe.register(Transient, lifespan="transient")
    safe.register(SafeConsumer, lifespan="singleton")
    container = safe.build()
    child = container.new_scope()
    provider = child.resolve(SafeConsumer).service
    child.__exit__(None, None, None)
    assert isinstance(provider(), Transient)
    container.__exit__(None, None, None)
    with pytest.raises(ProviderScopeClosedError):
        provider()


def test_singleton_provider_rejects_transient_target_that_reaches_scope_slot():
    class Target:
        def __init__(self, request_id: int):
            self.request_id = request_id

    class Consumer:
        def __init__(self, target: Provider[Target]):
            self.target = target

    builder = ContainerBuilder()
    builder.declare_scope_slot(int)
    builder.register(Target, lifespan="transient")
    builder.register(Consumer, lifespan="singleton")

    with pytest.raises(ContainerBuildError) as caught:
        builder.build()
    assert "provider-captive-scope" in issue_codes(caught.value)


def test_overlay_singleton_provider_uses_overlay_plan_and_inherited_singleton_keeps_parent_plan():
    class Service:
        def __init__(self, source: str):
            self.source = source

    class ParentConsumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    class OverlayConsumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    parent_service = Service("parent")
    overlay_service = Service("overlay")
    builder = ContainerBuilder()
    builder.register(Service, factory=lambda: parent_service, lifespan="transient")
    builder.register(ParentConsumer, lifespan="singleton")
    container = builder.build()

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(
        Service,
        factory=lambda: overlay_service,
        lifespan="transient",
        name="overlay",
    )
    overlay_builder.register(
        OverlayConsumer,
        lifespan="singleton",
        arguments={"service": select(cf.with_name("overlay"))},
    )
    overlay = overlay_builder.build()

    assert overlay.resolve(ParentConsumer).service().source == "parent"
    assert overlay.resolve(OverlayConsumer).service().source == "overlay"
    overlay.__exit__(None, None, None)
    assert container.resolve(ParentConsumer).service().source == "parent"


def test_non_singleton_provider_fails_after_bound_scope_closes():
    class Service:
        pass

    class Consumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register(Consumer, lifespan="transient")
    container = builder.build()
    scope = container.new_scope()
    provider = scope.resolve(Consumer).service
    scope.__exit__(None, None, None)

    with pytest.raises(ProviderScopeClosedError):
        provider()


def test_provider_cleanup_is_owned_by_bound_scope_and_runs_in_reverse_acquisition_order():
    events: list[str] = []

    class Resource:
        def __init__(self, number: int):
            self.number = number

    def create_resource():
        number = len(events) + 1
        events.append(f"open:{number}")
        try:
            yield Resource(number)
        finally:
            events.append(f"close:{number}")

    builder = ContainerBuilder()
    builder.register(Resource, factory=create_resource, lifespan="transient")
    container = builder.build()
    scope = container.new_scope()
    provider = scope.resolve(Provider[Resource])

    assert [provider().number, provider().number] == [1, 2]
    scope.__exit__(None, None, None)
    assert events == ["open:1", "open:2", "close:2", "close:1"]


def test_provider_target_pre_configuration_remains_lazy():
    events: list[str] = []

    class Service:
        pass

    class Consumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    def configure() -> None:
        events.append("configured")

    builder = ContainerBuilder()
    builder.pre_configure(Service, configure)
    builder.register(Service, lifespan="transient")
    builder.register(Consumer)
    container = builder.build()

    provider = container.resolve(Consumer).service
    assert events == []
    provider()
    provider()
    assert events == ["configured"]


def test_concurrent_provider_calls_share_scoped_coordinator_without_sharing_resolution_state():
    lock = threading.Lock()
    activations = 0

    class Service:
        pass

    def create_service() -> Service:
        nonlocal activations
        with lock:
            activations += 1
        time.sleep(0.02)
        return Service()

    builder = ContainerBuilder()
    builder.register(Service, factory=create_service, lifespan="scoped")
    container = builder.build()
    scope = container.new_scope()
    provider = scope.resolve(Provider[Service])

    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(executor.map(lambda _: provider(), range(16)))
    assert all(value is values[0] for value in values)
    assert activations == 1


@pytest.mark.asyncio
async def test_concurrent_async_provider_calls_share_scoped_coordinator_and_retry_failure():
    attempts = 0

    class Service:
        pass

    async def create_service() -> Service:
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.01)
        if attempts == 1:
            raise RuntimeError("try again")
        return Service()

    builder = ContainerBuilder()
    builder.register(Service, factory=create_service, lifespan="scoped")
    container = builder.build()
    provider = container.resolve(AsyncProvider[Service])

    first = await asyncio.gather(provider(), provider(), return_exceptions=True)
    assert all(isinstance(value, RuntimeError) for value in first)
    assert attempts == 1
    values = await asyncio.gather(provider(), provider())
    assert values[0] is values[1]
    assert attempts == 2


def test_provider_graph_metadata_explanations_manifest_and_diff_show_deferred_target():
    class Service:
        pass

    class OtherService(Service):
        pass

    class Consumer:
        def __init__(self, service: Provider[Service]):
            self.service = service

    def build(implementation=Service):
        builder = ContainerBuilder()
        builder.register(Service, implementation)
        builder.register(Consumer)
        builder.mark_entrypoint(Consumer)
        return builder.build()

    original = build()
    provider = original.graph.entrypoints[0].component.dependencies[0]
    assert provider.kind is ComponentKind.provider
    assert provider.activation is ComponentActivation.deferred
    assert provider.provider_mode == "sync"
    assert provider.dependencies[0].service_type is Service
    assert original.graph.explain(provider).selected
    assert "provides on demand" in original.graph.to_text()
    assert "provides on demand" in original.graph.to_mermaid()
    manifest = original.graph.manifest().to_dict()
    provider_node = manifest["roots"][0]["dependencies"][0]
    assert provider_node["provider_mode"] == "sync"
    assert provider_node["deferred_target"].endswith(".Service")
    assert not build(OtherService).graph.manifest().diff(original.graph.manifest()).is_empty


def test_provider_root_named_filter_targets_registration_metadata():
    class Service:
        def __init__(self, value: str):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Service, instance=Service("default"))
    builder.register(Service, instance=Service("named"), name="named")
    container = builder.build()

    provider = container.resolve(Provider[Service], cf.with_name("named"))
    assert provider().value == "named"


def test_closed_generic_and_decorated_provider_target_is_precompiled():
    T = TypeVar("T")

    class Repository(Generic[T]):
        pass

    class IntRepository(Repository[int]):
        pass

    class DecoratedRepository(Repository[int]):
        def __init__(self, inner: Repository[int]):
            self.inner = inner

    class Consumer:
        def __init__(self, repository: Provider[Repository[int]]):
            self.repository = repository

    builder = ContainerBuilder()
    builder.register(Repository[int], IntRepository)
    builder.register_decorator(Repository[int], DecoratedRepository, decorated_arg="inner")
    builder.register(Consumer)
    container = builder.build()

    value = container.resolve(Consumer).repository()
    assert isinstance(value, DecoratedRepository)
    assert isinstance(value.inner, IntRepository)
