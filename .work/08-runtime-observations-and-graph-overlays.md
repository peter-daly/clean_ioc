# 08 — Runtime observations over the compiled graph

Status: Planned extensions; item 12 runtime profiler implemented and independently reviewed  
Priority: P2  
Dependencies: 01–03 stable references, sharing semantics, and activation analysis  
Related proposal: [Graph-correlated activation tracing](../.v2_roadmap/08-graph-correlated-activation-tracing.md)

The focused [runtime resolution profiler](12-runtime-resolution-profiler.md) is the first deliverable of this work.
Implement the opt-in execution hooks, safe graph references, bounded in-process counts, sampled timings, and basic
text/JSON report there. This item then extends that same model with detailed recording, graph overlays, test-session
coverage, offline inspection, and optional OpenTelemetry integration. Do not duplicate observers, identities, or
aggregation. Exact counts in item 12 remain independent of any timing sampler; a later tracing sampler may suppress
detailed events but must not silently turn exact profiler counts into sampled counts.

## Outcome

Record opt-in activation, cache, wait, failure, and cleanup evidence and join it to the exact compiled graph. Provide
per-component summaries and test-session activation coverage without changing application classes or slowing the
uninstrumented execution path with observer checks.

```text
DatabasePool — observed during this recording
  Activations: 1
  Construction time: 180 ms
  Cache hits: 4,203
  Wait time for another caller's activation: 76 ms
  Cleanup failures: 0
```

The example values are illustrative. Reports must distinguish measured activity from static guarantees and describe
unseen branches as "not observed", not "unused" or "unreachable".

## Current foundation

The compiler emits lifespan-specialized steps with direct dependencies and cleanup descriptors. Scoped/singleton
coordinators distinguish activation winners from waiters. Providers start fresh resolution contexts; shared
pre-configurations and anchored parent singletons reuse executable objects across graph occurrences.

The earlier tracing proposal defines an observer, instrumentation option, event kinds, and optional OpenTelemetry
adapter. This item adds correlation rules, bounded recording/aggregation, and graph overlays to that design.

Primary integration points: `_Step` families, `_RuntimeResolutionContext`, `_Coordinator`, `_RuntimeOwner`,
`_CompiledDecorator`, `_CompiledPreConfiguration`, providers, public `Scope.resolve*` fast paths, proposed
`instrumentation.py`, optional `ext/opentelemetry`, and new instrumentation tests/benchmarks.

## Proposed model and API

- Reuse/refine `Instrumentation`, `ActivationObserver`, `ActivationEvent`, and `ActivationEventKind` from the proposal.
- Add `RecordingSession` with explicit event/memory limits and `ObservationReport` with recording scope, sampling,
  dropped-event counts, and graph correlation metadata.
- Add `ComponentObservation`: activation count, errors by type, cache hits, cache waits, construction durations,
  initializer activity, cleanup activity, and optional per-phase aggregates.
- Add `ActivationCoverage`: observed compiled occurrences and deferred targets in one named test/recording session.

Proposed usage:

```python
recorder = RecordingSession(max_events=100_000)
container = builder.build(instrumentation=Instrumentation(observer=recorder))
# Application/test execution occurs here.
report = recorder.report()
overlay = container.graph.with_observations(report)
```

Reports use a complete correlation catalog, including unmarked public roots and private/deferred targets. Do not rely
only on the default entry-point-focused fingerprint, which can omit observed nodes. Pair a full structural manifest
fingerprint with a redacted path/catalog description; values and runtime identities do not belong in this catalog.

## Implementation stages

### 1. Define correlation and event semantics

- [ ] Reuse 01 semantic paths and 02 sharing groups while keeping calling occurrence and actual activation owner
  distinct. One shared step must not be attributed arbitrarily to whichever graph path was enumerated first.
- [ ] Resolve shared initializers, provider roots, and anchored singleton correlation during compilation; pass an
  observed call-site context only through instrumented execution where dynamic attribution is required.
- [ ] Define balanced start/finish semantics for success, failure, cancellation, and retry. Distinguish attempted,
  completed, and failed activation counts.
- [ ] Measure constructor/factory body time separately from inclusive dependency-resolution duration and coordinator
  wait time. Define async-generator acquisition and cleanup boundaries explicitly.
- [ ] Use private or recording-local event sequence/correlation numbers when concurrent operations must be paired.
  They must be newly generated observation identifiers, never object IDs, scope IDs, owner tokens, or cache keys.
- [ ] Sample once per top-level resolution/provider call and propagate the decision through its observed execution.
  Owner cleanup is a separate observation operation because it may occur much later.

### 2. Emit separate observed execution plans

- [ ] Keep existing uninstrumented `_Step` implementations, root cache-hit fast paths, and ordinary scope creation free
  of observer branches, wrappers, timers, correlation IDs, and event allocation.
- [ ] Select observed step/runtime entry-point implementations at build time. Cover root cache-hit fast paths as well
  as nested step execution; otherwise common singleton/scoped hits would disappear from reports.
- [ ] Instrument constructors/factories, decorators, pre-configurations, providers/maps, collections, cache hits,
  coordinator waits, and finalizer execution without changing ordering, cache identity, or cancellation semantics.
- [ ] Root-owned singleton/initializer observation policy belongs to its declaring owner. Ordinary scopes inherit it.
  Initially require compatible instrumentation for overlays that anchor parent steps; reject conflicting overrides
  clearly instead of silently changing parent observation or promising a disabled path that still emits events.
  This refines the older proposal's unrestricted overlay override idea and must be documented there when implemented.
- [ ] Keep event observers outside the component graph and selection/filter systems.

### 3. Bound recording and isolate observer failures

- [ ] Implement bounded recording with explicit drop/sampling counters and deterministic aggregation from captured
  events. Do not label sampled counts as total application counts.
- [ ] An observer or sampler error must not fail application activation, swallow application exceptions, or alter
  cleanup. Disable/log the faulty observer using a documented bounded policy without serializing event secrets.
- [ ] Avoid retaining component instances, request objects, traceback frames, or original trace contexts until owner
  cleanup. Precompute safe static correlation metadata where possible.
- [ ] Support streaming observers; in-memory recording is optional, not a required production sink.
- [ ] Compute exact percentiles only for retained complete samples, or label bounded histogram/sketch estimates.
  Distinguish absent samples from a measured zero duration.

### 4. Produce graph overlays and activation coverage

- [ ] Aggregate by occurrence and by sharing group, preserving distinction between activation location and cache-hit
  consumers. Show recording interval/scope, sampling, errors, and incomplete capture on every report.
- [ ] Join only to a matching graph/catalog. Reject mismatched artifacts; require an explicit semantic correspondence
  operation for cross-build comparisons instead of assuming equal type names imply equal wiring.
- [ ] Render annotated text/JSON and Mermaid views with selectable duration/count/failure layers. Base graph and its
  fingerprint remain unchanged by observation data.
- [ ] Add test-session coverage showing observed entry points, eager nodes, and deferred targets. "Not observed" does
  not mean dead code, and activation coverage is not method/branch coverage of application implementations.
- [ ] Add an offline CLI report command accepting explicit graph and observation artifacts. It must not execute the
  application just to render a recording; malformed/mismatched input returns exit code 2.

### 5. Optional OpenTelemetry adapter

- [ ] Add an optional packaging extra and adapter for resolution, activation, initializer, and cleanup spans, with
  cache/wait events or appropriate duration spans. Reuse the core event contract.
- [ ] Respect the caller's tracing context without installing global providers/exporters. Keep cleanup in separate
  operations and avoid retaining original request contexts on long-lived instances.
- [ ] Export only safe type/path/lifespan/kind metadata and exception type by default. Messages/stacks, configured
  arguments, map keys, slot values, callback closure state, and runtime IDs are excluded.
- [ ] Control high-cardinality attributes and event volume through filters, sampling, and documented exporter policy.

## Verification

Test sync/async success and failure, cancellation, retry, zero/one/many observers as supported, root fast cache hits,
concurrent singleton/scoped winners and waiters, nested scopes, compatible/incompatible overlays, shared initializers,
decorators, provider calls/maps, and cleanup exception aggregation. Ensure observer errors never mask application errors.

Verify event pairing and attribution where multiple occurrence plans share a cache or executable step. Test bounded
buffers, sampled recordings, incomplete events, catalog mismatch, unmarked roots, private/deferred targets, and
same-type registrations. Inspect reports recursively for forbidden values and identities. Adapter tests should use
local test exporters without installing a process-global provider.

Inspect uninstrumented plans and benchmark build time, cold activation, cache hits, scope creation, and allocations
separately from observed-mode overhead. Preserve the existing normal execution path structurally; record measurements
without claiming zero overhead for enabled instrumentation or conclusive timing on a noisy machine.

## Acceptance criteria

- Observations correlate to the correct compiled occurrence/owner and distinguish construction, waiting, and hits.
- Disabled instrumentation does not add work to the ordinary execution path.
- Recording is bounded, failures are isolated, redaction holds, and cancellation/cleanup semantics are unchanged.
- Overlays and coverage reports remain explicitly observational and cannot mutate compiled facts or fingerprints.
- Core functionality works without OpenTelemetry installed; the optional adapter follows the same event semantics.
