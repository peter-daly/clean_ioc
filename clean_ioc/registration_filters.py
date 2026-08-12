import inspect
from collections.abc import Iterable
from typing import Callable, TypeVar

from funcie import constant, predicate

from .core import Lifespan, Registration

__all__ = [
    "all_registrations",
    "create_filter",
    "has_generic_args_matching",
    "has_lifespan",
    "has_lifespan_in",
    "has_tag",
    "has_tag_with_value_in",
    "has_tag_with_value_or_missing_tag",
    "is_named",
    "is_not_named",
    "name_ends_with",
    "name_starts_with",
    "with_id",
    "with_implementation",
    "with_implementation_matching_filter",
    "with_name",
]

all_registrations = constant(True)
all_registrations.__doc__ = "Match every registration."


def create_filter(func: Callable[[Registration], bool]):
    """Create a composable registration filter from ``func``.

    ``func`` receives a registration and must return whether it matches.
    """
    return predicate(func)


def with_name(name: str | None):
    """Match registrations whose name equals ``name``.

    Pass ``None`` to match unnamed registrations.
    """

    def _with_name(r: Registration):
        return r.name == name

    _with_name.__name__ = f"with_name({name})"

    return predicate(_with_name)


def with_id(registration_id: str):
    """Match the registration whose unique ID equals ``registration_id``."""

    def _with_id(r: Registration):
        return r.id == registration_id

    _with_id.__name__ = f"with_id({registration_id})"

    return predicate(_with_id)


def name_starts_with(prefix: str):
    """Match named registrations whose name starts with ``prefix``."""

    def _name_starts_with(r: Registration):
        if r.name is not None:
            return r.name.startswith(prefix)
        return False

    _name_starts_with.__name__ = f"name_starts_with({prefix})"

    return predicate(_name_starts_with)


def name_ends_with(suffix: str):
    """Match named registrations whose name ends with ``suffix``."""

    def _name_ends_with(r: Registration):
        if r.name is not None:
            return r.name.endswith(suffix)
        return False

    _name_ends_with.__name__ = f"name_ends_with({suffix})"

    return predicate(_name_ends_with)


is_not_named = with_name(None)
is_not_named.__doc__ = "Match registrations that do not have a name."
is_not_named.__name__ = "is_not_named"


is_named = ~is_not_named
is_named.__doc__ = "Match registrations that have a name."
is_named.__name__ = "is_named"


def with_implementation(implementation: type):
    """Match registrations whose implementation equals ``implementation``."""

    def _with_implementation(r: Registration):
        return r.implementation == implementation

    _with_implementation.__name__ = f"with_implementation({implementation})"

    return predicate(_with_implementation)


def with_implementation_matching_filter(type_filter: Callable[[type], bool]):
    """Match implementation types accepted by ``type_filter``.

    Factory-function implementations do not match because they are not implementation
    types. Use this with predicates from ``clean_ioc.type_filters`` or another callable
    accepting a type.
    """

    def _with_implementation_matching_filter(r: Registration):
        if inspect.isfunction(r.implementation):
            return False

        return type_filter(r.implementation)  # type: ignore

    return predicate(_with_implementation_matching_filter)


def has_generic_args_matching(pair: tuple[TypeVar | str, type]):
    """Match a generic argument by type-variable key and concrete type.

    ``pair`` contains a ``TypeVar`` (or its string name) and the concrete type
    expected in the registration's generic mapping.
    """

    def _has_generic_args_matching(r: Registration):
        return r.generic_mapping.get(pair[0]) == pair[1]

    return predicate(_has_generic_args_matching)


def has_tag(name: str, value: str | None = None):
    """Match registrations containing a tag named ``name``.

    When ``value`` is provided, the tag value must also match. When it is ``None``,
    only the tag name is checked.
    """

    def _has_tag(r: Registration):
        return r.has_tag(name, value)

    _has_tag.__name__ = f"has_tag({name}, {value})"

    return predicate(_has_tag)


def has_tag_with_value_or_missing_tag(name: str, value: str):
    """Match a tag value while allowing registrations without that tag.

    Registrations containing ``name`` with a different value do not match.
    """
    return has_tag(name, value) | ~has_tag(name)


def has_tag_with_value_in(name: str, *values: str):
    """Match registrations whose ``name`` tag has any of ``values``."""
    predicates = [has_tag(name, v) for v in values]

    def _has_tag_with_value_in(r: Registration):
        return any([p(r) for p in predicates])

    return predicate(_has_tag_with_value_in)


def has_lifespan(lifespan: Lifespan):
    """Match registrations whose lifespan equals ``lifespan``."""

    def _has_lifespan(r: Registration):
        return r.lifespan == lifespan

    _has_lifespan.__name__ = f"has_lifespan({lifespan})"

    return predicate(_has_lifespan)


def has_lifespan_in(lifespans: Iterable[Lifespan]):
    """Match registrations whose lifespan occurs in ``lifespans``."""

    def _has_lifespans(r: Registration):
        return r.lifespan in lifespans

    return predicate(_has_lifespans)
