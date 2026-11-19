# 07 — Behaviour-aware diffs and build variants

Status: Planned  
Priority: P1  
Dependencies: 01–03; 06 for capability comparison  
Related proposals: [Semantic change policy](../.v2_roadmap/03-semantic-graph-change-policy.md) and
[Build-variant checking](../.v2_roadmap/04-build-variant-matrix-checking.md)

## Outcome

Explain graph changes as specific wiring and ownership consequences with affected entry points, then use the same
comparison engine to check explicitly declared deployment/tenant variants built from fresh builders.

```text
OrderRepository: scoped → transient
  Affected entry points: PlaceOrder, CancelOrder
  Container cache sharing across resolutions is removed.
  Resource acquisition may occur more often.
  Cleanup owner remains the resolving scope.
```

The report can prove which registration, cache contract, or decorator changed. It cannot prove business compatibility,
actual object identity returned by arbitrary factories, external side effects, or a precise performance impact.

## Current foundation

`GraphManifest.diff()` and `GraphDiff` report added/removed/changed semantic paths. Manifests already contain lifespan,
activation, ownership, provider, and boundary metadata. Build inputs can select variants but are redacted. Existing
roadmap proposals define `SemanticGraphChange`, `DiffPolicy`, `BuildVariant`, and `BuildMatrix`; refine these types
rather than implementing a second competing set.

Primary integration points: `tooling.py`, `graph_analysis.py`, `cli.py`, proposed `matrix.py`, `ContainerBuilder` and
`ScopeBuilder`, compiler-tooling tests, and documentation examples.

## Proposed reports and compatibility

- Extend the earlier `SemanticGraphChange` proposal with evidence paths, before/after affected roots, bounded
  consequence descriptions, and match certainty.
- Keep raw `GraphDiff.added`, `.removed`, and `.changed` available. Add opt-in semantic reports and policy evaluation.
- Prefer existing manifest facts; if sharing/eager-deferred analysis needs extra data, introduce an optional frozen
  analysis sidecar paired with its manifest fingerprint. Baselines without it report reduced analysis capability.
- Keep risk a configurable review policy, separate from factual classification. Unknown semantic changes must not be
  silently classified as harmless. Text consequences are templates based on known facts, not generated guesses.

Proposed CLI extensions: `clean-ioc diff TARGET BASELINE --semantic`, optional `--policy LOCATOR`, and
`clean-ioc matrix MATRIX_LOCATOR --format text|json`. Preserve current raw-diff output and exit behaviour.

## Implementation stages

### 1. Match before/after nodes conservatively

- [ ] Match unchanged semantic paths first, then compare structurally corresponding relationships within matched roots.
- [ ] Use service/name/kind/argument/boundary and local structural context to identify a replacement or reorder. Do not
  assume an ordinal shift means every following collection member was replaced.
- [ ] Do not compare random registration UUIDs across builds. Use semantic registration/group evidence from 01/02 where
  available, and retain add/remove results when several matches are equally plausible.
- [ ] Detect root removal, selected implementation replacement, decorator reorder, and boundary contract changes.
- [ ] Record correspondence uncertainty and analysis-sidecar availability rather than hiding it behind a risk score.

### 2. Classify facts and consequences

- [ ] Classify dependency/root addition/removal, implementation, activation, lifespan, cache/cleanup owner, async
  requirement, scope slot, deferred target, decorator, initializer, selection metadata, and boundary changes.
- [ ] Use 01 to compute affected roots on both graphs: removed paths still need before-graph impact information.
- [ ] Use 02/03 for sharing and activation consequences. State "may acquire more often" where invocation counts are
  unknown; do not claim a latency or business-behaviour regression from graph structure alone.
- [ ] Distinguish removal of an async requirement from removal of async-only work inside an uninvoked provider target.
- [ ] Compare semantic capability tags using 06. Keep annotation-only and runtime observation changes out of the default
  semantic diff. Configuration-value changes remain outside redacted manifest comparisons and must be documented.

### 3. Add explicit policy evaluation

- [ ] Implement the existing `ChangeRisk`, `ChangeAllowance`, `DiffPolicy`, and report proposal with stable codes.
- [ ] Support allow/deny policies by change kind and component/root path. Show the matched policy and affected paths
  for each finding. Do not persist approvals or update baselines implicitly.
- [ ] Keep raw change detection exit codes intact. Document policy mode separately: 0 accepted/no policy violations,
  1 rejected change or build failure, 2 invalid inputs/policy/serialization.
- [ ] Add SARIF only by sharing the policy-pack serializer when available; text/JSON delivery does not depend on a new
  SARIF implementation or IDE integration.

### 4. Implement named build variants

- [ ] Add `BuildVariant(name, builder_factory, build_args=...)` and `BuildMatrix(variants, reference, policies)` using
  the older proposal's public design. Input mappings remain private, including keys and hashes.
- [ ] Validate unique safe public variant names and an existing reference. Variant names are public labels, not values
  derived automatically from private tenant identifiers or build inputs.
- [ ] Call each factory once in declaration order; reject reuse of the same single-use builder across variants.
- [ ] Build and fully validate each variant without activation. Close successful returned runtimes owned by the matrix
  after artifact capture; do not close an externally supplied parent of a ScopeBuilder.
- [ ] Continue after independent failures. If the reference fails, report one comparison-unavailable condition and keep
  per-variant findings; never compare against a fabricated empty graph.
- [ ] Compare valid variants and enforce same-entrypoint and permitted-drift policies. No automatic flag Cartesian
  product, runtime flag mutation, or parallel composition in the first implementation.
- [ ] Integrate partial graphs from 05 when available without treating them as valid diff baselines.

### 5. Documentation and rollout

- [ ] Ship semantic classification/impact before policy and matrix support, with independent acceptance checks.
- [ ] Add examples for a lifespan change, decorator removal, provider target change, and production/local comparison.
- [ ] Document reduced certainty with older sidecar-free baselines, deterministic artifact generation, and explicit
  regeneration when beta semantic formats change. Do not introduce schema-version adapters.

## Verification

Use before/after fixtures for all change kinds, duplicate same-type registrations, collection insertions, decorator
reorders, closed generic pattern changes, aliases, root removal, private boundaries, overlay ownership, and supplied
values. Reordering equivalent inputs must not create unsupported replacement claims. Same semantic graph with new
UUIDs or different provenance must remain equivalent.

Matrix tests cover duplicate names/builders, missing reference, factory failure, failed reference, repaired variants,
validation-only rules, user policy failure, ScopeBuilder parents, deterministic ordering, and proper runtime closure.
Check constructor/factory counters remain zero. Scan reports and errors for build-input keys, values, identities,
callback representations, and exception messages containing secrets.

## Acceptance criteria

- Every classified consequence cites an actual before/after graph fact and affected root evidence.
- Ambiguous matching and unavailable analysis are explicit; raw diffs remain usable.
- Every named variant is independently built and validated with a fresh builder and no component activation.
- Policy mode is deterministic and reviewable; no baseline or approval is changed automatically.
