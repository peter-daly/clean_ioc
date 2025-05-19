# from __future__ import annotations
from typing import Tuple

import pytest

from clean_ioc import (
    Container,
)


@pytest.mark.asyncio
async def test_async_simple_closures():
    container = Container()

    test_name = "Bob"
    test_age = 20
    container.register(str, instance=test_name)
    container.register(int, instance=test_age)

    def test(name: str, age: int) -> Tuple[str, int]:
        return name, age

    result = container.call(test)
    assert result[0] == test_name
    assert result[1] == test_age

    result = await container.call_async(test)
    assert result[0] == test_name
    assert result[1] == test_age


@pytest.mark.asyncio
async def test_async_relational_closures():
    class A:
        @property
        def name(self) -> str:
            return self.__class__.__name__

    class B(A):
        @property
        def name(self) -> str:
            return self.__class__.__name__

    class C:
        @property
        def name(self) -> str:
            return self.__class__.__name__

    class D(C):
        @property
        def name(self) -> str:
            return self.__class__.__name__

    container = Container()
    container.register(A, B)
    container.register(C, D)

    def test(foo: A, bar: C) -> Tuple[str, str]:
        return foo.name, bar.name

    result = container.call(test)
    assert result[0] == "B"
    assert result[1] == "D"

    result = await container.call_async(test)
    assert result[0] == "B"
    assert result[1] == "D"
