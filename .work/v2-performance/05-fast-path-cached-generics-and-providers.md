# 05 — Fast-path cached generic roots and provider calls

Created: 2026-11-18  
Status: Complete (keep)\
Priority: P2 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: `/root/v2_item05` (`gpt-6.2-sol`, high reasoning)\
Independent review: `/root/v2_item05/review` (`gpt-6.2-sol`, high reasoning)

## Outcome

Return existing singleton and scoped instances from eligible generic-root and ordinary-provider requests without allocating a resolution context, its empty cache, and its activation stack. Preserve the behavior of uncached resolution and all lifetime boundaries. Apply the [common implementation and completion criteria](README.md).

## Evidence

The local CPython 3.14.4 prototype used nine alternating before/after pairs, per-variant warmup, and normal garbage collection. Median cached singleton lookup improved from 1.146 to 0.835 µs for `Repo[int]` (27%); synchronous provider invocation improved from 0.416 to 0.270 µs (35%); asynchronous provider invocation improved from 0.491 to 0.296 µs (40%). Known generic keys already bypass alias normalization: unnecessary context creation and dispatch are the opportunity.

The avoided context, dictionary, and list total 184 bytes by shallow object sizing on this interpreter. This is allocation churn, **not retained-memory savings**. These exploratory monkeypatch measurements establish a candidate, not application throughput or cross-version guarantees. See the [probe](../../.benchbro/v2-perf-review/runtime_probe.py) and [raw results](../../.benchbro/v2-perf-review/runtime_probe_results.json); only the generic/provider rows belong to this item.

## Scope and guardrails

Inspect `Scope.resolve`, `Scope.resolve_async`, `_FrozenProvider.__call__`, `_FrozenAsyncProvider.__call__`, and existing cached registration steps. Extend eligible cache-hit paths while retaining sync-support checks, scope closure errors, singleton-owner closure checks, inherited scoped lookup, and current cache identity rules.

Unknown aliases, collection-shaped requests, custom filters, misses, observed/profiling execution, and special provider forms must retain appropriate existing paths. Do not accidentally reuse per-resolution or transient values. Include existing ordinary-class cache-hit paths when checking closure consistency: an optimization must never return a cached singleton from a closed owner.

This item is independently startable. Coordinate edits to the shared runtime module with item 06; there is no implementation dependency or required shared abstraction.

## Acceptance criteria

- [x] Eligible sync and async generic/provider cache hits avoid resolution-context allocation.
- [x] Closed scopes and closed singleton owners reject access with the established errors.
- [x] Alias, filter, collection, decorator, inherited-scope, and profiling behavior remains correct.
- [x] Cold activation, failure/retry, and concurrent singleton initialization preserve lifetime semantics.
- [x] Repeated measurements demonstrate the intended gains without material ordinary-class or miss-path regressions.

## Validation workloads

Exercise warm and cold ordinary/generic singleton and scoped roots; sync/async providers; nested scopes and closed ancestors; custom filters, aliases, and collection requests; profiled execution; transient and per-resolution controls. Run relevant lookup/provider/lifetime tests and repeat isolated timings with identical environments, warmups, and allocation measurements separated from timing.

## Implementation

Default non-collection root requests use the existing root selector before checking the
cache. Ordinary provider calls use their existing frozen target. A shortcut requires an
exact ordinary singleton or scoped step. Singleton hits check the runtime owner, including
the existing ordinary class path, and scoped hits use the existing inherited lookup.
Sync entry points check whether the target supports sync resolution before returning a
cached value. Misses still activate through the compiled step and its coordinator.

Custom filters and collection dispatch retain their existing selection and execution.
Unknown aliases still go through normal canonicalization. Observed providers and scopes,
managed and per-call providers, and the transient and per-resolution lifetimes retain
their established resolution behavior.

## Measurements

The baseline is `74c07b2ce2f128e09aa0648f04df4451662bb1b8`, which includes
items 01–03 and the existing local CI, legacy alias compatibility, and project
configuration edits. The baseline and final candidate ran from separate package
snapshots with the same lockfile on CPython 3.14.4 on macOS ARM64, BenchBro 1.0.0,
typetoolbox 0.4.0 and funcie 0.2.0. Garbage collection was enabled. Three alternating
process pairs each used two warmups and nine repeats, with 20,000 warm calls or
256 first calls on fresh owners per repeat. The async collection control used 2,000
calls per repeat. Compilation, cache priming, and construction or cleanup of cold
owners and their provider handles were outside the measured intervals. A warm provider
batch included one handle lookup. Reported values are medians of run medians.

| Warm call | Sync baseline → final, ns | Async baseline → final, ns |
| --- | ---: | ---: |
| Ordinary singleton root | 286 → 287 | 327 → 335 |
| Ordinary scoped root | 350 → 325 | 393 → 376 |
| Closed generic singleton root | 1,132 → 900 | 1,268 → 945 |
| Closed generic scoped root | 1,126 → 929 | 1,258 → 975 |
| Ordinary singleton provider | 406 → 216 | 487 → 259 |
| Ordinary scoped provider | 404 → 246 | 486 → 287 |
| Closed generic singleton provider | 408 → 217 | 485 → 255 |
| Closed generic scoped provider | 402 → 245 | 480 → 289 |

Warm generic roots saved 0.20–0.32 µs per call and ordinary provider calls saved
0.16–0.23 µs. Every process pair agreed on the direction for those workloads.
An early shared helper slowed ordinary warm roots by 6–19% in exploratory comparisons.
The final implementation checks the cache directly at each entry point. An isolated
comparison using just the closed-owner fix cost 10–13 ns for warm ordinary singleton
calls. The final change measured between −1 and +6 ns for the same calls across
the container and its ordinary child when measured in the isolation fixture.

Warm sync and async collection latency moved by less than 1%, and filter,
alias, provider-handle and transient-root latency improved by 0–5%. The
transient provider control rose from 992 to 1,027 ns and the per-resolution
provider from 1,076 to 1,097 ns. These calls incur the eligibility check.

Cold synchronous provider controls measured 0.5–2.5% slower in the mixed
workload and 3.9–6.2% slower in the fresh-owner isolation runs, as much as
0.19 µs per call. In the mixed workload the cold scoped generic sync root was
7.0% slower by run medians, with individual pairs ranging from 6.1% faster to
10.1% slower. The fresh-owner setup for each individual case measured a 4.4%
cost (0.18 µs) for that root. These misses each incur an additional cache probe.

Cold async results depended on measurement cadence. The mixed workload reported
−0.3% to +4.5% across trivial provider misses. Cold-only BenchBro reruns showed
20–25% slowdowns on generic async providers and a 7.6% slowdown on the
representative async provider in the fresh-owner isolation setup. A final
targeted diagnostic used a continuous event loop per process, three alternating
process pairs, and 17 batches of 800 fresh owners after warmup. It prepared each
batch and collected garbage before timing. Wall and process CPU time agreed.

| Cold async call | Direct baseline → final wall time, µs |
| --- | ---: |
| Ordinary singleton root | 3.68 → 3.67 |
| Ordinary scoped root | 3.71 → 3.64 |
| Closed generic singleton root | 4.56 → 4.50 |
| Closed generic scoped root | 4.50 → 4.43 |
| Closed generic singleton provider | 3.48 → 3.56 |
| Closed generic scoped provider | 3.45 → 3.55 |
| Route index provider | 9.83 → 9.88 |

The route index activates a configuration singleton, parses a short JSON document
and indexes routes by name. The sync variant measured 7.76 → 7.61 µs in the
mixed workload and 7.67 → 7.90 µs in the fresh-owner isolation setup. Its
direct async pairs ranged from 4.8% faster to 1.7% slower in process CPU time.
Generic async provider misses were 0.08–0.10 µs slower by wall medians. The
larger cold-only figures did not reproduce in this diagnostic.

Separately, tracing 2,000 already-warm calls gave peak extra Python allocations of
564 → 340 bytes for a sync generic root, 1,328 → 644 bytes for the async root,
368 → 184 bytes for the sync provider and 880 → 448 bytes for the async provider.
The ordinary root control stayed at 200 bytes. Post-GC deltas were 0–64 bytes.
These are per-batch peaks, including Python call frames and temporaries. Direct
tests also verify that the eligible calls skip context construction entirely.

Raw measurements, fixture scripts and source hashes are in
`.benchbro/v2-perf-05/`.

## Validation and review

Focused tests cover warm generic and ordinary singleton identity across roots and
providers, closed singleton owners and provider scopes, scoped instances backed
by inherited provisions, shared async cold initialization and retry, rejection of
sync requests after warming an async-only target, and custom collection filters.

Local `make ci` passed on macOS ARM64 for the five configured Python versions.
CPython 3.11.13 had 2,662 passes and 8 skips, 3.12.11 had 2,667 passes and
3 skips, and 3.13.5, 3.14.8 and 3.15.2 each had 2,670 passes.
Workflow lint and the strict documentation build passed. Both FastAPI 0.121.0
and 0.165.0 passed all 16 integration tests on CPython 3.12.11.

Independent review found one behavioral difference in the first candidate.
Classifying a filtered `GenericAlias` invoked its custom `__class__` descriptor
one fewer time than the baseline, changing the filter result. The final code
preserves the classification order, with a regression test in both modes.
The reviewer reran 422 focused tests, reproduced equivalent alias descriptor,
hash and equality sequences, and verified that closing an overlay rejects warm
singleton access from its live child without affecting the root container's own
singleton. No findings remained after re-review.

Keep the change. Warm generic roots and provider calls consistently save one
resolution context. Warm ordinary class performance stays within a few
nanoseconds for singleton roots in the isolated control. Cold trivial activations
and non-caching providers incur a small measurable cost. The changelog records
the optimization and the closed-singleton-owner correction.
