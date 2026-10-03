# Boundaries and visibility

A bundle groups registrations; a boundary controls access to them. Call `create_boundary()` on a container or scope
builder to obtain a `BoundaryBuilder`. Apply ordinary bundles or register components directly on that retained handle;
its registrations are private by default. `Expose` makes one local component visible to root composition; `Use` admits
one root or exposed component into another boundary.

Boundaries do not create child containers, runtime namespaces, proxies, or plugin loaders. A boundary changes candidate
visibility and may project a different public service type, name, and complete tag set. The source plan keeps its
implementation, decorators, pre-configurations, lifespan, registration identity, runtime instance, cache, and cleanup
owner.

```python
from dataclasses import dataclass
from typing import Protocol

from clean_ioc import ContainerBuilder, Expose, Use


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


builder = ContainerBuilder()
builder.register(Settings, instance=Settings("secret"))
payments = builder.create_boundary(
    name="payments",
    uses=(Use.root(Settings),),
    exposes=(Expose(PaymentGateway),),
)
orders = builder.create_boundary(
    name="orders",
    uses=(Use("payments", PaymentGateway),),
    exposes=(Expose(PlaceOrder),),
)

orders.apply_bundle(orders_bundle)  # contribution order across boundaries is immaterial
payments.apply_bundle(payments_bundle)
container = builder.build()

container.resolve(PlaceOrder)      # exposed
container.resolve(PaymentGateway)  # exposed
# container.resolve(StripeSdk)     # private: raises CannotResolveError
```

The payments component may use `Settings` only because it declares `Use.root(Settings)`. Orders may use the gateway
only because payments exposes it and orders names that exposure in `Use`. Root composition sees every exposure without
declaring a use. A boundary cannot expose a component that it obtained through `Use`; register and expose a local
adapter when publishing a different contract.

## Incremental composition and lifecycle

Keep the handle to contribute more bundles before the parent builds:

```python
builder = ContainerBuilder()
builder.register(Settings, instance=Settings("secret"))
payments = builder.create_boundary(
    "payments", uses=(Use.root(Settings),), exposes=(Expose(PaymentGateway),)
)
payments.apply_bundle(payments_bundle)

# Later contributions use the same ordinary ComponentBuilder operations.
payments.add_validation_rule(lambda context: ())
component_id = payments.get_component_id(PaymentGateway)
if component_id is not None:
    payments.patch_component(PaymentGateway, component_id, lifespan="scoped")

container = builder.build()
```

A convenience bundle may create a boundary and retain or return its handle through its own API. Possessing that
handle grants explicit access to configure the subsystem; applying a bundle to the parent never redirects it into a
boundary. `ComponentBuilder` includes `create_boundary()` so boundary-owning bundles can use the shared protocol.
Nested boundaries are not supported: calling `create_boundary()` on a boundary handle raises `ValueError`.

Registrations, decorators, pre-configurations, discovery rules, and validation rules are snapshotted during parent
compilation. A successful parent build freezes every owned boundary handle, including handles retained by bundles.
Further mutations raise `BuilderAlreadyBuiltError`. A boundary has no separate `build()` or resolution API, and runtime
containers and scopes remain immutable.

A failed build leaves both parent and boundary composition editable. Register missing dependencies, patch components,
or replace visibility declarations and retry the parent build. The `uses` and `exposes` properties accept iterables and
store tuples; for example, `payments.exposes = (*payments.exposes, Expose(StripeSdk))` explicitly changes the public
contract. Names are fixed when a boundary is created, and duplicate names never reopen an existing boundary.

`has_component()`, `get_component_id()`, and `get_component_ids()` on the boundary handle preview its local registrations
and explicitly admitted components with the parent's current composition and build arguments. These queries do not
freeze the builder, but still require valid visibility contracts and compilable queried dependencies. Parent queries
cannot see unexposed private registrations, and parent patch operations cannot change them.

Bundle application has the same semantics on every builder: if a bundle raises, earlier operations remain in the
composition. Repair that retained state before retrying. Successfully applied run-once bundles retain their claims;
neither a later bundle exception nor a failed compilation rolls their registrations back.

The former `Boundary(root_bundle=...)` declaration and `install_boundary()` API have been removed. Migrate by creating
the boundary, then calling `boundary.apply_bundle(previous_root_bundle)`; additional bundles can use that same handle.

## Named and tagged components

Boundary declarations select exactly one original component. Use the normal component filters to select a named or
tagged definition, then use the normal argument-selection API in the consumer:

```python
from clean_ioc import Expose, Tag, Use, select
from clean_ioc import component_filters as cf


def payments_bundle(builder):
    builder.register(StripeSdk)
    builder.register(
        PaymentGateway,
        StripeGateway,
        name="stripe",
        tags=(Tag("region", "global"),),
    )


class Checkout:
    def __init__(self, gateway: PaymentGateway):
        self.gateway = gateway


def checkout_bundle(builder):
    builder.register(
        Checkout,
        arguments={"gateway": select(cf.with_name("stripe"))},
    )


builder = ContainerBuilder()
builder.register(Settings, instance=Settings("secret"))
payments = builder.create_boundary(
    "payments",
    uses=(Use.root(Settings),),
    exposes=(Expose(PaymentGateway, filter=cf.with_name("stripe")),),
)
checkout = builder.create_boundary(
    "checkout",
    uses=(Use("payments", PaymentGateway, filter=cf.with_name("stripe")),),
    exposes=(Expose(Checkout),),
)
payments.apply_bundle(payments_bundle)
checkout.apply_bundle(checkout_bundle)
container = builder.build()
```

The component is still named `"stripe"`; exposure does not make it the unnamed default. Tags remain available to
filters and graph tooling. Declare one `Expose` per collection member that should be public and one `Use` per member
that a consumer should admit.

An exposure may instead define a complete public identity with `BoundaryAlias`. The exposure filter sees the local
service type, name, and tags; root composition and consuming boundaries see the alias service type, name, and tags:

```python
from clean_ioc import BoundaryAlias


class PublicPaymentGateway(Protocol): ...


builder = ContainerBuilder()
builder.register(Settings, instance=Settings("secret"))
payments = builder.create_boundary(
    "payments",
    uses=(Use.root(Settings),),
    exposes=(
        Expose(
            PaymentGateway,
            filter=cf.with_name("stripe"),
            alias=BoundaryAlias(
                PublicPaymentGateway,
                name="primary",
                tags=(Tag("audience", "public"),),
            ),
        ),
    ),
)


class AliasedCheckout:
    def __init__(self, gateway: PublicPaymentGateway):
        self.gateway = gateway


def aliased_checkout_bundle(builder):
    builder.register(
        AliasedCheckout,
        arguments={"gateway": select(cf.with_name("primary"))},
    )


checkout = builder.create_boundary(
    "checkout",
    uses=(Use("payments", PublicPaymentGateway, filter=cf.with_name("primary")),),
    exposes=(Expose(AliasedCheckout),),
)

payments.apply_bundle(payments_bundle)
checkout.apply_bundle(aliased_checkout_bundle)
container = builder.build()
gateway = container.resolve(PublicPaymentGateway, filter=cf.with_name("primary"))
```

Selection happens on the appropriate side of the contract. `Expose.service_type` and `Expose.filter` select exactly
one local component using its source service type, name, and tags. A consuming `Use` must name the public service type,
and `Use.filter` runs against the public name and tags. Root resolution uses that same public view. Neither a `Use`
filter nor a root filter can select an aliased exposure by its source name or source tags.

This is a boundary contract, not another registration or a proxy. Internal dependencies, exposure filters, and
registration policies still see `PaymentGateway`, `"stripe"`, and the original tags. External filters and graph
contracts see `PublicPaymentGateway`, `"primary"`, and only the alias tags. The alias therefore does not duplicate
singleton state or change lifespan, caching, instance identity, or cleanup ownership. Omitting `alias` preserves the
local service type, name, and tags. A boundary may publish multiple distinct aliases for the same source registration;
exact duplicate public identities are rejected.

## Entry points, providers, and policies

`mark_entrypoint()` remains a tooling declaration, not an access grant. A marker inside a boundary must select one
local component that the boundary also exposes. Root composition may mark a root registration or an exposure.

`Provider[T]` and `AsyncProvider[T]` freeze `T` using the visibility of the component that injects the provider, so
deferred execution cannot widen access. Raw `Scope` and `ResolutionContext` injection remain deliberate runtime escape
hatches; use typed providers when architecture segregation matters.

Aliases follow the same rule through eager collections and typed providers. Root or a boundary that has admitted
`PublicPaymentGateway` may request a collection, `Provider[PublicPaymentGateway]`, or
`AsyncProvider[PublicPaymentGateway]`; matching and filtering use the public identities, while invocation activates the
original source plans. Requesting `PaymentGateway` externally does not bypass the alias. Inside `payments`, collections
and providers continue to select the source identity.

`register_provider_map(...)` is also available inside boundary bundles. Its entries use the map declaration's visibility;
exposing `Mapping[K, Provider[T]]` publishes that map without publishing or changing the ownership of its private target
registrations. The map service itself may be exposed under a `BoundaryAlias`; root and consuming `Use` declarations then
select the map by its public alias, but its entries retain the source map's already-compiled private target plans. `Use`
may admit an exposed map into another boundary. See
[lazy provider maps](advanced/special-dependency-types.md#lazy-provider-maps).

Validation rules installed at root receive the complete graph. A rule installed by a boundary bundle receives that
boundary's local roots and outgoing boundary edges; `ValidationContext.boundary` and `GraphVisit.boundary` identify the
relevant defining area.

## Decorators, scope slots, and overlays

Decorators, pre-configurations, and registration discovery inside a boundary apply only to that boundary's local
registrations. They do not implicitly alter a component across a boundary.

Private boundary scope slots are not supported because runtime `Scope.provide()` has no boundary qualifier. Declare a
root slot and admit it with `Use.root(...)` instead.

`ScopeBuilder.create_boundary()` can add a new overlay-owned boundary and that boundary can use parent exposures. An
overlay cannot reopen, patch, or reuse the name of a parent boundary. A parent boundary never sees a boundary added by
a child overlay, and parent-owned singleton plans and cleanup ownership stay frozen.

Parent exposures keep their public aliases in an overlay. An overlay-owned boundary names that public identity in
`Use`, and overlay root resolution also uses the public identity. The overlay cannot use the source identity to bypass
the contract or re-alias the parent exposure; it must register and expose a local adapter to publish another contract.

`Expose`, `Use`, and `Use.root` accept native or backported type aliases. Boundary matching uses canonical service keys,
so an alias changes neither visibility nor ownership and cannot expose a private component indirectly.

## Diagnostics and review

Boundary names use `^[a-z][a-z0-9_-]*$`; `root` is reserved. Creation rejects invalid, duplicate, or inherited boundary
names. Build-time errors distinguish use cycles, missing and ambiguous exposure/use selection, private dependencies, re-exports, entry-point violations,
private slots, cross-boundary decoration, and prohibited overlay access.

Graph text and Mermaid output label defining boundaries and boundary edges. Manifests record the deterministic boundary
contract, resolved exposures and uses, component areas, and cross-boundary sources without serializing bundle objects,
filters, configured values, build inputs, owner tokens, or runtime identities. Each exposure records its public identity
as `service`, `name`, and `tags`, and its selected local identity as `source_service`, `source_name`, and `source_tags`.
The `boundaries`, `boundary`, and `source_boundary` fields describe visibility.

Semantic diffs compare the whole recorded exposure. Changing a source field or a public alias field therefore reports
the old contract as `boundary-exposure-removed` with high risk and the new contract as `boundary-exposure-added` with
medium risk. The diff does not classify source and public edits separately. Boundary additions, removals, uses, and
component moves have their own classifications. Tooling formats remain unversioned during beta; regenerate saved graphs
and baselines when the format changes. Schema versioning will begin after beta.

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc graph my_app.composition:application_builder --format mermaid
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway
```
