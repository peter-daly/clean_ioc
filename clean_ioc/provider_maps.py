"""Declarations for explicitly curated provider maps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from typing_extensions import TypeForm

K = TypeVar("K")
TService = TypeVar("TService")


@dataclass(frozen=True, slots=True, eq=False)
class ProviderMapGroup(Generic[K, TService]):
    """An immutable identity for registrations contributing to a provider map.

    Contributions are additive composition metadata; they do not affect regular
    service resolution, visibility, or collection selection.
    """

    name: str
    key_type: TypeForm[K]
    service_type: TypeForm[TService]
