"""Conservative annotation compatibility for build-time factory checks."""

from __future__ import annotations

import inspect
import types
import typing
from collections import abc
from typing import Any, ForwardRef, ParamSpec, TypeVar, TypeVarTuple, get_args, get_origin

from .generic_utils import _project_service_type
from .type_aliases import is_new_type, normalize_type_alias

# Standard collection aliases do not expose TypeVars at runtime. Only these
# well-defined variances are inferred; other unfamiliar forms remain unknown.
_VARIANCE = {
    abc.Iterable: (1,),
    abc.Iterator: (1,),
    abc.Collection: (1,),
    abc.Container: (1,),
    abc.Sequence: (1,),
    abc.Reversible: (1,),
    abc.Set: (1,),
    abc.Mapping: (0, 1),
    frozenset: (1,),
    type: (1,),
}
_INVARIANT = (list, dict, set, abc.MutableSequence, abc.MutableMapping, abc.MutableSet)
_UNIONS = (typing.Union, types.UnionType)


def _all(results: typing.Iterable[bool | None]) -> bool | None:
    captured = tuple(results)
    return False if False in captured else None if None in captured else True


def _any(results: typing.Iterable[bool | None]) -> bool | None:
    captured = tuple(results)
    return True if True in captured else None if None in captured else False


def _annotation(annotation: Any) -> Any:
    annotation = normalize_type_alias(annotation)
    while get_origin(annotation) is typing.Annotated:
        annotation = get_args(annotation)[0]
    return type(None) if annotation is None else annotation


def _unknown(annotation: Any) -> bool:
    return annotation in (Any, inspect.Signature.empty) or isinstance(
        annotation, (str, ForwardRef, TypeVar, ParamSpec, TypeVarTuple)
    )


def _invariant(actual: Any, expected: Any) -> bool | None:
    actual, expected = _annotation(actual), _annotation(expected)
    if _unknown(actual) or _unknown(expected):
        return None
    if actual == expected:
        return True
    if isinstance(actual, (list, tuple)) and isinstance(expected, type(actual)):
        if len(actual) == len(expected):
            return _all(_invariant(a, b) for a, b in zip(actual, expected, strict=True))
        return False
    if (get_origin(actual) or actual) == (get_origin(expected) or expected):
        left, right = get_args(actual), get_args(expected)
        if not left or not right:
            return None
        if len(left) == len(right):
            return _all(_invariant(a, b) for a, b in zip(left, right, strict=True))
    return False


def factory_result_compatibility(actual: Any, expected: Any) -> bool | None:
    """True for supported assignability, False for a mismatch, None if unknown.

    This checks declarations only. Structural protocols, unresolved references,
    erased generic arguments, and unsupported typing forms are not guessed.
    """
    actual, expected = _annotation(actual), _annotation(expected)
    if _unknown(actual) or _unknown(expected):
        return None
    if actual == expected or actual in (typing.Never, typing.NoReturn):
        return True
    actual_origin, expected_origin = get_origin(actual), get_origin(expected)
    if actual_origin in _UNIONS:
        return _all(factory_result_compatibility(member, expected) for member in get_args(actual))
    if expected_origin in _UNIONS:
        return _any(factory_result_compatibility(actual, member) for member in get_args(expected))
    if is_new_type(actual):
        return factory_result_compatibility(actual.__supertype__, expected)
    if is_new_type(expected):
        return False
    if actual_origin is typing.Literal:
        if expected_origin is typing.Literal:
            return all(any(type(a) is type(b) and a == b for b in get_args(expected)) for a in get_args(actual))
        return _all(factory_result_compatibility(type(value), expected) for value in get_args(actual))
    if expected_origin is typing.Literal:
        return False

    actual_class, expected_class = actual_origin or actual, expected_origin or expected
    if not isinstance(actual_class, type) or not isinstance(expected_class, type):
        return None
    # A protocol may be satisfied structurally even without nominal inheritance.
    # Runtime-checkable protocols cannot prove return-annotation assignability.
    if getattr(expected_class, "_is_protocol", False) and expected_class not in actual_class.__mro__:
        return None
    if expected_class in (float, complex) and int in actual_class.__mro__:
        return True
    if expected_class is complex and float in actual_class.__mro__:
        return True
    try:
        if not issubclass(actual_class, expected_class):
            return False
    except TypeError:
        return None
    expected_args = get_args(expected)
    if not expected_args:
        return True
    if actual_class is not expected_class:
        try:
            projected = _project_service_type(actual, expected)
        except ValueError:
            return None
        if projected is None:
            return None
        actual = projected
    actual_args = get_args(actual)
    if not actual_args:
        return None
    if expected_class is tuple:
        if len(expected_args) == 2 and expected_args[1] is Ellipsis:
            elements = actual_args[:1] if len(actual_args) == 2 and actual_args[1] is Ellipsis else actual_args
            return _all(factory_result_compatibility(item, expected_args[0]) for item in elements)
        if len(actual_args) != len(expected_args) or Ellipsis in actual_args:
            return False
        return _all(factory_result_compatibility(a, b) for a, b in zip(actual_args, expected_args, strict=True))
    if len(actual_args) != len(expected_args):
        return None
    variance = _VARIANCE.get(expected_class)
    if expected_class in _INVARIANT:
        variance = (0,) * len(expected_args)
    if variance is None:
        parameters = getattr(expected_class, "__parameters__", ())
        if len(parameters) != len(expected_args) or any(
            not isinstance(parameter, TypeVar) or getattr(parameter, "__infer_variance__", False)
            for parameter in parameters
        ):
            return None
        variance = tuple(1 if p.__covariant__ else -1 if p.__contravariant__ else 0 for p in parameters)
    return _all(
        factory_result_compatibility(a, b)
        if direction == 1
        else factory_result_compatibility(b, a)
        if direction == -1
        else _invariant(a, b)
        for a, b, direction in zip(actual_args, expected_args, variance, strict=True)
    )
