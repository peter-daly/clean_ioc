# 26 — Replace analyse with verify and return a verification report

Created: 2026-10-12\
Status: Complete — implemented and validated; [result](26-result.md)\
Assignment: `/root/graph_memory_task_26`, medium reasoning\
Recommended reasoning effort: Medium (`medium`)\
Prerequisites: Tasks 19–24; released `2.0.0rc5` API

## Outcome

Rename `ContainerBuilder.analyse()` and `ScopeBuilder.analyse()` to `verify()`.
Return a public `VerificationReport` with direct inspection and assertion methods,
so callers can write:

```python
report = make_builder().verify()
report.assert_valid()
```

The returned object should expose `is_valid`, `errors`, `warnings`, `issues` and
completion/coverage information directly. Callers should not need a nested
`result.report.assert_valid()` step. Preserve the existing separation: `build()`
creates an execution runtime without running verification rules; `verify()` runs
the complete verification workflow without activating application objects.

## Current implementation

`analyse()` currently returns `AnalysisResult`, which owns graphs, optional emitted
execution and test-runtime cleanup. Its nested immutable `AnalysisReport` already
provides `assert_valid()`, validity/findings and text, JSON and SARIF output.
This task brings those capabilities onto the object returned by `verify()`; it is
not a new validation engine or a reason to run checks twice.

## Work

- Define and export `VerificationReport` as the public return type for both root
  and scope verification. Replace the public `AnalysisResult`/`AnalysisReport`
  split at the call site. Internal storage may remain separated where this helps
  preserve immutable findings and resource ownership.
- Provide direct `assert_valid()`, `is_valid`, `errors`, `warnings`, `issues`,
  completion/coverage and rule/stage outcomes, plus the existing text, JSON and
  SARIF reporting capabilities. Preserve source and boundary attribution.
- Preserve assertion semantics: complete reports without errors are valid;
  warnings alone do not fail. Errors or incomplete verification fail
  `assert_valid()` with useful captured diagnostics. It must work under `python -O`
  and must not replay callbacks, recompile or construct application objects.
- Preserve existing graph/partial-graph, census, triage, selected-registration,
  composition and explicit `create_runtime()` capabilities on the returned report.
  Keep validity distinct from whether an execution plan was emitted. Document
  immutable findings separately from runtime ownership and close/aclose state;
  preserve independent test runtimes, borrowed parents and context-manager cleanup.
- Keep admitted attempts single-use, including failed verification. Keep the
  unified `add_validation_rule(rule)` API and execution-only `build()` behavior.
- Treat this as a breaking API migration, consistent with tasks 19–24. Update
  public exports, annotations, related exception references and messages rather
  than introducing permanent parallel `analyse` and `verify` entry points.
- Migrate CLI and matrix internals, compilation profiling's named operation,
  examples, tests, benchmark definitions, packaged skills/codemod guidance and
  upgrade notes. Use `verify()` and the direct report API in current documentation;
  preserve historical task records, captured sources and measurements unchanged.
- Record the consumer migration from `builder.analyse()` and
  `result.report.assert_valid()` to `builder.verify()` and `report.assert_valid()`.
  Update verification adapters in isolated Bark/Cop copies when checking consumer
  compatibility; preserve discovery, real rule registration and runtime behavior.

## Acceptance

- Both builders return the documented `VerificationReport`; normal use supports
  `make_builder().verify().assert_valid()` without an intermediate report property.
- Valid, warning-only, invalid and incomplete reports retain their existing
  semantics. Repeated assertions, inspection and serialization do not rerun rules
  or selection callbacks, and diagnostics retain distinct declaration identities.
- Graph inspection, explicit runtime creation and cleanup remain available with
  their existing ownership rules. Verification alone activates no application
  constructors; production build invokes no verification rules.
- Tests cover root and overlay verification, failed attempts, callback counts,
  partial reports, optimized-Python assertions, CLI/matrix output and consumer
  discovery. Full CI, supported-Python checks and executable documentation pass.
- Document the breaking migration and any deliberately retained analysis terms.
  There is one supported verification entry point and no new fine-grained flags.

## Boundaries

The maintainer has authorized implementation by a medium-reasoning subagent.
No version bump, commit, push, release or original consumer-checkout edits are
included in this assignment. Task 25 remains
the separate performance acceptance item: preserve the RC5 baseline and identify
the exact final revision if this rename lands before those measurements.
