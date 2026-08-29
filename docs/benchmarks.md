---
description: Reproducible BenchBro experiments separating Clean IoC build cost, compiled runtime latency, and Python allocations.
---

# Benchmarks

The compiled model deliberately moves work from resolution to `build()`. The benchmark suite therefore measures four boundaries separately:

- container and scope-overlay compilation;
- resolution and ordinary scope creation after compilation;
- semantic manifest creation and manifest diffing after compilation;
- Python allocations through `tracemalloc`.

## Local directional snapshot

Measured with BenchBro 1.0 on 29 August 2026 using CPython 3.14.4, macOS 15.7.9, and Apple arm64:

| Operation | Median / peak | CV | Quality |
| --- | ---: | ---: | --- |
| Direct Python construction | 0.56 µs | 4.00% | Noisy |
| Resolve pre-built instance | 2.45 µs | 1.66% | Noisy |
| Resolve cached singleton | 2.54 µs | 1.52% | Noisy |
| Resolve transient | 5.00 µs | 6.35% | Noisy |
| Resolve five-component plan | 20.04 µs | 2.28% | Noisy |
| Create ordinary scope | 3.82 µs | 1.90% | Noisy |
| Resolve request-slot plan | 24.15 µs | 2.71% | Noisy |
| Build five-component container | 362.85 µs | 0.33% | Stable |
| Build with entry-point diagnostics | 382.08 µs | 1.04% | Stable |
| Build scope overlay | 338.68 µs | 1.46% | Stable |
| Build open generic factory container | 320.65 µs | 0.72% | Stable |
| Create semantic manifest | 83.46 µs | 1.87% | Noisy |
| Diff identical manifest | 52.38 µs | 1.83% | Stable |
| Diff one wiring change | 57.43 µs | 1.10% | Noisy |
| Resolve five-component allocation peak | 3,959.7 B | 17.98% | Noisy |
| Create-scope allocation peak | 2,646.2 B | 0.56% | Stable |

“Noisy” means BenchBro found an IQR outlier or exceeded the configured CV threshold. The entry-point build is about 5.3% above the otherwise equivalent build in this run. Treat these results as evidence about this machine and implementation—not a package guarantee or CI threshold.

The allocation case measures Python allocations visible to `tracemalloc`, not whole-process resident memory. Allocation snapshots remain directional and are not evidence of whole-process memory reduction.

## Measurement boundaries

Runtime containers and the provided request scope are session systems prepared outside the measured interval. Each runtime invocation performs exactly one resolve or scope creation.

Build benchmarks deliberately include:

- builder construction;
- registrations;
- component-plan compilation;
- immutable runtime creation.

This keeps startup cost visible instead of hiding it in setup.

The `compiler-tooling` case prepares compiled graphs and manifests as session systems. Its measured functions isolate three read-only operations: creating an uncached semantic manifest, diffing identical manifests, and diffing a single wiring change. Container composition and graph compilation remain outside this tooling boundary.

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
