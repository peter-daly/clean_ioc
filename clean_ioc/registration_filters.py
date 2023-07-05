from . import Registration
from .functional_utils import constant, fn_not, fn_or

all_registrations = constant(True)


def with_name(name: str | None):
    """
    Filter registrations equal the name
    """

    def predicate(r: Registration):
        return r.name == name

    return predicate


def name_starts_with(prefix: str):
    """
    Filter registrations where the name starts the prefix
    """

    def predicate(r: Registration):
        if r.name is not None:
            return r.name.startswith(prefix)
        return False

    return predicate


def name_ends_with(suffix: str):
    """
    Filter registrations where the name ends the suffix
    """

    def predicate(r: Registration):
        if r.name is not None:
            return r.name.endswith(suffix)
        return False

    return predicate


def is_named(r: Registration):
    """
    Filter registrations that have a name
    """
    return r.is_named


is_not_named = with_name(None)


def with_implementation(implementation: type):
    """
    Filter to registrations that have the implementation
    """

    def predicate(r: Registration):
        return r.implementation == implementation

    return predicate


def has_generic_args_matching(pair: tuple[type, type]):
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

    def predicate(r: Registration):
        return r.generic_mapping.get(pair[0]) == pair[1]

    return predicate


def has_tag(name: str, value: str | None = None):
    def predicate(r: Registration):
        return r.has_tag(name, value)

    return predicate


def has_tag_with_value_or_missing_tag(name: str, value: str):
    return fn_or(has_tag(name, value), fn_not(has_tag(name)))


def has_tag_with_value_in(name: str, *values: str):
    predicates = [has_tag(name, v) for v in values]
    return fn_or(*predicates)
