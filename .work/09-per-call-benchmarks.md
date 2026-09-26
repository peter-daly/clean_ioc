# Per-call scope benchmarks

Measured 24 September 2026 on CPython 3.14.4, macOS ARM64, battery power, with BenchBro 1.0.0. Runs were sequential, using the same interpreter and dependency lock. The ordinary-code baseline was freshly measured from an isolated checkout of `d61505b`; the comparison is the working tree containing the completed per-call implementation.

Per-call handling adds approximately **0.74–0.90 µs per operation** over the equivalent handwritten wrapper in this small workload. Ordinary resolution shows no clear material regression; the latest repeat moved +0.7–2.8% while the direct-Python control moved +1.9%. Ordinary build measurements stayed within ±0.6%.

## Per-call versus a handwritten scope wrapper

Each operation opens a fresh scope, constructs one scoped service and one generator-managed scoped dependency, calls a method, and closes the scope. Both variants retain their wrapper/handle between calls. Parent scopes are unwarmed, so ordinary child-scope inheritance does not reuse resources. Async activation and cleanup are included, with no external I/O.

Runtime measurements batch 100 operations per benchmark invocation to amortize runner overhead. The values below divide reported batch times by 100. Container construction and handle acquisition are excluded from runtime timing. Build timings include registration and compilation for the same two-component container, without activating a service.

| Measurement | Handwritten wrapper | Per-call | Extra time | Increase |
| --- | ---: | ---: | ---: | ---: |
| Sync operation | 8.77–8.86 µs | 9.67–9.69 µs | 0.84–0.90 µs | 9.4–10.3% |
| Async operation | 10.45–10.57 µs | 11.27–11.30 µs | 0.74–0.82 µs | 7.0–7.9% |
| Container build | 3.05–3.12 ms | 3.41–3.59 ms | 0.36–0.47 ms | 11.7–15.0% |

Ranges show medians from two unchanged runs, not confidence intervals. Repeat-sample CV ranged from 0.75% to 7.80%; several runs had outlier flags. Runtime overhead was consistent across both runs; the build increase varied from about 0.36 to 0.47 ms. These are microbenchmarks, not end-to-end application latency.

An initial unbatched exploratory run had a 20% CV for sync per-call execution. It is retained as `feature-final.json` but is not used for the comparison above. Batched and unbatched timings are different measurements and should not be compared directly.

## Ordinary runtime paths

The original historical baseline used mains power. A new baseline was collected on battery before drawing conclusions. Both current runs are shown below to expose run-to-run variation; the latest repeat is used in the summary.

| Benchmark | Fresh original (µs) | Current run 1 (µs) | Current run 2 (µs) | Latest change |
| --- | ---: | ---: | ---: | ---: |
| direct-python-construction | 0.576 | 0.597 | 0.587 | +1.9% |
| resolve-pre-built-instance | 0.952 | 0.965 | 0.979 | +2.8% |
| resolve-cached-singleton | 0.888 | 0.923 | 0.903 | +1.7% |
| resolve-transient | 1.892 | 1.917 | 1.905 | +0.7% |
| resolve-five-component-plan | 6.300 | 6.329 | 6.345 | +0.7% |
| create-scope | 1.655 | 1.682 | 1.693 | +2.3% |
| resolve-request-slot-plan | 7.746 | 7.887 | 7.829 | +1.1% |

## Ordinary build paths

| Benchmark | Fresh original (ms) | Current (ms) | Change |
| --- | ---: | ---: | ---: |
| build-five-component-container | 6.558 | 6.587 | +0.4% |
| build-five-component-container-with-entrypoint-diagnostics | 6.530 | 6.510 | -0.3% |
| build-scope-overlay | 6.953 | 6.914 | -0.6% |
| build-open-generic-factory-container | 3.579 | 3.568 | -0.3% |

## Reproduction and evidence

- Benchmark definition: [`bench_per_call_scopes.py`](../benchmarks/bench_per_call_scopes.py).
- Adaptive sampling: at least 7, at most 30 repeats; target relative margin 3%; at least 0.25 seconds; maximum 10 seconds per benchmark. Runtime batches contain 100 operations, with at least 100 batches per repeat. GC uses the existing BenchBro disable-during-measure policy.
- Preflight verified the result and exactly 100 resource activations and cleanups per batch for each of the four runtime variants.
- Repository lint, formatting, type checks, complete benchmark discovery, and diff checks passed. Production code was not changed during these measurements.
- JSON reports preserve sample quality, environment, and settings. Existing historical named baselines were retained.

```sh
uv run benchbro run benchmarks/bench_per_call_scopes.py --baseline per-call-batched-feature --output-json .benchbro/per-call-scopes/feature-batched-repeat.json --output-md .benchbro/per-call-scopes/feature-batched-repeat.md
uv run benchbro run benchmarks/bench_clean_ioc.py --case compiled-runtime --no-compare --output-json .benchbro/per-call-scopes/runtime-final-repeat.json --output-md .benchbro/per-call-scopes/runtime-final-repeat.md
uv run benchbro run benchmarks/bench_clean_ioc.py --case compiled-build --no-compare --output-json .benchbro/per-call-scopes/build-final.json --output-md .benchbro/per-call-scopes/build-final.md
```

Fresh original-code measurements used the same `.venv/bin/python -m benchbro` from a detached `d61505b` worktree; import paths were checked before running. That temporary checkout was removed afterward.

Raw results:
- [feature-batched.json](../.benchbro/per-call-scopes/feature-batched.json)
- [feature-batched-repeat.json](../.benchbro/per-call-scopes/feature-batched-repeat.json)
- [runtime-baseline-fresh.json](../.benchbro/per-call-scopes/runtime-baseline-fresh.json)
- [runtime-final.json](../.benchbro/per-call-scopes/runtime-final.json)
- [runtime-final-repeat.json](../.benchbro/per-call-scopes/runtime-final-repeat.json)
- [build-baseline-fresh.json](../.benchbro/per-call-scopes/build-baseline-fresh.json)
- [build-final.json](../.benchbro/per-call-scopes/build-final.json)
