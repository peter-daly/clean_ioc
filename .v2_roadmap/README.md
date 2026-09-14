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
| P1 | Done | [Typed deferred dependencies](05-typed-deferred-dependencies.md) | Support precompiled on-demand resolution without injecting an untyped service locator. |
| P2 | Done | [Boundaries and visibility](07-boundaries-and-visibility.md) | Add opt-in compile-time visibility boundaries around reusable bundles without renaming components. |
| P2 | Proposed | [Graph-correlated activation tracing](08-graph-correlated-activation-tracing.md) | Correlate optional runtime telemetry with the exact compiled component graph. |
| P1 | Done | [Modern Python type-alias support](09-modern-python-type-alias-support.md) | Normalize native and backported aliases across composition and resolution while preserving NewType identity. |
| P1 | Done | [Lazy provider maps with callable keys](10-lazy-provider-maps.md) | Freeze application-defined keys and individually invocable provider targets during compilation. |
| P1 | Done; performance inconclusive | [Generic registration patterns](11-generic-registration-patterns.md) | Structural factory templates compile with deterministic specificity and frozen closed plans; timing verification needs a quiet machine. |

Priority describes sequencing value, not document order. Resource ownership is P0 because typed deferred dependencies
must not ship until their lifetime and cleanup behavior can be proven.

## Dependency order

```text
compilation provenance
    ├── architecture policy diagnostics
    ├── semantic graph changes ── build-variant matrices
    ├── boundary provenance and visibility
    └── graph-correlated tracing

resource ownership proof
    ├── typed deferred dependencies ── boundaries and visibility
    ├── boundaries and visibility
    └── graph-correlated tracing
```

The proposals should be implemented in thin vertical slices. A public data type must not be released before the graph,
diagnostics, CLI behavior, redaction, and compatibility rules for that type are implemented together.

## Remaining suggestions

The remaining proposals are retained for later work:

1. [Architecture contracts and policy packs](02-architecture-contracts-and-policy-packs.md): provide reusable validation
   rules for layering, lifespans, capabilities, runtime-container access, metadata, and SARIF reporting. This is the
   recommended next item.
2. [Semantic graph-change policy](03-semantic-graph-change-policy.md): classify graph changes by architectural meaning,
   risk, and affected entry points, then enforce an explicit acceptance policy in CI.
3. [Build-variant matrix checking](04-build-variant-matrix-checking.md): compile and compare supported environments,
   tenants, and feature configurations. This should follow policy packs and semantic graph-change policy.
4. [Graph-correlated activation tracing](08-graph-correlated-activation-tracing.md): correlate runtime activation, caching,
   and cleanup events with compiled graph identities, with optional OpenTelemetry integration. This can proceed
   independently now that provenance and resource ownership are complete.

Recommended sequence: policy packs, semantic graph-change policy, then build-variant matrix checking. Activation tracing
does not need to wait for that sequence.

## Accepted core ideas

The following ideas are accepted; implementation status is noted per item. Unimplemented ideas remain future work,
not release commitments.

- **Implemented:** [Lazy provider maps with callable keys](10-lazy-provider-maps.md) inject a mapping from application-defined keys to
  typed providers, such as `Mapping[str, Provider[PaymentGateway]]`, without constructing every target. The required `key` argument is a pure,
  synchronous callable with signature `Callable[[Component], K]`, where `K` is hashable. It receives component metadata
  during compilation, not an activated instance. Freeze the resulting keys and provider target plans during build;
  reject duplicate or unhashable keys and report key-callable failures as structured build issues. Calling a selected
  provider activates only that target and its dependencies, following the existing visibility, scope, caching, and
  cleanup rules. Keys are not recomputed during runtime lookup. For registrations with string names, illustrative usage
  is `builder.register_provider_map(PaymentGateway, key=lambda component: component.name)`. The final API adds explicit
  `key_type`, `asynchronous`, `component_filter`, and map `name` options.
- **Done (implementation), performance inconclusive:** [Generic registration patterns](11-generic-registration-patterns.md) choose reusable registration
  templates by the structure of a requested type, such
  as `Serializer[list[T]]` versus `Serializer[dict[str, T]]`. A request for `Serializer[list[Order]]` binds `T` to `Order`
  and compiles the list factory's `Serializer[Order]` dependency. This extends existing generic factory specialization
  with structural template selection. Exact registrations precede matching patterns and open-generic fallbacks;
  supported class bounds/constraints and structural subsumption determine specificity. Ambiguity and growing expansion
  are diagnosed during build. Closed requests retain normal visibility, decorators, caching, and ownership semantics.
  The API is `builder.register_pattern(Serializer[list[T]], factory=make_list_serializer)`, with normal lifespans,
  names, tags, arguments, and `when` filters. Correctness checks pass on Python 3.11–3.14. Repeated benchmarks are recorded
  separately as inconclusive under substantial machine noise; no claim of regression-free timing is made.

## Maybe pile

- **Typed assisted factories:** combine caller-supplied arguments with compiled injected dependencies through a typed
  factory interface. Ordinary application code can usually use a small factory class, such as a `ReportJobGenerator`
  that receives a repository and accepts a report ID in its `generate()` method. Revisit this idea when a concrete
  framework extension needs to combine framework-supplied runtime arguments with injected dependencies and would benefit
  from container-managed product activation. Product lifespans, decorators, scope binding, and cleanup ownership need a
  separate design before implementation. This idea is under consideration, not accepted for implementation.

## Shared design decisions

- Building remains side-effect-free with respect to constructors, factories, generators, context managers, and cleanup.
- Runtime containers and scopes remain immutable. None of these proposals introduces post-build registration or patching.
- Every new activation or ownership edge appears in both the frozen runtime steps and the public `Component` graph.
- Provenance, source locations, build-argument names and values, configured values, and runtime instances are excluded
  from default manifests and fingerprints.
- Clean IoC JSON formats remain unversioned during beta. Do not add version fields, version checks, or migration
  adapters until the release leaves beta. Regenerate saved graphs and baselines when their format changes.
- Existing builders and ordinary bundles remain supported unless a proposal explicitly defines an opt-in replacement.
- CLI commands accept import locators rather than evaluating Python expressions.
- The uninstrumented runtime hot path must not gain observer checks, event allocation, or recursive graph work.
- Error and policy codes are stable, lowercase, and hyphenated so CI systems can suppress or promote them predictably.

## Definition of done

A roadmap item is complete only when its public interfaces, compiler representation, runtime behavior, diagnostics,
serialization and redaction behavior, sync/async behavior, overlay behavior, and acceptance tests agree. Documentation
examples must use public imports and be executable by the repository's documentation example validator when promoted
into the supported documentation.
