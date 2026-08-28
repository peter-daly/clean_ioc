# Special dependency types

Clean IoC 2 keeps the runtime special surface small: `DependencyContext`, `ResolutionContext`, `Scope`, and `Container`.

## `DependencyContext`

A value provider receives static information about the parameter's compiled occurrence:

```python
from clean_ioc import DependencyContext


def module_name(default, context: DependencyContext):
    return context.parent.implementation.__module__
```

It exposes the parameter name, current component, service, implementation, static parent, and decorated component. It never exposes a runtime instance.

## `ResolutionContext`

`ResolutionContext` resolves an already-compiled root inside the active top-level resolve. It preserves `once_per_graph` identity.

Prefer constructor injection. Use `ResolutionContext` or helpers such as `use_registered(...)` only when the dependency itself is selected dynamically.

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
