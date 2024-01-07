# from __future__ import annotations
import asyncio
from typing import Callable, Generic, Protocol, TypeVar
import pytest
from traitlets import Any
from clean_ioc import (
    Container,
    CannotResolveException,
    ContainerScope,
    DependencyContext,
    DependencySettings,
    Lifespan,
    NeedsScopedRegistrationError,
    Scope,
    Tag,
)
from clean_ioc.functional_utils import fn_not
from clean_ioc.registration_filters import (
    has_tag,
    has_tag_with_value_in,
    with_implementation,
    with_name,
)
from clean_ioc.parent_context_filters import parent_implementation_is
from unittest.mock import AsyncMock, Mock
from assertive import (
    assert_that,
    is_exact_type,
    is_same_instance_as,
    has_length,
    raises_exception,
    was_called_with,
    was_called,
    is_type,
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

    container.register_open_generic(A)

    a = container.resolve(A[int])

    assert_that(a).matches(is_exact_type(B))


def test_simple_open_generic_with_protocol():
    T = TypeVar("T")

    class A(Protocol[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)

    a = container.resolve(A[int])

    assert_that(a).matches(is_exact_type(B))


def test_simple_open_generic_should_fail_when_no_implementation():
    T = TypeVar("T")

    class A(Generic[T]):
        pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)

    with raises_exception(CannotResolveException):
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

    container.register_open_generic(A, fallback_type=C)

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

    container.register_open_generic(A)
    container.register_open_generic_decorator(A, ADec)

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("DecoratedGeneric_ADec")


def test_open_generic_decorators_with_protocol():
    T = TypeVar("T")

    class A(Protocol[T]):
        pass

    class ADec(A[T]):
        def __init__(self, a: A[T]):
            pass

    class B(A[int]):
        pass

    container = Container()

    container.register_open_generic(A)
    container.register_open_generic_decorator(A, ADec)

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("DecoratedGeneric_ADec")


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

    container.register_open_generic(A)
    container.register_open_generic_decorator(A, ADecGeneric, decorated_arg="a")
    container.register_open_generic_decorator(A, ADecNonGeneric, decorated_arg="a")

    a = container.resolve(A[int])

    assert_that(type(a).__name__).matches("DecoratedGeneric_ADecGeneric")
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

    assert_that(c.b.a.s).matches("3")
    assert_that(c.b.x).matches(5)
    assert_that(c.y).matches(100)
    assert_that(c.z).matches(10)


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
    container.register(A, dependency_config={"x": DependencySettings(value=10)})

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
    al3 = container.resolve(list[A], filter=fn_not(has_tag("a", "a1")))
    al4 = container.resolve(list[A], filter=fn_not(has_tag("a")))
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
    container.register_decorator(
        A, DecA, registration_filter=fn_not(has_tag("do_not_decorate"))
    )

    ar1 = container.resolve(A, filter=with_name("a1"))
    ar2 = container.resolve(A, filter=with_name("a2"))

    assert_that(ar1).matches(is_exact_type(DecA))
    assert_that(ar2).matches(is_exact_type(A))


def test_scope_subclass_as_context_manager():
    class A:
        pass

    a_instance = A()

    class TestScope(ContainerScope):
        def __init__(self, container: Container, a: A):
            super().__init__(container)
            self.a = a

        def before_start(self):
            self.register(A, instance=self.a)

    container = Container()
    with container.new_scope(TestScope, a_instance) as scope:
        a_resolved = scope.resolve(A)
        assert_that(a_resolved).matches(is_same_instance_as(a_instance))


@pytest.mark.asyncio()
async def test_scope_subclass_as_async_context_manager():
    hook_mock = Mock()
    class_mock = Mock()

    class A:
        async def async_call(self):
            class_mock()

    class TestScope(ContainerScope):
        async def after_finish_async(self):
            hook_mock()
            current_a_instances = self.get_resolved_instances(A)
            await asyncio.gather(*[a.async_call() for a in current_a_instances])

    container = Container()
    container.register(A, lifespan=Lifespan.scoped)

    async with container.new_scope(TestScope) as scope:
        scope.resolve(A)

    hook_mock.assert_called()
    class_mock.assert_called()


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

    container.register(A, B, parent_context_filter=parent_implementation_is(E))
    container.register(A, C, parent_context_filter=parent_implementation_is(D))
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

    assert_that(async_teardown).matches(was_called().never)
