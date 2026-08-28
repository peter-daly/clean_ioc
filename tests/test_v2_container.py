from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch

import pytest

import clean_ioc.component_filters as cf
from clean_ioc import (
    BuilderAlreadyBuiltError,
    Component,
    ContainerBuilder,
    ContainerBuildError,
    DependencySettings,
    Lifespan,
    ScopeProvisionError,
    UndeclaredScopeSlotError,
)


def test_builder_compiles_an_immutable_container_and_is_single_use():
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Service)

    container = builder.build()

    assert isinstance(container.resolve(Service).dependency, Dependency)
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.register(str, instance="late")
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.build()


def test_failed_build_leaves_builder_reusable():
    class Missing:
        pass

    class Service:
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Service)

    with pytest.raises(ContainerBuildError):
        builder.build()

    builder.register(Missing)
    assert isinstance(builder.build().resolve(Service).missing, Missing)


def test_component_filters_run_at_build_and_are_frozen_for_resolution():
    class Service:
        pass

    calls: list[Component] = []

    def when(component: Component) -> bool:
        calls.append(component)
        return True

    builder = ContainerBuilder()
    component_id = builder.register(Service, when=when)
    container = builder.build()
    build_calls = len(calls)

    assert build_calls > 0
    assert container.resolve(Service)
    assert container.resolve(Service)
    assert len(calls) == build_calls
    component = next(component for component in container.components if component.id == component_id)
    assert component.service_type is Service
    assert component.parent is None


def test_component_filters_cover_selection_and_undecorated_descendants():
    class Database:
        pass

    class Service:
        def __init__(self, database: Database):
            self.database = database

    class Decorator:
        def __init__(self, child: Service):
            self.child = child

    builder = ContainerBuilder()
    builder.register(Database)
    builder.register(Service, name="database")
    builder.register_decorator(
        Service,
        Decorator,
        when=cf.has_descendant(cf.service_type_is(Database)),
    )

    container = builder.build()
    service = container.resolve(Service, filter=cf.with_name("database"))

    assert isinstance(service, Decorator)
    assert isinstance(service.child.database, Database)


def test_collections_are_static_components_with_selected_members():
    class Plugin:
        pass

    class First(Plugin):
        pass

    class Second(Plugin):
        pass

    class Host:
        def __init__(self, plugins: list[Plugin]):
            self.plugins = plugins

    builder = ContainerBuilder()
    builder.register(Plugin, First)
    builder.register(Plugin, Second, name="excluded")
    builder.register(Host)
    container = builder.build()

    host_component = next(component for component in container.components if component.service_type is Host)
    collection = host_component.dependencies[0]

    assert collection.kind.value == "collection"
    assert [component.implementation_type for component in collection.dependencies] == [First]
    assert [type(plugin) for plugin in container.resolve(Host).plugins] == [First]


def test_declared_scope_slots_are_provided_before_resolution_and_inherited():
    class Request:
        pass

    class Handler:
        def __init__(self, request: Request):
            self.request = request

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Handler)
    container = builder.build()

    parent_request = Request()
    parent = container.new_scope().provide(Request, parent_request)
    assert parent.resolve(Handler).request is parent_request

    child = parent.new_scope()
    assert child.resolve(Handler).request is parent_request

    unlocked_child = parent.new_scope()
    child_request = Request()
    unlocked_child.provide(Request, child_request)
    assert unlocked_child.resolve(Handler).request is child_request

    with pytest.raises(ScopeProvisionError):
        parent.provide(Request, Request())
    with pytest.raises(UndeclaredScopeSlotError):
        container.new_scope().provide(str, "no slot")


def test_scope_builder_overrides_without_mutating_parent_plan():
    class Service:
        pass

    class RootService(Service):
        pass

    class TenantService(Service):
        pass

    builder = ContainerBuilder()
    builder.register(Service, RootService)
    container = builder.build()

    scope_builder = container.new_scope_builder()
    scope_builder.register(Service, TenantService)
    tenant_scope = scope_builder.build()

    assert isinstance(container.resolve(Service), RootService)
    assert isinstance(tenant_scope.resolve(Service), TenantService)
    assert isinstance(tenant_scope.new_scope().resolve(Service), TenantService)


def test_scope_builder_singletons_are_owned_and_torn_down_by_built_scope():
    class Resource:
        pass

    torn_down: list[Resource] = []
    root = ContainerBuilder().build()
    builder = root.new_scope_builder()
    builder.register(
        Resource,
        lifespan=Lifespan.singleton,
        scoped_teardown=torn_down.append,
    )

    with builder.build() as scope:
        resource = scope.resolve(Resource)
        assert scope.new_scope().resolve(Resource) is resource
        assert torn_down == []

    assert torn_down == [resource]


def test_runtime_resolution_does_not_allocate_legacy_dependency_nodes():
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(Service)
    container = builder.build()

    with patch("clean_ioc.core.DependencyNode", side_effect=AssertionError("runtime graph allocation")):
        assert isinstance(container.resolve(Service).dependency, Dependency)


def test_once_per_graph_scoped_singleton_and_transient_lifespans():
    class Item:
        pass

    class Pair:
        def __init__(self, first: Item, second: Item):
            self.first = first
            self.second = second

    for lifespan, same_within_graph, same_across_resolves in (
        (Lifespan.transient, False, False),
        (Lifespan.once_per_graph, True, False),
        (Lifespan.scoped, True, True),
        (Lifespan.singleton, True, True),
    ):
        builder = ContainerBuilder()
        builder.register(Item, lifespan=lifespan)
        builder.register(Pair)
        container = builder.build()
        first = container.resolve(Pair)
        second = container.resolve(Pair)
        assert (first.first is first.second) is same_within_graph
        assert (first.first is second.first) is same_across_resolves


def test_generator_and_context_manager_finalizers_follow_cache_owner():
    events: list[str] = []

    class ScopedResource:
        pass

    @contextmanager
    def resource_factory():
        events.append("enter")
        yield ScopedResource()
        events.append("exit")

    builder = ContainerBuilder()
    builder.register(ScopedResource, factory=resource_factory, lifespan=Lifespan.scoped)
    container = builder.build()

    with container.new_scope() as scope:
        scope.resolve(ScopedResource)
        assert events == ["enter"]

    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_async_factory_and_async_context_manager_resolution():
    events: list[str] = []

    class Dependency:
        pass

    @asynccontextmanager
    async def dependency_factory():
        events.append("enter")
        yield Dependency()
        events.append("exit")

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency, factory=dependency_factory, lifespan=Lifespan.scoped)
    builder.register(Service)
    container = builder.build()

    async with container.new_scope() as scope:
        service = await scope.resolve_async(Service)
        assert isinstance(service.dependency, Dependency)
        assert events == ["enter"]

    assert events == ["enter", "exit"]


def test_value_provider_has_a_precompiled_fallback_edge():
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    calls = 0

    def provider(default, context):
        nonlocal calls
        calls += 1
        assert context.component.service_type is Service
        return default

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(
        Service,
        dependency_config={"dependency": DependencySettings(value_factory=provider)},
    )
    container = builder.build()

    assert isinstance(container.resolve(Service).dependency, Dependency)
    assert calls == 1


def test_shared_pre_configuration_runs_once_across_roots_and_scope_overlays():
    class First:
        pass

    class Second:
        pass

    calls: list[str] = []

    def configure() -> None:
        calls.append("configured")

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    builder.pre_configure((First, Second), configure)
    container = builder.build()

    container.resolve(First)
    container.resolve(Second)
    container.new_scope_builder().build().resolve(First)

    assert calls == ["configured"]
