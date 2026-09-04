# Clean IoC

[![CI](https://github.com/peter-daly/clean_ioc/actions/workflows/ci.yml/badge.svg)](https://github.com/peter-daly/clean_ioc/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/clean-ioc.svg)](https://pypi.org/project/clean-ioc/)
[![Python](https://img.shields.io/pypi/pyversions/clean-ioc.svg)](https://pypi.org/project/clean-ioc/)
[![License](https://img.shields.io/pypi/l/clean-ioc.svg)](https://github.com/peter-daly/clean_ioc/blob/main/LICENSE)

Clean IoC is a typed dependency-injection container for Python 3.11+. Version 2 separates mutable composition from
immutable runtime execution:

1. Register components with `ContainerBuilder`.
2. Call `build()` to validate and compile every visible dependency plan.
3. Resolve from the immutable `Container` or a lightweight `Scope`.

Constructors, factories, generators, and context managers do not run during the build. Explicit `derive(...)` argument
policies do run at build time because their concrete results become part of the frozen plan. At runtime, Clean IoC
executes the compiled activation instructions and maintains lifespan caches and cleanup state. It does not rebuild the
dependency graph during resolution.

> **2.0 beta:** the compiled API remains subject to breaking changes while the V2 surface is finalized. V1 is not
> shipped as a parallel public API.

```bash
pip install clean_ioc
pip install "clean_ioc[fastapi]"  # optional FastAPI integration
```

## Minimal example

Application code uses ordinary Python types:

```python
from typing import Protocol

from clean_ioc import ContainerBuilder


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


builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway, lifespan="singleton")
builder.register(Checkout)

container = builder.build()
checkout = container.resolve(Checkout)

assert checkout.place_order(2500) == "charged:2500"
```

Application types do not require Clean IoC base classes or decorators. The container remains at the composition root,
and activation returns ordinary Python objects rather than generated proxies.

## Build and runtime model

`ContainerBuilder.build()` performs registration discovery, contextual selection, structural validation, and activation-plan
compilation at an explicit application boundary.

| Build time | Runtime |
| --- | --- |
| Specialize generic types | Select a frozen root plan |
| Build occurrence-specific component trees | Execute precompiled activation steps |
| Evaluate filters and explicit `build_args` | Cache plain instances by lifespan |
| Detect missing, circular, and captive dependencies | Coordinate concurrent scoped/singleton builds |
| Freeze decorators, pre-configurations, and argument policies | Track only activation and teardown state |

Application-defined build arguments make environment-dependent composition explicit without turning those inputs into
runtime services:

```python
container = builder.build(
    build_args={"environment": "production", "mode": "live"},
)
```

Derived argument policies and component filters can inspect the immutable mapping during compilation. The chosen wiring
is frozen, while graph manifests and reports omit build-argument names and values.

`build()` raises `ContainerBuildError` if a graph is incomplete, a singleton captures scoped state, or a singleton or
scoped component captures `once_per_graph` state. Lifespan checks are transitive, including dependencies reached through
transient components. A failed build leaves the builder reusable. A builder becomes immutable and single-use after a
successful build.

## Graph inspection

Mark application entry points to focus graph output and reachability analysis:

```python
builder.mark_entrypoint(Checkout)
container = builder.build()

print(container.build_report.to_text())
print(container.graph.to_mermaid())
container.graph.manifest().to_json()
```

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc graph my_app.composition:application_builder --format json -o dependency-graph.json
clean-ioc diff my_app.composition:application_builder dependency-graph.json
```

Each target can be a builder, a built container or scope, or a zero-argument factory function returning one.

Build errors are aggregated across independent roots. Deterministic JSON manifests omit configured values and runtime
identities, allowing wiring changes to be reviewed without serializing secrets. Entry points focus the default graph and
enable warnings for unreachable registrations; every visible root is still compiled, validated, and resolvable.
Expensive custom rules can be registered with `strict_only=True`, keeping their graph or source-AST inspection out of
application startup while still running under the strict-by-default `clean-ioc check` command in CI.

## Component model

`Component` is the immutable, plan-backed model used for registrations, dependency occurrences, filters, and graph
inspection. It exposes the service, implementation, lifespan, name, tags, generic mapping, parent, dependencies,
decorators, and pre-configurations.

```python
import clean_ioc.component_filters as cf

builder.register(PaymentGateway, StripeGateway, name="stripe")

component_id = builder.get_component_id(
    PaymentGateway,
    filter=cf.with_name("stripe"),
)
```

The same filter API applies to root selection, dependency selection, contextual registration, decorators, and
pre-configuration:

```python
builder.register(
    PaymentGateway,
    StripeGateway,
    when=cf.parent(cf.has_tag("channel", "web")),
)

gateway = container.resolve(PaymentGateway, filter=cf.with_name("stripe"))
```

Composition, dependency, decorator, and pre-configuration filters run while the container or scope is built. Their
decisions are frozen and are not repeated during resolution. A filter passed directly to `resolve(...)` selects among
already-compiled root plans.

Pre-configurations are compiled as lazy singleton initializers. Their dependency paths are validated during build. Shared
targets run one definition in declaration order, and concurrent first resolutions join the same attempt. Optional
failures can be logged and suppressed with `continue_on_failure=True`; other failures remain retryable.

## Scopes, provided values, and overlays

An ordinary scope reuses the compiled plan:

```python
builder.declare_scope_slot(RequestContext)
builder.register(RequestHandler)
container = builder.build()

with container.new_scope() as scope:
    scope.provide(RequestContext, current_request)
    handler = scope.resolve(RequestHandler)
```

Slots represent values that are unavailable during root compilation, such as request or framework context. Only declared
slots may be provided. Duplicate provisions are rejected, and provisions lock when resolution starts. Nested scopes
inherit provided values and may override them before their first resolve.

Use `ScopeBuilder` when a child scope requires different registrations or decorators:

```python
tenant_builder = container.new_scope_builder()
tenant_builder.register(PaymentGateway, TenantGateway)

with tenant_builder.build() as tenant_scope:
    tenant_scope.resolve(Checkout)
```

Singletons introduced by a `ScopeBuilder` belong to its built scope and descendants. Existing root singletons remain
anchored to the root container and cannot be rewired by overlay dependencies or decorators. A built overlay starts a
new scoped cache boundary and is finalized when that scope exits. The root container is not mutated.

## Lifespans and ownership

| Lifespan | Reuse boundary | Typical ownership |
| --- | --- | --- |
| `transient` | Every dependency edge | Context-sensitive objects |
| `once_per_graph` | One top-level resolve | Ordinary application services |
| `scoped` | One explicit scope | Request state, units of work, DB sessions |
| `singleton` | Owning container or compiled overlay scope | Settings, pools, long-lived clients |

Pass these as plain strings to `lifespan=`. The exported `Lifespan` name is a `Literal` type alias for annotations, not an enum.

Generator factories, context managers, and their async equivalents are finalized by their cache owner.

## FastAPI integration

FastAPI remains responsible for HTTP parameters, validation, and security dependencies. `Resolve` is the route-level
equivalent of `Depends` for an application entry point compiled by Clean IoC:

```python
from fastapi import FastAPI

from clean_ioc import ContainerBuilder
from clean_ioc.ext.fastapi import Resolve, install_fastapi


builder = ContainerBuilder()
builder.register(OrderRepository, SqlOrderRepository, lifespan="scoped")
builder.register(PlaceOrder)
container = builder.build()

app = FastAPI()
install_fastapi(app, container)


@app.post("/orders")
async def place_order(command: OrderRequest, handler: PlaceOrder = Resolve(PlaceOrder)):
    return await handler(command)
```

Native FastAPI supports nested dependency chains and caches repeated dependency callables within a request. For
framework-independent application classes, those chains require provider functions at each layer. Clean IoC derives the
application graph from ordinary constructor annotations and keeps only `Resolve(EntryPoint)` at the route boundary.

| Requirement | FastAPI with Clean IoC |
| --- | --- |
| Route-level application dependency | `service: Service = Resolve(Service)` |
| Request-owned component | `lifespan="scoped"` |
| Application-owned component | `lifespan="singleton"` |
| Shared value within one resolution | `lifespan="once_per_graph"` |
| Invalid component or lifespan graph | `ContainerBuildError` before activation |

The integration creates an ordinary child scope for each complete HTTP request or WebSocket connection. Streaming
responses, background work, and cleanup remain inside that boundary. FastAPI route selections are checked against the
compiled container during application startup.

## Composition features

- Sync and async factories, generators, context managers, and deterministic cleanup.
- Named, tagged, parent-aware, and descendant-aware component filters.
- Z-indexed decorators with stable IDs, builder patch/removal, owned metadata, and build-time validation.
- Build-time generic discovery, generic factory specialization, open-generic fallback, and plan-driven decorator policies.
- Immutable build inputs with explicit `build_arg(...)`, `generic_arg(...)`, and `inject()` argument policies.
- Coordinated first activation across threads and event loops.
- Bundles targeting one shared `ComponentBuilder` composition protocol.
- Synchronous custom graph rules with structured findings, path-aware traversal, lazy type-AST inspection, and
  strict-only CI execution.
- BenchBro experiments separating build cost, runtime latency, and Python allocations.

## Project links

- [Documentation](https://peter-daly.github.io/clean_ioc/)
- [Compiled scopes](https://peter-daly.github.io/clean_ioc/scopes/)
- [Compiler tooling](https://peter-daly.github.io/clean_ioc/compiler-tooling/)
- [Component filtering](https://peter-daly.github.io/clean_ioc/advanced/filtering/)
- [FastAPI integration](https://peter-daly.github.io/clean_ioc/extensions/fastapi/)
- [Benchmarks](https://peter-daly.github.io/clean_ioc/benchmarks/)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGES.rst)
