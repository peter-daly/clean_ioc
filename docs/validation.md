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
is synchronous, receives a per-build `ValidationContext`, and returns or yields zero or more `BuildIssue` values. The
context's `graph` is the complete `CompiledGraph`; `graph.walk()` visits every occurrence with its root and complete
semantic path, including decorators, pre-configurations, collections, configured values, runtime contexts, and scope
slots.

The examples below introduce the core API. See the dedicated [custom graph validation cookbook](custom-validation.md)
for registration-uniqueness, architecture, metadata, lifespan, decorator, build-argument, AST, bundle, overlay, testing,
and CI recipes.

This example prevents a domain-layer component from depending directly on infrastructure:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext


def enforce_architecture(context: ValidationContext) -> Iterable[BuildIssue]:
    graph = context.graph
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
runtime's report and participate in the strict-by-default `clean-ioc check` and `--ignore CODE` policies. Prefer an
application or organization prefix for custom codes.

Rules that are too expensive for application startup can be deferred to strict validation:

```python
builder.add_validation_rule(enforce_architecture, strict_only=True)
```

A strict-only rule is frozen into the graph policy but skipped by `build()`. The CLI runs deferred rules by default
with `clean-ioc check ...`, which is suitable for CI. The default strict mode also makes every unsuppressed warning
fatal; `--ignore CODE` can suppress warnings from either ordinary or strict-only rules, but never errors. Pass
`--no-strict` to skip deferred rules and leave warnings informational.

For programmatic tooling, request a fresh aggregate report from an already-built container or scope:

```python
report = container.validation_report(include_strict_rules=True)
```

This runs only the deferred rules and appends their findings after the stored build findings. It does not mutate
`container.build_report` or raise for a strict-only error. Calling it again performs a new validation pass.

### Inspecting implementation source

`context.type_ast(type)` lazily extracts and parses an inspectable Python class definition. Results are cached within
the validation context, so every rule in one build shares one parse per concrete type. The returned `TypeAst` includes
the source filename, original first line, dedented source, and an `ast.ClassDef` whose line numbers match the original
file.

```python
import ast

from clean_ioc import ValidationContext


def forbid_direct_environment_access(context: ValidationContext):
    for visit in context.graph.walk():
        inspected = context.type_ast(visit.component.implementation_type)
        if inspected is None:
            continue

        for node in ast.walk(inspected.node):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "getenv"
            ):
                yield visit.issue(
                    "my-app-direct-environment-access",
                    f"Direct os.getenv() call at {inspected.filename}:{node.lineno}",
                )


builder.add_validation_rule(forbid_direct_environment_access, strict_only=True)
```

Source inspection returns `None` for built-in, extension, dynamically generated, and otherwise unavailable class
definitions. Each rule decides whether that should be ignored or reported. Treat the returned AST as read-only; copy it
before using a mutating `ast.NodeTransformer`. The context and its cache are not stored on the resulting container or
graph, and source data never enters manifests or fingerprints. Marking a source-inspection rule as strict-only also
defers its inspection and parsing cost until a strict validation pass.

Ordinary rules execute only after structural compilation produces a complete graph. They therefore do not run during
builder preview queries or when missing dependencies, cycles, or another structural failure prevent that graph from
existing. They do run alongside complete-graph findings such as a missing marked entry point. Strict-only rules require
a successfully built graph and run only when strict validation is requested. A rule that raises, returns a non-iterable
value, or yields a malformed issue produces `validation-rule-error`; later rules still run so the report remains useful.

Rules should be deterministic, side-effect-free, and safe to run again after a failed build. They may inspect
`context.graph.build_args`, but Clean IoC does not automatically copy those inputs into a report: do not include secrets
in a custom issue's code, message, root, or path.

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
