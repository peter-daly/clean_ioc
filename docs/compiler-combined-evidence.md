# Combined compiler follow-up evidence — 7 October 2026

All five sequential implementation changes are complete, with combined installed
development-wheel unit verification. The final worker builder is measurably faster,
but release coherence and Linux deployment acceptance remain outstanding. Final
Cop integration passed all 64 tests in 405.62 s (0:06:45).

The [original evidence report](compiler-memory-evidence.md) retains historical
measurements. [Sanitized combined results](https://github.com/peter-daly/clean_ioc/blob/version2/benchmarks/compiler_combined_results.json)
contain exact fresh-process samples, wheel hashes, base heads, final work counters,
and relevant Linux resource measurements without settings or unrelated filenames.

## Combined changes and preserved behavior

1. Graph-owned occurrence path indexes reuse inspection traversals. Entry-point
   and all-root views retain their own path precedence, and boundary resets remain
   correct. Repeated explanations avoid rebuilding the full path index.
2. Compiler-local diagnostic names cache recursive type labels during one build.
   Identity keys retain sources, closed generic bindings remain distinct, and no
   global cache or compiler object remains attached to the frozen plan. GC-disabled
   success and failed-budget retention regressions continue to pass.
3. Bark adopts 43 and Cop adopts three explicit `candidate_when` filters where
   structured parent eligibility can reject an unrelated candidate before compiling
   its dependency subtree. Unknown/contextual work still receives ordinary
   evaluation and full validation. Existing opaque callbacks preserve per-use
   behavior and short-circuit order.
4. Five internal Bark provider maps use `dependency_only`, avoiding unused root
   provider families. Route **contributions remain public** because command/reply
   consumer registries discover them through `scope.components`. This does not
   privatize contribution roots or collapse closed executor groups.
5. Proven invariant subplans reuse validated executable and diagnostic payloads
   before repeated dependency compilation, with fresh occurrence records. Keys
   include actual registration/layer and closed type identities, boundary and
   retention context. The full registration footprint prevents hidden stack
   cycles. Opaque/contextual descendants, providers/maps, slots, runtime context,
   per-call plans, anchored descendants, resolution requests, decorators and
   pre-configurations conservatively fall back. External promoted cleanup owners
   also force ordinary compilation. See [the reuse evidence](invariant-subplan-evidence.md).

API inventory-saga roots remain required for synchronous admission and progress.
Route precedence, command/reply fanout, saga executor applicability, async/managed
cleanup, scope/overlay identity and complete validation are retained. No handlers
or user capacity assertions were removed, and deployment memory, CPU and readiness
limits were unchanged. The 28-route/7-saga compiler budget regression is tightened
to 6,000 graph occurrences and uses 5,670, retaining all discovery roots.
`CompilationBudget(graph_occurrences=6_000)` counts physical component records
plus provider-view contexts; it does not count only physical records.

## Installed development-wheel provenance

The Clean IoC source base is `3d576f10427d506b414889af21ad95291c39cccf` on
`version2`; Bark is based on `beb28b53bbee725cb70cb9d44c0388b5cbcb868a` on
`v1_rc`; the pinned Cop verification checkout is based on
`97011b424a439297eaf7e90c73023e2a7f89573c`. All implementation/composition edits
remain uncommitted. Raw provenance includes the captured tracked-diff hashes,
without listing unrelated Cop untracked files.

| Installed development artifact | SHA-256 |
| --- | --- |
| Clean IoC for stage4 (compiler changes 1–2; unchanged library through stages 3–4) | `c5ff629bff6902d70f75793dc6aa372b65da077335d42f30b48a9e003c55cc84` |
| Final Clean IoC stage5 | `845779a6cab18b147d7558cbd5363b3f308650c5b1709acd14999edf8e312531` |
| Bark stage4, also used with final Clean IoC | `047d046561f219b331cd812feb2c52fe9883de070226e1b4ed602222012bf758` |

Both Clean IoC wheels identify as `2.0.0rc2`; Bark identifies as `1.0.0b1`.
Hashes distinguish these local development artifacts. They are not published
release artifacts, and the measured environments use installed wheels from
`site-packages` with no `PYTHONPATH` or source overrides.

## Paired macOS builder measurements

Python 3.14.4, macOS 26.7.1 ARM64; three fresh processes per app/stage, alternating
stage order, with the same Cop source and Bark wheel. Stage4 includes changes 1–4;
stage5 adds only the invariant reuse implementation. Normal probes call
`get_container(config)` without profiling. Imports and settings construction
precede the timer; settings are supplied privately and were not printed.

| App | Stage4 build-only time | Stage5 build-only time | Stage4 process peak RSS | Stage5 process peak RSS |
| --- | ---: | ---: | ---: | ---: |
| API | 0.8647–0.8775 s | 0.8204–0.8327 s | 194.02–194.41 MiB | 196.20–241.94 MiB |
| Worker | 6.8317–6.8961 s | 6.2177–6.3208 s | 490.45–582.80 MiB | 478.63–562.61 MiB |

The worker's additional build-time reduction is about 9% across these samples.
Worker RSS ranges overlap and API RSS does not improve; no reliable isolated Cop
RSS reduction is demonstrated for change5. Workstation high-water RSS is variable,
includes imports/settings and allocator behavior, and does not establish runtime
headroom in a 512 MiB Linux deployment.

An independent final installed-wheel worker profile confirms the actual skipped
work. Its timing is instrumented and is not compared against normal builder timing.

| Final worker work/allocation measure | Count |
| --- | ---: |
| Candidate definitions considered | 63,280 |
| Candidate compilation entries, including early lookup | 37,935 |
| Actual registration subplan bodies compiled | 17,421 |
| Early invariant subplan cache hits | 20,514 |
| Parameter processing attempts | 34,910 |
| Selection callbacks executed | 82,558 |
| Physical component records | 91,570 |
| Provider view contexts | 4,220 |
| Provider-induced target copies | 0 |
| Independent post-compilation executable intern hits | 64 |

Before change5, stage4 worker entries were 48,586, parameter attempts 46,025 and
selection callbacks 103,860. Fresh occurrence records remain allocated: early
reuse skips actual dependency compilation and shares immutable diagnostic payloads,
without hiding physical records in a revised counter. Selection history/census
reports actual evaluation and does not fabricate cached-descendant callback attempts.

The isolated 64-route synthetic experiment separately demonstrates a real allocation
benefit: traced peak allocations fall from 28,232,542 to 10,489,767 bytes, while
physical records remain 9,984. This controlled allocation result is distinct from
the noisier application's process RSS measurements.

## Combined verification

| Check | Latest result |
| --- | --- |
| Clean IoC `make ci` | 1,805 passed; lint, formatting, typing, graph policy, docs examples and benchmark discovery passed |
| Final Bark unit suite | 5,941 passed, 26 existing skips; 92.91 s |
| Final Cop unit suite | 494 passed, including two new regressions; 41.47 s |
| Bark public API check | Passed with the formatter available on `PATH` |
| Bark broad typing | Five pre-existing errors; changed production code and new tests clean |
| Earlier stage4 full Cop integration | 64 passed in 396.51 s; all original capacity assertions unchanged |
| Final full Cop integration | 64 passed in 405.62 s (0:06:45); all four original catalogue memory assertions passed unchanged |

Clean IoC coverage includes each provider family/form, contextual and opaque
callback fallback, parent/argument/owner paths, generic and alias identities,
failed/retried/circular/captive validation, full-depth/physical budgets, cleanup,
overlay anchors, runtime occurrence profiling and compiler lifetime. Bark/Cop
regressions preserve route discovery, precedence/fanout and the inventory-saga roots.
The final integration run started all five application hosts and passed the
access, deletion and inventory workflows. All four original catalogue memory
assertions passed unchanged.

## Linux startup diagnosis at unchanged limits

The configured `ghcr.io/bark-com/ubuntu:3.14.4` ARM64 image fails a direct
`from compression import zstd` import with missing `_zstd`, before container
compilation. Its recorded digest is
`sha256:b80e1db51da5cde244cb0aae087c7e6a992f8d691747a704630ab1a370ff6160`.
This independently confirmed base-image issue blocks the configured-image run.
The deployed production architecture has not been established; the result describes
the examined ARM64 image only. No application compression fallback was introduced.

A `python:3.14.4-slim` ARM64 reference image allows diagnosis with the same installed
development wheels, Cop source and support dependencies. It is not the configured
deployment image and cannot establish acceptance for that image. Actual Gunicorn
startup was measured with Docker memory 512 MiB, swap zero, CPU 0.1 (100m), and the
unchanged 120-second readiness window.

| Final reference-image host | Ready in window | Observed time | Whole application cgroup memory peak | OOM observed |
| --- | --- | ---: | ---: | --- |
| API | Yes | 89.817 s to readiness | 354,549,760 bytes / 338.13 MiB | No |
| Worker | **No** | 121.368 s observation; deadline exceeded | 530,903,040 bytes / 506.31 MiB | No within this observation window |

The worker was essentially continuously CPU-throttled: 1,240 of 1,241 reported
periods were throttled, with 12.40 CPU-seconds used by the observation. Absence of
an OOM in this window does not establish later safety or startup success. The
worker's unchanged readiness gate did not pass.

These Linux numbers are whole application cgroup high-water measurements, including
Gunicorn and startup work. They differ from build-only stopwatch measurements and
Darwin process RSS. The API reference-image result cannot compensate for the worker
failure or configured-image import blocker. **Linux/deployment acceptance remains
unpassed**, and no resource limit, timeout, capacity assertion or handler set was
relaxed to obtain these results.

## Release gate and reproduction artifacts

Clean IoC `2.0.0rc2` remains unpublished. Bark/Cop manifests and locks still reference
rc1 and the original Bark pin, so these installed development wheels do not represent
a coherent released dependency lock. No updated published `v1_rc` revision, artifact
URL or release acceptance is claimed. Publication and a coherent downstream lock
update must precede release-like acceptance with those released artifacts.

The verification runner preserves exact local scripts and Dockerfiles under the
private evidence root `bark-ioc-sequential-uqaff4c3`: `paired_probes.py`,
`linux_startup.py`, `Dockerfile.reference`, and the results named in the sanitized
combined JSON. Local settings/env files are intentionally excluded. Reproduction
requires the pinned source bases plus uncommitted implementation changes, the wheel
hashes above, identical privately supplied settings and support services; it must
keep installed-wheel routing and the original memory/CPU/readiness limits.
