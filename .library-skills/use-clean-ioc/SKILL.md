---
name: use-clean-ioc
description: Use Clean IoC 2 to compose and compile typed Python dependency plans with ContainerBuilder, immutable Container and Scope runtimes, lifespans, scope slots, ScopeBuilder overlays, component filters, decorators, generics, factories, and cleanup. Use whenever code imports clean_ioc or needs Clean IoC dependency-injection architecture; use the FastAPI skill for clean_ioc.ext.fastapi details.
---

# Use Clean IoC

Separate mutable composition from immutable runtime execution:

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(Repository, SqlRepository)
builder.register(Service)

container = builder.build()
service = container.resolve(Service)
```

Treat the installed package as the source of truth. Inspect public signatures when the task depends on an unfamiliar alpha API.

## Respect the build boundary

Perform registration, decoration, pre-configuration, slot declaration, bundle application, component queries, and patches on a builder. Call `build()` only after composition is complete.

`build()` strictly compiles every visible root without invoking constructors, factories, generators, context managers, or parameter value providers. A failed build leaves the builder reusable. A successful build makes it single-use.

Do not attempt to mutate a `Container` or `Scope`.

## Choose the correct child API

- `new_scope()` reuses the frozen plan and creates a cache/cleanup boundary. It never compiles.
- Declare framework/request holes with `builder.declare_scope_slot(Type, name=None)`, then call `scope.provide(Type, value, name=None)` before resolution.
- Use `new_scope_builder()` only when child registrations, decorators, or pre-configurations genuinely differ. `ScopeBuilder.build()` recompiles the visible plan.

Slots must be declared, cannot be provided twice in one scope, and lock after resolution begins. Nested scopes inherit provisions and can override them before their own first resolve.

Singletons registered by `ScopeBuilder` belong to its built scope and descendants, not the root container.

## Use one component filter vocabulary

Import selection predicates from `clean_ioc.component_filters`:

```python
import clean_ioc.component_filters as cf
```

Use them for:

- `resolve(..., filter=...)` and `DependencySettings(filter=...)`;
- `register(..., when=...)` for occurrence eligibility;
- `register_decorator(..., when=...)`;
- `pre_configure(..., when=...)`;
- `has_component`, `get_component_id(s)`, and `patch_component` workflows.

For parent-aware selection, compose `cf.parent(...)`. For dependency-subtree selection, use `cf.has_descendant(...)`. Filters see immutable static `Component` occurrences, never runtime instances, and custom filters run at build rather than resolution.

Run the discovery helper before inventing a component predicate:

```bash
python <path-to-this-skill>/scripts/discover_component_filters.py
python <path-to-this-skill>/scripts/discover_component_filters.py generic --full
```

Keep `clean_ioc.type_filters` separate for Python subclass/generic discovery.

## Lifespans and execution

- `transient`: every dependency edge;
- `once_per_graph`: one top-level resolve;
- `scoped`: runtime scope cache;
- `singleton`: root container or owning compiled overlay scope.

Scoped and singleton components must not directly or transitively depend on `once_per_graph`; a transient wrapper does not make that capture valid. A singleton must not depend on scoped state. These invalid paths fail `build()` with `captive-dependency`.

Use `resolve_async()` whenever an activation path may contain async functions, generators, context managers, or cleanup. Always exit the owning scope/container so cleanup runs.

## Advanced features

Read [references/advanced-patterns.md](references/advanced-patterns.md) when the task uses decorators, generic discovery, bundles, pre-configuration, runtime value providers, `ResolutionContext`, component patching, or non-trivial cleanup.

## Preserve application boundaries

Prefer ordinary constructor/factory injection. Keep builders in composition roots. Do not inject a builder or use runtime resolution as an application-wide service locator.
