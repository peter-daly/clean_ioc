# Sequential runtime-build optimization evidence

Measured 8 October 2026. All six proposed changes were assigned to separate
GPT-6.1-Sol High agents and implemented sequentially, with an installed-wheel
Cop comparison after each. A seventh separately measured change addresses a
signature-parser allocation hotspot discovered during this work. An eighth
step forwards the production options through the actual Bark host helpers,
after Linux verification exposed a path bypassing the direct container helper.
A ninth memory-only step releases an empty draft dictionary's retained capacity.
The user then prioritized memory and deferred build-time optimization; extended
Linux observations measure memory through readiness without changing application
settings or claiming the earlier readiness deadline passes.

## Final actual-host macOS result

| Application | Median host initialization | Fresh-process peak RSS range | Physical graph records |
| --- | ---: | ---: | ---: |
| API | 0.367 s | 212.08–215.34 MiB | 3,528 |
| Worker | 3.500 s | 217.55–220.80 MiB | 51,834 |

Steps 8–9 measure the actual `apps.api.app` and `apps.worker.app` modules after
loading their configuration/container modules and Bark bootstrapping imports.
The timed interval includes module-level configuration construction, builder
composition, host setup and installation. Each stage/application has three
normal samples; a separate worker sample uses tracemalloc. The host wrapper
and supervisor add seven physical records to the worker compared with its
direct container builder. These times are not comparable to the shorter
measurement boundary in steps 1–7.

The final host worker retains 35,932,944 traced bytes (34.27 MiB) after GC and
peaks at 53,012,388 traced bytes (50.56 MiB). The normal RSS figures above
come from untraced processes.

## Direct-container results after step 7

| Application | Median build time | Fresh-process peak RSS range | Physical graph records |
| --- | ---: | ---: | ---: |
| API | 0.313 s | 207.52–211.19 MiB | 3,528 |
| Worker | 3.400 s | 218.84–219.78 MiB | 51,827 |

These are three normal fresh-process samples per application, using the actual
Cop `get_container(config)` composition roots. The final worker's separate
traced allocation peak is 55,537,218 bytes (52.96 MiB); retained allocations
after garbage collection are 38,469,996 bytes (36.69 MiB). Traced allocations
are not RSS and exclude imports and configuration construction.

## Measurement method and provenance

The pinned Cop checkout starts at `97011b424a439297eaf7e90c73023e2a7f89573c`;
Bark starts at `beb28b53bbee725cb70cb9d44c0388b5cbcb868a`; Clean IoC starts at
`3d576f10427d506b414889af21ad95291c39cccf`. Each stage freezes its application
source snapshot and installs the corresponding Clean IoC and Bark wheels into
one Python 3.14.4 environment with fixed support dependencies. Stages are
alternated across three fresh processes per application. Traced worker samples
run separately from normal timing/RSS samples. No dependency source overrides
or `PYTHONPATH` overrides are used. Measurements run without concurrent test
or benchmark workloads. Platform: macOS 26.7.1 ARM64.

Timing and tracing start after application imports, configuration creation and
a garbage collection. They surround the actual `get_container(config)` call,
including builder composition and compilation. Process peak RSS includes prior
imports. Retained traced memory is sampled after garbage collection while the
container remains live. Each pair has one separately traced worker sample per
stage; normal timing is the median of three samples.

The starting baseline already includes prior compiler and optional-diagnostics
optimizations. It is not the original rc1 trial (reported API 676.20 MiB and
worker 2,685.12 MiB). Those older figures are historical, not a controlled
before/after comparison for this series.

## Measurements after each step

Each row below uses that step's own paired experiment. Ordinary run-to-run
variation means rows should not be treated as a single uninterrupted trend.
All before/after samples, stage hashes and wheel identities are retained in
[`runtime_build_series_results.json`](../benchmarks/runtime_build_series_results.json).

| Step | Change | API median s | Worker median s | Worker peak RSS range MiB |
| --- | --- | ---: | ---: | ---: |
| 0 | Starting baseline | 0.766 | 5.408 | 408.75–437.05 |
| 1 | Skip definite early rejections | 0.739 | 5.216 | 396.12–496.03 |
| 2 | Declare public provider forms | 0.461 | 4.239 | 384.17–455.97 |
| 3 | Separate selected registrations from public roots | 0.356 | 3.894 | 383.31–417.47 |
| 4 | Release overlay composition in compact mode | 0.370 | 3.861 | 383.22–392.33 |
| 5 | Defer reachability advisories; omit histories | 0.350 | 3.977 | 387.55–439.17 |
| 6 | Avoid diagnostic retries after failure | 0.345 | 3.799 | 381.88–424.84 |
| 7 | Skip signature checks for empty dependencies | 0.313 | 3.400 | 218.84–219.78 |

| Step | API records | Worker records | Worker traced retained MiB | Worker traced peak MiB |
| --- | ---: | ---: | ---: | ---: |
| 0 | 11,910 | 91,570 | 65.07 | 190.00 |
| 1 | 10,032 | 66,225 | 50.62 | 178.47 |
| 2 | 5,240 | 59,353 | 41.30 | 178.47 |
| 3 | 3,528 | 51,827 | 37.58 | 178.47 |
| 4 | 3,528 | 51,827 | 36.74 | 178.47 |
| 5 | 3,528 | 51,827 | 36.69 | 178.47 |
| 6 | 3,528 | 51,827 | 36.70 | 178.47 |
| 7 | 3,528 | 51,827 | 36.69 | 52.96 |

Steps 1–3 reduce physical graph growth and retained metadata. Steps 4–5 provide
smaller retention savings in this application and no reliable peak or timing
improvement. Step 6 improves failure handling only: the 120-invalid-root
synthetic workload drops from 841 compilation attempts to one, with no
successful-build saving. Step 7 produces the large remaining startup-peak
reduction while leaving the execution graph and retained allocations unchanged.

In step 7's paired Cop experiment, worker peak RSS falls from 382.41–386.16 MiB
to 218.84–219.78 MiB, median build time from 3.766 to 3.400 seconds, and traced
peak from 187,126,382 to 55,537,218 bytes (70.3% lower).

## Why the memory ballooned

The compiler validated dependency argument names repeatedly, even when the
dependency mapping was empty. Python 3.14's built-in signature parser copies
`sys.modules`; a near-peak diagnostic snapshot attributed approximately
123.61 MiB to 2,496 such temporary allocations. The snapshot changes garbage
collection behavior and is diagnostic evidence, not the paired peak metric.

A separate actual worker counter observed 2,812 built-in text-signature parses.
Of these, 2,803 came from `_validate_dependency_names` with an empty dependency
mapping: 1,996 for `UtcDatetimeProvider`, 550 for `ResolveQueueNameFromHeader`,
253 for `HeaderBasedPrefixResolver`, and four for `SystemMonotonicClock`.
The two-line guard removes all 2,803. Nine unrelated registration/composition
parses remain. Registration-time signature analysis and missing-dependency
validation continue; configured argument names still undergo the existing
validation. There is no new cache, forced garbage collection or runtime flag.

## Production and validation examples

All five Cop composition roots now use:

```python
container = get_builder(config).build(
    provider_roots=(),
    allow_scope_builders=False,
    check_unreachable=False,
    aggregate_errors=False,
)
```

Diagnostics are off by default. Injected providers and provider maps still
compile; `provider_roots=()` omits unrequested public provider forms. Ordinary
scopes, slots, resource ownership, warmup and cleanup remain available. Compact
runtimes cannot create registration-changing scope builders. The selected
registration catalogue supports Bark discovery without making private route
contributions public roots.

For full validation of the same public resolution surface:

```python
with get_builder(config).build(
    diagnostics=True,
    provider_roots=(),
    allow_scope_builders=False,
    check_unreachable=True,
    aggregate_errors=True,
) as container:
    report = container.validation_report()
```

`validation_report()` also recovers deferred unreachable-component warnings
from an already-built compact runtime, without selector or constructor replay.
The no-retry option only avoids independent root recompilation after failure;
preparation findings, build-rule reports and essential validity checks remain.
An invalid build always fails and leaves its builder reusable. Full diagnostic
collection requires building with the diagnostic/aggregation options, since an
already-failed production build has no completed runtime to inspect.

## Step 8: actual host adoption

The live worker, reporting worker, response processor and example service
called `build_daemon_app(get_builder(config))`. That helper still used default
`builder.build()` options, so the direct `get_container()` optimization did
not reach these live hosts. The API already used `get_container()`.

Bark now exposes immutable `ContainerBuildOptions`, accepted by daemon,
FastAPI and job host helpers. Defaults remain compatible. Cop shares one
options value between all five direct builders and its four daemon apps:

```python
from bark_core.bootstrapping import ContainerBuildOptions, build_daemon_app

CONTAINER_BUILD_OPTIONS = ContainerBuildOptions(
    provider_roots=(),
    allow_scope_builders=False,
    check_unreachable=False,
    aggregate_errors=False,
)

container = CONTAINER_BUILD_OPTIONS.build(get_builder(config))
# Alternatively, in the separate daemon composition root:
app = build_daemon_app(get_builder(config), build_options=CONTAINER_BUILD_OPTIONS)
```

The two lines show alternative composition roots, not two containers to build
inside one application. Host registrations still precede compilation.

| Actual worker host metric | Step 7 | Step 8 |
| --- | ---: | ---: |
| Median initialization seconds | 4.390792 | 3.746252 |
| Normal peak RSS range MiB | 229.23–231.41 | 218.86–219.56 |
| Physical records | 57,626 | 51,834 |
| Provider view contexts | 3,164 | 0 |
| Traced retained bytes | 47,610,601 | 38,554,145 |
| Traced peak bytes | 66,974,206 | 55,631,448 |

Public ordinary components (212) and selected catalogue entries (334) remain
unchanged. Worker median host initialization falls 14.7%; retained traced
allocations fall 19.0%. API host timing is similar (0.364 to 0.373 seconds),
with unchanged graph counts. All 14 raw paired samples and detailed method
are in the Bark host evidence linked below.

## Step 9: release empty draft-table capacity

The actual worker heap diagnosis found that graph freezing popped every draft
but retained the now-empty dictionary's allocated hash table. Calling `clear()`
after the freeze loop releases that capacity without changing any immutable
record or runtime behavior. In an actual-host paired comparison:

| Worker host metric | Step 8 | Step 9 |
| --- | ---: | ---: |
| Traced retained bytes | 38,559,818 | 35,932,944 |
| Traced peak bytes | 55,639,141 | 53,012,388 |
| Normal peak RSS range MiB | 216.77–220.55 | 217.55–220.80 |
| Physical graph records | 51,834 | 51,834 |

The compiler retains about 2.5 MiB less memory (6.8%) and its traced peak falls
about 2.5 MiB (4.7%). The whole-process RSS ranges overlap, so this small change
does not establish an additional RSS improvement. A separate direct-builder
diagnostic measured 164.3 MiB peak RSS after imports/configuration but before
compilation; that portion is outside compiler allocations.

All fourteen paired actual-host samples are in
[`frozen_draft_capacity_application_results.json`](../benchmarks/frozen_draft_capacity_application_results.json).
The larger graph-storage redesign remains a future opportunity; this pass stops
with the measured dead-storage release. Required decorator selection facts stay
available because Bark's lock-validation rules use them even with diagnostics off.

## Detailed step evidence

1. [Early rejection allocation](early-rejection-records-evidence.md)
2. [Declared public provider forms](declared-provider-roots-evidence.md)
3. [Selected registration catalogue](selected-registration-catalogue-evidence.md)
4. [Compact runtime composition](compact-runtime-evidence.md)
5. [Deferred advisories](deferred-advisories-evidence.md)
6. [Failure aggregation](failure-aggregation-evidence.md)
7. [Empty dependency signature validation](empty-dependency-validation-evidence.md)
8. [Actual host build options](/Users/peter.daly/WS/bark/bark-core/docs/evidence/host-build-options/README.md)
9. [Frozen draft-table capacity](frozen-draft-capacity-evidence.md)

## Final verification

Clean IoC full CI passes 2,033 tests, including graph-growth, scope ownership,
cleanup, provider and failure-diagnostic regressions. Final Cop unit tests pass
498/498 (30.25 seconds), including four new actual-host composition tests. Final Bark unit
tests pass 5,963 with 26 skips (86.97 seconds). The complete Cop integration
suite passes 64/64 on Step 9 (356.97 seconds), including all four unchanged
catalogue memory assertions. The final unit and integration tests use the
frozen Step 9 Clean IoC and Step 8 Bark wheels, with the final Cop host composition
changes. Bark/Cop lint and formatting checks and Bark public
API generation checks pass. Full Bark typing retains three existing DynamoDB test errors and
one existing protocol variance warning. Cop's required `ty check` reports 309
diagnostics; a clean archive of Cop HEAD with the same installed dependencies
produces the identical 309 diagnostics (zero added or removed after normalizing
line numbers). These unrelated findings were not suppressed or changed.

## Linux startup at the configured resource limits

The Step 8 wheels and frozen Cop application snapshot were tested with the real
Gunicorn application entry points in fresh Linux ARM64 containers, sequentially.
Each run used 512 MiB memory, no additional swap, 100m CPU, and the existing
120-second readiness deadline. The measurement is the entire container's
cgroup v2 `memory.peak`, including startup imports and the host processes.
There is one run per application; this is not a distribution of repeated peaks.

| Application | Ready within 120 s | Readiness seconds | Observed peak MiB | Memory limit / OOM events |
| --- | --- | ---: | ---: | --- |
| API | Yes | 81.19 | 313.79 | None |
| Worker | No | — | 337.15 | None |
| Reporting worker | Yes | 75.14 | 297.46 | None |
| Response processor | Yes | 79.25 | 284.31 | None |

For successful runs, observation ends at readiness. The worker's observation
ends at the deadline: 337.15 MiB is not a proven completed-startup peak. Its
container remained alive, with every CPU quota period throttled. The readiness
failure remains unresolved; these data do not prove that the worker fits the
complete deployment startup budget. Limits, deadlines and assertions were not
raised or relaxed.

The configured image `ghcr.io/bark-com/ubuntu:3.14.4`, locally identified as
`sha256:b80e1db51da5cde244cb0aae087c7e6a992f8d691747a704630ab1a370ff6160`,
fails `from compression import zstd` because Python lacks the `_zstd` extension.
This blocks application startup before container compilation. The table uses
a Python 3.14.4 slim reference image instead; it does not establish acceptance
on the configured deployment image. The Step 8 reference image is
`cop-ioc-verification:runtime-step8-reference`, ID
`sha256:229dc33d171ce60cabb5a07449192f34021324cf5b20163e2993f4f6e140e1a5`.

Sanitized raw samples, cgroup counters, image identities and the configured-image
failure are in
[`runtime_build_linux_results.json`](../benchmarks/runtime_build_linux_results.json).
The configured image still needs repair before deployment-image acceptance.
The user has deferred startup-time optimization; the memory follow-up below
observes completed startup without changing the deployed settings.

## Final memory-only Linux follow-up

After the user prioritized memory, the observation window was extended to at
most 600 seconds while retaining 512 MiB memory, 100m CPU, the normal Gunicorn
entry points, and unchanged application settings. This changes only the
diagnostic observer; it does not change any deployment timeout. Each final
Step 9 application completed startup, and measurement ended at readiness.

| Application | Full-startup peak MiB | MiB below the 512 MiB limit | Memory-limit / OOM events |
| --- | ---: | ---: | --- |
| API | 309.03 | 202.97 | None |
| Worker | 362.38 | 149.62 | None |

These are single fresh-container observations on the Python 3.14.4 slim ARM64
reference image. The previous Step 8 worker's extended observation peaked at
359.18 MiB; the final Step 9 value is higher by 3.20 MiB, so the Linux runs do
not establish an isolated whole-container peak improvement from the final
empty-table release. Its compiler allocation saving is demonstrated separately
by the paired traced measurements. Both complete worker startups stayed below
the unchanged memory limit without memory-limit or OOM events.

The final image is `cop-ioc-verification:runtime-step9-reference`, ID
`sha256:9a70dd873b7789a2c96f0334dc9ad1a0a4d9a487605419ed21573f66b8627995`.
The raw artifact linked above includes all three extended observations and
their cgroup counters. The configured Ubuntu image's missing `_zstd` extension
remains separate from these memory measurements. Startup-time work is deferred;
these observations do not claim that the original 120-second worker readiness
gate passes, or that steady-state/load memory has been measured.

## Artifact identities and release boundary

Final Clean IoC wheel: `clean_ioc-2.0.0rc2-py3-none-any.whl`, SHA256
`c72e04bd8dc929b2e3ffe0c5d86dff9deab67f75aef602f4e104f0ad4efcb8b3`.

Final Bark wheel: `bark_core-1.0.0b1-py3-none-any.whl`, SHA256
`e8290f94f4f0482d57633292b80d30fe87a327b4eef2d89e325129044d92e93c`.

Changes remain local; no new committed `v1_rc` revision or release has been
published and dependency pins/locks are unchanged. Verification installs the
frozen development wheels explicitly with `--no-deps` over the fixed support
dependencies. This proves the tested wheel contents, not acceptance of the
original released dependency lock.
