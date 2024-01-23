from . import Resolver, RegistrationFilter, _default_registration_filter
from typing import Any, Callable, TypeVar


def use_registered(
    cls: type, filter: RegistrationFilter = _default_registration_filter
):
    def factory(resolver: Resolver):
        return resolver.resolve(cls, filter=filter)

    return factory


T = TypeVar("T")


def create_type_mapping(
    service_type: type[T],
    key_getter: Callable[[T], Any],
    filter: RegistrationFilter = _default_registration_filter,
):
    def factory(resolver: Resolver):
        items = resolver.resolve(list[service_type], filter=filter)
        return {key_getter(item): item for item in items}

    return factory
