from typing import Any, Callable, TypeVar

from .core import RegistrationFilter, Resolver, default_registration_filter


def use_registered(cls: type, filter: RegistrationFilter = default_registration_filter):
    def factory(resolver: Resolver):
        return resolver.resolve(cls, filter=filter)

    return factory


def use_registered_async(cls: type, filter: RegistrationFilter = default_registration_filter):
    async def factory(resolver: Resolver):
        return await resolver.resolve_async(cls, filter=filter)

    return factory


T = TypeVar("T")


def create_type_mapping(
    service_type: type[T],
    key_getter: Callable[[T], Any],
    filter: RegistrationFilter = default_registration_filter,
):
    def factory(resolver: Resolver):
        items = resolver.resolve(list[service_type], filter=filter)
        return {key_getter(item): item for item in items}

    return factory


def create_type_mapping_async(
    service_type: type[T],
    key_getter: Callable[[T], Any],
    filter: RegistrationFilter = default_registration_filter,
):
    async def factory(resolver: Resolver):
        items = await resolver.resolve_async(list[service_type], filter=filter)
        return {key_getter(item): item for item in items}

    return factory
