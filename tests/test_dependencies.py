# from __future__ import annotations
from typing import Callable, Generic, TypeVar
from expects import equal, expect, have_length, raise_error
from expects.matchers import Matcher
from traitlets import Any
from clean_ioc import (
    Container,
    CannotResolveException,
    DependencyContext,
    DependencySettings,
    Lifespan,
    NeedsScopedRegistrationError,
)
from clean_ioc.registration_filters import with_implementation, with_name, is_not_named
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


def test_nested_decorators_should_be_in_order_of_when_first_registered():
    class A:
        pass

    class DecALayer1:
        def __init__(self, a: A):
            self.a = a

    class DecALayer2:
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(A)
    container.register_decorator(A, DecALayer1)
    container.register_decorator(A, DecALayer2)

    a = container.resolve(A)

    expect(a).to(be_type(DecALayer2))
    expect(a.a).to(be_type(DecALayer1))
    expect(a.a.a).to(be_type(A))


def test_simple_decorator():
    class A:
        pass

    class DecA:
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(A)
    container.register_decorator(A, DecA)

    a = container.resolve(A)

    expect(a).to(be_type(DecA))


def test_decorator_with_decorated_arg_set():
    class A:
        pass

    class DecAny:
        def __init__(self, sub: Any):
            self.sub = sub

    container = Container()

    container.register(A)
    container.register_decorator(A, DecAny, decorated_arg="sub")

    a = container.resolve(A)

    expect(a).to(be_type(DecAny))


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


def test_open_generic_decorators_with_nongeneric_decorator():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class ADec:
        def __init__(self, a: A):
            pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)
    container.register_open_generic_decorator(A, ADec, decorated_arg="a")

    a = container.resolve(A[int])

    expect(type(a).__name__).to(equal("ADec"))


def test_open_generic_decorators_with_both_generic_and_nongeneric_decorator():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class ADecNonGeneric:
        def __init__(self, a: A):
            self.a = a

    class ADecGeneric(Generic[T]):
        def __init__(self, a: A[T]):
            self.a = a

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)
    container.register_open_generic_decorator(A, ADecNonGeneric, decorated_arg="a")
    container.register_open_generic_decorator(A, ADecGeneric, decorated_arg="a")

    a = container.resolve(A[int])

    expect(type(a).__name__).to(equal("DecoratedGeneric_ADecGeneric"))
    expect(type(a.a).__name__).to(equal("ADecNonGeneric"))
    expect(type(a.a.a).__name__).to(equal("B"))


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


def test_lifespans():
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

    container.register(A, lifespan=Lifespan.singleton)
    container.register(B, lifespan=Lifespan.once_per_graph)
    container.register(C, lifespan=Lifespan.transient)
    container.register(D, lifespan=Lifespan.transient)
    container.register(E, lifespan=Lifespan.once_per_graph)

    e: E = container.resolve(E)
    a: A = container.resolve(A)

    expect(e.d.c.b.a).to(be_same_instance_as(a))
    expect(e.d.c).to_not(be_same_instance_as(e.c))
    expect(e.d.b).to(be_same_instance_as(e.d.c.b))


def test_scopes_with_lifespans():
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

    container.register(A, lifespan=Lifespan.singleton)
    container.register(B, lifespan=Lifespan.once_per_graph)
    container.register(C, lifespan=Lifespan.transient)
    container.register(D, lifespan=Lifespan.transient)
    container.register(E, lifespan=Lifespan.scoped)

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

    container.register(A, lifespan=Lifespan.singleton)
    container.register(B, lifespan=Lifespan.once_per_graph)
    container.register(C, lifespan=Lifespan.scoped)

    with container.new_scope() as scope:
        scope.register(B)
        c_scoped: C = scope.resolve(C)

        c: C = container.resolve(C)

        expect(c.b).to_not(be_same_instance_as(c_scoped.b))
        expect(c.b.a).to(be_same_instance_as(c_scoped.b.a))


def test_expect_to_be_scoped():
    class A:
        pass

    container = Container()

    container.expect_to_be_scoped(A)

    with container.new_scope() as scope:
        scope.register(A)
        a_scoped: A = scope.resolve(A)

        expect(a_scoped).to(be_type(A))

    expect(lambda: container.resolve(A)).to(raise_error(NeedsScopedRegistrationError))


def test_expect_to_be_scoped_with_name():
    class A:
        pass

    container = Container()

    container.register(A)
    container.expect_to_be_scoped(A, name="ScopedA")

    with container.new_scope() as scope:
        scope.register(A, name="ScopedA")
        expect(lambda: container.resolve(A)).to(
            raise_error(NeedsScopedRegistrationError)
        )

        a_scoped: A = scope.resolve(A, filter=with_name("ScopedA"))

        expect(a_scoped).to(be_type(A))

    a_unscoped = container.resolve(A, filter=is_not_named)
    expect(a_unscoped).to(be_type(A))


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


def test_dependency_context_with_parent():
    class A:
        def __init__(self, parent_type: type | Callable):
            self.parent_type = parent_type

    class B:
        def __init__(self, a: A):
            self.a = a

    def a_fac(dependency_context: DependencyContext):
        return A(parent_type=dependency_context.parent.implementation)

    container = Container()
    container.register(A, factory=a_fac)
    container.register(B)

    b = container.resolve(B)
    expect(b.a.parent_type).to(equal(B))


def test_dependency_context_with_decorators_and_deep_child():
    class A:
        def __init__(
            self, parent_type: type | Callable, parent_type_undecorated: type | Callable
        ):
            self.parent_type = parent_type
            self.parent_type_undecorated = parent_type_undecorated

    class B:
        def __init__(self, a: A):
            self.a = a

        def get_a(self) -> A:
            return self.a

    class BDecoratedLayer1(B):
        def __init__(self, child: B, a: A):
            self.child = child
            self.a = a

        def get_a(self) -> A:
            return self.a

    class BDecoratedLayer2:
        def __init__(self, child: B):
            self.child = child

        def get_a(self) -> A:
            return self.child.get_a()

    def a_fac(dependency_context: DependencyContext):
        parent_type = dependency_context.parent.implementation
        parent_type_undecorated = dependency_context.parent.bottom_decorated
        return A(
            parent_type=parent_type, parent_type_undecorated=parent_type_undecorated
        )

    container = Container()
    container.register(A, factory=a_fac, lifespan=Lifespan.transient)
    container.register_decorator(B, BDecoratedLayer1)
    container.register_decorator(B, BDecoratedLayer2)
    container.register(B)

    b: B = container.resolve(B)

    a = b.get_a()

    expect(a.parent_type).to(equal(BDecoratedLayer1))
    expect(a.parent_type_undecorated).to(equal(B))
