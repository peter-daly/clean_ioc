"""Immutable template declarations and expansion records (internal until activation)."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar, get_args, get_origin

from .components import Component, ComponentFilter, all_components
from .generic_utils import _project_service_type
from .metadata import Tag
from .service_groups import DerivedServices, ServiceGroup
from .tooling import DefinitionOrigin
from .type_aliases import normalize_type_alias

if TYPE_CHECKING:
    from .container import _Blueprint


@dataclass(frozen=True, slots=True)
class RegistrationInfo:
    id: str
    service_type: Any
    implementation_type: Any | None
    name: str | None = None
    tags: tuple[Tag, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))

    def implementation_bindings(self, base_type: Any) -> Mapping[TypeVar, Any] | None:
        """Project static evidence, retaining the declaring TypeVar identities."""
        if self.implementation_type is None:
            return None
        base_type = normalize_type_alias(base_type)
        projected = _project_service_type(self.implementation_type, base_type)
        if projected is None:
            return None
        origin = get_origin(base_type) or base_type
        parameters = getattr(origin, "__parameters__", ())
        arguments = get_args(projected) or parameters
        return MappingProxyType(dict(zip(parameters, arguments)))


@dataclass(frozen=True, slots=True)
class DecoratorTemplate:
    services: ServiceGroup | DerivedServices
    decorator_type: Any
    decorated_arg: str | None = None
    arguments: Mapping[str, Any] | None = None
    when: ComponentFilter = all_components
    position: int = 0
    name: str | None = None
    tags: Iterable[Tag] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.services, (ServiceGroup, DerivedServices)):
            raise TypeError("DecoratorTemplate.services requires ServiceGroup or DerivedServices")
        if not callable(self.when):
            raise TypeError("DecoratorTemplate.when must be callable")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments or {})))
        object.__setattr__(self, "tags", tuple(self.tags))


@dataclass(frozen=True, slots=True)
class _DecoratorTemplateDefinition:
    id: str
    for_each: Any
    template: Callable[[RegistrationInfo], DecoratorTemplate]
    source_filter: ComponentFilter
    order: int
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class _GeneratedDecoratorDefinition:
    id: str
    declaration: _DecoratorTemplateDefinition
    source: RegistrationInfo
    specification: DecoratorTemplate
    source_order: int
    declaration_area: str | None
    declaration_owner_token: str
    source_area: str | None
    source_owner_token: str

    @property
    def order(self) -> int:
        return self.declaration.order


@dataclass(frozen=True, slots=True)
class _TemplateSourceSelection:
    template_id: str
    source: RegistrationInfo
    component: Component
    selected: bool
    source_order: int
    declaration_area: str | None
    source_area: str | None
    generated_id: str | None


@dataclass(frozen=True, slots=True)
class _TemplateExpansion:
    # Original declarations remain in this prepared snapshot. Candidates are
    # deliberately separate: M05 must compile their selectors before publication.
    blueprint: _Blueprint
    candidates: tuple[_GeneratedDecoratorDefinition, ...] = ()
    selections: tuple[_TemplateSourceSelection, ...] = ()
    build_args: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "build_args", MappingProxyType(dict(self.build_args)))
