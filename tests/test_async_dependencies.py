# from __future__ import annotations
from unittest.mock import MagicMock

import pytest
from assertive import (
    assert_that,
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
    assert_that(a).matches(is_exact_type(B))


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
    assert_that(a).matches(is_exact_type(B))


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
        assert_that(mock.__aenter__).matches(was_called().once())
        assert_that(mock.__aexit__).matches(was_called().never())
        assert_that(a).matches(is_exact_type(B))

    assert_that(mock.__aenter__).matches(was_called().once())
    assert_that(mock.__aexit__).matches(was_called().once())


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
        assert_that(a_mock.__aenter__).matches(was_called().once())
        assert_that(a_mock.__aexit__).matches(was_called().never())
        assert_that(c_mock.__enter__).matches(was_called().once())
        assert_that(c_mock.__exit__).matches(was_called().never())
        assert_that(c).matches(is_exact_type(C))

    assert_that(a_mock.__aenter__).matches(was_called().once())
    assert_that(a_mock.__aexit__).matches(was_called().once())
    assert_that(c_mock.__enter__).matches(was_called().once())
    assert_that(c_mock.__exit__).matches(was_called().once())


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

    assert_that(arr).matches([10, 5])
