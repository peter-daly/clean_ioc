# Advanced Clean IoC 2 patterns

## Factories and cleanup

Type-annotate factory parameters; they become compiled component edges. Sync/async functions, generators, and context-manager-shaped callables are supported. Factory code remains dormant during `build()`.

Cleanup follows the cache owner:

- scoped finalizer → owning scope;
- root singleton finalizer → container;
- `ScopeBuilder` singleton finalizer → built overlay scope.

Use `scoped_teardown=` for scoped or singleton components when cleanup is separate from construction.

## Dependency settings and runtime providers

Inline fixed values directly:

```python
builder.register(Client, dependency_config={"timeout": 5.0})
```

Use `DependencySettings` for a component filter, component-list modifier, or value provider. Providers run at activation with a static `DependencyContext`; returning `EMPTY` executes the fallback edge compiled during build.

Prefer declared slots for request/framework values shared across components.

## Decorators

```python
builder.register(Handler, ConcreteHandler)
builder.register_decorator(Handler, LoggingHandler, decorated_arg="child")
```

Lower `position` values are nearest the core. `when=` predicates are evaluated against the completed undecorated core subtree, before decorator dependencies are added. This prevents one decorator from making another decorator eligible.

## Generic discovery

Import candidate modules before calling `register_generic_subclasses(OpenGeneric)`. Narrow discovery with `subclass_type_filter` from `clean_ioc.type_filters`. Use `fallback_type=` for unmatched closed requests.

Register generic decorators after subclass discovery. Generated concrete decorator types are memoized process-wide.

The compiler creates occurrence-specific component plans, so the same stable component ID may have different parents and generic mappings under different roots.

## Bundles and component patches

Bundles accept the shared `ComponentBuilder` protocol and are composition-only. Apply them to `ContainerBuilder` or `ScopeBuilder`, never a runtime.

Retain the ID returned by `register(...)` when a reusable bundle needs a pre-build customization:

```python
component_id = builder.register(Client)
builder.patch_component(Client, component_id, lifespan=Lifespan.singleton)
```

Use `RemoveDependencySetting` to remove an inherited dependency override. Patches are unavailable after successful build.

## Pre-configuration

`pre_configure(Service, function, when=...)` compiles the function's dependencies and runs the function once before an applicable component's first activation. Use `continue_on_failure=True` only when optional failure is deliberate.

## Dynamic selection inside activation

Inject `ResolutionContext` only when a component must select among already-compiled roots at runtime. It preserves `once_per_graph` identity and cannot mutate or compile composition.

Factory helpers such as `use_registered(...)` use the active compiled resolution context internally.

Avoid broad service-locator usage. Prefer explicit constructor dependencies and component filters when selection is static.
