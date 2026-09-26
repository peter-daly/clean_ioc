# Bundles

A bundle groups registrations; a boundary controls access to them. A bundle packages repeatable composition against
the shared `ComponentBuilder` protocol. The same bundle can target a root `ContainerBuilder` or an experimental
`ScopeBuilder`, or a retained `BoundaryBuilder`.

```python
from clean_ioc import ComponentBuilder, ContainerBuilder
from clean_ioc.bundles import BaseBundle


class ClientBundle(BaseBundle):
    def apply(self, builder: ComponentBuilder):
        builder.register(ClientConfig, instance=ClientConfig())
        builder.register(ApiClient)


builder = ContainerBuilder()
builder.apply_bundle(ClientBundle())
container = builder.build()
```

A bundle may also register a [decorator template](decorator-templates.md) and share one `ServiceGroup` declaration with contributing registrations. Same-named group objects have different identities.

Bundles are composition-only. They are never injectable at runtime and cannot mutate a built container or scope.
An existing bundle can also be applied unchanged to a retained boundary handle; see
[Boundaries and visibility](boundaries.md). Every bundle applied to that handle contributes to the same private
composition until its parent builds. Nested bundle applications retain their provenance path.

```python
from clean_ioc import Expose

builder = ContainerBuilder()
client = builder.create_boundary("client", exposes=(Expose(ApiClient),))
client.apply_bundle(ClientBundle())
container = builder.build()
container.resolve(ApiClient)  # exposed; ClientConfig remains private
```

Boundary-owning bundles can call `builder.create_boundary(...)` through `ComponentBuilder` and expose the returned
handle for application extensions. The boundary handle supports ordinary registration and bundle operations but
cannot create nested boundaries or build independently.

The shared protocol also supports custom validation rules, so a bundle can install organization or framework policy
along with its registrations:

```python
class ArchitecturePolicyBundle(BaseBundle):
    def apply(self, builder: ComponentBuilder):
        builder.add_validation_rule(enforce_architecture)
        builder.add_validation_rule(inspect_all_source, mode="validation")
```

Rules installed on a root builder are inherited by scope overlays and validate each overlay's complete compiled graph.
The `mode="validation"` form lets a bundle install an expensive CI policy without adding it to application startup.
See [Custom graph validation](custom-validation.md#package-rules-in-bundles) for a complete policy-bundle example.

## Run-once policies

Use `OnlyRunOncePerInstanceBundle` when one bundle object may be applied repeatedly but should compose each builder once:

```python
from clean_ioc.bundles import OnlyRunOncePerInstanceBundle


class InfrastructureBundle(OnlyRunOncePerInstanceBundle):
    def apply(self, builder: ComponentBuilder):
        builder.register(Database)
        builder.register(Repository)
```

Use `OnlyRunOncePerClassBundle` when every instance of the bundle class shares one identifier. Extend `RunOnceBundle` and implement `get_bundle_identifier()` for a custom policy.

The identifier answers **which bundle** is unique. Set `run_once_per` on a subclass to choose **where** it is unique:

```python
class SharedInfrastructure(OnlyRunOncePerClassBundle):
    run_once_per = "container"

    def apply(self, builder: ComponentBuilder):
        builder.register(Database)
```

| `run_once_per` | One application per identifier in... |
| --- | --- |
| `"boundary"` (default) | Each root or scope builder, or each isolated boundary. This preserves the earlier per-builder behavior. |
| `"scope"` | A root composition or one scope overlay, including all boundaries installed there. |
| `"container"` | A root container composition and all its scope overlays and boundaries. |

The choice applies to `RunOnceBundle`, `OnlyRunOncePerInstanceBundle`, and `OnlyRunOncePerClassBundle`. A scope overlay gets a fresh `"scope"` identity; nested runtime scopes without an overlay do not apply bundles. The same bundle can still run in a separate container. These are composition identities, not component lifespans or runtime caches.
Use `"boundary"` when each isolated boundary needs its own registrations: a wider policy skips the bundle in later boundaries covered by the same scope or container.
Custom `ComponentBuilder` implementations can support the wider choices by implementing `bundle_run_key(per: BundleRunScope) -> str`.

## Bundle-owned component IDs

`register(...)` returns a component ID. A bundle may retain it for a later pre-build patch:

```python
class ServiceBundle(BaseBundle):
    component_id: str

    def apply(self, builder: ComponentBuilder):
        self.component_id = builder.register(Service)


bundle = ServiceBundle()
builder = ContainerBuilder()
builder.apply_bundle(bundle)
builder.patch_component(Service, bundle.component_id, lifespan="singleton")
container = builder.build()
```
