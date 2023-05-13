from . import Registration
from .functional_utils import constant, fn_not

all_registrations = constant(True)


def with_name(name: str | None):
    """
    Filter registartions equal the name
    """

    def predicate(r: Registration):
        return r.name == name

    return predicate


def name_starts_with(prefix: str):
    """
    Filter registartions where the name starts the prefix
    """

    def predicate(r: Registration):
        if r.name is not None:
            return r.name.startswith(prefix)
        return False

    return predicate


def name_ends_with(suffix: str):
    """
    Filter registartions where the name ends the suffix
    """

    def predicate(r: Registration):
        if r.name is not None:
            return r.name.endswith(suffix)
        return False

    return predicate


def is_named(r: Registration):
    """
    Filter registartions that have a name
    """
    return r.is_named


is_not_named = with_name(None)


def with_implementation(implementation: type):
    """
    Filter to registartions that have the implementation
    """

    def predicate(r: Registration):
        return r.implementation == implementation

    return predicate


def has_generic_args_matching(pair: tuple[type, type]):
    """
    Filter registartions where generic type arg matches
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

    def predicate(r: Registration):
        return r.generic_mapping.get(pair[0]) == pair[1]

    return predicate
