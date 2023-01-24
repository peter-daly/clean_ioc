from typing import Callable
from . import Registration
from .functional_utils import constant

all_registrations = constant(True)


def with_name(name: str):
    def predicate(r: Registration):
        return r.name == name

    return predicate


def name_starts_with(name: str):
    def predicate(r: Registration):
        if r.name is not None:
            return r.name.startswith(name)
        return False

    return predicate


def name_end_with(name: str):
    def predicate(r: Registration):
        if r.name is not None:
            return r.name.endswith(name)
        return False

    return predicate


def is_named(r: Registration):
    return r.is_named


def with_implementation(implementation: type):
    def predicate(r: Registration):
        return r.implementation == implementation

    return predicate


def has_generic_args_matching(pair: tuple[type, type]):
    def predicate(r: Registration):
        return r.generic_mapping.get(pair[0]) == pair[1]

    return predicate
