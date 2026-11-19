# 03 — Remove registration rescans

Created: 2026-11-18  
Status: Complete (keep) \
Priority: P1 — recommended; not a release blocker  
Blocked by: None — can start immediately  
Assignment: GPT-6.2 Sol (`gpt-6.2-sol`), high reasoning — `/root/v2_item03`

## Outcome

Make registration declaration work scale with the new registration rather than the entire accumulated registry. Preserve the existing public API, registration order, alias metadata, and object identity.

## Review evidence

`_BuilderBase.register` currently visits every service bucket and registration after insertion, solely to assign `declared_service_type` to the newly returned registration ID. Repeating this scan produces quadratic work as declarations accumulate.

An isolated, process-only prototype assigned through the newest entry in the requested service bucket instead. The existing `_Registry` insertion paths prepend the registration there; implementation aliases reference that same object. Five alternating baseline/candidate runs measured repeated factory registrations for one service, excluding container compilation:

| Declarations | Baseline median | Candidate median |
| --- | ---: | ---: |
| 1,000 | 77.8 ms | 65.2 ms |
| 5,000 | 599.3 ms | 326.1 ms |

These are approximately 16% and 46% reductions in declaration time, not application startup claims. Thirty-three existing type-alias and alias-lookup tests passed with the prototype. That was exploratory verification, not production validation or acceptance of an implementation. Review scripts and measurements are in `.benchbro/v2-perf-review/compiler_registration_probe.py` and `compiler_registration_timing.jsonl`.

## Implementation guardrails

Use the existing service-bucket insertion contract, or an equally direct internal reference to the inserted registration. Confirm that concrete, implementation, factory, and instance paths consistently identify the new object. Preserve shared identity when a registration appears under both service and implementation keys. Normalize the lookup key as today, while retaining the original declared alias on the object. Check generic specialization and generated registrations rather than assuming every declaration is an ordinary class.

Avoid a new global index or cross-build cache. Preserve callbacks, opaque application objects, existing hashing/equality behavior, diagnostics, selection, boundary visibility, and lifetime semantics. Do not broaden the work into registry redesign.

## Acceptance criteria

- [x] The post-insertion operation no longer scans unrelated registrations or service buckets.
- [x] Each registration path updates exactly the newly inserted object, including aliases and specialization-related declarations.
- [x] Service and implementation views retain the same registration identity and ordering.
- [x] Focused regressions and the [common validation criteria](README.md) pass.

## Validation and measurement

Exercise each insertion form, repeated declarations, type aliases, generic registrations, registration templates, and overlays. Repeat the declaration comparison on the same interpreter with alternating runs; distinguish small-workload noise from scaling improvements. Check representative complete builds for regressions. Report observations without imposing a fixed percentage performance gate.

### Implementation

The four registry insertion methods return the registration object. The
builder captures it through a private helper and writes the original declared
type directly to it. Both the builder and legacy registration methods still
return string IDs. Implementation aliases use the same object in both buckets,
and bucket insertion and discovery lookup stay in their existing order.

Capturing the object avoids a second service-key lookup. A class metaclass can
run application code during a registry hash or equality comparison. During an
implementation-key lookup that follows the service insertion, such a callback
can add another registration to the same service bucket. The returned object
continues to identify the outer registration in that case.

### Measurement method

The fresh baseline is `655c3044d4ba91adeb5723a7a6d44f0e622fd55e`, including items
01 and 02 and the pre-existing compatibility edits. The package snapshots
differ only in `clean_ioc/_legacy.py` and `clean_ioc/container.py`. Both used
CPython 3.14.4, BenchBro 1.0.0, macOS 26.7.3 ARM64 and an Apple M2 Max. Runtime
dependencies were funcie 0.2.0, typetoolbox 0.4.0 and typing-extensions 4.16.0.
The `uv.lock` SHA-256 was
`dbdf4ff668bcc32ab220899f2d28add11b62de86ea0dfe6adeb3bdad17a6fb79`.

Run the [declaration workloads](../../benchmarks/bench_registration_declarations.py)
and the existing [compiler fixtures](../../benchmarks/bench_compiler_optimization.py)
with the same interpreter and dependencies. Set `source` to the absolute
directory containing the selected `clean_ioc` package and use a distinct `run`
label for each invocation. Alternate the versions starting with the baseline.

```sh
results="$PWD/.benchbro/v2-perf-03"
mkdir -p "$results"
PYTHONPATH="$source" .venv/bin/benchbro run benchmarks/bench_registration_declarations.py \
  --fixed --repeats 9 --warmup 3 --no-compare --baseline v2-registration-declarations \
  --output-json "$results/declarations-$run.json" --output-md "$results/declarations-$run.md"
PYTHONPATH="$source" .venv/bin/benchbro run benchmarks/bench_compiler_optimization.py \
  --case compiler-declaration-build \
  --fixed --repeats 9 --warmup 3 --no-compare --baseline v2-registration-declarations \
  --output-json "$results/builds-$run.json" --output-md "$results/builds-$run.md"
```

Declaration timings include fresh builder construction and registration. Class
creation is outside timing. Each repeat measures one builder, with automatic
GC enabled. The empty-build control measures 100 fresh construction, build and
close operations per repeat. The existing complete-build workloads measure eight
declaration, compilation and close operations per repeat, with automatic GC
disabled during measurement. The complete-build cases do not activate services.
Allocation tracing was disabled throughout.

### Timing results

Three alternating baseline/candidate pairs. Times are milliseconds per workload,
reported as the median of the three run medians with their ranges in brackets.

| Workload | Baseline | Candidate | Median change |
| --- | ---: | ---: | ---: |
| 100 repeated factories | 6.344 [6.075–6.381] | 6.020 [5.996–6.272] | −5.1% |
| 1,000 repeated factories | 73.34 [72.77–75.01] | 64.37 [63.02–65.49] | −12.2% |
| 5,000 repeated factories | 571.8 [568.6–586.2] | 323.5 [320.4–330.7] | −43.4% |
| 1,000 distinct concrete types | 95.54 [94.16–98.71] | 62.01 [61.32–63.34] | −35.1% |
| Empty build control | 0.2025 [0.2017–0.2055] | 0.2034 [0.2026–0.2034] | +0.4% |
| Wide build | 27.25 [26.37–28.28] | 26.03 [25.62–26.91] | −4.5% |
| Diamond build | 9.403 [9.332–9.742] | 9.359 [9.243–9.468] | −0.5% |
| Generic build | 19.76 [19.14–19.95] | 19.18 [18.84–20.06] | −2.9% |
| Collection build | 9.388 [9.319–9.414] | 9.230 [9.191–9.821] | −1.7% |
| Template build | 11.01 [10.99–11.05] | 10.97 [10.88–11.48] | −0.4% |
| Managed warmup build | 2.788 [2.781–2.813] | 2.796 [2.793–2.833] | +0.3% |

Each pair improved by 12.2–13.4% at 1,000 repeated factories, 43.1–44.0% at
5,000, and 32.7–37.9% with 1,000 distinct concrete types. The 100-factory
ranges overlap. Baseline declaration medians spanned 3.0–5.0% and BenchBro flagged
some runs for outliers. The empty and complete-build ranges overlap, with a
21.7% within-run coefficient of variation for one diamond-build baseline.
There was no material slowdown in the controls. These measurements establish
declaration gains on this interpreter and fixture, with the cost of normal
registration construction still present. Local reports are in
`.benchbro/v2-perf-03/`.

### Validation and review

- Six new cases cover repeated aliases in all four insertion forms, distinct
  singleton or supplied instance identity, service and implementation view
  ordering, a reentrant implementation hash, and a generated registration
  specialized through an overlay. The reentry case also detects an added service
  hash after insertion.
- Local `make ci` passed on macOS ARM64 for the five Python versions required by
  current CI. CPython 3.11.13 had 2,657 passes and 8 skips, 3.12.11 had 2,662
  passes and 3 skips, and 3.13.5, 3.14.8 and 3.15.2 each had 2,665 passes. The
  hosted Ubuntu jobs were outside this run. All pre-commit hooks and strict
  MkDocs also passed. CPython 3.12.11 passed all 16 FastAPI integration tests
  with both FastAPI 0.121.0 and the latest release selected by CI, 0.165.0.
- Independent review by `/root/v2_item03/review` found no actionable issues.
  The reviewer passed 213 focused tests, confirmed that legacy registration
  still returns string IDs for all four forms, and checked shared object identity
  across service and implementation registry keys. The bucket-head alternative
  failed the reentry test for the extra hash and, with the hash assertion removed,
  for the incorrect declared alias. The reviewer also checked the measurement
  order and matching environments.

Keep the change. It substantially reduces declaration time for large registries,
with no material change in the empty-build control or representative complete
builds. The changelog records the declaration improvement.
