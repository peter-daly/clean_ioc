# 01 — Allocate profiling histograms on demand

Created: 2026-11-18  
Status: Complete (keep)  
Priority: P1 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: GPT-6.2 Sol (`gpt-6.2-sol`), high reasoning — `/root/v2_profiler_histograms`

## Outcome

Optional runtime profiling should retain duration storage only for metrics that
have actually received a timed sample. Counts-only profiling and unobserved
catalog entries must remain inexpensive while producing the same complete public
reports, exact counters and duration summaries.

## Review evidence

`_MutableRecord` eagerly allocates eight lists of 67 integers for every record.
With 100 unrelated singleton services, default provider roots and
`ResolutionProfiler(sample_durations=0)`, the review captured 40,003 records and
320,024 entirely zero histogram lists. Those lists alone occupied 192,014,400
bytes; traced retained build allocations were 225,202,738 bytes.

A temporary prototype deferred the 64 histogram buckets until their first use.
Retained allocations fell to 61,345,049 bytes, approximately 73% lower, and all
31 existing profiling tests passed. This was a bounded allocation experiment,
not a production implementation or a timing result. Its list-subclass mechanism
is not a required design; avoid adding costly indirection to sampled updates.

## Scope and guardrails

Choose the simplest sparse or lazy representation that preserves counter updates,
snapshot aggregation and sampled histograms. Treat missing duration storage as
an immutable zero value when reading; allocate private mutable storage on the
first timed update. Reading or merging a report must not populate live zero
histograms simply because all catalog entries are included.

Keep unused records visible, including their existing zero-sample summaries.
Do not reduce catalog coverage, conflate missing samples with measured zero
duration, change sampling policy, or share mutable buckets between records.
Preserve thread-safe snapshots and the collector's failure isolation. Ordinary
uninstrumented resolution must gain no observer work.

## Acceptance criteria

- [x] Counts-only collection and repeated snapshots avoid full zero histograms,
  including registration-group and cache-group aggregation.
- [x] First and subsequent samples preserve totals, maxima, bucket boundaries
  and approximate p95; zero, partial and full sampling behave correctly.
- [x] Independent records, executions and compatible overlays cannot contaminate
  each other's counters or duration storage.
- [x] Reporting preserves catalog entries, exact counts, serialization and
  snapshot immutability before activation, after resolution and after cleanup.
- [x] Concurrent recording/reporting and recording failures preserve existing
  thread-safety, incomplete-state and application-continuation behavior.
- [x] Repeated measurements confirm lower memory for the review workload and
  establish update/report timing for counts-only, partial and full sampling,
  with an uninstrumented control and a densely sampled workload.

## Implementation

Each profiler record keeps a sparse metric dictionary. The first timed update
creates a private fixed-size histogram under the existing collector lock. Later
updates still use direct dictionary indexing. Snapshots use immutable zero
summaries for missing metrics and preserve all eight duration fields. Registration
and cache groups merge sampled metrics using their own bucket arrays. They keep
empty groups and merge exact counters even when every duration is absent.
Changes are confined to opt-in instrumentation.

## Measurements

Fresh baseline `3246679499590627125ea4e743e5083ac402865f`, Clean IoC `2.0.0rc6`,
with the existing CI, compatibility, and work-list edits present. The eager and
sparse runs used the same declarations and dependencies on an Apple M2 Max,
macOS 26.7.3 ARM64, CPython 3.14.4 and BenchBro 1.0.0. Installed runtime
dependencies were funcie 0.2.0, typetoolbox 0.4.0 and typing-extensions 4.16.0.
The `uv.lock` SHA-256 was
`dbdf4ff668bcc32ab220899f2d28add11b62de86ea0dfe6adeb3bdad17a6fb79`.

Use [the benchmark and allocation probe](../../benchmarks/bench_profiler_histograms.py)
from the candidate workspace. Run the same commands against each source tree in
alternating order, keeping the executable and dependencies fixed. Set `source`
to the absolute path containing the selected `clean_ioc` package, and `run` to
a distinct label for each invocation.

```sh
results="$PWD/.benchbro/v2-perf-01"
mkdir -p "$results"
PYTHONPATH="$source" .venv/bin/benchbro run benchmarks/bench_profiler_histograms.py \
  --fixed --repeats 15 --warmup 5 --no-compare --baseline v2-profiler-histograms \
  --output-json "$results/timing-$run.json" --output-md "$results/timing-$run.md"
PYTHONPATH="$source" .venv/bin/python -P benchmarks/bench_profiler_histograms.py \
  > "$results/memory-$run.json"
```

### Traced Python allocations

Values are medians across three fresh processes per variant, in decimal MB.
Tracing starts after declarations and a collection. Measurements include build
and its context entry, then two resolves per service, then a snapshot for the
small profiled cases. No child scopes are created. Cleanup runs after tracing.
Each peak is measured separately for its phase and includes live allocations
from prior phases. Retained values are taken after garbage collection.

| Workload and endpoint | Retained MB, eager → sparse | Phase peak MB, eager → sparse |
| --- | ---: | ---: |
| 100 singletons, default provider roots, counts only, build | 225.21 → 24.89 | 228.95 → 28.62 |
| Same, after resolving all services | 225.27 → 24.95 | 225.28 → 24.95 |
| 8 singletons, default provider roots, counts only, holding one report | 22.65 → 2.70 | 23.95 → 2.80 |
| Same, after discarding the report | 18.18 → 2.14 | 22.65 → 2.70 |
| 8 transients, no automatic provider roots, uninstrumented, after resolves | 0.052 → 0.051 | 0.053 → 0.053 |
| Same transients, fully sampled, after resolves | 0.786 → 0.150 | 0.789 → 0.153 |
| Same fully sampled transients, holding one report | 0.969 → 0.193 | 1.015 → 0.213 |

The large counts-only workload retained all 40,003 records and went from
320,024 zero histograms to zero histogram arrays. Retained build allocation fell
89.0% and peak fell 87.5%. The fully sampled transient fixture exercised all
eight services and populated 32 histograms across 131 compiled records. The
uninstrumented control's small allocation differences varied between runs.
These numbers measure traced Python allocations, without process RSS.

### Untraced timing

Three alternating eager/sparse pairs, each with 15 repeat samples and five warmup
invocations. Each update repeat runs 500 batches of 16 resolutions, two per
service. Each report repeat runs three `report()` calls. Fixture setup, initial
resolutions, and teardown are outside timing. Reports exclude JSON/text rendering.
Each cell is the median of the three run medians.

| Workload | Duration sampling | Resolve µs per call, eager → sparse | Report ms, eager → sparse |
| --- | --- | ---: | ---: |
| Cached singleton, default provider roots | Uninstrumented | 0.324 → 0.323 | — |
| Cached singleton, default provider roots | 0% | 3.457 → 3.456 | 96.406 → 6.886 |
| Cached singleton, default provider roots | 50% | 3.681 → 3.685 | 98.113 → 6.864 |
| Cached singleton, default provider roots | 100% | 3.945 → 3.931 | 97.753 → 6.910 |
| Transient, no automatic provider roots | Uninstrumented | 1.255 → 1.254 | — |
| Transient, no automatic provider roots | 0% | 5.067 → 5.027 | 3.190 → 0.234 |
| Transient, no automatic provider roots | 50% | 6.098 → 6.105 | 3.165 → 0.327 |
| Transient, no automatic provider roots | 100% | 6.972 → 7.037 | 3.134 → 0.326 |

Snapshot medians fell 89.6–93.0% across both workload shapes. Warmed resolve
medians moved between −0.8% and +0.9%. Some update repeats were noisy, with a
maximum CV of 39% in an eager half-sampled singleton run. Fully sampled transient
run medians overlapped (6.658–7.136 µs eager and 6.897–7.052 µs sparse). The
timings do not establish a steady-state update speedup or penalty. First-sample
allocation now happens during recording, outside the warmed update measurement.
Raw local reports are under `.benchbro/v2-perf-01/`.

## Validation and review

- 35 focused profiler tests passed, including counts-only lifecycle and JSON,
  bucket/p95 boundaries and independent group merges, partial sampling, distinct
  runtimes and overlays, concurrent first samples, and recorder failure isolation.
- Local `make ci` passed on macOS ARM64 for every configured Python version.
  Python 3.11.13 had 2,643 passes and 8 skips, 3.12.11 had 2,648 passes and 3
  skips, and 3.13.5, 3.14.4 and 3.15.2 each had 2,651 passes. This includes
  lint, format, type checks, executable documentation, and benchmark discovery.
  The GitHub-hosted Ubuntu workflow was outside this local validation.
- All pre-commit hooks and the strict MkDocs build passed. The FastAPI minimum
  lane (0.121.0) and the latest available lane (0.164.0) passed 16 tests each on
  Python 3.12.11.
- Independent review by `/root/v2_profiler_histograms/review` found no actionable
  issues. The reviewer matched baseline and candidate report data for 701 mixed
  updates at each of 0%, 37%, and 100% across two executions, and injected a
  first-histogram `MemoryError` during a real resolution. The application
  continued with its cached singleton and the profile marked itself incomplete.

Keep the implementation. The measured memory and snapshot improvements hold
across repeated runs, with warmed update differences inside observed variation.
The runtime profiling guide and changelog document the allocation behavior.
