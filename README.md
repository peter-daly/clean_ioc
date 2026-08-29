# Clean IoC

**Compile your Python dependency graph once. Resolve it without rebuilding the graph.**

[![CI](https://github.com/peter-daly/clean_ioc/actions/workflows/ci.yml/badge.svg)](https://github.com/peter-daly/clean_ioc/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/clean-ioc.svg)](https://pypi.org/project/clean-ioc/)
[![Python](https://img.shields.io/pypi/pyversions/clean-ioc.svg)](https://pypi.org/project/clean-ioc/)
[![License](https://img.shields.io/pypi/l/clean-ioc.svg)](https://github.com/peter-daly/clean_ioc/blob/main/LICENSE)

Clean IoC is a typed dependency-injection container for Python 3.10+. Version 2 separates mutable composition from immutable runtime execution:

1. Register components with `ContainerBuilder`.
2. Call `build()` to validate and compile every visible dependency plan.
3. Resolve from the immutable `Container` or a lightweight `Scope`.

Constructors, factories, generators, and parameter value providers do not run during the build. At runtime Clean IoC executes frozen instructions, caches plain instances, and does not allocate a dependency graph.

> **2.0 alpha:** the compiled API is intentionally experimental while its compatibility surface and performance are hardened.

```bash
pip install clean_ioc
# With FastAPI support:
pip install "clean_ioc[fastapi]"
```

## See it in 30 seconds

Your application code uses ordinary Python types:

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

container = builder.build()  # validates and compiles; user code has not run
checkout = container.resolve(Checkout)

assert checkout.place_order(2500) == "charged:2500"
```

No application base classes. No decorators on domain code. No global container. No generated proxies.

## Why compile the container?

Traditional runtime DI repeatedly discovers registrations, evaluates contextual filters, and constructs bookkeeping nodes while resolving objects. Clean IoC moves that work to an explicit application boundary.

| Build time | Runtime |
| --- | --- |
| Specialize generic types | Select a frozen root plan |
| Build occurrence-specific component trees | Execute precompiled activation steps |
| Evaluate component and decorator filters | Cache plain instances by lifespan |
| Detect missing, circular, and captive dependencies | Coordinate concurrent scoped/singleton builds |
| Freeze decorators, pre-configurations, and fallback edges | Track only activation and teardown state |

`build()` fails before startup completes if a graph is incomplete, a singleton captures scoped state, or a singleton/scoped component captures `once_per_graph` state. The lifespan checks are transitive, so a transient wrapper cannot hide a captive dependency. A failed build leaves the builder reusable, so composition can be repaired and built again. A successful builder is single-use.

## Make the object graph reviewable

Mark the requests that start your application and turn the compiled graph into a CI-verifiable artifact:

```python
builder.mark_entrypoint(Checkout)
container = builder.build()

print(container.build_report.to_text())
print(container.graph.to_mermaid())
container.graph.manifest().to_json()
```

```bash
clean-ioc check my_app.composition:application_builder --strict
clean-ioc graph my_app.composition:application_builder --format json -o dependency-graph.json
clean-ioc diff my_app.composition:application_builder dependency-graph.json
```

Build errors are aggregated across independent roots. Stable JSON manifests omit configured values and runtime identities, so wiring changes can be reviewed without serializing secrets. Entry points focus the default graph and warn about unreachable registrations; every visible root is still compiled, validated, and resolvable.

## One static model: `Component`

Registration metadata and dependency-graph nodes are replaced by one immutable, plan-backed model. Every `Component` exposes its service, implementation, lifespan, name, tags, generic mapping, parent, dependencies, decorators, and pre-configurations.

```python
import clean_ioc.component_filters as cf

builder.register(PaymentGateway, StripeGateway, name="stripe")

component_id = builder.get_component_id(
    PaymentGateway,
    filter=cf.with_name("stripe"),
)
```

Use the same filters for root selection, dependency selection, contextual registration, decorators, and pre-configuration:

```python
builder.register(
    PaymentGateway,
    StripeGateway,
    when=cf.parent(cf.has_tag("channel", "web")),
)

gateway = container.resolve(PaymentGateway, filter=cf.with_name("stripe"))
```

Composition, dependency, decorator, and pre-configuration filters run while the container or scope is built. Their decisions are frozen and are not repeated during resolution. A filter passed directly to `resolve(...)` only selects among those already-compiled root plans.

## Scopes, request values, and experimental overlays

Creating an ordinary scope is cheap and never compiles:

```python
builder.declare_scope_slot(RequestContext)
builder.register(RequestHandler)
container = builder.build()

with container.new_scope() as scope:
    scope.provide(RequestContext, current_request)
    handler = scope.resolve(RequestHandler)
```

Slots make late request/framework values explicit. Only declared slots may be provided; duplicate provisions are rejected, and provisions lock when resolution starts. Nested scopes inherit provided values and may override them before their first resolve.

When a child genuinely needs different composition, use `ScopeBuilder` and pay the compile cost explicitly:

```python
tenant_builder = container.new_scope_builder()
tenant_builder.register(PaymentGateway, TenantGateway)

with tenant_builder.build() as tenant_scope:
    tenant_scope.resolve(Checkout)
```

Singletons introduced by a `ScopeBuilder` belong to its built scope and descendants. Existing root singletons remain anchored to the root container and cannot be rewired by overlay dependencies or decorators. A built overlay also starts a fresh scoped cache boundary. It is finalized when that built scope exits, without mutating the root container.

## Lifespans that match ownership

| Lifespan | Reuse boundary | Typical ownership |
| --- | --- | --- |
| `transient` | Every dependency edge | Context-sensitive objects |
| `once_per_graph` | One top-level resolve | Ordinary application services |
| `scoped` | One explicit scope | Request state, units of work, DB sessions |
| `singleton` | Owning container or compiled overlay scope | Settings, pools, long-lived clients |

Pass these as plain strings to `lifespan=`. The exported `Lifespan` name is a `Literal` type alias for annotations, not an enum.

Generator factories, context managers, and their async equivalents are finalized by their cache owner.

## FastAPI without framework-coupled services

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

The integration creates an ordinary child scope for the complete HTTP request or WebSocket connection. Streaming responses, background work, and cleanup remain inside that boundary. FastAPI route selections are checked against the compiled container during application startup.

## Built for demanding object graphs

- Sync and async factories, generators, context managers, and deterministic cleanup.
- Named, tagged, parent-aware, and descendant-aware component filters.
- Z-indexed decorators with stable IDs, builder patch/removal, owned metadata, and build-time validation.
- Build-time generic discovery, generic factory specialization, open-generic fallback, and plan-driven decorator policies.
- Coordinated first activation across threads and event loops.
- Bundles targeting one shared `ComponentBuilder` composition protocol.
- BenchBro experiments separating build cost, runtime latency, and Python allocations.

Clean IoC is a particularly good fit for Clean Architecture, hexagonal applications, CQRS handlers, message consumers, CLIs, and FastAPI services where dependency ownership matters beyond one function call.

## Project links

- [Documentation](https://peter-daly.github.io/clean_ioc/)
- [Compiled scopes](https://peter-daly.github.io/clean_ioc/scopes/)
- [Compiler tooling](https://peter-daly.github.io/clean_ioc/compiler-tooling/)
- [Component filtering](https://peter-daly.github.io/clean_ioc/advanced/filtering/)
- [FastAPI integration](https://peter-daly.github.io/clean_ioc/extensions/fastapi/)
- [Benchmarks](https://peter-daly.github.io/clean_ioc/benchmarks/)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGES.rst)

If this model fits a problem other Python DI containers make awkward, consider starring the repository. It helps the right niche find it.
