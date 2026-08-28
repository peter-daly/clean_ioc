# The build boundary

`ContainerBuilder.build()` is the validation and compilation boundary. It walks every visible root, specializes generic dependencies, constructs occurrence-specific component trees, evaluates filters, and freezes runtime instructions.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(Repository, SqlRepository)
builder.register(CreateOrder)

container = builder.build()
```

No user constructor, factory, generator, teardown callback, or parameter value provider runs during this work.

## Strict failures

Build fails when a visible plan contains:

- a missing component or scope-slot declaration;
- a circular component path;
- a singleton that captures a scoped component;
- an invalid decorator or pre-configuration dependency.

```python
from clean_ioc import ContainerBuildError

try:
    container = builder.build()
except ContainerBuildError as error:
    print(error)
```

The alpha currently reports the first strict compilation failure. Aggregated diagnostics are a planned refinement of the compiled model.

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

## Child composition

`new_scope()` never validates or compiles because it reuses its parent's frozen plan. `new_scope_builder().build()` is a separate strict build boundary for a child overlay.
