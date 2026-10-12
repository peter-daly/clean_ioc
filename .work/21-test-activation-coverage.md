# 21 — Test activation coverage

Created: 2026-10-04\
Status: Deferred; not scheduled; implementation not started\
Priority: P2\
Baseline: Clean IoC 2.0.0b29 on `version2`\
Dependencies: Existing runtime profiler, full graph catalog, and occurrence/sharing identities\
Parent work: [Runtime observations](08-runtime-observations-and-graph-overlays.md)\
Related work: [Runtime profiler](12-runtime-resolution-profiler.md),
[instance-sharing groups](02-instance-sharing-groups.md), and
[build matrices](../.v2_roadmap/04-build-variant-matrix-checking.md)

## Outcome

Show which compiled dependency paths a named test or test session requested, activated, or reached through a cache,
including deferred provider targets. Combine those observations with the matching compiled graph so a developer can
see gaps in exercised composition without mistaking them for unreachable code.

This is a focused delivery slice of item 08. It extends the existing profiler/correlation model; it does not create
another instrumentation system or require detailed tracing from item 22.

## Current foundation and initial scope

`ResolutionProfiler` already captures exact request, activation, failure, and cache counters independently of duration
sampling, including catalog paths with zero observed activity. First investigate deriving named coverage reports from
fresh instrumented test runtimes and captured snapshots. Session deltas or pytest fixtures can follow if their
boundaries and concurrency semantics can be made precise without resetting unrelated live collectors.

No new public recording API is accepted yet. Proposed report/session names must reuse or refine item 08's
`ActivationCoverage` model. Standard pytest integration is optional convenience, not a prerequisite for a Python report.

## Evidence contract

1. Distinguish requested, activation attempted, activation completed, activation failed, and cache-observed paths.
   A cache hit exercises a consumer edge but does not prove that the underlying constructor ran during this session.
   Preserve actual activation owner versus calling occurrence and registration/sharing-group attribution.
2. Report zero-count paths as "not observed during this session", not unused, unreachable, or untested application
   code. This measures DI activation behavior, not method execution, branches, statements, or factory-body coverage.
3. Keep exact counts independent of timing/event sampling. Sampled detailed traces cannot silently define total
   coverage. Capture failures, dropped updates, incomplete sessions, and in-flight work remain visible.
4. Join to the matching full graph and captured correlation catalog, including unmarked, private, collection,
   deferred, and anchored paths. Equal type names or default entry-point fingerprints are not sufficient identity.
5. Do not merge different build-local registration identities just because structural fingerprints match. Define an
   explicit validated semantic correspondence if cross-build coverage comparison is later needed. Matrix variants
   retain separate catalogs and observations.
6. `BuildMatrix` remains a static composition check and activates nothing. Coverage is supplied by tests that execute
   application behavior against instrumented runtimes; constructing a matrix report does not create observations.
7. Named sessions use documented public labels and precise start/end boundaries. Nested/concurrent sessions must not
   double count or steal observations; choose isolated runtimes for the initial delivery if isolation is simpler.
8. A report is an immutable observation. It cannot mutate compiled graphs, change fingerprints, or become a static
   ownership/architecture guarantee. Any test assertions act on captured coverage, not on `BuildReport`.
9. Bound retained data by compiled references and explicit session limits. Do not retain application instances,
   request data, slot values, callback state, exception messages/frames, or runtime object/scope identifiers.
10. Collect only through opt-in observed plans. Ordinary tests, uninstrumented resolution, and scope creation gain
    no coverage branches, session lookups, timers, or event allocation.

## Reports and tooling

Deliver useful text/JSON views and a focused annotated graph projection showing observed request/activation/cache
categories and not-observed paths. Reuse existing semantic paths, sharing groups, and safe source locations.

Consider assertions for explicitly selected expected paths or deferred targets, with visible recording completeness.
Do not introduce a universal coverage percentage that hides provider branches, shared activations, or cache-only paths.
Selection denominators and observation categories must be explicit if percentages are offered later.

An offline renderer may join saved graph and coverage artifacts without importing/building/running the application.
Reject mismatched or malformed artifacts clearly. Use item 08's common artifact/correlation design rather than a second
format incompatible with detailed tracing. Public beta artifacts remain unversioned.

## Stages when resumed

1. Map existing exact profiler fields to honest coverage categories and define catalog/session/completeness semantics.
2. Implement a small snapshot-derived named report, graph joins, text/JSON output, and focused observation assertions.
3. Verify source/graph projections and artifact validation; add pytest convenience only when justified by real tests.
4. Exercise cached versus cold tests, failures/cancellation, providers/maps, sharing, overlays, and sampling extremes;
   run CI/docs and obtain independent review.

## Acceptance criteria

- Tests can identify observed and not-observed compiled paths and deferred targets with accurate session boundaries.
- Cached requests do not falsely claim constructor coverage; shared activations are not multiplied across paths.
- Timing sampling does not remove exact coverage, and incomplete capture is never presented as complete evidence.
- Reports match their full catalog, remain bounded/redacted, and can be rendered without executing application code.
- Static build/matrix behavior and normal uninstrumented runtime costs remain unchanged.

## Deferred status

Resume only when the maintainer prioritizes this item. Item 12 remains implemented; only this additional coverage slice
is deferred. This document scopes item 08's coverage deliverable rather than replacing its shared design rules.
