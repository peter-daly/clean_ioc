# Boundaries and visibility

A bundle groups registrations; a boundary controls access to them. Wrap an ordinary bundle in a `Boundary` to make
its registrations private by default at compile time. `Expose` makes one unchanged local component visible to root
composition; `Use` admits one unchanged root or exposed component into another boundary.

Boundaries do not create child containers, runtime namespaces, aliases, proxies, or plugin loaders. A boundary
changes only candidate visibility. The selected component keeps its service type, implementation, name, tags,
lifespan, instance identity, cache, and cleanup owner.

```python
from dataclasses import dataclass
from typing import Protocol

from clean_ioc import Boundary, ContainerBuilder, Expose, Use


@dataclass(frozen=True)
class Settings:
    stripe_key: str


class PaymentGateway(Protocol): ...


class StripeSdk:
    def __init__(self, settings: Settings): ...


class StripeGateway(PaymentGateway):
    def __init__(self, sdk: StripeSdk): ...


class PlaceOrder:
    def __init__(self, gateway: PaymentGateway): ...


def payments_bundle(builder):
    builder.register(StripeSdk, lifespan="singleton")
    builder.register(PaymentGateway, StripeGateway, lifespan="singleton")


def orders_bundle(builder):
    builder.register(PlaceOrder)
    builder.mark_entrypoint(PlaceOrder)


payments = Boundary(
    name="payments",
    root_bundle=payments_bundle,
    uses=(Use.root(Settings),),
    exposes=(Expose(PaymentGateway),),
)
orders = Boundary(
    name="orders",
    root_bundle=orders_bundle,
    uses=(Use("payments", PaymentGateway),),
    exposes=(Expose(PlaceOrder),),
)

builder = ContainerBuilder()
builder.register(Settings, instance=Settings("secret"))
builder.install_boundary(orders)    # installation order is immaterial
builder.install_boundary(payments)
container = builder.build()

container.resolve(PlaceOrder)      # exposed
container.resolve(PaymentGateway)  # exposed
# container.resolve(StripeSdk)     # private: raises CannotResolveError
```

The payments component may use `Settings` only because it declares `Use.root(Settings)`. Orders may use the gateway
only because payments exposes it and orders names that exposure in `Use`. Root composition sees every exposure without
declaring a use. A boundary cannot expose a component that it obtained through `Use`; register and expose a local
adapter when publishing a different contract.

## Named and tagged components

Boundary declarations select exactly one original component. Use the normal component filters to select a named or
tagged definition, then use the normal argument-selection API in the consumer:

```python
from clean_ioc import Expose, Tag, Use, select
from clean_ioc import component_filters as cf


def payments_bundle(builder):
    builder.register(
        PaymentGateway,
        StripeGateway,
        name="stripe",
        tags=(Tag("region", "global"),),
    )


def checkout_bundle(builder):
    builder.register(
        Checkout,
        arguments={"gateway": select(cf.with_name("stripe"))},
    )


payments = Boundary(
    "payments",
    payments_bundle,
    exposes=(Expose(PaymentGateway, filter=cf.with_name("stripe")),),
)
checkout = Boundary(
    "checkout",
    checkout_bundle,
    uses=(Use("payments", PaymentGateway, filter=cf.with_name("stripe")),),
    exposes=(Expose(Checkout),),
)
```

The component is still named `"stripe"`; exposure does not make it the unnamed default. Tags remain available to
filters and graph tooling. Declare one `Expose` per collection member that should be public and one `Use` per member
that a consumer should admit.

## Entry points, providers, and policies

`mark_entrypoint()` remains a tooling declaration, not an access grant. A marker inside a boundary must select one
local component that the `Boundary` also exposes. Root composition may mark a root registration or an exposure.

`Provider[T]` and `AsyncProvider[T]` freeze `T` using the visibility of the component that injects the provider, so
deferred execution cannot widen access. Raw `Scope` and `ResolutionContext` injection remain deliberate runtime escape
hatches; use typed providers when architecture segregation matters.

`register_provider_map(...)` is also available inside boundary bundles. Its entries use the map declaration's visibility;
exposing `Mapping[K, Provider[T]]` publishes that map without publishing or changing the ownership of its private target
registrations. `Use` may admit an exposed map into another boundary. See
[lazy provider maps](advanced/special-dependency-types.md#lazy-provider-maps).

Validation rules installed at root receive the complete graph. A rule installed by a boundary bundle receives that
boundary's local roots and outgoing boundary edges; `ValidationContext.boundary` and `GraphVisit.boundary` identify the
relevant defining area.

## Decorators, scope slots, and overlays

Decorators, pre-configurations, and registration discovery inside a boundary apply only to that boundary's local
registrations. They do not implicitly alter a component across a boundary.

Private boundary scope slots are not supported because runtime `Scope.provide()` has no boundary qualifier. Declare a
root slot and admit it with `Use.root(...)` instead.

`ScopeBuilder.install_boundary()` can add a new overlay-owned boundary and that boundary can use parent exposures. An
overlay cannot reopen, patch, or reuse the name of a parent boundary. A parent boundary never sees a boundary added by
a child overlay, and parent-owned singleton plans and cleanup ownership stay frozen.

`Expose`, `Use`, and `Use.root` accept native or backported type aliases. Boundary matching uses canonical service keys,
so an alias changes neither visibility nor ownership and cannot expose a private component indirectly.

## Diagnostics and review

Boundary names use `^[a-z][a-z0-9_-]*$`; `root` is reserved. Build-time errors distinguish invalid or duplicate names,
use cycles, missing and ambiguous exposure/use selection, private dependencies, re-exports, entry-point violations,
private slots, cross-boundary decoration, and prohibited overlay access.

Graph text and Mermaid output label defining boundaries and boundary edges. Manifests record the deterministic
boundary contract, resolved exposures and uses, component areas, and cross-boundary sources without serializing bundle
objects, filters, configured values, build inputs, owner tokens, or runtime identities. The `boundaries`, `boundary`,
and `source_boundary` fields describe visibility. Semantic diffs classify boundary additions, removals, uses,
exposures, and component moves. Tooling formats remain unversioned during beta; regenerate saved graphs and baselines
when the format changes. Schema versioning will begin after beta.

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc graph my_app.composition:application_builder --format mermaid
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway
```
