from typing import Callable

from funcie import constant, predicate

from .core import Node, NodeFilter

__all__ = [
    "has_dependant_implementation_type",
    "has_dependant_instance_type",
    "has_dependant_service_type",
    "has_registration_tag",
    "implementation_matches_type_filter",
    "implementation_type_is",
    "jump_parent",
    "registration_name_is",
    "service_type_is",
    "service_type_matches_type_filter",
    "yes",
]

yes = constant(True)
yes.__doc__ = "Match every node."


def implementation_type_is(cls: type):
    """Match nodes whose registered implementation equals ``cls``."""

    def inner(node: Node):
        return node.implementation == cls

    return predicate(inner)


def service_type_matches_type_filter(type_filter: Callable[[type], bool]):
    """Match nodes whose service type is accepted by ``type_filter``."""

    def inner(node: Node):
        return type_filter(node.service_type)

    return predicate(inner)


def implementation_matches_type_filter(type_filter: Callable[[type], bool]):
    """Match nodes whose normalized implementation type is accepted by ``type_filter``.

    For class implementations, the normalized type is the class itself. For callable
    implementations, it is the callable's type.
    """

    def inner(node: Node):
        return type_filter(node.implementation_type)

    return predicate(inner)


def service_type_is(cls: type):
    """Match nodes whose registered service type equals ``cls``."""

    def inner(node: Node):
        return node.service_type == cls

    return predicate(inner)


def registration_name_is(name: str):
    """Match nodes created from a registration named ``name``."""

    def inner(node: Node):
        return node.registration_name == name

    return predicate(inner)


def has_registration_tag(name: str, value: str | None = None):
    """Match nodes created from a registration containing a tag named ``name``.

    When ``value`` is provided, the tag value must also match. When it is ``None``,
    only the tag name is checked.
    """

    def inner(node: Node):
        return node.has_registration_tag(name, value)

    return predicate(inner)


def has_dependant_service_type(service_type: type):
    """Match nodes with a descendant whose service type equals ``service_type``."""

    def inner(node: Node):
        return node.has_dependant_service_type(service_type)

    return predicate(inner)


def has_dependant_implementation_type(implementation_type: type):
    """Match nodes with a descendant whose implementation type equals ``implementation_type``."""

    def inner(node: Node):
        return node.has_dependant_implementation_type(implementation_type)

    return predicate(inner)


def has_dependant_instance_type(instance_type: type):
    """Match nodes with a resolved descendant whose instance type equals ``instance_type``."""

    def inner(node: Node):
        return node.has_dependant_instance_type(instance_type)

    return predicate(inner)


def jump_parent(filter: NodeFilter):
    """Apply ``filter`` to the node's parent instead of to the node itself."""

    def inner(node: Node):
        return filter(node.parent)

    return predicate(inner)
