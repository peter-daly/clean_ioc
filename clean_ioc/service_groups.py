"""Identity declarations for explicit service membership."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from typing_extensions import TypeForm


@dataclass(frozen=True, slots=True, eq=False)
class ServiceGroup:
    """An immutable identity for registrations under a service contract.

    Membership is stored on each registration, never on this reusable declaration.
    """

    name: str
    service_type: TypeForm[Any] = field(kw_only=True)
