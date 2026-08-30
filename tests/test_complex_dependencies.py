# from __future__ import annotations
from typing import Any, Generic, Protocol, TypeVar

from assertive import (
    is_exact_type,
)
from typetoolbox.generics import GenericTypeMap

import clean_ioc.component_filters as cf
import clean_ioc.type_filters as tf
from clean_ioc import (
    Component,
    ContainerBuilder,
    DependencyContext,
    DependencySettings,
    Tag,
)
from clean_ioc.factories import use_component


def test_value_factories_with_generic_decorators():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)
    ISOLATION_CLASS_ATTRIBUTE = "__ISOLATION_LEVEL__"  # noqa: N806

    def isolation_level_factory(default_value: Any, context: DependencyContext):
        assert context.parent is not None
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

    builder = ContainerBuilder()

    builder.register_generic_subclasses(MessageHandler)
    builder.register_decorator(MessageHandler, TransactionMessageHandlerDecorator, decorated_arg="child")

    builder.register(
        TransactionManager,
        SqlTransactionManager,
        dependency_config={"isolation_level": DependencySettings(value_factory=isolation_level_factory)},
    )
    container = builder.build()
    handler_a: TransactionMessageHandlerDecorator[MessageA] = container.resolve(
        MessageHandler[MessageA]
    )  # ty:ignore[invalid-assignment]
    handler_b: TransactionMessageHandlerDecorator[MessageB] = container.resolve(
        MessageHandler[MessageB]
    )  # ty:ignore[invalid-assignment]

    transaction_manager_a: SqlTransactionManager = handler_a.transaction_manager  # type: ignore
    transaction_manager_b: SqlTransactionManager = handler_b.transaction_manager  # type: ignore

    assert transaction_manager_a.isolation_level is None
    assert transaction_manager_b.isolation_level == "REPEATABLE READ"


def test_generic_decorators_where_we_want_to_filter_away_on_certain_generic_types():
    class Message:
        pass

    TMessage = TypeVar("TMessage", bound=Message)
    ISOLATION_CLASS_ATTRIBUTE = "__ISOLATION_LEVEL__"  # noqa: N806

    def decorator_registration_filter(registration: Component):
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

    builder = ContainerBuilder()

    builder.register_generic_subclasses(MessageHandler)
    builder.register_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        when=decorator_registration_filter,
    )

    builder.register(
        TransactionManager,
        SqlTransactionManager,
    )
    container = builder.build()
    handler_a = container.resolve(MessageHandler[MessageA])
    handler_b = container.resolve(MessageHandler[MessageB])

    assert handler_a == is_exact_type(AHandler)
    assert type(handler_b).__name__ == "__DecoratedGeneric__TransactionMessageHandlerDecorator"


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
        def inner(parent: Component):
            return parent.generic_mapping[TMessage] == message_type

        return inner

    builder = ContainerBuilder()

    builder.register_generic_subclasses(MessageHandler)
    builder.register_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
    )

    builder.register(
        TransactionManager,
        SqlTransactionManager,
        when=cf.parent(parents_message_type_is(MessageA)),
    )
    builder.register(
        TransactionManager,
        DocDbTransactionManager,
        when=cf.parent(parents_message_type_is(MessageB)),
    )
    container = builder.build()
    handler_a = container.resolve(MessageHandler[MessageA])
    handler_b = container.resolve(MessageHandler[MessageB])

    assert handler_a.transaction_manager == is_exact_type(SqlTransactionManager)  # type: ignore
    assert handler_b.transaction_manager == is_exact_type(DocDbTransactionManager)  # type: ignore


def test_generic_decorator_can_set_the_generic_args_of_a_dependency_with_different_generic_args():
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

    builder = ContainerBuilder()

    builder.register(DocDbConnection)
    builder.register(SqlDbConnection)
    builder.register(TransactionManager, SqlTransactionManager)
    builder.register(TransactionManager, DocDbTransactionManager)
    builder.register(DocRepository)
    builder.register(SqlRepository)

    builder.register_generic_subclasses(MessageHandler, subclass_type_filter=~tf.name_end_with("Decorator"))
    builder.register_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        dependency_config={
            "transaction_manager": DependencySettings(filter=cf.implementation_is(DocDbTransactionManager))
        },
        when=cf.has_descendant(cf.service_type_is(DocDbConnection)),
    )

    builder.register_decorator(
        MessageHandler,
        TransactionMessageHandlerDecorator,
        decorated_arg="child",
        dependency_config={
            "transaction_manager": DependencySettings(filter=cf.implementation_is(SqlTransactionManager))
        },
        when=cf.has_descendant(cf.service_type_is(SqlDbConnection)),
    )

    container = builder.build()
    handler_a: Any = container.resolve(MessageHandler[MessageA])
    handler_b: Any = container.resolve(MessageHandler[MessageB])
    handler_c: Any = container.resolve(MessageHandler[MessageC])

    assert handler_a.transaction_manager == is_exact_type(SqlTransactionManager)
    assert handler_a.child == is_exact_type(AHandler)
    assert handler_b.transaction_manager == is_exact_type(DocDbTransactionManager)
    assert handler_b.child == is_exact_type(BHandler)
    assert handler_c.transaction_manager == is_exact_type(DocDbTransactionManager)
    assert handler_c.child.transaction_manager == is_exact_type(SqlTransactionManager)
    assert handler_c.child.child == is_exact_type(CHandler)


def test_can_filter_parent_based_on_registration_name():
    class Dependency:
        def __init__(self, x: int):
            self.x = x

    builder = ContainerBuilder()

    builder.register(Dependency, name="FIVE")
    builder.register(Dependency, name="TEN")

    builder.register(int, instance=5, when=cf.parent(cf.with_name("FIVE")))
    builder.register(int, instance=10, when=cf.parent(cf.with_name("TEN")))

    container = builder.build()
    five = container.resolve(Dependency, filter=cf.with_name("FIVE"))
    ten = container.resolve(Dependency, filter=cf.with_name("TEN"))

    assert five.x == 5
    assert ten.x == 10


def test_can_filter_parent_based_on_registration_tags():
    class Dependency:
        def __init__(self, x: int):
            self.x = x

    builder = ContainerBuilder()

    builder.register(Dependency, tags=[Tag("number", "FIVE")])
    builder.register(Dependency, tags=[Tag("number", "TEN")])

    builder.register(int, instance=5, when=cf.parent(cf.has_tag("number", "FIVE")))
    builder.register(int, instance=10, when=cf.parent(cf.has_tag("number", "TEN")))

    container = builder.build()
    five = container.resolve(Dependency, filter=cf.has_tag("number", "FIVE"))
    ten = container.resolve(Dependency, filter=cf.has_tag("number", "TEN"))

    assert five.x == 5
    assert ten.x == 10


def test_generic_shared_dependency_among_different_generic_decorator_types_with_different_fallbacks():
    class Command:
        pass

    TCommand = TypeVar("TCommand", bound=Command, covariant=True)

    class Query:
        pass

    TQuery = TypeVar("TQuery", bound=Query)

    class CommandA(Command):
        pass

    class CommandB(Command):
        pass

    class QueryC(Query):
        pass

    class QueryD(Query):
        pass

    class CommandHandler(Protocol[TCommand]):
        pass

    class QueryHandler(Generic[TQuery]):
        pass

    class AHandler(CommandHandler[CommandA]):
        pass

    class BHandler(CommandHandler[CommandB]):
        pass

    class CHandler(QueryHandler[QueryC]):
        pass

    class DHandler(QueryHandler[QueryD]):
        pass

    TContext = TypeVar("TContext")

    class ContextGetter(Generic[TContext]):
        pass

    class BasicCommandContextGetter(ContextGetter[Command]):
        pass

    class CommandAContextGetter(ContextGetter[CommandA]):
        pass

    class BasicQueryContextGetter(ContextGetter[Query]):
        pass

    class QueryDContextGetter(ContextGetter[QueryD]):
        pass

    class CommandContextDecorator(Generic[TCommand]):
        def __init__(self, handler: CommandHandler[TCommand], context_getter: ContextGetter[TCommand]):
            self.handler = handler
            self.context_getter = context_getter
            pass

    class QueryContextDecorator(Generic[TQuery]):
        def __init__(self, handler: QueryHandler[TQuery], context_getter: ContextGetter[TQuery]):
            self.handler = handler
            self.context_getter = context_getter
            pass

    builder = ContainerBuilder()

    builder.register_generic_subclasses(
        ContextGetter,
        fallback_type=BasicCommandContextGetter,
        when=cf.parent(cf.implementation_matches_type_filter(tf.is_subclass_of(CommandContextDecorator))),
    )

    builder.register_generic_subclasses(
        ContextGetter,
        fallback_type=BasicQueryContextGetter,
        when=cf.parent(cf.implementation_matches_type_filter(tf.is_subclass_of(QueryContextDecorator))),
    )

    builder.register_generic_subclasses(CommandHandler)
    builder.register_generic_subclasses(QueryHandler)

    builder.register_decorator(CommandHandler, CommandContextDecorator)
    builder.register_decorator(QueryHandler, QueryContextDecorator)

    container = builder.build()
    command_handler_a: CommandContextDecorator = container.resolve(CommandHandler[CommandA])  # type: ignore
    command_handler_b: CommandContextDecorator = container.resolve(CommandHandler[CommandB])  # type: ignore
    query_handler_c: QueryContextDecorator = container.resolve(QueryHandler[QueryC])  # type: ignore
    query_handler_d: QueryContextDecorator = container.resolve(QueryHandler[QueryD])  # type: ignore

    assert command_handler_a.context_getter == is_exact_type(CommandAContextGetter)
    assert command_handler_a.handler == is_exact_type(AHandler)

    assert command_handler_b.context_getter == is_exact_type(BasicCommandContextGetter)
    assert command_handler_b.handler == is_exact_type(BHandler)

    assert query_handler_c.context_getter == is_exact_type(BasicQueryContextGetter)
    assert query_handler_c.handler == is_exact_type(CHandler)

    assert query_handler_d.context_getter == is_exact_type(QueryDContextGetter)
    assert query_handler_d.handler == is_exact_type(DHandler)


def test_use_component_factory_with_multiple_base_classes():
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

    builder = ContainerBuilder()

    builder.register(A, AB, lifespan="scoped")
    builder.register(B, factory=use_component(AB), lifespan="scoped")
    builder.register(C, lifespan="scoped")

    container = builder.build()
    b_component = next(component for component in container.components if component.service_type is B)
    assert any(component.service_type is AB for component in b_component.dependencies)
    with container.new_scope() as scope:
        c = scope.resolve(C)

        assert c.a is c.b


def test_generic_decorator_when_decorator_decoprates_common_base_classes():
    TThing = TypeVar("TThing")

    class ThingDoer(Generic[TThing]):
        pass

    class DefaultThingDoer(ThingDoer[Any]):
        pass

    TOperation = TypeVar("TOperation", contravariant=True)
    TOperationResult = TypeVar("TOperationResult", covariant=True)

    class OperationHandler(Protocol[TOperation, TOperationResult]):
        def handle(self, operation: TOperation, /) -> TOperationResult: ...

    class OperationDecorator(Generic[TOperation, TOperationResult]):
        def __init__(self, handler: OperationHandler[TOperation, TOperationResult], thing_doer: ThingDoer[TOperation]):
            self.handler = handler
            self.thing_doer = thing_doer

        def handle(self, operation: TOperation) -> TOperationResult:
            return self.handler.handle(operation)

    class Command:
        pass

    class CommandResult:
        pass

    TCommand = TypeVar("TCommand", bound=Command, contravariant=True)

    class ACommand(Command):
        pass

    class CommandHandler(OperationHandler[TCommand, CommandResult], Protocol[TCommand]):
        def handle(self, command: TCommand) -> CommandResult: ...

    class AHandler(CommandHandler[ACommand]):
        def handle(self, command: ACommand) -> CommandResult:
            return CommandResult()

    class Query:
        pass

    class QueryResult:
        pass

    TQuery = TypeVar("TQuery", bound=Query, contravariant=True)
    TQueryResult = TypeVar("TQueryResult", bound=QueryResult, covariant=True)

    class QueryHandler(OperationHandler[TQuery, TQueryResult], Protocol[TQuery, TQueryResult]):
        def handle(self, query: TQuery) -> TQueryResult: ...

    class BQuery(Query):
        pass

    class BResult(QueryResult):
        pass

    class BHandler(QueryHandler[BQuery, BResult]):
        def handle(self, query: BQuery) -> BResult:
            return BResult()

    class Event:
        pass

    TEvent = TypeVar("TEvent", bound=Event, contravariant=True)

    class EventHandler(OperationHandler[TEvent, None], Protocol[TEvent]):
        def handle(self, event: TEvent) -> None: ...

    class CEvent(Event):
        pass

    class CHandler(EventHandler[CEvent]):
        def handle(self, event: CEvent) -> None:
            pass

    class DoAThingWithCEvent(ThingDoer[CEvent]):
        pass

    builder = ContainerBuilder()

    builder.register_generic_subclasses(CommandHandler)
    builder.register_generic_subclasses(QueryHandler)
    builder.register_generic_subclasses(EventHandler)
    builder.register_generic_subclasses(ThingDoer, fallback_type=DefaultThingDoer)

    builder.register_decorator(CommandHandler, OperationDecorator, decorated_arg="handler")
    builder.register_decorator(QueryHandler, OperationDecorator, decorated_arg="handler")
    builder.register_decorator(EventHandler, OperationDecorator, decorated_arg="handler")

    container = builder.build()
    command_handler: OperationDecorator = container.resolve(CommandHandler[ACommand])  # type: ignore
    query_handler: OperationDecorator = container.resolve(QueryHandler[BQuery, BResult])  # type: ignore
    event_handler: OperationDecorator = container.resolve(EventHandler[CEvent])  # type: ignore

    assert command_handler.thing_doer == is_exact_type(DefaultThingDoer)
    assert query_handler.thing_doer == is_exact_type(DefaultThingDoer)
    assert event_handler.thing_doer == is_exact_type(DoAThingWithCEvent)

    assert command_handler.handler == is_exact_type(AHandler)
    assert query_handler.handler == is_exact_type(BHandler)
    assert event_handler.handler == is_exact_type(CHandler)


def test_generic_decorator_when_decorator_decoprates_common_base_classes_can_have_different_dependencies():
    TThing = TypeVar("TThing")

    class ThingDoer(Generic[TThing]):
        pass

    TOperation = TypeVar("TOperation", contravariant=True)
    TOperationResult = TypeVar("TOperationResult", covariant=True)

    class OperationHandler(Protocol[TOperation, TOperationResult]):
        def handle(self, operation: TOperation, /) -> TOperationResult: ...

    class OperationDecorator(Generic[TOperation, TOperationResult]):
        def __init__(self, handler: OperationHandler[TOperation, TOperationResult], thing_doer: ThingDoer[TOperation]):
            self.handler = handler
            self.thing_doer = thing_doer

        def handle(self, operation: TOperation) -> TOperationResult:
            return self.handler.handle(operation)

    class Command:
        pass

    class CommandResult:
        pass

    TCommand = TypeVar("TCommand", bound=Command, contravariant=True)

    class ACommand(Command):
        pass

    class BCommand(Command):
        pass

    class CommandHandler(OperationHandler[TCommand, CommandResult], Protocol[TCommand]):
        def handle(self, command: TCommand) -> CommandResult: ...

    class AHandler(CommandHandler[ACommand]):
        def handle(self, command: ACommand) -> CommandResult:
            return CommandResult()

    class BHandler(CommandHandler[BCommand]):
        def handle(self, command: BCommand) -> CommandResult:
            return CommandResult()

    class Event:
        pass

    TEvent = TypeVar("TEvent", bound=Event, contravariant=True)

    class EventHandler(OperationHandler[TEvent, None], Protocol[TEvent]):
        def handle(self, event: TEvent) -> None: ...

    class CEvent(Event):
        pass

    class DEvent(Event):
        pass

    class CHandler(EventHandler[CEvent]):
        def handle(self, event: CEvent) -> None:
            pass

    class DHandler(EventHandler[DEvent]):
        def handle(self, event: DEvent) -> None:
            pass

    class DoAThingWithCommand(ThingDoer[Command]):
        pass

    class DoAThingWithBCommand(ThingDoer[BCommand]):
        pass

    class DoAThingWithEvent(ThingDoer[Event]):
        pass

    class DoAThingWithCEvent(ThingDoer[CEvent]):
        pass

    def thing_doer_type_filter(parent: type):
        def is_subclass_of_parent(subclass: type):
            generic_type_map = GenericTypeMap(subclass)
            generic_type = generic_type_map["TThing"]
            return issubclass(generic_type, parent)

        return is_subclass_of_parent

    builder = ContainerBuilder()

    builder.register_generic_subclasses(
        ThingDoer,
        fallback_type=DoAThingWithCommand,
        subclass_type_filter=thing_doer_type_filter(Command),
        tags=[Tag("command")],
    )

    builder.register_generic_subclasses(
        ThingDoer,
        fallback_type=DoAThingWithEvent,
        subclass_type_filter=thing_doer_type_filter(Event),
        tags=[Tag("event")],
    )

    builder.register_generic_subclasses(CommandHandler)
    builder.register_generic_subclasses(EventHandler)
    builder.register_decorator(
        CommandHandler,
        OperationDecorator,
        decorated_arg="handler",
        dependency_config={"thing_doer": DependencySettings(filter=cf.has_tag("command"))},
    )

    builder.register_decorator(
        EventHandler,
        OperationDecorator,
        decorated_arg="handler",
        dependency_config={"thing_doer": DependencySettings(filter=cf.has_tag("event"))},
    )

    container = builder.build()
    a_handler: OperationDecorator = container.resolve(CommandHandler[ACommand])  # type: ignore
    b_handler: OperationDecorator = container.resolve(CommandHandler[BCommand])  # type: ignore
    c_handler: OperationDecorator = container.resolve(EventHandler[CEvent])  # type: ignore
    d_handler: OperationDecorator = container.resolve(EventHandler[DEvent])  # type: ignore

    assert a_handler.thing_doer == is_exact_type(DoAThingWithCommand)
    assert b_handler.thing_doer == is_exact_type(DoAThingWithBCommand)
    assert c_handler.thing_doer == is_exact_type(DoAThingWithCEvent)
    assert d_handler.thing_doer == is_exact_type(DoAThingWithEvent)


def test_can_register_a_generic_type_that_has_been_dynamically_created_with_a_generic_dependency():
    T = TypeVar("T")

    class GenericDependency(Generic[T]):
        pass

    class GenericClass(Generic[T]):
        def __init__(self, value: T, dependency: GenericDependency[T]):
            self.value = value
            self.dependency = dependency

    class A:
        pass

    class MyClass(GenericClass[A]):
        pass

    class MyDepedency(GenericDependency[A]):
        pass

    builder = ContainerBuilder()

    builder.register(GenericClass[A], MyClass)
    builder.register(GenericDependency[A], MyDepedency)
    builder.register(A)

    container = builder.build()
    instance = container.resolve(GenericClass[A])
    assert isinstance(instance, MyClass)
    assert isinstance(instance.value, A)
    assert isinstance(instance.dependency, MyDepedency)


def test_generic_decorator_type_is_memoised_across_containers():
    """Repeated container builds must not mint fresh decorator classes.

    create_generic_decorator_type used to call types.new_class on every
    invocation; each new class was then pinned for the life of the process by
    typing's parameterisation caches, so applications that build a container
    per test/request leaked thousands of classes per build.
    """
    TMessage = TypeVar("TMessage")

    class MessageA:
        pass

    class MessageHandler(Generic[TMessage]):
        def handle(self, message: TMessage):
            pass

    class AHandler(MessageHandler[MessageA]):
        pass

    class LoggingDecorator(MessageHandler[TMessage], Generic[TMessage]):
        def __init__(self, child: MessageHandler[TMessage]):
            self.child = child

        def handle(self, message: TMessage):
            self.child.handle(message)

    def build_container():
        builder = ContainerBuilder()
        builder.register_generic_subclasses(MessageHandler)
        builder.register_decorator(MessageHandler, LoggingDecorator, decorated_arg="child")
        return builder.build()

    handler_1 = build_container().resolve(MessageHandler[MessageA])
    handler_2 = build_container().resolve(MessageHandler[MessageA])

    assert handler_1 is not handler_2
    assert type(handler_1) is type(handler_2)
    assert isinstance(handler_1, LoggingDecorator)
    assert isinstance(handler_1.child, AHandler)  # type: ignore[attr-defined]
