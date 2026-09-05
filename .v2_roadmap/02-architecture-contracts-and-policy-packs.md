# Architecture contracts and policy packs

Status: Proposal
Priority: P0
Dependencies: Compilation provenance for source-linked diagnostics

## Summary

Provide reusable first-party validation rules for common architectural constraints and package them as callable policy
bundles. Add SARIF output to `clean-ioc check` so graph violations appear as source-linked CI findings.

## Problem and differentiation

`ValidationRule` is deliberately general, but every application must currently write traversal, matching, issue codes,
and tests for recurring rules. That makes the strongest V2 capability feel like an extension mechanism rather than a
product.

First-party policies make the compiled graph an architecture contract. The differentiator is not merely finding missing
dependencies; it is enforcing application-specific rules over the complete occurrence graph before startup.

## Goals

- Cover high-value layering, decorator, lifespan, runtime-access, metadata, and capability rules.
- Compose policies through existing `ComponentBuilder` methods without a second configuration system.
- Produce stable issue codes and path-aware diagnostics.
- Support ordinary build-time and strict-only CI policies.
- Export standards-compliant SARIF with source locations when provenance exists.

## Non-goals

- A YAML or TOML policy language in the first release.
- Import-graph or package-dependency analysis unrelated to compiled components.
- Replacing arbitrary application-defined validation callbacks.
- Automatically rewriting registrations to satisfy a policy.
- Treating tags as trusted security enforcement at runtime.

## User stories

- A clean-architecture application prevents domain components from depending on infrastructure components.
- A payments team requires every gateway to be decorated with tracing and idempotency behavior.
- A platform team prohibits `Scope` and `ResolutionContext` outside delivery adapters.
- CI rejects any entry point that transitively gains the `network` capability.
- A library distributes its recommended graph rules as one reusable bundle.

## Public API

Add `clean_ioc.policies` with immutable matchers and rule factories:

```python
import clean_ioc.component_filters as cf
from clean_ioc.metadata import Tag
from clean_ioc.policies import (
    Layer,
    PolicyPack,
    capability_boundary,
    forbid_dependency,
    forbid_runtime_access,
    layering,
    require_decorator,
    require_lifespan,
    require_tags,
)

architecture = PolicyPack(
    "application-architecture",
    layering(
        layers=(
            Layer("domain", module_prefixes=("my_app.domain",)),
            Layer("application", module_prefixes=("my_app.application",)),
            Layer("infrastructure", module_prefixes=("my_app.infrastructure",)),
        ),
        allowed_dependencies={
            "domain": frozenset({"domain"}),
            "application": frozenset({"application", "domain"}),
            "infrastructure": frozenset({"infrastructure", "application", "domain"}),
        },
    ),
    require_decorator(
        cf.service_type_is(PaymentGateway),
        decorator_type=TracedGateway,
    ),
    forbid_runtime_access(
        cf.create_filter(lambda component: component.implementation_type.__module__.startswith("my_app.domain")),
    ),
    require_tags(
        cf.create_filter(lambda component: component.implementation_type.__module__.startswith("my_app.infrastructure")),
        Tag("owner", "platform"),
    ),
    strict_only=False,
)

builder.apply_bundle(architecture)
```

`PolicyPack` is a callable bundle implementing `__call__(builder: ComponentBuilder) -> None`. It registers its rules
through `add_validation_rule()` and therefore works with both `ContainerBuilder` and `ScopeBuilder`; no new builder method
is required. Pack and rule names are included in diagnostic metadata but not graph fingerprints.

The standard factories are:

- `layering(...)`: match implementation modules to named layers and validate every direct component edge against an
  explicit allowed-dependency map. Unmatched modules are ignored unless `require_match=True`.
- `forbid_dependency(source, target, *, transitive=False)`: reject matching source-to-target edges. Transitive mode
  reports the shortest semantic path for each source occurrence.
- `require_decorator(target, *, decorator_type, count=1)`: require an exact compiled decorator type and count.
- `require_lifespan(target, *allowed)`: constrain the public lifespan string of matching components.
- `forbid_runtime_access(target)`: reject `Scope` or `ResolutionContext` dependencies below matching components.
- `require_tags(target, *tags)`: require exact `Tag` pairs on the compiled occurrence.
- `capability_boundary(entrypoints, *, allow)`: collect `Tag("capability", value)` transitively and reject capabilities
  not allowed for each matching entry point.

Filters use the existing immutable `Component` model. Factories return normal `ValidationRule` callbacks and may be used
without a `PolicyPack` when applications want individual control.

## Policy semantics

Rules evaluate the complete graph returned by `CompiledGraph.walk()`, not only marked entry points. A rule that explicitly
accepts an `entrypoints` filter limits its subject roots but still evaluates the complete subgraph below each selected
root.

One semantic occurrence produces at most one issue per rule. When the same registration occurs under multiple roots,
each violating path is reported because its architectural context may differ. Issues are ordered by root order, graph
walk order, pack order, then rule order.

Graph-only policies run during `build()` by default. `PolicyPack(strict_only=True)` registers every contained rule as
strict-only. Source-AST policies are not part of this initial pack; applications continue to use explicit strict-only
rules for AST work.

Capabilities use ordinary exact tags in the first release. A component may declare multiple capability tags, such as
`network`, `filesystem`, `database`, `secrets`, or an application-defined value. Capabilities accumulate transitively;
they are never inferred from imports or implementation names.

## Stable issue codes

- `policy-layer-violation`
- `policy-forbidden-dependency`
- `policy-missing-decorator`
- `policy-decorator-count`
- `policy-invalid-lifespan`
- `policy-runtime-access`
- `policy-missing-tag`
- `policy-capability-violation`
- `policy-unmatched-layer` when `require_match=True`

Issue messages name the policy pack and rule, but suppression continues to operate on the stable code. A malformed custom
matcher or policy callback remains `validation-rule-error`, and subsequent rules continue.

## SARIF output

Extend the check command:

```bash
clean-ioc check my_app.composition:application_builder --format sarif -o clean-ioc.sarif
```

The output conforms to SARIF 2.1.0:

- `ruleId` is the `BuildIssue.code`;
- errors map to SARIF `error` and warnings map to `warning`;
- the primary location is the violating component's relative registration source when available;
- dependency paths become a SARIF code flow with source locations when available;
- the result message contains the safe issue text and semantic component path;
- the tool execution records the Clean IoC version and graph fingerprint, but no build inputs.

`check -o` is supported for text, JSON, and SARIF. Existing text/JSON behavior and strict warning promotion remain
unchanged. SARIF writes a valid report even when the target fails structurally. Invalid CLI input still exits `2` and
does not fabricate a SARIF build result.

## Privacy and serialization

- SARIF URIs are relative to the build working directory when possible and never contain absolute paths by default.
- Policy names, issue codes, semantic type names, and component paths are safe output.
- Build-argument keys and values, configured values, runtime objects, callable representations, and filter closure data
  are never emitted.
- Policies and policy results affect reports, not graph fingerprints. Capability tags already present in manifests
  continue to affect fingerprints as ordinary component tags.

## Compatibility

Existing custom rules, bundles, `--ignore`, `--strict`, and `--no-strict` behavior remain unchanged. Policy packs are
opt-in and use the existing builder protocol. Adding `sarif` and `-o` extends the CLI without changing default output.

## Rejected alternatives

- **A declarative policy DSL:** Python filters and rule factories are typed, composable, and already part of composition.
- **Infer layers from directory order:** allowed edges must be explicit so refactors do not silently change policy.
- **Infer capabilities from imports:** imports do not reliably describe runtime effects and create false confidence.
- **Report one issue per registration:** occurrence-specific paths are necessary for contextual filters and decorators.
- **Put policy results in manifests:** a manifest describes the graph; a report describes policy evaluation.

## Rollout

1. Ship the matcher helpers, stable issue codes, and graph-only rule factories.
2. Add `PolicyPack` and examples for clean architecture and capability boundaries.
3. Add provenance-backed SARIF output and `check -o`.
4. Publish reusable policy packs for FastAPI boundaries and recommended Clean IoC conventions.

## Acceptance tests

- Validate allowed and forbidden direct and transitive layer edges across constructors, factories, collections,
  decorators, argument selection, and pre-configurations.
- Require decorators by exact specialized type and count without matching a similarly named type.
- Validate lifespan, runtime-access, tag, and transitive capability rules on occurrence-specific paths.
- Confirm overlay policy inheritance is parent-first and local packs run afterward.
- Confirm strict-only packs are skipped by `build()` and included by explicit strict reports and the default CLI check.
- Aggregate multiple policy failures deterministically and continue after malformed custom rules.
- Generate valid SARIF with and without source information and with structural build failures.
- Prove SARIF and JSON never contain build-argument keys, values, absolute paths, or runtime identities.
- Verify existing `--ignore`, warning promotion, text/JSON output, and exit codes remain compatible.
