# from __future__ import annotations
from typing import Any, Generic, TypeVar

from assertive import (
    assert_that,
    is_exact_type,
    is_none,
)

import clean_ioc.node_filters as nf
import clean_ioc.registration_filters as rf
import clean_ioc.type_filters as tf
from clean_ioc import (
    Container,
    DependencyContext,
    DependencySettings,
    Registration,
)
from clean_ioc.core import Node, Tag


def test_value_factories_with_generic_decorators():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)
    ISOLATION_CLASS_ATTRIBUTE = "__ISOLATION_LEVEL__"  # noqa: N806

    def isolation_level_factory(default_value: Any, context: DependencyContext):
        message_type = context.parent.generic_mapping[TMessage]
        if isolation_level := getattr(message_type, ISOLATION_CLASS_ATTRIBUTE, None):
            return isolation_level

        return default_value

    def isolation_level(level: str):
        def decorator(cls: type):
            setattr(cls, ISOLATION_CLASS_ATTRIBUTE, level)
            return cls

        return decorator

    class MessageHandler(Generic[TMessage]):
        def handle(self, message: TMessage):
            pass

    class MessageA(Message):
        pass

    @isolation_level("REPEATABLE READ")
    class MessageB(Message):
        pass

    class AHandler(MessageHandler[MessageA]):
        pass

    class BHandler(MessageHandler[MessageB]):
        pass

    class TransactionManager:
        pass

    class SqlTransactionManager(TransactionManager):
        def __init__(self, isolation_level: str | None = None):
            self.isolation_level = isolation_level

    class TransactionMessageHandlerDecorator(MessageHandler[TMessage], Generic[TMessage]):
        def __init__(
            self,
            child: MessageHandler[TMessage],
            transaction_manager: TransactionManager,
        ):
            self.child = child
            self.transaction_manager = transaction_manager

        def handle(self, message: TMessage):
            self.child.handle(message)

    container = Container()

    container.register_generic_subclasses(MessageHandler)
    container.register_generic_decorator(MessageHandler, TransactionMessageHandlerDecorator, decorated_arg="child")

    container.register(
        TransactionManager,
        SqlTransactionManager,
        dependency_config={"isolation_level": DependencySettings(value_factory=isolation_level_factory)},
    )
    handler_a: TransactionMessageHandlerDecorator[MessageA] = container.resolve(
        MessageHandler[MessageA]  # type: ignore
    )
    handler_b: TransactionMessageHandlerDecorator[MessageB] = container.resolve(
        MessageHandler[MessageB]  # type: ignore
    )

    transaction_manager_a: SqlTransactionManager = handler_a.transaction_manager  # type: ignore
    transaction_manager_b: SqlTransactionManager = handler_b.transaction_manager  # type: ignore

    assert_that(transaction_manager_a.isolation_level).matches(is_none())
    assert_that(transaction_manager_b.isolation_level).matches("REPEATABLE READ")


def test_generic_decorators_where_we_want_to_filter_away_on_certain_generic_types():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)
    ISOLATION_CLASS_ATTRIBUTE = "__ISOLATION_LEVEL__"  # noqa: N806

    def decorator_registration_filter(registration: Registration):
        message_type = registration.generic_mapping[TMessage]
        return hasattr(message_type, ISOLATION_CLASS_ATTRIBUTE)

    def isolation_level(level: str):
        def decorator(cls: type):
            setattr(cls, ISOLATION_CLASS_ATTRIBUTE, level)
            return cls

        return decorator

    class MessageHandler(Generic[TMessage]):
        def handle(self, message: TMessage):
            pass

    class MessageA(Message):
        pass

    @isolation_level("REPEATABLE READ")
    class MessageB(Message):
        pass

    class AHandler(MessageHandler[MessageA]):
        pass

    class BHandler(MessageHandler[MessageB]):
        pass

    class TransactionManager:
        pass

    class SqlTransactionManager(TransactionManager):
        pass

    class TransactionMessageHandlerDecorator(MessageHandler[TMessage], Generic[TMessage]):
        def __init__(
            self,
            child: MessageHandler[TMessage],
            transaction_manager: TransactionManager,
        ):
            self.child = child
            self.transaction_manager = transaction_manager

        def handle(self, message: TMessage):
            self.child.handle(message)

    container = Container()

    container.register_generic_subclasses(MessageHandler)
    container.register_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        registration_filter=decorator_registration_filter,
    )

    container.register(
        TransactionManager,
        SqlTransactionManager,
    )
    handler_a = container.resolve(MessageHandler[MessageA])
    handler_b = container.resolve(MessageHandler[MessageB])

    assert_that(handler_a).matches(is_exact_type(AHandler))
    assert_that(type(handler_b).__name__).matches("__DecoratedGeneric__TransactionMessageHandlerDecorator")


def test_generic_decorators_with_different_implementations_of_the_same_dependency():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)

    class MessageHandler(Generic[TMessage]):
        def handle(self, message: TMessage):
            pass

    class MessageA(Message):
        pass

    class MessageB(Message):
        pass

    class AHandler(MessageHandler[MessageA]):
        pass

    class BHandler(MessageHandler[MessageB]):
        pass

    class TransactionManager:
        pass

    class SqlTransactionManager(TransactionManager):
        pass

    class DocDbTransactionManager(TransactionManager):
        pass

    class TransactionMessageHandlerDecorator(MessageHandler[TMessage], Generic[TMessage]):
        def __init__(
            self,
            child: MessageHandler[TMessage],
            transaction_manager: TransactionManager,
        ):
            self.child = child
            self.transaction_manager = transaction_manager

        def handle(self, message: TMessage):
            self.child.handle(message)

    def parents_message_type_is(message_type: type):
        def inner(parent: Node):
            return parent.generic_mapping[TMessage] == message_type

        return inner

    container = Container()

    container.register_generic_subclasses(MessageHandler)
    container.register_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
    )

    container.register(
        TransactionManager,
        SqlTransactionManager,
        parent_node_filter=parents_message_type_is(MessageA),
    )
    container.register(
        TransactionManager,
        DocDbTransactionManager,
        parent_node_filter=parents_message_type_is(MessageB),
    )
    handler_a = container.resolve(MessageHandler[MessageA])
    handler_b = container.resolve(MessageHandler[MessageB])

    assert_that(handler_a.transaction_manager).matches(  # type: ignore
        is_exact_type(SqlTransactionManager)
    )
    assert_that(handler_b.transaction_manager).matches(  # type: ignore
        is_exact_type(DocDbTransactionManager)
    )


def test_decorator_chooses_dependency_based_on_decorated_dependencies():
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
        def __init__(self, sql_repository: SqlRepository, doc_repository: DocRepository):
            self.sql_repository = sql_repository
            self.doc_repository = doc_repository

    class TransactionManager:
        pass

    class SqlTransactionManager(TransactionManager):
        pass

    class DocDbTransactionManager(TransactionManager):
        pass

    class TransactionMessageHandlerDecorator(MessageHandler[TMessage], Generic[TMessage]):
        def __init__(
            self,
            child: MessageHandler[TMessage],
            transaction_manager: TransactionManager,
        ):
            self.child = child
            self.transaction_manager = transaction_manager

        def handle(self, message: TMessage):
            self.child.handle(message)

    container = Container()

    container.register(DocDbConnection)
    container.register(SqlDbConnection)
    container.register(TransactionManager, SqlTransactionManager)
    container.register(TransactionManager, DocDbTransactionManager)
    container.register(DocRepository)
    container.register(SqlRepository)

    container.register_generic_subclasses(MessageHandler, subclass_type_filter=~tf.name_end_with("Decorator"))
    container.register_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        dependency_config={
            "transaction_manager": DependencySettings(filter=rf.with_implementation(DocDbTransactionManager))
        },
        decorated_node_filter=nf.has_dependant_service_type(DocDbConnection),
    )

    container.register_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        dependency_config={
            "transaction_manager": DependencySettings(filter=rf.with_implementation(SqlTransactionManager))
        },
        decorated_node_filter=nf.has_dependant_service_type(SqlDbConnection),
    )

    handler_a: Any = container.resolve(MessageHandler[MessageA])
    handler_b: Any = container.resolve(MessageHandler[MessageB])
    handler_c: Any = container.resolve(MessageHandler[MessageC])

    assert_that(handler_a.transaction_manager).matches(is_exact_type(SqlTransactionManager))
    assert_that(handler_a.child).matches(is_exact_type(AHandler))
    assert_that(handler_b.transaction_manager).matches(is_exact_type(DocDbTransactionManager))
    assert_that(handler_b.child).matches(is_exact_type(BHandler))
    assert_that(handler_c.transaction_manager).matches(is_exact_type(DocDbTransactionManager))
    assert_that(handler_c.child.transaction_manager).matches(is_exact_type(SqlTransactionManager))
    assert_that(handler_c.child.child).matches(is_exact_type(CHandler))


def test_can_filter_parent_context_based_on_registration_name():
    class Dependency:
        def __init__(self, x: int):
            self.x = x

    container = Container()

    container.register(Dependency, name="FIVE")
    container.register(Dependency, name="TEN")

    container.register(int, instance=5, parent_node_filter=nf.registration_name_is("FIVE"))
    container.register(int, instance=10, parent_node_filter=nf.registration_name_is("TEN"))

    five = container.resolve(Dependency, filter=rf.with_name("FIVE"))
    ten = container.resolve(Dependency, filter=rf.with_name("TEN"))

    assert_that(five.x).matches(5)
    assert_that(ten.x).matches(10)


def test_can_filter_parent_context_based_on_registration_tags():
    class Dependency:
        def __init__(self, x: int):
            self.x = x

    container = Container()

    container.register(Dependency, tags=[Tag("number", "FIVE")])
    container.register(Dependency, tags=[Tag("number", "TEN")])

    container.register(int, instance=5, parent_node_filter=nf.has_registartion_tag("number", "FIVE"))
    container.register(int, instance=10, parent_node_filter=nf.has_registartion_tag("number", "TEN"))

    five = container.resolve(Dependency, filter=rf.has_tag("number", "FIVE"))
    ten = container.resolve(Dependency, filter=rf.has_tag("number", "TEN"))

    assert_that(five.x).matches(5)
    assert_that(ten.x).matches(10)
