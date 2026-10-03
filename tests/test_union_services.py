"""Explicit union keys retain normal composition and resolution semantics."""

from collections.abc import AsyncIterator, Iterator
from typing import Generic, TypeVar, Union, assert_type

import pytest
from typing_extensions import TypeForm

import clean_ioc.component_filters as cf
from clean_ioc import (
    AsyncProvider,
    CannotResolveError,
    ComponentBuilder,
    ContainerBuilder,
    ContainerBuildError,
    Lifespan,
    Provider,
    ResolutionContext,
    inject,
    select,
)
from clean_ioc.factories import use_component, use_component_async
from clean_ioc.tooling import qualified_name


class StandaloneClient:
    mode = "standalone"


class ClusterClient:
    mode = "cluster"


Client = StandaloneClient | ClusterClient
T = TypeVar("T")


class Box(Generic[T]):
    pass


class Consumer:
    def __init__(self, client: Client):
        self.client = client


def create_client() -> Client:
    return StandaloneClient()


@pytest.mark.parametrize("key", [Client, ClusterClient | StandaloneClient, Union[StandaloneClient, ClusterClient]])
@pytest.mark.parametrize("implementation", [StandaloneClient, ClusterClient])
@pytest.mark.parametrize("source", ["factory", "instance", "implementation"])
def test_union_registration_and_injection(key: TypeForm[Client], implementation: type[Client], source: str):
    calls: list[Client] = []

    def factory() -> Client:
        value = implementation()
        calls.append(value)
        return value

    builder = ContainerBuilder()
    if source == "factory":
        builder.register(key, factory=factory, lifespan="singleton")
    elif source == "instance":
        builder.register(key, instance=implementation())
    else:
        builder.register(key, implementation, lifespan="singleton")
    builder.register(Consumer)

    with builder.build() as container:
        assert calls == []
        value = container.resolve(Client)
        assert_type(value, StandaloneClient | ClusterClient)
        assert type(value) is implementation
        assert container.resolve(Consumer).client is value
        assert container.resolve(Union[ClusterClient, StandaloneClient]) is value
        assert container.resolve(ClusterClient | StandaloneClient) is value
        assert not container.has_component(StandaloneClient)
        assert not container.has_component(ClusterClient)
        if source == "factory":
            assert calls == [value]


@pytest.mark.parametrize("key", [Client, Union[StandaloneClient, ClusterClient], StandaloneClient | None])
def test_union_requires_an_explicit_activation_source(key: TypeForm[object]):
    builder = ContainerBuilder()
    with pytest.raises(TypeError, match="Union service .* requires a factory, instance or implementation type"):
        builder.register(key)
    # A rejected registration must leave the builder reusable and unmodified.
    builder.register(key, factory=create_client)
    with builder.build() as container:
        assert isinstance(container.resolve(key), StandaloneClient)


def test_registering_members_does_not_register_the_union():
    builder = ContainerBuilder()
    builder.register(StandaloneClient)
    builder.register(ClusterClient)
    with builder.build() as container:
        with pytest.raises(CannotResolveError):
            container.resolve(Client)

    builder = ContainerBuilder()
    builder.register(StandaloneClient)
    builder.register(ClusterClient)
    builder.register(Consumer)
    with pytest.raises(ContainerBuildError) as raised:
        builder.build()
    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "missing-component"
    assert raised.value.report.errors[0].path[-1] == qualified_name(Client)


def test_optional_union_preserves_python_default_and_explicit_injection():
    class Defaulted:
        def __init__(self, client: StandaloneClient | None = None):
            self.client = client

    builder = ContainerBuilder()
    builder.register(StandaloneClient | None, StandaloneClient)
    builder.register(Defaulted)
    builder.register(Defaulted, name="injected", arguments={"client": inject()})
    with builder.build() as container:
        assert container.resolve(Defaulted).client is None
        assert isinstance(container.resolve(Defaulted, cf.with_name("injected")).client, StandaloneClient)

    class Required:
        def __init__(self, client: StandaloneClient | None):
            self.client = client

    missing = ContainerBuilder()
    missing.register(StandaloneClient)
    missing.register(Required)
    with pytest.raises(ContainerBuildError, match="missing-component"):
        missing.build()


@pytest.mark.parametrize("lifespan", ["transient", "per_resolution", "scoped", "singleton"])
def test_union_lifespans(lifespan: Lifespan):
    class Pair:
        def __init__(self, left: Client, right: Client):
            self.left, self.right = left, right

    builder = ContainerBuilder()
    builder.register(Client, factory=create_client, lifespan=lifespan)
    builder.register(Pair, lifespan="transient")
    with builder.build() as container:
        with container.new_scope() as scope:
            first = scope.resolve(Pair)
            second = scope.resolve(Pair)
            assert (first.left is first.right) == (lifespan != "transient")
            assert (first.left is second.left) == (lifespan in ("scoped", "singleton"))
        with container.new_scope() as scope:
            assert (scope.resolve(Client) is first.left) == (lifespan == "singleton")


def test_union_generator_and_provider_share_scoped_resource_and_cleanup():
    events: list[str] = []

    def resource() -> Iterator[Client]:
        events.append("open")
        try:
            yield ClusterClient()
        finally:
            events.append("close")

    class Deferred:
        def __init__(self, client: Provider[Client]):
            self.client = client

    builder = ContainerBuilder()
    builder.register(Client, factory=resource, lifespan="scoped")
    builder.register(Deferred)
    with builder.build() as container:
        assert events == []
        with container.new_scope() as scope:
            provider = scope.resolve(Deferred).client
            assert events == []
            value = provider()
            assert_type(value, StandaloneClient | ClusterClient)
            assert scope.resolve(Provider[Client])() is value
            assert scope.resolve(Client) is value
            assert events == ["open"]
        assert events == ["open", "close"]


async def test_async_union_factory_and_resolution_context():
    calls: list[str] = []

    async def factory() -> Client:
        calls.append("factory")
        return ClusterClient()

    async def forward(context: ResolutionContext) -> Client:
        value = await context.resolve_async(Client)
        assert_type(value, StandaloneClient | ClusterClient)
        return value

    builder = ContainerBuilder()
    builder.register(Client, factory=factory, lifespan="singleton")
    builder.register(object, factory=forward, name="context")
    builder.register(object, factory=use_component_async(Client), name="helper")
    async with builder.build() as container:
        assert calls == []
        with pytest.raises(RuntimeError, match="requires resolve_async"):
            container.resolve(Client)
        value = await container.resolve_async(Client)
        assert_type(value, StandaloneClient | ClusterClient)
        assert await container.resolve_async(object, cf.with_name("context")) is value
        assert await container.resolve_async(object, cf.with_name("helper")) is value
        assert calls == ["factory"]


async def test_async_union_resource_and_provider_cleanup():
    events: list[str] = []

    async def resource() -> AsyncIterator[Client]:
        events.append("open")
        try:
            yield ClusterClient()
        finally:
            events.append("close")

    class Deferred:
        def __init__(self, client: AsyncProvider[Client]):
            self.client = client

    builder = ContainerBuilder()
    builder.register(Client, factory=resource, lifespan="scoped")
    builder.register(Deferred)
    async with builder.build() as container:
        assert events == []
        async with container.new_scope() as scope:
            provider = scope.resolve(Deferred).client
            assert events == []
            value = await provider()
            assert_type(value, StandaloneClient | ClusterClient)
            assert await (await scope.resolve_async(AsyncProvider[Client]))() is value
            assert await scope.resolve_async(Client) is value
        assert events == ["open", "close"]


def test_union_scope_slots_and_overlay_registration():
    def bundle(builder: ComponentBuilder):
        builder.declare_scope_slot(Client)
        builder.register(Consumer)

    builder = ContainerBuilder()
    builder.apply_bundle(bundle)
    value = ClusterClient()
    with builder.build() as container:
        with container.new_scope() as scope:
            scope.provide(ClusterClient | StandaloneClient, value)
            assert scope.has_provision(Client)
            assert scope.resolve(Consumer).client is value
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Client, factory=create_client, lifespan="singleton")
        with overlay_builder.build() as overlay:
            assert isinstance(overlay.resolve(Consumer).client, StandaloneClient)
        with container.new_scope() as scope:
            scope.provide(Client, value)
            assert scope.resolve(Consumer).client is value


def test_union_selection_helpers_patching_and_pre_configuration():
    events: list[str] = []

    def configure():
        events.append("configured")

    def forward(context: ResolutionContext) -> Client:
        value = context.resolve(Client)
        assert_type(value, StandaloneClient | ClusterClient)
        return value

    builder = ContainerBuilder()
    composition: ComponentBuilder = builder
    component_id = composition.register(Client, factory=create_client)
    composition.patch_component(Client, component_id, lifespan="singleton")
    composition.pre_configure(Client, configure)
    composition.register(Client, ClusterClient, name="cluster")
    composition.register(object, factory=forward, name="context")
    composition.register(object, factory=use_component(Client), name="helper")
    composition.register(Consumer, arguments={"client": select(cf.with_name("cluster"))})
    unnamed_union = cf.service_type_is(Client) & cf.is_not_named
    composition.mark_entrypoint(Client, filter=unnamed_union)
    with builder.build() as container:
        assert events == []
        assert container.resolve(Consumer).client.mode == "cluster"
        assert events == ["configured"]
        value = container.resolve(Client, unnamed_union)
        assert container.resolve(object, cf.with_name("context")) is value
        assert container.resolve(object, cf.with_name("helper")) is value
        assert all(cf.service_type_is(Client)(item) for item in container.components if item.id == component_id)
        explanation = container.graph.explain(Client, filter=unnamed_union)
        assert explanation.selected[0].component_id == component_id


def test_equivalent_union_graphs_have_identical_manifests_and_fingerprints():
    manifests = []
    for key in (Client, ClusterClient | StandaloneClient, Union[StandaloneClient, ClusterClient]):
        builder = ContainerBuilder()
        builder.register(key, factory=create_client)
        builder.register(Consumer)
        with builder.build() as container:
            union_components = [component for component in container.components if component.service_type == Client]
            assert union_components
            assert all(component.implementation_type is type(create_client) for component in union_components)
            manifests.append(container.graph.manifest())
    assert len({manifest.to_json() for manifest in manifests}) == 1
    assert len({manifest.fingerprint for manifest in manifests}) == 1


def test_union_identities_are_canonical_recursively_and_other_names_are_unchanged():
    expected = f"typing.Union[{__name__}.ClusterClient, {__name__}.StandaloneClient]"
    assert qualified_name(Client) == expected
    assert qualified_name(Union[ClusterClient, StandaloneClient]) == expected
    assert qualified_name(dict[str, list[Client]]) == f"dict[str, list[{expected}]]"
    assert qualified_name(dict[str, list[ClusterClient | StandaloneClient]]) == f"dict[str, list[{expected}]]"
    assert qualified_name(StandaloneClient) == f"{__name__}.StandaloneClient"
    assert qualified_name(list[int]) == "list[int]"


def test_class_generic_and_union_resolution_keep_precise_types():
    builder = ContainerBuilder()
    builder.register(StandaloneClient)
    builder.register(Box[int])
    builder.register(Client, factory=create_client)
    with builder.build() as container:
        assert_type(container.resolve(StandaloneClient), StandaloneClient)
        assert_type(container.resolve(Box[int]), Box[int])
        assert_type(container.resolve(Client), StandaloneClient | ClusterClient)
        assert_type(container.resolve(Union[StandaloneClient, ClusterClient]), StandaloneClient | ClusterClient)
        assert_type(container.resolve(list[Client]), list[StandaloneClient | ClusterClient])
        assert_type(container.resolve(Provider[Client]), Provider[StandaloneClient | ClusterClient])
