# Declared provider root preparation evidence

Step 2 makes automatic public provider forms an explicit application capability when
`build(provider_roots=...)` is supplied. `None` retains every existing family/form.
The worker, API, response processor, reporting worker and example-service Cop
composition roots use `provider_roots=()` after auditing their deferred handles
and framework root lookups. Their providers are injected directly or through
provider maps; framework resolution requests ordinary services/handlers.

A managed handle can enter a managed `ResolutionContext`, so private target
adapters remain necessary when managed acquisition is possible. The compiler
retains that closure for requested/marked/injected managed handles and conservatively
for inherited anchors or boundaries. If absence is proven, it omits all automatic
provider wrappers, views and managed conversions. All retained private work counts
against physical compilation budgets and profiler counters. Full mode reuses its
existing managed roots in the private closure.

The focused regressions cover all four families and all four target forms, public
capability restrictions, dependency-injected providers and maps, empty/default
collections, marked roots, aliases/names/fallbacks, closed generic requests, build
failures and reuse, private-context scalar/provider/collection lookup and cleanup,
observed execution, physical budgets, hidden boundary dependencies, orphan pruning
and overlay singleton ownership. A parent-aware runtime filter explicitly observes
the same managed-provider target view in both modes without replaying selection.

## Reproduction

```sh
uv run python benchmarks/declared_provider_roots_evidence.py --routes 128
uv run python benchmarks/declared_provider_roots_evidence.py --routes 128 --declared
uv run python benchmarks/declared_provider_roots_evidence.py --routes 128 --heap
uv run python benchmarks/declared_provider_roots_evidence.py --routes 128 --declared --heap
```

The workload has 128 public senders, a shared dependency-only middle/leaf path and
128 dependency-only transports restricted by their parent sender. Each run is a
fresh process. Timing uses three uninstrumented processes per mode; heap and
counter attribution use separate processes. Both modes resolve all 128 senders
with the correct transport implementation after the measured build. This is
synthetic compiler evidence; actual Cop installed-wheel measurements are separate.

Python 3.14.4, macOS arm64; package Python source SHA-256:
`e09fc8bbd6b46abc53f9ca25c1982bf4832fbf3e478ee0db553ace38c165e094`.
Raw samples are in `benchmarks/declared_provider_roots_results.json`.

| Measurement | Full compatibility mode | Declared mode, no managed acquisition |
| --- | ---: | ---: |
| Physical component records | 4,096 | 512 |
| Provider target view contexts | 2,048 | 0 |
| Public provider annotation keys | 2,048 | 0 |
| Private managed annotation keys | 512 | 0 |
| Median uninstrumented build seconds | 0.166589 | 0.081391 |
| Peak traced build bytes | 7,294,761 | 2,488,665 |
| Retained traced bytes | 6,797,170 | 2,105,985 |

Physical records decrease by 87.5%; traced peak decreases by 65.9% and retained
heap by 69.0%. Median synthetic build time decreases by 51.1%. These measurements
are workload-specific and do not predict the complete application's startup cost.
No deployment limit, package version or lockfile changes are required.

## Actual Cop installed-wheel comparison

Paired fresh processes compare the frozen step 1 and step 2 Clean IoC wheels
against their matching Cop source snapshots. Step 2's five composition roots
opt into `provider_roots=()`; the Bark wheel is identical in both stages. This
measures that combined library/application change, with normal diagnostics and
no runtime profiling. Python 3.14.4, macOS 26.7.1 arm64. Each normal median and
RSS range uses three processes per application/stage; allocation tracing uses
one separate worker process per stage.

| Application / measurement | Step 1 | Step 2 |
| --- | ---: | ---: |
| API median normal build seconds | 0.762964 | 0.461392 |
| API peak RSS range, MiB | 234.1–238.2 | 225.0–227.2 |
| API physical component records | 10,032 | 5,240 |
| API provider view contexts | 3,220 | 0 |
| Worker median normal build seconds | 5.264095 | 4.239437 |
| Worker peak RSS range, MiB | 396.2–437.5 | 384.2–456.0 |
| Worker physical component records | 66,225 | 59,353 |
| Worker provider view contexts | 4,220 | 0 |
| Worker traced retained bytes after GC | 53,074,137 | 43,301,429 |
| Worker traced peak build bytes | 187,139,483 | 187,139,768 |

Normal median build time decreases by 39.5% for API and 19.5% for worker. The
worker's traced retained heap decreases by 18.4%, while its traced peak is
essentially unchanged (285 bytes higher). Worker RSS ranges overlap; these
samples do not establish a reliable reduction in worker process peak RSS.
The traced retained allocation and traced build peak are separate measurements.

Sanitized raw samples and source/wheel SHA-256 identities are preserved in
`benchmarks/declared_provider_roots_application_results.json`. Absolute local
and temporary paths have been removed. Downstream application suite results
are tracked separately from these measurements.

Validation: full `make ci` succeeds, including 1,920 tests, lint, formatting, type
checking, documentation examples and benchmark discovery. Step 2 adds 62 focused
provider declaration regressions. No runtime compilation or graph mutation is
introduced.

Downstream installed-wheel checks also pass: Bark 5,941 unit tests (26 skips),
Cop 494 unit tests, and all 64 Cop integration tests (384.59 seconds). All five
hosts start within the existing integration readiness timeout; all four catalogue
capacity cases pass their unchanged shared-process memory assertions. These are
macOS checks with development wheels, not verification of the locked dependency
set or the deployed Linux resource budget.

The step 2 reference Linux image was also tested with Gunicorn at 512 MiB,
100m CPU, no swap and the unchanged 120-second readiness deadline. The API was
ready in 89.80 seconds with a 335,831,040-byte cgroup peak (320.27 MiB) and no
memory-limit events. The worker was not ready at the deadline; its cgroup peak
reached 536,870,912 bytes (512 MiB), with 78 `max` events and no OOM/kill. Every
observed CPU period was throttled in both runs. This is not a deployment pass:
the configured `ghcr.io/bark-com/ubuntu:3.14.4` ARM64 image still fails to import
`compression.zstd` because Python's `_zstd` extension is missing. The reference
image uses Python 3.14.4 slim to isolate compilation/startup from that image defect.
