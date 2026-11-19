# 11 — Compilation profiler

Status: Implemented and independently reviewed (2026-09-25)  
Priority: P1  
Dependencies: Existing build pipeline; independent of 08 runtime observations  
Related work: 04 specialization explanations; 05 failed-build attempts; 10 selection census

## Outcome

Explain where a real `build()` spends time and which declarations cause repeated compilation work. Separate compiler
work, composition callbacks, validation, and diagnostic retries so maintainers can investigate slow application startup
without confusing build cost with object activation.

Illustrative output; numbers are not measurements of the current implementation:

```text
Compilation profile — one failed build, elapsed wall time 2.00 s
  Discovery and blueprint preparation       0.12 s
  Alias/boundary preparation                0.08 s
  Decorator-template expansion              0.25 s
  Primary compilation                      0.80 s
  Diagnostic root retries                  0.70 s
  Other build work                         0.05 s
  Final validation                         not reached

Within primary compilation (nested; do not add to the phase totals):
  Candidate compilation: 840 attempts, 210 distinct definitions
  Generic specialization: 120 requests, 40 materializations
  Selection callbacks: 0.21 s across 560 calls
```

The profile measures the enabled run and includes instrumentation overhead. It is diagnostic evidence, not a benchmark,
a promise about production latency, or a reason to change callback ordering.

## Current foundation

Both `ContainerBuilder.build()` and `ScopeBuilder.build()` prepare a compilation snapshot, compile with reports, and
create an immutable runtime. The pipeline includes discovery, alias/boundary preparation, decorator-template expansion,
recursive candidate compilation, graph/plan freezing, ownership analysis, and build-mode validation.

Failed builds may repeat root compilation through `_error_report()`. Composition callbacks already execute at their
defined stages; activation constructors, registered factories, and resource acquisition do not run during build.
Explicit derivations and decorator-template factories are composition callbacks and must be categorized accordingly.

Primary integration points: both public `build()` methods, `_compilation_snapshot()`, `_compile_with_report()`,
`_expand_decorator_templates()`, `_Compiler`, `_error_report()`, `_finalize_plan()`, validation-rule iteration,
`cli.py`, a proposed compilation-profiling module, and build-performance fixtures.

## Scope and non-goals

- Opt-in elapsed-time measurement, work counters, and bounded definition/request attribution for one actual build.
- Profile successful builds and failures, including preparation errors before a graph exists and ordinary diagnostic
  retries. Keep the original build outcome and exception behaviour.
- Cover build-mode validation; validation-only rules are excluded and labelled as such in the first version.
- Do not rerun callbacks, perform automatic repeated builds, activate services, collect arbitrary function locals,
  sample the whole process, or reuse activation-tracing events as compiler events.
- Existing registration calls and application imports before `build()` are outside its measurement interval.

## Proposed model and API

- `CompilationProfiler`: a bounded collector for one build with explicit record limits and an immutable report method.
- `CompilationSpan`: compiler phase or operation, parent reference, attempt reference, safe optional definition/request
  reference, elapsed/inclusive and self/exclusive durations, and completed/failed/interrupted state.
- `CompilationCounters`: precisely defined counts for candidates, callbacks, materialized specializations, occurrences,
  emitted steps, reused plans, and diagnostic attempts; unmeasured counters are absent, never silently zero.
- `CompilationProfile`: elapsed build interval, phase summaries, bounded costly-definition summaries, counter units,
  capture completeness, and enabled-instrumentation metadata.

Proposed Python usage:

```python
profile = CompilationProfiler(max_records=10_000)
try:
    container = builder.build(profile=profile)
finally:
    print(profile.report().to_text())
```

Add the same optional argument to `ScopeBuilder.build()`. The collector survives a failed build without being retained
by its runtime plan. Reports are frozen snapshots; reusing the same collector for another build is rejected explicitly.
All names are proposals until implemented. Text and JSON are the initial output formats.

Proposed CLI: `clean-ioc profile TARGET --format text|json [-o PATH]`. Accept an unbuilt builder or a zero-argument
factory returning one. Reject already-built containers/scopes, including factories returning them: profiling cannot
reconstruct an earlier build. Existing tooling commands retain their broader target contract. Importing the target and
running a builder factory happens before the measured build and is explicitly excluded from the report.

## Implementation stages

### 1. Define measurement boundaries and units

- [x] Start the build interval before `_compilation_snapshot()` and finish after successful runtime construction or
  failed-build report completion. Include discovery and preparation, not just `_Compiler.compile()`.
- [ ] Define non-overlapping top-level phases and nested spans for candidate expansion, generic specialization,
  parameter processing, selection callbacks, template callbacks, plan freezing, and individual validation rules.
- [x] Use a monotonic elapsed-time clock with explicit units. Distinguish inclusive duration from exclusive/self
  duration, and never sum inclusive ancestors with their descendants into a total.
- [x] Label sequential diagnostic retries separately from primary compilation, preserving root/attempt attribution.
  Keep template source-inspection compilers distinguishable from final target compilation and error-report retries.
- [x] Measure generator-based validation rules across iteration, not just the call that creates an iterator. Separate
  derive policies and template factories from registered activation factories in labels and counters.
- [ ] Define work counters at their actual operations: a lookup request, materialized specialization, graph occurrence,
  and emitted executable step are different units. Record real reuse only where the compiler establishes it.

### 2. Instrument the enabled build once

- [x] Choose profiling support once at build entry and carry it through preparation, compilation, finalization, and
  retries. Disabled builds must allocate no profiling records and call no profiling clock; keep overhead minimal and
  measure it rather than promising zero compiler overhead.
- [x] Close measured spans on success, failure, and interruption using compiler-owned control flow. Preserve original
  exceptions and builder repairability; a later repair uses a fresh collector.
- [x] Invoke every callback exactly where normal compilation invokes it, with identical ordering and counts. Do not
  retry to obtain a better timing, and do not execute constructors or resource cleanup to measure activation cost.
- [ ] Attribute recursive work to actual definition/request occurrences. Keep parent-owned anchored plan reuse in
  overlays separate from fresh compilation; do not charge the original parent build again.
- [x] Keep timing and recording objects out of frozen steps, ordinary resolution, scope creation, manifests, and graph
  fingerprints. Profiling must not require enabling runtime instrumentation.
- [x] Handle internal recording failures without masking the application's compilation failure or changing selection;
  report a bounded profiler diagnostic when possible. Do not accept arbitrary event callbacks in the first version.

### 3. Bound collection and report honestly

- [x] Bound detailed spans and attribution tables, using overflow buckets or omitted-detail counts. Keep top-level
  elapsed time and supported aggregate counters available after the detail limit is reached.
- [x] Mark attribution completeness. A costly-definition ranking over retained samples must not be presented as a
  complete global ranking, and exclusive durations must not silently treat omitted child time as self time.
- [x] Use compiler-owned sequence references for recording-local spans and safe semantic labels for definitions.
  Do not retain traceback frames, builder graphs, callback closures, configured values, or build-input identifiers.
- [x] Render top-level phase totals, nested hotspots, work counts, attempt summaries, and capture limits. Include
  units, excluded phases, and a statement that instrumented durations are observations.
- [x] Make serialization of a captured report deterministic while allowing measured times to vary between builds.
  Omit absolute timestamps, arbitrary object representations, and machine/process identifiers by default.
- [x] Keep JSON unversioned during beta and entirely separate from structural manifests and semantic diffs.

### 4. Expose CLI and documentation

- [x] Load a builder without using the existing helper that eagerly calls `build()`. Run exactly one profiled build;
  preserve its existing internal diagnostic retries and do not silently rebuild a consumed builder.
- [x] Emit a partial profile when compilation fails and exit 1. Invalid targets, invalid limits, and output failures
  exit 2. A successful profiled build exits 0; this command does not replace strict `check` or run validation-only rules.
- [x] Document the measurement boundary for module import, builder-factory execution, registration work, build-mode
  versus validation-only rules, and parent builds reused by overlays.
- [x] Add a slow-filter example and an occurrence-expansion example showing how timing and work counts answer
  different questions. Describe investigation steps without automatic performance-policy thresholds.

## Verification

Use a controllable test clock to verify nested accounting, exclusive/inclusive semantics, phase totals, missing phases,
span closure on exceptions, and deterministic serialization of a captured report. Do not assert real-time thresholds
in correctness tests. Verify partial recordings and exclusive accounting when detail capture overflows.

Cover discovery, boundary/alias preparation, decorator-template source inspection, generic requests/materializations,
derive policies, predicates, generator validation rules, successful freezing, independent-root retries, pre-graph
failures, and overlays reusing parent plans. Compare callback order/counts, build reports, manifests, and runtime
behaviour with profiling enabled and disabled. Check that a consumed collector/builder is not reused by the CLI.

Inspect disabled build and runtime paths for profiler allocations, clock calls, and retained collectors. Measure
disabled build cost against the existing baseline and enabled overhead separately on wide, deep, generic-heavy, and
callback-heavy compositions. Record noisy or inconclusive results honestly. Verify redaction and bounded memory with
sentinel secrets and large compositions; timing records must not retain application objects after the report freezes.

## Acceptance criteria

- A profile accounts for the actual public build interval and separates primary work, nested work, and diagnostic retries.
- Work counts distinguish requests, attempts, materializations, occurrences, steps, and reuse where measured.
- Failed and truncated recordings remain useful without overstating complete attribution or changing build outcomes.
- Profiling adds no callback invocations, activation, or work to ordinary runtime resolution and scope creation.
- Disabled compilation has no profiling clock calls or records; enabled overhead is measured and documented.
- Timings remain optional, redacted observations outside all structural fingerprints and default reports.

## Implementation and verification (2026-09-25)

The optional `CompilationProfiler` is integrated into both public builders. It retains at most `max_records` detailed
spans, while phase totals and named work counters continue after truncation. Text/JSON reports include sampled costly
definitions, attempt references, capture completeness, and units. The CLI accepts only an unbuilt builder or a factory
returning one. Failed builds return partial profiles, including preparation failures and diagnostic retries.

Focused tests cover nested inclusive/self accounting with overflow, clock failure without replacing an application
exception, pre-graph failure and builder repair, retry attribution, generator validation, callback count, redaction,
overlay anchor reuse, and CLI target/exit behavior. The full test suite passed (861 tests); focused generic and
decorator-template checks passed (113 tests). Ruff lint, `ty check .`, and documentation example validation passed.
Reviewer follow-up tests cover distinct named declarations sharing an implementation and alias preparation both before
and after template expansion. A local 25-pair smoke
measurement showed enabled/disabled median ratios of 1.05× (wide), 1.04× (deep), 1.01× (closed generic), and 1.01×
(selection callback heavy). These measurements are noisy and do not establish a historical disabled-build baseline.

The first release counts returned candidate plan steps, not every lower-level `_Step` constructor. Factory
specialization requests/materializations are counted at the factory specialization cache; other generic binding work
is reflected in candidate and parameter spans. Boundary visibility callbacks are covered by the boundary preparation
phase but do not yet have individual callback spans. Costly-definition rankings are explicitly limited to retained
spans. These unit and attribution limits are documented in the user guide and should be assessed during review.
