# Compiler optimization baseline — items 18–20

Captured 2026-10-04 before production changes, on released `eacdf70ab262ec27595c5f43d237a43e882ca72c`
(Clean IoC 2.0.0b30), branch `codex/compiler-optimization`. Preparatory benchmark code and scheduling documents
were uncommitted; production code was unchanged. No version bump or existing results/history replacement.

## Experiment and provenance

BenchBro 1.0.0, CPython 3.14.4, macOS 26.7.1 / Darwin 25.6.0, arm64, 12 reported CPUs, AC power.
`pmset -g therm` recorded no thermal/performance warning, but no CPU power status was available. The parent paused
other heavy agent jobs throughout the unprofiled captures; this was not an isolated machine or controlled thermal lab.
Captured quiet-window recording timestamps: `2026-10-04T09:13:44.934241+00:00` through `2026-10-04T09:21:35.475230+00:00`.
Lock SHA-256: `0a39ba6f6ac45ec27723907c0ab79a48797517dee1274187ea6e49574ab09be5`.
Benchmark harness SHA-256: `70a2a037e26df5fa4daf02e66af484687ebee5604e8a92c58a18d6e1dc6b733d`.
The JSON runs retain full interpreter, OS, power, repository and lock provenance.

[Harness](../benchmarks/bench_compiler_optimization.py) uses stable module-level ordinary constructors/factories and
closed aliases, with fresh single-use builders. Sizes: 24 independent roots, depth-5 binary diamond, eight generic
consumers across four closed bindings, 12-worker explicit and template collections, and a managed-provider plus
declared warmup compatibility shape. Related generic batches compile three fresh builders with same/changed inputs;
overlays inherit a parent singleton or locally override it; a three-variant matrix includes capture/diff reports and close.
Definitions/imports are excluded. These are steady-schema fresh builds, not cold interpreter/fresh-definition creation.

Declaration+build includes registration, build and normal owner close. Build-only uses iteration-scoped fixtures:
fresh declarations are outside timing, the complete public build is inside timing, and owner close is outside.
Related batches include declarations/build/close; overlay parent setup is excluded while overlay declarations/build/close
are included. Matrix includes its complete normal check. Every owner closes; compile probes verified zero constructors,
resource acquisitions or warmup activations. Existing runtime controls use prebuilt warmed session owners with normal close.

Both unprofiled compiler runs used fixed 25 repeats and five warmups; iterations per sample were eight for individual
builds/overlays, three for three-builder batches, two for the three-variant matrix. Runtime controls used 25 repeats,
five warmups and 100 iterations per sample, each invocation containing 100 operations. GC uses BenchBro's
`disable_during_measure` policy. Explicit `/tmp` outputs and `--no-compare` avoided tracked results and history;
a dedicated ignored `compiler-optimization-preparation` named baseline received only new entries, never existing baselines.

## Unprofiled results and limits

Each cell pair below is run 1 / unchanged run 2. All cases have 25 repeat samples. Margins are BenchBro's relative
95% confidence margins; outliers and noisy flags are retained without filtering. No before/after feature comparison
exists here. Do not subtract independently timed declaration and build medians to infer registration cost.

| Case / operation | Median ms 1 / 2 | Change | CV % 1 / 2 | Margin % 1 / 2 | Outliers 1 / 2 | Noisy 1 / 2 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| declaration-build / fresh[wide-24] | 43.56 / 45.81 | +5.2% | 8.6 / 8.9 | 3.5 / 3.6 | 2 / 1 | True / True |
| declaration-build / fresh[diamond-depth-5] | 49.69 / 53.88 | +8.4% | 9.1 / 10.0 | 3.7 / 4.0 | 0 / 0 | False / False |
| declaration-build / fresh[generic-8-roots] | 115.23 / 85.13 | -26.1% | 17.7 / 12.6 | 7.1 / 5.0 | 0 / 1 | True / True |
| declaration-build / fresh[collection-12] | 55.64 / 33.30 | -40.2% | 16.0 / 19.4 | 6.4 / 7.8 | 0 / 1 | True / True |
| declaration-build / fresh[template-12] | 60.21 / 32.23 | -46.5% | 13.8 / 18.3 | 5.5 / 7.3 | 3 / 0 | True / True |
| declaration-build / fresh[managed-warmup] | 11.31 / 5.91 | -47.7% | 34.1 / 15.2 | 13.6 / 6.1 | 0 / 2 | True / True |
| build-only / wide-24 | 62.64 / 46.79 | -25.3% | 16.6 / 12.1 | 6.7 / 4.8 | 0 / 1 | True / True |
| build-only / diamond-depth-5 | 54.30 / 47.29 | -12.9% | 12.1 / 12.1 | 4.8 / 4.8 | 1 / 1 | True / True |
| build-only / generic-8-roots | 82.17 / 83.87 | +2.1% | 10.9 / 12.1 | 4.3 / 4.8 | 0 / 0 | True / True |
| build-only / collection-12 | 25.80 / 26.20 | +1.6% | 8.5 / 11.6 | 3.4 / 4.7 | 2 / 1 | True / True |
| build-only / template-12 | 34.08 / 28.94 | -15.1% | 9.7 / 15.0 | 3.9 / 6.0 | 1 / 0 | True / True |
| build-only / managed-warmup | 5.51 / 6.42 | +16.5% | 19.4 / 16.6 | 7.7 / 6.7 | 0 / 0 | True / True |
| related-builds / three-fresh-generics[same-input] | 267.42 / 239.42 | -10.5% | 11.7 / 9.4 | 4.7 / 3.8 | 2 / 1 | True / True |
| related-builds / three-fresh-generics[changed-input] | 261.91 / 249.86 | -4.6% | 9.2 / 9.1 | 3.7 / 3.6 | 2 / 0 | True / False |
| related-overlays / fresh-overlay[inherited] | 4.56 / 4.66 | +2.2% | 22.4 / 13.0 | 9.0 / 5.2 | 1 / 1 | True / True |
| related-overlays / fresh-overlay[local-override] | 4.84 / 4.83 | -0.1% | 22.6 / 21.6 | 9.1 / 8.7 | 2 / 0 | True / True |
| matrix / three-variants-and-reports | 306.19 / 250.65 | -18.1% | 14.8 / 7.2 | 5.9 / 2.9 | 0 / 0 | True / False |

16/17 compiler cases were noisy in run 1; 14/17 in run 2. Unchanged median drift ranges from −47.7% to +16.5%.
These captures establish reproducible workloads and coarse cost scale, not a small-regression threshold. A future
small speedup remains inconclusive unless a steadier matching environment or a larger convincing effect establishes it.

Runtime medians below are microseconds **per 100-operation batch**; divide by 100 for per-operation cost.

| Existing runtime path | Median μs 1 / 2 | Change | CV % 1 / 2 | Margin % 1 / 2 | Outliers 1 / 2 | Noisy 1 / 2 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| batch-of-100[resolve] | 40.04 / 38.53 | -3.8% | 31.0 / 30.2 | 12.4 / 12.1 | 0 / 3 | True / True |
| batch-of-100[provider] | 51.84 / 51.07 | -1.5% | 30.8 / 29.2 | 12.3 / 11.7 | 0 / 5 | True / True |
| batch-of-100[scope] | 141.35 / 144.02 | +1.9% | 33.2 / 20.5 | 13.3 / 8.2 | 1 / 0 | True / True |
| batch-of-100[per-call] | 1281.62 / 1306.95 | +2.0% | 22.0 / 11.9 | 8.8 / 4.8 | 1 / 1 | True / True |

All eight runtime measurements were noisy; unchanged drift −3.8% to +2.0% is smaller than their uncertainty.
These are controls for later runtime changes, not evidence of a current regression or improvement.

## Separate allocation and work evidence

[Evidence helper](../benchmarks/compiler_optimization_evidence.py) records five separate `tracemalloc` samples after
one warm schema build. Fresh declarations occur **before** tracing. Peak measures traced build allocations; retained
bytes measure compiler-created allocations still live after dropping the builder and collecting GC while the unactivated
runtime is retained. They include frozen metadata and runtime/coordinator overhead, but exclude predeclared objects,
Python code and process RSS. Post-close/drop/GC bytes can include interpreter/type caches and tracing overhead; they
are not a proven leak. No instrumented duration is a latency benchmark.

Private inventory walks distinct executable objects from all normal roots, provider roots and warmup roots, following
step targets, dependency/preconfiguration/decorator records and tuple edges. It excludes blueprint, registration,
component, values, ownership tokens, caches/coordinators and callback data. Its shallow storage count is a lower bound
for reachable executable structure, not the entire plan size. Only aggregate counts/class names/bytes are exported.
Public graph occurrence counts are separate from all compiler `_draft` work, including synthesized provider clones.

| Shape | Public graph occurrences | Compiler draft occurrences | Candidate attempts / returned steps | Retained unique steps | Shallow executable bytes | Traced build peak bytes | Traced retained bytes | Post-release bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| wide-24 | 24 | 1080 | 24 / 24 | 696 | 94,896 | 1,713,813 | 1,493,120 | 78,603 |
| diamond-depth-5 | 63 | 1219 | 63 / 63 | 211 | 29,120 | 1,896,421 | 1,636,706 | 5,164 |
| generic-8-roots | 72 | 1568 | 64 / 64 | 416 | 56,672 | 2,793,854 | 2,385,574 | 73,607 |
| collection-12 | 26 | 650 | 157 / 157 | 118 | 17,056 | 859,745 | 723,643 | 2,707 |
| template-12 | 26 | 650 | 157 / 157 | 118 | 17,056 | 1,045,033 | 752,303 | 2,774 |
| managed-warmup | 5 | 141 | 4 / 4 | 61 | 8,440 | 245,742 | 185,985 | 1,829 |

No compilation-profile detail was truncated (50,000-record cap). Full reports retain phases and exact supported counts.
The failed-one-root probe records two candidate attempts, two draft occurrences, two parameter-processing attempts,
and one diagnostic-root attempt. It produces no runtime and no activation. Template output/callback counting is not
currently a dedicated profiler counter; 12 generated worker definitions here are a workload fact, not inferred from steps.

## Candidate costs for the three items

**18, reuse investigation:** per-build signature validation calls are 24 (wide), 63 (diamond), 64 (generic), and 157
(collection/template), repeating across fresh same-schema builders. The generic graph requests factory specialization
16 times and materializes four within each build. Five-build cProfile captures show `_get_arg_info` calls 145 including
wide declarations versus zero during wide build-only; generic 115 including declarations versus 20 during build-only;
template 450 including declarations versus 360 during build-only (generated declarations occur inside preparation).
Registration parsing is therefore a different boundary from repeated occurrence validation. Signature validation is a
minority cost: ~18 ms cumulative across five generic builds versus ~955 ms total profiled self time, and ~45 ms across
five explicit collection builds versus ~351 ms. A broad cross-build cache is not justified by signature work alone.
Any narrow reuse design must preserve mutable annotations/defaults/signatures/global forward-reference bindings and
callbacks, and must exclude owner/value/runtime state. Large retained provider expansion is a stronger measured target.

**19, plan representation:** wide roots retain 24 registration steps plus 192 ordinary provider steps, 192 managed
provider steps, 144 ordinary collection steps and 144 managed collection steps. In five build-only cProfile invocations,
`_compile_provider_roots` has ~480 ms cumulative versus ~566 ms cumulative for `build` (~85%; nested values must never
be summed). `_provider_collection_root` is called 1,440 times; `_clone_component_tree` 1,920; `qualified_name` 36,480.
This eager provider/collection expansion dominates a small public graph and offers a concrete eligibility investigation.
Preserve graph occurrences, provider forms, explicit owner semantics, instance identities and managed-provider behavior;
removing provider availability or lazily compiling at runtime is not equivalent. Do not optimize by merging mutable
initializer state. Five generic builds clone 5,760 component-tree nodes. Shallow step bytes are only a small part of
traced retained memory, so reducing wrappers alone does not prove overall plan-memory improvement.

**20, budgets:** actual draft work is 1,080 / 1,219 / 1,568 for wide/diamond/generic while public graph counts are
24 / 63 / 72. Final graph visits, returned candidate steps, retained unique steps, specialization materializations and
compiler operations are distinct units. Count limits at operations before work, including synthesized provider clones,
preparation/template work and retries; never infer them from the public graph. The generic graph's maximum public path
has three components, the diamond six. `_finalize_plan` cumulative cProfile time across five build-only invocations is
~8 ms wide, ~53 ms diamond, ~83 ms generic, ~24 ms collection and ~22 ms template; `_census_inventory` is roughly
0.7–2.6 ms across five builds. Graph cloning, drafts, freezing and reporting remain part of the budget boundary even
when they are nested compiler work. Disabled-budget and runtime overhead require a later matching before/after check.

cProfile spans cover exactly five builds per shape: declaration+build includes registration, build-only excludes it,
and both exclude close. Cumulative timings include nested calls and are instrumentation-sensitive; only exact call
counts and broad attribution support these target choices. CompilationProfiler captures the full public build including
preparation/finalization with its own instrumentation. No claims mix these durations with unprofiled latency.

## Artifacts and verification

All raw captures stay outside Git. Timing outputs:

- `/tmp/compiler-optimization-before-{1,2}.json` and `.md` (~40 KiB JSON each): 17 compiler operations, 25 samples each;
- `/tmp/compiler-optimization-runtime-before-{1,2}.json` and `.md` (~10 KiB JSON each): four runtime controls, 25 samples each;
- `/tmp/compiler-optimization-smoke.{json,md}` and `/tmp/compiler-optimization-discovery.txt`: shaping checks;
- `/tmp/compiler-optimization-evidence.json` (~191 KiB): allocation samples, inventory and summarized cProfile;
- `/tmp/compiler-optimization-{shape}-compilation-profile.json` (~10–169 KiB): six full public build profiles;
- `/tmp/compiler-optimization-failed-compilation-profile.json` (~5 KiB): failure/retry profile;
- `/tmp/compiler-optimization-{shape}-{build,declarations}.prof` (~44–68 KiB each): 12 raw cProfile files.

CLI discovery and a focused smoke capture passed. Ruff and ty checks passed for both new modules. Direct fixture checks
verified all six builds, both related batches/overlays and the matrix with zero application activations. Fresh-build
iteration-fixture cleanup closes its yielded owner normally. No production implementation or runtime API changed.
See [benchmark commands](../benchmarks/README.md#compiler-optimization-baseline-items-1820).
