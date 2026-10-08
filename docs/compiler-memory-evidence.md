# Compiler memory evidence — 7 October 2026

For the latest measured state, see
[the sequential runtime-build evidence](runtime-build-series-evidence.md).
It includes the subsequent production options, signature-parser fix, actual-host
adoption and draft-capacity release. Measurements below are historical.

The subsequent [early rejection allocation change](early-rejection-records-evidence.md) removes proven
early-rejected physical records in ordinary builds and preserves them in diagnostic builds. Its isolated
before/after evidence is separate from the historical comparisons below.

## Latest combined result — all five follow-up changes

The final installed **development** wheels include reusable graph path indexes,
compiler-local diagnostic names, early eligibility in Bark/Cop, five dependency-only
internal provider maps, and proven invariant subplan reuse. Three alternating fresh
installed-wheel samples per app show worker build time of **6.2177–6.3208 s** after
all five changes, versus **6.8317–6.8961 s** with changes 1–4. The additional reuse
reduces worker build time by about 9%; overlapping process RSS ranges do not
establish an isolated, repeatable Cop memory reduction for change 5.

Clean IoC CI, final Bark unit tests and final Cop unit tests passed. The final full
Cop integration run passed all 64 tests in 405.62 s, including all four unchanged
catalogue memory assertions and all five application hosts. The earlier changes
1–4 integration result is retained as historical evidence.
Linux/deployment acceptance remains unpassed: the configured ARM64 base image fails
before compilation because `_zstd` is missing, and the diagnostic reference image's
worker does not become ready within the unchanged 120-second window at 512 MiB/100m.
Clean IoC rc2 remains unpublished and downstream locks still select the original
released dependencies. See [the detailed combined follow-up evidence](compiler-combined-evidence.md)
and [sanitized raw combined measurements](../benchmarks/compiler_combined_results.json).

## Historical measurements below

The following sections preserve the original compiler-memory revision and its
then-current development-wheel results. Their “final” measurements and outstanding
work refer to that historical revision; the combined follow-up above supersedes
its current-status claims without replacing the original evidence.

This revision reduces automatic compiler allocation and adds explicit early eligibility. It does **not** establish the 512 MiB / 100m deployment gate. The worker still exceeds the memory budget in macOS development measurements.

## Implementation and opt-in changes

- Automatic provider roots use one immutable parent-aware target context per selected target, with no physical descendant copies. Every public scalar, list, tuple and set form of Provider, AsyncProvider, ManagedProvider and AsyncManagedProvider remains prepared during build. Views remap parent, decorator, owner and explanation references; runtime steps retain selected targets. Managed conversion memoization retains its source steps to prevent recycled identity collisions.
- `register_provider_map(..., root_policy="dependency_only")` applies ordinary root-policy validation and semantics across the implementation, overloads and bundle protocol. The default remains `"resolvable"`. Pure dependency-only definitions no longer generate even empty automatic provider collection families. Selected maps and contributions still validate completely.
- `candidate_when=` is explicit early eligibility using structured `cf` predicates. Known false excludes only that request context. Unknown expressions, including unresolved generic bindings, receive full compilation and normal callback short-circuit evaluation. Existing `when` and `select` keep their validation contract. Cross-boundary eligibility hides external consumer parents.
- Proven equivalent registration activation steps share immutable executables after complete per-occurrence compilation, validation and selection. Keys include actual registration/layer identity, closed binding, step type, runtime and cleanup owners, and selected dependency-step identities/names. Decorated, configured, provider-map and per-call targets bypass sharing. Opaque callbacks still execute per use; this cache does not skip candidate compilation or merge runtime caches. Runtime profiling binds observations to the actual occurrence.
- Freezing releases drafts as records are created. Generic-map lookup uses typetoolbox’s read-only API lazily. Immutable explanation mappings transfer into final inspection without repeated dictionary copies. Argument paths and the richer ownership presentation are rendered on inspection. Mandatory ownership/captive validation still runs during compilation; rejected/intermediate graph records are retained.
- `CompilationProfiler(max_records=0)` now includes definition, registration and root aggregates, physical record/view counts, provider adapters/copies, eligibility rejections and template reuse. Budget occurrences count physical records plus view contexts; full logical target depth remains checked.

## Synthetic growth

Baseline source: `ee00bf9` (`version2`, 2.0.0rc2), archived without changing the checkout. Candidate: this revision. Python 3.14.4, macOS 26.7.1 arm64. Each row uses a fresh process and `CompilationProfiler(max_records=0)`. Timings and peak RSS from separate uninstrumented runs are retained in the raw results.

| Shape | Baseline physical records | Candidate records | Candidate view contexts | Baseline / candidate subtree compilations | Baseline / candidate retained registration templates |
| --- | ---: | ---: | ---: | ---: | ---: |
| Leaf → Middle → Root | 186 | 90 | 48 | 6 / 6 | 6 / 3 |
| Two parent-specific transports (legacy when) | 282 | 66 | 32 | 10 / 10 | 6 / 6 |
| 32-node chain; one public root | 1,357 | 61 | 16 | 33 / 33 | 33 / 33 |
| 32 independent routes; shared infrastructure | 3,712 | 1,056 | 512 | 160 / 160 | 160 / 36 |
| 32 sender-specific transports (legacy when) | 10,008 | 6,048 | 512 | 5,152 / 5,152 | 192 / 68 |
| 32 sender-specific transports (candidate_when) | 10,008 | 2,080 | 512 | 5,152 / 192 | 192 / 68 |

The small chain keeps 48 provider request keys and unchanged 6 candidate attempts / 9 selection callbacks. The two-transport reproduction keeps correct transport selection and unchanged 10 candidate attempts / 16 selection callbacks. Its pure dependency-only internals now create no independent provider families.

| Growth shape | Size | Baseline records | Candidate records + contexts | Candidate unique / reused compiled registration templates |
| --- | ---: | ---: | ---: | ---: |
| chain | 4 | 209 | 33 + 16 | 5 / 0 |
| chain | 8 | 373 | 37 + 16 | 9 / 0 |
| chain | 16 | 701 | 45 + 16 | 17 / 0 |
| chain | 32 | 1,357 | 61 + 16 | 33 / 0 |
| routes | 4 | 548 | 132 + 64 | 8 / 12 |
| routes | 8 | 1,000 | 264 + 128 | 12 / 28 |
| routes | 16 | 1,904 | 528 + 256 | 20 / 60 |
| routes | 32 | 3,712 | 1,056 + 512 | 36 / 124 |
| senders (early eligibility) | 4 | 796 | 148 + 64 | 12 / 12 |
| senders (early eligibility) | 8 | 1,632 | 328 + 128 | 20 / 28 |
| senders (early eligibility) | 16 | 3,784 | 784 + 256 | 36 / 60 |
| senders (early eligibility) | 32 | 10,008 | 2,080 + 512 | 68 / 124 |

For the 32-node single-root chain, provider support retains 28 adapter/collection records plus 16 contexts, irrespective of target depth. For 32 routes, retained registration templates fall from 160 to 36. With 32 sender policies, early eligibility rejects 992 unrelated candidates and reduces actual subtree compilations from 5,152 to 192. The compact rejection records still grow with the declared candidate cross-product; the report does not claim linear complexity for those comparisons.

Actual shallow retained record/context storage falls from 347,392 to 16,512 bytes for the 32-node chain, and from 950,272 to 299,008 bytes for 32 independent routes. These lower bounds exclude dictionaries, edges, steps, explanation payloads, Python objects and allocator overhead. Physical allocation reduction is demonstrated independently of the revised budget unit; it is not a counter-only improvement.

## Pinned Cop development comparison

Reference worktree: `/Users/peter.daly/.codex/worktrees/registration-partitions-main/data-protection-cop`. Cop `97011b424a439297eaf7e90c73023e2a7f89573c`; Bark `beb28b53bbee725cb70cb9d44c0388b5cbcb868a` (1.0.0b1); Python 3.14.4. The original shared `/Users/peter.daly/WS/bark/data-protection-cop` checkout had drifted to a 1.24.0 lock and was not used for this comparison. Both shared checkouts and their environments were preserved.

Baseline and candidate use disposable source archives and separate environments under `/tmp`. Baseline dependencies were synchronized from the reference committed lock with Clean IoC 2.0.0rc1. Candidate changes only the installed Clean IoC distribution to a built development 2.0.0rc2 wheel, without editing the Cop lock or application composition. This substitution is development evidence, not released Cop acceptance. The supplied report settings JSON was loaded identically without printing values; Config construction precedes timing.

Uninstrumented probes call the normal `get_container(Config())` for API and worker, start `time.monotonic()` immediately before the call, and capture process peak `resource.getrusage(RUSAGE_SELF).ru_maxrss` (bytes on Darwin). No compiler monkey-patches or profiler are installed. Each sample starts a fresh process. Imports, settings construction and process startup are excluded from elapsed build time but can contribute to process high-water RSS.

| App | Baseline build time | Final development-wheel build time | Baseline peak RSS | Final development-wheel peak RSS |
| --- | ---: | ---: | ---: | ---: |
| API | 8.88–9.05 s | 6.70–6.93 s | 667.56–671.14 MiB | 396.78–437.23 MiB |
| WORKER | 47.98–50.25 s | 29.14–29.24 s | 2,478.11–3,047.38 MiB | 1,593.02–1,691.02 MiB |

Raw samples include exact wheel SHA-256 and platform metadata. Fresh-process Darwin high-water values vary; these runs are not retained-heap measurements or CPU-limited Linux readiness measurements. Earlier development-wheel samples are kept separately in the raw file.

Independent profiled observations (never compared as acceptance timing) reproduce the report’s baseline counters. API physical records fall from 116,095 to 19,435, with 3,812 compact target contexts. Worker physical records fall from 802,981 to 151,633, with 4,764 contexts. Provider-induced target copies are zero. Worker candidate compilation attempts remain 127,451, parameter processing attempts remain 78,587, and selection callback calls remain 208,237: existing validation was preserved. The worker records 27,641 unique compiled registration activation templates and 99,810 reuses. These are compiler-work counts; actual retained templates are separately inventoried in the synthetic probe.

## Verification and remaining work

`make ci` passed: Ruff lint/format, ty, 1,762 tests, documentation examples, and BenchBro discovery. New semantic coverage includes every provider family/form; parent-aware graph inspection and exported manifests; lazy explanations and ownership reports; no runtime compiler calls; unused/consumed/named maps, invalid root policies, boundaries and nested overlay contribution order; early exclusion versus legacy missing-dependency validation and independently required roots; unknown/AND/OR/NOT callback order; unresolved generic facts; closed generic bindings; all applicable operation executors; managed conversion collection forms; and transient/per_resolution/scoped/singleton identities. Existing full suites cover selected missing/generic/circular/captive failures, frozen parent/overlay singleton ownership, managed acquisitions, async cleanup and partial failures. Constructors/factories remain inactive during build.

The pinned Bark dispatcher compilation-budget regression also passed (2 tests), using the installed candidate wheel, including its bounded missing-storage diagnostics. The Cop unit/integration release-acceptance suites were not claimed or substituted by these development measurements.

Bark must separately adopt dependency-only map declarations for suitable internal route helpers/contributions and apply `candidate_when` to valid contextual transport eligibility. Preserve public validation/direct-resolution handler roots, per-route provider-map groups, closed saga executor keys, all inventory-saga roots, nested overlay merge order and duplicate-key/precedence rules. Do not aggregate maps broadly or blanket-disable handler roots. No Bark/Cop composition or downstream release was modified here.

The worker retains substantial legacy candidate/intermediate metadata and still compiles its unrelated subtrees until explicit early eligibility is adopted. Executable sharing does not make those occurrences disappear. Further compiler work could prove context-independent subplan compilation reuse and deduplicate diagnostic payloads; opaque callbacks, selection contracts and failure evidence constrain that work. Reachability alone does not justify dropping rejected evidence.

Linux acceptance is outstanding. The reference Dockerfile installs the committed lock, which still selects rc1; a normal candidate application image requires the separate Clean IoC/Bark release and Cop dependency update. No application deployment/readiness run at unchanged 512 MiB / 100m limits, cgroup measurement, OOM check or startup-timeout validation was performed. Workstation memory and build times do not establish that gate. No limits/timeouts/assertions were changed, validation was not disabled and no handlers were removed.

After the separate Bark v1_rc update/publication, Cop must lock that released revision with no source overrides, run full unit/integration suites, and measure normal Linux startup through readiness with unchanged limits.

## Reproduction artifacts

- `benchmarks/compiler_memory_evidence.py`: standalone chain/route/sender probes; `--profile` uses zero spans, `--early` enables explicit eligibility.
- `benchmarks/compiler_memory_results.json`: fresh-process synthetic samples, physical storage, actual retained templates and compilation counters.
- `benchmarks/cop_compiler_memory_evidence.py`: reproducible normal Cop API/worker probe, using the selected interpreter and installed library; optional zero-span profiling and explicit settings/project paths.
- `benchmarks/compiler_memory_cop_results.json`: baseline, earlier development, and final-wheel uninstrumented Cop samples.
- `benchmarks/compiler_memory_cop_profiles.json`: separate profiled Cop counters/phases and allocation evidence.
- `/tmp/ioc-memory-final-ci.log`: local complete CI output.
- `/tmp/ioc-memory-final-wheels/clean_ioc-2.0.0rc2-py3-none-any.whl`: measured development wheel; package version was not bumped or published.


## Latest followup: optional diagnostic capture

[Optional compiler diagnostics evidence](optional-diagnostics-evidence.md) records the latest same-wheel off/on
comparison and preserves the historical measurements above. Three fresh worker samples per mode measured
5.39–5.45 seconds / 410–430 MiB with diagnostics off, versus 6.19–6.32 seconds / 470–506 MiB with capture on;
physical record/view counts were unchanged. API RSS did not show a reliable improvement. Final Bark unit checks passed
5,941 tests (26 skipped), Cop unit checks passed 494 tests, and the full Cop integration suite passed 64 tests
with the four original catalogue-capacity cases and all five host readiness checks unchanged. The actual worker heap
comparison saved 52.415 MiB (44.614%) after GC and 56.263 MiB (22.837%) at traced peak.

The ARM64 Python 3.14.4-slim Linux reference API became ready at 89.388 seconds under the unchanged 512 MiB / 100m
limits. The worker did not become ready within 120 seconds, reached the 512 MiB memory cap and recorded 112 memory-max
events without an OOM kill. This is not successful worker or configured-image acceptance; the configured base's missing
Python `_zstd` extension remains unresolved. That followup contains completed integration and actual-worker heap results; configured-image and constrained-worker
readiness acceptance remain unresolved.
