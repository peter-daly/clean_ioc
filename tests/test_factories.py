# from __future__ import annotations
from typing import Generic, TypeVar
from expects import equal, expect, have_length, raise_error
from expects.matchers import Matcher
from clean_ioc import (
    Container,
    CannotResolveExpcetion,
    DependencySettings,
    LifestyleType,
)
from clean_ioc.factories import use_registered
from clean_ioc.registration_filters import with_implementation, with_name
from .matchers import be_type, be_same_instance_as
from clean_ioc.registration_filters import with_name


def test_simple_use_registered():
    class A:
        pass

    class B:
        pass

    class C(A, B):
        pass

    c = C()

    container = Container()
    container.register(C, instance=c)
    container.register(A, factory=use_registered(C))
    container.register(B, factory=use_registered(C))

    a = container.resolve(A)
    b = container.resolve(B)

    expect(a).to(be_type(C))
    expect(b).to(be_type(C))

    expect(a).to(be_same_instance_as(c))
    expect(b).to(be_same_instance_as(c))


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
    container.register(B, factory=use_registered(C))

    a = container.resolve(A)
    b = container.resolve(B)

    expect(a).to(be_same_instance_as(c1))
    expect(b).to(be_same_instance_as(c2))
