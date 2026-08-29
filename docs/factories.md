# Factories and resources

Use a factory when construction is not a direct class call, needs injected dependencies, or owns setup and cleanup.

```python
from clean_ioc import ContainerBuilder


def client_factory(config: Config) -> Client:
    return Client(config.endpoint)


builder = ContainerBuilder()
builder.register(Config)
builder.register(Client, factory=client_factory)
container = builder.build()
```

Factory parameters become compiled dependency edges. The factory itself does not run during `build()`.

## Async factories

```python
async def token_factory(config: Config) -> Token:
    return await fetch_token(config)


builder.register(Token, factory=token_factory)
container = builder.build()
token = await container.resolve_async(Token)
```

A plan containing async activation must use `resolve_async()`.

## Generator factories

Yield one value and put cleanup after the yield:

```python
def connection_factory():
    connection = Connection.open()
    try:
        yield connection
    finally:
        connection.close()


builder = ContainerBuilder()
builder.register(Connection, factory=connection_factory, lifespan="scoped")
container = builder.build()

with container.new_scope() as scope:
    connection = scope.resolve(Connection)
```

The generator finalizer belongs to the same owner as the cached component.

## Context managers

Functions decorated with `@contextmanager` and `@asynccontextmanager` are supported as factories. Clean IoC enters them on activation and exits them when the owning scope or container closes.

Keep resource acquisition and release together in the generator or context-manager factory. This makes cleanup ownership explicit and works for both synchronous and asynchronous resources. A `ScopeBuilder` singleton is finalized by its built scope; a root singleton is finalized by the container.

## Reusing another compiled component

Factory helpers such as `use_registered(...)` resolve through the current `ResolutionContext`, preserving `once_per_graph` identity:

```python
from clean_ioc.factories import use_registered

builder.register(SenderImpl)
builder.register(Sender, factory=use_registered(SenderImpl))
builder.register(BatchSender, factory=use_registered(SenderImpl))
```

The referenced root plan is already compiled. Runtime use does not trigger registration discovery or graph compilation.

## Runtime value providers

Parameter value providers are the deliberate runtime exception: the provider runs during activation with a static `DependencyContext` and a precompiled fallback edge. See [value factories](advanced/value-factories.md).
