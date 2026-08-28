---
description: Reproducible Clean IoC microbenchmarks for instance, singleton, transient, graph resolution, and static explanations.
---

# Benchmarks

Clean IoC favors predictable ownership and graph capability over being the smallest possible service lookup. These microbenchmarks make its framework overhead visible and reproducible.

## Current result

Measured with BenchBro 1.0.0 on 28 August 2026 using CPython 3.14.4 and macOS 15.7.9 on Apple arm64. Adaptive sampling used 20,000 measured invocations per repeat and stopped between 7 and 30 repeat samples after reaching a 3% relative-margin target or the 10-second limit.

| Scenario | Median | Operations/sec | Samples | CV | Quality |
| --- | ---: | ---: | ---: | ---: | --- |
| Direct Python construction | 0.57 µs | 1,754,360 | 7 | 1.09% | Stable |
| Resolve pre-built instance | 9.15 µs | 107,056 | 10 | 4.56% | Noisy¹ |
| Resolve cached singleton | 8.97 µs | 110,281 | 7 | 2.65% | Noisy¹ |
| Resolve transient | 13.15 µs | 74,642 | 13 | 5.21% | Noisy¹ |
| Resolve five-node graph | 44.19 µs | 22,486 | 7 | 2.37% | Stable |
| Explain five-node graph | 33.59 µs | 29,582 | 7 | 2.18% | Noisy¹ |

¹ BenchBro marks a result noisy when its coefficient of variation crosses the configured threshold or its IQR analysis finds an outlier. Each noisy row above had one outlier and a CV below 5.3%. Two unchanged comparison runs kept every median within 3.4% of the initial baseline, so these figures are useful as directional framework-overhead measurements rather than hard application limits.

The direct-construction row passes through the same benchmark call boundary as every other row. It is a harness reference, not a raw constructor floor or a like-for-like feature comparison. Real factories, database calls, network clients, and application work usually dominate container overhead.

## Reproduce it

Install the locked development environment, inspect discovery, and run the suite:

```bash
uv sync
uv run benchbro list --verbose
uv run benchbro run
```

`make benchmark` runs the same configured suite. CI uses the much faster discovery-only check so benchmark definitions cannot silently drift while host-specific timing remains opt-in.

The checked-in `benchbro.toml` owns the sampling policy and writes two reviewable artifacts:

- `benchmarks/results.json` preserves the complete schema-versioned result and environment metadata.
- `benchmarks/results.md` is the generated human-readable report.

Container setup and BenchBro dependency injection are explicitly excluded from the measured interval. Each invocation measures one Python construction, Clean IoC resolution, or static explanation operation.

Normal runs compare with the machine-local `.benchbro/baseline.local.json`. That directory is ignored by Git; use `--new-baseline` only when the current environment and behavior should deliberately replace your local reference. BenchBro rejects environment-mismatched comparisons by default.

## Concurrency correctness

Scoped and singleton activation uses a shared build coordinator. Concurrent threads and async tasks that request the same uncached registration wait for the first build and receive the same cached instance. Failed first builds wake every waiter and leave the registration retryable.

This behavior is covered by dedicated tests because “one build per ownership boundary” is a correctness guarantee, not a timing result.
