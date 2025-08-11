# from __future__ import annotations
from collections.abc import MutableSequence, Sequence
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any, Callable, Generic, Protocol, TypeVar
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from assertive import (
    assert_that,
    has_length,
    is_exact_type,
    is_gt,
    is_same_instance_as,
    raises_exception,
    was_called,
    was_called_once,
    was_called_with,
    was_not_called,
)

from clean_ioc import (
    CannotResolveError,
    Container,
    DependencyContext,
    DependencySettings,
    Lifespan,
    NeedsScopedRegistrationError,
    Registration,
    Tag,
)
from clean_ioc.factories import use_from_current_graph
from clean_ioc.node_filters import implementation_type_is
from clean_ioc.registration_filters import (
    has_tag,
    has_tag_with_value_in,
    with_implementation,
    with_name,
)
from clean_ioc.value_factories import (
    dont_use_default_value,
    set_value,
)


def test_simple_implementation_registation():
    class A:
        pass

    class B(A):
        pass

    container = Container()
    container.register(A, B)

    a = container.resolve(A)
    assert_that(a).matches(is_exact_type(B))


def test_simple_implementation_registation_can_also_resolve_from_implementation_type():
    class A:
        pass

    class B(A):
        pass

    container = Container()
    container.register(A, B)

    b = container.resolve(B)
    assert_that(b).matches(is_exact_type(B))


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
    assert_that(a).matches(is_exact_type(B))


def test_simple_instance_registation():
    class A:
        pass

    instance = A()

    container = Container()
    container.register(A, instance=instance)

    a = container.resolve(A)
    assert_that(a).matches(is_exact_type(A))
    assert_that(a).matches(is_same_instance_as(instance))


def test_simple_self_registation():
    class A:
        pass

    container = Container()
    container.register(A)

    a = container.resolve(A)
    assert_that(a).matches(is_exact_type(A))


def test_list():
    class A:
        pass

    class B(A):
        pass

    container = Container()

    container.register(A)
    container.register(A, B)

    array = container.resolve(list[A])

    assert_that(array).matches(has_length(2))
    assert_that(array[0]).matches(is_exact_type(B))
    assert_that(array[1]).matches(is_exact_type(A))


def test_sequence():
    class A:
        pass

    class B(A):
        pass

    container = Container()

    container.register(A)
    container.register(A, B)

    array = container.resolve(Sequence[A])

    assert_that(array).matches(has_length(2))
    assert_that(array[0]).matches(is_exact_type(B))  # type: ignore
    assert_that(array[1]).matches(is_exact_type(A))  # type: ignore


def test_mutable_sequence():
    class A:
        pass

    class B(A):
        pass

    container = Container()

    container.register(A)
    container.register(A, B)

    array = container.resolve(MutableSequence[A])

    assert_that(array).matches(has_length(2))
    assert_that(array[0]).matches(is_exact_type(B))  # type: ignore
    assert_that(array[1]).matches(is_exact_type(A))  # type: ignore


def test_list_with_filter():
    class A:
        pass

    class B(A):
        pass

    container = Container()

    container.register(A)
    container.register(A, B)

    array = container.resolve(list[A], filter=with_implementation(B))

    assert_that(array).matches(has_length(1))
    assert_that(array[0]).matches(is_exact_type(B))


def test_with_named_filter():
    class A:
        pass

    container = Container()

    a1 = A()
    a2 = A()

    container.register(A, instance=a1, name="A1")
    container.register(A, instance=a2, name="A2")

    a = container.resolve(A, filter=with_name("A1"))

    assert_that(a).matches(is_same_instance_as(a1))


def test_with_named_filter_unnamed_always_returned_first():
    class A:
        pass

    container = Container()

    unnamed_a = A()
    named_a = A()

    container.register(A, instance=unnamed_a)
    container.register(A, instance=named_a, name="NamedA")

    a = container.resolve(A)

    assert_that(a).matches(is_same_instance_as(unnamed_a))


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

    assert_that(array).matches(has_length(2))
    assert_that(array[0]).matches(is_same_instance_as(a3))
    assert_that(array[1]).matches(is_same_instance_as(a1))


def test_different_collection_types():
    class A:
        pass

    container = Container()

    a1 = A()
    a2 = A()
    a3 = A()

    container.register(A, instance=a1, tags=[Tag("number", "one")])
    container.register(A, instance=a2, tags=[Tag("number", "two")])
    container.register(A, instance=a3, tags=[Tag("number", "three")])

    a_set = container.resolve(set[A])
    a_tuple = container.resolve(tuple[A], has_tag_with_value_in("number", "one", "two"))
    a_list = container.resolve(list[A])

    assert_that(a_set).matches(has_length(3))
    assert_that(a_tuple).matches(has_length(2))
    assert_that(a_list).matches(has_length(3))


def test_nested_decorators_should_be_in_order_of_when_first_registered():
    class A:
        pass

    class DecALayer1(A):
        def __init__(self, a: A):
            self.a = a

    class DecALayer2(A):
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(A)
    container.register_decorator(A, DecALayer1)
    container.register_decorator(A, DecALayer2)

    a = container.resolve(A)

    assert_that(a).matches(is_exact_type(DecALayer1))
    assert_that(a.a).matches(is_exact_type(DecALayer2))  # type: ignore
    assert_that(a.a.a).matches(is_exact_type(A))  # type: ignore


def test_nested_decorators_with_sort_index():
    class A:
        pass

    class D1(A):
        def __init__(self, a: A):
            self.a = a

    class D2(A):
        def __init__(self, a: A):
            self.a = a

    class D3(A):
        def __init__(self, a: A):
            self.a = a

    class D4(A):
        def __init__(self, a: A):
            self.a = a

    class D5(A):
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(A)
    container.register_decorator(A, D1)
    container.register_decorator(A, D2)
    container.register_decorator(A, D3, position=10)
    container.register_decorator(A, D4, position=-10)
    container.register_decorator(A, D5, position=10)

    a: Any = container.resolve(A)

    assert a == is_exact_type(D3)
    assert a.a == is_exact_type(D5)
    assert a.a.a == is_exact_type(D1)
    assert a.a.a.a == is_exact_type(D2)
    assert a.a.a.a.a == is_exact_type(D4)


def test_simple_decorator():
    class A:
        pass

    class DecA(A):
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(A)
    container.register_decorator(A, DecA)

    a = container.resolve(A)

    assert_that(a).matches(is_exact_type(DecA))


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

    assert_that(a).matches(is_exact_type(DecAny))


def test_simple_open_generic():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_generic_subclasses(A)

    a = container.resolve(A[int])

    assert_that(a).matches(is_exact_type(B))


def test_simple_open_generic_with_protocol():
    T = TypeVar("T", covariant=True)

    class A(Protocol[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_generic_subclasses(A)

    a = container.resolve(A[int])

    assert_that(a).matches(is_exact_type(B))


def test_simple_open_generic_should_fail_when_no_implementation():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_generic_subclasses(A)

    with raises_exception(CannotResolveError):
        container.resolve(A[str])


def test_simple_open_generic_with_fallback_should_not_fail():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    class C(A):
        pass

    container = Container()

    container.register_generic_subclasses(A, fallback_type=C)

    a = container.resolve(A[str])

    assert_that(a).matches(is_exact_type(C))


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

    container.register_generic_subclasses(A)
    container.register_generic_decorator(A, ADec)

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("__DecoratedGeneric__ADec")


def test_open_generic_decorators_with_protocol():
    T = TypeVar("T", covariant=True)

    class A(Protocol[T]):
        pass

    class ADec(A[T]):
        def __init__(self, a: A[T]):
            pass

    class B(A[int]):
        pass

    container = Container()

    container.register_generic_subclasses(A)
    container.register_generic_decorator(A, ADec, decorated_arg="a")

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("__DecoratedGeneric__ADec")


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

    container.register_generic_subclasses(A)
    container.register_generic_decorator(A, ADec, decorated_arg="a")

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("ADec")


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

    container.register_generic_subclasses(A)
    container.register_generic_decorator(A, ADecGeneric, decorated_arg="a")
    container.register_generic_decorator(A, ADecNonGeneric, decorated_arg="a")

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("__DecoratedGeneric__ADecGeneric")
    assert_that(type(a.a).__name__).matches("ADecNonGeneric")  # type: ignore
    assert_that(type(a.a.a).__name__).matches("B")  # type: ignore


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
        A,
        dependency_config={"s": DependencySettings(value_factory=dont_use_default_value)},
    )
    container.register(
        B,
        dependency_config={"x": DependencySettings(value_factory=set_value(5))},
    )
    container.register(
        C,
        dependency_config={"y": DependencySettings(value_factory=set_value(100))},
    )
    container.register(str, factory=str_fac)
    container.register(int, instance=const_int)

    c: C = container.resolve(C)

    assert_that(c.b.a.s).matches("3")
    assert_that(c.b.x).matches(5)
    assert_that(c.y).matches(100)
    assert_that(c.z).matches(10)


def test_a_dependency_value_factory_with_a_dependency_context_filter():
    def greeting_value_factory(default_value: Any, context: DependencyContext):
        if class_greeting := getattr(context.parent.service_type, "GREETING", None):
            return class_greeting
        return default_value

    class A:
        def __init__(self, greeting: str = "AAAAA"):
            self.greeting = greeting

    class B:
        GREETING = "BBBBB"

        def __init__(self, a: A):
            self.a = a

    class C:
        GREETING = "CCCCC"

        def __init__(self, a: A):
            self.a = a

    class D:
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(
        A,
        dependency_config={"greeting": DependencySettings(value_factory=greeting_value_factory)},
    )
    container.register(B)
    container.register(C)
    container.register(D)

    b = container.resolve(B)
    c = container.resolve(C)
    d = container.resolve(D)

    assert_that(b.a.greeting).matches("BBBBB")
    assert_that(c.a.greeting).matches("CCCCC")
    assert_that(d.a.greeting).matches("AAAAA")


def test_simple_self_regristation_with_constructor_with_positional_and_keyword_args_no_args():
    class A:
        def __init__(self, *args, **kwargs):
            pass

    container = Container()
    container.register(A)

    a = container.resolve(A)
    assert_that(a).matches(is_exact_type(A))


def test_simple_self_regristation_with_constructor_with_positional_and_keyword_args():
    class A:
        def __init__(self, *args, **kwargs):
            self.kw = kwargs

    container = Container()
    container.register(A, dependency_config={"x": DependencySettings(value_factory=set_value(10))})

    a = container.resolve(A)
    assert_that(a).matches(is_exact_type(A))
    assert_that(a.kw["x"]).matches(10)


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

    assert_that(e.d.c.b.a).matches(is_same_instance_as(a))
    assert_that(e.d.c).does_not_match(is_same_instance_as(e.c))
    assert_that(e.d.b).matches(is_same_instance_as(e.d.c.b))


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

    assert_that(e1).does_not_match(is_same_instance_as(e2))
    assert_that(a1).matches(is_same_instance_as(a2))
    assert_that(e2_1).matches(is_same_instance_as(e2))
    assert_that(e2.d.c.b.a).matches(is_same_instance_as(e2.d.c.b.a))


def test_scope_registrations_overrides_container():
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

        assert_that(c.b).does_not_match(is_same_instance_as(c_scoped.b))
        assert_that(c.b.a).matches(is_same_instance_as(c_scoped.b.a))


def test_expect_to_be_scoped():
    class A:
        pass

    container = Container()

    container.expect_to_be_scoped(A)

    with container.new_scope() as scope:
        scope.register(A)
        a_scoped: A = scope.resolve(A)

        assert_that(a_scoped).matches(is_exact_type(A))

    with raises_exception(NeedsScopedRegistrationError):
        container.resolve(A)


def test_expect_to_be_scoped_with_name():
    class A:
        pass

    container = Container()

    container.register(A)
    container.expect_to_be_scoped(A, name="ScopedA")

    with container.new_scope() as scope:
        scope.register(A, name="ScopedA")
        assert_that(lambda: container.resolve(A, filter=with_name("ScopedA"))).matches(
            raises_exception(NeedsScopedRegistrationError)
        )

        a_scoped: A = scope.resolve(A, filter=with_name("ScopedA"))

        assert_that(a_scoped).matches(is_exact_type(A))

    a_unscoped = container.resolve(A)
    assert_that(a_unscoped).matches(is_exact_type(A))


def test_simple_bundle_registation():
    class A:
        pass

    class B(A):
        pass

    def module(c: Container):
        c.register(A, B)

    container = Container()

    container.apply_bundle(module)

    a = container.resolve(A)
    assert_that(a).matches(is_exact_type(B))


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
    assert_that(b.a.parent_type).matches(B)


def test_dependency_context_with_decorators_and_deep_child():
    class A:
        def __init__(self, parent_type: type | Callable, parent_type_undecorated: type | Callable):
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
        parent_type_undecorated = dependency_context.parent.bottom_decorated_node.implementation
        return A(parent_type=parent_type, parent_type_undecorated=parent_type_undecorated)

    container = Container()
    container.register(A, factory=a_fac, lifespan=Lifespan.transient)
    container.register_decorator(B, BDecoratedLayer1)
    container.register_decorator(B, BDecoratedLayer2)
    container.register(B)

    b: B = container.resolve(B)

    a = b.get_a()

    assert_that(a.parent_type).matches(BDecoratedLayer1)
    assert_that(a.parent_type_undecorated).matches(B)


def test_has_registrations():
    class A:
        pass

    class B:
        pass

    container = Container()

    container.register(A)

    assert_that(container.has_registration(A)).matches(True)
    assert_that(container.has_registration(B)).matches(False)


def test_pre_configurations():
    mock_method = Mock()

    class A:
        def name(self):
            return "A"

    class B:
        pass

    def pre_configure_b(a: A):
        mock_method(a.name())

    container = Container()

    container.register(A)
    container.register(B)
    container.pre_configure(B, pre_configure_b)

    container.resolve(B)
    container.resolve(B)
    container.resolve(B)

    mock_method.assert_called_once_with("A")


def test_pre_configurations_with_collections():
    mock_method = Mock()

    class A:
        def name(self):
            return "A"

    class B:
        pass

    class C:
        pass

    def pre_configure(a: A):
        mock_method(a.name())

    container = Container()

    container.register(A)
    container.register(B)
    container.register(C)
    container.pre_configure((B, C), pre_configure)

    container.resolve(C)
    container.resolve(B)

    mock_method.assert_called_once_with("A")


async def test_pre_configurations_async():
    mock_method = Mock()

    class A:
        def name(self):
            return "A"

    class B:
        pass

    def pre_configure(a: A):
        mock_method(a.name())

    container = Container()

    container.register(A)
    container.register(B)
    container.pre_configure(B, pre_configure)

    await container.resolve_async(B)

    mock_method.assert_called_once_with("A")


def test_registration_with_tags():
    class A:
        pass

    a1 = A()
    a2 = A()
    a3 = A()

    container = Container()

    container.register(A, instance=a1, tags=[Tag("a", "a1")])
    container.register(A, instance=a2, tags=[Tag("a")])
    container.register(A, instance=a3)

    ar1 = container.resolve(A, filter=has_tag("a", "a1"))
    al1 = container.resolve(list[A], filter=has_tag("a"))
    al2 = container.resolve(list[A], filter=has_tag("a", "a1"))
    al3 = container.resolve(list[A], filter=~has_tag("a", "a1"))
    al4 = container.resolve(list[A], filter=~has_tag("a"))
    al5 = container.resolve(list[A])

    assert_that(ar1).matches(is_same_instance_as(a1))

    assert_that(al1).matches(has_length(2))
    assert_that(al1[0]).matches(is_same_instance_as(a2))
    assert_that(al1[1]).matches(is_same_instance_as(a1))

    assert_that(al2).matches(has_length(1))
    assert_that(al2[0]).matches(is_same_instance_as(a1))

    assert_that(al3).matches(has_length(2))
    assert_that(al3[0]).matches(is_same_instance_as(a3))
    assert_that(al3[1]).matches(is_same_instance_as(a2))

    assert_that(al4).matches(has_length(1))
    assert_that(al4[0]).matches(is_same_instance_as(a3))

    assert_that(al5).matches(has_length(3))
    assert_that(al5[0]).matches(is_same_instance_as(a3))
    assert_that(al5[1]).matches(is_same_instance_as(a2))
    assert_that(al5[2]).matches(is_same_instance_as(a1))


def test_decorator_with_registration_filters():
    class A:
        pass

    class DecA(A):
        def __init__(self, a: A):
            pass

    a1 = A()
    a2 = A()

    container = Container()

    container.register(A, instance=a1, name="a1")
    container.register(A, instance=a2, name="a2", tags=[Tag("do_not_decorate")])
    container.register_decorator(A, DecA, registration_filter=~has_tag("do_not_decorate"))

    ar1 = container.resolve(A, filter=with_name("a1"))
    ar2 = container.resolve(A, filter=with_name("a2"))

    assert_that(ar1).matches(is_exact_type(DecA))
    assert_that(ar2).matches(is_exact_type(A))


def test_parent_context_filter():
    class A:
        pass

    class B(A):
        pass

    class C(A):
        pass

    class D:
        def __init__(self, a: A):
            self.a = a

    class E:
        def __init__(self, a: A):
            self.a = a

    container = Container()

    container.register(A, B, parent_node_filter=implementation_type_is(E))
    container.register(A, C, parent_node_filter=implementation_type_is(D))
    container.register(D)
    container.register(E)

    e = container.resolve(E)
    d = container.resolve(D)

    assert_that(e.a).matches(is_exact_type(B))
    assert_that(d.a).matches(is_exact_type(C))


def test_scoped_teardowns():
    class A:
        pass

    teardown = Mock()
    container = Container()
    container.register(A, lifespan=Lifespan.scoped, scoped_teardown=teardown)
    with container.new_scope() as scope:
        a = scope.resolve(A)

    assert_that(teardown).matches(was_called_with(a))


@pytest.mark.asyncio()
async def test_sync_scoped_teardowns_are_called_for_in_scope():
    class A:
        pass

    sync_teardown = Mock()
    container = Container()
    container.register(A, lifespan=Lifespan.scoped, scoped_teardown=sync_teardown)
    async with container.new_scope() as scope:
        a = scope.resolve(A)

    assert_that(sync_teardown).matches(was_called_with(a))


@pytest.mark.asyncio()
async def test_async_scoped_teardowns_are_called_for_in_scope():
    class A:
        pass

    async_teardown = AsyncMock()
    container = Container()
    container.register(A, lifespan=Lifespan.scoped, scoped_teardown=async_teardown)
    async with container.new_scope() as scope:
        a = scope.resolve(A)

    assert_that(async_teardown).matches(was_called_with(a))


def test_async_scoped_teardowns_dont_get_called_in_sync_context_manager():
    class A:
        pass

    async_teardown = AsyncMock()
    container = Container()

    container.register(A, lifespan=Lifespan.scoped, scoped_teardown=async_teardown)
    with container.new_scope() as scope:
        scope.resolve(A)

    assert_that(async_teardown).matches(was_called().never())


def test_generator_factory():
    mock = Mock()

    def generator(x: int):
        yield str(x)
        mock(x)

    container = Container()
    container.register(int, instance=5)
    container.register(str, factory=generator, lifespan=Lifespan.scoped)

    with container.new_scope() as scope:
        s = scope.resolve(str)
        assert_that(s).matches("5")
        assert_that(mock).matches(was_called().never())
    assert_that(mock).matches(was_called_with(5))


def test_generator_factory_works_in_a_scope_without_scoped_objects():
    mock = Mock()

    def generator(x: int):
        yield str(x)
        mock(x)

    container = Container()
    container.register(int, instance=5)
    container.register(str, factory=generator)

    with container.new_scope() as scope:
        s = scope.resolve(str)
        assert_that(s).matches("5")
        assert_that(mock).matches(was_called().never())
    assert_that(mock).matches(was_called_with(5))


def test_generator_doesnt_finish_when_not_in_a_scope():
    mock = Mock()

    def generator(x: int):
        yield str(x)
        mock(x)

    container = Container()
    container.register(int, instance=5)

    container.register(str, factory=generator)
    result = container.resolve(str)

    assert_that(result).matches("5")
    assert_that(mock).matches(was_called().never())


def test_generator_factory_with_a_context_manager():
    mock = MagicMock()

    def generator(x: int):
        with mock:
            yield str(x)

    container = Container()
    container.register(int, instance=5)
    container.register(str, factory=generator, lifespan=Lifespan.scoped)

    with container.new_scope() as scope:
        s = scope.resolve(str)
        assert_that(s).matches("5")
        assert_that(mock.__enter__).matches(was_called().once())
        assert_that(mock.__exit__).matches(was_called().never())
    assert_that(mock.__enter__).matches(was_called().once())
    assert_that(mock.__exit__).matches(was_called().once())


def test_generators_can_depend_on_other_generators():
    int_mock = MagicMock()
    str_mock = MagicMock()

    def generator_int():
        yield 5
        int_mock(datetime.now())

    def generator_str(x: int):
        yield str(x)
        str_mock(datetime.now())

    container = Container()
    container.register(int, factory=generator_int)
    container.register(str, factory=generator_str)

    with container.new_scope() as scope:
        s = scope.resolve(str)
        assert_that(s).matches("5")

    int_mock_call_arg = int_mock.mock_calls[0].args[0]
    str_mock_call_arg = str_mock.mock_calls[0].args[0]

    assert_that(int_mock_call_arg).matches(is_exact_type(datetime))
    assert_that(str_mock_call_arg).matches(is_exact_type(datetime))

    assert_that(int_mock_call_arg).matches(is_gt(str_mock_call_arg))


def test_nested_scopes():
    container = Container()
    container.register(int, instance=5)
    container.register(str, instance="hello")

    with container.new_scope() as outer_scope:
        outer_scope.register(int, instance=10)
        with outer_scope.new_scope() as inner_scope:
            inner_scope.register(int, instance=15)
            inner_scope.register(str, instance="goodbye")
            container_int = container.resolve(int)
            outer_int = outer_scope.resolve(int)
            inner_int = inner_scope.resolve(int)

            container_str = container.resolve(str)
            outer_str = outer_scope.resolve(str)
            inner_str = inner_scope.resolve(str)

            assert container_int == 5
            assert outer_int == 10
            assert inner_int == 15

            assert container_str == "hello"
            assert outer_str == "hello"
            assert inner_str == "goodbye"


def test_nested_scopes_with_scoped_registrations():
    with Container() as container:
        container.register(int, instance=5)
        container_int = container.resolve(int)
        with container.new_scope() as outer_scope:
            outer_scope.register(int, instance=10)
            outer_int = outer_scope.resolve(int)
            with outer_scope.new_scope() as inner_scope:
                inner_scope.register(int, instance=15)
                inner_scope.register(str, instance="goodbye")
                inner_int = inner_scope.resolve(int)

    assert inner_int == 15
    assert outer_int == 10
    assert container_int == 5


def test_generators_across_scopes():
    int_mock = MagicMock()
    str_mock = MagicMock()
    float_mock = MagicMock()

    def generator_int():
        with int_mock:
            yield 5

    def generator_str(x: int):
        with str_mock:
            yield str(x)

    def generator_float(y: str):
        with float_mock:
            yield float(y)

    with Container() as container:
        with container.new_scope() as outer_scope:
            outer_scope.register(str, factory=generator_str, lifespan=Lifespan.singleton)
            outer_scope.register(float, factory=generator_float, lifespan=Lifespan.scoped)
            outer_scope.register(int, factory=generator_int, lifespan=Lifespan.scoped)

            with outer_scope.new_scope() as inner_scope:
                inner_x = inner_scope.resolve(float)
                assert inner_x == 5.0

                assert_that(int_mock.__enter__).matches(was_called().once())
                assert_that(int_mock.__exit__).matches(was_called().never())
                assert_that(str_mock.__enter__).matches(was_called().once())
                assert_that(str_mock.__exit__).matches(was_called().never())
                assert_that(float_mock.__enter__).matches(was_called().once())
                assert_that(float_mock.__exit__).matches(was_called().never())

            assert_that(int_mock.__enter__).matches(was_called().once())
            assert_that(int_mock.__exit__).matches(was_called().once())
            assert_that(str_mock.__enter__).matches(was_called().once())
            assert_that(str_mock.__exit__).matches(was_called().never())
            assert_that(float_mock.__enter__).matches(was_called().once())
            assert_that(float_mock.__exit__).matches(was_called().once())

        # Exit outer scope
        assert_that(int_mock.__enter__).matches(was_called().once())
        assert_that(int_mock.__exit__).matches(was_called().once())
        assert_that(str_mock.__enter__).matches(was_called().once())
        assert_that(str_mock.__exit__).matches(was_called().never())
        assert_that(float_mock.__enter__).matches(was_called().once())
        assert_that(float_mock.__exit__).matches(was_called().once())

    # Exit container
    assert_that(int_mock.__enter__).matches(was_called().once())
    assert_that(int_mock.__exit__).matches(was_called().once())
    assert_that(str_mock.__enter__).matches(was_called().once())
    assert_that(str_mock.__exit__).matches(was_called().once())
    assert_that(float_mock.__enter__).matches(was_called().once())
    assert_that(float_mock.__exit__).matches(was_called().once())


def test_singleton_implementation_and_service_type_resolve_to_same_instance():
    class A:
        pass

    class B(A):
        pass

    container = Container()
    container.register(A, B, lifespan=Lifespan.singleton)

    a = container.resolve(A)
    b = container.resolve(B)

    assert a is b


def test_pre_configuration_on_error_raises_error():
    class A:
        pass

    def pre_configure():
        raise ValueError()

    container = Container()
    container.register(A)
    container.pre_configure(A, pre_configure)

    with pytest.raises(ValueError):
        container.resolve(A)


async def test_pre_configuration_on_error_raises_error_async():
    class A:
        pass

    async def pre_configure():
        raise ValueError()

    container = Container()
    container.register(A)
    container.pre_configure(A, pre_configure)

    with pytest.raises(ValueError):
        await container.resolve_async(A)


def test_pre_configuration_on_error_continues_when_continue_on_failure_is_true():
    class A:
        pass

    def pre_configure():
        raise ValueError()

    container = Container()
    container.register(A)
    container.pre_configure(A, pre_configure, continue_on_failure=True)

    a = container.resolve(A)

    assert a == is_exact_type(A)


def test_pre_configuration_as_a_generator():
    class A:
        pass

    spy = Mock()

    def pre_configure():
        spy()
        yield
        spy()

    container = Container()
    with container:
        container.pre_configure(A, pre_configure)
        container.register(A)
        container.resolve(A)
        assert spy == was_called().once()

    assert spy == was_called().twice()


def test_decorator_as_a_function():
    class A:
        pass

    def decorator_fn(instance: A):
        setattr(instance, "decorated", True)
        return instance

    container = Container()
    container.register(A)
    container.register_decorator(A, decorator_fn)

    a = container.resolve(A)

    assert getattr(a, "decorated", False)


def test_decorator_as_a_generator():
    class A:
        pass

    spy = Mock()

    def decorator_fn(instance: A):
        spy(instance)
        yield instance
        spy(instance)

    container = Container()
    container.register(A)
    container.register_decorator(A, decorator_fn)

    with container:
        a = container.resolve(A)
        assert spy == was_called_with(a).once()

    assert spy == was_called_with(a).twice()


async def test_decorator_as_an_async_generator():
    class A:
        pass

    spy = AsyncMock()

    async def decorator_fn(instance: A):
        await spy(instance)
        yield instance
        await spy(instance)

    container = Container()
    container.register(A)
    container.register_decorator(A, decorator_fn)

    async with container:
        a = await container.resolve_async(A)
        assert spy == was_called_with(a).once()

    assert spy == was_called_with(a).twice()


def test_using_current_graph_finds_dependencies_from_within():
    class A(Protocol):
        pass

    class B(Protocol):
        pass

    class AB(A, B):
        pass

    class C:
        def __init__(self, a: A, b: B):
            self.a = a
            self.b = b

    container = Container()

    container.register(A, AB)
    container.register(B, factory=use_from_current_graph(AB))
    container.register(C)
    c = container.resolve(C)

    assert c.a is c.b


async def test_using_current_graph_async_finds_dependencies_from_within():
    class A(Protocol):
        pass

    class B(Protocol):
        pass

    class AB(A, B):
        pass

    class C:
        def __init__(self, a: A, b: B):
            self.a = a
            self.b = b

    container = Container()

    container.register(A, AB)
    container.register(B, factory=use_from_current_graph(AB))
    container.register(C)
    c = container.resolve(C)

    assert c.a is c.b


def test_registartion_list_modifiers():
    class A:
        pass

    class B(A):
        NUMBER = 1

    class C(A):
        NUMBER = 5

    class D(A):
        NUMBER = 3

    class E:
        def __init__(self, alist: list[A]):
            self.alist = alist

    def modifier(regs: list[Registration]):
        return sorted(regs, key=lambda r: getattr(r.implementation, "NUMBER"))

    container = Container()

    container.register(A, B)
    container.register(A, C)
    container.register(A, D)

    container.register(E, dependency_config={"alist": DependencySettings(list_modifier=modifier)})

    e = container.resolve(E)

    assert e.alist == has_length(3)

    assert e.alist[0] == is_exact_type(B)
    assert e.alist[1] == is_exact_type(D)
    assert e.alist[2] == is_exact_type(C)


def test_context_manager_factory_with_generator():
    class A:
        def __init__(self):
            self.spy = MagicMock()

        def __enter__(self):
            self.spy.enter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.spy.exit()
            pass

    container = Container()

    @contextmanager
    def generator():
        with A() as a:
            yield a

    container.register(A, factory=generator)

    with container:
        a = container.resolve(A)
        assert a == is_exact_type(A)
        assert a.spy.enter == was_called_once()
        assert a.spy.exit == was_not_called()
    assert a.spy.exit == was_called_once()


async def test_async_context_manager_with_generator_generator():
    class A:
        pass

    container = Container()

    @asynccontextmanager
    async def generator():
        yield A()

    container.register(A, factory=generator)

    async with container:
        a = await container.resolve_async(A)
        assert_that(a).matches(is_exact_type(A))


def test_resolve_from_registration_ids():
    class A:
        pass

    a1 = A()
    a2 = A()

    container = Container()
    container.register(A, instance=a1)
    container.register(A, instance=a2)

    ids = container.get_registration_ids(A)

    resolved_a1 = container.resolve_from_registration_id(A, ids[1])
    resolved_a2 = container.resolve_from_registration_id(A, ids[0])
    assert resolved_a1 is a1
    assert resolved_a2 is a2


def test_setting_dependency_config_can_accept_values():
    class A:
        pass

    class B:
        def __init__(self, a: A, x: int, y: int = 99):
            self.a = a
            self.x = x
            self.y = y

    container = Container()
    container.register(A)

    container.register(B, dependency_config={"x": 42})

    item = container.resolve(B)

    assert item.x == 42
    assert item.y == 99


def test_setting_dependency_config_can_accept_values_and_will_override_default_properties_when_set():
    class A:
        pass

    class B:
        def __init__(self, a: A, x: int, y: int = 99):
            self.a = a
            self.x = x
            self.y = y

    container = Container()
    container.register(A)

    container.register(B, dependency_config={"x": 42, "y": 25})

    item = container.resolve(B)

    assert item.x == 42
    assert item.y == 25


def test_using_registration_id_returned_from_registration():
    class A:
        pass

    container = Container()
    reg_id = container.register(A)

    resolved_a = container.resolve(A, filter=lambda r: r.id == reg_id)

    assert resolved_a is not None
