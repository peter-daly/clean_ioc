# Scopes

A scope is a child container with its own scoped-instance cache.
Create scopes with `new_scope()`.

```python
from clean_ioc import Container, Lifespan
```

## Basic scope usage

```python
class DbConnection:
    def run_sql(self, statement: str):
        print(statement)


container = Container()
container.register(DbConnection, lifespan=Lifespan.scoped)

with container.new_scope() as scope:
    db1 = scope.resolve(DbConnection)
    db2 = scope.resolve(DbConnection)
    print(db1 is db2)  # True
```

## Async scope usage

```python
import asyncio

from clean_ioc import Container, Lifespan


class AsyncDbConnection:
    async def run_sql(self, statement: str):
        print(statement)


async def main():
    container = Container()
    container.register(AsyncDbConnection, lifespan=Lifespan.scoped)

    async with container.new_scope() as scope:
        db = await scope.resolve_async(AsyncDbConnection)
        await db.run_sql("SELECT 1")


asyncio.run(main())
```

## Scoped teardown

Use `scoped_teardown` for scoped registrations.

```python
class DbConnection:
    def close(self):
        print("CLOSING")


def close_connection(conn: DbConnection):
    conn.close()


container = Container()
container.register(DbConnection, lifespan=Lifespan.scoped, scoped_teardown=close_connection)

with container.new_scope() as scope:
    scope.resolve(DbConnection)
# prints CLOSING
```

## Generator factories as teardown alternative

You can colocate setup/teardown in a single factory.

```python
from contextlib import contextmanager


class DbConnection:
    def close(self):
        print("CLOSING")


@contextmanager
def connection_factory():
    conn = DbConnection()
    try:
        yield conn
    finally:
        conn.close()


container = Container()
container.register(DbConnection, lifespan=Lifespan.scoped, factory=connection_factory)

with container.new_scope() as scope:
    scope.resolve(DbConnection)
# prints CLOSING
```

## Scope-local overrides

Registrations on a scope override parent registrations for that scope.

```python
container = Container()
container.register(int, instance=1)

with container.new_scope() as scope:
    scope.register(int, instance=2)
    print(scope.resolve(int))      # 2

print(container.resolve(int))      # 1
```

## Nested scopes

Child scopes can still access parent scoped/singleton instances.

```python
container = Container()
container.register(str, instance="root")

with container.new_scope() as parent:
    parent.register(int, instance=10)

    with parent.new_scope() as child:
        print(child.resolve(int))  # 10
        print(child.resolve(str))  # root
```
