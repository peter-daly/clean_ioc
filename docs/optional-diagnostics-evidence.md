# Optional compiler diagnostics evidence

Normal `ContainerBuilder.build()` and `ScopeBuilder.build()` now use `diagnostics=False`. Validation/inspection CLI
commands and matrix checks request full capture. CLI profiling follows the normal default, with `--diagnostics`
for an explicit comparison. An existing scope is never recompiled by validation or inspection.

The subsequent [early rejection allocation change](early-rejection-records-evidence.md) also omits physical
records for proven early exclusions when diagnostics are off. It preserves full evidence with diagnostics on.
The historical measurements below precede that change; late-rejected/intermediate records remain retained.

The allocation change happens during compilation: ordinary selection avoids candidate-history objects, explanation
paths, argument/generic explanations, partial-graph capture and census inventory. Mandatory structural validation,
independent-root error aggregation, runtime graphs, ownership, source origins, actual fallback identities and captured
decorator/template safety facts remain available. Rich-only evidence fails explicitly with an opt-in instruction;
omitted callback evaluations are never synthesized as recorded decisions.

## Fresh-process allocation comparison

Run the same workload in two fresh processes:

```console
PYTHONPATH=. .venv/bin/python benchmarks/optional_diagnostics_evidence.py --heap
PYTHONPATH=. .venv/bin/python benchmarks/optional_diagnostics_evidence.py --heap --diagnostics
```

The fixture has 256 resolvable routes sharing an eight-level dependency chain. The builder is composed before tracing,
then the script records compilation peak and retained Python allocations after garbage collection. Manifest generation
happens after tracing. Both modes retained 9,728 physical records and 4,096 provider-view contexts and produced the
same semantic graph fingerprint. Results are saved in `benchmarks/optional_diagnostics_results.json`.

Python 3.14.4 on macOS 26.7.1 ARM64, one fresh-process pair:

| Measurement | Diagnostics off | Diagnostics on | Reduction |
| --- | ---: | ---: | ---: |
| Traced retained allocations | 12,313,991 bytes | 15,866,968 bytes | 22.39% |
| Traced peak allocations | 13,977,024 bytes | 17,176,819 bytes | 18.63% |
| Occurrence explanations | 0 | 6,656 | |
| Parameter explanation owners | 0 | 2,304 | |

This fixture has no generic substitutions, so generic explanation counts are zero in both modes. Traced elapsed times
and process RSS are retained in the raw file for reproducibility; they are not treated as ordinary build performance
measurements or as representative application memory limits.

## Verification

The complete `make ci` passed with 1,842 tests, one pre-existing FastAPI deprecation warning, lint/format/type checks,
documentation examples and benchmark discovery. The subsequent CLI-only amendment passed 247 focused optional-diagnostics, profiling, CLI/tooling, census and matrix
tests, plus documentation validation, lint, formatting and type checks. It leaves compiler sources unchanged.

Focused coverage exercises normal and full builds, required safety rules, actual generic constructor/factory fallback
identities, aliases, boundaries, parent singleton ownership and overlays; callback/preference parity; rejected optional
history access; failed-build aggregation and repair; budget exhaustion before compilation, during compilation and
recovery; early declaration errors; structural builder previews; CLI/matrix validation; runtime profiling; compiler
collection by GC; and a regression bound for retained/peak allocation savings. Existing tests that inspect full history
request it explicitly; ordinary runtime and safety tests keep the new default.

## Actual Cop application comparison

The same final development compiler/runtime wheel was tested with diagnostics off and on in three fresh processes
per application/mode. Mode order alternated across pairs (off/on, on/off, off/on); instrumentation was `none`.
These are build elapsed times and process high-water RSS on Python 3.14.4, macOS 26.7.1 ARM64. They do not measure
retained heap or establish CPU-limited Linux startup acceptance.

| Application | Diagnostics off build | Diagnostics on build | Off peak RSS | On peak RSS |
| --- | ---: | ---: | ---: | ---: |
| API | 0.7444–0.7804 s | 0.8084–0.8120 s | 199.63–234.13 MiB | 205.69–210.28 MiB |
| Worker | 5.3905–5.4492 s | 6.1910–6.3185 s | 409.91–429.67 MiB | 469.75–506.31 MiB |

The worker samples show lower build time and peak RSS with diagnostic capture off. Comparing medians gives
**12.54% lower elapsed build time** and **16.58% lower process peak RSS**. API RSS ranges overlap and are
variable; this comparison does **not** demonstrate a reliable API RSS improvement. Each mode keeps 11,910 API and
91,570 worker physical records, with 3,220 and 4,220 provider-view contexts respectively. The off mode has zero
occurrence/parameter/generic explanation sidecars; worker on-mode counts are 60,066 / 28,218 / 4,657.
Sanitized raw samples and check results are in `benchmarks/optional_diagnostics_application_results.json`.

The full installed-wheel Bark unit suite passed **5,941 tests**, with **26 skipped**, in 88.74 seconds. The full Cop
unit suite passed **494 tests** in 39.54 seconds. These checks retained default build mode and required application
safety rules, including exact closed handlers taking precedence over specialized generic fallbacks. The full Cop
integration suite subsequently passed **64 tests** in **393.48 seconds**, using the CLI-amended wheel. All four
original catalogue-capacity cases (reviewed, +50, +75, +500), access/deletion/inventory workflows and the readiness
checks for all five hosts passed with the existing 120-second host startup timeout. Capacity assertions were unchanged.

The measured runtime wheel SHA-256 is `265368cd1deb04fc28ae38b155eb67046270e3dafa4ed8af8309892edec39e57`.
The final CLI amendment is `4e0d2fd53eafcfc9d03837b58b6f2d59e0d14c88e1405a0240b22dd7174d7749`;
only CLI behavior differs, with unchanged compiler sources. Bark's wheel remains
`047d046561f219b331cd812feb2c52fe9883de070226e1b4ed602222012bf758`.
These are unreleased development-wheel checks; no releases, pins or lockfiles were changed.

## Actual worker retained-heap comparison

A separate fresh process per mode traced the actual Cop worker using the CLI-amended wheel. Tracing started **after
imports and configuration construction**, and included builder composition plus compilation. Both modes retained
91,570 physical records and 4,220 provider-view contexts. The comparison uses retained allocations **after garbage
collection**, because immediate after-build values had different GC timing.

| Measurement | Diagnostics off | Diagnostics on | Saved | Reduction |
| --- | ---: | ---: | ---: | ---: |
| Retained after GC | 68,232,121 bytes (65.071 MiB) | 123,192,875 bytes (117.486 MiB) | 52.415 MiB | 44.614% |
| Traced peak | 199,334,062 bytes (190.100 MiB) | 258,330,036 bytes (246.363 MiB) | 56.263 MiB | 22.837% |

Sanitized raw heap samples and matching source hashes are included in the application results JSON. Instrumented
elapsed times and RSS are retained only as raw probe metadata and must not be compared as normal build performance.
These measurements include builder composition; the earlier synthetic allocation fixture starts tracing after its
builder is composed, so their measurement scopes differ.

## Linux reference startup remains incomplete

Normal Gunicorn startup used the measured runtime wheel in a **Python 3.14.4-slim ARM64 reference image**, with the
unchanged **512 MiB / 100m CPU** limits, zero swap and a 120-second readiness budget. This is a reference-image check,
not the configured application image: the original configured base's missing Python `_zstd` extension remains a blocker.

| Application | Readiness | Observed duration | Cgroup memory peak | Memory max events | OOM / OOM kill |
| --- | --- | ---: | ---: | ---: | ---: |
| API | Ready at 89.388 s | 89.388 s | 357,036,032 bytes (340.50 MiB) | 0 | 0 / 0 |
| Worker | Not ready within 120 s | 121.529 s | 536,870,912 bytes (512 MiB) | 112 | 0 / 0 |

CPU throttling affected all 901 observed API periods and 1,247 of 1,248 worker periods. The worker reached the memory
cap and triggered 112 `memory.events.max` events; absence of an OOM kill does not establish adequate memory headroom
or successful startup. There is **no successful Linux worker acceptance claim**. Limits, timeouts and assertions were
not relaxed, and validation was not disabled.

## Remaining acceptance limits

All reported local library, unit, integration and application heap checks are complete. Configured-image acceptance
and successful worker readiness under the unchanged constrained Linux limits remain unresolved. The reference image
cannot substitute for the original configured Python's missing `_zstd` extension module. Earlier compiler optimization
evidence and historical startup reports remain preserved; no limits, timeouts, assertions, releases, pins or locks
were changed for these results.
