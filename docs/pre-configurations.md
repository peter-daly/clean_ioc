# Pre-configurations

A pre-configuration is a lazy, container-owned initializer. `build()` compiles its dependencies, validates them as a singleton path, and adds the initializer to the static component graph. The function itself does not run until the first applicable component is activated.

```python
import logging

from clean_ioc import ContainerBuilder


def configure_logging(logger: logging.Logger):
    logger.setLevel(logging.INFO)


builder = ContainerBuilder()
builder.register(logging.Logger, factory=logging.getLogger, lifespan="singleton")
builder.register(Client)
configuration_id = builder.pre_configure(Client, configure_logging)
container = builder.build()
```

`pre_configure()` returns a stable definition ID. That ID also appears on the initializer's `Component` in graph and manifest tooling.

Use `dependency_config` for argument-level selection or values. Use the single `when=` component filter to select static occurrences:

```python
import clean_ioc.component_filters as cf

builder.pre_configure(
    Client,
    configure_client,
    when=cf.has_tag("environment", "production"),
)
```

The filter runs during `build()` against each matching component. It cannot inspect runtime instances.

## Shared initializers and ordering

Pass several service types to share one initializer:

```python
builder.pre_configure((ApiClient, EventPublisher), configure_observability)
```

This creates one compiled initializer, not one copy per service type. The first matching activation triggers it; later activations reuse its completed state across root resolutions, ordinary scopes, and scope overlays. Concurrent sync or async triggers wait for the same in-flight attempt.

Applicable initializers run in declaration order. In an overlay, inherited parent initializers run before initializers declared on the `ScopeBuilder`. A closed generic target such as `Repository[Order]` matches that exact specialization, while an open generic target applies to its compiled specializations.

## Lifespans and cleanup

An initializer is effectively singleton even when the component that triggers it is transient. Its complete dependency path is therefore validated as singleton-owned:

```text
pre-configuration -> scoped          invalid
pre-configuration -> once_per_graph  invalid
pre-configuration -> transient       valid when its descendants are valid
pre-configuration -> singleton       valid
```

This validation is transitive, so a transient dependency cannot hide scoped or `once_per_graph` state. An inherited initializer keeps its frozen parent dependency plan; an overlay cannot rewire it by overriding one of those dependencies.

A parent definition that had no applicable component, and therefore no compiled parent plan, cannot become newly applicable to an overlay registration. Declare that initializer on the `ScopeBuilder` instead.

Generator and context-manager initializers are cleaned up by the layer that declared them. For example, a root initializer first triggered from an overlay remains alive until the root container closes.

## Failure behavior

The default propagates an initializer failure to every caller waiting for that attempt. Its state remains incomplete, so a later resolution can retry.

`continue_on_failure=True` is for deliberately optional setup. An exception raised by the configuration function is logged, activation continues, and the initializer is considered complete; it is not retried on every resolution. Dependency-resolution failures still propagate because the configuration function never ran.
