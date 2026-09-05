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
    pre-configuration checks always run during `build()`. Marking a custom rule as strict-only, or passing
    `clean-ioc check --no-strict`, never disables those startup safety checks.

## When rules run

Choose whether a custom policy belongs on the application startup path or only in deliberate validation tooling:

| Check | `build()` | `clean-ioc check` | `clean-ioc check --no-strict` |
| --- | ---: | ---: | ---: |
| Built-in structural checks | Yes | Yes | Yes |
| Ordinary custom rule | Yes | Yes | Yes |
| `strict_only=True` custom rule | No | Yes | No |
| Unsuppressed warning fails | No | Yes | No |

Register fast, essential policies as ordinary rules:

```python
builder.add_validation_rule(enforce_architecture)
```

Defer source parsing, whole-graph analysis, or other expensive policies to CI:

```python
builder.add_validation_rule(inspect_implementation_asts, strict_only=True)
```

`clean-ioc check` is strict by default. Use `--ignore CODE` to suppress a selected warning, or `--no-strict` for a
lightweight local check that skips strict-only rules and leaves ordinary warnings informational. Errors are never
ignored.

```bash
clean-ioc check my_app.composition:application_builder
clean-ioc check my_app.composition:application_builder --ignore my-app-missing-owner
clean-ioc check my_app.composition:application_builder --no-strict
```

An already-built container or scope can also produce a fresh strict report:

```python
report = container.validation_report(include_strict_rules=True)
if not report.is_valid:
    print(report.to_text())
```

This runs only deferred rules, appends their findings after the stored `container.build_report`, and does not mutate the
container or raise for a strict-only error. Each call is a new validation pass.

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
Clean IoC deduplicates exact duplicate `BuildIssue` values while preserving the first occurrence.

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

This strict-only rule finds direct `os.getenv(...)` calls inside component classes:

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


builder.add_validation_rule(forbid_direct_environment_access, strict_only=True)
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
        builder.add_validation_rule(forbid_direct_environment_access, strict_only=True)
```

Rules registered on a root builder are frozen into its policy. A `ScopeBuilder` inherits those rules and applies them
parent-first to the complete recompiled overlay graph, followed by rules declared on the child builder. Ordinary
`new_scope()` calls reuse the prior graph and report without rerunning rules.

## Test rules without starting the application

Strict-only rules are easy to exercise in unit tests because a built container can produce their report directly:

```python
def test_architecture_policy(application_builder):
    container = application_builder.build()
    report = container.validation_report(include_strict_rules=True)

    assert report.is_valid, report.to_text()
```

For ordinary rules, assert against `ContainerBuildError.report`:

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

## Rule behavior and failure handling

Rules run in declaration order after built-in complete-graph findings. Parent rules precede overlay rules. Exact
duplicate issues are removed while the first occurrence retains its position.

Each yielded value is validated. If a rule raises, returns a non-iterable, returns an awaitable, or yields a malformed
issue, Clean IoC records a `validation-rule-error`, stops that rule, retains any issues it already yielded, and continues
with later rules. Asynchronous rules are rejected during registration.

Rules should be deterministic, side-effect-free, and safe to run more than once. Structural compilation failures do not
invoke custom rules because no honest complete graph exists. Failed builders remain reusable, and explicit strict
reports intentionally perform a new validation pass each time.
