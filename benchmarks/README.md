# Microbenchmarks

The suite uses [BenchBro](https://github.com/peter-daly/benchbro) to measure repeat-level samples, report noise and confidence, and keep comparisons environment-aware.

`bench_registration_patterns.py` compares pattern compilation with explicit closed registrations at nesting depths
1, 3, and 6; measures additional same-origin template alternatives; and compares frozen transient/singleton resolution
against explicit controls. Setup and warmup are excluded from runtime measurements. Build includes declarations,
compilation, and close. Use dedicated named baselines and explicit report paths under an ignored `.benchbro/`
experiment, and inspect sample quality before interpreting comparisons.

`bench_registration_templates.py` compares one generated worker per source against equivalent explicit registrations
at 1, 10, and 100 sources. Build includes declarations, compilation, and close. Runtime uses prebuilt, warmed
containers and measures single-worker resolution plus collections of 100 workers, with transient and singleton
lifespans. Fixture checks ensure each worker receives the same exact source in both modes. The separate
`registration-template-parent-build` case measures sources depending on generated services, using exact parent filters
and dependency-only registrations at the same sizes. Its explicit control produces the same parent-specific edges.

Capture the current registration-template baseline with explicit report paths:

```bash
uv run benchbro run benchmarks/bench_registration_templates.py --no-compare \
  --output-json .benchbro/registration-templates-before-parent-resolution/run-1.json \
  --output-md .benchbro/registration-templates-before-parent-resolution/run-1.md
```

Repeat unchanged code with different report filenames to check normal variance before comparing a later change.
`--no-compare` skips comparison, but BenchBro can still backfill new entries in its local baseline.

Run it from the repository root:

```bash
uv run benchbro run
```

`make benchmark` is the equivalent convenience target.

Use `uv run benchbro list --verbose` to inspect the discovered operations. The suite separates seven questions:

- `compiled-runtime`: resolution, scope creation, and request-slot plan execution with composition excluded;
- `compiled-build`: explicit root, scope-overlay, and open-generic factory compilation, including builder setup;
- `compiled-build-features`: five-component builds that isolate build validation, validate-only rule
  registration, resource ownership, typed providers, and boundary visibility;
- `compiler-validation`: deferred whole-graph walking and source AST inspection on an already-built graph;
- `compiler-tooling`: uncached semantic manifest and ownership-report creation plus identical/single-change manifest diffs,
  with composition excluded;
- `compiled-allocations`: Python allocations reported by `tracemalloc`, not process RSS.
- `fastapi-five-layer-request`: end-to-end `TestClient` requests through five cached FastAPI dependencies versus
  five Clean IoC `per_resolution` components.

Runtime containers and provided request scopes are prepared outside the measured interval. Build benchmarks deliberately include registration and compilation.
Build cases use 100 iterations per repeat and tooling cases use 500 so each repeat is long enough for stable timing
without multiplying millisecond-scale compiler work tens of thousands of times.
The FastAPI applications and clients are also prepared outside the measured interval; request dispatch, dependency resolution,
response serialization, and the complete ASGI middleware path remain inside it. Run only that comparison with
`uv run benchbro run benchmarks/bench_fastapi.py --case fastapi-five-layer-request --no-compare`.

The configured run writes a complete machine-readable result to `benchmarks/results.json` and a readable report to `benchmarks/results.md`. BenchBro keeps the machine-local comparison baseline under `.benchbro/`, which is intentionally ignored by Git.

These are framework-overhead microbenchmarks, not application-throughput claims. Compare results only on a matching Python, operating system, architecture, and machine environment.

### Declared warm-up plans

`bench_warmup.py` measures cached plain/observed runs (100 calls per batch),
no-plan/declared builds, and cold build + warm-up + resource shutdown. Resources
have no I/O; session fixtures are created during unmeasured warmup and closed at
run end. `bench_managed_provider_regressions.py` also probes unchanged ordinary
resolution, provider, child-scope and per-call paths. See item 17's measurements
in [.work/17-declared-warmup-plans.md](../.work/17-declared-warmup-plans.md).

```sh
uv run benchbro run benchmarks/bench_warmup.py --fixed --repeats 25 --no-compare \
  --output-json /tmp/warmup.json --output-md /tmp/warmup.md
```

### Compiler optimization baseline (items 18–20)

`bench_compiler_optimization.py` uses stable definitions with fresh single-use
builders for bounded wide roots, diamonds, repeated generic subgraphs, explicit
collections, registration templates, and a managed-provider/warmup compatibility
shape. It separates declaration + build + close from build-only (fresh iteration
fixtures exclude declarations and normal close). Three-builder same/changed-input
batches, parent overlays, and a three-variant matrix exercise related compositions;
matrix includes reports and teardown. No application objects activate during build.
These cases measure steady schemas, not fresh definition creation or process import.

Capture both unchanged runs before modifying production code:

```sh
uv run benchbro run benchmarks/bench_compiler_optimization.py --fixed --repeats 25 \
  --warmup 5 --baseline compiler-optimization-preparation --no-compare \
  --output-json /tmp/compiler-optimization-before-1.json \
  --output-md /tmp/compiler-optimization-before-1.md
# Repeat with before-2 output filenames.
uv run python -m benchmarks.compiler_optimization_evidence
```

The evidence helper writes separate `/tmp/compiler-optimization-*` allocation,
compiler-profile and cProfile artifacts. It records Python traced peak and retained
runtime/plan bytes, graph visits/occurrences, and unique executable objects. The
shallow executable-byte count is a lower bound; traced retained bytes are compiler-created
allocations including runtime/plan metadata and exclude pre-trace declarations. Instrumented timings are diagnostic evidence,
not comparable latency baselines. Existing runtime regressions remain in
`bench_managed_provider_regressions.py`. See
[the captured baseline and limitations](../.work/compiler-optimization-baseline.md).
