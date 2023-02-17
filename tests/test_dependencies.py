# from __future__ import annotations
from typing import Generic, TypeVar
from expects import equal, expect, have_length, raise_error
from expects.matchers import Matcher
from clean_ioc import (
    Container,
    CannotResolveException,
    DependencySettings,
    LifestyleType,
)
from clean_ioc.registration_filters import with_implementation, with_name
from tests.matchers import be_same_instance_as, be_type


def test_simple_implementation_registation():
    class A:
        pass

    class B(A):
        pass

    container = Container()
    container.register(A, B)

    a = container.resolve(A)
    expect(a).to(be_type(B))


def test_simple_factory_registation():
    class A:
        pass

    class B(A):
        pass

    def fac():
        return B()

    container = Container()
    container.register(A, factory=fac)

    a = container.resolve(A)
    expect(a).to(be_type(B))


def test_simple_instance_registation():
    class A:
        pass

    instance = A()

    container = Container()
    container.register(A, instance=instance)

    a = container.resolve(A)
    expect(a).to(be_type(A))
    expect(a).to(be_same_instance_as(instance))


def test_simple_self_registation():
    class A:
        pass

    container = Container()
    container.register(A)

    a = container.resolve(A)
    expect(a).to(be_type(A))


def test_list():
    class A:
        pass

    class B(A):
        pass

    container = Container()

    container.register(A)
    container.register(A, B)

    array = container.resolve(list[A])

    expect(array).to(have_length(2))
    expect(array[0]).to(be_type(B))
    expect(array[1]).to(be_type(A))


def test_list_with_filter():
    class A:
        pass

    class B(A):
        pass

    container = Container()

    container.register(A)
    container.register(A, B)

    array = container.resolve(list[A], filter=with_implementation(B))

    expect(array).to(have_length(1))
    expect(array[0]).to(be_type(B))


def test_with_named_filter():
    class A:
        pass

    container = Container()

    a1 = A()
    a2 = A()

    container.register(A, instance=a1, name="A1")
    container.register(A, instance=a2, name="A2")

    a = container.resolve(A, filter=with_name("A1"))

    expect(a).to(be_same_instance_as(a1))


def test_list_with_named_filter():
    class A:
        pass

    container = Container()

    a1 = A()
    a2 = A()
    a3 = A()

    container.register(A, instance=a1, name="IN_LIST")
    container.register(A, instance=a2, name="NOT_IN_LIST")
    container.register(A, instance=a3, name="IN_LIST")

    array = container.resolve(list[A], filter=with_name("IN_LIST"))

    expect(array).to(have_length(2))
    expect(array[0]).to(be_same_instance_as(a3))
    expect(array[1]).to(be_same_instance_as(a1))


def test_simple_decorator():
    class A:
        pass

    class DecA:
        def __init__(self, a: A):
            self.a = a
            pass

    container = Container()

    container.register(A)
    container.register_decorator(A, DecA)

    a = container.resolve(A)

    expect(a).to(be_type(DecA))


def test_simple_open_generic():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)

    a = container.resolve(A[int])

    expect(a).to(be_type(B))


def test_simple_open_generic_should_fail_when_no_implementation():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)

    expect(lambda: container.resolve(A[str])).to(raise_error(CannotResolveException))


def test_simple_open_generic_with_fallback_should_not_fail():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    class C(A):
        pass

    container = Container()

    container.register_open_generic(A, fallback_type=C)

    a = container.resolve(A[str])

    expect(a).to(be_type(C))


def test_open_generic_decorators():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class ADec(Generic[T]):
        def __init__(self, a: A[T]):
            pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)
    container.register_open_generic_decorator(A, ADec)

    a = container.resolve(A[int])

    expect(type(a).__name__).to(equal("DecoratedGeneric_ADec"))


def test_deep_dependencies_with_dependency_settings():
    class A:
        def __init__(self, s: str = "Hello"):
            self.s = s

    class B:
        def __init__(self, a: A, x: int):
            self.a = a
            self.x = x

    class C:
        def __init__(self, b: B, y: int = 20, z: int = 10):
            self.b = b
            self.y = y
            self.z = z

    def str_fac(zz: int):
        return str(zz)

    const_int = 3

    container = Container()

    container.register(
        A, dependency_config={"s": DependencySettings(use_default_paramater=False)}
    )
    container.register(
        B,
        dependency_config={"x": DependencySettings(value=5)},
    )
    container.register(
        C,
        dependency_config={"y": DependencySettings(value=100)},
    )
    container.register(str, factory=str_fac)
    container.register(int, instance=const_int)

    c: C = container.resolve(C)

    expect(c.b.a.s).to(equal("3"))
    expect(c.b.x).to(equal(5))
    expect(c.y).to(equal(100))
    expect(c.z).to(equal(10))


def test_lifestyles():
    class A:
        pass

    class B:
        def __init__(self, a: A):
            self.a = a

    class C:
        def __init__(self, b: B):
            self.b = b

    class D:
        def __init__(self, b: B, c: C):
            self.b = b
            self.c = c

    class E:
        def __init__(self, d: D, c: C):
            self.d = d
            self.c = c

    container = Container()

    container.register(A, lifestyle=LifestyleType.singleton)
    container.register(B, lifestyle=LifestyleType.once_per_graph)
    container.register(C, lifestyle=LifestyleType.transient)
    container.register(D, lifestyle=LifestyleType.transient)
    container.register(E, lifestyle=LifestyleType.once_per_graph)

    e: E = container.resolve(E)
    a: A = container.resolve(A)

    expect(e.d.c.b.a).to(be_same_instance_as(a))
    expect(e.d.c).to_not(be_same_instance_as(e.c))
    expect(e.d.b).to(be_same_instance_as(e.d.c.b))


def test_scopes_with_lifestyles():
    class A:
        pass

    class B:
        def __init__(self, a: A):
            self.a = a

    class C:
        def __init__(self, b: B):
            self.b = b

    class D:
        def __init__(self, b: B, c: C):
            self.b = b
            self.c = c

    class E:
        def __init__(self, d: D, c: C):
            self.d = d
            self.c = c

    container = Container()

    container.register(A, lifestyle=LifestyleType.singleton)
    container.register(B, lifestyle=LifestyleType.once_per_graph)
    container.register(C, lifestyle=LifestyleType.transient)
    container.register(D, lifestyle=LifestyleType.transient)
    container.register(E, lifestyle=LifestyleType.scoped)

    scope1 = container.new_scope()
    scope2 = container.new_scope()

    e1: E = scope1.resolve(E)
    a1: A = scope1.resolve(A)

    e2: E = scope2.resolve(E)
    a2: A = scope2.resolve(A)

    e2_1: E = scope2.resolve(E)

    expect(e1).to_not(be_same_instance_as(e2))
    expect(a1).to(be_same_instance_as(a2))
    expect(e2_1).to(be_same_instance_as(e2))
    expect(e2.d.c.b.a).to(be_same_instance_as(e2.d.c.b.a))


def test_scope_registartions_overrides_container():
    class A:
        pass

    class B:
        def __init__(self, a: A):
            self.a = a

    class C:
        def __init__(self, b: B):
            self.b = b

    container = Container()

    container.register(A, lifestyle=LifestyleType.singleton)
    container.register(B, lifestyle=LifestyleType.once_per_graph)
    container.register(C, lifestyle=LifestyleType.scoped)

    with container.new_scope() as scope:
        scope.register(B)
        c_scoped: C = scope.resolve(C)

        c: C = container.resolve(C)

        expect(c.b).to_not(be_same_instance_as(c_scoped.b))
        expect(c.b.a).to(be_same_instance_as(c_scoped.b.a))


def test_simple_module_registation():
    class A:
        pass

    class B(A):
        pass

    def module(c: Container):
        c.register(A, B)

    container = Container()

    container.apply_module(module)

    a = container.resolve(A)
    expect(a).to(be_type(B))
