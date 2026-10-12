---
name: use-clean-ioc
description: Use Clean IoC 2 to compose and compile typed Python dependency plans with ContainerBuilder, immutable Container and Scope runtimes, lifespans, scope slots, ScopeBuilder overlays, component filters, decorators, generics, factories, and cleanup. Use whenever code imports clean_ioc or needs Clean IoC dependency-injection architecture; use the FastAPI skill for clean_ioc.ext.fastapi details.
---

# Use Clean IoC

For a Clean IoC 1.x application upgrade, use the migrate-clean-ioc Library Skill first.

Separate mutable composition from immutable runtime execution:

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(Repository, SqlRepository)
builder.register(Service)

container = builder.build()
service = container.resolve(Service)
```

Treat the installed package as the source of truth. Inspect public signatures when the task depends on an unfamiliar API.

## Respect the build boundary

Perform registration, decoration, pre-configuration, slot declaration, bundle application, component queries, and patches on a builder. Call `build()` only after composition is complete.

`build()` emits only the execution plan. It runs no validation rules or safety-policy audits. Missing dependencies or cycles can still prevent instruction emission. Constructors and activation factories remain lazy; selection, derivation and template callbacks run during compilation.

Use a fresh composition factory's `verify()` for complete diagnostics, architectural checks and every custom rule. It returns a `VerificationReport` with a immutable findings, a full or partial inspection graph, and an optional executable test plan. Use `result.create_runtime()` to test that plan without recompilation. Reading the report or creating test runtimes does not replay callbacks.

Every admitted build or verification attempt consumes its builder, including failed or interrupted attempts. Repair declarations in a fresh builder. Invalid inputs rejected before admission leave the builder mutable.

Do not attempt to mutate a `Container` or `Scope`.

## Choose the correct child API

- `new_scope()` reuses the frozen plan and creates a cache/cleanup boundary. It never compiles.
- Declare framework/request holes with `builder.declare_scope_slot(Type, name=None)`, then call `scope.provide(Type, value, name=None)` before resolution.
- Use `ScopeBuilder(parent, composition=handle)` when child declarations differ. Request the external handle with `builder.retain_composition()` before building, or use `result.composition` from analysis with a runtime created from that result. A matching live parent is required. The handle retains declaration memory, has no close lifecycle, and is not retained by the runtime. Request a handle for each overlay that must support further composition.

Slots must be declared, cannot be provided twice in one scope, and lock after resolution begins. Nested scopes inherit provisions and can override them before their own first resolve.

Singletons registered by `ScopeBuilder` belong to its built scope and descendants, not the root container.

## Use one component filter vocabulary

Import selection predicates from `clean_ioc.component_filters`:

```python
import clean_ioc.component_filters as cf
```

Use them for:

- `resolve(..., filter=...)` and `select(...)` argument policies;
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
- `per_resolution`: one top-level resolve;
- `scoped`: runtime scope cache;
- `singleton`: root container or owning compiled overlay scope.

Scoped and singleton components must not directly or transitively depend on `per_resolution`; a transient wrapper does not make that capture valid. A singleton must not depend on scoped state. `verify()` reports these invalid paths as `captive-dependency`; `build()` does not audit them.

Use `resolve_async()` whenever an activation path may contain async functions, generators, context managers, or cleanup. Always exit the owning scope/container so cleanup runs.

## Advanced features

Read [references/advanced-patterns.md](references/advanced-patterns.md) when the task uses decorators, generic discovery, bundles, pre-configuration, runtime value providers, `ResolutionContext`, component patching, or non-trivial cleanup.

## Preserve application boundaries

Prefer ordinary constructor/factory injection. Keep builders in composition roots. Do not inject a builder or use runtime resolution as an application-wide service locator.
