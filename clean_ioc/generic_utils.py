import types
from collections import deque
from typing import (
    Any,
    Generic,
    Protocol,
    TypeVar,
    Union,
    _GenericAlias,  # ty:ignore[unresolved-import]
    _SpecialGenericAlias,  # ty:ignore[unresolved-import]
    get_args,
    get_origin,
)

from typetoolbox.generics import GenericTypeMap

from .type_aliases import TypeAliasNormalizationError, normalize_type_alias

TypingGenericAlias = (_GenericAlias, _SpecialGenericAlias, types.GenericAlias)
GenericDefinitionClasses = (Generic, Protocol)


def constructor_type(implementation: Any) -> type | None:
    """Recognise classes and class aliases without mistaking unions for constructors."""
    try:
        implementation = normalize_type_alias(implementation)
    except TypeAliasNormalizationError:
        return None
    if isinstance(implementation, type):
        return implementation
    origin = get_origin(implementation)
    if isinstance(origin, type) and origin not in (Union, types.UnionType):
        return origin
    return None


def map_type_vars_to_parent(*, child_type: type | TypeVar | _GenericAlias, parent_type: type) -> type | TypeVar:
    parent_type_generic_type_map = GenericTypeMap(parent_type)

    if type(child_type) is TypeVar:
        if child_resolved_type := parent_type_generic_type_map.get(child_type):
            return child_resolved_type
        return child_type

    child_mapping = GenericTypeMap(child_type)
    parent_mapping = GenericTypeMap(parent_type)

    child_generic_type_map = GenericTypeMap(child_type)

    if child_generic_type_map.is_mapping_specialized():
        return child_type
    output_args = []
    generic_args = get_generic_type_args(child_type)

    for a in generic_args:
        if from_parent := parent_mapping.get(a):
            output_args.append(from_parent)
            continue

        if from_child := child_mapping.get(a):
            if linked_to_open := parent_mapping.get(from_child):
                output_args.append(linked_to_open)
                continue

        output_args.append(a)

    return child_type[tuple(output_args)]  # ty: ignore[not-subscriptable]


def get_generic_type_args(type: type):
    queue = deque()
    queue.append(type)

    while queue:
        type_check = queue.popleft()
        if origin_type := getattr(type_check, "__origin__", None):
            queue.append(origin_type)
            if origin_type in GenericDefinitionClasses:
                return type_check.__args__

        for base in getattr(type_check, "__orig_bases__", ()):
            queue.append(base)
            if base_origin := getattr(base, "__origin__", None):
                queue.append(base_origin)

    return ()


def _rebuild_type(annotation: Any, arguments: tuple[Any, ...]) -> Any:
    if not arguments:
        return annotation
    if isinstance(annotation, types.UnionType):
        result = arguments[0]
        for argument in arguments[1:]:
            result = result | argument
        return result
    copy_with = getattr(annotation, "copy_with", None)
    if callable(copy_with):
        return copy_with(arguments)
    target = get_origin(annotation) or annotation
    try:
        return target[arguments[0] if len(arguments) == 1 else arguments]
    except TypeError:
        return annotation


def resolve_typevar_bindings(
    annotation: Any,
    bindings: dict[str, Any],
    *,
    resolving: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(annotation, TypeVar):
        name = annotation.__name__
        resolved = bindings.get(name, annotation)
        if resolved is annotation or name in resolving:
            return annotation
        return resolve_typevar_bindings(resolved, bindings, resolving=resolving | {name})
    if isinstance(annotation, list):
        return [resolve_typevar_bindings(item, bindings, resolving=resolving) for item in annotation]
    if isinstance(annotation, tuple):
        return tuple(resolve_typevar_bindings(item, bindings, resolving=resolving) for item in annotation)
    arguments = get_args(annotation)
    if not arguments:
        return annotation
    resolved_arguments = tuple(
        resolve_typevar_bindings(argument, bindings, resolving=resolving) for argument in arguments
    )
    return _rebuild_type(annotation, resolved_arguments)


def _resolve_typevar_identities(annotation: Any, bindings: dict[TypeVar, Any]) -> Any:
    """Substitute one inheritance edge without conflating same-named variables."""
    if isinstance(annotation, TypeVar):
        return bindings.get(annotation, annotation)
    if isinstance(annotation, list):
        return [_resolve_typevar_identities(item, bindings) for item in annotation]
    arguments = get_args(annotation)
    if not arguments:
        return annotation
    return _rebuild_type(annotation, tuple(_resolve_typevar_identities(item, bindings) for item in arguments))


def _project_service_type(service_type: Any, contract_type: Any) -> Any | None:
    """Project an explicit registered-service hierarchy onto a generic base.

    Return the base with its inherited arguments, None for unrelated types, and
    reject conflicting inheritance paths. Unresolved variables remain variables;
    matching a closed contract or binding a decorator is a later compiler step.
    This deliberately does not infer membership from an implementation class.
    """
    service_type = normalize_type_alias(service_type)
    contract_type = normalize_type_alias(contract_type)
    contract_origin = get_origin(contract_type) or contract_type
    if not isinstance(contract_origin, type):
        return None
    results: list[Any] = []

    def visit(current: Any, path: frozenset[type]) -> None:
        origin = get_origin(current) or current
        if not isinstance(origin, type) or origin in path:
            return
        parameters = getattr(origin, "__parameters__", ())
        arguments = get_args(current) or parameters
        bindings = dict(zip(parameters, arguments, strict=True)) if parameters else {}
        if origin is contract_origin:
            projected = _rebuild_type(origin, arguments)
            if projected not in results:
                results.append(projected)
            return
        # getattr(__orig_bases__) can inherit stale bases from a grandparent.
        # Only declarations on this class describe its immediate generic edges.
        for base in vars(origin).get("__orig_bases__", origin.__bases__):
            if (get_origin(base) or base) in GenericDefinitionClasses:
                continue
            visit(_resolve_typevar_identities(base, bindings), path | {origin})

    visit(service_type, frozenset())
    if len(results) > 1:
        raise ValueError(f"Ambiguous service projection from {service_type!r} to {contract_type!r}: {results!r}")
    return results[0] if results else None
