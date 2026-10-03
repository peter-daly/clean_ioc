---
description: Enforce application architecture and composition policy with reusable Clean IoC graph validation rules.
---

# Custom graph validation

Clean IoC compiles the complete dependency graph before runtime. Custom validation rules turn that graph into an
application-specific policy boundary: invalid architecture, missing conventions, and suspicious implementation details
can be reported before any component is activated.

A rule is a synchronous callable that receives a `ValidationContext` and returns or yields `BuildIssue` values:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext


def validate_graph(context: ValidationContext) -> Iterable[BuildIssue]:
    for visit in context.graph.walk():
        if violates_policy(visit.component):
            yield visit.issue(
                "my-app-policy",
                "The component violates an application policy",
            )


builder.add_validation_rule(validate_graph)
```

`visit.issue(...)` creates an error by default and fills in the root and complete semantic path. The resulting finding
uses the same reports, JSON output, CLI exit codes, and warning suppression as Clean IoC's built-in findings.

!!! important
    Clean IoC's built-in missing-component, circular-dependency, captive-dependency, lifespan, decorator, and
    pre-configuration checks always run during `build()`. Setting `mode="validation"` on a custom rule never
    disables those startup safety checks.

## When rules run

Clean IoC has two rule execution modes. CLI strictness is a separate decision about warning severity; it does not select
which rules run.

The public `ValidationRuleMode` type is `Literal["build", "validation"]`. Every custom rule belongs to exactly one mode,
selected when it is registered:

```python
builder.add_validation_rule(required_at_startup)  # mode="build" is the default
builder.add_validation_rule(expensive_policy, mode="validation")
```

The values are case-sensitive literal strings; boolean flags and any value other than `"build"` or `"validation"` raise
`ValueError` during registration.

| Rule | During `build()` | During `validation_report()` |
| --- | ---: | ---: |
| Built-in structural checks | Always | Prior findings retained; not rerun |
| `mode="build"` custom rule (default) | Runs | Prior findings retained; not rerun |
| `mode="validation"` custom rule | Skipped | Runs |

### Build mode protects application startup

`ContainerBuilder.build()` runs built-in structural checks and every custom rule whose `mode` is `"build"`. This is the
default so an application that never runs separate validation does not silently miss its custom
policies. An error from this subset raises `ContainerBuildError`; a warning is retained in `container.build_report`
without preventing startup.

Custom rules run only after structural compilation has produced a complete graph. For example, a missing dependency or
dependency cycle can prevent that graph from existing and stop the build before custom rules run. Once the graph does
exist, built-in complete-graph findings—such as an unreachable component or missing marked entry point—are aggregated
with findings from build rules.

Use the default for inexpensive rules that must hold whenever the application starts:

```python
builder.add_validation_rule(enforce_architecture)
```

Use `mode="validation"` when a rule is too expensive for startup or is intended only for deliberate test and CI
validation:

```python
builder.add_validation_rule(inspect_implementation_asts, mode="validation")
```

### Validation mode runs validate-only rules

An already-built container or scope can run its validate-only rules and return a complete report:

```python
report = container.validation_report()
if not report.is_valid:
    print(report.to_text())
```

Validation mode does not rerun build rules: the container already passed their error checks during `build()`.
It runs every rule registered with `mode="validation"` and returns their errors in the report instead of raising.
Each call creates a new shared `ValidationContext` for those validate-only rules, so they must be deterministic,
side-effect-free, and safe to run repeatedly.

The complete report starts with every stored `container.build_report` finding, including built-in findings and warnings
from build rules, then adds the new validate-only results. Exact duplicate findings are removed across those two sources
within the new report, and the stored build report is never mutated.

### Strictness controls warnings, not rule execution

For a successfully built target, `clean-ioc check` always runs validation mode. It is strict by default, so unsuppressed
errors and warnings produce a non-zero exit status. `--no-strict` uses the same stored build findings and runs the same
validate-only rules, but only errors produce a non-zero status. `--ignore CODE` may suppress a selected warning; errors
cannot be ignored.
An ignored warning is removed from the CLI's displayed report as well as from its exit-status decision. The underlying
container report is unchanged.

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc check my_app.composition:application_builder --ignore my-app-missing-owner
clean-ioc check my_app.composition:application_builder --no-strict
```

### Choose the execution mode by use case

| Use case | Registration | Reason |
| --- | --- | --- |
| Fast invariant required by every application instance | Default | An error stops an unsafe container from starting |
| Cheap advisory visible at startup | Default rule yielding a warning | The warning is retained without failing `build()` |
| Expensive whole-graph or source-AST analysis | `mode="validation"` | Keeps the startup path fast while retaining CI coverage |
| Policy meaningful only to architecture tests | `mode="validation"` | Runs through `validation_report()` and `clean-ioc check` |
| Reusable library policy that consumers might not check separately | Default | Avoids depending on downstream CI configuration |

!!! tip "Recommended trade-off"
    Keep cheap graph-metadata checks in build mode so every application instance is protected, even when a separate
    validation command is accidentally skipped. Prefer `mode="validation"` for rules that read source files,
    parse ASTs, or perform other expensive whole-graph analysis, and make `clean-ioc check` or an equivalent
    `validation_report()` test mandatory in CI.

    A build rule is paid for on every application build but is not rerun by full validation. A validate-only rule is paid
    for only during deliberate validation, but application startup alone will not enforce it. For a composition target,
    `clean-ioc check` first builds the container and then runs validation, so build rules and validate-only rules each run
    once. If an expensive rule protects runtime correctness rather than an architectural convention, keep it in build
    mode or split it into a cheap startup invariant and a deeper validate-only rule.

## What a rule can inspect

`context.graph` is the complete immutable `CompiledGraph`. Its `walk()` method traverses every compiled root in stable
depth-first order, even when entry-point markers focus graph rendering on a smaller public surface.

Each `GraphVisit` exposes:

| Field | Meaning |
| --- | --- |
| `root` | The compiled root occurrence and requested type |
| `component` | The current immutable `Component` occurrence |
| `components` | Every component from the root to the current occurrence |
| `root_name` | The diagnostic name of the requested root |
| `path` | The same semantic path used by built-in findings |
| `issue(...)` | A `BuildIssue` located at this occurrence |

The current component exposes its service and implementation types, stable registration ID, occurrence ID, name, tags,
lifespan, kind, activation kind, decorator position, dependencies, decorators, pre-configurations, async requirement,
and cleanup behavior.

One registration may occur beneath several roots or parents. Use `graph.walk()` directly when the path matters. For a
policy that should inspect each registration only once, deduplicate by `component.id`:

```python
from collections.abc import Iterator

from clean_ioc import ComponentKind, GraphVisit, ValidationContext


def unique_registration_visits(context: ValidationContext) -> Iterator[GraphVisit]:
    seen: set[str] = set()
    for visit in context.graph.walk():
        component = visit.component
        if component.kind is not ComponentKind.registration or component.id in seen:
            continue
        seen.add(component.id)
        yield visit
```

## Recipe: enforce architecture boundaries

The most direct architecture rule examines each dependency edge. In a visit path, the final two components are the
owner and the dependency used at that occurrence:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext


def forbid_domain_to_infrastructure(context: ValidationContext) -> Iterable[BuildIssue]:
    for visit in context.graph.walk():
        if len(visit.components) < 2:
            continue

        owner, dependency = visit.components[-2:]
        owner_module = owner.implementation_type.__module__
        dependency_module = dependency.implementation_type.__module__

        if owner_module.startswith("my_app.domain") and dependency_module.startswith("my_app.infrastructure"):
            yield visit.issue(
                "my-app-domain-depends-on-infrastructure",
                "Domain components cannot depend directly on infrastructure components",
            )
```

Because the issue is created from the dependency visit, a report points to the exact root-to-dependency path that broke
the boundary. The same registration can legitimately pass beneath one parent and fail beneath another.

## Recipe: reject duplicate service names

Clean IoC permits multiple registrations for one service. An application can impose the stronger convention that each
`(service_type, name)` pair identifies only one registration. Tracking stable component IDs avoids treating repeated
occurrences of the same registration as duplicates:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ComponentKind, ValidationContext


def require_unique_service_names(context: ValidationContext) -> Iterable[BuildIssue]:
    registrations: dict[tuple[object, str | None], set[str]] = {}

    for visit in context.graph.walk():
        component = visit.component
        if component.kind is not ComponentKind.registration:
            continue

        key = (component.service_type, component.name)
        component_ids = registrations.setdefault(key, set())
        if component.id in component_ids:
            continue
        if component_ids:
            name = component.name if component.name is not None else "<default>"
            yield visit.issue(
                "my-app-duplicate-service-name",
                f"More than one registration uses the {name!r} name for this service type",
            )
        component_ids.add(component.id)
```

The first registration is retained as the accepted definition; each later distinct registration reports its own path.
Clean IoC deduplicates exact duplicate `BuildIssue` values within each independently constructed report while preserving
the first occurrence.

## Recipe: enforce lifespan and ownership metadata

Tags make organization-specific ownership visible to both filters and validation. This example requires database
adapters to be singletons and warns when they have no owning-team tag:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, IssueSeverity, ValidationContext


def validate_database_adapters(context: ValidationContext) -> Iterable[BuildIssue]:
    for visit in unique_registration_visits(context):
        component = visit.component
        if not component.implementation_type.__module__.startswith("my_app.infrastructure.database"):
            continue

        if component.lifespan != "singleton":
            yield visit.issue(
                "my-app-database-lifespan",
                "Database adapters must use the singleton lifespan",
            )

        if not component.has_tag("owner"):
            yield visit.issue(
                "my-app-missing-owner",
                "Database adapters should declare an owner tag",
                severity=IssueSeverity.warning,
            )
```

Register metadata at composition time:

```python
from clean_ioc import Tag

builder.register(
    OrderRepository,
    SqlOrderRepository,
    lifespan="singleton",
    tags=(Tag("owner", "payments"),),
)
```

## Recipe: require a policy decorator

A boundary tag can identify components that must have an authorization, audit, retry, or tracing decorator. Decorator
metadata is available from the exact compiled pipeline, after all filters and build arguments have selected it:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext


def require_authorization(context: ValidationContext) -> Iterable[BuildIssue]:
    for visit in unique_registration_visits(context):
        component = visit.component
        if not component.has_tag("boundary", "http"):
            continue
        if any(decorator.has_tag("policy", "authorization") for decorator in component.decorators):
            continue

        yield visit.issue(
            "my-app-missing-authorization",
            "HTTP boundary components must have an authorization decorator",
        )
```

The policy is decoupled from a particular decorator class:

```python
from clean_ioc import Tag

builder.register(CheckoutHandler, tags=(Tag("boundary", "http"),))
builder.register_decorator(
    CheckoutHandler,
    AuthorizeCheckout,
    decorated_arg="handler",
    tags=(Tag("policy", "authorization"),),
)
```

## Recipe: flag risky cleanup policy

Component activation metadata can support operational conventions. This advisory rule highlights transient resources
that manage cleanup, allowing a team to review whether a wider ownership boundary would be safer:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, IssueSeverity, ValidationContext


def warn_about_transient_resources(context: ValidationContext) -> Iterable[BuildIssue]:
    for visit in unique_registration_visits(context):
        component = visit.component
        if component.lifespan == "transient" and component.manages_cleanup:
            yield visit.issue(
                "my-app-transient-resource",
                "A transient component owns cleanup; confirm that this is intentional",
                severity=IssueSeverity.warning,
            )
```

Warnings remain visible in `container.build_report` without stopping application startup. The strict CLI treats an
unsuppressed warning as a failure, so teams can adopt advisory rules gradually.

## Recipe: validate environment-specific composition

Rules can inspect immutable build arguments and the graph selected by them. This example prevents fake adapters in a
production build without revealing the value of any build argument in the issue:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext


def forbid_production_fakes(context: ValidationContext) -> Iterable[BuildIssue]:
    if context.graph.build_args.get("environment") != "production":
        return

    for visit in unique_registration_visits(context):
        if visit.component.has_tag("test-double"):
            yield visit.issue(
                "my-app-production-test-double",
                "Production composition contains a test double",
            )
```

Build arguments are never copied into findings automatically. Rule authors should avoid putting credentials, tokens,
or other input values in issue messages, roots, paths, or codes.

## Recipe: inspect implementation ASTs

`context.type_ast(type)` lazily reads and parses an inspectable Python class. Results are cached once per concrete type
for the current validation pass and shared by all rules in that pass. Source is not attached to the compiled graph,
runtime, manifest, or fingerprint.

AST inspection performs filesystem reads and parsing, so it is normally best registered with
`mode="validation"` and enforced by the full validation suite in tests or CI. Register it for build mode only when
the policy must block every application startup and that guarantee is worth the added startup cost.

This validate-only rule finds direct `os.getenv(...)` calls inside component classes:

```python
import ast
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext


def forbid_direct_environment_access(context: ValidationContext) -> Iterable[BuildIssue]:
    for visit in unique_registration_visits(context):
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
                    f"Use injected settings instead of os.getenv at {inspected.filename}:{node.lineno}",
                )


builder.add_validation_rule(forbid_direct_environment_access, mode="validation")
```

`type_ast()` returns `None` for built-in, extension, dynamically generated, or otherwise unavailable types. Each rule
decides whether missing source should be accepted or reported. Treat the returned AST as read-only; copy it before
using a mutating `ast.NodeTransformer`.

## Recipe: build reusable parameterized rules

A rule factory can package the same policy for several boundaries or applications:

```python
from collections.abc import Iterable

from clean_ioc import BuildIssue, ValidationContext, ValidationRule


def forbid_module_dependency(
    owner_prefix: str,
    dependency_prefix: str,
    *,
    code: str,
) -> ValidationRule:
    def validate(context: ValidationContext) -> Iterable[BuildIssue]:
        for visit in context.graph.walk():
            if len(visit.components) < 2:
                continue
            owner, dependency = visit.components[-2:]
            if owner.implementation_type.__module__.startswith(owner_prefix) and (
                dependency.implementation_type.__module__.startswith(dependency_prefix)
            ):
                yield visit.issue(
                    code,
                    f"{owner_prefix} cannot depend directly on {dependency_prefix}",
                )

    return validate


builder.add_validation_rule(
    forbid_module_dependency(
        "my_app.domain",
        "my_app.infrastructure",
        code="my-app-domain-infrastructure-boundary",
    )
)
```

Custom codes must be non-empty strings. Built-in codes are not reserved, but an application or organization prefix
makes ownership and `--ignore CODE` policy clearer.

## Package rules in bundles

Bundles can install policy beside reusable composition because `add_validation_rule()` is part of the shared
`ComponentBuilder` protocol:

```python
from clean_ioc import ComponentBuilder
from clean_ioc.bundles import BaseBundle


class OrganizationPolicyBundle(BaseBundle):
    def apply(self, builder: ComponentBuilder) -> None:
        builder.add_validation_rule(require_unique_service_names)
        builder.add_validation_rule(forbid_direct_environment_access, mode="validation")
```

Rules registered on a root builder are frozen into its policy. A `ScopeBuilder` inherits those rules and applies build
rules parent-first to the complete recompiled overlay graph, followed by build rules declared on the child builder.
Ordinary `new_scope()` calls reuse the prior graph and report without rerunning rules. Calling `validation_report()` on
that new scope runs the validate-only rules parent-first against the shared graph and retains the stored build findings.

## Test the full suite without starting the application

Build the immutable plan, then request the complete validation report. The first call runs build rules; the second runs
validate-only rules and combines their findings with the stored build report. Components are compiled but not activated:

```python
def test_architecture_policy(application_builder):
    container = application_builder.build()
    report = container.validation_report()

    assert report.is_valid, report.to_text()
```

`report.is_valid` checks for errors. To apply the CLI's default strict policy in a unit test, reject warnings too:

```python
assert not report.issues, report.to_text()
```

If a built-in or build rule reports an error, no container is returned. Test that earlier boundary through
`ContainerBuildError.report`:

```python
import pytest

from clean_ioc import ContainerBuildError


def test_invalid_composition_is_rejected(invalid_builder):
    with pytest.raises(ContainerBuildError) as raised:
        invalid_builder.build()

    assert "my-app-layer-boundary" in {issue.code for issue in raised.value.report.errors}
```

CI can use the same composition target as production without activating application components:

```yaml
- name: Validate dependency graph and architecture
  run: clean-ioc check my_app.composition:application_builder
```

The CLI target may be a builder, built container or scope, or a zero-argument factory returning any of them.
If the target cannot build, `check` reports that build failure; validate-only rules require a successfully built graph
and cannot run in that invocation.

## Rule behavior and failure handling

Build rules run in declaration order after built-in complete-graph findings. Validate-only rules run in declaration
order when a validation report is requested. Parent rules precede overlay rules within either phase. The complete report
lists stored build findings before validate-only findings; exact duplicates are removed while the first occurrence
retains its position.

Each yielded value is validated. If a rule raises, returns a non-iterable, returns an awaitable, or yields a malformed
issue, Clean IoC records a `validation-rule-error`, stops that rule, retains any issues it already yielded, and continues
with later rules. Asynchronous rules are rejected during registration.

Rules should be deterministic and side-effect-free. Structural compilation failures do not invoke custom rules because
no honest complete graph exists. Failed builders remain reusable. Each explicit validation report performs a new pass
of validate-only rules without rerunning build rules.
