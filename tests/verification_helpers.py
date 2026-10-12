"""Narrow optional captured facts where a fixture requires their presence."""

from typing import TypeVar

T = TypeVar("T")


def present(value: T | None) -> T:
    assert value is not None
    return value
