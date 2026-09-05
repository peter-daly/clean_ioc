# Clean IoC V2 differentiation roadmap

Status: Proposal index
Audience: Clean IoC maintainers and design partners

## Strategy

Clean IoC should compete as a dependency-plan compiler and architecture-policy engine, not as the Python container with
the longest provider catalogue. V2 already has the essential foundation: an explicit build boundary, immutable runtime
plans, a complete occurrence-specific component graph, custom validation, deterministic redacted manifests, and
semantic graph diffs.

The roadmap extends that foundation so a team can answer four questions before application code runs:

1. Why was this component selected?
2. Does the resulting graph obey the application's architecture rules?
3. What architectural risk did this change introduce, and which entry points are affected?
4. Who owns every runtime resource, including deferred and dynamically selected dependencies?

These documents are design proposals, not release commitments. Each proposal is intended to be decision-ready before
implementation begins.

## Proposals

| Priority | Status | Proposal | Outcome |
| --- | --- | --- | --- |
| P0 | Done | [Compilation provenance and explain](01-compilation-provenance-and-explain.md) | Make every build-time selection inspectable without changing graph fingerprints. |
| P0 | Done | [Resource ownership proof](06-resource-ownership-proof.md) | Prove that cached objects, runtime contexts, and cleanup-bearing dependencies have compatible owners. |
| P0 | Proposed | [Architecture contracts and policy packs](02-architecture-contracts-and-policy-packs.md) | Turn the validation extension point into reusable architecture-as-code with CI-native output. |
| P1 | Proposed | [Semantic graph-change policy](03-semantic-graph-change-policy.md) | Classify graph changes by meaning, risk, and affected entry point. |
| P1 | Proposed | [Build-variant matrix checking](04-build-variant-matrix-checking.md) | Validate and compare every explicitly supported environment or tenant composition. |
| P1 | Proposed | [Typed deferred dependencies](05-typed-deferred-dependencies.md) | Support precompiled on-demand resolution without injecting an untyped service locator. |
| P2 | Proposed | [Assemblies and visibility](07-assemblies-and-visibility.md) | Add opt-in compile-time visibility boundaries around reusable bundles without renaming components. |
| P2 | Proposed | [Graph-correlated activation tracing](08-graph-correlated-activation-tracing.md) | Correlate optional runtime telemetry with the exact compiled component graph. |

Priority describes sequencing value, not document order. Resource ownership is P0 because typed deferred dependencies
must not ship until their lifetime and cleanup behavior can be proven.

## Dependency order

```text
compilation provenance
    ├── architecture policy diagnostics
    ├── semantic graph changes ── build-variant matrices
    ├── assembly provenance and visibility
    └── graph-correlated tracing

resource ownership proof
    ├── typed deferred dependencies ── assemblies and visibility
    ├── assemblies and visibility
    └── graph-correlated tracing
```

The proposals should be implemented in thin vertical slices. A public data type must not be released before the graph,
diagnostics, CLI behavior, redaction, and compatibility rules for that type are implemented together.

## Shared design decisions

- Building remains side-effect-free with respect to constructors, factories, generators, context managers, and cleanup.
- Runtime containers and scopes remain immutable. None of these proposals introduces post-build registration or patching.
- Every new activation or ownership edge appears in both the frozen runtime steps and the public `Component` graph.
- Provenance, source locations, build-argument names and values, configured values, and runtime instances are excluded
  from default manifests and fingerprints.
- New JSON formats are versioned. Readers reject unsupported schema versions rather than guessing.
- Existing builders, ordinary bundles, and schema-version-1 graph manifests remain supported unless a proposal explicitly
  defines an opt-in replacement.
- CLI commands accept import locators rather than evaluating Python expressions.
- The uninstrumented runtime hot path must not gain observer checks, event allocation, or recursive graph work.
- Error and policy codes are stable, lowercase, and hyphenated so CI systems can suppress or promote them predictably.

## Definition of done

A roadmap item is complete only when its public interfaces, compiler representation, runtime behavior, diagnostics,
serialization and redaction behavior, sync/async behavior, overlay behavior, and acceptance tests agree. Documentation
examples must use public imports and be executable by the repository's documentation example validator when promoted
into the supported documentation.
