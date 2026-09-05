# Special dependency types

Clean IoC 2 keeps the runtime special surface small: `Provider`, `AsyncProvider`, `ResolutionContext`, `Scope`, and
`Container`.

`ParameterContext` is related but is not a runtime dependency. Clean IoC passes it only to an explicit `derive(...)`
policy during `build()`. See [argument policies](arguments.md).

## Typed providers

Use `Provider[T]` when a known dependency should be created later rather than while its consumer is constructed:

```python
from clean_ioc import Provider


class BatchRunner:
    def __init__(self, units: Provider[UnitOfWork]):
        self.units = units

    def run(self, items):
        for item in items:
            self.units().process(item)
```

The compiler unwraps `T`, applies any `select(...)` policy once, validates the complete target graph, and stores a direct
reference to its frozen activation step. A provider call starts a fresh top-level resolution in the scope where the
handle was obtained. Transients are therefore new per call, `once_per_graph` values are shared only inside one call,
and scoped and singleton targets retain their normal caches.

Use `AsyncProvider[T]` for a target that requires async resolution:

```python
from clean_ioc import AsyncProvider


class Worker:
    def __init__(self, repositories: AsyncProvider[Repository]):
        self.repositories = repositories

    async def run(self):
        repository = await self.repositories()
```

Providers take no arguments. Their targets may be a closed service type or `list[T]`, `tuple[T, ...]`, or `set[T]`.
They can also be resolved as roots, such as `scope.resolve(Provider[Report])`. A handle never performs registration or
candidate discovery, and calling it after its bound scope closes raises `ProviderScopeClosedError`.

For a named target, apply `select(...)` to the provider argument; the filter sees the target component rather than the
synthetic handle:

```python
import clean_ioc.component_filters as cf
from clean_ioc import select


builder.register(
    ClientSelector,
    arguments={"client": select(cf.with_name("primary"))},
)
```

A singleton may retain a provider only when its deferred target contains no scoped component, scope slot, `Scope`, or
`ResolutionContext` edge. This rule keeps a provider from disguising captured request state.

## `ResolutionContext`

`ResolutionContext` resolves an already-compiled root inside the active top-level resolve. It preserves `once_per_graph` identity.

Prefer constructor injection. When the target type is known, prefer a typed provider. Use `ResolutionContext` or helpers
such as `use_component(...)` only when the dependency type itself must be selected dynamically.

```python
from clean_ioc import ResolutionContext


class SenderSelector:
    def __init__(self, context: ResolutionContext):
        self.context = context

    def select(self, premium: bool) -> Sender:
        name = "premium" if premium else "standard"
        return self.context.resolve(Sender, filter=cf.with_name(name))
```

ResolutionContext can only select frozen root plans. It cannot register, patch, decorate, provide slots, or compile.

## `Scope`

Injecting `Scope` returns the current runtime scope. This is useful at framework boundaries that must create a nested cache boundary. Application services should normally depend on their actual collaborators.

## `Container`

Injecting `Container` returns the immutable root container, even while resolving inside a child scope. It has resolution and scope-creation APIs but no composition APIs.
