from typing import Callable

from theutilitybelt.functional.predicate import predicate
from theutilitybelt.functional.utils import constant

from .core import Node, NodeFilter

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


def has_registration_tag(name: str, value: str | None = None):
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
