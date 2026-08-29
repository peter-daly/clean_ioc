"""Factories for selecting values from an already-compiled component plan."""

from typing import Any, Callable, TypeVar

from .components import ComponentFilter, default_component_filter
from .container import ResolutionContext

T = TypeVar("T")

__all__ = [
    "create_type_mapping",
    "create_type_mapping_async",
    "use_component",
    "use_component_async",
]


def use_component(
    service_type: type[T],
    filter: ComponentFilter = default_component_filter,
) -> Callable[[ResolutionContext], T]:
    """Create a factory that selects another component in the current graph."""

    def factory(context: ResolutionContext) -> T:
        return context.resolve(service_type, filter=filter)

    return factory


def use_component_async(
    service_type: type[T],
    filter: ComponentFilter = default_component_filter,
) -> Callable[[ResolutionContext], Any]:
    """Create an async factory that selects another component in the current graph."""

    async def factory(context: ResolutionContext) -> T:
        return await context.resolve_async(service_type, filter=filter)

    return factory


def create_type_mapping(
    service_type: type[T],
    key_getter: Callable[[T], Any],
    filter: ComponentFilter = default_component_filter,
):
    """Create a factory mapping keys to all matching compiled components."""

    def factory(context: ResolutionContext) -> dict[Any, T]:
        items = context.resolve(list[service_type], filter=filter)  # ty: ignore[invalid-type-form]
        return {key_getter(item): item for item in items}

    return factory


def create_type_mapping_async(
    service_type: type[T],
    key_getter: Callable[[T], Any],
    filter: ComponentFilter = default_component_filter,
):
    """Create an async factory mapping keys to matching compiled components."""

    async def factory(context: ResolutionContext) -> dict[Any, T]:
        items = await context.resolve_async(list[service_type], filter=filter)  # ty: ignore[invalid-type-form]
        return {key_getter(item): item for item in items}

    return factory
