# Clean IoC

A lightweight dependency injection container for Python that relies on type hints and keeps application code framework-agnostic.

## Why Clean IoC

- Constructor injection by default.
- Minimal ceremony: register types, then resolve.
- Supports sync + async factories.
- Built-in lifespans: `transient`, `once_per_graph`, `scoped`, `singleton`.
- Scoped teardown support.
- Dependency graph inspection for debugging and tooling.

## Installation

```bash
pip install clean_ioc
```

FastAPI extension:

```bash
pip install "clean_ioc[fastapi]"
```

Python requirement: `>=3.10`.

## Quick Start

```python
from clean_ioc import Container


class UserRepository:
    def find(self, user_id: str) -> dict:
        return {"id": user_id, "name": "Ada"}


class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def get_user(self, user_id: str) -> dict:
        return self.repo.find(user_id)


container = Container()
container.register(UserRepository)
container.register(UserService)

service = container.resolve(UserService)
print(service.get_user("123"))
```

## Registration Modes

All registrations end up as a `service_type -> something that can build/return an instance`.
The four modes mostly differ in who controls creation and lifecycle semantics.

Important default behavior:

- `resolve(...)` uses the default registration filter, which selects unnamed registrations only.
- If you register with `name=...`, resolve with an explicit filter (for example `with_name("...")`).
- For competing registrations, the most recently registered entry is selected first.

### 1. Register implementation

Map an abstraction (or base type) to a concrete implementation type.

```python
container.register(IService, ServiceImpl)
```

What happens:

- Clean IoC inspects `ServiceImpl.__init__` type hints.
- Each constructor argument is resolved recursively.
- A new `ServiceImpl` instance is created according to `lifespan`.

When to use:

- Default option for interface/abstraction-based design.
- You want constructor injection with minimal boilerplate.

Tradeoffs:

- Construction logic must fit constructor injection.
- If construction needs conditionals/runtime branching, factory mode is often better.

### 2. Register concrete type

Register a class as both service and implementation.

```python
container.register(ServiceImpl)
```

Equivalent to:

```python
container.register(ServiceImpl, ServiceImpl)
```

What happens:

- Same recursive constructor resolution as implementation mode.
- Useful when you do not need an abstraction for this dependency.

When to use:

- Internal app services where interface swapping is unnecessary.
- Small/medium code paths where direct concrete usage is acceptable.

Tradeoffs:

- Tighter coupling to concrete type compared to abstraction mapping.

### 3. Register factory

Use a function/callable to create the instance.

```python
def create_service(repo: Repo) -> ServiceImpl:
    return ServiceImpl(repo)

container.register(IService, factory=create_service)
```

What happens:

- Factory parameters are injected using type hints, same as constructors.
- Supports sync, async, generator, and async-generator factories.
- Also supports `@contextmanager` and `@asynccontextmanager` factory functions.
- Generator/contextmanager factories participate in finalization patterns.

When to use:

- Complex creation logic.
- Runtime branching (`if config.use_mock: ...`).
- Third-party objects you cannot construct directly with pure constructor DI.

Tradeoffs:

- Slightly more indirection than type registration.
- You own factory correctness and readability.

Example with context managers:

```python
from contextlib import asynccontextmanager, contextmanager


@contextmanager
def db_session() -> DbSession:
    session = DbSession()
    try:
        yield session
    finally:
        session.close()


@asynccontextmanager
async def async_client() -> AsyncClient:
    client = AsyncClient()
    try:
        yield client
    finally:
        await client.aclose()


container.register(DbSession, factory=db_session)
container.register(AsyncClient, factory=async_client)
```

### 4. Register pre-built instance

Provide an already-created object.

```python
client = ApiClient(base_url="https://api.example.com")
container.register(ApiClient, instance=client)
```

What happens:

- The container returns the same instance reference.
- If lifespan is not `singleton`, instance registrations are internally treated as scoped.
- Useful for objects created outside DI (SDK clients, settings objects, test doubles).

When to use:

- Existing object lifecycle is managed elsewhere.
- You need strict identity semantics.
- Testing/mocking scenarios.

Tradeoffs:

- No constructor injection for that instance (it already exists).
- Can hide lifecycle ownership if overused.

### Choosing quickly

- Prefer `implementation` for standard abstraction -> concrete mappings.
- Prefer `concrete` for straightforward internal services.
- Prefer `factory` when creation logic is dynamic or async-heavy.
- Prefer `instance` when object already exists or must be identity-stable.

## Lifespans

- `Lifespan.transient`: new instance every time.
- `Lifespan.once_per_graph`: one instance per single top-level resolve call.
- `Lifespan.scoped`: one instance per scope.
- `Lifespan.singleton`: one instance per container hierarchy.

```python
from clean_ioc import Lifespan

container.register(DbSession, lifespan=Lifespan.scoped)
container.register(Cache, lifespan=Lifespan.singleton)
```

## Scopes

Scopes define a lifetime boundary for scoped dependencies.
Think of a scope as a unit-of-work container layered on top of the root container.

```python
with container.new_scope() as scope:
    service = scope.resolve(Service)
```

### How scope lifetime behaves

- `singleton`: shared across the container and child scopes.
- `scoped`: one instance per scope.
- `once_per_graph`: one instance per single resolve graph.
- `transient`: always rebuilt.

### Why scopes matter

Scopes are ideal for request lifecycles where you want one shared dependency instance per request (for example DB session, unit-of-work, per-request context).

### Scoped teardown

`scoped_teardown` can be attached to scoped registrations to clean up when scope exits.

```python
container.register(
    DbSession,
    lifespan=Lifespan.scoped,
    scoped_teardown=lambda s: s.close(),
)
```

You can often replace `scoped_teardown` with a generator/contextmanager factory, which keeps setup and teardown logic in one place.

```python
from contextlib import contextmanager


@contextmanager
def db_session_factory() -> DbSession:
    session = DbSession()
    try:
        yield session
    finally:
        session.close()


container.register(DbSession, factory=db_session_factory, lifespan=Lifespan.scoped)
```

Use whichever style is clearer for your team:

- `scoped_teardown`: explicit teardown callback attached at registration.
- generator/contextmanager factory: setup and cleanup colocated in a single factory function.

### FastAPI request scope example

With the FastAPI extension, each request gets a Clean IoC scope. Dependencies registered as `Lifespan.scoped` are reused within that request and cleaned up when the request completes.

```python
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from clean_ioc import Container, Lifespan, Scope
from clean_ioc.ext.fastapi import Resolve, add_container_to_app, get_scope


class DbSession:
    def close(self):
        ...


class UserRepository:
    def __init__(self, db: DbSession):
        self.db = db


class UserService:
    def __init__(self, repo: UserRepository, request: Request):
        self.repo = repo
        self.request = request


def add_request_to_scope(request: Request, scope: Scope = Depends(get_scope)):
    # Makes FastAPI's Request injectable in container-managed dependencies.
    scope.register(Request, instance=request)


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    container = Container()
    container.register(
        DbSession,
        lifespan=Lifespan.scoped,
        scoped_teardown=lambda s: s.close(),
    )
    container.register(UserRepository)
    container.register(UserService)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(
    lifespan=app_lifespan,
    dependencies=[Depends(add_request_to_scope)],
)


@app.get("/users/{user_id}")
async def get_user(user_id: str, service: UserService = Resolve(UserService)):
    # service/repo/db are resolved from the request scope
    # and DbSession teardown runs at end of request scope.
    return {"user_id": user_id}
```

Request lifecycle summary:

| Registration lifespan | Instance frequency in FastAPI app |
| --- | --- |
| `singleton` | One instance shared across the container/app lifetime |
| `scoped` | One instance per request scope |
| `once_per_graph` | One instance per resolve graph call (for example one `resolve(...)` / `Resolve(...)` execution) |
| `transient` | New instance every time it is requested |

Note:

- In FastAPI, multiple dependency resolutions in a single request can produce multiple resolve graphs.
- `once_per_graph` is therefore graph-scoped, not request-scoped.

## Filtering Registrations

When multiple registrations exist for a service, choose one at resolve time.

Selection rules recap:

- Default filter resolves unnamed registrations only.
- Named registrations require an explicit filter.
- The container checks registrations in reverse registration order (last registered first), then applies your filter.

```python
from clean_ioc.registration_filters import with_name, has_tag

container.register(PaymentGateway, StripeGateway, name="stripe")
container.register(PaymentGateway, AdyenGateway, name="adyen")

gateway = container.resolve(PaymentGateway, filter=with_name("stripe"))
```

Tags are useful for environment/tenant/channel style routing.

```python
from clean_ioc import Tag
from clean_ioc.registration_filters import has_tag_with_value_in

container.register(Notifier, EmailNotifier, tags=[Tag("channel", "email")])
container.register(Notifier, SmsNotifier, tags=[Tag("channel", "sms")])

notifier = container.resolve(Notifier, filter=has_tag_with_value_in("channel", "sms"))
```

## Collections

Resolve all matching registrations with `list[T]`, `tuple[T]`, `set[T]`, and related collection annotations.

```python
class Pipeline:
    def __init__(self, handlers: list[Handler]):
        self.handlers = handlers
```

Each `Handler` registration is resolved and collected.

## Decorators

Decorators wrap a resolved service instance after the base registration is built.
They are applied during resolution, not at registration time.

```python
container.register(Service)
container.register_decorator(Service, LoggingServiceDecorator)
container.register_decorator(Service, MetricsServiceDecorator, position=10)
```

### How they are applied

1. Clean IoC resolves and builds the base `Service` instance.
2. It finds matching decorators for that registration.
3. It applies decorators in order, passing the previous instance into the next.
4. The final wrapped instance is what `resolve(...)` returns.

Resolution pipeline (high-level):

```text
choose registration -> run pre-configurations -> build instance -> apply decorators -> cache by lifespan
```

### Ordering

- Use `position` to control order.
- Lower `position` values are applied first.
- For decorators with the same `position`, the most recently registered one is applied first.

Decorator chain visualization:

```text
base instance: ServiceImpl
after first decorator: LoggingDecorator(ServiceImpl)
after second decorator: MetricsDecorator(LoggingDecorator(ServiceImpl))
returned by resolve(Service): MetricsDecorator(...)
```

### Injecting the wrapped instance

Each decorator must accept the decorated service instance as one argument.

```python
class LoggingServiceDecorator(Service):
    def __init__(self, child: Service, logger: Logger):
        self.child = child
        self.logger = logger
```

By default, Clean IoC auto-detects which argument receives the wrapped service by matching the service type annotation.
If needed, set it explicitly with `decorated_arg`.

```python
container.register_decorator(Service, LoggingServiceDecorator, decorated_arg="child")
```

All other decorator parameters are dependency-injected normally.

### Filtering where decorators apply

You can target decorators narrowly using:

- `registration_filter`: apply only to matching registrations (e.g. by name/tag).
- `decorator_node_filter`: apply only when the current dependency graph node matches a condition.

```python
from clean_ioc.registration_filters import has_tag
from clean_ioc.node_filters import jump_parent, service_type_is

container.register(Service, ServiceImpl, tags=[Tag("channel", "api")])

container.register_decorator(
    Service,
    LoggingServiceDecorator,
    registration_filter=has_tag("channel", "api"),
    decorator_node_filter=jump_parent(service_type_is(Controller)),
)
```

### Function decorators are supported

`decorator_type` can also be a function/callable, not only a class.
Its parameters are resolved the same way as factory registrations.

## Pre-configuration Hooks

Run setup logic before target registrations are built.

```python
def configure_repo(config: AppConfig, repo: Repo):
    repo.connect(config.db_url)

container.pre_configure(Repo, configure_repo)
```

Pre-configurations are run once per registered pre-configuration object (not once per resolve call) and can be set to continue on failure.

## Advanced Injection Helpers

### `DependencyContext`

Inject metadata about the current dependency being resolved.

```python
from clean_ioc import DependencyContext

def create_logger(dependency_context: DependencyContext) -> Logger:
    return Logger(name=str(dependency_context.parent.implementation))
```

### `CurrentGraph`

Resolve additional dependencies from the current graph context.

```python
from clean_ioc import CurrentGraph

def create_handler(graph: CurrentGraph) -> Handler:
    repo = graph.resolve(Repo)
    return Handler(repo)
```

## Async Support

Supported:

- async factories
- async generator factories
- async resolve path (`resolve_async`)
- async scope cleanup

```python
handler = await container.resolve_async(Handler)
```

## Generic Registrations

Clean IoC supports open-generic patterns by registering concrete subclasses against their closed generic base types.

### How resolution works

If you resolve a closed generic type like `Handler[UserCreated]`, Clean IoC:

1. looks for an exact registration for `Handler[UserCreated]`
2. if none exists, it can fall back to an open generic registration for `Handler`

### Register generic subclasses

`register_generic_subclasses(...)` scans subclasses and registers each one against its mapped closed generic base.

Important:

- Subclasses must be imported before calling `register_generic_subclasses(...)`, otherwise they are not discoverable.

```python
from typing import Generic, TypeVar
from clean_ioc import Container

TEvent = TypeVar("TEvent")


class Event:
    pass


class UserCreated(Event):
    pass


class UserDeleted(Event):
    pass


class Handler(Generic[TEvent]):
    def handle(self, event: TEvent) -> None:
        raise NotImplementedError


class UserCreatedHandler(Handler[UserCreated]):
    def handle(self, event: UserCreated) -> None:
        ...


class UserDeletedHandler(Handler[UserDeleted]):
    def handle(self, event: UserDeleted) -> None:
        ...


container = Container()
container.register_generic_subclasses(Handler)

created_handler = container.resolve(Handler[UserCreated])
deleted_handler = container.resolve(Handler[UserDeleted])
```

### Fallback for unmatched generic args

You can provide a `fallback_type` to handle generic combinations without a specific subclass mapping.

```python
class DefaultHandler(Handler[TEvent]):
    def handle(self, event: TEvent) -> None:
        ...


container.register_generic_subclasses(Handler, fallback_type=DefaultHandler)
```

This allows `container.resolve(Handler[SomeNewEvent])` to still succeed.

### Register generic decorators

Use `register_generic_decorator(...)` to decorate every mapped generic service registration.

```python
class LoggingHandlerDecorator(Generic[TEvent], Handler[TEvent]):
    def __init__(self, child: Handler[TEvent]):
        self.child = child

    def handle(self, event: TEvent) -> None:
        print("handling", type(event).__name__)
        self.child.handle(event)


container.register_generic_decorator(Handler, LoggingHandlerDecorator)
```

If the decorator type is open generic, Clean IoC maps it to concrete decorator types for each discovered subclass mapping.

### Generic-aware filtering

For multiple registrations of the same open generic service, use `has_generic_args_matching(...)` in `clean_ioc.registration_filters` to select by specific type arg mappings.

## Graph Introspection

Resolve the full dependency graph when debugging behavior:

```python
graph = container.resolve_dependency_graph(Service)
```

You can inspect whether graph nodes contain dependent service/implementation/instance types.

## Error Diagnostics

Failures raise `CannotResolveError` with a trace-like chain showing dependency, registration, decorator, and pre-configuration steps leading to the failure.

## Utility Factories

`clean_ioc.factories` contains helpers such as:

- `use_registered`
- `use_registered_async`
- `use_from_current_graph`
- `create_type_mapping`

These are useful when composing factory-based registrations.

## FastAPI Extension

FastAPI integration is available under:

- `clean_ioc.ext.fastapi.core`
- `clean_ioc.ext.fastapi.dependencies`

See the docs for full integration patterns.

## Development

Run tests:

```bash
make test
```

Build:

```bash
make build
```

## Links

- Documentation: https://peter-daly.github.io/clean_ioc/
- Repository: https://github.com/peter-daly/clean_ioc
- Changelog: `CHANGES.rst`
