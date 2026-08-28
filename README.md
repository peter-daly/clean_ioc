# Clean IoC

**Python dependency injection that can prove its wiring before your app starts.**

[![CI](https://github.com/peter-daly/clean_ioc/actions/workflows/ci.yml/badge.svg)](https://github.com/peter-daly/clean_ioc/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/clean-ioc.svg)](https://pypi.org/project/clean-ioc/)
[![Python](https://img.shields.io/pypi/pyversions/clean-ioc.svg)](https://pypi.org/project/clean-ioc/)
[![License](https://img.shields.io/pypi/l/clean-ioc.svg)](https://github.com/peter-daly/clean_ioc/blob/main/LICENSE)

Clean IoC is a typed inversion-of-control container for Python 3.10+. It keeps your domain code free of framework imports while handling lifespans, async resources, decorators, contextual selection, open generics, and FastAPI request scopes.

Its differentiator is confidence: validate a complete object graph at startup, get actionable errors for missing registrations, cycles, and captive dependencies, or render the wiring as text or Mermaid—without constructing a single object.

```bash
pip install clean_ioc
# With FastAPI support:
pip install "clean_ioc[fastapi]"
```

## See it in 30 seconds

Your application code only needs normal Python types:

```python
from typing import Protocol

from clean_ioc import Container, Lifespan


class PaymentGateway(Protocol):
    def charge(self, amount: int) -> str: ...


class StripeGateway:
    def charge(self, amount: int) -> str:
        return f"charged:{amount}"


class Checkout:
    def __init__(self, gateway: PaymentGateway):
        self.gateway = gateway

    def place_order(self, amount: int) -> str:
        return self.gateway.charge(amount)


container = Container()
container.register(PaymentGateway, StripeGateway, lifespan=Lifespan.singleton)
container.register(Checkout)

container.validate(Checkout)  # static: no constructors or factories are called
checkout = container.resolve(Checkout)

assert checkout.place_order(2500) == "charged:2500"
```

No base classes. No decorators on application code. No global container. No generated proxy objects.

## Prove the graph before production

Most dependency-injection mistakes otherwise appear only when a rarely used endpoint or worker path is first executed. Clean IoC can inspect that path during startup or CI:

```python
container.validate(Checkout)
```

Validation reports all discovered problems together:

```text
Container validation failed with 2 problems:
- [missing-registration] No registration can supply AuditSink (Checkout -> AuditSink)
- [captive-dependency] Singleton Checkout cannot depend on scoped RequestState (Checkout -> RequestState)
```

Ask the same static model to explain a graph:

```python
plan = container.explain(Checkout)

print(plan.to_text())
print(plan.to_mermaid())
```

```text
Checkout [once_per_graph]
   └─ gateway: PaymentGateway -> StripeGateway [singleton]
```

This gives code reviewers, onboarding developers, and coding agents a shared, inspectable description of the architecture. See [validation and graph explanations](https://peter-daly.github.io/clean_ioc/validation/).

## Why teams reach for Clean IoC

| Need | What Clean IoC provides |
| --- | --- |
| Keep the domain portable | Constructor and factory injection through ordinary type hints |
| Catch broken wiring early | Static `validate()` with missing, cycle, lifetime, and async checks |
| Understand a large graph | `explain().to_text()` and `explain().to_mermaid()` |
| Own resources correctly | `transient`, `once_per_graph`, `scoped`, and `singleton` lifespans |
| Handle concurrent traffic | One coordinated build per scoped/singleton registration across tasks and threads |
| Add cross-cutting behavior | Typed decorator chains with ordering and contextual filters |
| Build CQRS/event systems | Automatic closed-generic discovery and open-generic decorators |
| Integrate with FastAPI | Application container, request scopes, async resolution, request/response helpers |
| Collaborate with coding agents | Package-distributed Clean IoC and FastAPI skills |

Clean IoC is a particularly good fit for Clean Architecture, hexagonal applications, CQRS handlers, message consumers, CLIs, and FastAPI services where dependency ownership matters beyond a single function call.

## Lifespans that match real ownership

```python
container.register(AppSettings, instance=settings, lifespan=Lifespan.singleton)
container.register(HttpClient, factory=create_http_client, lifespan=Lifespan.singleton)
container.register(UnitOfWork, factory=create_uow, lifespan=Lifespan.scoped)
container.register(PlaceOrder)  # once_per_graph by default

with container.new_scope() as scope:
    handler = scope.resolve(PlaceOrder)
```

| Lifespan | Reuse boundary | Typical ownership |
| --- | --- | --- |
| `transient` | Every dependency edge | Context-sensitive or disposable objects |
| `once_per_graph` | One top-level resolve | Ordinary application services |
| `scoped` | One explicit scope | Request state, unit of work, DB session |
| `singleton` | Root container | Settings, pools, long-lived clients |

Generator factories, context managers, teardown callbacks, and async equivalents are finalized when their owning scope exits. Invalid singleton-to-scoped capture fails with a readable path instead of silently retaining request state.

## FastAPI without framework-coupled services

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from clean_ioc import Container, Lifespan
from clean_ioc.ext.fastapi import Resolve, add_container_to_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    container = Container()
    container.register(OrderRepository, SqlOrderRepository, lifespan=Lifespan.scoped)
    container.register(PlaceOrder)
    container.validate(PlaceOrder)

    async with add_container_to_app(app, container):
        yield


app = FastAPI(lifespan=lifespan)


@app.post("/orders")
async def place_order(command: OrderRequest, handler: PlaceOrder = Resolve(PlaceOrder)):
    return await handler(command)
```

Each request gets one child scope. Endpoint services resolve asynchronously, so sync and async factories can coexist, and scoped resources close at the request boundary. Clean IoC is continuously tested against the minimum supported and latest FastAPI releases.

See the [FastAPI guide](https://peter-daly.github.io/clean_ioc/extensions/fastapi/) and the [complete Clean Architecture example](https://github.com/peter-daly/clean_ioc/tree/main/examples/fastapi_clean_architecture).

## The deeper toolkit

- Resolve every implementation through `list[Service]`, `tuple[Service]`, or `set[Service]`.
- Select named or tagged registrations from the root or at individual dependency edges.
- Select implementations from the parent graph—useful for multi-tenant and adapter-heavy systems.
- Register sync/async factories, generator factories, and context managers with automatic cleanup.
- Apply decorators to services without modifying their implementations.
- Discover concrete generic handlers and apply generic decorators across them.
- Package repeatable registrations as bundles and safely patch them before first use.
- Inspect the runtime dependency graph when instance-level detail matters.

The [documentation](https://peter-daly.github.io/clean_ioc/) goes from basic registration through contextual filtering and generic handler pipelines.

## Choosing the right level of DI

| Approach | Best when |
| --- | --- |
| Manual wiring | The application is small and the object graph rarely changes |
| Framework-native dependencies | Dependencies live entirely at one framework boundary |
| Clean IoC | Domain/application code must stay portable, graphs are deep or contextual, or resource lifetimes need explicit ownership |

Clean IoC is intentionally more capable than a tiny service dictionary and less invasive than a framework that requires application-wide annotations or wrappers. Registrations remain explicit at the composition root; ordinary code stays ordinary.

## Project health

- Production/stable package with typed public APIs (`py.typed`)
- CI across Python 3.10–3.14
- FastAPI compatibility matrix from 0.101.0 to latest 0.x
- Unit, integration, documentation-example, lint, and type checks
- BenchBro-powered [microbenchmarks](https://peter-daly.github.io/clean_ioc/benchmarks/) with confidence and noise reporting
- MIT licensed

## Start here

- [Documentation](https://peter-daly.github.io/clean_ioc/)
- [Validation and explanations](https://peter-daly.github.io/clean_ioc/validation/)
- [Clean Architecture example](https://github.com/peter-daly/clean_ioc/tree/main/examples/fastapi_clean_architecture)
- [FastAPI integration](https://peter-daly.github.io/clean_ioc/extensions/fastapi/)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGES.rst)

If Clean IoC saves you from one production-only wiring bug—or makes one architecture review clearer—consider starring the repository. It helps the right Python teams discover a deliberately niche project.
