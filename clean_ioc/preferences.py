"""Immutable, ordered soft preferences for single injected dependencies."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from .components import ComponentFilter

__all__ = ["ComponentPreference", "prefer"]


def _validate_stage(predicate: ComponentFilter) -> None:
    if not callable(predicate):
        raise TypeError("A preference stage requires a component predicate")
    target = predicate if inspect.isroutine(predicate) else getattr(predicate, "__call__", predicate)
    if any(
        check(candidate)
        for candidate in (predicate, target)
        for check in (inspect.iscoroutinefunction, inspect.isasyncgenfunction, inspect.isgeneratorfunction)
    ):
        raise TypeError("A preference stage requires a plain synchronous predicate")


@dataclass(frozen=True, slots=True, init=False, eq=False)
class ComponentPreference:
    """An immutable chain; each pure synchronous predicate breaks only remaining ties."""

    predicates: tuple[ComponentFilter, ...] = field(repr=False)

    def __init__(self, predicate: ComponentFilter) -> None:
        _validate_stage(predicate)
        object.__setattr__(self, "predicates", (predicate,))

    def then(self, predicate: ComponentFilter) -> ComponentPreference:
        """Return an extended chain without changing this chain or any earlier winner."""
        result = ComponentPreference(predicate)
        object.__setattr__(result, "predicates", (*self.predicates, predicate))
        return result


def prefer(predicate: ComponentFilter) -> ComponentPreference:
    """Start a fallback-preserving preference chain."""
    return ComponentPreference(predicate)


def _validate_preference(value: ComponentPreference | None) -> None:
    if value is not None and not isinstance(value, ComponentPreference):
        raise TypeError("prefer must be a ComponentPreference or None")
