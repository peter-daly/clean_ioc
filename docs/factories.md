# Factories

Factories are callables that construct dependency instances for a registration.

```python
from clean_ioc import Container
```

## Why use factories

Use a factory when:

- construction needs conditional/runtime logic
- setup and teardown should live together
- creation depends on graph-aware services like `Resolver` or `CurrentGraph`
- you want to expose one concrete object through multiple service types

Factory parameters are dependency-injected using normal type-hint resolution.

## Function factory with injected dependencies

```python
from clean_ioc import Container, DependencySettings
from clean_ioc.registration_filters import with_name


class Settings:
    def __init__(self, dsn: str):
        self.dsn = dsn


def settings_factory(dsn: str) -> Settings:
    return Settings(dsn=dsn)


container = Container()
container.register(str, instance="postgresql://prod-db", name="prod_dsn")

# dependency_config works for factory parameters too
container.register(
    Settings,
    factory=settings_factory,
    dependency_config={"dsn": DependencySettings(filter=with_name("prod_dsn"))},
)

settings = container.resolve(Settings)
print(settings.dsn)  # postgresql://prod-db
```

## Factory with `Resolver`

```python
from clean_ioc import Container, Resolver


class Config:
    pass


class Client:
    def __init__(self, config: Config):
        self.config = config


def client_factory(resolver: Resolver) -> Client:
    # manual composition inside the factory
    return Client(config=resolver.resolve(Config))


container = Container()
container.register(Config)
container.register(Client, factory=client_factory)

client = container.resolve(Client)
print(type(client).__name__)  # Client
```

## Async function factory

Use `resolve_async` with async factories.

```python
import asyncio

from clean_ioc import Container


class Connection:
    pass


async def connection_factory() -> Connection:
    return Connection()


async def main():
    container = Container()
    container.register(Connection, factory=connection_factory)

    conn = await container.resolve_async(Connection)
    print(type(conn).__name__)  # Connection


asyncio.run(main())
```

## Generator factory (setup and teardown)

Generator factories colocate resource acquisition and release.

```python
from clean_ioc import Container, Lifespan


class Connection:
    def close(self):
        print("closed")


def connection_factory():
    conn = Connection()
    yield conn
    conn.close()


container = Container()
container.register(Connection, factory=connection_factory, lifespan=Lifespan.scoped)

with container.new_scope() as scope:
    scope.resolve(Connection)
# prints: closed
```

Cleanup timing is tied to the owning context:

- `Lifespan.scoped`: cleanup runs when the scope exits
- `Lifespan.singleton`: cleanup runs when the container exits (`with Container() as c`)
- if you resolve outside a scope/container context, cleanup callbacks are not flushed automatically

## Async generator factory

```python
import asyncio

from clean_ioc import Container, Lifespan


class Connection:
    async def close(self):
        print("closed")


async def connection_factory():
    conn = Connection()
    yield conn
    await conn.close()


async def main():
    container = Container()
    container.register(Connection, factory=connection_factory, lifespan=Lifespan.scoped)

    async with container.new_scope() as scope:
        await scope.resolve_async(Connection)


asyncio.run(main())
```

## `@contextmanager` and `@asynccontextmanager`

```python
import asyncio
from contextlib import asynccontextmanager, contextmanager

from clean_ioc import Container, Lifespan


class Connection:
    def close(self):
        print("sync close")


class AsyncConnection:
    async def close(self):
        print("async close")


@contextmanager
def sync_connection_factory():
    conn = Connection()
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def async_connection_factory():
    conn = AsyncConnection()
    try:
        yield conn
    finally:
        await conn.close()


async def main():
    container = Container()
    container.register(Connection, factory=sync_connection_factory, lifespan=Lifespan.scoped)
    container.register(AsyncConnection, factory=async_connection_factory, lifespan=Lifespan.scoped)

    with container.new_scope() as scope:
        scope.resolve(Connection)

    async with container.new_scope() as scope:
        await scope.resolve_async(AsyncConnection)


asyncio.run(main())
```

## Factory helpers (`clean_ioc.factories`)

The `clean_ioc.factories` module contains reusable factory builders.

```python
from clean_ioc.factories import create_type_mapping, use_from_current_graph, use_registered
```

### `use_registered(...)`

Resolve a different registered service within a factory.

```python
from clean_ioc import Container
from clean_ioc.factories import use_registered


class Sender:
    pass


class BatchSender:
    pass


class SenderImpl(Sender, BatchSender):
    pass


class Client:
    def __init__(self, sender: Sender, batch_sender: BatchSender):
        self.sender = sender
        self.batch_sender = batch_sender


container = Container()
container.register(SenderImpl)
container.register(Sender, factory=use_registered(SenderImpl))
container.register(BatchSender, factory=use_registered(SenderImpl))
container.register(Client)

client = container.resolve(Client)
print(client.sender is client.batch_sender)  # True
```

`use_registered(...)` can also receive a registration filter:

```python
from clean_ioc.registration_filters import with_name


class A:
    pass


class C(A):
    pass


c1 = C()
c2 = C()

container = Container()
container.register(C, instance=c1, name="C1")
container.register(C, instance=c2, name="C2")
container.register(A, factory=use_registered(C, with_name("C2")))

print(container.resolve(A) is c2)  # True
```

### `use_from_current_graph(...)`

Resolve from the current active graph.

This is useful when multiple service interfaces must share one in-graph object instance.

```python
from clean_ioc import Container
from clean_ioc.factories import use_from_current_graph


class A:
    pass


class B:
    pass


class AB(A, B):
    pass


container = Container()
container.register(A, AB)
container.register(B, factory=use_from_current_graph(AB))
```

### `create_type_mapping(...)`

Build a dictionary from all resolved registrations of one service type.

```python
from clean_ioc import Container
from clean_ioc.factories import create_type_mapping


class Handler:
    key = ""


class UserHandler(Handler):
    key = "user"


class AuditHandler(Handler):
    key = "audit"


def get_key(handler: Handler) -> str:
    return type(handler).key


container = Container()
container.register_subclasses(Handler)
container.register(dict[str, Handler], factory=create_type_mapping(Handler, key_getter=get_key))

handler_map = container.resolve(dict[str, Handler])
print(sorted(handler_map.keys()))  # ['audit', 'user']
```

Async variants are also available:

- `use_registered_async(...)`
- `use_from_current_graph_async(...)`
- `create_type_mapping_async(...)`

## Common pitfalls

- registering an async factory but calling `resolve(...)` instead of `resolve_async(...)`
- expecting generator/contextmanager cleanup without scope or container lifecycle boundaries
- missing type hints on factory parameters
- mixing factory logic and parameter value overriding (use `DependencySettings(value_factory=...)` for value override behavior)

## See also

- [Advanced: Special Dependency Types](./advanced/special-dependency-types.md)
- [Advanced: Value Factories](./advanced/value-factories.md)
