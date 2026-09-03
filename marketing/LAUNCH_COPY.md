# Clean IoC 2 alpha launch copy

## Technical community post

### Title

Clean IoC 2: compile a Python dependency graph once, then resolve without rebuilding it

### Body

I maintain a typed dependency-injection container for Python. Its old runtime model treated every resolve as a fresh graph-building exercise, even when the registrations had not changed.

The 2.0 alpha splits that into two explicit jobs:

```python
builder = ContainerBuilder()
builder.register(OrderRepository, SqlOrderRepository, lifespan="scoped")
builder.register(CreateOrder)

container = builder.build()
handler = container.resolve(CreateOrder)
```

`build()` specializes generics, constructs occurrence-specific component trees, evaluates contextual filters and
explicit derived argument policies, checks missing/circular/captive dependencies, and freezes activation instructions.
It does not run constructors, factories, generators, context managers, or teardown callbacks.

The runtime container is immutable. Resolution executes frozen steps, caches plain instances, and does not allocate dependency-graph nodes.

The other experiment is child composition. `new_scope()` remains cheap and reuses its parent's plan. When a tenant or test genuinely needs different registrations, `new_scope_builder().build()` compiles an overlay explicitly. Late request/framework values use declared scope slots and `scope.provide(...)`, so FastAPI does not mutate or recompile the container per request.

Registration metadata and graph nodes have also become one read-only `Component` model. The same `component_filters` predicates now drive root selection, dependency selection, parent-aware registration, decorators, and pre-configuration.

This is a major-version alpha because the build boundary changes the programming model. I would especially value feedback from people with deep FastAPI, CQRS, plugin, or multi-tenant object graphs: which composition patterns cannot be frozen at startup?

Repository: https://github.com/peter-daly/clean_ioc

## Short social post

Clean IoC 2 alpha compiles Python DI plans before startup:

`ContainerBuilder` → `build()` → immutable `Container`

- strict missing/cycle/captive checks
- no user activation during build
- no dependency-graph allocation during resolve
- one static `Component` filter model
- cheap scopes + explicit compiled scope overlays
- declared FastAPI request slots

BenchBro results separate build cost, runtime latency, and allocations. Looking for hard object graphs that break the model.

https://github.com/peter-daly/clean_ioc

## Article outline

### Title

What if a Python DI container stopped building graphs at runtime?

### Sections

1. Why mutable composition and runtime resolution are different jobs.
2. The explicit build boundary and what must remain side-effect free.
3. Occurrence-specific component plans for parent-aware generics.
4. Evaluating decorators against the undecorated core subtree.
5. Runtime providers with static context and a precompiled fallback edge.
6. Cheap child scopes, declared slots, and explicit scope overlays.
7. Measuring startup, runtime, and allocations as separate questions.
8. What remains experimental and which graphs should challenge the design.
