# from __future__ import annotations
from unittest.mock import MagicMock

import pytest
from assertive import (
    is_exact_type,
    was_called,
)

from clean_ioc import (
    Container,
)


@pytest.mark.asyncio
async def test_simple_implementation_registration():
    class A:
        pass

    class B(A):
        pass

    container = Container()
    container.register(A, B)

    a = await container.resolve_async(A)
    assert a == is_exact_type(B)


@pytest.mark.asyncio
async def test_async_factory_registration():
    class A:
        pass

    class B(A):
        pass

    async def a_fac():
        return B()

    container = Container()
    container.register(A, factory=a_fac)

    a = await container.resolve_async(A)
    assert a == is_exact_type(B)


@pytest.mark.asyncio
async def test_async_factory_generator_registration():
    mock = MagicMock()

    class A:
        pass

    class B(A):
        pass

    async def a_fac():
        async with mock:
            yield B()

    container = Container()
    container.register(A, factory=a_fac)

    async with container.new_scope() as scope:
        a = await scope.resolve_async(A)
        assert mock.__aenter__ == was_called().once()
        assert mock.__aexit__ == was_called().never()
        assert a == is_exact_type(B)

    assert mock.__aenter__ == was_called().once()
    assert mock.__aexit__ == was_called().once()


@pytest.mark.asyncio
async def test_async_factory_generator_registration_with_dependencies():
    a_mock = MagicMock()
    c_mock = MagicMock()

    class A:
        pass

    class B(A):
        pass

    class C:
        pass

    async def a_fac():
        async with a_mock:
            yield B()

    async def c_fac(a: A):
        with c_mock:
            yield C()

    container = Container()
    container.register(A, factory=a_fac)
    container.register(C, factory=c_fac)

    async with container.new_scope() as scope:
        c = await scope.resolve_async(C)
        assert a_mock.__aenter__ == was_called().once()
        assert a_mock.__aexit__ == was_called().never()
        assert c_mock.__enter__ == was_called().once()
        assert c_mock.__exit__ == was_called().never()
        assert c == is_exact_type(C)

    assert a_mock.__aenter__ == was_called().once()
    assert a_mock.__aexit__ == was_called().once()
    assert c_mock.__enter__ == was_called().once()
    assert c_mock.__exit__ == was_called().once()


@pytest.mark.asyncio
async def test_async_returns_a_list():
    async def fac1():
        return 5

    async def fac2():
        return 10

    container = Container()
    container.register(int, factory=fac1)
    container.register(int, factory=fac2)

    arr = await container.resolve_async(list[int])

    assert arr == [10, 5]
