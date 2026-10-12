# Task 24 inventory

The task-relative patch changes 159 files. [Changed-source hashes](evidence/24/changed-source-hashes.json) enumerate each before/after identity; [final-source hashes](evidence/24/final-source-hashes.json) cover all 295 captured source/documentation files. The starting compiler is task 23's `e81406c5c439144e618a6891ec64450c5107ba7e4fc5b69bd75a8314a98dc28e`; final compiler is `f63fce1615aa2614d747d0caa318b99e881d26d72a7c10943069679205641896`.

## Public package and tools

| Surface | Change |
| --- | --- |
| `clean_ioc/container.py` | Remove legacy runtime APIs/private harness; capture result-owned census/triage; preserve policy attribution and incomplete coverage; fix selection/audit integration defects |
| `clean_ioc/tooling.py`, `__init__.py` | Remove `BuildReport` alias/export; current analysis guidance |
| `clean_ioc/cli.py` | One explicit analysis per inspection/check target; completed report/partial failure handling; named compilation-profile operation |
| `clean_ioc/matrix.py` | Fresh analysis per variant, completed findings, result cleanup |
| Tests | Policy assertions moved to analysis; execution/binding/cleanup/capacity guards kept on runtime paths; explicit composition ownership and one-attempt builders |

The census/triage result methods are a justified integration addition: completed one-attempt analysis needs a public owner for failure facts once runtime inspection APIs disappear. They capture immutable facts before return, preserve partial lower bounds and exact final report attribution, and do not retain a compiler/exception or replay callbacks.

New and extended regressions cover build skipping all checks, impossible binding without a rich error, bounded-generic decorator compatibility and concrete mismatch, generated decorator origins, parent-anchor metadata, explicit provider policies, empty discovery declarations, same-text findings from multiple boundaries in complete and partial results, and repeated read/runtime creation callback counts.

## Documentation and examples

README, Unreleased CHANGES only, V1_TO_V2_UPGRADE, V2_DEVELOPMENT, CLI/compiler/validation/scopes/policy/generic/decorator/provider/warmup/profiler/FastAPI guides and examples describe separate operations. `scripts/validate_docs_examples.py` uses completed analysis and fresh builders. Packaged use/migrate/FastAPI skills and references are updated; the migration script reports retired APIs requiring semantic decisions, with meaningful migration tests.

Current examples show external composition for overlays and ordinary scopes without handles. Historical benchmark pages are explicitly labelled; recorded numerical evidence is unchanged. Current driver command examples use named operations. Earlier source hashes and evidence were not rewritten for lint.

## Benchmark and experimental surfaces

- Active BenchBro definitions use production build or explicit fresh analysis, externally retained composition for overlay fixtures, and accurate registered-rule scenario names. Discovery ran on every supported Python lane; no benchmark was executed.
- Current graph-memory/reachability drivers expose `--operation build|analyse`; inspection requires analysis. Measurement CLI tests inject a stub backend to verify parsing, forwarding and output contracts without sampling memory or timing.
- Current compiler/catalogue/optimization helper drivers use named operations. The compilation-budget fixture preserves budget refusal behavior and has eight correctness-only fixture checks.
- The private artifact schema is 9 and serializes restricted execution plans. Unsupported instances/factories/boundaries/slots/warmups and pre-resolution restrictions remain. Fresh-process round trips verify execution semantics and no compiler/reflection replay.
- Ten historical independent-toggle entrypoints now stop explicitly: diagnostic_names, optional_diagnostics, deferred_advisories, early_rejection_records, declared_provider_roots, empty_dependency_validation, frozen_draft_capacity, invariant_subplan, failure_aggregation and compact_runtime evidence drivers. Exact original `.py.txt` sources and hashes are preserved under `evidence/24/retired-drivers`.

## Checks and reproducibility

[Check results](evidence/24/check-results.json) and [logs](evidence/24/checks/) record full CI on Python 3.11–3.14, full pre-commit, strict documentation, executable examples, discovery and FastAPI minimum/latest compatibility. `.work` is historical investigation material excluded from ty; only immutable graph-memory evidence is additionally excluded from Ruff. No active package or test exclusions were added.

`task-relative.patch` applies to the exact task-start snapshot recorded by `start-source-hashes.json`; unchanged-at-start `pyproject.toml` and `mkdocs.yml` hashes are in `start-extra-source-hashes.json`. Reconstruction applied the patch in an isolated directory, matched every final source hash and verified imports there. The final package manifest is independent of documentation and consumer artifacts and remained unchanged during final checks.

## Consumers

Root owns isolated Bark/Cop copies and the sanitized consumer annex under `evidence/24/consumers`. Production adapters call build; explicit CI adapters call analyse. Both actual UoW rules remain registered under the unified API. Consumer source patches, import proofs, original-checkout hashes, semantic catalogues, callback counts and final unit/integration results are retained there. The frozen final sweep passed 6,040 Bark tests (29 existing skips), 504 Cop unit tests and all 64 integrations, with catalogue counts 245/332. All four patches passed apply checks; 750 Bark and 150 Cop original source files are unchanged. Original Bark/Cop checkouts and preserved baselines are unchanged.

No memory/timing comparison, package release, deployment, commit or push is part of this inventory. Performance acceptance remains task 25.
