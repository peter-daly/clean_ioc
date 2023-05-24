from typing import TypeVar  # type: ignore
from typing import Generic, Protocol

from clean_ioc.typing_utils import (
    get_subclasses,
    get_typevar_to_type_mapping,
    is_open_generic_type,
)


class A:
    pass


class B(A):
    pass


class C(B):
    pass


T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")


class GBase(Generic[T1]):
    pass


class GChild(GBase[int]):
    pass


class HBase(Generic[T1, T2]):
    pass


class HChild1(HBase[int, T2], Generic[T2]):
    pass


class JBase(Protocol[T1]):
    def get_item(self, t: T1) -> T1:
        ...


class JChild(JBase[int]):
    def get_item(self, t: int):
        return t * 2


def test_subclasses():
    x = get_subclasses(A)
    assert x == [B, C]


def test_typevar_type_mapping_with_protocol():
    m = get_typevar_to_type_mapping(JChild)
    assert m[T1] == int


def test_is_open_generic():
    assert is_open_generic_type(HBase) == True
    assert is_open_generic_type(HBase[T1, T2]) == True
    assert is_open_generic_type(HBase[T1, int]) == True
    assert is_open_generic_type(HBase[int, T2]) == True
    assert is_open_generic_type(HBase[int, int]) == False


def test_get_typevar_to_type_mapping():
    m1 = get_typevar_to_type_mapping(HBase[int, str])

    assert m1[T1] == int
    assert m1[T2] == str

    m2 = get_typevar_to_type_mapping(HBase)

    assert m2[T1] == T1
    assert m2[T2] == T2

    m3 = get_typevar_to_type_mapping(GChild)

    assert m3[T1] == int

    m4 = get_typevar_to_type_mapping(HBase[int, int])

    assert m4[T1] == int
    assert m4[T2] == int

    m5 = get_typevar_to_type_mapping(HChild1[str])

    assert m5[T1] == int
    assert m5[T2] == str

    m6 = get_typevar_to_type_mapping(int)
    assert m6 == {}
