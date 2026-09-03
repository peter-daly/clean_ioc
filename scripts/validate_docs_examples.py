"""Validate the documented Clean IoC 2 composition and runtime boundaries."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import Generic, TypeVar

import clean_ioc.component_filters as cf
from clean_ioc import (
    INJECT,
    Component,
    ContainerBuilder,
    ContainerBuildError,
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


def main() -> None:
    validate_build_and_resolution()
    validate_failed_builder_is_reusable()
    validate_components_and_filters()
    validate_lifespans_slots_and_overlays()
    validate_generics_and_decorators()
    validate_factories_and_cleanup()
    validate_derived_injection()
    validate_build_arguments()
    validate_inject_and_generic_arg()
    asyncio.run(validate_async_factory())
    print("documentation examples validated")


if __name__ == "__main__":
    main()
