# The build boundary

`ContainerBuilder.build()` is the validation and compilation boundary. It first materializes queued subclass and generic discovery rules from the currently live Python classes. It then walks every visible root, specializes generic dependencies, constructs occurrence-specific component trees, evaluates filters, and freezes runtime instructions.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(Repository, SqlRepository)
builder.register(CreateOrder)

container = builder.build()
```

No user constructor, factory, generator, context manager, or parameter value provider runs during this work.

A successful build therefore establishes the runtime invariant: the `Container` contains one complete, immutable, structurally valid component plan. Later Python subclasses do not join or invalidate that plan.

## Strict failures

Build fails when a visible plan contains:

- a missing component or scope-slot declaration;
- a circular component path;
- a singleton that captures a scoped component;
- a singleton or scoped component that directly or transitively captures `once_per_graph` state;
- an invalid decorator or pre-configuration dependency.

```python
from clean_ioc import ContainerBuildError

try:
    container = builder.build()
except ContainerBuildError as error:
    print(error.report.to_text())
```

The compiler aggregates failures from independent roots into a structured `BuildReport`. Each issue has a stable code, severity, message, and semantic path. A failed builder remains reusable after the complete report is produced.

A successful runtime exposes the same report as `container.build_report`. Mark public resolution requests with `builder.mark_entrypoint(...)` to add reachability warnings and focus graph renderers without weakening whole-container validation. See [Compiler tooling](compiler-tooling.md) for graph manifests, semantic diffs, and CI commands.

## Builder state after build

A failed build leaves the builder reusable:

```python
try:
    builder.build()
except ContainerBuildError:
    builder.register(MissingDependency)

container = builder.build()
```

After a successful build, the builder rejects registration, decoration, pre-configuration, patching, slot declaration, bundle application, and a second `build()` call. The resulting `Container` has no mutation APIs.

## Inspecting the static plan

Runtime containers expose their compiled root components:

```python
for component in container.components:
    print(component.service_type, component.implementation_type, component.lifespan)

    for dependency in component.dependencies:
        print("  ", dependency.argument, dependency.service_type)
```

`Component` objects are immutable views of static occurrences. A stable component ID identifies its registration; `occurrence_id` distinguishes the same registration under different parents.

`container.graph` adds a complete, read-only view that also models configured/default values, runtime contexts, value providers, declared slots, decorators, and pre-configurations. It can render text or Mermaid and produce deterministic, redacted JSON manifests.

## Child composition

`new_scope()` never validates or compiles because it reuses its parent's frozen plan. `new_scope_builder().build()` is a separate strict build boundary for a child overlay. It runs only discovery rules declared on that `ScopeBuilder`; inherited root rules are already frozen and are never rescanned.
