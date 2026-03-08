# Factories

Factories are callables used to build dependency instances.

```python
from clean_ioc import Container
```

## Function factory

```python
class Connection:
    pass


def connection_factory() -> Connection:
    return Connection()


container = Container()
container.register(Connection, factory=connection_factory)

conn = container.resolve(Connection)
print(type(conn).__name__)  # Connection
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
    print(type(conn).__name__)


asyncio.run(main())
```

## Generator factory (setup/teardown)

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
