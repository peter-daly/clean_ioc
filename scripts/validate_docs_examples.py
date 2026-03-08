"""Validate key documentation examples as runnable smoke tests."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from typing import Generic, Protocol, TypeVar

import clean_ioc.value_factories as vf
from clean_ioc import Container, DependencyContext, DependencySettings, Lifespan, Resolver, Tag
from clean_ioc.factories import use_from_current_graph
from clean_ioc.registration_filters import has_tag, with_name


def _assert(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def validate_registration_modes():
    class Repo:
        def value(self) -> int:
            return 1

    class RepoImpl(Repo):
        pass

    class Service:
        def __init__(self, repo: Repo):
            self.repo = repo

    class Config:
        def __init__(self, env: str):
            self.env = env

    container = Container()
    container.register(Repo, RepoImpl)
    container.register(Service)
    _assert(isinstance(container.resolve(Service).repo, RepoImpl), "implementation registration failed")

    container = Container()
    container.register(RepoImpl)
    _assert(isinstance(container.resolve(RepoImpl), RepoImpl), "concrete registration failed")

    container = Container()

    def config_factory() -> Config:
        return Config(env="prod")

    container.register(Config, factory=config_factory)
    _assert(container.resolve(Config).env == "prod", "factory registration failed")

    container = Container()
    cfg = Config(env="test")
    container.register(Config, instance=cfg)
    _assert(container.resolve(Config) is cfg, "instance registration failed")


def validate_filtering():
    container = Container()
    container.register(str, instance="dev", name="dev")
    container.register(str, instance="prod", tags=[Tag("env", "prod")])
    container.register(str, instance="staging", tags=[Tag("env", "staging")])

    _assert(container.resolve(str, filter=with_name("dev")) == "dev", "with_name filtering failed")
    _assert(container.resolve(str, filter=has_tag("env", "prod")) == "prod", "tag filtering failed")


def validate_lifespans_and_scopes():
    class A:
        pass

    container = Container()
    container.register(A, lifespan=Lifespan.singleton)
    _assert(container.resolve(A) is container.resolve(A), "singleton reuse failed")

    container = Container()
    container.register(A, lifespan=Lifespan.transient)
    _assert(container.resolve(A) is not container.resolve(A), "transient reuse failed")

    container = Container()
    container.register(A, lifespan=Lifespan.scoped)
    with container.new_scope() as s1:
        a1 = s1.resolve(A)
        a2 = s1.resolve(A)
        _assert(a1 is a2, "scoped same-scope reuse failed")
    with container.new_scope() as s2:
        a3 = s2.resolve(A)
    _assert(a1 is not a3, "scoped cross-scope isolation failed")


def validate_decorators():
    class Sender(Protocol):
        def send(self, text: str) -> str: ...

    class BaseSender:
        def send(self, text: str) -> str:
            return f"base:{text}"

    class LogDec:
        def __init__(self, child: Sender):
            self.child = child

        def send(self, text: str) -> str:
            return f"log:{self.child.send(text)}"

    class MetricsDec:
        def __init__(self, child: Sender):
            self.child = child

        def send(self, text: str) -> str:
            return f"metrics:{self.child.send(text)}"

    container = Container()
    container.register(Sender, BaseSender)
    container.register_decorator(Sender, LogDec, position=0)
    container.register_decorator(Sender, MetricsDec, position=10)
    value = container.resolve(Sender).send("x")
    _assert(value == "metrics:log:base:x", "decorator ordering failed")


def validate_value_factories():
    class Client:
        def __init__(self, number: int = 10):
            self.number = number

    container = Container()
    container.register(int, instance=2)
    container.register(
        Client,
        name="default",
        dependency_config={"number": DependencySettings(value_factory=vf.use_default_value)},
    )
    container.register(
        Client,
        name="resolved",
        dependency_config={"number": DependencySettings(value_factory=vf.dont_use_default_value)},
    )
    _assert(container.resolve(Client, filter=with_name("default")).number == 10, "use_default_value failed")
    _assert(container.resolve(Client, filter=with_name("resolved")).number == 2, "dont_use_default_value failed")


def validate_special_dependency_types():
    class Logger:
        def __init__(self, module_name: str):
            self.module_name = module_name

    class Client:
        def __init__(self, logger: Logger):
            self.logger = logger

    def logger_factory(context: DependencyContext) -> Logger:
        return Logger(module_name=context.parent.implementation.__module__)

    container = Container()
    container.register(Logger, factory=logger_factory, lifespan=Lifespan.transient)
    container.register(Client)
    client = container.resolve(Client)
    _assert(client.logger.module_name == __name__, "DependencyContext factory failed")

    class Sender:
        pass

    class BatchSender:
        pass

    class SenderImpl(Sender, BatchSender):
        pass

    class UsesBoth:
        def __init__(self, sender: Sender, batch_sender: BatchSender):
            self.sender = sender
            self.batch_sender = batch_sender

    container = Container()
    container.register(Sender, SenderImpl)
    container.register(BatchSender, factory=use_from_current_graph(SenderImpl))
    container.register(UsesBoth)
    obj = container.resolve(UsesBoth)
    _assert(obj.sender is obj.batch_sender, "CurrentGraph helper failed")


def validate_generics():
    T = TypeVar("T")

    class Event:
        pass

    class AEvent(Event):
        pass

    class BEvent(Event):
        pass

    class Handler(Generic[T]):
        def value(self) -> str:
            raise NotImplementedError

    class AHandler(Handler[AEvent]):
        def value(self) -> str:
            return "A"

    class BHandler(Handler[BEvent]):
        def value(self) -> str:
            return "B"

    container = Container()
    container.register_generic_subclasses(Handler)
    _assert(container.resolve(Handler[AEvent]).value() == "A", "generic subclass A failed")
    _assert(container.resolve(Handler[BEvent]).value() == "B", "generic subclass B failed")


async def validate_async_factories():
    class Token:
        def __init__(self, value: str):
            self.value = value

    async def token_factory() -> Token:
        return Token("abc")

    @asynccontextmanager
    async def token_cm_factory():
        token = Token("cm")
        yield token

    container = Container()
    container.register(Token, factory=token_factory)
    token = await container.resolve_async(Token)
    _assert(token.value == "abc", "async function factory failed")

    container = Container()
    container.register(Token, factory=token_cm_factory, lifespan=Lifespan.scoped)
    async with container.new_scope() as scope:
        token = await scope.resolve_async(Token)
        _assert(token.value == "cm", "async contextmanager factory failed")


def validate_generator_factories():
    class Conn:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    last_conn: Conn | None = None

    @contextmanager
    def conn_factory():
        nonlocal last_conn
        conn = Conn()
        last_conn = conn
        try:
            yield conn
        finally:
            conn.close()

    container = Container()
    container.register(Conn, factory=conn_factory, lifespan=Lifespan.scoped)
    with container.new_scope() as scope:
        scope.resolve(Conn)
    _assert(last_conn is not None and last_conn.closed, "contextmanager teardown failed")


def validate_resolver_injection():
    class Client:
        def __init__(self, resolver: Resolver):
            self.resolver = resolver

        def number(self):
            return self.resolver.resolve(int)

    container = Container()
    container.register(int, instance=1)
    container.register(Client)
    _assert(container.resolve(Client).number() == 1, "resolver injection failed")

    with container.new_scope() as scope:
        scope.register(int, instance=10)
        _assert(scope.resolve(Client).number() == 10, "scope resolver override failed")


def main():
    validate_registration_modes()
    validate_filtering()
    validate_lifespans_and_scopes()
    validate_decorators()
    validate_value_factories()
    validate_special_dependency_types()
    validate_generics()
    validate_generator_factories()
    validate_resolver_injection()
    asyncio.run(validate_async_factories())
    print("All documentation example validations passed.")


if __name__ == "__main__":
    main()
