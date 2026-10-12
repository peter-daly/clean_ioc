"""Registration-based target selection shared by decorator-template policies."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeVar, get_args, get_origin

from .generic_utils import (
    _bind_typevar_identities,
    _project_service_type,
    _typevar_identities,
)
from .service_groups import DerivedServices, ServiceGroup
from .type_aliases import normalize_type_alias


class _ServiceTargetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _ServiceTarget:
    registration_id: str
    requested_service_type: Any
    registered_service_type: Any
    projected_contract: Any
    # Parameters declared by the contract's origin, independent of selector vars.
    bindings: Mapping[TypeVar, Any]
    declaration_bindings: Mapping[TypeVar, Any]


def _select_service_target(
    selector: ServiceGroup | DerivedServices,
    *,
    registration_id: str,
    registered_service_type: Any,
    requested_service_type: Any,
    groups: Iterable[ServiceGroup],
) -> _ServiceTarget | None:
    """Select one already available definition/request; never enumerate services.

    The caller retains visibility, ordering and occurrence identity. Membership
    checks precede projection, so a nonmember cannot cause projection errors.
    The returned request is untouched, including an alias supplied by the caller.
    """
    if not isinstance(selector, (ServiceGroup, DerivedServices)):
        raise TypeError("A service target must be ServiceGroup or DerivedServices")
    if isinstance(selector, ServiceGroup) and selector not in groups:
        return None
    contract = normalize_type_alias(selector.service_type)
    registered = normalize_type_alias(registered_service_type)
    declared_projection = _project_service_type(registered, contract)
    if declared_projection is None:
        if isinstance(selector, DerivedServices):
            return None
        raise _ServiceTargetError(f"Registered service {registered!r} does not derive from {contract!r}")

    # A class registration may also have an implementation lookup key. Establish
    # membership from its declared service above, then recover that service's
    # concrete arguments, without replacing the actual wrapped request key.
    request = normalize_type_alias(requested_service_type)
    if (get_origin(request) or request) is (get_origin(registered) or registered):
        actual_service = request
    elif not _typevar_identities(registered):
        # A closed declaration is authoritative even when resolution uses an
        # implementation lookup key with a different generic specialization.
        actual_service = registered
    else:
        actual_service = _project_service_type(request, registered)
        if actual_service is None:
            actual_service = registered
    declared_service = _project_service_type(registered, registered)
    if get_args(declared_service) and _bind_typevar_identities(declared_service, actual_service) is None:
        raise _ServiceTargetError(f"Request {request!r} conflicts with registered service {registered!r}")
    projected = _project_service_type(actual_service, contract)
    if projected is None or _typevar_identities(projected):
        raise _ServiceTargetError(f"Unresolved contract projection from {request!r} to {contract!r}")
    declaration_bindings = _bind_typevar_identities(contract, projected) if get_args(contract) else {}
    if declaration_bindings is None:
        if isinstance(selector, DerivedServices):
            return None
        raise _ServiceTargetError(f"Projected service {projected!r} conflicts with contract {contract!r}")
    origin = get_origin(contract) or contract
    parameters = getattr(origin, "__parameters__", ())
    bindings = dict(zip(parameters, get_args(projected), strict=True)) if parameters else {}
    return _ServiceTarget(
        registration_id=registration_id,
        requested_service_type=requested_service_type,
        registered_service_type=registered,
        projected_contract=projected,
        bindings=MappingProxyType(bindings),
        declaration_bindings=MappingProxyType(declaration_bindings),
    )
