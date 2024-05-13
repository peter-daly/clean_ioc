# Scopes

Scopes allow you to define a dependency that will stay alive for a period of time (while the scope is alive).
Some examples where scopes are useful are:
 - http request in a web server
 - message/event if working on a message based system
 - a thread cotext

For instance you could set up that an single database connection open for a scope
```python
class DbConnection:
    def run_sql(self, statement):
        # Done some sql Stuff
        pass

container.register(DbConnection, lifespan=Lifespan.scoped)

with container.get_scope() as scope:
    db_conn = scope.resolve(DbConnection)
    db_conn.run_sql("UPDATE table SET column = 1")

    db_conn_2 = scope.resolve(DbConnection) # Same DbConnection instance
    db_conn_2.run_sql("UPDATE table SET column = 2")

```

Scopes can also be use with asyncio

```python
class AsyncDbConnection:
    async def run_sql(self, statement):
        # Done some sql Stuff
        pass

container.register(AsyncDbConnection, lifespan=Lifespan.scoped)

async with container.get_scope() as scope:
    db_conn = scope.resolve(AsyncDbConnection)
    await db_conn.run_sql("UPDATE table SET column = 1")
```


## Scoped Teardowns
When registering a component you have the option to run a teardown function after the scope is complete
```python
class AsyncDbConnection:
    async def run_sql(self, statement):
        # Done some sql Stuff
        pass
    async def close(self):
        # Close the connection
        pass

async def close_connection(conn: AsyncDbConnection):
    print('CLOSING CONNECTION')
    await conn.close()

container.register(DbConnection, lifespan=Lifespan.scoped, scoped_teardown=close_connection)

async with container.get_scope() as scope:
    db_conn = scope.resolve(AsyncDbConnection)
    await db_conn.run_sql("UPDATE table SET column = 1")

# prints CLOSING CONNECTION
```


## Scopes with generator factories

If you use a generator or async generator as a factory when a scope ends it can run more teardown functions in the factory

```python
class AsyncDbConnection:
    async def run_sql(self, statement):
        # Done some sql Stuff
        pass
    async def close(self):
        # Close the connection
        pass

async def connection_factory(conn: AsyncDbConnection):
    connection = AsyncDbConnection()
    yield connection
    print('CLOSING CONNECTION')
    await conn.close()


container.register(DbConnection, lifespan=Lifespan.scoped, factory=close_connection)

async with container.get_scope() as scope:
    db_conn = await scope.resolve_async(AsyncDbConnection)
    await db_conn.run_sql("UPDATE table SET column = 1")

# prints CLOSING CONNECTION
```


!!! Question "Should I use factory generators or scoped teardowns is there any difference?"
    For the purposes above both serve the same purpose so it's really up the the user's taste to see what they want to use. Generators come in useful if the object being returned is a context manager or async context manager, which can be the case in a lot of db connection libraries.

    ```python
    class AsyncDbConnection:
        async def run_sql(self, statement):
            # Done some sql Stuff
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.close()

        async def close(self):
            # Close the connection
            pass

    async def connection_factory(conn: AsyncDbConnection):
        async AsyncDbConnection() as conn:
            yield connection


    container.register(DbConnection, lifespan=Lifespan.scoped, factory=close_connection)

    async with container.get_scope() as scope:
        db_conn = await scope.resolve_async(AsyncDbConnection)
        await db_conn.run_sql("UPDATE table SET column = 1")
    ```


## Registering within scopes
Each scope has it's own registry which enables you to register new dependencies that are available within the scope.
When within new scopes you can register dependencies that will live within the scope.

```python

container = Container()

container.register(int, instance=1)
container.register(float, instance=1.0)

with container.get_scope() as scope:
    scope.register(int, instance=2)
    scope.resolve(int) # returns 2
    scope.resolve(float) # returns 1.0

container.resolve(int) # returns 1
container.resolve(float) # returns 1.0

```

An exampes of this is if you have a scope that you use for a web request and you want to register the CurrentUser within the dependencies.


## Nesting scopes

When within a scope you create new child scopes. Any scoped object that is created in the parent scope will be available in the child scope.

```python

container = Container()

container.register(int, instance=1)
container.register(float, instance=1.0)
with container.get_scope() as scope:
    scope.register(int, instance=2)
    with scope.get_scope() as inner_scope:
        inner_scope.register(int, instance=3)
        inner_scope.resolve(int) # returns 3
        inner_scope.resolve(float) # returns 1.0
    scope.resolve(int) # returns 2
    scope.resolve(float) # returns 1.0

container.resolve(int) # returns 1
container.resolve(float) # returns 1.0
```



## The container is just the root scope

As you may have noticed the a lot of the things you can do in a container you can do in a scope, this is because the container is just the root scope. If you use the container a context manager or async context manager then you can apply teardowns to objects from the container.

```python
class AsyncDbConnection:
    async def run_sql(self, statement):
        # Done some sql Stuff
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        # Close the connection
        pass

async def connection_factory(conn: AsyncDbConnection):
    async AsyncDbConnection() as conn:
        yield connection


container.register(DbConnection, lifespan=Lifespan.scoped, factory=close_connection)

async with container:
    db_conn = await scope.resolve_async(AsyncDbConnection)
    await db_conn.run_sql("UPDATE table SET column = 1")
```