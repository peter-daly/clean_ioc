# Factories

Factories are just Callables that can be return your dependency. Factories can be useful if you need to your implementation to be dynamic based on the context/state of your application or current dependencies in the graph.
Factories can also have dependencies.

## Function
The most basic factory is using a function

```python

class DbUserRepository:
    def __init__(self, connection: Connection):
        self.dep = dep

    def get_user(self, id: str):
        ## DB Logic to get user
        pass

def connection_factory():
    ## DO initialisation to get the connection
    return Connection()


container = Container()
container.register(Connection, factory=connection_factory)
container.register(UserRepository, DbUserRepository)

repo = container.resolve(UserRepository)

user = repo.get_user(10)
```


## Async Function (Coroutine)


!!! warning
    Async function factories must only run when using ***resolve_async***

```python

class DbUserRepository:
    def __init__(self, connection: Connection):
        self.dep = dep

    async def get_user(self, id: str):
        ## DB Logic to get user
        pass

async def connection_factory():
    ## Do some asyncio operations
    return Connection()


container = Container()
container.register(Connection, factory=connection_factory)
container.register(UserRepository, DbUserRepository)

repo = await container.resolve_async(UserRepository)

user = await repo.get_user(10)
```

## Generator

You can also use a generator as your factory callable.
This enables you to run some teardown tasks then the scope or container is ending.

```python

class DbUserRepository:
    def __init__(self, connection: Connection):
        self.dep = dep

    def get_user(self, id: str):
        ## DB Logic to get user
        pass

def connection_factory():
    ## DO initialisation to get the connection
    connection = Connection()
    yield connection
    connection.close()


container = Container()
container.register(Connection, factory=connection_factory)
container.register(UserRepository, DbUserRepository)

repo = container.resolve(UserRepository)

user = repo.get_user(10)
```


## Async Generator

!!! warning
    Async generator factories must only run when using ***resolve_async***

```python

class DbUserRepository:
    def __init__(self, connection: Connection):
        self.dep = dep

    async def get_user(self, id: str):
        ## DB Logic to get user
        pass

async def connection_factory():
    ## DO initialisation to get the connection
    connection = Connection()
    yield connection
    await connection.close()


container = Container()
container.register(Connection, factory=connection_factory)
container.register(UserRepository, DbUserRepository)

repo = await container.resolve_async(UserRepository)

user = await repo.get_user(10)
```