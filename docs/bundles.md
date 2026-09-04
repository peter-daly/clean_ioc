# Bundles

A bundle packages repeatable composition against the shared `ComponentBuilder` protocol. The same bundle can target a root `ContainerBuilder` or an experimental `ScopeBuilder`.

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

Bundles are composition-only. They are never injectable at runtime and cannot mutate a built container or scope.

The shared protocol also supports custom validation rules, so a bundle can install organization or framework policy
along with its registrations:

```python
class ArchitecturePolicyBundle(BaseBundle):
    def apply(self, builder: ComponentBuilder):
        builder.add_validation_rule(enforce_architecture)
```

Rules installed on a root builder are inherited by scope overlays and validate each overlay's complete compiled graph.

## Run-once policies

Use `OnlyRunOncePerInstanceBundle` when one bundle object may be applied repeatedly but should compose each builder once:

```python
from clean_ioc.bundles import OnlyRunOncePerInstanceBundle


class InfrastructureBundle(OnlyRunOncePerInstanceBundle):
    def apply(self, builder: ComponentBuilder):
        builder.register(Database)
        builder.register(Repository)
```

Use `OnlyRunOncePerClassBundle` when every instance of the bundle class shares one identifier per builder. Extend `RunOnceBundle` and implement `get_bundle_identifier()` for a custom policy.

Run history is keyed by the builder's ID, not by a runtime container.

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
