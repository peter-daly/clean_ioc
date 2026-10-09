"""Structural template matching used exclusively during composition compilation."""

import types
import typing
from collections.abc import Callable
from typing import Any, TypeVar, get_args, get_origin

from .type_aliases import is_new_type


class PatternError(ValueError):
    def __init__(self, message: str, code: str = "pattern-unsupported-form"):
        super().__init__(message)
        self.code = code


def variables(annotation: Any) -> tuple[TypeVar, ...]:
    """Keep identity until the explicit bridge to name-based factory metadata."""
    found: dict[TypeVar, None] = {}

    def visit(value: Any) -> None:
        if isinstance(value, TypeVar):
            found[value] = None
        elif isinstance(value, (tuple, list)):
            for item in value:
                visit(item)
        else:
            for item in get_args(value):
                visit(item)

    visit(annotation)
    return tuple(found)


def _domain(variable: TypeVar) -> tuple[type, ...]:
    return variable.__constraints__ or ((variable.__bound__,) if variable.__bound__ is not None else (object,))


def _validate_domain(variable: TypeVar) -> None:
    for bound in _domain(variable):
        if not isinstance(bound, type) or bound is Any or getattr(bound, "_is_protocol", False):
            raise PatternError("Pattern TypeVar bounds and constraints must be ordinary, unparameterized classes")


def _safe_subclass(candidate: type, bound: type) -> bool:
    try:
        return issubclass(candidate, bound)
    except Exception as error:
        raise PatternError("A pattern TypeVar bound could not be checked safely") from error


def equivalent(left: Any, right: Any) -> bool:
    """Compare type structure without conflating distinct terminal identities."""
    if left is right:
        return True
    origin = get_origin(left)
    if origin is None or origin is not get_origin(right):
        return False
    left_args, right_args = get_args(left), get_args(right)
    return len(left_args) == len(right_args) and all(
        equivalent(a, b) for a, b in zip(left_args, right_args, strict=True)
    )


def validate_structure(value: Any, *, symbolic: bool = True) -> None:
    if isinstance(value, TypeVar):
        if not symbolic:
            raise PatternError("Pattern requests must be closed", "pattern-incompatible-binding")
        _validate_domain(value)
        return
    if is_new_type(value):
        return
    origin = get_origin(value)
    if origin is not None:
        if (
            not isinstance(origin, type)
            or origin in (typing.Union, types.UnionType, Callable, typing.Annotated)
            or getattr(origin, "_is_protocol", False)
        ):
            raise PatternError("Patterns support class origins and ordered type arguments only")
        for argument in get_args(value):
            validate_structure(argument, symbolic=symbolic)
        return
    if not isinstance(value, type) or value is Any or getattr(value, "__parameters__", ()):
        raise PatternError("Patterns require concrete classes, nominal NewTypes, or TypeVars at terminal positions")


def validate_pattern(pattern: Any) -> None:
    if get_origin(pattern) is None or not variables(pattern):
        raise PatternError(
            "A registration pattern must be a parameterized class containing a TypeVar", "pattern-invalid"
        )
    validate_structure(pattern)
    names: dict[str, TypeVar] = {}
    for variable in variables(pattern):
        previous = names.setdefault(variable.__name__, variable)
        if previous is not variable:
            raise PatternError("Distinct pattern TypeVars share a name", "pattern-incompatible-binding")


def _accepts(variable: TypeVar, value: Any) -> bool:
    domain = _domain(variable)
    if isinstance(value, TypeVar):
        return variable is value or all(
            any(_safe_subclass(bound, allowed) for allowed in domain) for bound in _domain(value)
        )
    if len(domain) == 1 and domain[0] is object:
        return True
    target = get_origin(value) or value
    return isinstance(target, type) and any(_safe_subclass(target, allowed) for allowed in domain)


def match(pattern: Any, request: Any) -> dict[TypeVar, Any] | None:
    """Also implements subsumption when the request is another validated pattern."""
    bindings: dict[TypeVar, Any] = {}

    def visit(template: Any, concrete: Any) -> bool:
        if isinstance(template, TypeVar):
            if not _accepts(template, concrete):
                return False
            if template in bindings:
                return equivalent(bindings[template], concrete)
            bindings[template] = concrete
            return True
        origin = get_origin(template)
        if origin is None:
            return template is concrete
        arguments, concrete_arguments = get_args(template), get_args(concrete)
        return (
            origin is get_origin(concrete)
            and len(arguments) == len(concrete_arguments)
            and all(visit(left, right) for left, right in zip(arguments, concrete_arguments, strict=True))
        )

    return bindings if visit(pattern, request) else None


def more_specific(left: Any, right: Any) -> bool:
    return match(right, left) is not None and match(left, right) is None


def factory_bindings(pattern: Any, request: Any, annotations: tuple[Any, ...]) -> dict[str, Any]:
    bound = match(pattern, request)
    if bound is None:
        raise PatternError("The pattern does not match the closed request", "pattern-incompatible-binding")
    identities = {variable.__name__: variable for variable in bound}
    for annotation in annotations:
        for variable in variables(annotation):
            if variable.__name__ in identities and identities[variable.__name__] is not variable:
                raise PatternError("Distinct factory and pattern TypeVars share a name", "pattern-incompatible-binding")
            if variable not in bound:
                raise PatternError(
                    "Factory TypeVar is not bound by its registration pattern", "pattern-incompatible-binding"
                )
    return {variable.__name__: value for variable, value in bound.items()}


def size(value: Any) -> int:
    return 1 + sum(size(argument) for argument in get_args(value))
