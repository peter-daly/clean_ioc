---
name: use-clean-ioc
description: Use Clean IoC to design, implement, debug, review, and test Python dependency injection with Container registration and resolution, lifespans, scopes, factories, filters, decorators, bundles, generic registrations, and sync or async resource cleanup. Use whenever code imports clean_ioc or needs Clean IoC dependency-injection architecture; use the dedicated FastAPI skill for framework integration details.
---

# Use Clean IoC

Build an explicit registry and let Clean IoC recursively construct type-annotated dependency graphs. Keep application classes unaware of the container whenever constructor or factory injection is sufficient.

## Confirm the installed API

Treat the installed Clean IoC version as the source of truth. Inspect public signatures or docstrings before using an unfamiliar option:

```python
import inspect

from clean_ioc import Container

print(inspect.signature(Container.register))
```

Import core public types from `clean_ioc`. Import specialized filters, factories, node filters, type filters, and value factories from their public submodules.

Discover registration filters from the installed version before inventing a custom lambda:

```bash
python <path-to-this-skill>/scripts/discover_registration_filters.py
python <path-to-this-skill>/scripts/discover_registration_filters.py tag --full
```

With no search terms, the script lists every public registration filter. Search terms are case-insensitive and must all occur in the filter's name, signature, or docstring. Use `--full` to print complete docstrings. Import selected filters from `clean_ioc.registration_filters`.

Discover filters for the `parent_node_filter` registration argument in the same way:

```bash
python <path-to-this-skill>/scripts/discover_parent_node_filters.py
python <path-to-this-skill>/scripts/discover_parent_node_filters.py implementation --full
```

These filters are exposed by `clean_ioc.node_filters`. Search before writing a custom node predicate, especially when selection depends on a parent's service type, implementation, registration name or tags, or dependency descendants.

## Build the dependency graph

Annotate every injected constructor or factory parameter with the service type to resolve. Register abstractions separately from their implementations:

```python
from typing import Protocol

from clean_ioc import Container


class UserRepository(Protocol):
    def get_name(self, user_id: str) -> str: ...


class SqlUserRepository:
    def get_name(self, user_id: str) -> str:
        return "Ada"


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository


container = Container()
container.register(UserRepository, SqlUserRepository)
container.register(UserService)

service = container.resolve(UserService)
```

## Validate and explain before resolving

After registration, statically validate the application's public entry points at the
composition root. Validation does not invoke constructors, factories, decorators,
pre-configurations, or custom value providers:

```python
container.validate(UserService, CreateOrder, HandlePayment)
```

With no service types, `validate()` checks every registration visible to the current
scope. It raises `ContainerValidationError` with all discovered missing registrations,
cycles, singleton-to-scoped captures, and—when `allow_async=False`—async-only activation
paths. Use the stricter mode for entry points that must call `resolve(...)` rather than
`resolve_async(...)`:

```python
container.validate(Command, allow_async=False)
```

Use `explain(...)` to review a selected graph without creating it:

```python
plan = container.explain(UserService)
print(plan.to_text())
print(plan.to_mermaid())
```

The plan models argument names, implementations, lifespans, registration names,
collections, supplied values, decorators, and pre-configurations. Check `plan.is_valid`
and `plan.issues` when building diagnostics or architecture tooling.

Choose one registration form for each service:

```python
# Map an abstraction to an implementation.
container.register(UserRepository, SqlUserRepository)

# Construct a concrete class directly.
container.register(UserService)

# Call a type-annotated factory; its parameters are injected.
container.register(Settings, factory=create_settings)

# Return a pre-built object.
container.register(Settings, instance=settings)
```

`register(...)` returns a registration ID. Use `get_registration_id(service_type, filter=...)` to find the first matching ID in normal resolution order, or `get_registration_ids(...)` to retrieve every matching ID. The singular method returns `None` when there is no match. Resolve a specific registration with the normal type-and-filter API and `with_id`, for example `container.resolve(Service, filter=with_id(registration_id))`. Import `with_id` from `clean_ioc.registration_filters`. Do not use the deprecated `resolve_from_registration_id(...)` or `resolve_from_registration_id_async(...)` methods.

Patch a registration only during setup and before its first resolution:

```python
from clean_ioc import Lifespan, RemoveDependencySetting, Tag

container.patch_registration(
    Service,
    registration_id,
    dependency_config={
        "repository": replacement_settings,
        "logger": RemoveDependencySetting,
    },
    lifespan=Lifespan.scoped,
    tags=[Tag("environment", "production")],
)
```

The service type and registration ID identify a registration owned by that exact scope. Dependency configuration is shallow-merged by argument name; the removal sentinel restores normal/default injection. Tags merge by name, and the last patch value wins. Never attempt to change a registration's name, service type, implementation, factory, instance, parent-node filter, or teardown. A missing local type/ID pair raises `KeyError`, and a patch after first use raises `RuntimeError`.

Inline fixed constructor or factory argument values directly in `dependency_config`:

```python
class Client:
    def __init__(self, x: int):
        self.x = x


container.register(Client, dependency_config={"x": 12345})
```

Use the exact parameter name as the key. An inline value overrides a declared default and is normalized internally to a `DependencySettings` value factory that always returns that value. Use an explicit `DependencySettings` only when the parameter needs a registration filter, list modifier, or custom value factory.

## Resolve with the correct execution model

Use `resolve(...)` only when the entire graph is synchronous. Use `resolve_async(...)` when any factory, generator, context manager, or teardown in the activation path is asynchronous:

```python
client = container.resolve(Client)
async_client = await container.resolve_async(AsyncClient)
```

Resolve all matching registrations through a supported collection annotation. Registrations are returned in last-registered-first order unless a list modifier changes the order:

```python
handlers = container.resolve(list[Handler])
handlers_tuple = container.resolve(tuple[Handler])
handlers_set = container.resolve(set[Handler])
```

Use `call(...)` or `call_async(...)` when invoking a function whose annotated parameters should be injected.

## Resolve at the application boundary

Resolve the root service explicitly in small scripts, tests, CLIs, and custom workers. In larger systems, let the framework or its Clean IoC integration own resolution when one exists. The framework adapter should establish the correct scope, resolve the entry-point service, and release resources at the framework lifecycle boundary.

For example, FastAPI endpoints declare a resolved dependency instead of calling the container themselves:

```python
from clean_ioc.ext.fastapi import Resolve

# Given an app configured with the Clean IoC FastAPI lifespan:
@app.get("/users/{user_id}")
async def get_user(
    user_id: str,
    service: UserService = Resolve(UserService),
):
    return await service.get_user(user_id)
```

The FastAPI integration resolves `UserService` asynchronously from the current request scope. Configure the root container in the application lifespan as described by the `use-clean-ioc-fastapi` skill.

Apply the same composition-boundary rule to other integrations: let request, message, task, or job infrastructure drive root resolution while ordinary application services receive dependencies through constructors. Do not pass the container through the application or call `resolve(...)` throughout business logic.

## Choose lifespans deliberately

Import `Lifespan` from `clean_ioc` and select based on ownership:

| Lifespan | Reuse boundary | Typical use |
| --- | --- | --- |
| `transient` | Never reused | Context-sensitive values or disposable operations |
| `once_per_graph` | One top-level resolve graph; the default | Ordinary services |
| `scoped` | One `Scope` | Request, job, or unit-of-work state |
| `singleton` | Root `Container` | Configuration and long-lived client pools |

Never make a singleton depend directly or indirectly on a non-instance `scoped`
registration. Clean IoC rejects this captive dependency during validation and runtime
resolution because it would retain a request/job-owned object for the application
lifetime. Scoped and singleton first activation is coordinated across threads and async
tasks, so concurrent callers share one build at the relevant ownership boundary.

Open scopes as context managers so cached objects and finalizers are released:

```python
from clean_ioc import Container, Lifespan

container = Container()
container.register(UnitOfWork, lifespan=Lifespan.scoped)

with container.new_scope() as scope:
    first = scope.resolve(UnitOfWork)
    second = scope.resolve(UnitOfWork)
    assert first is second
```

Use `async with` and `resolve_async(...)` for async resources:

```python
async with container.new_scope() as scope:
    connection = await scope.resolve_async(AsyncConnection)
```

Enter the root container as a sync or async context when singleton factories have teardown work. Do not expect generator factories or teardown callbacks to finish automatically when their owning scope/container is never exited.

Prefer a generator or context-manager factory when setup and cleanup belong together:

```python
def connection_factory():
    connection = Connection()
    try:
        yield connection
    finally:
        connection.close()


container.register(
    Connection,
    factory=connection_factory,
    lifespan=Lifespan.scoped,
)
```

Use `scoped_teardown=` when cleanup is clearer as a separate callback.

## Select registrations explicitly

The default filter selects unnamed registrations. When multiple unnamed registrations exist, direct resolution selects the most recently registered match. Use a filter whenever a name or tag carries selection intent:

```python
from clean_ioc import Tag
from clean_ioc.registration_filters import has_tag, with_name

container.register(Gateway, StripeGateway, name="stripe")
container.register(Gateway, SandboxGateway, tags=[Tag("environment", "test")])

stripe = container.resolve(Gateway, filter=with_name("stripe"))
test_gateway = container.resolve(Gateway, filter=has_tag("environment", "test"))
```

Apply `DependencySettings(filter=...)` when a parent constructor or factory parameter needs a particular child registration. Do not resolve named registrations without an explicit filter and assume the name will be preferred automatically.

## Keep overrides local

Register test doubles or request/job-specific values on a child scope when only that scope should see the override:

```python
container.register(Clock, SystemClock)

with container.new_scope() as scope:
    scope.register(Clock, instance=fake_clock)
    service = scope.resolve(Service)
```

The child scope can use parent registrations, while its own matching registrations take precedence within that scope.

## Use advanced features only when needed

Read [references/advanced-patterns.md](references/advanced-patterns.md) completely before implementing any of these:

- dependency configuration or value factories;
- registration, node, or list filtering;
- decorators, bundles, or pre-configurations;
- subclass or open-generic discovery;
- `Resolver`, `CurrentGraph`, `DependencyContext`, or factory helpers.

For FastAPI application lifespan, per-request scopes, `Resolve(...)`, and request/response injection, use the `use-clean-ioc-fastapi` skill when it is available.

## Verify the graph

Exercise the real container in focused tests:

- resolve the root service and assert concrete implementation types;
- resolve twice to verify the selected lifespan boundary;
- enter and exit scopes to verify teardown timing;
- exercise both matching and non-matching filters;
- use `resolve_async(...)` for every graph containing async activation;
- import all subclass modules before testing discovery-based registration.

## Avoid common mistakes

- Do not omit type annotations from injected parameters.
- Do not use `resolve(...)` for graphs containing async factories or async generators.
- Do not expect a named registration to match the default unnamed filter.
- Do not use `scoped` resources without an explicit scope ownership boundary.
- Do not create singleton database sessions or request-specific state; reserve singleton for concurrency-safe application resources.
- Do not expect subclass discovery to find classes whose modules have not been imported.
- Do not hide ordinary constructor injection behind manual calls to `Container` or `Resolver`.
