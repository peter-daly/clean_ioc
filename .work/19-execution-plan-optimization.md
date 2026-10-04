# 19 — Execution-plan optimization

Created: 2026-10-04\
Status: Prioritized; queued after item 18; implementation not started\
Priority: P2\
Baseline: Clean IoC 2.0.0b30 at `eacdf70` on `codex/compiler-optimization`\
Dependencies: Existing frozen steps, occurrence graph, ownership/sharing analysis, and compilation profiler\
Related work: [Instance-sharing groups](02-instance-sharing-groups.md),
[compilation profiler](11-compilation-profiler.md),
[runtime profiler](12-runtime-resolution-profiler.md), and
[incremental compilation](18-incremental-compilation.md)

## Outcome

Investigate reducing execution-plan allocation or execution overhead by sharing equivalent immutable structure or
simplifying safe step sequences within one compiled build. Preserve separate graph occurrences so selection,
provenance, ownership, and runtime attribution remain inspectable.

This item concerns the representation produced by a build. Item 18 concerns reuse across builds; neither is a
prerequisite for the other. Exact optimizations and public configuration remain undecided until measured evidence
identifies a useful, provably equivalent transformation.

## Current foundation

The runtime already uses lifespan-specialized steps, direct root maps, cached-root fast paths, frozen async capability,
and selected shared/anchored initializer plans. Graph occurrences intentionally preserve different parents and
dependency contexts even when they refer to the same registration. Profiler attribution already distinguishes actual
activation from the graph edge consuming a cache.

Do not replace those specialized paths with a generic dispatcher or assume repeated service types imply equivalent work.

## Required equivalence model

Before sharing or simplifying a step, account for its effective service and implementation, bound arguments, selected
dependency steps, generic specialization, decorators, pre-configurations, resolution-context bridges, async capability,
cache/cleanup owners, scope policy, and occurrence-sensitive behavior. Public graph equality alone is insufficient.

Mutable initializer/coordinator state cannot be shared solely because immutable step descriptions match. Reuse must
follow the existing registration and owner semantics, never create a new application-instance sharing relationship.

## Required constraints

1. Preserve factory/constructor/decorator invocation counts, pre-configuration semantics, dependency order where
   defined, callback behavior, and all four concrete lifespans. Sharing an executable object must not merge transient
   products or separate per-resolution products that currently share.
2. Keep singleton/scoped cache keys and owners correct. Preserve cleanup ownership, acquisition/finalization order,
   exception aggregation, cancellation, and concurrent initialization behavior.
3. Preserve occurrence-specific derived arguments, contextual filters/preferences, generic bindings, slots,
   visibility, and anchored parent singleton composition. Structural similarity is not proof of equivalence.
4. Graph paths, selected/rejected explanations, policy findings, source-linked SARIF, semantic diffs, ownership,
   activation analysis, and sharing reports remain truthful. Do not collapse diagnostic occurrences to save step memory.
5. Observed plans retain exact calling-edge and activation attribution. An optimization must not attribute one shared
   initializer's work to every graph path or make profiler counts disappear.
6. Existing ordinary runtime paths remain specialized. No per-resolution graph traversal, equivalence calculation,
   optimizer checks, or new observer branches belong on the uninstrumented hot path.
7. Changes to internal plan representation preserve default public manifests/fingerprints when composition semantics
   are unchanged. Optimization metadata belongs in compiler profiling or an optional diagnostic sidecar.
8. Add only transformations with a documented proof boundary and measured benefit. Do not ship broad automatic
   common-subexpression elimination, arbitrary factory memoization, or speculative parallel activation.

## Scope and verification

Start by measuring emitted step counts, allocation, build cost, and runtime cost for repeated generic subgraphs,
diamonds, large collections, and parent/overlay sharing. Evaluate small internal transformations first; no new public
optimizer framework is required.

Compare optimized and baseline executions for returned identities, activation traces/counts, scoped/per-resolution
sharing, custom selection/derived values, decorated resources, providers/maps, per-call boundaries, and cleanup.
Include async contention, failures, cancellation, templates, aliases, and profiling attribution. Integrate managed
providers and warm-up plans only if those features have landed by implementation time.

## Stages when resumed

1. Identify a measured source of avoidable plan cost and specify exact eligibility and equivalence conditions.
2. Implement one narrow transformation with before/after compiler and runtime evidence.
3. Verify complete graph/report equivalence plus behavioral lifecycle and observed-path correctness.
4. Run supported-Python checks and repeatable measurements, then obtain independent review before expanding scope.

## Acceptance criteria

- A documented transformation reduces a measured cost without changing application-instance identity, activation,
  selection, cleanup, or exception behavior.
- Occurrence graphs and all related diagnostics/observations stay accurate and deterministic.
- Runtime and compilation regressions are measured and justified; enabled profiling continues to describe real work.
- A transformation without convincing equivalence or useful benefit is declined or remains experimental rather than
  weakening the compiler's guarantees.

## Scheduling

Pre-change timing, allocation and compilation profiles are recorded in
[the compiler baseline](compiler-optimization-baseline.md). Eager provider-root expansion dominates the measured
wide-root build and is the first concrete representation target to investigate.

The maintainer prioritized this item on 2026-10-04 after item 18. Baseline benchmarks precede all compiler changes;
measure the completed item 18 state as well so item 19's impact can be distinguished. Sol High implements this item
and a separate Sol High agent reviews it before item 20 starts. Benchmark evidence selects the implementation target;
the common work-list CI, documentation, performance, and independent-review requirements apply.
