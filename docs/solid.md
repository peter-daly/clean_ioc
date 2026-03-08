# SOLID and Clean IoC

Clean IoC helps implement SOLID principles by making dependencies explicit and configurable.

## Single Responsibility Principle (SRP)

A class should have one reason to change.
In practice, this means separating business behavior from object construction, configuration, and infrastructure concerns.

Common SRP violation:

- class both performs domain logic and creates/manages its dependencies

How Clean IoC helps:

- constructors declare dependencies
- container setup handles wiring/lifecycle externally
- business classes stay focused on behavior

```python
class UserService:
    def __init__(self, repo: "UserRepository"):
        self.repo = repo
```

## Open/Closed Principle (OCP)

Swap implementations through registration.

Software should be open for extension, closed for modification.
Instead of editing existing high-level classes to support a new backend/integration, add a new implementation and change registrations.

Common OCP violation:

- adding `if provider == ...` branching in service classes for each new implementation

```python
container.register(UserRepository, SqlUserRepository)
# later
container.register(UserRepository, InMemoryUserRepository)
```

## Liskov Substitution Principle (LSP)

Resolve abstractions (`Protocol`/base classes), use compatible implementations.

Any implementation registered for an abstraction should preserve the abstraction's behavioral contract.
If consumers expect one behavior but a replacement breaks assumptions, substitutability fails.

Common LSP violation:

- implementation raises `NotImplementedError` for required operations of the abstraction

```python
from typing import Protocol


class Notifier(Protocol):
    def send(self, message: str) -> None:
        ...
```

## Interface Segregation Principle (ISP)

Split broad APIs and wire focused interfaces to the same concrete instance when useful.

Clients should not depend on methods they do not use.
Prefer small interfaces per use case, then map multiple interfaces to a shared implementation when appropriate.

Common ISP violation:

- a large interface forcing unrelated consumers to depend on unused methods

```python
from clean_ioc.factories import use_from_current_graph

container.register(Sender, MySender)
container.register(BatchSender, factory=use_from_current_graph(MySender))
```

## Dependency Inversion Principle (DIP)

High-level modules depend on abstractions; container binds abstractions to concretes.

Policies should depend on interfaces/protocols, not concrete low-level details.
This reduces coupling and makes behavior changes a registration concern rather than a code rewrite.

Common DIP violation:

- service directly instantiates infrastructure classes (`self.repo = SqlRepo()`)

```python
container.register(UserRepository, SqlUserRepository)
container.register(UserService)
service = container.resolve(UserService)
```
