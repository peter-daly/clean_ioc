"""Compile-time composition boundaries for Clean IoC."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .components import ComponentBuilder, ComponentFilter, default_component_filter


@dataclass(frozen=True, slots=True)
class Expose:
    """Make one unchanged, locally-defined component visible at the root."""

    service_type: Any
    filter: ComponentFilter = default_component_filter


@dataclass(frozen=True, slots=True)
class Use:
    """Admit one unchanged root or exposed component into an assembly."""

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


@dataclass(frozen=True, slots=True)
class Assembly:
    """An opt-in compile-time visibility boundary around an ordinary bundle."""

    name: str
    root_bundle: Callable[[ComponentBuilder], None]
    uses: tuple[Use, ...] = ()
    exposes: tuple[Expose, ...] = ()
