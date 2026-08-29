# Advanced Clean IoC 2 patterns

## Factories and cleanup

Type-annotate factory parameters; they become compiled component edges. Sync/async functions, generators, and context-manager-shaped callables are supported. Factory code remains dormant during `build()`.

Closed generic services automatically specialize ordinary TypeVars in factory dependencies. An open service registration is a reusable template for closed types encountered as dependencies during build; register a closed service explicitly when it must be resolved as a root. Use `factory_specialization=SomeClosedGeneric` only when the service and factory result cannot supply every binding. Unresolved or conflicting TypeVars fail the build; ParamSpec and TypeVarTuple are unsupported.

Cleanup follows the cache owner:

- scoped finalizer → owning scope;
- root singleton finalizer → container;
- `ScopeBuilder` singleton finalizer → built overlay scope.

Keep acquisition and release in one generator or context-manager factory. Registration-level cleanup callbacks are not part of V2.

An inherited root singleton remains anchored to its root activation plan and owner inside a `ScopeBuilder` overlay; overlay registrations and decorators do not rewire it. Singletons introduced by the overlay belong to the built scope. A built overlay starts a fresh scoped cache boundary, while ordinary nested scopes retain scoped inheritance.

`once_per_graph` state cannot appear anywhere below a scoped or singleton component, including through transient components, factories, decorators, collections, provider fallbacks, or pre-configurations. Promote that dependency to the owner's lifespan or shorten the owner. Plain transient dependencies remain valid below long-lived components, and shorter-lived components may depend on scoped or singleton components.

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

`register_subclasses(...)`, `register_generic_subclasses(...)`, and `register_generic_decorator(...)` queue discovery rules. Import candidate modules before `build()`; the build takes the live subclass snapshot, materializes matching registrations and decorators, validates them, and freezes the plan. Narrow discovery with `subclass_type_filter` from `clean_ioc.type_filters`. Use `fallback_type=` for unmatched closed requests.

The registration and decorator rules share the same build snapshot, so their declaration order does not control which concrete types are seen. Generated concrete decorator types are memoized process-wide. Use `types.new_class()` for dynamic parameterized generic bases, and retain dynamic class objects until build.

The compiler creates occurrence-specific component plans, so the same stable component ID may have different parents and generic mappings under different roots.

## Entry points and compiler tooling

Call `builder.mark_entrypoint(Service)` for each public resolution request. Mark `list[Service]` when every matching implementation is an entry point. Markers focus `container.graph` renderers and enable `unreachable-component` warnings; every visible root remains compiled, validated, and resolvable.

Use `container.build_report` after success or `ContainerBuildError.report` after failure for structured issues. Independent root errors are aggregated. Use `container.graph.to_text()`, `.to_mermaid()`, or `.manifest()` for the entry-point view and pass `all_roots=True` for the complete root set. Manifests are deterministic and redact configured values. Compare them with `current.diff(baseline)`.

For CI, expose a builder or zero-argument composition factory as `module:object`, then run `clean-ioc check TARGET --strict`, `clean-ioc graph TARGET --format json -o graph.json`, or `clean-ioc diff TARGET graph.json`. Warning codes may be ignored explicitly; errors cannot. Baselines never update implicitly.

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
