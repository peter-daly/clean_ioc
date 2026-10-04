# 18 — Incremental compilation

Created: 2026-10-04\
Status: Deferred; not scheduled; implementation not started\
Priority: P2\
Baseline: Clean IoC 2.0.0b29 on `version2`\
Dependencies: Existing composition snapshots, occurrence-specific compilation, and compilation profiler\
Related work: [Compilation profiler](11-compilation-profiler.md),
[build matrices](../.v2_roadmap/04-build-variant-matrix-checking.md), and
[execution-plan optimization](19-execution-plan-optimization.md)

## Outcome

Reduce repeated compiler work across related fresh builds, overlays, or matrix variants by reusing analysis that is
provably unaffected by the changed composition. Every build still produces its own immutable runtime with correct
selection, values, owners, graph occurrences, diagnostics, and validation results.

This is a deferred investigation and implementation item. Reusing an entire executable plan is not assumed safe, and
no public cache API or performance claim is accepted by this document.

## Current foundation

The compiler already caches selected specialization work within a build and reuses anchored parent singleton and
pre-configuration steps in overlays. Item 11 measures actual compilation phases, callback costs, and repeated work.
`BuildMatrix` deliberately requests fresh builders and closes each built runtime after capturing its report.

This item investigates reuse beyond those existing mechanisms; it must preserve matrix freshness and lifecycle rules.

## Design questions to settle before implementation

- Which work dominates representative repeated builds: signature/type processing, generic specialization, structural
  candidate expansion, callbacks, ownership analysis, diagnostics, or validation? Establish this with actual profiles.
- Which results are immutable analysis, and which embed configured values, parent context, registration identity,
  owner tokens, callback state, or runtime initializer/cache state?
- Can a trustworthy composition revision and dependency index establish eligibility without hashing arbitrary
  application values or treating callable identity as a purity guarantee?
- Should the first delivery reuse only signature/type analysis, or can a bounded reusable compilation snapshot
  safely support a larger subset? Public names and cache lifetime remain undecided until the evidence supports them.

## Required constraints

1. Default manifest fingerprints are not cache keys. They deliberately omit private build inputs, values, and
   contextual information that can change compilation. Equal fingerprints do not prove equivalent compiler inputs.
2. Changes to declarations, argument policies, filters/preferences, templates, visibility, generic bindings, root
   policies, slots, or build inputs invalidate affected work. In-place annotation/signature mutations and module reloads
   must also invalidate or make the source ineligible; a repaired builder cannot receive a stale cached result.
3. Preserve composition callback invocation/order and validation semantics. Do not skip filters, derivations, template
   callbacks, discovery, or rules on the assumption that they are pure. Any callback-reuse opt-in would need a separate
   explicit contract before acceptance; the initial investigation may conclude such work is ineligible.
4. Recreate occurrence-specific parent/dependency metadata and bind executable work to the new build's identities,
   values, and owners. Separate containers must never share singleton/scoped instances, coordinators, initializer
   completion, finalizers, or mutable compiler state through the reuse cache.
5. Existing anchored overlay reuse remains owner-aware. Do not change parent singleton wiring or import a parent's
   private inputs into a new composition merely because a subtree looks structurally equal.
6. Bound cache retention and define eviction, failure cleanup, concurrency, and invalidation. Do not retain completed
   runtimes or acquired resources. Private in-process analysis references are not exported as values or fingerprints.
7. Successful and failed builds retain current diagnostics, source/path explanations, builder repairability, and
   redaction. Runtime resolution stays plan-driven and gains no compiler-cache checks.
8. Reuse statistics describe actual eligible work/hits/misses and why reuse was rejected. They are compiler evidence,
   separate from runtime cache hits and graph fingerprints.

## Scope and verification

Use fresh related builds, changed build inputs, generic-heavy graphs, templates, contextual selection, and overlays as
representative cases. Compare complete compilation with reuse-enabled compilation for selected implementations,
arguments, paths, findings, ownership, activation counts, cache identity, and cleanup behavior.

Include mutable callback closure state, same callable identity with changed annotations, repaired failed builds,
changed visibility, anchored singletons, and concurrent separate builds. Verify bounds and recursively inspect
diagnostic output for private values. Reuse must never activate application objects during build.

Persistent on-disk caches, pickled runtime plans, runtime registration changes, automatic cross-process reuse, and
source-code generation are outside the initial scope.

## Stages when resumed

1. Profile representative repeated builds and record a dependency/eligibility model with explicit exclusions.
2. Select a small useful reuse boundary and a bounded opt-in design; document invalidation before implementation.
3. Implement it with full-compile equivalence tests, current tooling integration, and cache lifecycle verification.
4. Record supported-Python correctness and repeatable build-time/memory measurements; obtain independent review.

## Acceptance criteria

- Eligible reuse produces the same composition, diagnostics, callback behavior, ownership, and runtime behavior as
  full compilation, with fresh runtime caches and resource owners.
- Private values, mutable context, repaired declarations, and reloads cannot produce false cache hits.
- Reuse is bounded, inspectable, and absent from normal resolution paths.
- Representative measurements demonstrate a useful gain with stated limits; inconclusive measurements are labelled
  inconclusive. If eligibility leaves no worthwhile gain, record that finding instead of shipping an unsafe cache.

## Deferred status

Resume only when the maintainer prioritizes this item. The first decision is whether measured repeated work justifies
implementation. The common work-list CI, documentation, performance, and independent-review requirements apply.
