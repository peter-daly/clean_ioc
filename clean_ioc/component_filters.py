"""Composable predicates for the unified :class:`clean_ioc.Component` model."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Callable, TypeVar

from funcie import predicate

from .components import ComponentFilter, Lifespan, all_components

__all__ = [
    "all_components",
    "build_arg_is",
    "create_filter",
    "has_descendant",
    "has_build_arg",
    "has_generic_arg",
    "has_lifespan",
    "has_lifespan_in",
    "has_tag",
    "implementation_is",
    "implementation_type_is",
    "implementation_matches_type_filter",
    "is_named",
    "is_not_named",
    "name_ends_with",
    "name_starts_with",
    "parent",
    "service_type_is",
    "with_id",
    "with_name",
]

_MISSING_BUILD_ARG = object()


def _described(filter, description: str, *, selector: tuple[str, Any] | None = None):
    filter.__clean_ioc_description__ = description
    if selector is not None:
        filter.__clean_ioc_selector__ = selector
    return filter


def create_filter(function: ComponentFilter):
    result = predicate(function)
    name = getattr(function, "__qualname__", None) or getattr(function, "__name__", None)
    setattr(result, "__clean_ioc_description__", name or "<anonymous-filter>")
    return result


def has_build_arg(name: str):
    if not isinstance(name, str):
        raise TypeError("build argument names must be strings")
    return _described(predicate(lambda component: name in component.build_args), "has_build_arg(<redacted>)")


def build_arg_is(name: str, value: Any):
    if not isinstance(name, str):
        raise TypeError("build argument names must be strings")
    return _described(
        predicate(lambda component: component.build_args.get(name, _MISSING_BUILD_ARG) == value),
        "build_arg_is(<redacted>)",
    )


def with_name(name: str | None):
    return _described(
        predicate(lambda component: component.name == name),
        f"with_name({name!r})",
        selector=("name", name),
    )


def with_id(component_id: str):
    return _described(predicate(lambda component: component.id == component_id), f"with_id({component_id!r})")


def name_starts_with(prefix: str):
    return _described(
        predicate(lambda component: component.name is not None and component.name.startswith(prefix)),
        f"name_starts_with({prefix!r})",
    )


def name_ends_with(suffix: str):
    return _described(
        predicate(lambda component: component.name is not None and component.name.endswith(suffix)),
        f"name_ends_with({suffix!r})",
    )


is_not_named = with_name(None)
is_named = _described(predicate(lambda component: component.name is not None), "is_named")


def implementation_is(implementation: Any):
    return _described(predicate(lambda component: component.implementation == implementation), "implementation_is")


def implementation_type_is(implementation_type: type):
    return _described(
        predicate(lambda component: component.implementation_type == implementation_type),
        f"implementation_type_is({implementation_type.__module__}.{implementation_type.__qualname__})",
    )


def implementation_matches_type_filter(type_filter: Callable[[type], bool]):
    return _described(
        predicate(lambda component: type_filter(component.implementation_type)),
        "implementation_matches_type_filter",
    )


def service_type_is(service_type: type):
    return _described(
        predicate(lambda component: component.service_type == service_type),
        f"service_type_is({service_type.__module__}.{service_type.__qualname__})",
    )


def has_tag(name: str, value: str | None = None):
    return _described(
        predicate(lambda component: component.has_tag(name, value)),
        f"has_tag({name!r}, {value!r})",
    )


TGeneric = TypeVar("TGeneric")


def has_generic_arg(key: TypeVar | str, value: type):
    return _described(predicate(lambda component: component.generic_mapping.get(key) == value), "has_generic_arg")


def has_lifespan(lifespan: Lifespan):
    return _described(predicate(lambda component: component.lifespan == lifespan), f"has_lifespan({lifespan!r})")


def has_lifespan_in(lifespans: Iterable[Lifespan]):
    values = frozenset(lifespans)
    return _described(predicate(lambda component: component.lifespan in values), "has_lifespan_in")


def has_descendant(filter: ComponentFilter):
    return _described(predicate(lambda component: component.has_descendant(filter)), "has_descendant")


def parent(filter: ComponentFilter):
    return _described(
        predicate(lambda component: component.parent is not None and filter(component.parent)),
        "parent",
    )
