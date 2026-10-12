# Task 26 result — verify and direct VerificationReport

Implemented on 2026-10-12 by `/root/graph_memory_task_26` at medium reasoning.
Both `ContainerBuilder.verify()` and `ScopeBuilder.verify()` now return the public
`VerificationReport` directly. `report.assert_valid()`, `is_valid`, findings,
coverage, rule/stage outcomes, text/JSON/SARIF, graphs, census, triage, selected
registrations, composition and explicit `create_runtime()` are available on that
object. There is no `analyse()` entry point, nested `report` property, or permanent
`AnalysisResult`/`AnalysisReport` compatibility alias.

## Implementation decisions

The existing immutable findings dataclass became `VerificationReport`, with a
private mutable `_VerificationRuntime` sidecar for emitted-plan and test-runtime
ownership. Findings remain frozen and readable after close/aclose. Runtime cleanup
still runs in reverse creation order, attempts every cleanup, preserves independent
runtime caches, and leaves borrowed parents open. Each report-created runtime has
no backreference to the report. Failed triage facts retain a findings-only snapshot;
reads associate them with the public report without creating an ownership cycle.
Matrix snapshots explicitly remove the sidecar before copying captured records.

Validity and emission remain independent. Complete reports with warnings alone are
valid; errors or incomplete coverage fail `assert_valid()` with captured SARIF,
including under `python -O`. A policy-invalid report can still contain an executable
plan. Verification does not activate application constructors. Inspection,
serialization, assertions and runtime creation do not replay rules or selection
callbacks. Existing failed-attempt identities, distinct declaration findings and
source/boundary attribution remain intact. Admitted attempts remain single-use.
Production `build()` still performs execution compilation only, without validation
callbacks or policy audits; `add_validation_rule(rule)` stays the single rule API.

Public outcome/error names are now `VerificationRuleOutcome`,
`VerificationStageOutcome`, and `VerificationRuntimeUnavailableError`. CLI/matrix
callers, compilation profiling (`--operation verify`), active benchmark definitions,
examples, tests, packaged skills/codemod guidance and upgrade documentation use the
new API. The codemod reports legacy RC5 imports and calls for review. The upgrade
guide explicitly maps `builder.analyse()` and `result.report.assert_valid()` to
`builder.verify()` and `report.assert_valid()`.

Internal `_AnalysisState`/`_ANALYSIS_STATE`, graph-analysis algorithm names, private
analysis helper names and existing descriptive test names are deliberately retained:
they describe compiler/graph machinery, not an alternate public operation. Historical
`.work` records, archived sources, raw measurements and source-hash evidence are
unchanged. The current benchmark case is `compiler-verification`; historical case
names and recorded measurements remain historical evidence, not renamed baselines.

## Validation

| Gate | Result |
| --- | --- |
| Full `make ci`, Python 3.11.13 | 2,517 passed, 8 existing version-specific skips |
| Full `make ci`, Python 3.12.11 | 2,522 passed, 3 existing version-specific skips |
| Full `make ci`, Python 3.13.5 | 2,525 passed |
| Full `make ci`, Python 3.14.4 | 2,525 passed |
| Ruff lint/format and ty | Passed in every CI lane |
| Executable documentation and BenchBro discovery | Passed in every CI lane; discovery only |
| Strict MkDocs | Passed |
| All pre-commit hooks, including actionlint and full tests | Passed |
| FastAPI minimum and previously resolved latest compatibility environments | 14 passed each |
| Direct verification and codemod migration tests | 13 passed |
| Final focused pipeline check after duplicate-assertion cleanup | 64 passed |

The existing broad suite covers root/overlay verification, callback counts,
warning/error/incomplete reports, budgets, partial graphs, census/triage, provenance,
single-use failures, CLI/matrices, independent runtimes and sync/async cleanup. New
tests explicitly check removed aliases, direct public assertions, frozen findings
remaining readable after ownership closes, validity without emission, and builder
assertion behavior in an optimized Python subprocess. Optional captured facts are
narrowed with a small test helper rather than weakening the new public graph types.
The only test warning is the existing upstream Starlette HTTPX deprecation.
Experimental Python 3.15-dev was not rerun; it is outside the supported matrix.

See [check results](evidence/26/check-results.json) and the adjacent text logs.
These are local macOS arm64 correctness checks, not performance acceptance.

## Isolated consumers

Fresh task26 copies of the preserved task24 Bark/Cop sources were migrated. Their
verification adapters now call `verify()` and assertions inspect the returned report
directly. No original checkout or preserved task24 copy was edited.

- Bark: **6,040 passed, 29 existing skips**.
- Cop: **504 unit tests passed**.
- Cop API and worker discovery remain **245 / 332 entries**, with identical
  build/verify catalogues, including private/deferred routes and decorators.
- Production builds call neither real UoW validator. Verification calls both once;
  repeated text/JSON/SARIF reads do not replay them. Three actual invalid UoW/SQL
  fixtures retain their expected errors. Valid consumer verification retains its
  existing warnings and has no errors.
- Hash checks confirm all 750 original Bark and 150 original Cop Python files,
  plus 750 Bark and 152 Cop preserved task24 files, remain unchanged.

[Consumer summary](evidence/26/consumer-summary.json),
[migrated file hashes](evidence/26/consumer-migration-files.json), and
[source integrity](evidence/26/consumer-source-integrity.json) record the checks.
Private environments, TLS files, credentials and raw consumer logs stay outside the
repository. Cop service integration tests were not rerun for this API-only change;
the prior task24 integration evidence remains intact.

## Source identity and boundaries

Base HEAD is `20e7dd599a0b97f4284368c1243888421fe18f63`; the changes are uncommitted.
The package remains `2.0.0rc5`, and `uv.lock` is unchanged. The final package source
manifest SHA256 is `9229d0e003ef65e6655a62a343541276ab103bbdc852cda7d04ab9e2eb329750`;
see [source identity](evidence/26/source-identity.json) and
[package hashes](evidence/26/package-hashes.json).

No commit, version bump, push, release, original-consumer mutation or task25 work
was performed. No memory, startup or timing comparison was run, and no memory gain
is claimed. If these changes are committed before task25 measurements, task25 must
record that integrated commit and source hashes rather than treating the unchanged
RC5 version label as an exact source identity. The released RC5 baseline is preserved.
