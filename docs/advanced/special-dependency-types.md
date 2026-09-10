# Special dependency types

Clean IoC 2 keeps the runtime special surface small: `Provider`, `AsyncProvider`, `ResolutionContext`, `Scope`, and
`Container`.

`ParameterContext` is related but is not a runtime dependency. Clean IoC passes it only to an explicit `derive(...)`
policy during `build()`. See [argument policies](arguments.md).

## Typed providers

Use `Provider[T]` when a known dependency should be created later rather than while its consumer is constructed:

```python
from clean_ioc import Provider


class BatchRunner:
    def __init__(self, units: Provider[UnitOfWork]):
        self.units = units

    def run(self, items):
        for item in items:
            self.units().process(item)
```

The compiler unwraps `T`, applies any `select(...)` policy once, validates the complete target graph, and stores a direct
reference to its frozen activation step. A provider call starts a fresh top-level resolution in the scope where the
handle was obtained. Transients are therefore new per call, `per_resolution` values are shared only inside one call,
and scoped and singleton targets retain their normal caches.

Use `AsyncProvider[T]` for a target that requires async resolution:

```python
from clean_ioc import AsyncProvider


class Worker:
    def __init__(self, repositories: AsyncProvider[Repository]):
        self.repositories = repositories

    async def run(self):
        repository = await self.repositories()
```

Providers take no arguments. Their targets may be a closed service type or `list[T]`, `tuple[T, ...]`, or `set[T]`.
They can also be resolved as roots, such as `scope.resolve(Provider[Report])`. A handle never performs registration or
candidate discovery, and calling it after its bound scope closes raises `ProviderScopeClosedError`.

For a named target, apply `select(...)` to the provider argument; the filter sees the target component rather than the
synthetic handle:

```python
import clean_ioc.component_filters as cf
from clean_ioc import select


builder.register(
    ClientSelector,
    arguments={"client": select(cf.with_name("primary"))},
)
```

A singleton may retain a provider only when its deferred target contains no scoped component, scope slot, `Scope`, or
`ResolutionContext` edge. This rule keeps a provider from disguising captured request state.

## Lazy provider maps

Declare a read-only `Mapping[K, Provider[T]]` when consumers select one named implementation on demand:

```python
from collections.abc import Mapping
from clean_ioc import ContainerBuilder, Provider


class PaymentGateway:
    pass


class StripeGateway(PaymentGateway):
    pass


class PayPalGateway(PaymentGateway):
    pass


class Checkout:
    def __init__(self, gateways: Mapping[str, Provider[PaymentGateway]]):
        self.gateways = gateways


builder = ContainerBuilder()
builder.register(PaymentGateway, StripeGateway, name="stripe", lifespan="scoped")
builder.register(PaymentGateway, PayPalGateway, name="paypal", lifespan="scoped")
builder.register_provider_map(PaymentGateway, key=lambda component: component.name)
builder.register(Checkout)

with builder.build() as container:
    with container.new_scope() as scope:
        checkout = scope.resolve(Checkout)  # No gateway is activated.
        gateway = checkout.gateways["stripe"]()  # Only StripeGateway is activated.
```

The operation is available on `ContainerBuilder`, `ScopeBuilder`, and the `ComponentBuilder` bundle protocol:

```text
register_provider_map(
    service_type,
    *,
    key,                       # Callable[[Component], Hashable], required
    key_type=str,              # Explicit type used as K in the injection annotation
    asynchronous=False,       # True declares Mapping[K, AsyncProvider[T]]
    component_filter=all_components,
    name=None,                 # Name of this map registration
) -> str                       # Registration ID
```

Supply `key_type` for non-string keys, including empty maps. The callback's return annotation is never inferred.
For example, `key=lambda component: component.implementation_type, key_type=type` declares
`Mapping[type, Provider[PaymentGateway]]`. Keys must conform to the declared key type and retain stable equality and
hash behavior. As with registered service values, runtime type checking is not added. Both `collections.abc.Mapping`
and `typing.Mapping` annotations work, including aliases nested around the map, key, provider, or target. NewType
targets and keys retain their nominal type identity.

For async targets, declare `asynchronous=True`, inject `Mapping[str, AsyncProvider[PaymentGateway]]`, and call
`await gateways["stripe"]()`. Acquiring either kind of map is synchronous; `resolve_async()` is also supported.
Every selected target graph is validated during build, so a sync map containing an async target fails immediately.

The target filter includes all visible eligible registrations by default, including named registrations. Use
`component_filter=cf.with_name("stripe")` to narrow entries. Entry iteration follows the existing candidate order:
newest registrations first within a layer, with overlay candidates before inherited ones. Keys are never sorted.
An empty target set yields an empty map; an absent runtime key raises normal `KeyError`.

Each declaration is an ordinary selectable transient map registration. Multiple declarations do not merge; name them
and use normal root filters or `arguments={"gateways": select(cf.with_name("international"))}` to select a map.
Those filters select map definitions, while `component_filter` selects their target entries. Ordinary `dict` injection
and eager mapping factories keep their existing behavior.

Map declarations require closed key and target types. They cannot be patched to a cached lifespan or given argument
overrides; invalid declarations report `provider-map-invalid-declaration`. Cache the consumer when appropriate: its
map handles still bind according to the consumer's validated ownership.

The required `key` callable receives compiled target `Component` metadata and runs synchronously during compilation,
once per selected occurrence within that map compilation. It must be pure: previews, diagnostic recompilation after
failure, retries, and fresh builds may evaluate it again. It never receives an activated service. Runtime acquisition,
iteration, and provider invocation do not rerun the callback or component filters. Acquisition shares the frozen
key-to-entry index and creates scope-bound provider handles without activating targets or rehashing keys.

Duplicate keys use Python dictionary equality semantics. Invalid or async callbacks/results, unhashable keys, and
callback/hash/equality failures produce structured build errors with `provider-map-invalid-key`,
`provider-map-unhashable-key`, `provider-map-duplicate-key`, or `provider-map-key-evaluation`. Errors omit computed
keys and callback exception text. Failed builds remain repairable.

Each provider call starts a fresh resolution and preserves the target's normal lifespan, decorators, and cleanup owner.
Singleton capture has the same restrictions and owner binding as an individual provider. Escaped handles fail with
`ProviderScopeClosedError` after their bound owner closes. Ordinary child scopes reuse the frozen topology; overlays
compile their visible targets while inherited singleton consumers retain their original maps. Boundary-local maps
select only targets visible within their declaring boundary, even when the map itself is exposed.

Graph tooling represents a `provider_map` node with one `provider` child per entry and each child's direct target.
Manifests include this node kind plus `key_type` and `provider_mode` metadata. The format is unversioned during beta.
Computed keys and hashes are not added to manifests, explanations, or fingerprints. Ordinary component names and tags
retain their existing graph representation, including when a callback also uses them as keys. Changing only redacted
computed key values cannot be detected by the default fingerprint. Programs without maps keep their existing graph output.

## `ResolutionContext`

`ResolutionContext` resolves an already-compiled root inside the active top-level resolve. It preserves `per_resolution` identity.

Prefer constructor injection. When the target type is known, prefer a typed provider. Use `ResolutionContext` or helpers
such as `use_component(...)` only when the dependency type itself must be selected dynamically.

```python
from clean_ioc import ResolutionContext


class SenderSelector:
    def __init__(self, context: ResolutionContext):
        self.context = context

    def select(self, premium: bool) -> Sender:
        name = "premium" if premium else "standard"
        return self.context.resolve(Sender, filter=cf.with_name(name))
```

ResolutionContext can only select frozen root plans. It cannot register, patch, decorate, provide slots, or compile.

## `Scope`

Injecting `Scope` returns the current runtime scope. This is useful at framework boundaries that must create a nested cache boundary. Application services should normally depend on their actual collaborators.

## `Container`

Injecting `Container` returns the immutable root container, even while resolving inside a child scope. It has resolution and scope-creation APIs but no composition APIs.
