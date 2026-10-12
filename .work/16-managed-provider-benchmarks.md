# Managed provider measurements — 2026-10-04

CPython 3.14.4, macOS arm64, AC power. BenchBro fixed runs used 20 repeat samples and 5 warm-ups.
Each benchmark invocation batches 100 operations; values below divide batch medians by 100.
Build and fixture setup are excluded. Heavy test/review jobs were paused during measurements.
The resource cases model generator activation and finalization without external I/O or application block work.

The ordinary-path baseline uses an archive of `58b1db7`, the same interpreter/dependencies, and an unchanged
public-API benchmark module. Importing the baseline package from that archive was verified. The final managed
run includes the frozen cleanup-capability flag and all reviewed runtime fixes.

## Existing paths

Source: `benchmarks/bench_managed_provider_regressions.py` (also copied unchanged into the baseline archive).

| Operation | Baseline median µs | After median µs | Baseline CV % | After CV % |
| --- | ---: | ---: | ---: | ---: |
| Cached singleton resolve | 0.455 | 0.458 | 16.01 | 13.59 |
| Ordinary cached singleton provider call | 0.699 | 0.566 | 18.12 | 12.30 |
| Ordinary scope creation and close | 1.807 | 1.752 | 9.50 | 10.71 |
| Per-call method with scoped generator resource | 13.350 | 12.835 | 11.34 | 7.55 |

These observations show no material slowdown in the tested paths. Repeat variability prevents claiming small
improvements or establishing a precise non-regression bound. Ordinary `Scope.resolve`, `resolve_async`, `new_scope`,
ordinary frozen provider calls and the per-call proxy runtime were not changed by the managed implementation.
The benchmark excludes compilation; it makes no claim about container build cost or external resource latency.

## Final managed paths

Source: `benchmarks/bench_managed_providers.py`.

| Operation | Plain median µs | Observed median µs | Plain CV % | Observed CV % |
| --- | ---: | ---: | ---: | ---: |
| Create an unentered single-use manager | 0.302 | 0.283 | 19.75 | 27.71 |
| Resolve a managed handle | 2.870 | 6.495 | 16.39 | 17.63 |
| Sync scoped resource entry and exit | 8.262 | 24.036 | 15.53 | 15.80 |
| Cached singleton target acquisition and exit | 2.659 | 9.356 | 18.77 | 15.40 |
| Async scoped resource entry and exit | 13.589 | 37.313 | 25.41 | 18.79 |
| Ordinary cached singleton provider call (same fixture) | 0.568 | 4.072 | 28.96 | 21.60 |

Observed cases include exact counters and full duration sampling. All final managed cases were labelled noisy
by BenchBro; treat these as exploratory local costs, not latency guarantees or statistically precise rankings.
An earlier 20-repeat run also showed substantial variability (for example plain async acquisition median 21.699 µs).
The final table uses the latest reviewed implementation; the earlier result is noted only to disclose variation.

## Reproduction and artifacts

```shell
uv run benchbro run benchmarks/bench_managed_provider_regressions.py \
  --fixed --repeats 20 --warmup 5 --no-compare \
  --output-json /tmp/managed-regression-after.json \
  --output-md /tmp/managed-regression-after.md

uv run benchbro run benchmarks/bench_managed_providers.py \
  --fixed --repeats 20 --warmup 5 --no-compare \
  --output-json /tmp/managed-providers-capability-final.json \
  --output-md /tmp/managed-providers-capability-final.md
```

For the baseline, run the first module from the baseline archive with its public API probe copied into
`benchmarks/`, using the same interpreter and `PYTHONPATH` set to that archive. Capture separate `before` artifacts.
Local raw artifacts are `/tmp/managed-regression-before.{json,md}`, `/tmp/managed-regression-after.{json,md}` and
`/tmp/managed-providers-capability-final.{json,md}`. Machine-local history/baselines and raw environment identity
metadata are not committed.
