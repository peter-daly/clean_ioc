# Special dependency types

Clean IoC 2 keeps the runtime special surface small: `ResolutionContext`, `Scope`, and `Container`.

`ParameterContext` is related but is not a runtime dependency. Clean IoC passes it only to an explicit `derive(...)`
policy during `build()`. See [argument policies](arguments.md).

## `ResolutionContext`

`ResolutionContext` resolves an already-compiled root inside the active top-level resolve. It preserves `once_per_graph` identity.

Prefer constructor injection. Use `ResolutionContext` or helpers such as `use_component(...)` only when the dependency itself is selected dynamically.

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
