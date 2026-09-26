# Argument policies

Constructor, factory, decorator, and pre-configuration arguments use the same `arguments=` API. Each entry has one
clear meaning:

| Entry | Compiled result |
| --- | --- |
| no entry | The Python default, or an unnamed component when there is no default |
| a plain value | That exact value |
| `select(filter)` | A component selected by the filter, even when the parameter has a Python default |
| `inject()` | The ordinary unnamed component, even when the parameter has a Python default |
| `derive(function)` | A value computed from static component metadata during `build()` |
| `build_arg(name)` | One named build input, compiled as a frozen value |
| `generic_arg(key)` | One generic binding from the owning component, compiled as a frozen value |

## Build arguments

Pass user-defined composition inputs at the compilation boundary when a graph decision varies by environment, mode,
feature set, or another application-owned value:

```python
import clean_ioc.component_filters as cf
from clean_ioc import ContainerBuilder, ParameterContext, derive


def timeout(context: ParameterContext) -> int:
    return 30 if context.build_args["environment"] == "production" else 5


builder = ContainerBuilder()
builder.register(
    Client,
    arguments={"timeout": derive(timeout)},
)
builder.register(
    Publisher,
    LivePublisher,
    when=cf.build_arg_is("mode", "live"),
)

container = builder.build(
    build_args={
        "environment": "production",
        "mode": "live",
    },
)
```

`build_args` is available through `ParameterContext.build_args`, every compiled `Component`, `Container`/`Scope`, and
`CompiledGraph`. Clean IoC validates string keys, shallow-copies the supplied mapping, and exposes the copy as an
immutable mapping. Values are not deep-copied, so callbacks should treat contained objects as user-owned and read-only.

Build arguments are composition inputs, not automatically injected configuration services. They can control
`derive(...)`, custom or built-in component filters, decorators, pre-configurations, entry points, and other build-time
graph choices. The resulting decisions and derived values are frozen into the plan; the mapping is not consulted during
resolution. Callbacks remain synchronous and should be pure.

Project one input explicitly into a constructor or factory with `build_arg(name)`:

```python
from clean_ioc import build_arg


def create_client(environment: str) -> Client:
    return Client(environment)


builder.register(
    Client,
    factory=create_client,
    arguments={"environment": build_arg("environment")},
)
```

The lookup happens during compilation and produces an ordinary frozen value node. It does not rerun when the factory
activates. A missing key follows normal mapping behavior and becomes an `invalid-derived-argument` build error. Supply
an explicit fallback when absence is valid:

```python
arguments={"timeout": build_arg("timeout", default=30)}
```

The fallback may be any value, including `None`. Use `derive(...)` instead when the injected value needs a
transformation or other component metadata.

Use `cf.has_build_arg("name")` to test presence and `cf.build_arg_is("name", value)` to test equality. Both return false
for a missing key. Direct indexing follows normal mapping behavior and raises `KeyError`; when this happens in a build
callback it is reported as the surrounding build error.

Builder preview queries accept the same `build_args=` keyword. A `ScopeBuilder` inherits its parent's values and
shallowly overlays supplied keys. There is no removal sentinel: create a new root build when a key must be absent.
Ordinary `new_scope()` scopes reuse the parent mapping unchanged. Parent singleton and pre-configuration plans anchored
into an overlay keep the build arguments under which they were originally compiled.

Build reports, graph manifests, fingerprints, text output, and Mermaid output intentionally omit build-argument names
and values. Wiring changes caused by those inputs remain visible in the resulting graph.

## Fixed values

Plain values are compiled directly into the plan. Callable values are still values; Clean IoC does not invoke them.

```python
builder.register(
    Client,
    arguments={
        "endpoint": "https://api.example",
        "timeout": 5.0,
    },
)
```

## Component selection

Use `select(...)` when one argument needs a named, tagged, or otherwise filtered component:

```python
import clean_ioc.component_filters as cf
from clean_ioc import select


builder.register(str, instance="https://api.example", name="api")
builder.register(
    Client,
    arguments={"endpoint": select(cf.with_name("api"))},
)
```

Selection is a normal dependency edge. Missing components, circular paths, async requirements, and captive lifespans
are therefore checked during `build()`. For a collection parameter, the filter is applied to every candidate while
preserving the container's normal candidate order.

Use `inject()` when a parameter has a Python default but composition should force ordinary unnamed injection:

```python
from clean_ioc import inject


builder.register(
    Service,
    arguments={"logger": inject()},
)
```

This compiles the same component or scope-slot edge that a required unconfigured parameter would receive. Use
`select(filter)` instead when the dependency must be named, tagged, or otherwise filtered.

## Generic bindings

Use `generic_arg(...)` to project a binding from the owning component's specialized `generic_mapping`:

```python
from typing import Generic, TypeVar

from clean_ioc import generic_arg


TModel = TypeVar("TModel")


class Serializer(Generic[TModel]):
    def __init__(self, model_type: type):
        self.model_type = model_type


builder.register(
    Serializer[Order],
    arguments={"model_type": generic_arg(TModel)},
)
```

Pass the `TypeVar` when it is available in code. A string such as `generic_arg("TModel")` is also accepted for
reflection-driven composition. The lookup occurs during compilation and missing bindings are build errors.

## Derived build-time values

Use `derive(...)` for a pure composition rule that depends on where a component appears in the compiled graph:

```python
from clean_ioc import ParameterContext, derive


def isolation_level(context: ParameterContext):
    parent = context.component.parent
    if parent is None:
        return context.default

    message_type = parent.generic_mapping["TMessage"]
    return getattr(message_type, "isolation_level", context.default)


builder.register(
    TransactionManager,
    arguments={"isolation_level": derive(isolation_level)},
)
```

The function runs synchronously during `build()`, once for each compiled occurrence that needs the argument. It
receives immutable `ParameterContext` metadata:

- `name` and the specialized `annotation`;
- `has_default` and `default`;
- the owning `component` identity and metadata, including its static parent, tags, and generic mapping.

Returning a concrete value compiles a value node. Return `INJECT` to compile the normal unnamed component or declared
scope-slot edge instead:

```python
from clean_ioc import INJECT, derive


builder.register(
    Service,
    arguments={"dependency": derive(lambda context: INJECT)},
)
```

Derived functions must be synchronous. An exception is reported as an `invalid-derived-argument` build error. Builder
preview queries also compile a temporary plan, so they may evaluate a derived policy before the final `build()` call.
Keep policies pure and do not activate services or open resources: use an ordinary registered factory for runtime work,
or a declared scope slot for request, task, or framework boundary values.

## Patching

Use `REMOVE` with `patch_component(...)` or `patch_decorator(...)` to remove an existing argument override and restore
normal default/injection behavior:

```python
from clean_ioc import REMOVE


builder.patch_component(
    Service,
    component_id,
    arguments={"timeout": REMOVE},
)
```

Unknown argument names fail during build unless the target callable accepts `**kwargs`.
