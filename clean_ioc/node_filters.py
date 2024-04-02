from typing import Callable

from .core import Node, NodeFilter
from .functional_utils import constant, predicate

yes = constant(True)


def implementation_type_is(cls: type):
    def inner(node: Node):
        return node.implementation == cls

    return predicate(inner)


def service_type_matches_type_filter(type_filter: Callable[[type], bool]):
    def inner(node: Node):
        return type_filter(node.service_type)

    return predicate(inner)


def implementation_matches_type_filter(type_filter: Callable[[type], bool]):
    def inner(node: Node):
        return type_filter(node.implementation_type)  # type: ignore

    return predicate(inner)


def service_type_is(cls: type):
    def inner(node: Node):
        return node.service_type == cls

    return predicate(inner)


def registration_name_is(name: str):
    def inner(node: Node):
        return node.registration_name == name

    return predicate(inner)


def has_registartion_tag(name: str, value: str | None = None):
    def inner(node: Node):
        return node.has_registration_tag(name, value)

    return predicate(inner)


def has_dependant_service_type(service_type: type):
    def inner(node: Node):
        return node.has_dependant_service_type(service_type)

    return predicate(inner)


def has_dependant_implementation_type(implementation_type: type):
    def inner(node: Node):
        return node.has_dependant_implementation_type(implementation_type)

    return predicate(inner)


def has_dependant_instance_type(instance_type: type):
    def inner(node: Node):
        return node.has_dependant_instance_type(instance_type)

    return predicate(inner)


def jump_parent(filter: NodeFilter):
    def inner(node: Node):
        return filter(node.parent)

    return predicate(inner)
