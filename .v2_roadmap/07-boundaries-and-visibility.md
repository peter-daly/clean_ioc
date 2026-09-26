# Boundaries and visibility

Status: Done
Priority: P2
Dependencies: Compilation provenance; resource ownership proof
Integration dependencies: Typed deferred dependencies for service-locator-free deferred resolution; semantic graph-change
policy for diff classification

## Summary

Add opt-in `Boundary` declarations that give existing bundles a compile-time visibility boundary. Registrations made by
a boundary's `root_bundle` are private by default. `Expose` makes a local component visible at the root, optionally
under a public name, and `Use` admits an exposed component into another boundary.

A boundary segregates composition; it is not a Python module, package, plugin loader, or runtime child container.
Crossing a boundary never changes a component's decorators, lifespan, registration identity, runtime instance, cache,
or cleanup owner. A `BoundaryAlias` may project a distinct public service type, name, and complete tag set.

## Core decisions

The first release follows four rules:

1. A component registered inside a boundary is visible only inside that boundary unless explicitly exposed.
2. Another boundary sees an exposure only after explicitly declaring a use of it.
3. The root composition sees every exposure as a normal resolution candidate; entry-point marking does not affect
   visibility.
4. `Expose` and `Use` change visibility. `BoundaryAlias` may define a complete external selection identity, but never
   clones, proxies, or re-registers a component.

By default, a component registered with `name="stripe"` is exposed and used with its original type, name, and tags.
Declaring `Expose(..., alias=BoundaryAlias(PaymentGateway, name="primary", tags=(...)))` keeps the source identity on
the defining side while root composition and consuming boundaries select the complete public identity.

## Problem and differentiation

Bundles make registration reusable but intentionally add everything to the builder that receives them. In a large
application, a repository, SDK client, or infrastructure implementation can therefore be selected by an unrelated
feature merely because its type is present in the shared registry. Names and tags guide selection but do not prevent
selection.

Boundaries turn composition boundaries into compiler-enforced architecture. The compiler can prove that every
cross-boundary dependency was intentionally exposed and used, report the exact boundary involved, and include the
resulting contract in graph reviews. Existing Python DI libraries commonly offer reusable registration groups; fewer
make their public surface part of a statically validated dependency graph.

## Goals

- Keep boundary registrations private by default.
- Reuse ordinary Clean IoC bundles as the contents of a boundary.
- Require explicit `Use` declarations for dependencies on the root or another boundary.
- Preserve registration/runtime identity while allowing an explicit boundary alias to project public selection metadata.
- Preserve constructor injection, factories, generics, decorators, pre-configurations, lifespans, ownership, and typed
  deferred dependencies within the visibility model.
- Record boundary identity and boundary crossings in provenance, graph rendering, manifests, and semantic diffs.
- Preserve `mark_entrypoint()` as a tooling declaration for exposed boundary roots without turning it into an access
  grant.
- Reject boundary dependency cycles before compiling component activation plans.
- Keep existing builders, bundles, resolution calls, and applications fully compatible unless they opt in.

## Non-goals

- Controlling Python imports or dictating source-code directory structure.
- Treating boundaries as Python modules, packages, namespaces, distributions, or plugin-discovery mechanisms.
- Providing a security sandbox against direct construction, Python imports, or deliberate service-locator use.
- Runtime installation, enablement, unloading, or mutation of boundaries.
- Creating a child container or runtime lookup boundary for each boundary.
- Retagging components or renaming them implicitly while exposing or using them; public projection is explicit.
- Automatically exporting everything created by a bundle.
- Allowing one boundary to reopen or patch another boundary's private registrations.

## Representative user stories

- Payments exposes `PaymentGateway` while keeping `StripeSdk` and its retry implementation private.
- Orders explicitly uses the payments gateway and the database pool it needs.
- A build fails when orders accidentally requests a private payments implementation.
- An existing third-party bundle can be used unchanged as a boundary's `root_bundle`.
- A graph diff reports that a component became exposed or that one boundary gained a new dependency.
- A named or tagged component keeps the same selection identity unless its exposure explicitly supplies a
  `BoundaryAlias`.
- Orders can mark its exposed `PlaceOrder` component as an intended application root from inside its bundle.

## Full example

The bundle passed as `root_bundle` is an ordinary existing Clean IoC bundle:

```python
from dataclasses import dataclass
from typing import Protocol

from clean_ioc import Boundary, ComponentBuilder, ContainerBuilder, Expose, Use


@dataclass(frozen=True)
class AppSettings:
    database_url: str
    stripe_key: str


class PaymentGateway(Protocol): ...


class DatabasePool:
    def __init__(self, settings: AppSettings): ...


class StripeSdk:
    def __init__(self, settings: AppSettings): ...


class StripePaymentGateway(PaymentGateway):
    def __init__(self, sdk: StripeSdk): ...


class OrderRepository:
    def __init__(self, pool: DatabasePool): ...


class PlaceOrder:
    def __init__(self, repository: OrderRepository, payments: PaymentGateway): ...


def database_bundle(builder: ComponentBuilder) -> None:
    builder.register(DatabasePool, lifespan="singleton")


def payments_bundle(builder: ComponentBuilder) -> None:
    builder.register(StripeSdk, lifespan="singleton")
    builder.register(PaymentGateway, StripePaymentGateway, lifespan="singleton")


def orders_bundle(builder: ComponentBuilder) -> None:
    builder.register(OrderRepository, lifespan="scoped")
    builder.register(PlaceOrder, lifespan="scoped")
    builder.mark_entrypoint(PlaceOrder)


database = Boundary(
    name="database",
    root_bundle=database_bundle,
    uses=(Use.root(AppSettings),),
    exposes=(Expose(DatabasePool),),
)

payments = Boundary(
    name="payments",
    root_bundle=payments_bundle,
    uses=(Use.root(AppSettings),),
    exposes=(Expose(PaymentGateway),),
)

orders = Boundary(
    name="orders",
    root_bundle=orders_bundle,
    uses=(
        Use("database", DatabasePool),
        Use("payments", PaymentGateway),
    ),
    exposes=(Expose(PlaceOrder),),
)

builder = ContainerBuilder()
builder.register(
    AppSettings,
    instance=AppSettings(
        database_url="postgresql://localhost/orders",
        stripe_key="secret",
    ),
)
builder.install_boundary(database)
builder.install_boundary(payments)
builder.install_boundary(orders)

container = builder.build()

with container.new_scope() as scope:
    handler = scope.resolve(PlaceOrder)
```

The root can resolve `DatabasePool`, `PaymentGateway`, and `PlaceOrder` because they are exposed. It cannot resolve
`StripeSdk` or `OrderRepository`. The orders boundary can depend on the two components it uses, but it cannot see
`AppSettings`, `StripeSdk`, or any other root or boundary registration that it did not declare.

The `mark_entrypoint(PlaceOrder)` call focuses graph and reachability tooling. It is valid because the `orders`
declaration separately exposes `PlaceOrder`; the marker itself does not make the component visible.

## Named and tagged components

Names and tags are part of the component being made visible, not properties of the boundary:

```python
from clean_ioc import Boundary, ContainerBuilder, Expose, Tag, Use, select
from clean_ioc import component_filters as cf


class Checkout:
    def __init__(self, gateway: PaymentGateway): ...


def named_payments_bundle(builder: ComponentBuilder) -> None:
    builder.register(StripeSdk, lifespan="singleton")
    builder.register(
        PaymentGateway,
        StripePaymentGateway,
        lifespan="singleton",
        name="stripe",
        tags=(Tag("region", "global"),),
    )


def checkout_bundle(builder: ComponentBuilder) -> None:
    builder.register(
        Checkout,
        arguments={"gateway": select(cf.with_name("stripe"))},
    )


payments = Boundary(
    name="payments",
    root_bundle=named_payments_bundle,
    uses=(Use.root(AppSettings),),
    exposes=(
        Expose(PaymentGateway, filter=cf.with_name("stripe")),
    ),
)

checkout = Boundary(
    name="checkout",
    root_bundle=checkout_bundle,
    uses=(
        Use("payments", PaymentGateway, filter=cf.with_name("stripe")),
    ),
    exposes=(Expose(Checkout),),
)

builder = ContainerBuilder()
builder.register(
    AppSettings,
    instance=AppSettings(
        database_url="postgresql://localhost/orders",
        stripe_key="secret",
    ),
)
builder.install_boundary(payments)
builder.install_boundary(checkout)
container = builder.build()

gateway = container.resolve(PaymentGateway, filter=cf.with_name("stripe"))
same_gateway = container.resolve(
    PaymentGateway,
    filter=cf.has_tag("region", "global"),
)
```

Both resolutions select the same exposed component. Its name remains `"stripe"`, and its `region=global` tag remains
visible to filters and graph tooling. An unnamed/default resolution does not select it. There is no independent set of
"public tags" and no implicit tag inheritance rule because no second component is created.

For a named dependency, the consuming bundle must use the normal argument-selection API, as `checkout_bundle` does
above. `Use` does not turn a named component into the default.

## Proposed public API

Add `clean_ioc.boundaries` and re-export its four declarations from `clean_ioc`:

```python
from collections.abc import Callable
from dataclasses import dataclass

from clean_ioc import ComponentBuilder, ComponentFilter, Tag, default_component_filter


@dataclass(frozen=True, slots=True)
class BoundaryAlias:
    service_type: object
    name: str | None = None
    tags: tuple[Tag, ...] = ()


@dataclass(frozen=True, slots=True)
class Expose:
    service_type: object
    filter: ComponentFilter = default_component_filter
    alias: BoundaryAlias | None = None


@dataclass(frozen=True, slots=True)
class Use:
    source: str | None
    service_type: object
    filter: ComponentFilter = default_component_filter

    @classmethod
    def root(
        cls,
        service_type: object,
        *,
        filter: ComponentFilter = default_component_filter,
    ) -> "Use": ...


@dataclass(frozen=True, slots=True)
class Boundary:
    name: str
    root_bundle: Callable[[ComponentBuilder], None]
    uses: tuple[Use, ...] = ()
    exposes: tuple[Expose, ...] = ()
```

`Use.root(...)` stores `source=None`; ordinary `Use("payments", PaymentGateway)` names its source boundary. The public
spelling `root` is reserved and cannot be used as a boundary name.

Add `install_boundary(boundary: Boundary) -> None` to `ContainerBuilder` and `ScopeBuilder`, but not to the
`ComponentBuilder` protocol. This keeps ordinary bundle authors source-compatible and prevents a bundle running inside
a boundary from nesting or installing another boundary.

`install_boundary()` creates a private builder, applies `root_bundle` exactly once, and records the resulting immutable
boundary blueprint. Applying nested bundles from `root_bundle` remains inside the same boundary and retains the normal
bundle provenance stack. If bundle application raises, the private builder is discarded and the root builder is not
partially modified.

Boundary names match `^[a-z][a-z0-9_-]*$`, are unique across a root and all its overlays, and are identifiers in the
compiled architecture contract rather than Python import names. Use resolution is deferred until `build()`, so boundary
installation order does not affect the result.

## Visibility and selection semantics

The compiler associates every registration with one composition area: root or a named boundary. It does not add the
area to the component's resolution key. The component still has the existing `(service_type, name, tags)` selection
identity; the area is an additional candidate-visibility constraint.

Inside a boundary:

1. Local dependency requests consider matching local registrations.
2. Each `Use` adds its one selected component to the boundary's visible candidate set without creating a registration.
3. Root registrations are invisible unless selected by `Use.root(...)`.
4. Registrations from another boundary are invisible unless that boundary exposes them and the consumer declares a
   matching `Use`.
5. If local and used components both match, existing ordering and ambiguity behavior applies; `Use` is not an override.
6. An `Expose` filter runs against the local component type, name, and tags. Root and consuming-boundary filters see the
   complete `BoundaryAlias` identity when supplied; implementation type, lifespan, and generic mapping remain unchanged.

At the root:

- root registrations retain their existing visibility;
- exposed boundary components join the root-visible candidate set with unchanged registration identity and their
  declared public type, name, and tags;
- private boundary components are not root-resolution candidates;
- normal filters and collection resolution operate over root registrations plus matching exposures;
- duplicate candidates retain existing ambiguity diagnostics and deterministic collection ordering.

`Expose` must select exactly one locally defined registration. `Use` must select exactly one root registration or one
exposure from its named source. The first release does not expose or use a whole filtered set with one declaration.
Applications expose multiple collection members with multiple declarations; resolving `list[Service]` then collects
the individually visible members.

A boundary cannot expose a component obtained through `Use`. To publish a different contract, it registers a local
wrapper or adapter and exposes that local registration. This keeps public ownership attributable to the defining
boundary and avoids implicit re-export chains.

`Use.root(...)` selects only definitions from root composition layers, including root scope slots. It does not select
another boundary's exposure indirectly through the root, which would bypass the named boundary dependency graph.

## Compiler plan

The compiler adds composition-area visibility before its existing occurrence-specific dependency compilation:

1. Freeze root layers and every installed boundary's private registration blueprint.
2. Validate boundary names, duplicate declarations, `Expose` cardinality, and `Use` targets.
3. Build the directed boundary-use graph and reject any cycle, even if no constructor cycle currently traverses it.
4. Resolve each `Expose` against local definitions only and record the unchanged registration identity plus complete
   external service, name, and tag identity.
5. Resolve each `Use` against root definitions or the named boundary's resolved exposures.
6. Compile roots in each area using only local candidates plus resolved uses. Contextual registration filters cannot see
   a caller beyond an exposure boundary.
7. Project exposed roots into the root candidate set without emitting a proxy, alias registration, or activation step.
8. Run existing captive-lifespan and resource-ownership proof over the complete cross-boundary graph.
9. Freeze direct runtime plans and discard mutable visibility indexes.

All local closed roots are compiled and validated even when private. This preserves V2's whole-container validation
model. Exposures add root-visible roots; they do not cause otherwise invalid private registrations to be ignored.

Boundary-use cycles fail before component-cycle analysis because the declared architecture must remain acyclic even
when the currently selected constructors happen not to traverse every use. The issue contains the complete cycle, for
example `orders -> payments -> database -> orders`.

## Decorators, pre-configurations, generics, and providers

- Decorators and pre-configurations declared inside a boundary apply only to registrations defined in that boundary.
- Root or consumer-boundary decorators do not implicitly decorate a component across a visibility boundary. A consumer
  that needs different behavior registers an explicit local wrapper.
- Registration discovery initiated by `root_bundle` materializes only inside that boundary. Discovered registrations
  remain private unless an `Expose` selects them.
- Open-generic exposures expose the selected local generic registration family. Each requested closed specialization is
  compiled using the defining boundary's visible candidates and retains normal specialization behavior.
- `Provider[T]` and `AsyncProvider[T]` compile their deferred target using the visibility of the boundary containing the
  provider dependency. Deferred execution cannot widen that candidate set.
- Raw `Scope` or `ResolutionContext` injection remains an explicit escape hatch rather than a security boundary. The
  first-party runtime-container-access policy should reject it for teams requiring strict segregation; typed providers
  are the supported deferred-resolution alternative.

Boundary-local scope-slot declarations are deferred from the first release because `Scope.provide(type, value, name)`
has no boundary qualifier. A boundary can use a root-declared slot through `Use.root(...)`. Adding private slots later
requires a separate provisioning API rather than silently sharing `(type, name)` between boundaries.

## Entry points and validation rules

`mark_entrypoint()` retains its current tooling-only meaning:

- root composition may mark a root registration or an exposed boundary component;
- a boundary's `root_bundle` may mark a component defined locally by that boundary;
- a locally marked component must also appear in that boundary's `exposes` declaration;
- marking a component never exposes it and does not replace `Expose` or `Use`;
- an entry-point marker does not propagate through `Use` into a consuming boundary;
- exposed components remain resolvable when they are not marked.

The compiler resolves root and boundary-local entry-point filters after exposures. It reports a structured issue when a
local marker selects a private component, an imported component, no component, or multiple components. Graph roots and
manifest entry-point views record the defining boundary so identically typed roots remain attributable.

A validation rule added by the root runs against the complete compiled graph. A rule added inside a boundary receives
that boundary's local roots and its outgoing boundary edges but does not govern the internal definitions of boundaries
it uses. `ValidationContext` and `GraphVisit` gain an `boundary: str | None` property so rules can state boundary policy
without relying on source paths or Python package names.

## Runtime and ownership behavior

There is no runtime `BoundaryContainer` and no runtime boundary lookup. Once compilation succeeds, a cross-boundary
dependency is a direct frozen plan reference like any other dependency.

- An exposed or used singleton is the same singleton owned by the root or overlay that declared its boundary.
- Scoped components share the resolving scope under existing semantics.
- Once-per-graph components share the current resolution graph under existing semantics.
- Cleanup-bearing transients follow the compiled resource-ownership proof.
- An exposure does not add a cache, finalizer, proxy, wrapper, or branch to activation.
- The uninstrumented runtime hot path performs no boundary visibility checks.

## Scopes and overlays

`ScopeBuilder.install_boundary()` may add a new boundary whose name does not exist in any parent blueprint. An overlay
cannot reopen a parent boundary, change its `root_bundle`, add or remove a use or exposure, patch a private parent
registration, or reuse its name.

An overlay boundary may use a parent boundary's exposure. `Use.root(...)` in an overlay boundary follows normal root
layer precedence across overlay and parent root registrations. A parent boundary can never depend on a boundary added
by a child overlay.

Overlay root registrations may supersede a parent exposure under existing root selection rules, but this does not
change the parent boundary or any already compiled use edge. Parent singletons retain their frozen activation plans and
owners. Components created by an overlay boundary belong to the overlay's existing runtime owner.

## Component model, provenance, and graph rendering

Add `Component.boundary: str | None`, where `None` means root composition. The value describes where the registration
was defined; it does not participate in ordinary component filtering unless a dedicated boundary filter is added.

`DefinitionOrigin` gains the same optional boundary identifier. Explanations record boundary decisions with stable
reason codes such as `selected-local`, `selected-use`, `rejected-not-exposed`, and `rejected-not-used`. Provenance and
source locations remain excluded from default manifests and fingerprints.

Text and Mermaid renderers label defining boundaries and cross-boundary edges while retaining the complete dependency
path. Private dependencies below an exposed root remain inspectable in local tooling; visibility is an architecture
rule, not information redaction or a security boundary.

Example CLI usage remains on the existing commands:

```console
clean-ioc check my_app.composition:application_builder
clean-ioc graph my_app.composition:application_builder --format mermaid
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway
```

## Manifests, fingerprints, and semantic changes

Keep graph manifests unversioned during beta and include:

- the defining boundary on every component node;
- a deterministic top-level list of boundaries;
- each resolved exposure's source service/name/tags and public service/name/tags;
- each resolved use's source area, visible name, and unchanged selected component identity;
- the source boundary on every cross-boundary dependency edge.

Boundary declarations and resolved visibility affect fingerprints because they change the architecture contract. The
`root_bundle` callable, filter callable identities, bundle objects, source locations, build-argument values, configured
values, runtime instances, and owner tokens are not serialized. A filter refactor that selects the same component does
not change the fingerprint.

Semantic graph changes add these categories:

| Change | Default risk |
| --- | --- |
| `boundary-added` with no exposure or use | Low |
| `boundary-removed` | High |
| `boundary-use-added` or `boundary-use-removed` | High |
| `boundary-exposure-added` | Medium |
| `boundary-exposure-removed` | High |
| `boundary-component-moved` | High |
| `boundary-bypassed` | Critical |

Comparisons use boundary metadata directly. Regenerate saved baselines when the format changes; do not infer boundary
ownership from Python type locations or add legacy comparison branches during beta.

## Invariants

- Every compiled registration belongs to exactly one composition area.
- Private registrations are never candidates outside their defining boundary.
- Every cross-boundary dependency edge corresponds to one resolved `Use`.
- Every root-visible boundary component corresponds to one resolved `Expose`.
- Every `Expose` and `Use` preserves the selected component's lifespan, implementation, registration identity, cache,
  instance, and cleanup owner; `BoundaryAlias` may replace its type, name, and tags only in external selection views.
- No exposure or use creates an activation step or changes resource ownership.
- A boundary can expose only a component it defines locally.
- The boundary-use graph is acyclic and independent of installation order.
- Build args are shared as existing immutable compilation inputs and their names and values remain secret.
- Existing global builders and bundles behave exactly as before when no boundary is installed.

## Validation and issue codes

- `boundary-invalid-name` and `boundary-duplicate-name`;
- `boundary-use-cycle`, including the complete cycle path;
- `boundary-use-source-not-found`;
- `boundary-use-not-found` and `boundary-use-ambiguous`;
- `boundary-expose-not-found` and `boundary-expose-ambiguous`;
- `boundary-private-component` when a matching registration exists but is not visible;
- `boundary-reexport-unsupported` when `Expose` selects a used component;
- `boundary-entrypoint-not-local` when a local marker selects a component admitted by `Use`;
- `boundary-entrypoint-not-exposed` when a locally marked component is not exposed;
- `boundary-scope-slot-unsupported` for a private scope-slot declaration;
- `boundary-cross-boundary-decoration` for an attempted implicit decorator or pre-configuration;
- `overlay-boundary-reopened` and `overlay-boundary-private-component`.

When a missing dependency has a matching private registration elsewhere, diagnostics identify its boundary and suggest
adding `Expose` and `Use`. They do not reveal configured values, build inputs, runtime identities, or unrelated private
registrations.

## Failure modes and compatibility

- Invalid declarations fail `build()` with structured issues; bundle code errors still surface when
  `install_boundary()` applies `root_bundle`.
- A use that becomes ambiguous after a new exposure fails compilation rather than silently changing selection.
- Removing an exposure fails every dependent use, affected root resolution, and local entry-point marker in the same
  build.
- A visibility failure never falls back to all root or boundary registrations.
- Manifest comparisons use the current boundary metadata without version checks or legacy ownership inference.

Applications that never call `install_boundary()` retain their current registry, selection, runtime, and manifest
behavior. Existing bundles remain global when passed to `apply_bundle()` and become private only when explicitly passed
as a boundary's `root_bundle`. No bundle is isolated implicitly.

`Container.resolve()` and `Scope.resolve()` are unchanged. Unaliased components retain their existing selection
behavior; external occurrences of an aliased exposure report and select by its public type, name, and tags.
Manifests remain unversioned during beta. Regenerate saved graphs and baselines when their format changes. No legacy
visibility fields are translated, and schema versioning will begin after beta.

## Privacy and redaction

Boundary names, exposed service identities, uses, names, tags, lifespans, and compiled boundary paths are architecture
metadata and may appear in manifests. This matches the metadata already needed for graph review and selection.

Source paths, bundle callables, filter object identities, build-argument names and values, configured values, secrets
such as `AppSettings`, runtime instances, cache keys, finalizers, and owner tokens remain excluded. Boundaries segregate
dependency selection; they do not conceal qualified type names from developers who possess the compiled graph.

## Rejected alternatives

- **Call the feature modules or packages:** both terms already have precise Python meanings and imply source-layout or
  import behavior that this feature does not provide.
- **Copy aliases into separate public registrations:** that changes activation identity and ownership. Boundary aliases
  are selection views over the same source registration.
- **Make every bundle isolated:** this silently changes existing applications and third-party composition.
- **Use tags as boundaries:** tags guide filters but do not remove candidates from visibility.
- **Allow implicit root fallback:** boundaries fail open whenever a local dependency is missing.
- **Allow implicit use of every exposure:** the root contract would be explicit, but dependencies between boundaries
  would remain hidden.
- **Allow boundary-use cycles when constructors are acyclic:** the architecture would change silently as implementations
  evolve, and layering would be difficult to reason about.
- **Represent exposures as proxy or alias components:** this changes identity, graph shape, performance, and cleanup
  ownership for a visibility-only operation.

## Incremental rollout

1. Add immutable `Boundary`, `BoundaryAlias`, `Expose`, and `Use` declarations; private boundary builders; local-only compilation; root
   exposure; and unchanged identity semantics.
2. Add cross-boundary and root uses, cycle detection, private-component diagnostics, and installation-order independence.
3. Integrate contextual filters, discovery, decorators, pre-configurations, generics, typed providers, and complete
   ownership proof across boundaries.
4. Add scope overlays, boundary-scoped validation contexts, graph rendering, provenance explanations, unversioned manifests,
   semantic diff categories, and policy helpers.
5. Promote the feature from experimental only after all public operations have sync/async parity and the complete
   existing non-boundary test suite remains unchanged.

Each stage should be delivered as a thin vertical slice with public API, compiler model, diagnostics, documentation,
and tests agreeing. An experimental import path may be used before the manifest and overlay contracts are complete;
the top-level re-exports are the compatibility commitment.

## Acceptance tests

- Apply a function bundle, `BaseBundle`, nested bundle, and run-once bundle as `root_bundle` without changing their
  registration behavior.
- Resolve local dependencies, root uses, cross-boundary uses, unnamed exposures, named exposures, and tag-selected
  exposures.
- Prove that component IDs, instances, lifespans, caches, and cleanup owners are unchanged across exposure and use
  boundaries, while an explicit alias type, name, and tags are visible only outside the defining boundary.
- Reject direct access to private root and boundary registrations with actionable issue paths.
- Reject missing and ambiguous uses and exposures, attempted re-exports, unsupported local scope slots, duplicate names,
  invalid names, and every length of boundary-use cycle.
- Prove installation order does not affect use binding while declaration order still controls deterministic collection
  order where existing semantics require it.
- Cover constructors, sync and async factories, generators, context managers, collections, generics, discovery,
  decorators, pre-configurations, typed providers, and validation rules inside boundaries.
- Prove external decorators and pre-configurations cannot mutate an imported or exposed component implicitly.
- Mark exposed local and root-visible boundary entry points, reject private or imported local markers, and prove marking
  never grants visibility or propagates through `Use`.
- Preserve visibility through ordinary scopes and reject every parent-boundary reopening or private patch attempt from an
  overlay.
- Preserve parent and overlay singleton anchoring, scoped reuse, once-per-graph caching, and cleanup routing across
  boundaries.
- Render deterministic boundary labels and boundary edges in text, Mermaid, explanations, ownership reports, and JSON.
- Round-trip unversioned manifests and classify boundary contract changes without exposing
  provenance or runtime values.
- Prove manifests and fingerprints contain no bundle/filter identities, source paths, build inputs, configured values,
  runtime objects, owner tokens, or finalizers.
- Run the complete existing builder, bundle, compiler, ownership, provider, scope, and FastAPI suites unchanged when no
  boundary is installed.
