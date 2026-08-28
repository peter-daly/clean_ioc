---
description: Reproducible BenchBro experiments separating Clean IoC build cost, compiled runtime latency, and Python allocations.
---

# Benchmarks

The compiled model deliberately moves work from resolution to `build()`. The benchmark suite therefore measures three boundaries separately:

- container and scope-overlay compilation;
- resolution and ordinary scope creation after compilation;
- Python allocations through `tracemalloc`.

## Local directional snapshot

Measured twice unchanged with BenchBro 1.0 on 28 August 2026 using CPython 3.14.4, macOS 15.7.9, and Apple arm64. The second run produced:

| Operation | Median / peak | CV | Quality |
| --- | ---: | ---: | --- |
| Direct Python construction | 0.56 µs | 1.90% | Stable |
| Resolve pre-built instance | 2.44 µs | 4.09% | Noisy |
| Resolve cached singleton | 2.56 µs | 5.26% | Noisy |
| Resolve transient | 4.97 µs | 0.67% | Stable |
| Resolve five-component plan | 19.99 µs | 2.34% | Noisy |
| Create ordinary scope | 3.74 µs | 1.76% | Noisy |
| Resolve request-slot plan | 24.05 µs | 3.72% | Noisy |
| Build five-component container | 336.61 µs | 0.74% | Stable |
| Build scope overlay | 278.42 µs | 0.89% | Noisy |
| Resolve five-component allocation peak | 4,048.8 B | 28.98% | Noisy |
| Create-scope allocation peak | 2,635.5 B | 0.72% | Stable |

“Noisy” means BenchBro found an IQR outlier or exceeded the configured CV threshold. The unchanged comparison kept runtime medians within 3%, build medians within 1%, and allocation peaks within 0.3%. Treat this as evidence about this machine and implementation—not a package guarantee or CI threshold.

The allocation case measures Python allocations visible to `tracemalloc`, not whole-process resident memory. The noisy five-component allocation row needs more investigation before making an allocation-reduction claim.

## Measurement boundaries

Runtime containers and the provided request scope are session systems prepared outside the measured interval. Each runtime invocation performs exactly one resolve or scope creation.

Build benchmarks deliberately include:

- builder construction;
- registrations;
- component-plan compilation;
- immutable runtime creation.

This keeps startup cost visible instead of hiding it in setup.

## Reproduce it

```bash
uv sync
uv run benchbro list --verbose
uv run benchbro run --no-compare
uv run benchbro run
```

The first pass creates a machine-local baseline. The unchanged second pass establishes ordinary variance. Inspect sample count, confidence interval, relative margin, CV, outliers, and the noisy flag before interpreting a change.

The checked-in `benchbro.toml` owns sampling policy and writes:

- `benchmarks/results.json` — complete result and environment metadata;
- `benchmarks/results.md` — generated human-readable report.

Machine-local baselines and history remain under ignored `.benchbro/`.
