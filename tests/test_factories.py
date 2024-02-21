# from __future__ import annotations
from assertive import assert_that, is_exact_type, is_same_instance_as

from clean_ioc import (
    Container,
    Registration,
)
from clean_ioc.factories import create_type_mapping, use_registered
from clean_ioc.registration_filters import with_name


def test_simple_use_registered():
    class A:
        pass

    class B:
        pass

    class C(A, B):
        pass

    class D(C):
        pass

    d = D()

    container = Container()
    container.register(C, instance=d)
    container.register(A, factory=use_registered(C))
    container.register(B, factory=use_registered(C))

    a = container.resolve(A)
    b = container.resolve(B)

    assert_that(a).matches(is_exact_type(D))
    assert_that(b).matches(is_exact_type(D))

    assert_that(a).matches(is_same_instance_as(d))
    assert_that(b).matches(is_same_instance_as(d))


def test_use_registered_with_filters():
    class A:
        pass

    class B:
        pass

    class C(A, B):
        pass

    c1 = C()
    c2 = C()

    container = Container()
    container.register(C, instance=c1, name="C1")
    container.register(C, instance=c2, name="C2")
    container.register(A, factory=use_registered(C, with_name("C1")))
    container.register(B, factory=use_registered(C, with_name("C2")))

    a = container.resolve(A)
    b = container.resolve(B)

    assert_that(a).matches(is_same_instance_as(c1))
    assert_that(b).matches(is_same_instance_as(c2))


def test_create_type_mapping():
    class A:
        __KEY__ = None
        pass

    class B(A):
        __KEY__ = "B"
        pass

    class C(A):
        __KEY__ = "C"
        pass

    class D(A):
        __KEY__ = "D"
        pass

    container = Container()

    def get_key(a: A):
        return type(a).__KEY__

    container.register_subclasses(A)
    container.register(
        dict[str, A],
        factory=create_type_mapping(A, key_getter=get_key),
    )

    mapping = container.resolve(dict[str, A])

    assert_that(mapping["B"]).matches(is_exact_type(B))
    assert_that(mapping["C"]).matches(is_exact_type(C))
    assert_that(mapping["D"]).matches(is_exact_type(D))


def test_create_type_mapping_with_filter():
    class A:
        __KEY__ = None
        pass

    class B(A):
        __KEY__ = "B"
        pass

    class C(A):
        __KEY__ = "C"
        pass

    class D(A):
        __KEY__ = "D"
        pass

    container = Container()

    def get_key(a: A):
        return type(a).__KEY__

    def filter(r: Registration):
        return getattr(r.implementation, "__KEY__") in ("B", "D")

    container.register_subclasses(A)

    container.register(
        dict[str, A],
        factory=create_type_mapping(A, key_getter=get_key, filter=filter),
    )

    mapping: dict[str, A] = container.resolve(dict[str, A])

    assert_that(mapping.get("B")).matches(is_exact_type(B))
    assert_that(mapping.get("C")).matches(None)
    assert_that(mapping.get("D")).matches(is_exact_type(D))
