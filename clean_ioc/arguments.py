"""Build-time argument policies for Clean IoC composition."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping, TypeVar

from .components import Component, ComponentFilter, default_component_filter

__all__ = [
    "INJECT",
    "REMOVE",
    "ParameterContext",
    "build_arg",
    "derive",
    "generic_arg",
    "inject",
    "select",
]

_MISSING_BUILD_ARG = object()


@dataclass(frozen=True, slots=True)
class ParameterContext:
    """Static information available while deriving one compiled argument value."""

    name: str
    annotation: Any
    component: Component
    default: Any = None
    has_default: bool = False

    @property
    def build_args(self) -> Mapping[str, Any]:
        """Immutable user inputs for the owning component's compilation."""

        return self.component.build_args


@dataclass(frozen=True, slots=True)
class _SelectArgument:
    filter: ComponentFilter


@dataclass(frozen=True, slots=True)
class _DerivedArgument:
    function: Callable[[ParameterContext], Any]


@dataclass(frozen=True, slots=True)
class _FixedArgument:
    value: Any


class _Inject:
    __slots__ = ()

    def __repr__(self) -> str:
        return "INJECT"


class _Remove:
    __slots__ = ()

    def __repr__(self) -> str:
        return "REMOVE"


INJECT = _Inject()
"""Return from :func:`derive` to compile the normal component or scope-slot edge."""

REMOVE = _Remove()
"""Use in ``patch_component(arguments=...)`` to remove an inherited override."""


def select(filter: ComponentFilter = default_component_filter) -> _SelectArgument:
    """Select a component for an argument, ignoring any Python default."""

    if not callable(filter):
        raise TypeError("select() requires a component filter")
    return _SelectArgument(filter)


def build_arg(name: str, *, default: Any = _MISSING_BUILD_ARG) -> _DerivedArgument:
    """Compile one named build argument as a frozen value node."""

    if not isinstance(name, str):
        raise TypeError("build argument names must be strings")

    def resolve_build_arg(context: ParameterContext) -> Any:
        if default is not _MISSING_BUILD_ARG and name not in context.build_args:
            return default
        return context.build_args[name]

    return _DerivedArgument(resolve_build_arg)


def inject() -> _SelectArgument:
    """Force normal unnamed component injection, ignoring a Python default."""

    return _SelectArgument(default_component_filter)


def generic_arg(key: TypeVar | str) -> _DerivedArgument:
    """Compile one generic binding from the owning component as a frozen value node."""

    if not isinstance(key, (TypeVar, str)):
        raise TypeError("generic argument keys must be TypeVar objects or strings")

    def resolve_generic_arg(context: ParameterContext) -> Any:
        return context.component.generic_mapping[key]

    return _DerivedArgument(resolve_generic_arg)


def derive(function: Callable[[ParameterContext], Any]) -> _DerivedArgument:
    """Evaluate a pure argument policy once while the container is built."""

    if not callable(function):
        raise TypeError("derive() requires a callable")
    callable_target = function if inspect.isroutine(function) else getattr(function, "__call__", function)
    if any(
        predicate(callable_target)
        for predicate in (
            inspect.iscoroutinefunction,
            inspect.isasyncgenfunction,
            inspect.isgeneratorfunction,
        )
    ):
        raise TypeError("derive() requires a plain synchronous callable")
    return _DerivedArgument(function)
