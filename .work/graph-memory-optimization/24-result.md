# Task 24 result — build/analyse migration

The library API, tooling, tests, documentation and consumer adapters now use separate `build()` and `analyse()` operations. Production builds execute no registered validators or built-in policy audits. Analysis returns completed findings, coverage and available graphs; tests can create a runtime from its emitted plan without compiling again.

## Public behavior

- Removed legacy modes, rule phases, fine-grained public flags, `BuildReport`, runtime inspection/report properties, `new_scope_builder`, and the historical private `_build`/`_observe_plan` harness. Validation rules use `add_validation_rule(rule)`.
- CLI inspection/check/diff/census/triage and matrices consume completed analysis. Invalid or incomplete analysis does not pass a check. Compilation profiling explicitly selects `--operation build|analyse`.
- External `Composition` handles support overlay declarations. Ordinary scopes need no handle; runtimes retain no composition/report backreference. Admitted failures consume the builder, so retry examples use fresh composition factories.
- `AnalysisResult.selection_census()` and `triage_report()` own immutable facts captured before return. Partial lower bounds, final merged findings, declaration/boundary attribution and diagnostic attempt identities survive without retaining a compiler or exception traceback. Reads never replay callbacks.

## Integration corrections

The full migration exposed genuine analysis defects as well as obsolete tests. Fixes retain explicit provider-argument and empty-discovery membership audits, generated/ordinary decorator provenance, safe hostile-signature reporting, authored bounded-generic decorator contracts, parent-anchor origin reconstruction from retained declarations, and failed/successful analysis issue attribution. Equal text from distinct declarations or occurrences remains distinct; duplicate aggregation copies from the same context collapse.

An inherited generated candidate now evaluates a known-false selection predicate before looking for its absent parent singleton anchor. This preserves rejection without manufacturing a singleton. Actual missing parent anchors still fail locally. Tests explicitly distinguish analysis-only policy failures from production binding/runtime guards, including the original impossible-binding production test.

The parked private artifact experiment now accepts a restricted `_ExecutionPlan` under private schema 9. It retains unsupported-input exclusions and correctness checks for topology, identity, caches, cleanup and fresh-process load without compilation/reflection replay. It remains unsupported and does not promise analysis metadata or a public precompilation API.

## Verification

All checks use the frozen package manifest in [evidence/24/final-package-hashes.json](evidence/24/final-package-hashes.json).

| Gate | Result |
| --- | --- |
| `make ci`, Python 3.11.13 | 2,512 passed, 8 existing version-specific skips |
| `make ci`, Python 3.12.11 | 2,517 passed, 3 existing version-specific skips |
| `make ci`, Python 3.13.5 | 2,520 passed |
| `make ci`, Python 3.14.4 | 2,520 passed |
| Whole-workspace Ruff, format, ty | Passed in every CI lane |
| Executable documentation and BenchBro discovery | Passed in every CI lane; discovery only |
| Strict MkDocs | Passed |
| All pre-commit hooks, including actionlint and full tests | Passed |
| FastAPI 0.121.0 / Starlette 0.49.3, Python 3.12.11 | 14 passed |
| FastAPI 0.143.0 / Starlette 1.7.0, Python 3.12.11 | 14 passed |
| Isolated task-relative reconstruction | 2,520 passed; all source hashes match |
| Functional fixture/audit/artifact checks | 34 passed; measurement backend not invoked |
| Compilation-budget fixture combinations | 8 passed; measurement backend not invoked |

The full suite preserves functional capacity, ownership and cleanup assertions. The only test warning is the upstream Starlette HTTPX deprecation. Checks ran on macOS arm64; this is local correctness evidence, not a Linux release/readiness or performance claim. Python 3.15-dev is the repository's experimental lane and was not run. `uv.lock` and package version `2.0.0rc4` are unchanged.

Exact task-relative reconstruction matched all 295 source hashes and passed all 2,520 tests independently. The harness also includes 13 unchanged HEAD fixture files (the lockfile and example applications). The final source-stable consumer sweep also passed; see the [consumer annex](evidence/24/consumers/README.md).

## Consumer verification

The isolated final sweep passed **6,040 Bark unit tests (29 existing skips), 504 Cop unit tests and all 64 Cop integration tests**. Bark’s earlier 6,055-case total included 15 duplicate legacy host-mode variants; those are explicitly reconciled in the annex. Policy assertions moved to analysis, while dispatch, provider, saga, ownership and cleanup checks remain. Cop integration source and capacity assertions are unchanged.

Fresh build/analyse catalogues match at **245 API / 332 worker entries**, including private/deferred handlers and decorators. Production builds call neither real UoW rule; analysis calls both once. Three actual invalid UoW/SQL fixtures still yield their expected errors, and completed report reads do not repeat callbacks. Valid consumer analysis has no errors; its existing warnings are recorded honestly.

The final sweep verified identical Clean IoC and consumer/test source hashes before and after, actual import paths, all four consumer patches against their recorded original/preserved sources, and unchanged hashes for 750 Bark plus 150 Cop original Python files. Owned integration services were cleaned up. The [consumer annex](evidence/24/consumers/README.md) links sanitized results and source identities; private service logs, credentials and TLS material are excluded.

## Evidence and boundaries

- Compiler SHA256: `f63fce1615aa2614d747d0caa318b99e881d26d72a7c10943069679205641896`.
- Package manifest SHA256: `63bf835d6647f56482331e7ac535689c50feb134538f6081b50a76935ac0d35d`.
- Task-relative patch SHA256: `e742f88db4e75253129854a9918abb4e38cffa03423dfa6c2e2aee0499926f4e`.
- Final source manifest SHA256: `7b388343d52743bd78282b201baf9dab6555406d717ede830398bc405a3a50e8`.
- [Inventory](24-inventory.md), [check logs and manifests](evidence/24/), and [task-relative patch](evidence/24/task-relative.patch).

Historical evidence is preserved at its recorded revision. Ruff excludes only archived graph-memory evidence; ty excludes `.work` investigation material. Live package, tests, tools, benchmark definitions and packaged migration script remain checked. Ten obsolete toggle experiments now explicitly reject the current API, with exact original sources archived and hashed in [retired-drivers](evidence/24/retired-drivers/).

No memory/timing/population comparisons were run, and no performance gain is claimed. Task 25 owns those comparisons after integration. No commit, push, version bump, release or deployment was performed.
