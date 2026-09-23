import types
from collections import deque
from collections.abc import Callable
from itertools import combinations
from typing import (
    Any,
    Generic,
    ParamSpec,
    Protocol,
    TypeVar,
    TypeVarTuple,
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
    if isinstance(annotation, tuple):
        return tuple(_resolve_typevar_identities(item, bindings) for item in annotation)
    arguments = get_args(annotation)
    if not arguments:
        return annotation
    resolved = tuple(_resolve_typevar_identities(item, bindings) for item in arguments)
    if get_origin(annotation) is Callable and isinstance(resolved[0], list):
        copy_with = getattr(annotation, "copy_with", None)
        if callable(copy_with):
            # typing.Callable stores flattened arguments internally, whereas
            # get_args exposes its parameter list as a nested sequence.
            return copy_with((*resolved[0], *resolved[1:]))
    return _rebuild_type(annotation, resolved)


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
        if not isinstance(origin, type) or origin in path or contract_origin not in origin.__mro__:
            return
        parameters = getattr(origin, "__parameters__", ())
        if any(not isinstance(parameter, TypeVar) for parameter in parameters):
            raise ValueError("Service projection supports TypeVar parameters only, not ParamSpec or TypeVarTuple")
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


class _TypeBindingError(ValueError):
    """An ambiguous or unresolved identity-based generic binding."""


def _typevar_identities(annotation: Any) -> tuple[TypeVar, ...]:
    found: dict[TypeVar, None] = {}

    def visit(value: Any) -> None:
        if isinstance(value, TypeVar):
            found[value] = None
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        else:
            for item in get_args(value) or getattr(value, "__parameters__", ()):
                visit(item)

    visit(annotation)
    return tuple(found)


def _unsupported_type_parameters(annotation: Any) -> bool:
    if isinstance(annotation, (ParamSpec, TypeVarTuple)) or isinstance(get_origin(annotation), ParamSpec):
        return True
    if isinstance(annotation, (list, tuple)):
        return any(_unsupported_type_parameters(item) for item in annotation)
    return any(
        _unsupported_type_parameters(item) for item in get_args(annotation) or getattr(annotation, "__parameters__", ())
    )


def _bind_typevar_identities(pattern: Any, concrete: Any) -> dict[TypeVar, Any] | None:
    """Match a type expression against a closed type, retaining declaration identity.

    Union members are unordered and matched as disjoint partitions. More than
    one consistent assignment is an error rather than an arbitrary choice;
    inference through union collapse is unsupported. None denotes a mismatch.
    This is intentionally separate from the legacy name-based factory bridge.
    """
    pattern = normalize_type_alias(pattern)
    concrete = normalize_type_alias(concrete)
    if _unsupported_type_parameters(pattern) or _unsupported_type_parameters(concrete):
        raise _TypeBindingError("Type bindings support TypeVar parameters only, not ParamSpec or TypeVarTuple")
    if _typevar_identities(concrete):
        raise _TypeBindingError(f"Unresolved target type {concrete!r}")

    unsupported_branches: list[str] = []

    def visit(left: Any, right: Any, bindings: dict[TypeVar, Any]) -> list[dict[TypeVar, Any]]:
        if isinstance(left, TypeVar):
            if left in bindings:
                return [bindings] if bindings[left] == right else []
            domain = left.__constraints__ or ((left.__bound__,) if left.__bound__ is not None else ())
            if domain:
                candidate = get_origin(right) or right
                try:
                    allowed = any(isinstance(candidate, type) and issubclass(candidate, bound) for bound in domain)
                except TypeError as error:
                    raise _TypeBindingError(f"Cannot check TypeVar domain for {left!r}") from error
                if not allowed:
                    return []
            return [{**bindings, left: right}]
        if left == right:
            return [bindings]
        if isinstance(left, (list, tuple)):
            if type(left) is not type(right) or len(left) != len(right):
                return []
            return sequence(tuple(left), tuple(right), [bindings])
        left_origin, right_origin = get_origin(left), get_origin(right)
        union_origins = (Union, types.UnionType)
        if left_origin in union_origins and right_origin not in union_origins and _typevar_identities(left):
            if any(not _typevar_identities(member) and member != right for member in get_args(left)):
                return []
            unsupported_branches.append(f"Cannot infer TypeVar bindings from collapsed union {left!r} to {right!r}")
            return []
        if left_origin in union_origins and right_origin in union_origins:
            left_args, right_args = get_args(left), get_args(right)
            if len(left_args) > len(right_args):
                return []

            def union_members(remaining: tuple[Any, ...], available: tuple[Any, ...], state: dict[TypeVar, Any]):
                if not remaining:
                    return [state] if not available else []
                results = []
                # A variable can absorb several union members. Match disjoint
                # partitions, so fixed members are not redundantly re-inferred
                # into a variable. Retain all assignments until later repeated
                # variables have had a chance to disambiguate them.
                maximum = len(available) - len(remaining) + 1 if isinstance(remaining[0], TypeVar) else 1
                for size in range(1, maximum + 1):
                    for indices in combinations(range(len(available)), size):
                        members = tuple(available[index] for index in indices)
                        candidate = members[0] if size == 1 else Union[members]
                        rest = tuple(item for index, item in enumerate(available) if index not in indices)
                        for updated in visit(remaining[0], candidate, state):
                            results.extend(union_members(remaining[1:], rest, updated))
                return results

            return union_members(left_args, right_args, bindings)
        if left_origin is None or left_origin != right_origin:
            return []
        return sequence(get_args(left), get_args(right), [bindings])

    def sequence(left: tuple[Any, ...], right: tuple[Any, ...], states: list[dict[TypeVar, Any]]):
        if len(left) != len(right):
            return []
        for pattern_item, concrete_item in zip(left, right, strict=True):
            states = [updated for state in states for updated in visit(pattern_item, concrete_item, state)]
        return states

    results: list[dict[TypeVar, Any]] = []
    for result in visit(pattern, concrete, {}):
        if result not in results:
            results.append(result)
    if unsupported_branches:
        raise _TypeBindingError(unsupported_branches[0])
    if len(results) > 1:
        raise _TypeBindingError(f"Ambiguous TypeVar bindings from {pattern!r} to {concrete!r}")
    return results[0] if results else None
