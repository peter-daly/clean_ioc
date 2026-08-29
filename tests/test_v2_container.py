import gc
import inspect
import types
import weakref
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, Generic, ParamSpec, TypeVar, cast, get_args
from unittest.mock import Mock, patch

import pytest
from assertive import was_called

import clean_ioc.component_filters as cf
from clean_ioc import (
    BuilderAlreadyBuiltError,
    CannotResolveError,
    Component,
    ContainerBuilder,
    ContainerBuildError,
    DependencySettings,
    Lifespan,
    ScopeProvisionError,
    Tag,
    UndeclaredScopeSlotError,
)

T = TypeVar("T")
P = ParamSpec("P")


def test_lifespan_is_a_public_string_literal_and_component_metadata_uses_strings():
    assert get_args(Lifespan) == ("transient", "once_per_graph", "scoped", "singleton")

    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, lifespan="singleton")
    container = builder.build()

    component = container.graph.roots[0].component
    assert component.lifespan == "singleton"
    assert isinstance(component.lifespan, str)


def test_invalid_lifespan_string_is_rejected_during_composition():
    builder = ContainerBuilder()

    with pytest.raises(ValueError, match="lifespan must be one of"):
        builder.register(object, lifespan=cast(Any, "application"))


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


def test_decorator_definitions_have_stable_ids_metadata_and_z_index_order():
    class Service:
        pass

    class Transaction:
        def __init__(self, child: Service):
            self.child = child

    class Metrics:
        def __init__(self, child: Service):
            self.child = child

    builder = ContainerBuilder()
    builder.register(Service)
    transaction_id = builder.register_decorator(
        Service,
        Transaction,
        position=100,
        name="transaction",
        tags=[Tag("concern", "transaction")],
    )
    metrics_id = builder.register_decorator(
        Service,
        Metrics,
        position=1000,
        name="metrics",
        tags=[Tag("concern", "observability")],
    )

    container = builder.build()
    resolved = container.resolve(Service)
    component = next(component for component in container.components if component.service_type is Service)

    assert isinstance(resolved, Metrics)
    assert isinstance(resolved.child, Transaction)
    assert isinstance(resolved.child.child, Service)
    assert transaction_id != metrics_id
    assert [decorator.id for decorator in component.decorators] == [metrics_id, transaction_id]
    assert [decorator.position for decorator in component.decorators] == [1000, 100]
    assert [decorator.name for decorator in component.decorators] == ["metrics", "transaction"]
    assert component.decorators[0].has_tag("concern", "observability")


def test_decorator_signature_errors_are_aggregated_during_build():
    class First:
        pass

    class Second:
        pass

    class MissingChild:
        def __init__(self, value: str):
            self.value = value

    class InvalidExplicitChild:
        def __init__(self, child: Second):
            self.child = child

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    builder.register_decorator(First, MissingChild)
    builder.register_decorator(Second, InvalidExplicitChild, decorated_arg="wrapped")

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert [issue.code for issue in raised.value.report.errors] == ["invalid-decorator", "invalid-decorator"]
    assert "set decorated_arg=" in raised.value.report.errors[0].message
    assert "no argument named 'wrapped'" in raised.value.report.errors[1].message


def test_ambiguous_decorated_argument_requires_an_explicit_name():
    class Service:
        pass

    class Ambiguous:
        def __init__(self, first: Service, second: Service = cast(Service, None)):
            self.first = first
            self.second = second

    builder = ContainerBuilder()
    builder.register(Service)
    decorator_id = builder.register_decorator(Service, Ambiguous)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-decorator"
    assert "multiple arguments" in raised.value.report.errors[0].message

    builder.patch_decorator(Service, decorator_id, decorated_arg="first")
    assert isinstance(builder.build().resolve(Service), Ambiguous)


def test_v2_decorator_api_uses_one_component_filter():
    parameters = inspect.signature(ContainerBuilder.register_decorator).parameters

    assert "when" in parameters
    assert "registration_filter" not in parameters
    assert "decorator_node_filter" not in parameters


def test_callable_decorator_return_annotation_is_validated_during_build():
    class Service:
        pass

    def invalid(child: Service) -> str:
        return str(child)

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register_decorator(Service, invalid)

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-decorator"
    assert "not compatible" in raised.value.report.errors[0].message


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


def test_scope_builder_singleton_finalizers_are_owned_by_built_scope():
    class Resource:
        pass

    events: list[tuple[str, Resource]] = []

    @contextmanager
    def resource_factory():
        resource = Resource()
        events.append(("enter", resource))
        try:
            yield resource
        finally:
            events.append(("exit", resource))

    root = ContainerBuilder().build()
    builder = root.new_scope_builder()
    builder.register(
        Resource,
        factory=resource_factory,
        lifespan="singleton",
    )

    with builder.build() as scope:
        resource = scope.resolve(Resource)
        assert scope.new_scope().resolve(Resource) is resource
        assert events == [("enter", resource)]

    assert events == [("enter", resource), ("exit", resource)]


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
        ("transient", False, False),
        ("once_per_graph", True, False),
        ("scoped", True, True),
        ("singleton", True, True),
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
    builder.register(ScopedResource, factory=resource_factory, lifespan="scoped")
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
    builder.register(Dependency, factory=dependency_factory, lifespan="scoped")
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


def test_subclass_discovery_runs_at_build_and_seals_the_snapshot():
    class Service:
        pass

    builder = ContainerBuilder()
    assert builder.register_subclasses(Service) is None

    late_service_type = type("LateService", (Service,), {})
    container = builder.build()
    too_late_service_type = type("TooLateService", (Service,), {})

    assert isinstance(container.resolve(Service), late_service_type)
    assert late_service_type in {component.implementation_type for component in container.components}
    assert too_late_service_type not in {component.implementation_type for component in container.components}


def test_generic_subclass_and_decorator_discovery_share_the_build_snapshot():
    class Handler(Generic[T]):
        pass

    class Command:
        pass

    class HandlerDecorator(Generic[T]):
        def __init__(self, child: Handler[T]):
            self.child = child

    builder = ContainerBuilder()
    assert builder.register_generic_subclasses(Handler) is None
    builder.register_generic_decorator(Handler, HandlerDecorator, decorated_arg="child")

    late_handler_type = types.new_class("LateHandler", (Handler[Command],))
    container = builder.build()
    resolved = container.resolve(Handler[Command])

    assert type(resolved).__name__ == "__DecoratedGeneric__HandlerDecorator"
    assert isinstance(getattr(resolved, "child"), late_handler_type)


@pytest.mark.parametrize("generic_first", [True, False])
def test_deferred_generic_decorators_preserve_declaration_order(generic_first):
    class Handler(Generic[T]):
        pass

    class Command:
        pass

    class ConcreteHandler(Handler[Command]):
        pass

    class GenericDecorator(Generic[T]):
        def __init__(self, child: Handler[T]):
            self.child = child

    class ExplicitDecorator:
        def __init__(self, child: Handler[Command]):
            self.child = child

    builder = ContainerBuilder()
    builder.register_generic_subclasses(Handler)
    if generic_first:
        builder.register_generic_decorator(Handler, GenericDecorator, decorated_arg="child")
        builder.register_decorator(Handler[Command], ExplicitDecorator, decorated_arg="child")
    else:
        builder.register_decorator(Handler[Command], ExplicitDecorator, decorated_arg="child")
        builder.register_generic_decorator(Handler, GenericDecorator, decorated_arg="child")

    resolved = builder.build().resolve(Handler[Command])

    if generic_first:
        assert type(resolved).__name__ == "__DecoratedGeneric__GenericDecorator"
        assert isinstance(getattr(resolved, "child"), ExplicitDecorator)
    else:
        assert isinstance(resolved, ExplicitDecorator)
        assert type(getattr(resolved, "child")).__name__ == "__DecoratedGeneric__GenericDecorator"


def test_discovery_previews_keep_ids_stable_and_rescan_at_build():
    class Service:
        pass

    class Previewed(Service):
        pass

    builder = ContainerBuilder()
    builder.register_subclasses(Service)

    component_id = builder.get_component_id(Service)
    assert component_id is not None
    assert builder.get_component_id(Service) == component_id
    builder.patch_component(Service, component_id, lifespan="singleton")

    class AddedAfterPreview(Service):
        pass

    container = builder.build()
    components = {component.implementation_type: component for component in container.components}

    assert components[Previewed].id == component_id
    assert components[Previewed].lifespan == "singleton"
    assert AddedAfterPreview in components


@pytest.mark.parametrize("explicit_first", [True, False])
def test_explicit_registration_precedes_discovery_regardless_of_call_order(explicit_first):
    class Service:
        pass

    class Discovered(Service):
        pass

    class Explicit(Service):
        pass

    builder = ContainerBuilder()
    if explicit_first:
        builder.register(Service, Explicit)
        builder.register_subclasses(Service)
    else:
        builder.register_subclasses(Service)
        builder.register(Service, Explicit)

    assert isinstance(builder.build().resolve(Service), Explicit)


def test_failed_build_leaves_discovery_reusable_and_rescans_on_retry():
    class Missing:
        pass

    class Service:
        pass

    class First(Service):
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register_subclasses(Service)

    with pytest.raises(ContainerBuildError):
        builder.build()

    builder.register(Missing)

    class AddedAfterFailure(Service):
        pass

    container = builder.build()
    implementations = {component.implementation_type for component in container.components}

    assert First in implementations
    assert AddedAfterFailure in implementations


def test_discovery_deduplicates_diamonds_and_excludes_abstract_and_raw_generics():
    class Service:
        pass

    class Left(Service):
        pass

    class Right(Service):
        pass

    class Diamond(Left, Right):
        pass

    class AbstractService(Service, ABC):
        @abstractmethod
        def run(self): ...

    builder = ContainerBuilder()
    builder.register_subclasses(Service)
    container = builder.build()
    implementations = [
        component.implementation_type for component in container.components if component.service_type is Service
    ]

    assert implementations.count(Diamond) == 1
    assert AbstractService not in implementations

    class Handler(Generic[T]):
        pass

    raw_handler_type = type("RawHandler", (Handler,), {})

    generic_builder = ContainerBuilder()
    generic_builder.register_generic_subclasses(Handler)
    generic_container = generic_builder.build()

    assert raw_handler_type not in {component.implementation_type for component in generic_container.components}


def test_unretained_dynamic_subclass_can_disappear_before_build():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register_subclasses(Service)

    def create_ephemeral_type():
        ephemeral = type("Ephemeral", (Service,), {})
        return weakref.ref(ephemeral)

    reference = create_ephemeral_type()
    gc.collect()
    container = builder.build()

    assert reference() is None
    assert container.components == ()
    with pytest.raises(CannotResolveError):
        container.resolve(Service)


def test_scope_overlays_only_execute_their_own_discovery_rules():
    class Service:
        pass

    class RootService(Service):
        pass

    root_builder = ContainerBuilder()
    root_builder.register_subclasses(Service)
    container = root_builder.build()

    class LateService(Service):
        pass

    inherited_scope = container.new_scope_builder().build()
    inherited_implementations = {component.implementation_type for component in inherited_scope.components}
    assert LateService not in inherited_implementations

    overlay_builder = container.new_scope_builder()
    overlay_builder.register_subclasses(Service)
    overlay_scope = overlay_builder.build()
    overlay_implementations = {component.implementation_type for component in overlay_scope.components}

    assert RootService in overlay_implementations
    assert LateService in overlay_implementations


def test_closed_generic_factory_specializes_nested_dependencies():
    TItem = TypeVar("TItem")

    class Dependency(Generic[TItem]):
        pass

    class IntDependency(Dependency[int]):
        pass

    class Product(Generic[TItem]):
        def __init__(self, dependencies: list[Dependency[TItem]]):
            self.dependencies = dependencies

    def create_product(dependencies: list[Dependency[TItem]]) -> Product[TItem]:
        return Product(dependencies)

    builder = ContainerBuilder()
    builder.register(Dependency[int], IntDependency)
    builder.register(Product[int], factory=create_product)
    container = builder.build()

    product = container.resolve(Product[int])

    assert len(product.dependencies) == 1
    assert isinstance(product.dependencies[0], IntDependency)
    component = next(component for component in container.components if component.service_type == Product[int])
    assert component.generic_mapping[TItem] is int


def test_generic_factory_infers_a_bare_return_typevar_from_a_concrete_service():
    TConnection = TypeVar("TConnection")

    class Engine(Generic[TConnection]):
        pass

    class Connection:
        pass

    class MyConnection(Connection):
        pass

    class MyEngine(Engine[MyConnection]):
        pass

    def create_connection(engine: Engine[TConnection]) -> TConnection:
        assert isinstance(engine, MyEngine)
        return cast(TConnection, MyConnection())

    builder = ContainerBuilder()
    builder.register(Engine[MyConnection], MyEngine)
    builder.register(MyConnection, factory=create_connection)

    assert isinstance(builder.build().resolve(MyConnection), MyConnection)


def test_factory_specialization_supplies_typevars_not_expressed_by_the_service():
    TConnection = TypeVar("TConnection")

    class Engine(Generic[TConnection]):
        pass

    class Connection:
        pass

    class MyConnection(Connection):
        pass

    class MyEngine(Engine[MyConnection]):
        pass

    def create_connection(engine: Engine[TConnection]) -> Connection:
        assert isinstance(engine, MyEngine)
        return MyConnection()

    builder = ContainerBuilder()
    builder.register(Engine[MyConnection], MyEngine)
    builder.register(Connection, factory=create_connection, factory_specialization=MyEngine)

    assert isinstance(builder.build().resolve(Connection), MyConnection)


def test_open_generic_factory_specializes_known_occurrences_and_keeps_closed_caches_separate():
    TItem = TypeVar("TItem")
    calls = Mock()

    class Dependency(Generic[TItem]):
        pass

    class IntDependency(Dependency[int]):
        pass

    class StrDependency(Dependency[str]):
        pass

    class Product(Generic[TItem]):
        def __init__(self, dependency: Dependency[TItem]):
            self.dependency = dependency

    class FirstIntConsumer:
        def __init__(self, product: Product[int]):
            self.product = product

    class SecondIntConsumer:
        def __init__(self, product: Product[int]):
            self.product = product

    class StrConsumer:
        def __init__(self, product: Product[str]):
            self.product = product

    def create_product(dependency: Dependency[TItem]) -> Product[TItem]:
        calls(type(dependency))
        return Product(dependency)

    builder = ContainerBuilder()
    builder.register(Dependency[int], IntDependency, lifespan="singleton")
    builder.register(Dependency[str], StrDependency, lifespan="singleton")
    builder.register(Product, factory=create_product, lifespan="singleton")
    builder.register(FirstIntConsumer)
    builder.register(SecondIntConsumer)
    builder.register(StrConsumer)
    container = builder.build()

    assert calls == was_called().never()

    first = container.resolve(FirstIntConsumer).product
    second = container.resolve(SecondIntConsumer).product
    string = container.resolve(StrConsumer).product

    assert first is second
    assert first is not string
    assert isinstance(first.dependency, IntDependency)
    assert isinstance(string.dependency, StrDependency)
    assert calls == was_called().twice()
    with pytest.raises(CannotResolveError):
        container.resolve(Product[int])


def test_explicit_closed_factory_is_a_root_and_precedes_an_open_template():
    TItem = TypeVar("TItem")

    class Dependency(Generic[TItem]):
        pass

    class IntDependency(Dependency[int]):
        pass

    class Product(Generic[TItem]):
        def __init__(self, source: str):
            self.source = source

    def create_open(dependency: Dependency[TItem]) -> Product[TItem]:
        return Product("open")

    def create_closed(dependency: Dependency[int]) -> Product[int]:
        return Product("closed")

    builder = ContainerBuilder()
    builder.register(Dependency[int], IntDependency)
    builder.register(Product, factory=create_open)
    builder.register(Product[int], factory=create_closed)

    assert builder.build().resolve(Product[int]).source == "closed"


def test_generic_factory_specializations_apply_closed_decorators_and_share_singletons_with_scope_overlays():
    TItem = TypeVar("TItem")

    class Dependency(Generic[TItem]):
        pass

    class IntDependency(Dependency[int]):
        pass

    class Product(Generic[TItem]):
        pass

    class DecoratedProduct(Product[int]):
        def __init__(self, child: Product[int]):
            self.child = child

    class RootConsumer:
        def __init__(self, product: Product[int]):
            self.product = product

    class OverlayConsumer:
        def __init__(self, product: Product[int]):
            self.product = product

    def create_product(dependency: Dependency[TItem]) -> Product[TItem]:
        return Product()

    builder = ContainerBuilder()
    builder.register(Dependency[int], IntDependency, lifespan="singleton")
    builder.register(Product, factory=create_product, lifespan="singleton")
    builder.register_decorator(Product[int], DecoratedProduct, decorated_arg="child")
    builder.register(RootConsumer)
    container = builder.build()
    root_product = container.resolve(RootConsumer).product

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(OverlayConsumer)
    overlay = overlay_builder.build()

    assert isinstance(root_product, DecoratedProduct)
    assert overlay.resolve(OverlayConsumer).product is root_product


def test_open_generic_decorator_policy_applies_to_closed_factory_components():
    TItem = TypeVar("TItem")

    class Product(Generic[TItem]):
        pass

    class ProductDecorator(Generic[TItem]):
        def __init__(self, child: Product[TItem]):
            self.child = child

    def create_product() -> Product[int]:
        return Product()

    builder = ContainerBuilder()
    builder.register(Product[int], factory=create_product)
    decorator_id = builder.register_decorator(Product, ProductDecorator)
    container = builder.build()
    resolved = container.resolve(Product[int])

    assert type(resolved).__name__ == "__DecoratedGeneric__ProductDecorator"
    assert isinstance(getattr(resolved, "child"), Product)
    root = next(component for component in container.components if component.service_type == Product[int])
    assert root.decorators[0].id == decorator_id


def test_open_generic_callable_decorator_specializes_its_dependencies():
    TItem = TypeVar("TItem")

    class Product(Generic[TItem]):
        pass

    class WrappedProduct(Product[TItem], Generic[TItem]):
        def __init__(self, child: Product[TItem]):
            self.child = child

    class IntProduct(Product[int]):
        pass

    def wrap(child: Product[TItem]) -> Product[TItem]:
        return WrappedProduct(child)

    builder = ContainerBuilder()
    builder.register(Product[int], IntProduct)
    builder.register_decorator(Product, wrap)
    resolved = builder.build().resolve(Product[int])

    assert isinstance(resolved, WrappedProduct)
    assert isinstance(resolved.child, IntProduct)


def test_decorators_can_be_patched_removed_and_overridden_by_scope_builders():
    class Service:
        pass

    class Decorator:
        def __init__(self, child: Service):
            self.child = child

    builder = ContainerBuilder()
    builder.register(Service)
    decorator_id = builder.register_decorator(Service, Decorator)
    builder.patch_decorator(
        Service,
        decorator_id,
        position=900,
        name="patched",
        tags=[Tag("concern", "patched")],
    )
    container = builder.build()

    root = next(component for component in container.components if component.service_type is Service)
    assert isinstance(container.resolve(Service), Decorator)
    assert root.decorators[0].position == 900
    assert root.decorators[0].name == "patched"
    assert root.decorators[0].has_tag("concern", "patched")

    overlay_builder = container.new_scope_builder()
    overlay_builder.remove_decorator(Service, decorator_id)
    overlay = overlay_builder.build()

    assert type(overlay.resolve(Service)) is Service
    assert isinstance(container.resolve(Service), Decorator)


def test_generic_factory_build_errors_explain_unresolved_and_conflicting_typevars():
    TItem = TypeVar("TItem")
    TDependency = TypeVar("TDependency")

    class Dependency(Generic[TItem]):
        pass

    class Product(Generic[TItem]):
        pass

    class StrProduct(Product[str]):
        pass

    def unresolved(dependency: Dependency[TDependency]) -> Product[int]:
        return Product()

    unresolved_builder = ContainerBuilder()
    unresolved_builder.register(Product, factory=unresolved)
    unresolved_builder.register(Product[int], factory=unresolved)

    with pytest.raises(ContainerBuildError, match="Unable to resolve TypeVar.*TDependency"):
        unresolved_builder.build()

    def conflicting(dependency: Dependency[TItem]) -> Product[TItem]:
        return Product()

    conflicting_builder = ContainerBuilder()
    conflicting_builder.register(Product[int], factory=conflicting, factory_specialization=StrProduct)

    with pytest.raises(ContainerBuildError, match="Conflicting TypeVar.*TItem"):
        conflicting_builder.build()

    builder = ContainerBuilder()
    with pytest.raises(ValueError, match="factory_specialization requires factory"):
        builder.register(Product[int], factory_specialization=StrProduct)

    def unsupported(callback: Callable[P, int]) -> Product[int]:
        return Product()

    unsupported_builder = ContainerBuilder()
    unsupported_builder.register(Product[int], factory=unsupported)

    with pytest.raises(ContainerBuildError, match="Unsupported.*ParamSpec P.*only TypeVar"):
        unsupported_builder.build()


def test_generic_generator_factory_preserves_cleanup():
    TItem = TypeVar("TItem")
    events: list[str] = []

    class Dependency(Generic[TItem]):
        pass

    class IntDependency(Dependency[int]):
        pass

    class Product(Generic[TItem]):
        pass

    def create_product(dependency: Dependency[TItem]) -> Iterator[Product[TItem]]:
        assert isinstance(dependency, IntDependency)
        events.append("enter")
        yield Product()
        events.append("exit")

    builder = ContainerBuilder()
    builder.register(Dependency[int], IntDependency, lifespan="scoped")
    builder.register(Product[int], factory=create_product, lifespan="scoped")
    container = builder.build()

    with container.new_scope() as scope:
        assert isinstance(scope.resolve(Product[int]), Product)
        assert events == ["enter"]
    assert events == ["enter", "exit"]


@pytest.mark.asyncio
async def test_generic_async_context_manager_factory_preserves_cleanup():
    TItem = TypeVar("TItem")
    events: list[str] = []

    class Dependency(Generic[TItem]):
        pass

    class IntDependency(Dependency[int]):
        pass

    class Product(Generic[TItem]):
        pass

    @asynccontextmanager
    async def create_product(dependency: Dependency[TItem]) -> AsyncIterator[Product[TItem]]:
        assert isinstance(dependency, IntDependency)
        events.append("enter")
        yield Product()
        events.append("exit")

    builder = ContainerBuilder()
    builder.register(Dependency[int], IntDependency, lifespan="scoped")
    builder.register(Product[int], factory=create_product, lifespan="scoped")
    container = builder.build()

    async with container.new_scope() as scope:
        assert isinstance(await scope.resolve_async(Product[int]), Product)
        assert events == ["enter"]
    assert events == ["enter", "exit"]
