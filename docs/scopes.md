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

## Scope API selection

| Need | API |
| --- | --- |
| Same composition, new cache boundary | `new_scope()` |
| Supply a request/framework value | `declare_scope_slot()` + `scope.provide()` |
| Change child registrations/decorators | `new_scope_builder()` + `build()` |
| Change the application root | Create a new `ContainerBuilder` |
