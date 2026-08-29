"""Composable predicates for the unified :class:`clean_ioc.Component` model."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable, TypeVar

from funcie import predicate

from .components import ComponentFilter, Lifespan, all_components

__all__ = [
    "all_components",
    "create_filter",
    "has_descendant",
    "has_generic_arg",
    "has_lifespan",
    "has_lifespan_in",
    "has_tag",
    "implementation_is",
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


def create_filter(function: ComponentFilter):
    return predicate(function)


def with_name(name: str | None):
    return predicate(lambda component: component.name == name)


def with_id(component_id: str):
    return predicate(lambda component: component.id == component_id)


def name_starts_with(prefix: str):
    return predicate(lambda component: component.name is not None and component.name.startswith(prefix))


def name_ends_with(suffix: str):
    return predicate(lambda component: component.name is not None and component.name.endswith(suffix))


is_not_named = with_name(None)
is_named = ~is_not_named


def implementation_is(implementation: type):
    return predicate(lambda component: component.implementation == implementation)


def implementation_matches_type_filter(type_filter: Callable[[type], bool]):
    return predicate(lambda component: type_filter(component.implementation_type))


def service_type_is(service_type: type):
    return predicate(lambda component: component.service_type == service_type)


def has_tag(name: str, value: str | None = None):
    return predicate(lambda component: component.has_tag(name, value))


TGeneric = TypeVar("TGeneric")


def has_generic_arg(key: TypeVar | str, value: type):
    return predicate(lambda component: component.generic_mapping.get(key) == value)


def has_lifespan(lifespan: Lifespan):
    return predicate(lambda component: component.lifespan == lifespan)


def has_lifespan_in(lifespans: Iterable[Lifespan]):
    values = frozenset(lifespans)
    return predicate(lambda component: component.lifespan in values)


def has_descendant(filter: ComponentFilter):
    return predicate(lambda component: component.has_descendant(filter))


def parent(filter: ComponentFilter):
    return predicate(lambda component: component.parent is not None and filter(component.parent))
