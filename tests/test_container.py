"""Tests for the public compiled builder and runtime API."""

import asyncio
import gc
import inspect
import threading
import types
import weakref
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Callable, Generic, ParamSpec, TypeVar, cast, get_args
from unittest.mock import Mock, patch

import pytest
from assertive import was_called

import clean_ioc.component_filters as cf
from clean_ioc import (
    INJECT,
    REMOVE,
    BuilderAlreadyBuiltError,
    CannotResolveError,
    Component,
    ComponentKind,
    ContainerBuilder,
    ContainerBuildError,
    Lifespan,
    ScopeProvisionError,
    Tag,
    UndeclaredScopeSlotError,
    build_arg,
    derive,
    generic_arg,
    inject,
    select,
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


def test_runtime_ids_are_lazy_stable_and_unique():
    container = ContainerBuilder().build()
    first_scope = container.new_scope()
    second_scope = container.new_scope()

    assert container.id == container.id
    assert first_scope.id == first_scope.id
    assert len({container.id, first_scope.id, second_scope.id}) == 3


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


def test_implementation_type_filter_uses_normalized_factory_return_type():
    class Service:
        pass

    def create_service() -> Service:
        return Service()

    builder = ContainerBuilder()
    builder.register(Service, factory=create_service)
    container = builder.build()
    component = container.graph.roots[0].component

    assert cf.implementation_type_is(Service)(component)
    assert not cf.implementation_is(Service)(component)
    assert cf.implementation_is(create_service)(component)


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

    with patch("clean_ioc._legacy.DependencyNode", side_effect=AssertionError("runtime graph allocation")):
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


def test_cached_none_is_not_treated_as_a_cache_miss():
    class Service:
        pass

    calls = 0

    def create_service() -> Service:
        nonlocal calls
        calls += 1
        return cast(Service, None)

    builder = ContainerBuilder()
    builder.register(Service, factory=create_service, lifespan="singleton")
    container = builder.build()

    assert container.resolve(Service) is None
    assert container.resolve(Service) is None
    assert calls == 1


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


def test_derived_injection_has_a_precompiled_component_edge():
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    calls = 0

    def provider(context):
        nonlocal calls
        calls += 1
        assert context.component.service_type is Service
        return INJECT

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(
        Service,
        arguments={"dependency": derive(provider)},
    )
    container = builder.build()

    assert isinstance(container.resolve(Service).dependency, Dependency)
    assert calls == 1


def test_arguments_compile_plain_values_and_do_not_invoke_callable_values():
    callback = Mock()

    class Service:
        def __init__(self, timeout: float, callback: Callable[[], None]):
            self.timeout = timeout
            self.callback = callback

    builder = ContainerBuilder()
    builder.register(Service, arguments={"timeout": 2.5, "callback": callback})
    container = builder.build()

    service = container.resolve(Service)
    assert service.timeout == 2.5
    assert service.callback is callback
    callback.assert_not_called()
    component = next(component for component in container.components if component.service_type is Service)
    assert {dependency.kind for dependency in component.dependencies} == {ComponentKind.value}


def test_select_ignores_a_python_default_and_compiles_the_selected_component():
    class Dependency:
        pass

    selected = Dependency()

    class Service:
        def __init__(self, dependency: Dependency = cast(Dependency, None)):
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency, instance=selected, name="selected")
    builder.register(Service, arguments={"dependency": select(cf.with_name("selected"))})
    container = builder.build()

    assert container.resolve(Service).dependency is selected


def test_select_filters_collections_and_preserves_candidate_order():
    class Plugin:
        pass

    first = Plugin()
    ignored = Plugin()
    second = Plugin()

    class Service:
        def __init__(self, plugins: list[Plugin]):
            self.plugins = plugins

    builder = ContainerBuilder()
    builder.register(Plugin, instance=first, tags=[Tag("enabled")])
    builder.register(Plugin, instance=ignored)
    builder.register(Plugin, instance=second, tags=[Tag("enabled")])
    builder.register(Service, arguments={"plugins": select(cf.has_tag("enabled"))})

    assert builder.build().resolve(Service).plugins == [second, first]


def test_derive_runs_during_build_with_static_parameter_context():
    contexts = []

    class Service:
        def __init__(self, retries: int = 3):
            self.retries = retries

    def retries(context):
        contexts.append(context)
        return context.default + 1

    builder = ContainerBuilder()
    builder.register(Service, arguments={"retries": derive(retries)})
    container = builder.build()

    assert len(contexts) == 1
    assert contexts[0].name == "retries"
    assert contexts[0].annotation is int
    assert contexts[0].has_default
    assert contexts[0].component.service_type is Service
    assert container.resolve(Service).retries == 4
    assert container.resolve(Service).retries == 4
    assert len(contexts) == 1


def test_build_args_are_immutable_compilation_inputs_available_to_derive_and_graph_metadata():
    calls = 0
    nested = {"feature": True}
    supplied = {"environment": "production", "settings": nested}

    class Service:
        def __init__(self, timeout: int):
            self.timeout = timeout

    def timeout(context):
        nonlocal calls
        calls += 1
        assert context.build_args is context.component.build_args
        return 30 if context.build_args["environment"] == "production" else 5

    builder = ContainerBuilder()
    builder.register(Service, arguments={"timeout": derive(timeout)})
    container = builder.build(build_args=supplied)
    supplied["environment"] = "development"
    supplied["late"] = True

    component = next(component for component in container.components if component.service_type is Service)
    assert container.build_args == {"environment": "production", "settings": nested}
    assert container.graph.build_args is container.build_args
    assert component.build_args is container.build_args
    assert component.dependencies[0].kind is ComponentKind.value
    assert container.build_args["settings"] is nested
    assert "late" not in container.build_args
    with pytest.raises(TypeError):
        cast(dict[str, Any], container.build_args)["environment"] = "test"

    assert container.resolve(Service).timeout == 30
    assert container.resolve(Service).timeout == 30
    assert calls == 1
    assert container.new_scope().build_args is container.build_args


def test_build_arg_compiles_a_named_input_for_factory_injection():
    class Client:
        def __init__(self, environment: str):
            self.environment = environment

    def create_client(environment: str) -> Client:
        return Client(environment)

    supplied = {"environment": "production"}
    builder = ContainerBuilder()
    builder.register(
        Client,
        factory=create_client,
        arguments={"environment": build_arg("environment")},
    )
    container = builder.build(build_args=supplied)
    supplied["environment"] = "development"

    component = next(component for component in container.components if component.service_type is Client)
    assert component.dependencies[0].kind is ComponentKind.value
    assert container.resolve(Client).environment == "production"


def test_build_arg_can_use_an_explicit_default_for_a_missing_input():
    class Client:
        def __init__(self, timeout: int):
            self.timeout = timeout

    builder = ContainerBuilder()
    builder.register(Client, arguments={"timeout": build_arg("timeout", default=30)})

    assert builder.build().resolve(Client).timeout == 30


def test_build_arg_validates_its_name_and_reports_missing_values_during_build():
    with pytest.raises(TypeError, match="names must be strings"):
        build_arg(cast(Any, 1))

    class Service:
        def __init__(self, environment: str):
            self.environment = environment

    builder = ContainerBuilder()
    builder.register(Service, arguments={"environment": build_arg("environment")})

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-derived-argument"


def test_inject_forces_ordinary_component_injection_over_a_python_default():
    class Logger:
        pass

    class Service:
        def __init__(self, logger: Logger = cast(Logger, None)):
            self.logger = logger

    logger = Logger()
    builder = ContainerBuilder()
    builder.register(Logger, instance=logger)
    builder.register(Service, arguments={"logger": inject()})
    container = builder.build()

    service = container.resolve(Service)
    component = next(component for component in container.components if component.service_type is Service)
    assert service.logger is logger
    assert component.dependencies[0].kind is ComponentKind.registration


def test_generic_arg_compiles_typevar_and_string_bindings_from_the_owning_component():
    TItem = TypeVar("TItem")

    class Descriptor(Generic[TItem]):
        def __init__(self, item_type: type):
            self.item_type = item_type

    for key in (TItem, "TItem"):
        builder = ContainerBuilder()
        builder.register(
            Descriptor[int],
            arguments={"item_type": generic_arg(key)},
        )
        descriptor = builder.build().resolve(Descriptor[int])
        assert descriptor.item_type is int


def test_generic_arg_validates_its_key_and_reports_missing_bindings_during_build():
    with pytest.raises(TypeError, match="TypeVar objects or strings"):
        generic_arg(cast(Any, 1))

    class Service:
        def __init__(self, item_type: type):
            self.item_type = item_type

    builder = ContainerBuilder()
    builder.register(Service, arguments={"item_type": generic_arg("TItem")})

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-derived-argument"


def test_build_arg_filters_apply_across_graph_aware_composition():
    configured: list[str] = []

    class Plugin:
        pass

    class ProductionPlugin(Plugin):
        pass

    class Service:
        def __init__(self, plugins: list[Plugin]):
            self.plugins = plugins

    class Decorator(Service):
        def __init__(self, child: Service):
            self.child = child

    def configure() -> None:
        configured.append("configured")

    builder = ContainerBuilder()
    builder.register(
        Plugin,
        ProductionPlugin,
        when=lambda component: component.build_args["environment"] == "production",
    )
    builder.register(
        Service,
        arguments={"plugins": select(cf.has_build_arg("environment"))},
    )
    builder.register_decorator(Service, Decorator, when=cf.build_arg_is("mode", "live"))
    builder.pre_configure(Service, configure, when=cf.build_arg_is("mode", "live"))
    builder.mark_entrypoint(Service, filter=cf.build_arg_is("mode", "live"))

    container = builder.build(build_args={"environment": "production", "mode": "live"})
    service = container.resolve(Service)

    assert isinstance(service, Decorator)
    assert isinstance(service.child.plugins[0], ProductionPlugin)
    assert configured == ["configured"]
    assert container.graph.entrypoints[0].component.service_type is Service


def test_build_arg_filters_treat_missing_keys_as_non_matches():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, when=cf.has_build_arg("enabled"))

    assert not builder.has_component(Service)
    assert not builder.has_component(Service, filter=cf.build_arg_is("enabled", None))
    assert builder.has_component(Service, build_args={"enabled": None})
    assert builder.has_component(
        Service,
        filter=cf.build_arg_is("enabled", None),
        build_args={"enabled": None},
    )


def test_builder_preview_queries_accept_build_args():
    class Service:
        pass

    builder = ContainerBuilder()
    component_id = builder.register(Service, when=cf.build_arg_is("mode", "live"))

    assert not builder.has_component(Service, build_args={"mode": "test"})
    assert builder.has_component(Service, build_args={"mode": "live"})
    assert builder.get_component_ids(Service, build_args={"mode": "live"}) == [component_id]
    assert builder.get_component_id(Service, build_args={"mode": "live"}) == component_id


def test_invalid_build_args_leave_the_builder_reusable():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)

    with pytest.raises(TypeError, match="must be a mapping"):
        builder.build(build_args=cast(Any, [("environment", "production")]))
    with pytest.raises(TypeError, match="keys must be strings"):
        builder.build(build_args=cast(Any, {1: "production"}))

    assert builder.build(build_args={"environment": "production"}).build_args["environment"] == "production"


def test_compilation_failure_can_retry_with_different_build_args_then_becomes_single_use():
    class Service:
        def __init__(self, mode: str):
            self.mode = mode

    def mode(context):
        if context.build_args["mode"] != "live":
            raise ValueError("unsupported mode")
        return context.build_args["mode"]

    builder = ContainerBuilder()
    builder.register(Service, arguments={"mode": derive(mode)})

    with pytest.raises(ContainerBuildError):
        builder.build(build_args={"mode": "invalid"})

    container = builder.build(build_args={"mode": "live"})
    assert container.resolve(Service).mode == "live"
    with pytest.raises(BuilderAlreadyBuiltError):
        builder.build(build_args={"mode": "another"})


def test_missing_build_arg_in_derive_is_reported_as_a_build_error():
    class Service:
        def __init__(self, value: str):
            self.value = value

    builder = ContainerBuilder()
    builder.register(Service, arguments={"value": derive(lambda context: context.build_args["missing"])})

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-derived-argument"


def test_scope_builder_inherits_and_overrides_build_args_without_relabeling_anchored_plans():
    class RootSingleton:
        pass

    class OverlayService:
        def __init__(self, mode: str):
            self.mode = mode

    def configure_root() -> None:
        pass

    root_builder = ContainerBuilder()
    root_builder.register(RootSingleton, lifespan="singleton")
    root_builder.pre_configure(RootSingleton, configure_root)
    root = root_builder.build(build_args={"environment": "production", "mode": "root"})

    overlay_builder = root.new_scope_builder()
    overlay_builder.register(
        OverlayService,
        arguments={"mode": derive(lambda context: context.build_args["mode"])},
    )
    overlay = overlay_builder.build(build_args={"mode": "tenant"})

    assert overlay.build_args == {"environment": "production", "mode": "tenant"}
    assert overlay.graph.build_args is overlay.build_args
    assert overlay.resolve(OverlayService).mode == "tenant"
    overlay_component = next(component for component in overlay.components if component.service_type is OverlayService)
    assert overlay_component.build_args is overlay.build_args

    anchored = next(component for component in overlay.components if component.service_type is RootSingleton)
    assert anchored.build_args == {"environment": "production", "mode": "root"}
    assert anchored.pre_configurations[0].build_args == anchored.build_args
    assert overlay.new_scope().build_args is overlay.build_args


def test_build_args_are_omitted_from_reports_and_graph_serializations():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service)
    container = builder.build(build_args={"private-build-key": "private-build-value"})

    outputs = (
        container.build_report.to_json(),
        container.build_report.to_text(),
        container.graph.manifest().to_json(),
        container.graph.to_text(),
        container.graph.to_mermaid(),
    )
    assert all("private-build-key" not in output for output in outputs)
    assert all("private-build-value" not in output for output in outputs)

    equivalent_builder = ContainerBuilder()
    equivalent_builder.register(Service)
    equivalent = equivalent_builder.build(build_args={"another-private-key": object()})
    assert equivalent.graph.manifest().fingerprint == container.graph.manifest().fingerprint


def test_unknown_argument_override_fails_build_unless_callable_accepts_kwargs():
    class Service:
        pass

    builder = ContainerBuilder()
    builder.register(Service, arguments={"unknown": 1})

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-argument"

    received = None

    def create_service(**kwargs: Any) -> Service:
        nonlocal received
        received = kwargs
        return Service()

    valid_builder = ContainerBuilder()
    valid_builder.register(Service, factory=create_service, arguments={"known_at_composition": 1})
    valid_builder.build().resolve(Service)
    assert received == {"known_at_composition": 1}


def test_derive_rejects_async_functions_and_reports_failures_at_build():
    async def async_policy(context):
        return 1

    with pytest.raises(TypeError, match="synchronous"):
        derive(async_policy)

    class Service:
        def __init__(self, value: int):
            self.value = value

    def failing_policy(context):
        raise ValueError("bad policy")

    builder = ContainerBuilder()
    builder.register(Service, arguments={"value": derive(failing_policy)})

    with pytest.raises(ContainerBuildError) as raised:
        builder.build()

    assert raised.value.report is not None
    assert raised.value.report.errors[0].code == "invalid-derived-argument"


def test_patch_component_remove_restores_automatic_injection():
    class Dependency:
        pass

    injected = Dependency()
    configured = Dependency()

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    builder = ContainerBuilder()
    builder.register(Dependency, instance=injected)
    component_id = builder.register(Service, arguments={"dependency": configured})
    builder.patch_component(Service, component_id, arguments={"dependency": REMOVE})

    assert builder.build().resolve(Service).dependency is injected


def test_decorator_and_pre_configuration_use_the_same_arguments_api():
    configured: list[int] = []

    class Service:
        pass

    class Decorator(Service):
        def __init__(self, child: Service, label: str = "default"):
            self.child = child
            self.label = label

    def configure(batch_size: int = 1) -> None:
        configured.append(batch_size)

    builder = ContainerBuilder()
    builder.register(Service)
    decorator_id = builder.register_decorator(
        Service,
        Decorator,
        decorated_arg="child",
        arguments={"label": "configured"},
    )
    builder.patch_decorator(Service, decorator_id, arguments={"label": REMOVE})
    builder.pre_configure(Service, configure, arguments={"batch_size": 20})
    service = builder.build().resolve(Service)

    assert isinstance(service, Decorator)
    assert service.label == "default"
    assert configured == [20]


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


def test_pre_configurations_run_in_declaration_order_and_share_one_compiled_definition():
    class First:
        pass

    class Second:
        pass

    calls: list[str] = []

    def configure_first() -> None:
        calls.append("first")

    def configure_second() -> None:
        calls.append("second")

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    first_id = builder.pre_configure((First, Second), configure_first)
    second_id = builder.pre_configure((First, Second), configure_second)
    container = builder.build()

    components = {component.service_type: component for component in container.components}
    first_configurations = components[First].pre_configurations
    second_configurations = components[Second].pre_configurations

    assert (first_id, second_id) == tuple(component.id for component in first_configurations)
    assert tuple(component.occurrence_id for component in first_configurations) == tuple(
        component.occurrence_id for component in second_configurations
    )

    container.resolve(Second)
    container.resolve(First)

    assert calls == ["first", "second"]


def test_pre_configuration_api_uses_one_component_filter():
    parameters = inspect.signature(ContainerBuilder.pre_configure).parameters

    assert "when" in parameters
    assert "registration_filter" not in parameters


def test_sync_pre_configuration_is_single_flight_across_concurrent_triggers():
    class First:
        pass

    class Second:
        pass

    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def configure() -> None:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    builder.pre_configure((First, Second), configure)
    container = builder.build()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(container.resolve, First)
        assert entered.wait(timeout=2)
        second = executor.submit(container.resolve, Second)
        release.set()
        assert isinstance(first.result(timeout=2), First)
        assert isinstance(second.result(timeout=2), Second)

    assert calls == 1


@pytest.mark.asyncio
async def test_async_pre_configuration_is_single_flight_across_concurrent_triggers():
    class First:
        pass

    class Second:
        pass

    calls = 0

    async def configure() -> None:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)

    builder = ContainerBuilder()
    builder.register(First)
    builder.register(Second)
    builder.pre_configure((First, Second), configure)
    container = builder.build()

    first, second = await asyncio.gather(container.resolve_async(First), container.resolve_async(Second))

    assert isinstance(first, First)
    assert isinstance(second, Second)
    assert calls == 1


def test_inherited_pre_configuration_cleanup_belongs_to_the_declaring_container():
    class Service:
        pass

    events: list[str] = []

    @contextmanager
    def configure():
        events.append("enter")
        yield
        events.append("exit")

    builder = ContainerBuilder()
    builder.register(Service)
    builder.pre_configure(Service, configure)

    with builder.build() as container:
        overlay_builder = container.new_scope_builder()
        overlay_builder.register(Service)
        with overlay_builder.build() as overlay:
            overlay.resolve(Service)
        assert events == ["enter"]

        container.resolve(Service)
        assert events == ["enter"]

    assert events == ["enter", "exit"]


def test_pre_configuration_order_runs_from_parent_builder_to_overlay_builder():
    class Service:
        pass

    calls: list[str] = []

    builder = ContainerBuilder()
    builder.register(Service)
    builder.pre_configure(Service, lambda: calls.append("parent"))
    container = builder.build()

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Service)
    overlay_builder.pre_configure(Service, lambda: calls.append("overlay"))
    overlay = overlay_builder.build()

    overlay.resolve(Service)

    assert calls == ["parent", "overlay"]


def test_closed_generic_pre_configuration_matches_an_open_generic_registration():
    T = TypeVar("T")

    class Service(Generic[T]):
        pass

    class Consumer:
        def __init__(self, service: Service[int]):
            self.service = service

    calls: list[str] = []

    def configure() -> None:
        calls.append("configured")

    builder = ContainerBuilder()
    builder.register(Service)
    builder.register(Consumer)
    builder.pre_configure(Service[int], configure)
    container = builder.build()

    assert isinstance(container.resolve(Consumer).service, Service)
    assert calls == ["configured"]


def test_tolerated_pre_configuration_failure_is_logged_once_and_not_retried(caplog):
    class Service:
        pass

    calls = 0

    def configure() -> None:
        nonlocal calls
        calls += 1
        raise ValueError("optional configuration failed")

    builder = ContainerBuilder()
    builder.register(Service)
    builder.pre_configure(Service, configure, continue_on_failure=True)
    container = builder.build()

    with caplog.at_level("ERROR", logger="clean_ioc.container"):
        container.resolve(Service)
        container.resolve(Service)

    assert calls == 1
    assert sum("Failed to run pre-configuration" in record.message for record in caplog.records) == 1


def test_continue_on_failure_does_not_suppress_dependency_failures():
    class Dependency:
        pass

    class Service:
        pass

    def create_dependency() -> Dependency:
        raise ValueError("dependency failed")

    def configure(dependency: Dependency) -> None:
        pass

    builder = ContainerBuilder()
    builder.register(Dependency, factory=create_dependency, lifespan="singleton")
    builder.register(Service)
    builder.pre_configure(Service, configure, continue_on_failure=True)
    container = builder.build()

    with pytest.raises(ValueError, match="dependency failed"):
        container.resolve(Service)


def test_propagated_pre_configuration_failure_can_be_retried():
    class Service:
        pass

    calls = 0

    def configure() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("retry configuration")

    builder = ContainerBuilder()
    builder.register(Service)
    builder.pre_configure(Service, configure)
    container = builder.build()

    with pytest.raises(ValueError, match="retry configuration"):
        container.resolve(Service)

    assert isinstance(container.resolve(Service), Service)
    assert calls == 2


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
    builder.register_decorator(Handler, HandlerDecorator, decorated_arg="child")

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
        builder.register_decorator(Handler, GenericDecorator, decorated_arg="child")
        builder.register_decorator(Handler[Command], ExplicitDecorator, decorated_arg="child")
    else:
        builder.register_decorator(Handler[Command], ExplicitDecorator, decorated_arg="child")
        builder.register_decorator(Handler, GenericDecorator, decorated_arg="child")

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
