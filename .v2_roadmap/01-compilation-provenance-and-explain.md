# Compilation provenance and `explain`

Status: Done
Priority: P0
Dependencies: None

## Summary

Record where composition definitions came from and why the compiler selected or rejected each candidate. Expose that
information through `CompiledGraph.explain(...)` and `clean-ioc explain` without placing source locations or decision
history in default manifests or fingerprints.

## Problem and differentiation

The compiled graph shows what will execute, but it does not explain why a candidate won, why a contextual registration
did not apply, which bundle introduced a decorator, or where an argument policy originated. Users must currently infer
those decisions from composition code and filters.

Graph renderers are common in dependency-injection libraries. A deterministic explanation of compiler decisions is more
valuable: it turns the container into a queryable compiler rather than a picture of providers after selection.

## Goals

- Locate registrations, decorators, pre-configurations, slots, entry-point declarations, and validation rules.
- Explain root and dependency selection, including all considered candidates in declaration order.
- Describe generic specialization, decorator applicability, argument policies, and overlay anchoring.
- Provide stable machine-readable reason codes and readable text.
- Preserve existing redaction and deterministic-fingerprint guarantees.

## Non-goals

- Replaying arbitrary filter logic or interpreting a filter's Python source.
- Serializing callables, closure values, build arguments, configured values, or runtime instances.
- Making occurrence IDs stable between builds.
- Changing the outcome of selection or validation.

## User stories

- A developer asks why `StripeGateway` was selected for `PaymentGateway` under one handler but not another.
- A bundle author finds the composition call site that introduced an unexpected decorator.
- A CI report links an architectural violation to the registration declaration and the affected dependency path.
- An overlay author confirms that a singleton remains anchored to its parent plan rather than being rewired.

## Public model

Add immutable public records to `clean_ioc.tooling`:

```python
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class SourceLocation:
    module: str | None
    symbol: str | None
    path: str | None
    line: int | None


@dataclass(frozen=True, slots=True)
class DefinitionOrigin:
    kind: str
    location: SourceLocation | None
    layer: str
    bundle_path: tuple[str, ...]
    definition_id: str | None


class DecisionOutcome(str, Enum):
    selected = "selected"
    rejected = "rejected"
    included = "included"


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    component_id: str
    outcome: DecisionOutcome
    reason_codes: tuple[str, ...]
    reason: str
    origin: DefinitionOrigin


@dataclass(frozen=True, slots=True)
class CompilationExplanation:
    subject: str
    path: tuple[str, ...]
    selected: tuple[CandidateDecision, ...]
    rejected: tuple[CandidateDecision, ...]

    def to_text(self) -> str: ...
    def to_dict(self) -> dict[str, object]: ...
    def to_json(self, *, indent: int | None = 2) -> str: ...
```

`DefinitionOrigin.kind` uses the stable values `registration`, `decorator`, `pre-configuration`, `scope-slot`,
`entrypoint`, `validation-rule`, and `synthetic`. `layer` is `root` or `overlay`; a later module-boundary feature may add
the module's stable name without changing these values.

`CompiledGraph.explain(...)` has two overloads:

```python
explanation = container.graph.explain(PaymentGateway)
explanation = container.graph.explain(component)
```

- Passing a service type explains default root selection for that type.
- Passing a `Component` explains the build decisions for that exact occurrence.
- Root selection accepts the same optional `filter=` argument as `resolve()`.
- A collection service explains each included member and every rejected candidate.
- The method returns an immutable result and never recompiles or reevaluates a filter.

The compiler retains a private explanation index keyed by occurrence ID and root request key. It is exposed only through
the immutable records above; consumers cannot mutate the compiled plan.

## CLI

Add:

```bash
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway
clean-ioc explain my_app.composition:application_builder --path 'root:my_app.Checkout:default:0/dependency:gateway:0'
clean-ioc explain my_app.composition:application_builder my_app.ports:PaymentGateway --name stripe --format json
```

`SERVICE` is an import locator in `module:attribute` form. `--path` is mutually exclusive with `SERVICE`; it uses a path
from the current graph manifest. The initial CLI supports default and exact-name root selection only. Arbitrary Python
filters remain available through the Python API and are not encoded on the command line.

Exit status is `0` for an explanation, `1` when the composition target does not build, and `2` for an invalid target,
service locator, path, or selection request.

## Compiler behavior

Builder operations capture an origin when a definition is created. `apply_bundle()` maintains a logical bundle stack,
so a definition records both its outer bundle path and the first caller outside the `clean_ioc` package. Source discovery
is best-effort: dynamically generated code, C extensions, and interactive sessions produce an origin with no location.

Selection records are created during compilation, not reconstructed later. Each record contains:

- the requested and specialized service type;
- the owning component and argument, when selecting a dependency;
- candidate IDs in registration order;
- the boolean result of `when=` and explicit selection filters;
- default-name eligibility and collection membership;
- generic compatibility or specialization failure;
- overlay visibility and singleton anchoring decisions;
- decorator and pre-configuration match results.

Built-in filters gain stable human-readable descriptions. For an arbitrary filter, the explanation uses its qualified
name when available and `<anonymous-filter>` otherwise. It records only the returned boolean or raised error; closure
contents and source text are never retained.

Failed builds attach the partial decision records to `ContainerBuildError` diagnostics when they are available. A failed
builder remains repairable, and a later build captures a fresh explanation index.

## Reason codes

The first release defines these candidate reason codes:

- `selected-default`, `selected-explicit-filter`, and `included-collection`;
- `rejected-name`, `rejected-filter`, and `rejected-service-type`;
- `rejected-generic-binding` and `rejected-overlay-visibility`;
- `anchored-parent-singleton`;
- `decorator-filter-matched` and `decorator-filter-rejected`;
- `pre-configuration-filter-matched` and `pre-configuration-filter-rejected`.

New reason codes may be added in minor releases. Existing codes retain their meaning.

## Privacy, manifests, and fingerprints

- Origin and explanation data are not added to `CompiledGraph.manifest()` and never affect its fingerprint.
- Explanation JSON uses qualified modules and paths relative to the build working directory when possible. It never emits
  an absolute path by default.
- Values, `build_args` keys, filter closure state, callable representations, memory addresses, and runtime IDs are absent.
- SARIF produced by the policy proposal may use the same relative source location.
- Explanation ordering is deterministic for one frozen blueprint and build input.

## Errors and failure modes

- `explain-service-not-found`: the service type is not a compiled root.
- `explain-path-not-found`: the manifest path does not identify a current occurrence.
- `explain-ambiguous-root`: the request needs a filter or exact name.
- `origin-unavailable` is informational metadata, not a build warning.
- A source-inspection failure never fails a build.
- A filter exception retains the existing build failure and records only its type and safe message.

## Compatibility

The feature adds data to the private `_PlanSet`, but it does not change registration APIs, `Component` equality, graph
manifests, or resolution. Origin capture is composition-time work. Runtime selection continues to use frozen direct maps.

## Rejected alternatives

- **Put source locations in manifests:** this makes fingerprints machine-dependent and leaks workspace structure.
- **Rerun filters when explaining:** filters may be stateful and build inputs may no longer exist.
- **Parse filter source to infer reasons:** arbitrary Python predicates cannot be interpreted reliably.
- **Use occurrence IDs in the CLI:** they are intentionally build-local and are not suitable for stored tooling links.

## Rollout

1. Capture definition origins and expose them on failed build issues internally.
2. Record root and dependency candidate decisions and add the Python API.
3. Cover decorators, pre-configurations, generics, and overlays.
4. Add text/JSON CLI output and integrate relative locations with SARIF.

## Acceptance tests

- Explain default, named, filtered, and collection selection with selected and rejected candidates in declaration order.
- Explain constructor, factory, decorator, pre-configuration, scope-slot, and argument-policy edges.
- Show closed-generic specialization and parent-singleton anchoring.
- Preserve explanations across normal scopes and use overlay-specific explanations for compiled overlays.
- Return safe, deterministic output for lambdas and source-less dynamically generated types.
- Prove explanation calls do not invoke filters, constructors, factories, generators, or context managers.
- Prove manifests and fingerprints are byte-for-byte unchanged when only source paths or bundle call sites change.
- Verify text and JSON CLI selection, invalid locators, ambiguous roots, and manifest paths.
