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


def test_value_factories_with_generic_decorators():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)
    ISOLATION_CLASS_ATTRIBUTE = "__ISOLATION_LEVEL__"

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

    class TransactionMessageHandlerDecorator(
        MessageHandler[TMessage], Generic[TMessage]
    ):
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

    container.register_open_generic(MessageHandler)
    container.register_open_generic_decorator(
        MessageHandler, TransactionMessageHandlerDecorator, decorated_arg="child"
    )

    container.register(
        TransactionManager,
        SqlTransactionManager,
        dependency_config={
            "isolation_level": DependencySettings(value_factory=isolation_level_factory)
        },
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
    ISOLATION_CLASS_ATTRIBUTE = "__ISOLATION_LEVEL__"

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

    class TransactionMessageHandlerDecorator(
        MessageHandler[TMessage], Generic[TMessage]
    ):
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

    container.register_open_generic(MessageHandler)
    container.register_open_generic_decorator(
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
    assert_that(type(handler_b).__name__).matches(
        "__DecoratedGeneric__TransactionMessageHandlerDecorator"
    )


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

    class TransactionMessageHandlerDecorator(
        MessageHandler[TMessage], Generic[TMessage]
    ):
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

    container.register_open_generic(MessageHandler)
    container.register_open_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
    )

    container.register(
        TransactionManager,
        SqlTransactionManager,
        parent_context_filter=lambda parent_context: parent_context.parent.generic_mapping[
            TMessage
        ]
        == MessageA,
    )
    container.register(
        TransactionManager,
        DocDbTransactionManager,
        parent_context_filter=lambda parent_context: parent_context.parent.generic_mapping[
            TMessage
        ]
        == MessageB,
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
        def __init__(
            self, sql_repository: SqlRepository, doc_repository: DocRepository
        ):
            self.sql_repository = sql_repository
            self.doc_repository = doc_repository

    class TransactionManager:
        pass

    class SqlTransactionManager(TransactionManager):
        pass

    class DocDbTransactionManager(TransactionManager):
        pass

    class TransactionMessageHandlerDecorator(
        MessageHandler[TMessage], Generic[TMessage]
    ):
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

    container.register_open_generic(
        MessageHandler, subclass_type_filter=fn_not(name_end_with("Decorator"))
    )
    container.register_open_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        dependency_config={
            "transaction_manager": DependencySettings(
                filter=with_implementation(DocDbTransactionManager)
            )
        },
        decorator_context_filter=lambda context: context.decorated.has_dependant_service_type(
            DocDbConnection
        ),
    )

    container.register_open_generic_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        dependency_config={
            "transaction_manager": DependencySettings(
                filter=with_implementation(SqlTransactionManager)
            )
        },
        decorator_context_filter=lambda context: context.decorated.has_dependant_service_type(
            SqlDbConnection
        ),
    )

    handler_a: Any = container.resolve(MessageHandler[MessageA])
    handler_b: Any = container.resolve(MessageHandler[MessageB])
    handler_c: Any = container.resolve(MessageHandler[MessageC])

    assert_that(handler_a.transaction_manager).matches(
        is_exact_type(SqlTransactionManager)
    )
    assert_that(handler_a.child).matches(is_exact_type(AHandler))
    assert_that(handler_b.transaction_manager).matches(
        is_exact_type(DocDbTransactionManager)
    )
    assert_that(handler_b.child).matches(is_exact_type(BHandler))
    assert_that(handler_c.transaction_manager).matches(
        is_exact_type(DocDbTransactionManager)
    )
    assert_that(handler_c.child.transaction_manager).matches(
        is_exact_type(SqlTransactionManager)
    )
    assert_that(handler_c.child.child).matches(is_exact_type(CHandler))


@pytest.mark.skip("Cached instances currently lose their graph information")
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
