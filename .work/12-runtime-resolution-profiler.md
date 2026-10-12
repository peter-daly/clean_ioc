# 12 — Runtime resolution profiler

Status: Implemented and independently reviewed (2026-09-25)  
Priority: P1  
Dependencies: 01–03 graph references, sharing, and activation semantics; 06 resource ownership proof from the V2 roadmap  
Related work: [08 runtime observations](08-runtime-observations-and-graph-overlays.md) and [11 compilation profiler](11-compilation-profiler.md)

## Outcome

Measure real runtime resolutions and activations so a developer can identify slow requests, factories that construct
often, cache contention, and expensive cleanup. An opt-in profiler reports what actually ran; it does not infer runtime
cost from the compiled graph or execute components merely to inspect them.

Illustrative output; values are examples, not measurements of Clean IoC:

```text
Checkout — 2,480 resolves, 2,480 completed, 0 failed
  Total resolve time: 4.2 s; sampled p95: 9.2 ms (248 of 2,480 timed)
  Largest measured contributor: DatabasePool cache wait, 1.4 s total

PaymentGateway → StripeGateway [factory]
  Activations: 2,480; cache hits: 0; failures: 0
  Factory body: 640 ms total across timed samples; sampled p95: 0.7 ms
```

Counts and durations have different coverage. Every activation and cache outcome is counted while profiling is enabled.
Timing may be sampled, and sampled totals and percentiles must never be presented as whole-traffic totals. A factory's
own execution time excludes dependency construction, coordinator waiting, and cleanup.

## Relationship to existing plans

This is the first useful runtime diagnostic slice of [08](08-runtime-observations-and-graph-overlays.md) and the older
[graph-correlated activation tracing proposal](../.v2_roadmap/08-graph-correlated-activation-tracing.md). Item 12 owns
the initial opt-in runtime execution hooks, safe correlation catalog, bounded in-process aggregation, and text/JSON
reports. Item 08 can extend those same hooks and identities with retained event streams, graph overlays, activation
coverage, offline inspection, and an optional OpenTelemetry adapter. Do not implement a second observer/event model.

The implemented `CompilationProfiler` and `build(profile=...)` from item 11 measure `build()` only. Runtime profiling
uses a distinct `instrumentation=` build option and a distinct collector; both options may be supplied together.

## Proposed public API

Add `Instrumentation` and `ResolutionProfiler` (names provisional) in `clean_ioc.instrumentation`:

```python
from clean_ioc.instrumentation import Instrumentation, ResolutionProfiler

runtime_profile = ResolutionProfiler(sample_durations=0.1)
container = builder.build(
    instrumentation=Instrumentation(profiler=runtime_profile)
    if enable_runtime_profiling else None,
)

# Exercise the application normally, then inspect a snapshot.
print(runtime_profile.report().to_text())
```

`ContainerBuilder.build()` and `ScopeBuilder.build()` gain an independent optional `instrumentation` keyword. The
application's configuration can set `enable_runtime_profiling` at its composition root. Do not interpret a magic
`build_args` key inside Clean IoC: build arguments currently participate in composition callbacks, while this option
selects runtime observation. Passing both remains legal and neither profiler changes graph fingerprints.

`ResolutionProfiler.report()` returns an immutable snapshot while the container is running or after it closes. A
report identifies its full compiled graph/catalog, recording interval, enabled mode, sample coverage, and any dropped
detail. It supports `to_text()` and `to_json()`; raw runtime object IDs and configured values are never exported.
Reporting is read-only and does not require closing the container or replaying requests.

No CLI command should build a target and claim it profiled application traffic. A later offline CLI can render a saved
runtime report and matching graph; that belongs to item 08. Item 12 documents programmatic setup and report export.

## Metrics and attribution

- **Top-level requests:** count attempted, completed, failed, and cancelled `resolve`, `resolve_async`, provider, and
  provider-map calls. Report sampled inclusive wall time, not time inferred from children.
- **Actual activation:** count attempts, completed constructions, and failures for each component, constructor,
  registered factory, generator/context-manager acquisition, decorator, and pre-configuration. Count cache hits and
  misses separately. A cached singleton activated once and resolved 1,000 times has one construction, not 1,000.
- **Time categories:** separate inclusive resolution time, component dependency time, constructor/factory body time,
  cache-coordinator wait time, pre-configuration, and finalizer/cleanup time. State exactly which nested durations can
  overlap; do not sum inclusive parent and child times into a claimed total.
- **Owners and paths:** aggregate by exact graph occurrence and by underlying registration/sharing group. Attribute
  activation to the owner/step that actually ran, while retaining the calling path for cache hits and waits. Avoid
  multiplying one shared initializer or anchored singleton activation across graph occurrences.
- **Rankings:** allow sorting by activation count, total measured factory self time, slow sampled requests, cache
  waits, and failure count. Every ranking states whether it uses exact counts or sampled durations.
- **Cleanup:** record owner close as a separate operation because it can happen long after a resolve. Track cleanup
  failures without attaching a prior request's context to a long-lived object.

The first version measures dependency activation and cleanup for `scope="per_call"`; time spent executing an
application service method is identified separately or excluded, so business work is not labelled as DI cost.

## Execution and recording design

### 1. Select observation at build time

- [x] Compile a separate observed set of lifespan-specialized steps and root entry points only when
  `instrumentation` is provided. Disabled `resolve*`, provider calls, cached-root fast paths, and ordinary `new_scope()`
  gain no observer branch, clock read, correlation allocation, or graph traversal.
- [x] Bind safe semantic occurrence references to observed steps during compilation. Use the all-roots graph catalog
  so private, unmarked, deferred, and provider-map targets can be correlated. Keep observation metadata out of normal
  manifests, fingerprints, selection, and injected services.
- [x] Build-time validation rejects malformed instrumentation. A build that fails compilation must not leave an
  apparently usable runtime profile; compilation timing remains item 11's concern.
- [x] Ordinary child scopes inherit the root plan and profiler. For overlays anchored to parent singleton/initializer
  steps, require compatible instrumentation or fail clearly before returning a runtime. Do not silently profile only
  part of an inherited owner or promise to turn off an already observed parent step.

### 2. Count all observed work; sample timing

- [x] Count every enabled top-level call, actual activation, cache hit/miss, coordinator wait, and failure. Make these
  counters independent of the timing sampler. Count a failed attempt once and a later retry as a new attempt.
- [x] Decide whether to time a top-level request once and propagate that choice through its nested observed steps.
  On-demand provider calls begin their own top-level operation. Cleanup uses its own timing choice.
- [x] Use a monotonic clock only for timed operations. Support sync and async activation, concurrent waiters, nested
  provider calls, cancellation, and reentrant resolution without mixing timing stacks or double counting.
- [x] Label the number of timed samples for every duration metric. Use bounded histograms/sketches for percentiles and
  label them approximate; exact percentiles are allowed only for a fully retained bounded sample set. A missing timed
  sample is not a measured zero.
- [x] Keep exact aggregate counters and fixed-size timing summaries bounded by compiled graph references. Bound any
  optional detailed examples separately, with explicit omitted counts. Avoid storing instances, arguments, traceback
  frames, per-request contexts, or unbounded event lists.

### 3. Keep errors and overhead controlled

- [x] Preserve activation, caching, cleanup, exception, and cancellation behavior with profiling enabled. A profiler
  recording failure must not mask or replace an application exception; disable faulty recording under a documented
  bounded policy and mark the resulting report incomplete.
- [x] Ensure thread/task-safe counters and interval snapshots without inventing a total order for concurrent async
  collections. Snapshot creation must not hold locks while calling application code.
- [x] Exclude exception messages/stacks, build-input names/values, configured/provided values, map keys, callback
  representations, owner tokens, runtime IDs, and arbitrary `repr()` output from text/JSON. Exception type may be
  included only through a safe qualified-type label.
- [x] Benchmark disabled and enabled cold resolves, cached singleton/scoped hits, provider calls, scope creation,
  and cleanup separately. Record the timing and allocation overhead without assuming an enabled profiler is free.

### 4. Ship useful reports

- [x] Return stable, bounded report records for roots, component occurrences, registration/sharing groups, and
  cleanup owners. Reports distinguish compiled facts from measured activity and label unobserved branches as
  "not observed" rather than unreachable or unused.
- [x] Provide text/JSON views showing the most frequently constructed factories and the largest measured sources of
  resolution latency. Show cache waits and hits alongside activation counts to explain repeated resolves.
- [x] Allow a report snapshot during live traffic; specify whether in-flight operations are excluded or shown
  separately. Include sample and incomplete-recording metadata in each report and safe graph identity for later joins.
- [x] Document a development and production configuration example using an application variable passed to
  `instrumentation=`. Make clear that `profile=` still means compilation profiling.

## Verification

Test transient versus singleton construction counts, warm root cache fast paths, per-resolution and scoped caches,
constructor versus factory self time, nested dependencies, decorators, pre-configurations, generators/context managers,
provider calls/maps, shared initializers, and per-call scope activation/cleanup. Include same-type registrations,
aliases, closed generics/patterns, boundaries, and anchored overlays.

Exercise sync/async success and failure, cancellation, concurrent singleton/scoped winners and waiters, retry after a
failed activation, owner close and cleanup exception aggregation, sampling at zero and full rates, live report snapshots,
and bounded detail overflow. A controllable clock should verify timing categories and nested accounting without
asserting wall-clock thresholds. Instrumentation failures must leave application results and exceptions unchanged.

Inspect disabled runtime paths for clock, observer, context, and allocation work. Verify deterministic serialization of
the same captured report, a safe full-graph catalog reference, accurate exact-versus-sampled labels, and recursive redaction
with sentinel secrets and objects whose representation raises. Compare cache identity and cleanup order with and without
profiling. Run appropriate performance measurements with results described as observations.

## Acceptance criteria

- An enabled container can report which roots resolve slowly and which factories actually construct most often.
- Exact activation/cache/failure counts remain separate from sampled duration estimates, including under concurrency.
- Factory self time, dependency time, cache waiting, and cleanup are distinguishable without double counting.
- Reports correlate to the compiled graph while respecting shared owners, boundaries, and overlays.
- Profiling is opt-in at build time; the disabled runtime path remains free of profiling work.
- Recording is bounded, safe to inspect live, redacted, and unable to change application outcomes.

## Implementation record (2026-09-25)

`clean_ioc/instrumentation.py` provides the collector and immutable report. `clean_ioc/container.py` compiles observed
step variants only when `instrumentation=` is supplied; ordinary `Scope.resolve*`, provider handles, cached root paths,
and `new_scope()` retain their original classes and behavior. `docs/runtime-profiling.md` has the executable public API
example. `tests/test_resolution_profiler.py` covers exact cache/activation counts, async contention, cancellation,
retry, pre-configuration, decorators, provider maps, per-call activation, cleanup, overlays, redaction, sampling,
and failed instrumentation clocks. A separate Sol Extra High review found and verified fixes for shared-step,
shared-initializer, overlay-first, collector-binding, and cleanup attribution. The reviewer signed off after the
focused profiler suite passed 31 tests.

The bounded catalog uses the all-roots graph fingerprint and the compiled sharing references. Activation stays on the
step that ran. Observed-only call-site wrappers attribute cache outcomes to the actual compiled edge for nested
dependencies, collections, deferred providers, declared resolution requests, per-call targets, and shared
pre-configurations. Concurrent initializer waiters count both a cache miss and a coordinator wait. An unmatched edge
uses an explicit `[cache caller unresolved]` fallback; it does not imply all candidate callers ran. Event streams,
graph overlays/coverage, offline CLI rendering, and OpenTelemetry remain in item 08 rather than this slice.

Local measurements from `uv run python benchmarks/bench_resolution_profiler.py` on Darwin arm64/Python 3.14 (median
of five rounds, 2026-09-25) were:

| Operation | Disabled | Enabled | Ratio |
| --- | ---: | ---: | ---: |
| Build | 2,648,020 ns | 7,525,308 ns | 2.84× |
| Cold transient resolve | 1,303 ns | 7,239 ns | 5.55× |
| Cached singleton hit | 281 ns | 3,700 ns | 13.18× |
| Cached scoped hit | 336 ns | 3,706 ns | 11.04× |
| Provider call | 406 ns | 3,233 ns | 7.96× |
| New scope | 915 ns | 926 ns | 1.01× |
| Cold scoped acquire and cleanup | 6,224 ns | 17,078 ns | 2.74× |
| Cold scoped acquisition | 4,284 ns | 19,948 ns | 4.66× |
| Prepared scope cleanup | 1,077 ns | 5,387 ns | 5.00× |

Approximate peak traced bytes per operation over 1,000 calls were cached hit 0.3 disabled/1.8 enabled, and new scope
16.5 disabled/16.5 enabled. These measurements are local observations, subject to machine noise and tracing overhead;
the enabled profiler has substantial cost on the shortest hot paths. The disabled runtime path was also inspected:
its existing step classes, `Scope.resolve*`, provider handles, and `new_scope()` do not call the collector or clock.
Final checks passed: `uv run pytest -q` (911 tests), `uv run ruff check .`, `uv run ty check .`,
and `uv run python scripts/validate_docs_examples.py`. The three new Python files are Ruff-formatted. The pre-existing
`clean_ioc/container.py` also contains the earlier items 09–11 changes, so it was not reformatted wholesale as part
of item 12; Ruff lint and ty pass for the complete file.
