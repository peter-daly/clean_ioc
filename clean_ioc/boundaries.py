"""Compile-time composition boundaries for Clean IoC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .components import ComponentFilter, default_component_filter
from .metadata import Tag


@dataclass(frozen=True, slots=True)
class BoundaryAlias:
    """Define the complete public identity of an exposed component."""

    service_type: Any
    name: str | None = None
    tags: tuple[Tag, ...] = ()


@dataclass(frozen=True, slots=True)
class Expose:
    """Make one local component visible, optionally through a public alias."""

    service_type: Any
    filter: ComponentFilter = default_component_filter
    alias: BoundaryAlias | None = None


@dataclass(frozen=True, slots=True)
class Use:
    """Admit one unchanged root or exposed component into a boundary."""

    source: str | None
    service_type: Any
    filter: ComponentFilter = default_component_filter

    @classmethod
    def root(
        cls,
        service_type: Any,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> Use:
        return cls(None, service_type, filter)
