import inspect
from collections.abc import Iterable
from typing import Callable, TypeVar

from theutilitybelt.functional.predicate import predicate
from theutilitybelt.functional.utils import constant

from .core import Lifespan, Registration

all_registrations = constant(True)


def create_filter(func: Callable[[Registration], bool]):
    return predicate(func)


def with_name(name: str | None):
    """
    Filter registrations equal the name
    """

    def _with_name(r: Registration):
        return r.name == name

    return predicate(_with_name)


def name_starts_with(prefix: str):
    """
    Filter registrations where the name starts the prefix
    """

    def _name_starts_with(r: Registration):
        if r.name is not None:
            return r.name.startswith(prefix)
        return False

    return predicate(_name_starts_with)


def name_ends_with(suffix: str):
    """
    Filter registrations where the name ends the suffix
    """

    def _name_ends_with(r: Registration):
        if r.name is not None:
            return r.name.endswith(suffix)
        return False

    return predicate(_name_ends_with)


is_not_named = with_name(None)
is_not_named.__doc__ = "Filter for registrations that do not have a name"

is_named = ~is_not_named
is_named.__doc__ = "Filter for registrations that have a name"


def with_implementation(implementation: type):
    """
    Filter to registrations that have the implementation
    """

    def _with_implementation(r: Registration):
        return r.implementation == implementation

    return predicate(_with_implementation)


def with_implementation_matching_filter(type_filter: Callable[[type], bool]):
    """
    Returns a filter function that checks if the implementation of a given registration matches a specified type filter.

    Parameters:
        type_filter (Callable[[type], bool]): A function that takes a type and returns a boolean indicating whether
        the type matches a specific criteria.

    Returns:
        Callable[[Registration], bool]: A filter function that takes a registration and returns True if
        the implementation of the registration matches the specified type filter, False otherwise.

    Example:
        >>> type_filter = lambda x: issubclass(x, int)
        >>> registration = Registration(implementation=123)
        >>> with_implementation_matching_filter(type_filter)(registration)
        True
    """

    def _with_implementation_matching_filter(r: Registration):
        if inspect.isfunction(r.implementation):
            return False

        return type_filter(r.implementation)  # type: ignore

    return predicate(_with_implementation_matching_filter)


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

    def _has_generic_args_matching(r: Registration):
        return r.generic_mapping.get(pair[0]) == pair[1]

    return predicate(_has_generic_args_matching)


def has_tag(name: str, value: str | None = None):
    """
    Check if a given registration has a specific tag.

    Parameters:
        name (str): The name of the tag to check for.
        value (str | None, optional): The value of the tag to check for. Defaults to None.

    Returns:
        Callable[[Registration], bool]: A filter function that takes a registration and returns True
        if the registration has the specified tag, False otherwise.
    """

    def _has_tag(r: Registration):
        return r.has_tag(name, value)

    return predicate(_has_tag)


def has_tag_with_value_or_missing_tag(name: str, value: str):
    """
    Check if a given registration has a specific tag with a given value or if it does not have that tag.

    Parameters:
        name (str): The name of the tag to check for.
        value (str): The value of the tag to check for.

    Returns:
        Callable[[Registration], bool]: A filter function that takes a registration and returns True
        if the registration has the specified tag with the given value or if it does not have that tag, False otherwise.
    """
    return has_tag(name, value) | ~has_tag(name)


def has_tag_with_value_in(name: str, *values: str):
    """
    Check if a given registration has a specific tag with a value that matches any of the given values.

    Parameters:
        name (str): The name of the tag to check for.
        *values (str): The values to check for.

    Returns:
        Callable[[Registration], bool]: A filter function that takes a registration and returns True if
        the registration has the specified tag with a value that matches any of the given values, False otherwise.
    """
    predicates = [has_tag(name, v) for v in values]

    def _has_tag_with_value_in(r: Registration):
        return any([p(r) for p in predicates])

    return predicate(_has_tag_with_value_in)


def has_lifespan(lifespan: Lifespan):
    """
    Check if a given registration has a specific lifespan.

    Parameters:
        lifespan (str): The lifespan to check for.

    Returns:
        Callable[[Registration], bool]: A filter function that takes a registration and returns True
        if the registration has the specified lifespan, False otherwise.
    """

    def _has_lifespan(r: Registration):
        return r.lifespan == lifespan

    return predicate(_has_lifespan)


def has_lifespan_in(lifespans: Iterable[Lifespan]):
    """
    Returns a predicate function that checks if the lifespan of a registration is in the given lifespans.

    Args:
        lifespans (Iterable[Lifespan]): The lifespans to check against.

    Returns:
        Callable[[Registration], bool]: A predicate function that returns True if the lifespan of a registration
        is in the given lifespans, False otherwise.
    """

    def _has_lifespans(r: Registration):
        return r.lifespan in lifespans

    return predicate(_has_lifespans)
