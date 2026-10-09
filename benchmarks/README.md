# Microbenchmarks

The suite uses [BenchBro](https://github.com/peter-daly/benchbro) to measure repeat-level samples, report noise and confidence, and keep comparisons environment-aware.

### Large graph memory fixture

`graph_memory_evidence.py` measures a larger composition with registration templates
in both dependency directions, decorator templates, all four provider forms, and
sync/async provider maps. It checks exact bindings, lazy activation and lifetime
identity, and reports retained graph storage alongside process memory. See the
[workload and reproduction instructions](../docs/graph-memory-fixture.md).

### Compiled graph artifact experiment: not ready

`graph_memory_artifact_evidence.py` repeats compilation/export/loading in separate
processes for the richer template/provider/map fixture after graph-memory tasks
01 and 02. The private codec includes only the additional shapes needed by this
fixture. See the [retest record](../.work/graph-memory-optimization/artifact-retest.md).

`graph_artifact_evidence.py` is an unfinished local experiment that **may be
dropped**. It is not a supported feature or production-ready artifact format.
Current measurements show about 0.62 seconds saved, similar retained memory, and
higher startup peak memory; they do not justify expanding support yet. The
prototype and results are retained for reference. See the
[experiment status, results, and reproduction instructions](../docs/graph-artifact-experiment.md).

### Benchmark suite

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

### Incremental-analysis investigation (item 18)

`incremental_analysis_probe.py` is an isolated experiment, with no supported cache
API. It preserves the original stable-schema fixture definitions and fresh owner
close. It measures complete declarations + build + close in four modes: normal,
conservative parameter-name reuse, an intentionally unsafe validation-omission
ceiling, and an unchanged normal repeat. Definitions/imports and cache construction
are excluded; fresh declarations and the patch context are included. The bounded
probe is warm across builders. Patching is process-global: run this investigation
alone, and never use its ceiling for application composition.

```sh
uv run benchbro run benchmarks/incremental_analysis_probe.py \
  --case incremental-name-analysis-investigation --fixed --repeats 25 --warmup 5 \
  --baseline item18-parameter-shape --no-compare \
  --output-json /tmp/item18-measurement-1.json --output-md /tmp/item18-measurement-1.md
# Repeat with measurement-2 output filenames; preserve the same probe digest.
uv run benchbro run benchmarks/incremental_lifetime_probe.py \
  --case incremental-analysis-lifetime --fixed --repeats 25 --warmup 5 \
  --baseline item18-lifetime --no-compare \
  --output-json /tmp/item18-lifetime.json --output-md /tmp/item18-lifetime.md
uv run python -m benchmarks.incremental_analysis_evidence
```

The explicit case filter excludes imported baseline cases from this experiment.
The evidence helper writes separate aggregate hit/rejection counts and five-sample
tracemalloc allocations to `/tmp/item18-evidence.json`. Name/kind analysis hits are
not runtime cache hits. See [the eligibility model and decision](../.work/18-incremental-compilation.md).

The lifetime probe isolates cross-build warm reuse from the same bounded cache
cleared before each build. Both retain within-build hits. It selects only the
original generic and collection shapes, with a warm-repeat drift control. Clear
is included in timing, slightly favoring warm reuse; probe construction is excluded.

### Captured clone metadata (item 19)

Item 19 removes a discarded implementation-type normalization when cloning graph
occurrences. It leaves eager provider roots, executable plans and ordinary runtime
paths intact. Use the unchanged stable fixture/evidence helpers above; no experiment
imports decorated benchmark modules into ordinary benchmark discovery.

```sh
uv run benchbro run benchmarks/bench_compiler_optimization.py \
  --case compiler-declaration-build --case compiler-build-only \
  --fixed --repeats 25 --warmup 5 --baseline item19-pre-state --no-compare \
  --output-json /tmp/item19-after-1.json --output-md /tmp/item19-after-1.md
# Repeat with after-2 filenames; pre-change isolated capture uses before-2.
uv run benchbro run benchmarks/bench_managed_provider_regressions.py \
  --fixed --repeats 25 --warmup 5 --baseline item19-runtime --no-compare \
  --output-json /tmp/item19-runtime-after.json --output-md /tmp/item19-runtime-after.md
# Repeat with runtime-after-2 filenames when a control shows an apparent increase.
# Run the instrumented helper only after latency measurements finish.
uv run python -m benchmarks.compiler_optimization_evidence --prefix /tmp/item19-after
```

Each latency run is unprofiled, with the existing eight build invocations per repeat;
declarations/close and fresh-fixture build-only boundaries remain separate. Runtime
controls retain 1,000 batches of 100 operations per repeat on prebuilt containers.
`--no-compare` retains named machine-local baselines without overwriting earlier
results. Read CV and unchanged-code drift before attributing differences. The
allocation helper has five traced samples per shape; raw cProfiles cover five
builds each, separately with and without declarations. Exact call counts, graph
and retained executable counts are the strongest evidence here. Shallow plan bytes
are a lower bound and traced allocation is not RSS. The accidentally overlapped
`/tmp/item19-before-1.*` latency is excluded; the overlapped pre-change profile times
are diagnostic attribution only, while their process-local work/allocation counts
remain usable. The original committed compiler baseline is also preserved.
See [item 19's proof, results and digests](../.work/19-execution-plan-optimization.md).

### Compilation budgets (item 20)

The post-item-19/pre-item-20 baseline is preserved separately from release/item19
artifacts. The first command captures disabled-budget overhead with the unchanged
six build-only fixtures. Use two runs and retain both; fixed repeats do not remove
between-run drift or high repeat variation.

```sh
uv run benchbro run benchmarks/bench_compiler_optimization.py \
  --case compiler-build-only --fixed --repeats 25 --warmup 5 \
  --baseline item20-post19 --no-compare \
  --output-json /tmp/item20-before-1.json --output-md /tmp/item20-before-1.md
# Repeat as before-2 before changing code. Final captures use item20-final and after-{1,2}.
uv run benchbro run benchmarks/compilation_budget_experiment.py \
  --case compilation-budgets --fixed --repeats 25 --warmup 5 \
  --baseline item20-final-modes --no-compare \
  --output-json /tmp/item20-budget-modes-1.json --output-md /tmp/item20-budget-modes-1.md
# Repeat as budget-modes-2; keep profiling/allocation and CI idle during latency capture.
uv run benchbro run benchmarks/bench_managed_provider_regressions.py \
  --fixed --repeats 25 --warmup 5 --baseline item20-runtime --no-compare \
  --output-json /tmp/item20-runtime-after-1.json --output-md /tmp/item20-runtime-after-1.md
# Repeat as runtime-after-2 with the original 1000 iterations of each 100-operation batch.
# Run only after all unprofiled measurements finish.
TMPDIR=/tmp uv run python -m benchmarks.compilation_budget_evidence
```

The experiment is outside `bench_*.py` discovery and needs its explicit case
filter because importing the stable fixture module also registers its cases.
None, all-unlimited counting, generous finite limits and occurrence100 bounded
failure use eight fresh prepared builds per repeat. Budgets, declarations and
normal close are excluded. The bounded operation includes safe failure capture.
Wide24, generic8, collection12 and template12 retain original fixture semantics;
the additional overlay excludes its caller-owned parent build/close. Its parent
uses the existing managed-warmup fixture. Runtime controls remain unchanged.

The separate evidence helper writes `/tmp/item20-evidence.json`, per-cell
`item20-*-compilation-profile.json` and raw `item20-*.prof`. Each cell records five
independent Python-traced allocation samples with declarations before tracing
and either an unactivated runtime or failure evidence retained. It also records
one full compilation profile and five cProfile builds, with normal close outside
profiling. Instrumented duration is not a latency result; traced bytes are not
RSS. It checks source digests and zero component activation. Configured budget
usage means admitted operation starts; successful profiler counters have their
own units. See [the operation contract](../docs/compilation-budgets.md) and
[the capture, uncertainty and review note](../.work/20-compilation-budgets.md).

### Compiler memory probes

`uv run python -m benchmarks.compiler_memory_evidence chain --size 32 --profile`
reports physical graph storage, provider view contexts, retained activation templates
and aggregate compiler counters. Other shapes are `small-chain`, `two-transports`,
`routes` and `senders`; `--early` opts senders into `candidate_when`. Omit `--profile`
for a separate fresh-process timing/RSS sample. The allocation totals are shallow
lower bounds, and RSS is a process high-water mark, not retained heap size.

For pinned Cop application comparisons, run `benchmarks/cop_compiler_memory_evidence.py`
with the Cop environment's Python, `api` or `worker`, and `--project /path/to/cop`.
`--settings-json /path/to/report-settings.json` loads environment strings without
printing values; `--profile` uses the existing zero-span profiler. Use separate
disposable environments for a candidate wheel; preserve the shared lock and environment.
Normal timing covers the actual `get_container` call after constructing Config.
Treat wheel substitution as development evidence and perform released Linux readiness
acceptance separately. See `docs/compiler-memory-evidence.md` for the recorded runs.

### Decorator fact inspection

The evidence runner reports identity-deduplicated retained decorator objects and
logical decision counts separately. Use `--inspection` for first/repeated public
explanation access (128 components) and, with `--diagnostics`, full selection census.
These operations occur after measured build/resolution intervals.
`--eager-decorator-facts` recreates the eager evidence representation solely inside
the evidence process, for inspection comparisons. Save new results under
`.work/graph-memory-optimization/evidence/` to preserve the original baseline.

The task-03 [reachability audit](graph_reachability_audit.py) is an offline
inspection utility, not a compiler pruning pass. It accounts for graph-qualified
execution references, public/provider/managed/architecture/warmup roots,
candidates, explanation sidecars, contextual views and explicitly supplied escaped
callback components. Run it separately from other measurements:

```sh
.venv/bin/python -m benchmarks.graph_reachability_audit --routes 8 --output .cache/graph-reachability.json
```

Its conservative retained set is evidence, not a proof that sidecar-only records
are individually necessary. The [task result](../.work/graph-memory-optimization/03-result.md)
records why ordinary runtime-root reachability is insufficient to authorize
pruning and measures the offline audit's temporary allocation cost.

Task 04's subtree-sharing implementation was reverted on 2026-10-09: retained
Python allocations fell, but process RSS increased and graph inspection slowed.
The [task result](../.work/graph-memory-optimization/04-result.md) preserves those
measurements; the [rollback record](../.work/graph-memory-optimization/04-rollback.md)
documents the restored pre-task-04 runtime, measurement runner and artifact codec.

The [artifact retest after task 05](../.work/graph-memory-optimization/artifact-retest-post05.md)
compares compilation and separate-process loading with explanation metadata on
and off. The private schema-7 codec accepts the reduced fixture runtime; add
`--no-explain-metadata` to `benchmarks.graph_memory_artifact_evidence` to select it.
