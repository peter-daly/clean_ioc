---
description: Typed Python dependency injection with build-time component compilation, immutable runtime plans, explicit lifespans, generics, decorators, and FastAPI scopes.
---

# Clean IoC 2

Clean IoC is a typed dependency-injection container for Python. Version 2 separates mutable composition in
`ContainerBuilder` from immutable runtime execution in `Container`. Application classes use standard constructors and
do not need to inherit from Clean IoC types or use injection decorators.

```bash
pip install clean_ioc
```

## Minimal container

```python
from typing import Protocol

from clean_ioc import ContainerBuilder


class UserRepository(Protocol):
    def get_name(self, user_id: str) -> str: ...


class SqlUserRepository:
    def get_name(self, user_id: str) -> str:
        return "Ada"


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository


builder = ContainerBuilder()
builder.register(UserRepository, SqlUserRepository, lifespan="scoped")
builder.register(UserService)

container = builder.build()

with container.new_scope() as scope:
    service = scope.resolve(UserService)
    assert service.repository.get_name("123") == "Ada"
```

`build()` specializes types, constructs occurrence-specific `Component` trees, evaluates filters, checks cycles and
captive lifespans, evaluates explicit `derive(...)` argument policies, and freezes activation instructions. It does not
invoke user constructors, factories, generators, or context managers.

Runtime resolution executes the compiled plan without rediscovering registrations or allocating graph nodes.

## Composition and runtime APIs

| API | Responsibility |
| --- | --- |
| `ContainerBuilder` | Register, decorate, configure, declare slots, and compile the root plan |
| `Container` | Resolve from the immutable root plan and own root singletons |
| `ScopeBuilder` | Compile a child overlay without mutating its parent |
| `Scope` | Resolve, cache scoped values, provide declared slots, and run cleanup |
| `Component` | Read-only static occurrence model used by every filter and query |

## Build-time validation

```python
builder = ContainerBuilder()
builder.register(UserService)  # UserRepository is missing

container = builder.build()  # raises ContainerBuildError
```

`build()` raises `ContainerBuildError` with a structured report for invalid plans. A failed build leaves the builder
reusable. After a successful build, the builder is immutable and cannot be built again.

## Core capabilities

| Capability | Use it for |
| --- | --- |
| Four explicit lifespans | Settings, clients, request state, units of work, ordinary services |
| Sync and async factories | Resource creation and deterministic cleanup |
| Unified component filters | Root, dependency, parent, decorator, and pre-configuration selection |
| Typed decorator chains | Logging, metrics, retries, caching, authorization |
| Generic discovery | CQRS handlers, event consumers, validators, pipelines |
| Declared scope slots | FastAPI requests, responses, tenant IDs, tracing context |
| Compiled scope overlays | Tenant, test, and plugin-specific composition |

## Documentation

- [Registration patterns](simple-uses.md) — registration forms and the build boundary
- [Lifespans](lifespans.md) and [scopes](scopes.md) — ownership, slots, and overlays
- [Filtering](advanced/filtering.md) — the unified `Component` model
- [Factories](factories.md) — sync, async, generators, and context managers
- [Decorators](decorators.md) and [generics](generics.md) — compiled handler pipelines
- [FastAPI](extensions/fastapi.md) — request scopes and explicit request values
- [Benchmarks](benchmarks.md) — build, runtime, and allocation experiments
