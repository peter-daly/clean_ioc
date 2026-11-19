# 06 — Fast-path fully cached asynchronous collections

Created: 2026-11-18  
Status: Declined\
Priority: P2 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: `/root/v2_item06` (`gpt-6.2-sol`, high reasoning)\
Independent review: `/root/v2_item06/review` (`gpt-6.2-sol`, high reasoning)

## Outcome

Avoid scheduling a separate asynchronous task for every collection member when every selected target already has a cached singleton or scoped value. Preserve cancellation checkpoints, ownership checks, collection ordering, and cold activation behavior. Apply the [common implementation and completion criteria](README.md).

## Evidence

A conservative CPython 3.14.4 prototype used nine alternating before/after pairs, per-variant warmup, and normal garbage collection. Resolving a one-item cached singleton collection improved from 47.35 to 16.86 µs (64%). A complete create-scope/resolve/close lifecycle using that cached singleton collection improved from 49.71 to 19.05 µs (62%). Both retained an explicit cancellation checkpoint.

The ten-item result was noisier (prototype sample range approximately 40% of its median); do not use it as primary evidence. Measurements are local microbenchmarks, not production throughput or guarantees across interpreters/event loops. The [prototype](../../.benchbro/v2-perf-review/cached_collection_probe.py) and [raw results](../../.benchbro/v2-perf-review/cached_collection_results.json) record the bounded experiment. Focused probe assertions checked cold factory task/`ContextVar` isolation and cancellation delivery on a warm hit; they do not replace regression coverage.

## Scope and guardrails

Inspect `_RuntimeResolutionContext.resolve_root_async` and the analogous `_CollectionStep.resolve_async` scheduling. Establish eligibility using exact ordinary singleton/scoped target types and confirmed cache hits for every member. Observed steps, managed collections, custom steps, missing entries, and activation-required targets must retain their appropriate execution paths.

Keep an explicit cancellation/fairness checkpoint. After yielding, preserve owner-open checks before returning cached values; do not trust only a check made before the checkpoint. Retain original `gather` behavior for cold or mixed-hit collections, including factory task identity, `ContextVar` isolation, cancellation propagation, sibling execution, and failure behavior.

Do not generalize this into sequential activation or a shortcut for every one-member collection: direct awaiting changes factory execution context. This item is independently startable. Coordinate shared-module edits with item 05 without requiring it or introducing a mandatory common helper.

## Acceptance criteria

- [ ] Only eligible, fully cached collections use the shortcut; results retain ordering and collection type.
- [ ] Warm hits still deliver cancellation and detect owner closure across the checkpoint.
- [ ] Cold/mixed collections preserve factory task isolation, context isolation, concurrency, and failure semantics.
- [ ] Profiling and managed-provider cleanup behavior remains correct.
- [ ] One-item and request-lifecycle gains reproduce; misses and mixed collections show no material regression.

## Validation workloads

Cover zero, one, and multiple members; singleton and inherited scoped caches; partial hits; async factories; cancellation and owner closure during suspension; failing siblings; repeated identities; profiled and managed collections. Measure root and dependency collections separately, including complete request lifecycles. Run relevant asynchronous resolution/provider tests and retain repeat-level timing samples.

## Candidate and measurements

The candidate checked exact singleton and scoped member steps before suspending.
It rechecked the bound scope, singleton owners and member caches after the first
yield. With all values still available, it yielded twice more to approximate the
default gather sequence. The observed, managed, per-call and custom task factory
paths used their existing scheduling. A cache entry removed during the first
yield led back to gather, so the factory still ran in a child task.

The baseline was `9fdc9b1b60187e7478aa3459697fc8c8b2dc16ce`, with accepted
items 01–03 and 05 and the existing local edits to CI, legacy alias compatibility
and project configuration. Separate package snapshots ran on macOS ARM64 with
CPython 3.14.4, Clean IoC 2.0.0rc6, BenchBro 1.0.0, typetoolbox 0.4.0 and funcie
0.2.0. Each of three alternating process pairs used two warmups and nine repeats
of 1,000 operations, with GC enabled and no allocation tracing. Containers were
built and selected caches were primed before timing. The lifecycle, cold and mixed cases included
creating and closing a fresh child per operation. Mixed rows probed one or ten
warm singleton registrations before encountering a cold scoped member.

| Workload | Root baseline → candidate, µs | Dependency baseline → candidate, µs |
| --- | ---: | ---: |
| Empty | 2.11 → 2.22 (+5.1%) | 2.72 → 2.88 (+5.6%) |
| Warm singleton | 48.46 → 45.29 (−6.6%) | 50.15 → 47.72 (−4.8%) |
| Ten warm singletons | 73.90 → 48.28 (−34.7%) | 73.57 → 49.86 (−32.2%) |
| Inherited warm scoped | 48.09 → 45.24 (−5.9%) | 48.58 → 47.23 (−2.8%) |
| Warm singleton request lifecycle | 50.43 → 47.70 (−5.4%) | 50.76 → 49.73 (−2.0%) |
| Cold scoped request | 54.76 → 56.81 (+3.7%) | 55.10 → 57.79 (+4.9%) |
| Mixed request, one hit | 57.16 → 60.55 (+5.9%) | 58.36 → 59.17 (+1.4%) |
| Mixed request, ten hits | 83.18 → 86.40 (+3.9%) | 86.50 → 87.26 (+0.9%) |
| Profiled warm singleton | 54.69 → 56.39 (+3.1%) | 58.69 → 56.38 (−3.9%) |

Values are medians of run medians. Warm singleton and lifecycle gains agreed
in direction across all three pairs but were much smaller than the exploratory
one-yield prototype. The ten-member improvement was 31–35% in each pair.
The managed acquisition control measured 7.43 → 7.64 µs, with paired increases
of 0.3–6.8% on a path unchanged by the candidate. Raw repeat samples, process
source verification, source hashes and fixture runner are under
`.benchbro/v2-perf-06/`. The benchmark fixture is included with the candidate.

## Validation and decision

Thirty focused tests passed on CPython 3.14.4. They cover both entry points,
cached ordering and identity, empty selections, inherited scoped hits, warm and
cold cancellation, bound scope and singleton owner closure, child task and
`ContextVar` isolation, concurrent siblings, profiling counters and a custom task
factory. Targeted type checking and lint passed. The independent review found
public cases outside those tests.

- The initial one-yield candidate returned a value after an already-expired
  positive `asyncio.timeout` deadline. Three yields fixed this example and ordinary
  delayed cancellations. A separate case shows that gather propagates cancellation
  even when the caller immediately retracts it. Schedule a
  callback with `loop.call_soon` immediately before a warm request. If the callback
  calls `request_task.cancel()` followed by `request_task.uncancel()`, the baseline
  still raises `CancelledError` because gather already cancelled its child. The
  three-yield candidate returns the value.
- Closing the bound singleton scope on the first loop turn and cancelling on
  the second produced `CancelledError` on the baseline and `ScopeClosedError`
  in the candidate. Closing a separate singleton owner on the first turn and
  cancelling on the fourth gave the opposite difference because the fallback
  gather started a turn later.
- At 990 ordinary nested scopes with the default recursion limit on CPython
  3.14, inherited scoped collection lookups succeeded in the baseline's child
  tasks and raised `RecursionError` in the candidate caller, at both entry
  points. The reviewer also confirmed that a custom event loop overriding
  `create_task()` directly lost its warm member callbacks.

Decline the candidate because it changes public cancellation behavior. The
representative one-member request saved 1–3 µs and cold and mixed paths incurred
additional probes. Validation stopped at the behavior failures, so the results
cover timing and focused tests on CPython 3.14.4.

## Stash record

- Stash at creation: `stash@{0}`
- Immutable stash commit: `9b21605413ffad4561481efaec30639b16dc2fe8`
- Message: `v2 item 06 declined: cached collection shortcut changes cancellation semantics`
- Contains the candidate implementation, new regression tests and benchmark fixture.
- No item 06 production changes are retained; this rejection record is committed separately.

Stash numbers can change; use the immutable commit to identify this candidate.
