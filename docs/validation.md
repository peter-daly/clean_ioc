# The build boundary

`ContainerBuilder.build()` is the validation and compilation boundary. It first materializes queued subclass and generic discovery rules from the currently live Python classes. It then walks every visible root, specializes generic dependencies, constructs occurrence-specific component trees, evaluates filters, and freezes runtime instructions.

```python
from clean_ioc import ContainerBuilder

builder = ContainerBuilder()
builder.register(Repository, SqlRepository)
builder.register(CreateOrder)

container = builder.build()
```

No user constructor, factory, generator, or context manager runs during this work. Functions passed explicitly to
`derive(...)` do run because their concrete values are compiled into the plan.

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

## Custom graph rules

Use `add_validation_rule()` to enforce application or organization policy against the complete immutable graph. A rule
is synchronous, receives `CompiledGraph`, and returns or yields zero or more `BuildIssue` values. `graph.walk()` visits
every occurrence with its root and complete semantic path, including decorators, pre-configurations, collections,
configured values, runtime contexts, and scope slots.

This example prevents a domain-layer component from depending directly on infrastructure:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, CompiledGraph


def enforce_architecture(graph: CompiledGraph) -> Iterable[BuildIssue]:
    for visit in graph.walk():
        if len(visit.components) < 2:
            continue
        parent, dependency = visit.components[-2:]
        if (
            parent.implementation_type.__module__.startswith("my_app.domain")
            and dependency.implementation_type.__module__.startswith("my_app.infrastructure")
        ):
            yield visit.issue(
                "my-app-domain-depends-on-infrastructure",
                "Domain components cannot depend directly on infrastructure components",
            )


builder.add_validation_rule(enforce_architecture)
```

`visit.issue()` creates an error by default and fills in the matching root and path. Pass
`severity=IssueSeverity.warning` for an advisory finding. Errors fail `build()`; warnings appear on the successful
runtime's report and participate in the existing `clean-ioc check --strict` and `--ignore CODE` policies. Prefer an
application or organization prefix for custom codes.

Rules execute only after structural compilation produces a complete graph. They therefore do not run during builder
preview queries or when missing dependencies, cycles, or another structural failure prevent that graph from existing.
They do run alongside complete-graph findings such as a missing marked entry point. A rule that raises, returns a
non-iterable value, or yields a malformed issue produces `validation-rule-error`; later rules still run so the report
remains useful.

Rules should be deterministic, side-effect-free, and safe to run again after a failed build. They may inspect
`graph.build_args`, but Clean IoC does not automatically copy those inputs into a report: do not include secrets in a
custom issue's code, message, root, or path.

## Builder state after build

A failed build leaves the builder reusable:

```python
try:
    builder.build()
except ContainerBuildError:
    builder.register(MissingDependency)

container = builder.build()
```

After a successful build, the builder rejects registration, decoration, pre-configuration, patching, slot declaration,
validation-rule registration, bundle application, and a second `build()` call. The resulting `Container` has no
mutation APIs.

## Inspecting the static plan

Runtime containers expose their compiled root components:

```python
for component in container.components:
    print(component.service_type, component.implementation_type, component.lifespan)

    for dependency in component.dependencies:
        print("  ", dependency.argument, dependency.service_type)
```

`Component` objects are immutable views of static occurrences. A stable component ID identifies its registration; `occurrence_id` distinguishes the same registration under different parents.

`container.graph` adds a complete, read-only view that also models configured/default values, runtime contexts,
declared slots, decorators, and pre-configurations. It can render text or Mermaid and produce deterministic, redacted
JSON manifests.

## Child composition

`new_scope()` never validates or compiles because it reuses its parent's frozen plan. `new_scope_builder().build()` is a
separate strict build boundary for a child overlay. It runs only discovery rules declared on that `ScopeBuilder`;
inherited root discovery is already frozen and is never rescanned. Custom validation rules are different: an overlay
inherits its parent's policy rules, applies them to the complete recompiled overlay graph, and then runs rules declared
on the `ScopeBuilder`.
