"""Typed handles for invoking a precompiled dependency plan on demand."""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

__all__ = ["AsyncProvider", "Provider"]

T_co = TypeVar("T_co", covariant=True)


class Provider(Protocol, Generic[T_co]):
    """A synchronous, argument-free handle to a frozen component plan."""

    def __call__(self) -> T_co: ...


class AsyncProvider(Protocol, Generic[T_co]):
    """An asynchronous, argument-free handle to a frozen component plan."""

    async def __call__(self) -> T_co: ...
