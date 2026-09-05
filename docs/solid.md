# Dependency boundaries

A dependency-injection container does not make an application modular by itself. Clean IoC provides construction and
ownership mechanisms that can support a modular design, but interface quality and behavioral contracts remain application
concerns.

## Composition root

Object construction, implementation selection, and lifespan policy belong at an application boundary:

```python
builder.register(UserRepository, SqlUserRepository, lifespan="scoped")
builder.register(UserService)
container = builder.build()
```

`UserService` remains responsible for application behavior. The composition root is responsible for selecting
`SqlUserRepository` and assigning its ownership boundary.

## Abstractions and implementations

High-level application services can depend on protocols or base classes while infrastructure supplies concrete
implementations:

```python
from typing import Protocol


class Notifier(Protocol):
    def send(self, message: str) -> None: ...


builder.register(Notifier, EmailNotifier)
```

Changing the mapping does not require a change to consumers of `Notifier`. Clean IoC checks that the selected component
can be constructed; it does not verify the behavioral semantics of the implementation.

## Narrow interfaces and shared implementations

Several focused service types can refer to one concrete component when they require shared identity:

```python
from clean_ioc.factories import use_component

builder.register(MySender)
builder.register(Sender, factory=use_component(MySender))
builder.register(BatchSender, factory=use_component(MySender))
```

`use_component()` creates compiler-visible edges to `MySender` and preserves `once_per_graph` identity during resolution.

## Validation limits

The compiler validates component selection, dependency cycles, generic specialization, decorator and pre-configuration
edges, and lifespan ownership. It cannot validate domain behavior, interface cohesion, or substitutability. Those remain
properties of the application and its tests.
