# Scopes and scope builders

An ordinary `Scope` is a lightweight runtime boundary. It reuses an already-compiled plan, owns scoped instances created within it, and runs their cleanup when it exits.

```python
from clean_ioc import ContainerBuilder


class DbConnection:
    pass


builder = ContainerBuilder()
builder.register(DbConnection, lifespan="scoped")
container = builder.build()

with container.new_scope() as scope:
    first = scope.resolve(DbConnection)
    second = scope.resolve(DbConnection)
    assert first is second
```

`new_scope()` never recompiles. Nested scopes inherit parent scoped and singleton values.

## One scope per method call

Set `scope="per_call"` on a service registration when each operation needs its own scoped dependencies. Callers keep the
same service interface:

```python
from typing import Protocol

from clean_ioc import ContainerBuilder


class MessageProcessor(Protocol):
    def process(self, message: str) -> str: ...


class RequestState:
    pass


class ActualMessageProcessor:
    def __init__(self, state: RequestState):
        self.state = state

    def process(self, message: str) -> str:
        return message.upper()


builder = ContainerBuilder()
builder.register(RequestState, lifespan="scoped")
builder.register(MessageProcessor, ActualMessageProcessor, scope="per_call")
with builder.build() as container:
    processor = container.resolve(MessageProcessor)
    assert processor.process("first") == "FIRST"
    assert processor.process("second") == "SECOND"
```

Resolving `MessageProcessor` obtains a lightweight handle without creating `ActualMessageProcessor`. Each method call
creates a fresh scope, constructs the implementation and its dependencies, runs the method, and closes that scope. An
`async def` method performs activation, invocation, and cleanup asynchronously in the caller's task. Its scope also
closes on exceptions and cancellation. A synchronous method requires a fully synchronous activation and cleanup plan.

The declared contract must expose public instance methods on a class, ABC, or Protocol; inherited methods and
`__call__` are supported. An ABC may use private abstract helpers behind a public operation: the handle forwards the
public call to the real implementation. Private abstract members have raising stubs on the handle; they are not scope
entry points. Other abstract special methods, such as `__str__`, are unsupported. Public properties and other
descriptors, required public instance data, static and class operations, generator operations, and declared iterator or
generator results are rejected at build time. An effective subclass `ClassVar` declaration can replace inherited public
instance data; callable class variables are not forwarded. Contract attribute hooks, finalizers, and behavioral special
methods such as `__iter__` are unsupported. The handle uses object identity for `repr`, `str`, equality, and hashing even
when the contract defines stateful versions; a dataclass `__replace__` on the handle raises `NotImplementedError`.
Implementation-only hooks still run on the real instance. Known implementation and
decorator methods must match the contract's sync or async mode. Common iterator and awaitable results that escape an
unknown factory's static checks are rejected during invocation. Direct returns of the scoped implementation, any
decorator instance, or a method bound to one are also rejected before cleanup; statically identifiable `Self` and
service-fluent return contracts fail at build. Other resource-backed or lazy results must not outlive an invocation
scope; Python cannot determine the lifetime of arbitrary closures, nested objects, or returned values. Contracts with custom allocation
(`__new__`), metaclasses, or subclass hooks are also rejected because a forwarding handle cannot safely construct them.

An ordinary child scope still inherits already-created parent scoped values. Per-call scopes always start with an empty
scoped cache, while inheriting declared scope provisions and singleton owners. A handle obtained directly from a child
or overlay follows that scope and fails after it closes. A root singleton that retains a handle keeps the root's frozen
plan and owner even if the singleton was first resolved through a child or overlay.

## Async scopes and cleanup

```python
async with container.new_scope() as scope:
    connection = await scope.resolve_async(DbConnection)
```

Use async context management whenever a plan may contain async generators or async context managers.

Generator factories and context managers belong to the same owner as the cached value. Scoped cleanup runs when the scope exits; root singleton cleanup runs when the container exits.

## Declared scope slots

Framework and request values do not exist while the root plan is compiled. Declare those holes explicitly on the builder, then provide values before resolution:

```python
class RequestContext:
    pass


class Handler:
    def __init__(self, request: RequestContext):
        self.request = request


builder = ContainerBuilder()
builder.declare_scope_slot(RequestContext)
builder.register(Handler)
container = builder.build()

with container.new_scope() as scope:
    scope.provide(RequestContext, RequestContext())
    handler = scope.resolve(Handler)
```

The following slot invariants apply:

- only `(type, name)` pairs declared by a builder may be provided;
- one scope cannot provide the same slot twice;
- all provisions lock when that scope begins resolution;
- a nested scope inherits provisions and may override them before its own first resolve.

These constraints keep the plan static while still supporting FastAPI requests, tenant IDs, trace contexts, and similar late-bound values.

## ScopeBuilder overlays

A child scope with different registrations requires a `ScopeBuilder` and a separate build:

```python
class PaymentGateway:
    pass


class ProductionGateway(PaymentGateway):
    pass


class TenantGateway(PaymentGateway):
    pass


builder = ContainerBuilder()
builder.register(PaymentGateway, ProductionGateway)
container = builder.build()

tenant_builder = container.new_scope_builder()
tenant_builder.register(PaymentGateway, TenantGateway)

with tenant_builder.build() as tenant_scope:
    assert isinstance(tenant_scope.resolve(PaymentGateway), TenantGateway)

assert isinstance(container.resolve(PaymentGateway), ProductionGateway)
```

`new_scope_builder()` is available on both `Container` and `Scope`. It recompiles the visible overlay roots for correctness while reusing frozen parent plans where ownership requires it.

An overlay singleton belongs to the built scope and its descendants. It is finalized when that built scope exits. An
inherited root singleton remains anchored to the root container's frozen activation plan and owner; overlay registrations
and decorators do not alter that plan.

A built overlay begins a new scoped cache boundary. An inherited scoped component can therefore use overlay dependencies
without reusing an instance created in the parent. Ordinary nested `new_scope()` calls retain their existing inheritance
semantics.

An overlay build also inherits the parent's immutable `build_args` and may shallowly override keys:

```python
tenant_scope = tenant_builder.build(build_args={"tenant": "acme"})
```

Components newly compiled for the overlay see the merged mapping. Anchored parent singleton and pre-configuration plans
retain the mapping under which the parent compiled, while ordinary `new_scope()` scopes reuse their parent's mapping
unchanged. Build a new root when a key must be absent because overlays do not have a build-argument removal sentinel.

## Scope API selection

| Need | API |
| --- | --- |
| Same composition, new cache boundary | `new_scope()` |
| Fresh scoped dependencies for each service method call | `register(..., scope="per_call")` |
| Supply a request/framework value | `declare_scope_slot()` + `scope.provide()` |
| Change child registrations/decorators | `new_scope_builder()` + `build()` |
| Change the application root | Create a new `ContainerBuilder` |

Scopes are idempotently closeable through synchronous or asynchronous context management. After exit, `resolve`,
`resolve_async`, `provide`, `new_scope`, and `new_scope_builder` raise `ScopeClosedError`. Closing a parent does not
implicitly close child scopes that have their own boundary; integrations should still nest scope contexts so inherited
resources are not used after their owner closes.
