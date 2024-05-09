from typing import (
    Generic,
    Protocol,
    TypeVar,  # type: ignore
)

from assertive import assert_that

from clean_ioc.typing_utils import (
    GenericTypeMap,
    get_subclasses,
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
    def get_item(self, t: T1) -> T1: ...


class JChild(JBase[int]):
    def get_item(self, t: int):
        return t * 2


def test_subclasses():
    x = get_subclasses(A)
    assert_that(x).matches([B, C])


def test_typevar_type_mapping_with_protocol():
    m = GenericTypeMap.from_type(JChild)
    assert_that(m[T1]).matches(int)


def test_is_open_generic():
    assert_that(is_open_generic_type(HBase)).matches(True)
    assert_that(is_open_generic_type(HBase[T1, T2])).matches(True)  # type: ignore
    assert_that(is_open_generic_type(HBase[T1, int])).matches(True)  # type: ignore
    assert_that(is_open_generic_type(HBase[int, T2])).matches(True)  # type: ignore
    assert_that(is_open_generic_type(HBase[int, int])).matches(False)


def test_get_typevar_to_type_mapping():
    m1 = GenericTypeMap.from_type(HBase[int, str])

    assert_that(m1[T1]).matches(int)
    assert_that(m1[T2]).matches(str)

    m2 = GenericTypeMap.from_type(HBase)

    assert_that(m2[T1]).matches(T1)
    assert_that(m2[T2]).matches(T2)

    m3 = GenericTypeMap.from_type(GChild)

    assert_that(m3[T1]).matches(int)

    m4 = GenericTypeMap.from_type(HBase[int, int])

    assert_that(m4[T1]).matches(int)
    assert_that(m4[T2]).matches(int)

    m5 = GenericTypeMap.from_type(HChild1[str])

    assert_that(m5[T1]).matches(int)
    assert_that(m5[T2]).matches(str)

    m6 = GenericTypeMap.from_type(int)
    assert_that(m6).matches(GenericTypeMap())


# def test_type_maps_can_work_with_3_12_generics():
#     class NewGeneric[X, Y]:
#         pass

#     class Impl(NewGeneric[int, str]):
#         pass

#     m1 = GenericTypeMap.from_type(Impl)
#     assert_that(m1["X"]).matches(int)
#     assert_that(m1["Y"]).matches(str)
