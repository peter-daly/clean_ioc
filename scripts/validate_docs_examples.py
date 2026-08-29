"""Validate the documented Clean IoC 2 composition and runtime boundaries."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import Generic, TypeVar

import clean_ioc.component_filters as cf
from clean_ioc import (
    Component,
    ContainerBuilder,
    ContainerBuildError,
    DependencySettings,
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


def validate_value_provider_fallback() -> None:
    class Dependency:
        pass

    class Service:
        def __init__(self, dependency: Dependency):
            self.dependency = dependency

    def provider(default, context):
        assert context.component.service_type is Service  # noqa: S101
        return default

    builder = ContainerBuilder()
    builder.register(Dependency)
    builder.register(
        Service,
        dependency_config={"dependency": DependencySettings(value_factory=provider)},
    )
    assert isinstance(builder.build().resolve(Service).dependency, Dependency)  # noqa: S101


def main() -> None:
    validate_build_and_resolution()
    validate_failed_builder_is_reusable()
    validate_components_and_filters()
    validate_lifespans_slots_and_overlays()
    validate_generics_and_decorators()
    validate_factories_and_cleanup()
    validate_value_provider_fallback()
    asyncio.run(validate_async_factory())
    print("documentation examples validated")


if __name__ == "__main__":
    main()
