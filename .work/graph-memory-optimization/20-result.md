# Task 20 — Completed analysis/validation pipeline

Date: 2026-10-10\
Status: Implementation and focused correctness verification complete; scoped coordinator review accepted\
No commit, push, version change, release, deployment or consumer edit.

Coordinator review: inspected rule execution/report completion, analysis/runtime
ownership boundaries and focused coverage; verified 65 source/patch hash entries
against the recorded final state. Accept the task 20 validation-separation work
as the base for sequential tasks 21–24. The follow-on gaps below remain explicit;
this is not whole-suite, release or performance acceptance.

`build()` now executes no custom validation rules and bypasses built-in policy audits. `analyse()` returns a distinct `AnalysisResult` with a completed immutable `AnalysisReport`: findings, root coverage, built-in stage coverage and one outcome per applicable rule declaration. Policy-invalid but emittable graphs continue through all rules. Callback failures retain preceding findings and permit later rules; partial graphs make custom full-graph rules explicitly unavailable. Report reads never replay work.

The [source/check matrix](20-inventory.md) records the mixed registration, preparation, specialization, compiler, deferred-provider, per-call and warmup decisions. The same binding/selection/cache/cleanup machinery still emits instructions. Actual runtime guards remain. One-attempt builder admission and `create_runtime()` from the already emitted plan are the minimal shared API plumbing needed for this task. Later ownership/finalization work is explicitly listed below.

## Verification

- **262 tests passed** in the workspace: 61 new pipeline regressions; migrated factory, policy and matrix tests; 12 selected existing runtime/cleanup regressions. [Exact commands](evidence/20/verification.json), [test log](evidence/20/pytest-final.log).
- **262 tests passed again from an isolated reconstruction** made by copying the frozen pre-task source and applying only the task-relative patch. Every changed source/test file byte-matched the workspace; imports came from the reconstructed source. [Reproduction identity](evidence/20/reproduction.json), [patch log](evidence/20/patch-reproduction.log), [isolated test log](evidence/20/reproduced-pytest.log).
- Ruff check, format check and `ty` passed on all seven changed package files; lint/format also covered the four changed test files. [Ruff](evidence/20/ruff-final.log), [format](evidence/20/format-final.log), [type check](evidence/20/ty-final.log).
- **Both real Bark callbacks verified**, using unchanged captured `bark_core.unit_of_work.bundles` and actual Bark test fixtures. Build invoked neither; analysis invoked each once and caught invalid UoW lifetime, SQL writes without ownership and nested SQL begin. Repeated text/JSON/SARIF exports left callback counts unchanged. The local proof adapter removes only the old registration phase argument; it does not remove, replace or stub either rule implementation. [Proof program](evidence/20/bark_rules_correctness.py), [final output and source hashes](evidence/20/bark-rules-correctness.json). An initial probe used the COP environment, which lacks SQLAlchemy; the completed proof uses the preserved Bark environment.

Coverage includes ordinary/private/generated/deferred policy cases, rejected and unused declarations, exact rule ordering/context, malformed/throwing generators, cooperative budget interruption, completed/failed/unavailable/interrupted outcomes, fatal allocation failure and internal compiler defects, original failure preservation when retries succeed, report-read stability, entrypoint-filter failure, and unavailable rules after failed warmup binding.

This is not a whole-suite pass or consumer migration claim. Historical tests expecting `build(mode=...)`, production policy rejection, repairable consumed builders, runtime-owned graph APIs, or replaying `validation_report()` remain to migrate with tasks 21–24. Forbidden compatibility behavior was not retained to satisfy them.

## Exact identity and reproduction

- Base HEAD: `34d1ea02840afe6f23f0693b32651028ec7d9128`, branch `version2`, with the entire accepted dirty state preserved before editing.
- Package label remains `2.0.0rc4`; it is not the source identity.
- Pre-task compiler SHA-256: `1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223`.
- Final compiler SHA-256: `502988d4c3af9faa33577e82e7bd8bde53a7b55c639a6dca01acee43806051d8`.
- [Task-relative patch](evidence/20/task20.patch) SHA-256: `f84ea4f9051f6f9e89b5ed31a7050aeffa0eeee9027cafc810481a5f617e8458`.
- [Changed-file and supporting source manifest](evidence/20/final-source-manifest.json); [preserved dependency identities](evidence/20/environment-identities.json).

The patch covers `container.py`, `components.py`, `policies.py`, `tooling.py`, package exports, minimal CLI check/matrix integration, and four test files. It excludes all pre-existing changes. To reproduce correctness in the live checkout, run `.venv/bin/python .work/graph-memory-optimization/evidence/20/verify.py`. That program executes correctness, lint and type checks only. For the already reconstructed source, use the recorded command/cwd in `reproduction.json`; the preserved library environment supplies dependencies and `PYTHONPATH` points to that reconstruction. `package_evidence.py` records the one-time reconstruction and deliberately refuses to overwrite it.

## Baselines retained; further measurements deferred

The private preservation root is:

`/Users/peter.daly/.codex/task-baselines/clean-ioc-task20-20261010-v2`

It contains the complete relevant pre-task source, dirty source/test/fixture changes, supporting files and lockfiles; the reconstructed task 10/11 source; all prior graph-memory evidence; consumer handover evidence; complete original/current consumer working roots and environments; and the library environment. Private consumer settings and raw stderr remain outside the repository. [Preservation metadata](evidence/20/baseline-preservation.json), [source manifest](evidence/20/preserved-source-manifest.json), [initial dirty patch](evidence/20/initial-dirty.patch), [initial status](evidence/20/initial-status.txt).

The original consumer compiler was confirmed and preserved at SHA-256 `6253f5e38bd8819099db53514ede0d3c0efc4f451b3ea33f05c6e4a9932e4253`. Task 10/11 source at `4a6c447812f7b313b96d2ce3bf09aab54207f24d88764b830a4c24010be5b683` was reconstructed from task 18's captured source overlay on the preserved supporting tree. Isolated functional imports/resolution succeeded for the pre-task and task 10/11 sources; hashes are in `current-reproduction.json` and `task10-11-reproduction.json`.

Before the maintainer deferred measurement, 36 serial native prerequisite samples had completed: API/worker × original baseline-full/current run/current analysis × three untraced and three traced samples. Both real consumer rules remained registered. The last sample had already finished when steering arrived; nothing was interrupted. [Raw sample records](evidence/20/native-baseline-samples.json) preserve actual imports/hashes and registration counts. Full raw output is under the private root's `prerequisite-samples`. There were no further timing/memory samples or task-20 performance comparisons after that direction. The historical sampling/preservation scripts are evidence of that earlier work, not instructions to rerun benchmarks now.

No memory saving, startup improvement, process-memory reduction from moved ownership, or isolated cause of the consumer upgrade regression is claimed. Final native/Linux untraced and traced measurements belong to task 25 after tasks 20–24 integrate.

## Required follow-on boundaries

1. **Task 21:** execution-only finalization/projection; consumed declaration release; independent preconfiguration state for separate created root runtimes; retain a completed execution projection when inspection-only architecture compilation fails. A small `CompiledGraph` bridge is still constructed for current runtime-feature readers.
2. **Task 22:** remove remaining optional evidence/census/origin allocations throughout ordinary build. The complete task 19 zero-allocation contract is not finished by task 20.
3. **Task 23:** external immutable Composition ownership and parent matching, no separate Composition cleanup lifecycle; warmup and instrumentation without graph/manifest readers. `AnalysisResult.composition` is currently `None`, and test runtimes still retain analysis graph/blueprint support.
4. **Task 24:** finish public tooling/runtime-report API and all consumer/test/doc migration. `BuildReport` remains an alias for the captured `AnalysisReport`; non-check CLI loaders still have obsolete mode calls. This intermediate API must not be released.
5. **Task 25:** final integrated correctness/consumer/performance acceptance using the preserved actual source baselines, not version labels.

Task 20's policy separation and completed-report work is complete. These remaining boundaries are required later tasks, not acceptance claims for this one.
