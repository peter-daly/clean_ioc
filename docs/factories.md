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

## Union service types

Register a union as one service key when a factory can return either of two types. For example, a Redis client factory
can choose between standalone and cluster clients using configuration:

```python
from redis import Redis
from redis.cluster import RedisCluster

from clean_ioc import ContainerBuilder

RedisClient = Redis | RedisCluster


class RedisConfig:
    def __init__(self, url: str, cluster_mode: bool):
        self.url = url
        self.cluster_mode = cluster_mode


def get_redis_client(config: RedisConfig) -> RedisClient:
    if config.cluster_mode:
        return RedisCluster.from_url(config.url)
    return Redis.from_url(config.url)


class Cache:
    def __init__(self, client: RedisClient):
        self.client = client


builder = ContainerBuilder()
builder.register(
    RedisConfig,
    instance=RedisConfig("redis://localhost:6379", cluster_mode=False),
    lifespan="singleton",
)
builder.register(RedisClient, factory=get_redis_client, lifespan="singleton")
builder.register(Cache)
container = builder.build()
client = container.resolve(RedisClient)  # Inferred as Redis | RedisCluster
cache = container.resolve(Cache)
```

`A | B`, `Union[A, B]`, and assignment aliases such as `Client = A | B` are supported. Equivalent unions, including
reversed member order, select the same key. You can also supply `instance=` or a concrete implementation class.
Registering a union without any of these construction choices raises `TypeError`.

The union is an explicit key: registering it does not register either member, and registrations under `A` or `B` do
not satisfy a dependency on `A | B`. Named selection, async resolution, providers, caching and resource cleanup use
the normal container rules. `A | None` does not make injection optional: a Python parameter default is used when
present; otherwise the complete union requires a registration or scope slot. Use `inject()` to override a default.

Public service-key annotations use `typing_extensions.TypeForm`, so type checkers supporting it retain the requested
union as the result type. This support does not introduce unwrapping for Python's `type Client = A | B` alias syntax.

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

Factory helpers such as `use_component(...)` resolve through the current `ResolutionContext`, preserving `per_resolution` identity:

```python
from clean_ioc.factories import use_component

builder.register(SenderImpl)
builder.register(Sender, factory=use_component(SenderImpl))
builder.register(BatchSender, factory=use_component(SenderImpl))
```

`use_component()` and `use_component_async()` attach their target and filter as compiler metadata. The referenced root therefore appears as a dependency edge in the compiled graph and participates in missing-component, circular-dependency, captive-lifespan, and sync/async validation. Runtime use still resolves through the current context to preserve `per_resolution` identity; it does not trigger registration discovery or graph compilation.

Direct calls made through an injected `ResolutionContext` remain dynamic because the compiler cannot inspect arbitrary
function bodies. Use the helpers when the target is known during composition and should appear in the compiled graph.

## Argument values and selection

Use `arguments=` for fixed constructor/factory values, `select(...)` for a filtered component edge, and `derive(...)`
for a pure build-time composition rule. `build_arg(...)` and `generic_arg(...)` project common metadata as frozen
values, while `inject()` forces ordinary unnamed injection over a Python default. Runtime-changing values belong in an
ordinary component factory or a declared scope slot. See [argument policies](advanced/arguments.md).
