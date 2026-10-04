# 22 — Detailed activation tracing

Created: 2026-10-04\
Status: Deferred; not scheduled; implementation not started\
Priority: P2\
Baseline: Clean IoC 2.0.0b29 on `version2`\
Dependencies: Existing observed runtime plans, full correlation catalog, and resource ownership proof\
Parent work: [Runtime observations](08-runtime-observations-and-graph-overlays.md)\
Related work: [Runtime profiler](12-runtime-resolution-profiler.md),
[test activation coverage](21-test-activation-coverage.md), and
[graph-correlated tracing proposal](../.v2_roadmap/08-graph-correlated-activation-tracing.md)

## Outcome

Add optional detailed events for resolution, activation, cache waiting/hits, pre-configuration, failures, and cleanup,
correlated to the exact compiled graph. Support bounded local recording, streaming observers, offline inspection,
and an optional OpenTelemetry adapter without changing application classes or ordinary resolution paths.

This is a focused delivery slice of item 08 and its older roadmap proposal. The implemented profiler remains the core
source of exact aggregate counters; tracing adds sampled event detail, not a competing observer/identity system.

## Design baseline

Item 12 already selects observed step/runtime variants at build time and distinguishes exact counts from sampled
durations. Evolve that existing `Instrumentation` contract. Older proposal snippets containing observer configuration
are design sketches, not current APIs to copy unchanged. Resolve schema and callback differences against the actual
runtime before implementing new public event types.

Core tracing must work without OpenTelemetry installed. Its optional adapter is a later stage of this same item and
uses the core event contract; it does not introduce separate instrumentation or configure a global exporter.

## Event and correlation contract

1. Distinguish resolution operations, application constructor/factory bodies, dependency work, pre-configurations,
   decorators, cache hits/misses/waits, and owner cleanup. Define balanced start/finish outcomes for success, failure,
   cancellation, and retry. Durations overlap where execution nests; reports must not sum them into a false total.
2. Correlate to full graph/catalog identities and semantic paths. Preserve actual activation owner versus cache-caller
   edge, including shared initializers, anchored singletons, unmarked roots, provider/map targets, and collections.
3. Use observation-local operation/event identifiers when pairing concurrent work is necessary. They are not object
   IDs, scope IDs, owner tokens, cache keys, or another structural registration identity.
4. Sample detailed work once at its resolution boundary and define propagation through nested DI work. Deferred
   provider calls and eventual owner cleanup have their own operation boundaries. Exact profiler counters remain
   independent of event and duration sampling.
5. Cleanup may happen long after creation. Do not retain original request trace contexts per singleton/resource to
   join it to an earlier request. Emit a separate cleanup operation with the safe compiled component reference.
6. Child scopes inherit their compiled observation policy. Respect existing restrictions on overlay instrumentation
   when steps anchor to a parent; do not claim an already observed parent step can become unobserved in a child.
7. If managed providers or warm-up plans have landed, observe their real acquisition/resolution and cleanup work
   using these same boundaries. They are not prerequisites and do not justify counting application method/block time
   as factory activation.

## Recording, failure isolation, and privacy

- Support a bounded optional in-memory recorder and a streaming observer. Define event/attribute limits, overflow,
  filtering, sampling, incomplete operations, and dropped-detail counts. A full buffer must not block or change
  application activation; observers have a documented prompt-return contract.
- Observer/sampler/exporter failures cannot fail activation or cleanup, mask application exceptions, or alter retries
  and cancellation. Use a bounded disable/report policy and safe failure labels, without logging private event values.
- Retain/export qualified types, safe graph paths, kind/lifespan, observation-local IDs, outcomes, and measured durations
  only as specified. Values, arguments, map keys, provisions, build-input names/values/hashes, object/scope IDs,
  callback state, exception messages, and traceback frames stay out of default events and recordings.
- Any optional sensitive exception-detail mode requires a separate explicit contract before acceptance. Do not enable
  it merely because an external telemetry API supports it.
- Select distinct observed execution paths at build time. Disabled resolution, cached root fast paths, provider calls,
  scope creation, and cleanup gain no observer checks, clock reads, event allocation, or tracing-context work.

## Reports and optional adapter

Recorded event reports must identify their full graph/catalog, recording scope, sampling, bounds, dropped detail,
and capture completeness. Join only matching artifacts, render captured data deterministically, and offer useful
text/JSON and focused graph overlays. Offline rendering must not build targets or execute application code.

Use item 08's common artifact and correlation model, shared with item 21. Coverage may use exact aggregate observations;
sampled event presence alone does not establish complete activation coverage.

The OpenTelemetry adapter maps the agreed event semantics to resolution/activation/pre-configuration/cleanup spans
and cache/wait evidence. Respect the caller's current tracing context and use local test exporters. Do not install
process-global providers/exporters or retain request contexts on long-lived runtime owners. Document attribute
cardinality, sampling interaction, safe exception-type handling, and enabled overhead using current official APIs
when implementation resumes.

## Stages when resumed

1. Reconcile item 08 and the older roadmap proposal with current instrumentation; specify one event, correlation,
   sampling, failure-isolation, and recording contract.
2. Implement observed event emission with correct root/cache/deferred/cleanup paths, preserving the ordinary runtime.
3. Add bounded recording/streaming support, artifact validation, offline rendering, and graph projections.
4. Add the optional OpenTelemetry adapter with isolated local exporter tests; no required dependency for core use.
5. Verify exact-versus-sampled behavior, failures/concurrency/cancellation/cleanup, redaction, bounds, disabled paths,
   and measured enabled overhead; obtain independent review.

## Acceptance criteria

- Detailed events identify the real compiled call/activation paths and pair concurrent operations correctly without
  exposing runtime identities or private application data.
- Sampling/dropped detail remain explicit and never corrupt or relabel the profiler's exact aggregate counts.
- Observer failures and recording limits do not change application results, exceptions, cancellation, or cleanup.
- Ordinary runtime paths remain structurally free of tracing work; enabled cost is measured and honestly documented.
- Core tracing works without OpenTelemetry, and its optional adapter follows the same safe lifecycle/event model.
- Offline reports/overlays join only matching catalogs and preserve graph facts and fingerprints.

## Deferred status

Resume only when the maintainer prioritizes this item. The runtime profiler from item 12 is already implemented;
detailed events, recording, offline tracing views, and the optional adapter remain deferred under item 08.
