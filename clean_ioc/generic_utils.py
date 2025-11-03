import types
from typing import (  # type: ignore
    Generic,
    Protocol,
    TypeVar,
    _GenericAlias,  # type: ignore
    _SpecialGenericAlias,  # type: ignore
)

from theutilitybelt.collections.queue import Queue
from theutilitybelt.typing.generics import GenericTypeMap

TypingGenericAlias = (_GenericAlias, _SpecialGenericAlias, types.GenericAlias)
GenericDefinitionClasses = (Generic, Protocol)


def map_type_vars_to_parent(*, child_type: type | TypeVar | _GenericAlias, parent_type: type) -> type | TypeVar:
    parent_type_generic_type_map = GenericTypeMap(parent_type)

    if type(child_type) is TypeVar:
        if child_resolved_type := parent_type_generic_type_map.get(child_type):
            return child_resolved_type
        return child_type

    child_mapping = GenericTypeMap(child_type)
    parent_mapping = GenericTypeMap(parent_type)

    child_generic_type_map = GenericTypeMap(child_type)

    if child_generic_type_map.is_generic_mapping_closed():
        return child_type
    output_args = []
    generic_args = get_generic_type_args(child_type)

    for a in generic_args:
        if from_parent := parent_mapping.get(a):
            output_args.append(from_parent)
            continue

        if from_child := child_mapping.get(a):
            if linked_to_open := parent_mapping.get(from_child):  # type: ignore
                output_args.append(linked_to_open)
                continue

        output_args.append(a)

    return child_type[tuple(output_args)]  # pyright: ignore[reportIndexIssue]


def get_generic_type_args(type: type):
    queue = Queue()
    queue.put(type)

    while not queue.is_empty():
        type_check = queue.get()
        if origin_type := getattr(type_check, "__origin__", None):
            queue.put(origin_type)
            if origin_type in GenericDefinitionClasses:
                return type_check.__args__

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.put(base)
            if base_origin := getattr(base, "__origin__", None):
                queue.put(base_origin)

    return ()
