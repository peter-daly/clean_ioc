"""Validate the documented Clean IoC 2 composition and runtime boundaries."""

import asyncio
import re
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar, assert_type

import clean_ioc.component_filters as cf
from clean_ioc import (
    INJECT,
    AsyncProvider,
    BuildIssue,
    Component,
    ContainerBuilder,
    ContainerBuildError,
    Expose,
    IssueSeverity,
    Provider,
    ProviderMapGroup,
    Use,
    ValidationContext,
    build_arg,
    derive,
    generic_arg,
    inject,
)


def validate_build_and_resolution() -> None:
    class Repository:
        pass

    class Service:
        def __init__(self, repository: Repository):
            self.repository = repository

    builder = ContainerBuilder()
    builder.register(Repository)
    builder.register(Service)
    container = builder.build()

    assert isinstance(container.resolve(Service).repository, Repository)  # noqa: S101


def validate_failed_builder_is_reusable() -> None:
    class Missing:
        pass

    class Service:
        def __init__(self, missing: Missing):
            self.missing = missing

    builder = ContainerBuilder()
    builder.register(Service)
    try:
        builder.build()
    except ContainerBuildError:
        builder.register(Missing)
    else:
        raise AssertionError("missing dependency did not fail build")

    assert isinstance(builder.build().resolve(Service).missing, Missing)  # noqa: S101


def validate_components_and_filters() -> None:
    class Service:
        pass

    seen: list[Component] = []

    def when(component: Component) -> bool:
        seen.append(component)
        return True

    builder = ContainerBuilder()
    component_id = builder.register(Service, name="primary", when=when)
    assert builder.get_component_id(Service, filter=cf.with_name("primary")) == component_id  # noqa: S101
    container = builder.build()
    build_calls = len(seen)

    assert isinstance(container.resolve(Service, filter=cf.with_name("primary")), Service)  # noqa: S101
    assert len(seen) == build_calls  # noqa: S101


def validate_lifespans_slots_and_overlays() -> None:
    class Request:
        pass

    class Handler:
        def __init__(self, request: Request):
            self.request = request

    builder = ContainerBuilder()
    builder.declare_scope_slot(Request)
    builder.register(Handler)
    container = builder.build()

    request = Request()
    with container.new_scope().provide(Request, request) as scope:
        assert scope.resolve(Handler).request is request  # noqa: S101

    class Root:
        pass

    class Overlay(Root):
        pass

    overlay_builder = container.new_scope_builder()
    overlay_builder.register(Root, Overlay, lifespan="singleton")
    with overlay_builder.build() as overlay:
        assert isinstance(overlay.resolve(Root), Overlay)  # noqa: S101


def validate_generics_and_decorators() -> None:
    T = TypeVar("T")

    class Message:
        pass

    class A(Message):
        pass

    class Handler(Generic[T]):
        pass

    class AHandler(Handler[A]):
        pass

    class Decorator(Handler[T], Generic[T]):
        def __init__(self, child: Handler[T]):
            self.child = child

    builder = ContainerBuilder()
    builder.register_generic_subclasses(Handler)
    builder.register_decorator(Handler, Decorator, decorated_arg="child")
    handler = builder.build().resolve(Handler[A])

    assert isinstance(handler, Decorator)  # noqa: S101
    assert isinstance(handler.child, AHandler)  # noqa: S101


def validate_factories_and_cleanup() -> None:
    class Resource:
        pass

    events: list[str] = []

    @contextmanager
    def factory():
        events.append("enter")
        yield Resource()
        events.append("exit")

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory, lifespan="scoped")
    container = builder.build()
    with container.new_scope() as scope:
        scope.resolve(Resource)

    assert events == ["enter", "exit"]  # noqa: S101


async def validate_async_factory() -> None:
    class Resource:
        pass

    @asynccontextmanager
    async def factory():
        yield Resource()

    builder = ContainerBuilder()
    builder.register(Resource, factory=factory, lifespan="scoped")
    container = builder.build()
    async with container.new_scope() as scope:
        assert isinstance(await scope.resolve_async(Resource), Resource)  # noqa: S101


def validate_derived_injection() -> None:
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    def provider(context):
        assert context.component.service_type is Service  # noqa: S101
        return INJECT

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(
        Service,
        arguments={"dependency": derive(provider)},
    )
    assert isinstance(builder.build().resolve(Service).dependency, Dependency)  # noqa: S101


def validate_build_arguments() -> None:
    class Client:
        def __init__(self, timeout: int, environment: str, region: str):
            self.timeout = timeout
            self.environment = environment
            self.region = region

    class Publisher:
        pass

    class LivePublisher(Publisher):
        pass

    def timeout(context):
        return 30 if context.build_args["environment"] == "production" else 5

    build_args = {"environment": "production", "mode": "live"}
    builder = ContainerBuilder()
    builder.register(
        Client,
        arguments={
            "timeout": derive(timeout),
            "environment": build_arg("environment"),
            "region": build_arg("region", default="global"),
        },
    )
    builder.register(
        Publisher,
        LivePublisher,
        when=cf.build_arg_is("mode", "live"),
    )
    assert builder.has_component(Publisher, build_args=build_args)  # noqa: S101

    container = builder.build(build_args=build_args)
    build_args["environment"] = "development"

    assert container.resolve(Client).timeout == 30  # noqa: S101
    assert container.resolve(Client).environment == "production"  # noqa: S101
    assert container.resolve(Client).region == "global"  # noqa: S101
    assert isinstance(container.resolve(Publisher), LivePublisher)  # noqa: S101
    assert container.build_args["environment"] == "production"  # noqa: S101


def validate_inject_and_generic_arg() -> None:
    TItem = TypeVar("TItem")

    class Dependency:
        pass

    fallback = Dependency()
    injected = Dependency()

    class Service:
        def __init__(self, dependency: Dependency = fallback):
            self.dependency = dependency

    class Descriptor(Generic[TItem]):
        def __init__(self, item_type: type = object):
            self.item_type = item_type

    Service.__init__.__annotations__["dependency"] = Dependency

    builder = ContainerBuilder()
    builder.register(Dependency, instance=injected)
    builder.register(Service, arguments={"dependency": inject()})
    builder.register(
        Descriptor[int],
        arguments={"item_type": generic_arg(TItem)},
    )
    container = builder.build()

    assert container.resolve(Service).dependency is injected  # noqa: S101
    assert container.resolve(Descriptor[int]).item_type is int  # noqa: S101


def validate_custom_graph_rules() -> None:
    class InfrastructureRepository:
        pass

    class DomainService:
        def __init__(self, repository: InfrastructureRepository):
            self.repository = repository

    InfrastructureRepository.__module__ = "example.infrastructure"
    DomainService.__module__ = "example.domain"

    def enforce_architecture(context: ValidationContext):
        for visit in context.graph.walk():
            if len(visit.components) < 2:
                continue
            owner, dependency = visit.components[-2:]
            if owner.implementation_type.__module__.startswith("example.domain") and (
                dependency.implementation_type.__module__.startswith("example.infrastructure")
            ):
                yield visit.issue(
                    "example-layer-boundary",
                    "Domain components cannot depend directly on infrastructure components",
                )

    invalid_builder = ContainerBuilder()
    invalid_builder.register(InfrastructureRepository)
    invalid_builder.register(DomainService)
    invalid_builder.add_validation_rule(enforce_architecture)

    try:
        invalid_builder.build()
    except ContainerBuildError as error:
        assert error.report is not None  # noqa: S101
        assert error.report.errors[0].code == "example-layer-boundary"  # noqa: S101
        assert error.report.errors[0].path[-1].endswith("InfrastructureRepository")  # noqa: S101
    else:
        raise AssertionError("custom architecture rule did not fail the build")

    class InspectedService:
        pass

    validation_calls = 0

    def expensive_rule(context: ValidationContext):
        nonlocal validation_calls
        validation_calls += 1
        assert context.type_ast(InspectedService) is not None  # noqa: S101
        return (
            BuildIssue(
                code="example-expensive-warning",
                severity=IssueSeverity.warning,
                message="Expensive policy warning",
            ),
        )

    validation_builder = ContainerBuilder()
    validation_builder.register(InspectedService)
    validation_builder.add_validation_rule(expensive_rule, mode="validation")
    container = validation_builder.build()

    assert validation_calls == 0  # noqa: S101
    assert not container.build_report.issues  # noqa: S101
    report = container.validation_report()
    assert validation_calls == 1  # noqa: S101
    assert report.warnings[0].code == "example-expensive-warning"  # noqa: S101
    assert not container.build_report.issues  # noqa: S101


def validate_boundaries() -> None:
    class RootSettings:
        pass

    class PrivateClient:
        def __init__(self, settings: RootSettings):
            self.settings = settings

    class PublicService:
        def __init__(self, client: PrivateClient):
            self.client = client

    def feature_bundle(builder):
        builder.register(PrivateClient)
        builder.register(PublicService)

    builder = ContainerBuilder()
    builder.register(RootSettings, lifespan="singleton")
    builder.create_boundary("feature", uses=(Use.root(RootSettings),), exposes=(Expose(PublicService),)).apply_bundle(
        feature_bundle
    )
    container = builder.build()
    assert isinstance(container.resolve(PublicService).client, PrivateClient)  # noqa: S101
    assert not container.has_component(PrivateClient)  # noqa: S101


def validate_union_factory() -> None:
    # Local clients exercise the Redis example without requiring Redis or a server.
    class Redis:
        pass

    class RedisCluster:
        pass

    RedisClient = Redis | RedisCluster  # noqa: N806

    class RedisConfig:
        def __init__(self, cluster_mode: bool):
            self.cluster_mode = cluster_mode

    def get_redis_client(config: RedisConfig) -> RedisClient:
        return RedisCluster() if config.cluster_mode else Redis()

    class Cache:
        def __init__(self, client: RedisClient):
            self.client = client

    for cluster_mode in (False, True):
        builder = ContainerBuilder()
        builder.register(RedisConfig, instance=RedisConfig(cluster_mode), lifespan="singleton")
        builder.register(RedisClient, factory=get_redis_client, lifespan="singleton")
        builder.register(Cache)
        with builder.build() as container:
            client = container.resolve(RedisClient)
            assert_type(client, Redis | RedisCluster)
            assert isinstance(client, RedisCluster if cluster_mode else Redis)  # noqa: S101
            assert container.resolve(Cache).client is client  # noqa: S101


def validate_provider_maps() -> None:
    class PaymentGateway:
        created = 0

        def __init__(self):
            PaymentGateway.created += 1

    class StripeGateway(PaymentGateway):
        pass

    class PayPalGateway(PaymentGateway):
        pass

    class Checkout:
        def __init__(self, gateways: Mapping[str, Provider[PaymentGateway]]):
            self.gateways = gateways

    delegated = ProviderMapGroup("delegated-gateways", str, PaymentGateway)

    builder = ContainerBuilder()
    builder.register(PaymentGateway, StripeGateway, name="stripe", lifespan="scoped", contributes={delegated: "stripe"})
    builder.register(PaymentGateway, PayPalGateway, name="paypal", lifespan="scoped")
    builder.register_provider_map(PaymentGateway, key=lambda component: component.name)
    builder.register_provider_map(delegated, name="explicit")
    builder.register_provider_map(
        PaymentGateway,
        key=lambda component: 7,
        key_type=int,
        component_filter=cf.with_name("stripe"),
        asynchronous=True,
    )
    builder.register(Checkout)
    with builder.build() as container:
        with container.new_scope() as scope:
            checkout = scope.resolve(Checkout)
            assert PaymentGateway.created == 0  # noqa: S101
            gateway = checkout.gateways["stripe"]()
            assert isinstance(gateway, StripeGateway)  # noqa: S101
            assert PaymentGateway.created == 1  # noqa: S101
            explicit = scope.resolve(Mapping[str, Provider[PaymentGateway]], cf.with_name("explicit"))
            assert isinstance(explicit["stripe"](), StripeGateway)  # noqa: S101
            async_map = scope.resolve(Mapping[int, AsyncProvider[PaymentGateway]])
            assert asyncio.run(async_map[7]()) is gateway  # noqa: S101


def validate_registration_patterns() -> None:
    T = TypeVar("T")

    class Serializer(Generic[T]):
        def serialize(self, value: T) -> str:
            raise NotImplementedError

    @dataclass
    class Order:
        reference: str

    class OrderSerializer(Serializer[Order]):
        def serialize(self, value: Order) -> str:
            return value.reference

    class ListSerializer(Serializer[list[T]]):
        def __init__(self, item_serializer: Serializer[T]):
            self.item_serializer = item_serializer

        def serialize(self, value: list[T]) -> str:
            return "[" + ", ".join(self.item_serializer.serialize(item) for item in value) + "]"

    def make_list_serializer(item_serializer: Serializer[T]) -> Serializer[list[T]]:
        return ListSerializer(item_serializer)

    class ExportOrders:
        def __init__(self, serializer: Serializer[list[Order]]):
            self.serializer = serializer

    class ExportBatches:
        def __init__(self, serializer: Serializer[list[list[Order]]]):
            self.serializer = serializer

    builder = ContainerBuilder()
    builder.register(Serializer[Order], OrderSerializer)
    builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)
    builder.register(ExportOrders)
    builder.register(ExportBatches)
    with builder.build() as container:
        exporter = container.resolve(ExportOrders)
        assert exporter.serializer.serialize([Order("A"), Order("B")]) == "[A, B]"  # noqa: S101
        batches = container.resolve(ExportBatches)
        assert batches.serializer.serialize([[Order("A")], [Order("B")]]) == "[[A], [B]]"  # noqa: S101


def validate_decorator_template_guide() -> None:
    """Execute the complete, standalone programs printed in the template guide."""
    guide = Path(__file__).resolve().parents[1] / "docs" / "decorator-templates.md"
    snippets = re.findall(r"```python\n(.*?)\n```", guide.read_text(), flags=re.DOTALL)
    assert len(snippets) >= 2  # noqa: S101
    for index, snippet in enumerate(snippets[:2], start=1):
        exec(compile(snippet, f"{guide} example {index}", "exec"), {"__name__": "__main__"})  # noqa: S102


def main() -> None:
    validate_build_and_resolution()
    validate_failed_builder_is_reusable()
    validate_components_and_filters()
    validate_lifespans_slots_and_overlays()
    validate_generics_and_decorators()
    validate_factories_and_cleanup()
    validate_union_factory()
    validate_derived_injection()
    validate_build_arguments()
    validate_inject_and_generic_arg()
    validate_custom_graph_rules()
    validate_boundaries()
    validate_provider_maps()
    validate_registration_patterns()
    validate_decorator_template_guide()
    asyncio.run(validate_async_factory())
    print("documentation examples validated")


if __name__ == "__main__":
    main()
