"""Composable predicates for the unified :class:`clean_ioc.Component` model."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import wraps
from types import GenericAlias
from typing import Any, Callable, Generic, Self, TypeVar, cast, get_args

from funcie import predicate as _predicate
from typetoolbox.generics import get_generic_mapping
from typing_extensions import TypeForm

from .components import Component, ComponentFilter, Lifespan, all_components, default_component_filter
from .metadata import Tag
from .sentinels import Undefined, _Undefined
from .tooling import qualified_name
from .type_aliases import normalize_type_alias

__all__ = [
    "ComponentSelector",
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
TService = TypeVar("TService")


class _SelectorAlias(GenericAlias):
    """Preserve standard typing metadata on frozen instances and factory results."""

    _alias: Any

    def __new__(cls, alias: Any) -> Self:
        result = super().__new__(cls, alias.__origin__, alias.__args__)
        object.__setattr__(result, "_alias", alias)
        return result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = cast(type, self.__origin__)(*args, **kwargs)
        object.__setattr__(result, "__orig_class__", self._alias)
        return result

    def __getitem__(self, parameters: Any) -> _SelectorAlias:
        return type(self)(self._alias[parameters])

    def __reduce__(self):
        return type(self), (self._alias,)

    def __getattribute__(self, name: str) -> Any:
        if name == "_alias":
            return object.__getattribute__(self, name)
        if name == "__orig_bases__":
            return (self._alias,)
        attribute = super().__getattribute__(name)
        if name in ("default", "all"):

            @wraps(attribute)
            def factory(*args: Any, **kwargs: Any) -> Any:
                result = attribute(*args, **kwargs)
                object.__setattr__(result, "__orig_class__", self._alias)
                return result

            return factory
        return attribute


@dataclass(frozen=True, slots=True)
class ComponentSelector(Generic[TService]):
    """Reusable inputs for a component filter, suitable for bundle configuration.

    ``Undefined`` fields impose no restriction. All supplied fields, tags, and
    the optional predicate must match; ``name=None`` selects unnamed components,
    and a tag without a value matches any value for that tag name. When every
    field is undefined, use the default filter for unnamed components.

    The type parameter constrains service and implementation types for static
    checking; it does not add a runtime filter.
    """

    implementation_type: TypeForm[TService] | None | _Undefined = Undefined
    name: str | None | _Undefined = Undefined
    lifespan: Lifespan | _Undefined = Undefined
    tags: Iterable[Tag] | _Undefined = Undefined
    service_type: TypeForm[TService] | None | _Undefined = Undefined
    predicate: ComponentFilter | _Undefined = Undefined
    __orig_class__: Any = field(default=None, init=False, repr=False, compare=False)

    @classmethod
    def __class_getitem__(cls, parameters: Any) -> _SelectorAlias:
        # Use Generic's validation and retain its canonical alias for typetoolbox.
        return _SelectorAlias(super(ComponentSelector, cls).__class_getitem__(parameters))

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # Keep inherited bindings in the standard form understood by type inspection.
        if bases := cls.__dict__.get("__orig_bases__"):
            cls.__orig_bases__ = tuple(base._alias if isinstance(base, _SelectorAlias) else base for base in bases)
        super(ComponentSelector, cls).__init_subclass__(**kwargs)

    def __post_init__(self) -> None:
        if self.predicate is not Undefined and not callable(self.predicate):
            raise TypeError("ComponentSelector.predicate must be a component filter")
        if self.tags is not Undefined:
            object.__setattr__(self, "tags", tuple(self.tags))

    @property
    def resolved_service_type(self) -> TypeForm[TService] | None | _Undefined:
        """Return the explicit service type, otherwise its retained generic binding."""
        if self.service_type is not Undefined:
            return self.service_type
        service_type = get_generic_mapping(self).get(TService, Undefined)
        return Undefined if isinstance(service_type, TypeVar) else service_type

    @classmethod
    def default(cls) -> Self:
        """Create a selector with every field undefined, suitable as a default value."""
        return cls()

    @classmethod
    def all(cls) -> Self:
        """Create a selector matching named and unnamed components."""
        return cls(predicate=all_components)

    def to_filter(self) -> ComponentFilter:
        """Return the default filter if empty, otherwise a composable filter."""
        if all(
            value is Undefined
            for value in (
                self.service_type,
                self.implementation_type,
                self.name,
                self.lifespan,
                self.tags,
                self.predicate,
            )
        ):
            return default_component_filter
        result = create_filter(all_components)
        if self.service_type is not Undefined:
            result &= service_type_is(self.service_type)
        if self.implementation_type is not Undefined:
            result &= implementation_type_is(self.implementation_type)
        if self.name is not Undefined:
            result &= with_name(self.name)
        if self.lifespan is not Undefined:
            result &= has_lifespan(self.lifespan)
        if self.tags is not Undefined:
            for tag in self.tags:
                result &= has_tag(tag.name, tag.value)
        if self.predicate is not Undefined:
            result &= create_filter(self.predicate)
        return result


class _StructuredPredicate(_predicate):
    """Normal predicate semantics plus an inspectable early eligibility expression."""

    def __init__(self, function, expression=None):
        super().__init__(function)
        self.expression = expression

    def __and__(self, other):
        return _StructuredPredicate(lambda value: self(value) and other(value), ("and", self, other))

    def __rand__(self, other):
        return _StructuredPredicate(lambda value: other(value) and self(value), ("and", other, self))

    def __or__(self, other):
        return _StructuredPredicate(lambda value: self(value) or other(value), ("or", self, other))

    def __ror__(self, other):
        return _StructuredPredicate(lambda value: other(value) or self(value), ("or", other, self))

    def __invert__(self):
        return _StructuredPredicate(lambda value: not self(value), ("not", self))


def predicate(function):
    if isinstance(function, _StructuredPredicate):
        return function
    return _StructuredPredicate(
        function, ("static",) if (function is all_components or function is default_component_filter) else None
    )


def _early_match(filter: ComponentFilter, component: Component) -> bool | None:
    """Evaluate only declared static leaves; unknown is never a rejection.

    Unknown left operands stop evaluation so their callbacks retain normal
    short-circuit order when evaluated later against the complete subtree.
    """
    if filter is all_components:
        return True
    expression = getattr(filter, "expression", None)
    if expression is None:
        return None
    operation, *operands = expression
    if operation == "generic":
        binding = component.generic_mapping.get(operands[0], Undefined)

        def unbound(value):
            return isinstance(value, TypeVar) or any(unbound(argument) for argument in get_args(value))

        return None if unbound(binding) else bool(filter(component))
    if operation == "static":
        return bool(filter(component))
    if operation == "parent":
        return False if component.parent is None else _early_match(operands[0], component.parent)
    left = _early_match(operands[0], component)
    if left is None:
        return None
    if operation == "not":
        return not left
    if operation == "and":
        return False if not left else _early_match(operands[1], component)
    return True if left else _early_match(operands[1], component)


def _described(filter, description: str, *, selector: tuple[str, Any] | None = None):
    filter.__clean_ioc_description__ = description
    if description.startswith(
        (
            "with_id(",
            "with_name(",
            "name_starts_with(",
            "name_ends_with(",
            "service_type_is(",
            "has_tag(",
            "has_generic_arg",
            "is_named",
        )
    ):
        filter.expression = ("static",)
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


def implementation_type_is(implementation_type: TypeForm[Any] | None):
    implementation_type = normalize_type_alias(implementation_type)
    return _described(
        predicate(lambda component: component.implementation_type == implementation_type),
        f"implementation_type_is({qualified_name(implementation_type)})",
    )


def implementation_matches_type_filter(type_filter: Callable[[type], bool]):
    return _described(
        predicate(lambda component: type_filter(component.implementation_type)),
        "implementation_matches_type_filter",
    )


def service_type_is(service_type: TypeForm[Any] | None):
    service_type = normalize_type_alias(service_type)
    return _described(
        predicate(lambda component: component.service_type == service_type),
        f"service_type_is({qualified_name(service_type)})",
    )


def has_tag(name: str, value: str | None = None):
    return _described(
        predicate(lambda component: component.has_tag(name, value)),
        f"has_tag({name!r}, {value!r})",
    )


TGeneric = TypeVar("TGeneric")


def has_generic_arg(key: TypeVar | str, value: type):
    result = _described(predicate(lambda component: component.generic_mapping.get(key) == value), "has_generic_arg")
    result.expression = ("generic", key)
    return result


def has_lifespan(lifespan: Lifespan):
    return _described(predicate(lambda component: component.lifespan == lifespan), f"has_lifespan({lifespan!r})")


def has_lifespan_in(lifespans: Iterable[Lifespan]):
    values = frozenset(lifespans)
    return _described(predicate(lambda component: component.lifespan in values), "has_lifespan_in")


def has_descendant(filter: ComponentFilter):
    return _described(predicate(lambda component: component.has_descendant(filter)), "has_descendant")


def parent(filter: ComponentFilter):
    result = _described(
        predicate(lambda component: component.parent is not None and filter(component.parent)),
        "parent",
    )

    result.expression = ("parent", filter)
    return result
