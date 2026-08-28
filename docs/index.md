---
description: Typed Python dependency injection with static graph validation, explicit lifespans, async cleanup, generics, decorators, and FastAPI request scopes.
---

# Python dependency injection you can verify

Clean IoC builds rich object graphs while keeping application code completely unaware of the container. Registrations stay at the composition root; domain and application services use ordinary typed constructors.

The unusual part is what happens before resolution: Clean IoC can validate the graph and explain its exact wiring without creating any objects.

```bash
pip install clean_ioc
```

## A complete first graph

```python
from typing import Protocol

from clean_ioc import Container, Lifespan


class UserRepository(Protocol):
    def get_name(self, user_id: str) -> str: ...


class SqlUserRepository:
    def get_name(self, user_id: str) -> str:
        return "Ada"


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository


container = Container()
container.register(UserRepository, SqlUserRepository, lifespan=Lifespan.scoped)
container.register(UserService)

container.validate(UserService)

with container.new_scope() as scope:
    service = scope.resolve(UserService)
    assert service.repository.get_name("123") == "Ada"
```

Application code imports neither Clean IoC nor a web framework. The composition root decides which implementation to use and how long it lives.

## Catch wiring errors at startup

```python
report = container.validate(UserService)
plan = container.explain(UserService)

print(report)
print(plan.to_text())
```

Static validation detects:

- missing registrations;
- circular dependencies, with the full cycle;
- singletons that capture scoped services;
- async factories used from sync-only entry points.

`explain()` also models collections, named registrations, supplied values, decorators, and pre-configurations. It can emit Mermaid for architecture documentation. [See validation and explanations](validation.md).

## Built for application architecture

| Capability | Use it for |
| --- | --- |
| Four explicit lifespans | Settings, clients, request state, units of work, and ordinary services |
| Sync and async factories | Resource creation and deterministic cleanup |
| Contextual filters | Select adapters based on the consuming service or registration metadata |
| Typed decorator chains | Logging, metrics, retries, caching, and authorization |
| Generic discovery | CQRS handlers, event consumers, validators, and pipelines |
| FastAPI integration | One application container and one child scope per request |
| Graph introspection | Debugging, reviews, onboarding, and architecture diagrams |

Scoped and singleton activation is coordinated across concurrent tasks and threads, so one cache boundary produces one instance—even under simultaneous first use.

## Where to go next

- [Why Clean IoC?](why-clean-ioc.md) — when a container is worth introducing
- [Simple uses](simple-uses.md) — the four registration forms
- [Validation and explanations](validation.md) — fail-fast startup and CI checks
- [Lifespans](lifespans.md) and [scopes](scopes.md) — resource ownership
- [Factories](factories.md) — sync, async, generators, and context managers
- [Filtering](advanced/filtering.md) — named, tagged, and parent-aware selection
- [Decorators](decorators.md) and [generics](generics.md) — handler pipelines and cross-cutting behavior
- [FastAPI](extensions/fastapi.md) — request scopes and endpoint injection
- [Clean Architecture example](examples/clean-architecture.md) — a real composition root
