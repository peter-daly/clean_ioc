"""Immutable specifications for registrations derived from registered sources."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ._decorator_templates import RegistrationInfo
from .components import Component, ComponentFilter, LifespanPolicy, RootPolicy, ScopePolicy, all_components
from .metadata import Tag
from .preferences import ComponentPreference
from .provider_maps import ProviderMapGroup
from .service_groups import ServiceGroup
from .tooling import DefinitionOrigin


@dataclass(frozen=True, slots=True)
class RegistrationTemplate:
    service_type: Any
    implementation_type: Any | None = None
    factory: Callable[..., Any] | None = None
    factory_specialization: object | None = None
    instance: Any = None
    lifespan: LifespanPolicy = "auto"
    scope: ScopePolicy = "current"
    name: str | None = None
    arguments: Mapping[str, Any] | None = None
    tags: Iterable[Tag] = ()
    when: ComponentFilter = all_components
    parent_precedence: int = 0
    prefer: ComponentPreference | None = None
    contributes: Mapping[ProviderMapGroup[Any, Any], Hashable] | None = None
    groups: Iterable[ServiceGroup] = ()
    root_policy: RootPolicy = "resolvable"

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments or {})))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "groups", tuple(self.groups))
        if self.contributes is not None:
            object.__setattr__(self, "contributes", MappingProxyType(dict(self.contributes)))


@dataclass(frozen=True, slots=True)
class _RegistrationTemplateDefinition:
    id: str
    for_each: Any
    template: Callable[[RegistrationInfo], RegistrationTemplate]
    source_filter: ComponentFilter
    order: int
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class _GeneratedRegistration:
    template_id: str
    source_id: str
    declaration_owner_token: str


class _RegistrationTemplateSource(Component):
    """Read static metadata without requiring the registrations being generated.

    Structural predicates retain the original source-inspection semantics by
    compiling that view on demand. The inspection callback is released when
    source selection finishes, so captured views cannot compile graphs later.
    """

    __slots__ = ("_inspect_source", "_inspected_source")

    _GRAPH_PROPERTIES = frozenset(
        {
            "requires_async",
            "manages_cleanup",
            "cache_owner",
            "cleanup_owner",
            "owner_occurrence_id",
            "ownership_reason",
            "provider_mode",
            "dependencies",
            "decorators",
            "decorated",
            "pre_configurations",
        }
    )

    def __init__(self, metadata: Component, inspect_source: Callable[[], Component]) -> None:
        super().__init__(metadata._graph, metadata.occurrence_id)
        self._inspect_source: Callable[[], Component] | None = inspect_source
        self._inspected_source: Component | None = None

    def __getattribute__(self, name: str) -> Any:
        if name in _RegistrationTemplateSource._GRAPH_PROPERTIES:
            inspected = self._inspected_source
            if inspected is None:
                inspect_source = self._inspect_source
                if inspect_source is None:
                    raise RuntimeError("Unrequested source graph properties are only available during source_filter")
                inspected = inspect_source()
                self._inspected_source = inspected
            return getattr(inspected, name)
        return super().__getattribute__(name)

    def finish_inspection(self) -> Component:
        self._inspect_source = None
        return self._inspected_source or Component(self._graph, self.occurrence_id)
