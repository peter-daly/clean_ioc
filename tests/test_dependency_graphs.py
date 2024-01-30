# from __future__ import annotations
from typing import Generic, TypeVar, Any
import pytest
from clean_ioc import (
    Container,
    DependencyContext,
    DependencySettings,
    Lifespan,
    Registration,
)
from clean_ioc.type_filters import (
    name_end_with,
)

from clean_ioc.functional_utils import fn_not
from clean_ioc.registration_filters import (
    with_implementation,
)
from assertive import (
    assert_that,
    is_exact_type,
    is_none,
)


def test_graphs_contain_dependency_logic_after_first_registration_is_cached():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)

    class SqlDbConnection:
        pass

    class DocDbConnection:
        pass

    class DocRepository:
        def __init__(self, connection: DocDbConnection):
            self.connection = connection

    class SqlRepository:
        def __init__(self, connection: SqlDbConnection):
            self.connection = connection

    class MessageHandler(Generic[TMessage]):
        def handle(self, message: TMessage):
            pass

    class MessageA(Message):
        pass

    class MessageB(Message):
        pass

    class MessageC(Message):
        pass

    class AHandler(MessageHandler[MessageA]):
        def __init__(self, repository: SqlRepository):
            self.repository = repository

    class BHandler(MessageHandler[MessageB]):
        def __init__(self, repository: DocRepository):
            self.repository = repository

    class CHandler(MessageHandler[MessageC]):
        def __init__(
            self, sql_repository: SqlRepository, doc_repository: DocRepository
        ):
            self.sql_repository = sql_repository
            self.doc_repository = doc_repository

    container = Container()

    container.register(DocDbConnection)
    container.register(SqlDbConnection)
    container.register(DocRepository, lifespan=Lifespan.singleton)
    container.register(SqlRepository, lifespan=Lifespan.singleton)

    container.register_open_generic(MessageHandler)

    a_graph = container.resolve_dependency_graph(MessageHandler[MessageA])
    b_graph = container.resolve_dependency_graph(MessageHandler[MessageB])
    c_graph = container.resolve_dependency_graph(MessageHandler[MessageC])

    assert a_graph.has_dependant_service_type(SqlDbConnection)
    assert b_graph.has_dependant_service_type(DocDbConnection)
    assert c_graph.has_dependant_service_type(DocDbConnection)


def test_dependency_graph_with_a_list_knows_it_has_a_dependency_on_int():
    class A:
        def __init__(self, b: list[int], s: str):
            self.b = b

    container = Container()

    container.register(A)
    container.register(int, instance=1)
    container.register(int, instance=2)
    container.register(int, instance=3)
    container.register(str, instance="hello")

    a_graph = container.resolve_dependency_graph(A)

    assert a_graph.has_dependant_service_type(list[int])
    assert a_graph.has_dependant_service_type(int)
    assert a_graph.has_dependant_service_type(str)


def test_dependency_graph_knows_is_instance_types():
    class A:
        pass

    class B(A):
        pass

    def a_factory():
        return B()

    container = Container()

    container.register(A, factory=a_factory)

    a_graph = container.resolve_dependency_graph(A)

    assert a_graph.has_dependant_service_type(A)
    assert not a_graph.has_dependant_implementation_type(B)
    assert a_graph.has_dependant_instance_type(B)


def test_once_per_graph_keeps_parentage():
    class A:
        pass

    class B:
        def __init__(self, a: A):
            self.a = a

    class C:
        def __init__(self, a: A, b: B):
            self.a = a
            self.b = b

    container = Container()

    container.register(A)
    container.register(B)
    container.register(C)

    c_graph = container.resolve_dependency_graph(C)

    assert c_graph.has_dependant_service_type(A)
