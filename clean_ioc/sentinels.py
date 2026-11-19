"""Sentinels for distinguishing omitted configuration from explicit values."""

from enum import Enum
from typing import Final

__all__ = ["Undefined"]


class _Undefined(Enum):
    VALUE = "Undefined"

    def __repr__(self) -> str:
        return "Undefined"


Undefined: Final = _Undefined.VALUE
"""An omitted configuration value, distinct from ``None``."""
