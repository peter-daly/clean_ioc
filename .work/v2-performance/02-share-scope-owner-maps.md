# 02 — Share scope owner maps

Created: 2026-11-18  
Status: Complete (keep)  
Priority: P1 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: GPT-6.2 Sol (`gpt-6.2-sol`), high reasoning — `/root/v2_scope_owner_maps`

## Outcome

Reduce the allocation cost of ordinary request scopes, managed-provider acquisitions and per-call scopes by reusing their existing singleton-owner mapping. An overlay that introduces an owner must retain its own mapping. This item can start independently; follow the [common measurement and completion criteria](README.md).

## Review evidence

`Scope.__init__` currently copies `owners` for every scope, but only construction with an `owned_token` adds an entry. A process-local prototype reused the mapping when no owner was added, while retaining the copy for overlays.

On CPython 3.14.4/macOS ARM64, 1,000 simultaneously live empty scopes retained **904,856 bytes before and 720,856 bytes after**, a reduction of **184,000 bytes (20.3%)**. Three repetitions matched. The prototype passed 273 focused resource-ownership, managed-provider, per-call, execution-plan and declared-provider-root tests. These are traced Python allocations after GC, excluding parent construction; they establish neither application RSS savings nor a throughput improvement. Review probes and results are local under `.benchbro/v2-perf-review/memory_review_probe.py`, `memory_review_results.json` and `memory_share_validation.py`.

## Implementation scope and guardrails

- Change owner-map allocation in `Scope.__init__`; keep copying before adding an overlay owner. Confirm all writes remain confined to construction.
- Preserve singleton identity, declaring-owner lookup, cleanup ownership and overlay isolation. Ordinary descendants must observe the same owners as before.
- Cover normal, observed, managed-acquisition and per-call scope construction. Keep public APIs and scope lifetime rules unchanged.
- Preserve independent-child behavior after a parent closes. Do not clear caches, change provisions, replace owner references with weak references, or combine unrelated scope-storage changes.

## Acceptance checklist

- [x] Ordinary scopes preserve inherited singleton identity and scoped-cache behavior.
- [x] Sibling and nested overlays preserve separate local singletons while sharing inherited owners correctly.
- [x] Sync/async cleanup runs exactly once at the declaring owner, including activation failure and cancellation.
- [x] Managed and per-call scopes preserve their isolated scoped values and inherited provisions, with instrumentation enabled and disabled.
- [x] Repeated measurements reproduce an allocation reduction without a material scope-lifecycle regression.
- [x] Relevant behavioral tests and repository checks pass on the Python versions required by current CI.

## Validation and measurement

Measure retained and peak allocations for 1,000 concurrent empty and resource-owning scopes, with a warmed parent outside tracing. Separately measure complete create/resolve/close lifecycles and representative managed/per-call operations. Include an overlay chain to exercise multiple owner entries. Record repeat variation and unchanged-code drift; avoid asserting private dictionary identity as a substitute for behavioral coverage.

### Implementation

`Scope.__init__` reuses the incoming owner map when it has no owner token to
add. It constructs an extended copy before publishing a new overlay owner.
The map is typed as a read-only `Mapping`. Root and overlay constructors are
the only writers. Resolution and finalizer routing look up entries, scope
construction passes the mapping through, and overlay compilation reads its
keys. Ordinary and observed child scopes, managed acquisitions, and both
per-call paths get the same sharing behavior through this constructor.

### Measurement method

The fresh baseline is `3246679499590627125ea4e743e5083ac402865f`, Clean IoC
`2.0.0rc6`, including the accepted item 01 change and the existing compatibility
and CI edits. The baseline and candidate package snapshots differ only in
`clean_ioc/container.py`. Both used CPython 3.14.4, BenchBro 1.0.0, macOS
26.7.3 ARM64 and an Apple M2 Max. Runtime dependencies were funcie 0.2.0,
typetoolbox 0.4.0, and typing-extensions 4.16.0. The `uv.lock` SHA-256 was
`dbdf4ff668bcc32ab220899f2d28add11b62de86ea0dfe6adeb3bdad17a6fb79`.

Run the [benchmark and allocation probe](../../benchmarks/bench_scope_owner_maps.py)
against each version with the same executable and dependencies. Use an absolute
`source` directory containing the selected `clean_ioc` package and a distinct
`run` label for each invocation. Capture baseline and candidate runs in
alternating order, starting with the baseline.

```sh
results="$PWD/.benchbro/v2-perf-02"
mkdir -p "$results"
PYTHONPATH="$source" .venv/bin/benchbro run benchmarks/bench_scope_owner_maps.py \
  --fixed --repeats 15 --warmup 5 --no-compare --baseline v2-scope-owner-maps \
  --output-json "$results/timing-$run.json" --output-md "$results/timing-$run.md"
PYTHONPATH="$source" .venv/bin/python -P benchmarks/bench_scope_owner_maps.py \
  > "$results/memory-$run.json"
```

The allocation probe runs in a separate process. Parent declarations, compilation,
fixture warmup, and cleanup are outside tracing. Each sample keeps 1,000 ordinary
scopes alive, optionally resolving a scoped generator resource in each. It
reports retained Python allocations after a full collection and the peak up to
that point. The deeper parent is the last of five overlays, with six owner
entries including the root.

BenchBro times empty create/enter/close, and create/enter/resolve/close for a
scoped generator resource. Managed acquisition measures call, enter, activation
and exit with the same resource. The per-call benchmark invokes a prepared
operation whose activation and cleanup also use that resource. The cached
singleton control resolves directly on the root. The overlay control builds and
closes a sixth overlay, including compilation and the required owner-map copy.
Parent setup and warmup are outside timing. Each run uses 15 repeats after five
warmup invocations, with automatic GC disabled during measurement and no
allocation tracing. Each repeat contains 500 batches of 100 operations, except
the overlay control, which builds 50 overlays per repeat.

### Traced allocations

All three fresh processes per variant reproduced the following counts exactly.

| 1,000 ordinary scopes below | Retained bytes after GC, before → after | Peak bytes, before → after |
| --- | ---: | ---: |
| Root, empty | 904,832 → 720,832 (−20.3%) | 905,448 → 721,312 (−20.3%) |
| Root, resource-owning | 1,696,832 → 1,512,832 (−10.8%) | 1,699,528 → 1,515,528 (−10.8%) |
| Five overlays, empty | 992,832 → 720,832 (−27.4%) | 993,312 → 721,312 (−27.4%) |
| Five overlays, resource-owning | 1,784,832 → 1,512,832 (−15.2%) | 1,787,528 → 1,515,528 (−15.2%) |

Each simultaneously live scope saved 184 retained bytes below the root and
272 below the overlay chain in this fixture. The measurements describe traced
Python allocations. Process RSS is outside this experiment.

### Untraced timing

Three alternating before/after pairs. Each cell gives the median of the three
run medians with their minimum and maximum in brackets. Times are per operation.

| Workload | Before | After | Median change |
| --- | ---: | ---: | ---: |
| Root, empty | 1.395 µs [1.382–1.406] | 1.208 µs [1.201–1.229] | −13.4% |
| Root, resource | 5.790 µs [5.697–5.827] | 5.496 µs [5.488–5.581] | −5.1% |
| Five overlays, empty | 1.292 µs [1.275–1.296] | 1.199 µs [1.186–1.209] | −7.2% |
| Five overlays, resource | 5.602 µs [5.514–5.634] | 5.530 µs [5.516–5.552] | −1.3% |
| Managed acquisition | 5.455 µs [5.427–5.521] | 5.357 µs [5.329–5.399] | −1.8% |
| Per-call operation | 9.520 µs [9.456–9.662] | 9.323 µs [9.318–9.612] | −2.1% |
| Cached root singleton control | 0.325 µs [0.321–0.328] | 0.324 µs [0.321–0.330] | −0.1% |
| Overlay build and close control | 4.959 ms [4.876–5.121] | 5.008 ms [4.925–5.039] | +1.0% |

Baseline medians spanned 1.6–2.3% for runtime cases and 4.9% for the overlay
build control. The largest within-run coefficient of variation was 6.3%, on
one resource-scope baseline. BenchBro flagged some runs for outliers. Empty
lifecycles and the root resource lifecycle improved in all three pairs, with
disjoint before/after median ranges. The managed difference was on the scale of
baseline variation. Per-call and overlay-descendant resource timings had mixed
paired directions, as did both controls. The overlay build control includes
compilation and cannot resolve small changes in constructor cost. These runs
establish no material lifecycle regression on this fixture. Application
throughput and other interpreters are outside the timing experiment. Raw local
samples and timing reports are under `.benchbro/v2-perf-02/`.

### Validation and review

- The focused ownership, managed and typed provider, per-call, execution-plan,
  declared-provider-root, and profiling suites passed 334 tests on CPython
  3.14.4. The new cases exercise observed and unobserved singleton and scoped
  identities, overlay collection after close, inherited provisions, parent/child
  independence, and resource cleanup on ordinary, failed and cancelled paths.
- Local `make ci` passed on macOS ARM64 on every Python version configured in CI.
  CPython 3.11.13 had 2,651 passes and 8 skips, 3.12.11 had 2,656 passes and 3
  skips, and 3.13.5, 3.14.4 and 3.15.2 each had 2,659 passes. This includes lint,
  formatting, types, executable docs and benchmark discovery. The GitHub-hosted
  Ubuntu jobs were outside this local run.
- All pre-commit hooks and strict MkDocs passed. On CPython 3.12.11 the FastAPI compatibility tests
  passed 16 cases each with FastAPI 0.121.0 and 0.164.0.
- Independent review by `/root/v2_scope_owner_maps/review` found no actionable
  issues. It passed 195 focused tests and verified that an in-memory mutation
  inserting overlay entries into a shared map fails the retention test with
  profiling enabled and disabled. A separate verification probe confirmed that
  two runtimes from one overlay report share the root singleton, retain distinct
  local singletons and finalize each local singleton once, in both modes. The
  reviewer confirmed the matching measurement settings and alternating order.

Keep the change. Retained and peak allocations fell consistently across all
four scope populations. Timings show no material lifecycle regression within
the measured workloads and run variation. The changelog records the reduction
in allocation for the affected scope paths.
