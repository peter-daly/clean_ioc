"""Private normalization for transparent PEP 695 and backported type aliases."""

from __future__ import annotations

import sys
import types
import typing
from collections.abc import Mapping
from typing import Any, ForwardRef, TypeVar, get_args, get_origin

from typing_extensions import NoDefault as ExtensionsNoDefault
from typing_extensions import TypeAliasType as ExtensionsTypeAliasType
from typing_extensions import evaluate_forward_ref

from .providers import AsyncProvider, Provider

_MAX_ALIAS_EXPANSIONS = 100
_NO_DEFAULT = object()


class TypeAliasNormalizationError(ValueError):
    """A safe, classified failure while expanding a real type alias."""

    def __init__(self, code: str, alias: Any, chain: tuple[Any, ...] = ()) -> None:
        self.code = code
        self.alias = alias
        self.chain = chain
        labels = " -> ".join(alias_label(item) for item in (*chain, alias))
        super().__init__(f"Could not normalize type alias {labels}")


def _alias_classes() -> tuple[type, ...]:
    native = getattr(typing, "TypeAliasType", None)
    values = (ExtensionsTypeAliasType,) if native is None else (native, ExtensionsTypeAliasType)
    return tuple(dict.fromkeys(values))


_TYPE_ALIAS_CLASSES = _alias_classes()


def is_type_alias(value: Any) -> bool:
    """Recognize only native/backported aliases and their applications."""

    if isinstance(value, _TYPE_ALIAS_CLASSES):
        return True
    return isinstance(get_origin(value), _TYPE_ALIAS_CLASSES)


def is_new_type(value: Any) -> bool:
    """Recognize nominal ``NewType`` declarations without following them."""

    new_type = getattr(typing, "NewType", None)
    return (
        isinstance(value, new_type)
        if isinstance(new_type, type)
        else callable(value) and hasattr(value, "__supertype__")
    )


def alias_label(value: Any) -> str:
    alias = get_origin(value) if isinstance(get_origin(value), _TYPE_ALIAS_CLASSES) else value
    module = getattr(alias, "__module__", None)
    name = getattr(alias, "__qualname__", None) or getattr(alias, "__name__", None) or "<type-alias>"
    prefix = f"{module}." if module and module != "builtins" else ""
    arguments = get_args(value)
    if not arguments:
        return f"{prefix}{name}"
    return f"{prefix}{name}[{', '.join(_safe_type_label(item) for item in arguments)}]"


def _safe_type_label(value: Any) -> str:
    if is_type_alias(value):
        return alias_label(value)
    module = getattr(value, "__module__", None)
    name = getattr(value, "__qualname__", None) or getattr(value, "__name__", None)
    if name:
        return f"{module}.{name}" if module and module != "builtins" else name
    origin = get_origin(value)
    if origin is not None:
        return _safe_type_label(origin)
    return "<type>"


def normalize_type_alias(value: Any) -> Any:
    """Return the canonical type expression for *value*.

    Ordinary values use a very small fast path. Alias evaluation failures are
    never memoized, so a repaired defining module can be retried by a builder.
    """

    if isinstance(value, type) or not _contains_alias(value):
        return value
    return _normalize(value, {}, (), 0)


def _contains_alias(value: Any) -> bool:
    if isinstance(value, type):
        return False
    if is_type_alias(value):
        return True
    origin = get_origin(value)
    if origin is typing.Literal:
        return False
    arguments = get_args(value)
    # The two Mapping spellings have distinct runtime identities. Canonicalize
    # declared provider maps without changing ordinary eager Mapping keys.
    if origin is Mapping and len(arguments) == 2 and get_origin(arguments[1]) in (Provider, AsyncProvider):
        if not isinstance(value, types.GenericAlias):
            return True
    if origin is typing.Annotated:
        arguments = arguments[:1]
    return any(_contains_alias(item) for item in arguments if not isinstance(item, (list, tuple))) or any(
        _contains_alias(nested) for item in arguments if isinstance(item, (list, tuple)) for nested in item
    )


def _normalize(
    value: Any,
    bindings: dict[TypeVar, Any],
    active: tuple[tuple[Any, tuple[Any, ...]], ...],
    expansions: int,
) -> Any:
    if isinstance(value, TypeVar):
        replacement = bindings.get(value, value)
        return value if replacement is value else _normalize(replacement, bindings, active, expansions)

    alias = value if isinstance(value, _TYPE_ALIAS_CLASSES) else get_origin(value)
    if isinstance(alias, _TYPE_ALIAS_CLASSES):
        arguments = get_args(value)
        parameters = tuple(getattr(alias, "__type_params__", ()) or getattr(alias, "__parameters__", ()))
        if expansions >= _MAX_ALIAS_EXPANSIONS:
            raise TypeAliasNormalizationError("type-alias-recursive", value, tuple(item[0] for item in active))
        if arguments and len(arguments) > len(parameters):
            raise TypeAliasNormalizationError("type-alias-arguments", value)
        supplied = [_normalize(argument, bindings, active, expansions) for argument in arguments]
        for parameter in parameters[len(supplied) :]:
            default = getattr(parameter, "__default__", _NO_DEFAULT)
            no_default = getattr(typing, "NoDefault", _NO_DEFAULT)
            if default is _NO_DEFAULT or default is no_default or default is ExtensionsNoDefault:
                if arguments:
                    raise TypeAliasNormalizationError("type-alias-arguments", value)
                supplied.append(parameter)
            else:
                supplied.append(default)
        unsupported = tuple(
            parameter for parameter in parameters if type(parameter).__name__ in ("ParamSpec", "TypeVarTuple")
        )
        if unsupported:
            raise TypeAliasNormalizationError("type-alias-unsupported-parameter", value)
        local_bindings = dict(bindings)
        local_bindings.update(zip(parameters, supplied, strict=True))
        token = (alias, tuple(_structural_token(item) for item in supplied))
        if token in active:
            raise TypeAliasNormalizationError("type-alias-recursive", value, tuple(item[0] for item in active))
        try:
            target = alias.__value__
            target = _evaluate_forward_refs(target, alias)
        except Exception as error:
            raise TypeAliasNormalizationError("type-alias-unresolved", value) from error
        result = _normalize(target, local_bindings, (*active, token), expansions + 1)
        if not _is_supported_type_expression(result):
            raise TypeAliasNormalizationError("type-alias-invalid", value)
        return result

    origin = get_origin(value)
    if origin is None or origin is typing.Literal:
        return value
    arguments = get_args(value)
    if origin is typing.Annotated:
        normalized = (_normalize(arguments[0], bindings, active, expansions), *arguments[1:])
    else:
        normalized = tuple(_normalize_argument(item, bindings, active, expansions) for item in arguments)
    if origin is Mapping and len(normalized) == 2 and get_origin(normalized[1]) in (Provider, AsyncProvider):
        return Mapping[normalized[0], normalized[1]]
    if normalized == arguments:
        return value
    return _rebuild(value, normalized)


def _normalize_argument(value: Any, bindings: dict[TypeVar, Any], active, expansions: int) -> Any:
    if isinstance(value, list):
        return [_normalize(item, bindings, active, expansions) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize(item, bindings, active, expansions) for item in value)
    return _normalize(value, bindings, active, expansions)


def _evaluate_forward_refs(value: Any, alias: Any) -> Any:
    module = sys.modules.get(getattr(alias, "__module__", ""))
    namespace = {} if module is None else dict(vars(module))
    parameters = tuple(getattr(alias, "__type_params__", ()) or getattr(alias, "__parameters__", ()))
    for parameter in parameters:
        namespace.setdefault(parameter.__name__, parameter)
    return _evaluate_forward_value(value, namespace, parameters)


def _evaluate_forward_value(value: Any, namespace: dict[str, Any], parameters: tuple[Any, ...]) -> Any:
    if isinstance(value, str):
        value = ForwardRef(value)
    if isinstance(value, ForwardRef):
        return evaluate_forward_ref(
            value,
            globals=namespace,
            locals=namespace,
            type_params=parameters,
        )
    origin = get_origin(value)
    if origin is None or origin is typing.Literal:
        return value
    arguments = get_args(value)
    if origin is typing.Annotated:
        evaluated = (_evaluate_forward_value(arguments[0], namespace, parameters), *arguments[1:])
    else:
        evaluated = tuple(
            _evaluate_forward_value(item, namespace, parameters)
            if not isinstance(item, (list, tuple))
            else type(item)(_evaluate_forward_value(nested, namespace, parameters) for nested in item)
            for item in arguments
        )
    return value if evaluated == arguments else _rebuild(value, evaluated)


def _rebuild(value: Any, arguments: tuple[Any, ...]) -> Any:
    if get_origin(value) is typing.Annotated:
        return typing.Annotated[arguments[0], *arguments[1:]]
    if isinstance(value, types.UnionType):
        result = arguments[0]
        for argument in arguments[1:]:
            result = result | argument
        return result
    copy_with = getattr(value, "copy_with", None)
    if callable(copy_with):
        try:
            return copy_with(arguments)
        except (AssertionError, TypeError):
            pass
    origin = get_origin(value) or value
    try:
        return origin[arguments[0] if len(arguments) == 1 else arguments]
    except (AttributeError, TypeError) as error:
        raise TypeAliasNormalizationError("type-alias-invalid", value) from error


def _is_supported_type_expression(value: Any) -> bool:
    return (
        value is Any
        or value is None
        or isinstance(value, (type, TypeVar))
        or is_new_type(value)
        or get_origin(value) is not None
    )


def _structural_token(value: Any) -> Any:
    origin = get_origin(value)
    if origin is not None:
        return (id(origin), tuple(_structural_token(item) for item in get_args(value)))
    return id(value)
