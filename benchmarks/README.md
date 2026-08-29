# Microbenchmarks

The suite uses [BenchBro](https://github.com/peter-daly/benchbro) to measure repeat-level samples, report noise and confidence, and keep comparisons environment-aware.

Run it from the repository root:

```bash
uv run benchbro run
```

`make benchmark` is the equivalent convenience target.

Use `uv run benchbro list --verbose` to inspect the discovered operations. The suite separates four questions:

- `compiled-runtime`: resolution, scope creation, and request-slot plan execution with composition excluded;
- `compiled-build`: explicit root, scope-overlay, and open-generic factory compilation, including builder setup;
- `compiler-tooling`: uncached semantic manifest creation and identical/single-change manifest diffs, with composition excluded;
- `compiled-allocations`: Python allocations reported by `tracemalloc`, not process RSS.

Runtime containers and provided request scopes are prepared outside the measured interval. Build benchmarks deliberately include registration and compilation.

The configured run writes a complete machine-readable result to `benchmarks/results.json` and a readable report to `benchmarks/results.md`. BenchBro keeps the machine-local comparison baseline under `.benchbro/`, which is intentionally ignored by Git.

These are framework-overhead microbenchmarks, not application-throughput claims. Compare results only on a matching Python, operating system, architecture, and machine environment.
