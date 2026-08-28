---
description: Typed Python dependency injection with build-time component compilation, immutable runtime plans, explicit lifespans, generics, decorators, and FastAPI scopes.
---

# Compile the graph once. Resolve the plan.

Clean IoC keeps application code unaware of the container while making dependency composition explicit and inspectable. Version 2 separates the mutable `ContainerBuilder` from the immutable runtime `Container`.

```bash
pip install clean_ioc
```

## A complete first plan

```python
from typing import Protocol

from clean_ioc import ContainerBuilder, Lifespan


class UserRepository(Protocol):
    def get_name(self, user_id: str) -> str: ...


class SqlUserRepository:
    def get_name(self, user_id: str) -> str:
        return "Ada"


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository


builder = ContainerBuilder()
builder.register(UserRepository, SqlUserRepository, lifespan=Lifespan.scoped)
builder.register(UserService)

container = builder.build()

with container.new_scope() as scope:
    service = scope.resolve(UserService)
    assert service.repository.get_name("123") == "Ada"
```

`build()` specializes types, constructs occurrence-specific `Component` trees, evaluates filters, checks cycles and captive lifespans, and freezes activation instructions. It does not invoke user constructors, factories, generators, teardown callbacks, or value providers.

Runtime resolution executes the frozen plan. It does not rediscover registrations or allocate graph nodes.

## Composition and runtime are different jobs

| API | Responsibility |
| --- | --- |
| `ContainerBuilder` | Register, decorate, configure, declare slots, compile root plan |
| `Container` | Resolve from the immutable root plan and own root singletons |
| `ScopeBuilder` | Compile an experimental child overlay without mutating its parent |
| `Scope` | Resolve, cache scoped values, provide declared slots, and run cleanup |
| `Component` | Read-only static occurrence model used by every filter and query |

## Build failures happen before activation

```python
builder = ContainerBuilder()
builder.register(UserService)  # UserRepository is missing

container = builder.build()  # raises ContainerBuildError
```

A failed build leaves the builder reusable. A successful build makes the builder immutable and single-use.

## Built for application architecture

| Capability | Use it for |
| --- | --- |
| Four explicit lifespans | Settings, clients, request state, units of work, ordinary services |
| Sync and async factories | Resource creation and deterministic cleanup |
| Unified component filters | Root, dependency, parent, decorator, and pre-configuration selection |
| Typed decorator chains | Logging, metrics, retries, caching, authorization |
| Generic discovery | CQRS handlers, event consumers, validators, pipelines |
| Declared scope slots | FastAPI requests, responses, tenant IDs, tracing context |
| Compiled scope overlays | Experimental tenant/test/plugin composition |

## Where to go next

- [Simple uses](simple-uses.md) — registration forms and the build boundary
- [Lifespans](lifespans.md) and [scopes](scopes.md) — ownership, slots, and overlays
- [Filtering](advanced/filtering.md) — the unified `Component` model
- [Factories](factories.md) — sync, async, generators, and context managers
- [Decorators](decorators.md) and [generics](generics.md) — compiled handler pipelines
- [FastAPI](extensions/fastapi.md) — request scopes and explicit request values
- [Benchmarks](benchmarks.md) — build, runtime, and allocation experiments
