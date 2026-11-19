"""Typed handles for invoking a precompiled dependency plan on demand."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Generic, Protocol, TypeVar

__all__ = ["AsyncManagedProvider", "AsyncProvider", "ManagedProvider", "Provider"]

T_co = TypeVar("T_co", covariant=True)


class Provider(Protocol, Generic[T_co]):
    """A synchronous, argument-free handle to a frozen component plan."""

    def __call__(self) -> T_co: ...


class AsyncProvider(Protocol, Generic[T_co]):
    """An asynchronous, argument-free handle to a frozen component plan."""

    async def __call__(self) -> T_co: ...


class ManagedProvider(Protocol, Generic[T_co]):
    """Create a single-use context manager acquiring a frozen plan in a fresh scope."""

    def __call__(self) -> AbstractContextManager[T_co]: ...


class AsyncManagedProvider(Protocol, Generic[T_co]):
    """Create an async context manager; acquisition happens on async entry."""

    def __call__(self) -> AbstractAsyncContextManager[T_co]: ...
