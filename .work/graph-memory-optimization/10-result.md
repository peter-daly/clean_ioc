# Task 10 result — implemented

Completed 2026-10-10 by the assigned high-effort task agent. **KEEP.** The parent
review accepted the two-mode contract and the conservative validation compatibility
path. No commit, version bump, push, release or downstream deployment was performed.

## Public contract and migration

The complete [capability/migration table](10-contract.md) covers both builders,
all former build parameters, runtime APIs, CLI/matrices, profiling, overlays and
the parked artifact experiment. The implemented decisions are:

- `build(mode="run")` is the default; the only other mode is `"analysis"`.
  `BuildMode` is exported and runtimes expose `build_mode`.
- Fine-grained public build options are removed immediately in this RC. Invalid
  modes and removed/mixed arguments fail before compilation without consuming the
  builder. Private `_build` policy machinery remains solely an implementation and
  historical regression harness, not a third public mode or compatibility API.
- `set_provider_roots(None | iterable)` is a composition declaration. It captures
  and normalizes input, preserves empty versus automatic/all semantics, replaces
  prior declarations on repeat calls, and leaves prior state unchanged on invalid
  input. Scope declarations default independently to automatic/all. Injection,
  marked provider entrypoints and managed private targets keep their semantics.
- Run releases inspection evidence and the overlay blueprint, skips optional
  unreachable/orphan analysis and independent diagnostic failure retries, and
  preserves executable relationships, complete selected-registration discovery,
  warmup/observation descriptors, ownership/cleanup and mandatory checks.
- Analysis captures full diagnostics, validates unused dependency-only declarations,
  checks reachability, retains composition and supports complete graph tooling.
  An analysis parent permits run or analysis overlays; a run overlay is terminal.
  Ordinary scopes inherit their plan's mode.
- Both modes run structural and build-mode rules. Public builds conservatively
  capture rich temporary diagnostic evidence when build-mode rules are registered.
  Validation-only rules do not run at build time or prevent run startup.
  `analysis.validation_report()` is the explicit full-validation operation:
  validation-only rules run once per call; errors are returned as report issues.
  CLI check and each matrix variant perform exactly one such pass. Existing run
  runtimes are rejected by analysis tooling rather than silently rebuilt.

Analysis-only orphan work can discover errors and invoke callbacks absent from a
run build. Failed analysis builds can perform diagnostic root retries. Callback
counts and build success are therefore not claimed identical for these additional
operations. Shared executable roots and selected catalogue semantics are preserved.

## Reporting correction found during migration

The old `clean_orphans=False` inspection graph did not distinguish dependency-only
architecture roots from public resolution roots. Making this analysis policy the
default for tooling exposed an existing semantic-diff blind spot: promoting a
selected dependency to a public root could disappear from the diff.

`GraphRoot.resolvable` now distinguishes public and analysis-only/boundary-local
roots. Nonpublic manifest roots carry `resolvable: false`; public roots retain
legacy omission/default-true spelling. Text rendering uses `Inspect` for nonpublic
roots. Promotion/demotion is classified as `root-added`/`root-removed` at medium/high
risk. The field is boolean and root-only on imported manifests, so nested metadata
changes cannot be silently ignored. Focused tests cover fingerprint/JSON roundtrip,
promotion, demotion, invalid placement, validation findings and unchanged discovery.
The original public-root-promotion regression assertion remains intact.

## Changed files and coverage

The exact production, test, benchmark and documentation file inventory is in
[evidence/10/changed-files.txt](evidence/10/changed-files.txt); source hashes and a
reconstructable implementation diff are in
[accepted-source.json](evidence/10/accepted-source.json) and
[accepted-source.patch](evidence/10/accepted-source.patch). The new test module is
also preserved as inert text for later source reconstruction.

Production changes are limited to `clean_ioc/container.py`, `__init__.py`, `cli.py`,
`matrix.py`, `tooling.py` and `semantic_diff.py`. Documentation updates cover the
current guides, README/upgrade notes, release notes and executable examples.
Historical evidence pages received migration labels only; their findings and raw
measurements were not rewritten. Historical evidence collectors and the parked
artifact fixtures explicitly use the private compiler harness. Active graph,
validation and overlay benchmark fixtures request analysis. The current memory
runner accepts `--build-mode run|analysis`; omitting it preserves its labeled
historical private-policy comparison path.

Historical flag-heavy regression modules keep their original coverage through
private calls, explicitly labeled in source. This is supplemented by public-mode
acceptance, not treated as evidence of unsupported public hybrids. An inventory
before the last three focused additions counted 327 public default-run call sites,
159 explicit public analysis calls, 13 parametrized public-mode calls and 821
private historical calls. Ordinary runtime tests and application examples continue
to exercise default run.

## Verification

- Final `make ci`: Ruff lint/format, typing, **2,204 tests**, executable documentation
  and BenchBro discovery pass. The existing single pytest warning remains.
- Public mode module: **41 tests** pass, including two-route rich fixtures in both
  modes, providers/maps/template selections, ownership, terminal overlays,
  declarations, rich mandatory rules, retry, full-validation counts and public run
  artifact export/load. The final focused artifact run passed **59 tests**.
- Historical reduced-execution harness: **222 passed, 16 deselected**.
- Benchmark graph/validation/ownership fixture smoke checks pass.
- Strict MkDocs passes. Historical external-link information remains informational;
  removed-section anchor aliases preserve older evidence links.
- `git diff --check` passes. No historical `.work` probes were executed, integrated
  or reformatted. Supported-Python cross-version testing and downstream Bark/Cop
  verification remain part of the later workstream acceptance, not claimed here.

Check logs are copied into `evidence/10/`. The 59-test focused artifact run preceded
the final type-only correction to its context-manager binding; the final full CI
covers that correction and all 41 mode tests together.

## Fresh pre-change baseline

Captured serially before production changes, with no concurrent tests/benchmarks:
three fresh normal processes and three separate traced processes, eight routes,
Python 3.14.4, macOS 26.7.1 ARM64, HEAD `34d1ea0` plus the initial dirty validation
fix. All six production/fixture source hash sets match. The initial working diff
is [before.patch](evidence/10/before.patch), and all samples/source identities are
[before-run-equivalent.json](evidence/10/before-run-equivalent.json).

This is the old reduced/no-blueprint workload: diagnostics off, metadata off,
blueprint off, reachability/aggregation off, declared Worker provider forms,
no retained builder or captured selection views. It provides the run-equivalent
starting baseline; it is not a measurement of the final two-mode implementation.

| Measurement | Median | Range |
| --- | ---: | ---: |
| Fixture import, composition and build | 10.920 s | 10.902–10.942 s |
| Resolution workload | 14.285 ms | 14.158–14.358 ms |
| Current/peak process RSS after build | 130.172 MiB | 128.719–130.375 MiB |
| Retained traced allocations after collection | 3.102 MiB | 3.101–3.102 MiB |
| Traced allocation peak through build | 72.844 MiB | 72.844–72.844 MiB |

The graph has 8,982 physical records, 1,765 distinct execution steps and 51 selected
registration entries in every sample. Workload validation passes. No performance
improvement is claimed by this contract migration. The coordinating agent waived
redundant task-10 after repeats: tasks 11–18 will measure subsequent selected
optimizations and task 18 the combined source.

## Handoff to task 11

1. Audit all mandatory structural/build-rule, selector/template/provider-map,
   warmup/instrumentation, budget and failure-evidence consumers before narrowing
   temporary graph/fact construction. Public run's `conservative_rules=True`
   detects registered build-mode rules from the completed blueprint and enables
   rich temporary diagnostics; validation-only rules do not activate this path.
2. Explicitly audit boundary-local `CompiledGraph` copies created by
   `_run_validation_rules` / `_run_budget_validation_rules`. Root graph expiration
   in `_reduce_explanation_metadata` does not establish the lifetime of escaped
   boundary-local copies. Preserve safety and truthful evidence while measuring
   retention before choosing a narrower contract.
3. Establish minimum run failure evidence for early declarations, structural
   failures, build-rule failures and budget exhaustion. `_build_plan` strips
   optional requested diagnostic fields on run failures, but report graphs and
   escaped objects need the deeper evidence/liveness audit. Do not hide findings
   or replay callbacks to manufacture omitted evidence.
4. Preserve explicit full validation (`analysis.validation_report()`), fresh
   validation-only callbacks per request, no duplicate CLI/matrix pass, no implicit
   rebuilding, retryable failed builders and complete selected discovery.
5. Account for analysis orphan compilation and aggregated-failure attempts when
   comparing callback counts. Public roots/catalogue must stay distinct from
   analysis-only graph roots; retain the new resolvability and semantic-diff tests.
6. Retain the initial validation-only-rules fix, parked artifact compatibility and
   private historical regression coverage. No task 06–09 optimization is adopted.
   This task settles policy/retention; allocation minimization remains the next
   tasks' responsibility.
