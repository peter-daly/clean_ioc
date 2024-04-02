import inspect
from typing import Callable, TypeVar

from .core import Registration
from .functional_utils import constant, predicate

all_registrations = constant(True)


def with_name(name: str | None):
    """
    Filter registrations equal the name
    """

    def inner(r: Registration):
        return r.name == name

    return predicate(inner)


def name_starts_with(prefix: str):
    """
    Filter registrations where the name starts the prefix
    """

    def inner(r: Registration):
        if r.name is not None:
            return r.name.startswith(prefix)
        return False

    return predicate(inner)


def name_ends_with(suffix: str):
    """
    Filter registrations where the name ends the suffix
    """

    def inner(r: Registration):
        if r.name is not None:
            return r.name.endswith(suffix)
        return False

    return predicate(inner)


def _is_named(r: Registration):
    """
    Filter registrations that have a name
    """
    return r.is_named


is_named = predicate(_is_named)
is_not_named = with_name(None)


def with_implementation(implementation: type):
    """
    Filter to registrations that have the implementation
    """

    def inner(r: Registration):
        return r.implementation == implementation

    return predicate(inner)


def with_implementation_matching_filter(type_filter: Callable[[type], bool]):
    """
    Returns a filter function that checks if the implementation of a given registration matches a specified type filter.

    Parameters:
        type_filter (Callable[[type], bool]): A function that takes a type and returns a boolean indicating whether the type matches a specific criteria.

    Returns:
        Callable[[Registration], bool]: A filter function that takes a registration and returns True if the implementation of the registration matches the specified type filter, False otherwise.

    Example:
        >>> type_filter = lambda x: issubclass(x, int)
        >>> registration = Registration(implementation=123)
        >>> with_implementation_matching_filter(type_filter)(registration)
        True
    """

    def inner(r: Registration):
        if inspect.isfunction(r.implementation):
            return False

        return type_filter(r.implementation)  # type: ignore

    return predicate(inner)


def has_generic_args_matching(pair: tuple[TypeVar | str, type]):
    """
    Filter registrations where generic type arg matches
    >>> TBar = TypeVar("TBar")
    >>> class Foo(Generic[TBar]):
    ...    pass
    >>> class IntFoo(Foo[int]):
    ...    pass
    >>> class StringFoo(Foo[str]):
    ...    pass
    >>> container.register(Foo, IntFoo)
    >>> container.register(Foo, StringFoo)
    >>> container.resolve(Foo, filter=has_generic_args_matching((TBar, int))) # returns instance of IntFoo
    """

    def inner(r: Registration):
        return r.generic_mapping.get(pair[0]) == pair[1]

    return predicate(inner)


def has_tag(name: str, value: str | None = None):
    def inner(r: Registration):
        return r.has_tag(name, value)

    return predicate(inner)


def has_tag_with_value_or_missing_tag(name: str, value: str):
    return has_tag(name, value) | ~has_tag(name)


def has_tag_with_value_in(name: str, *values: str):
    predicates = [has_tag(name, v) for v in values]

    def inner(r: Registration):
        return any([p(r) for p in predicates])

    return predicate(inner)
