from . import Resolver, RegistartionFilter
from .registration_filters import all_registrations


def use_registered(cls: type, filter: RegistartionFilter = all_registrations):
    def factory(resolver: Resolver):
        return resolver.resolve(cls, filter=filter)

    return factory
