# 24 — Migrate tooling, documentation and consumer validation

Created: 2026-10-10\
Status: Complete — implementation, full quality checks and consumer verification reviewed; [result](24-result.md)\
Assignment: `/root/graph_memory_task_24`, high reasoning\
Recommended reasoning effort: High (`high`)\
Prerequisites: 19–23; actual Bark/Cop verification fixtures and patches

Migration target: the reviewed [19-contract](19-contract.md).
The maintainer authorized sequential work on 21–24; all four tasks are implemented
and reviewed. Full library checks and actual Bark/Cop unit/integration verification
pass. Consumer adaptation used isolated copies; original checkouts remain unchanged.
See the [result](24-result.md) and [consumer evidence](evidence/24/consumers/README.md).

## Outcome

Make production call `build()` and development/CI call `analyse()`. The migration
is behavioral as well as syntactic: production no longer executes checks that used
to be mandatory. Do not keep old validation expectations hidden in a wrapper.

## Work

- CLI check/explain/manifest/diff/census/triage and build matrices call `analyse()`
  and read its completed report. Eliminate duplicate validation passes. Map partial
  analysis failures and rule exceptions to correct exit/report behavior.
- Migrate `BuildReport` imports to proposed `AnalysisReport`, use
  `AnalysisResult.report` and its coverage/outcomes, and move graph access to the
  result. Incomplete analysis is not a successful check. Test resolution uses
  explicit `result.create_runtime()` with result-owned cleanup, while production
  uses a fresh builder's `build()`.
- Remove `BuildMode`, `ValidationRuleMode`, runtime `build_mode`,
  `explain_metadata_enabled`, `allow_scope_builders`, `build_report`,
  `validation_report()` and runtime graph access. Update scope overlay composition
  ownership and single-attempt retry expectations, and migrate warmup/profiling
  serializers away from manifest fingerprint/path assumptions.
- Explain that an admitted build/analysis failure consumes its builder; use a
  fresh composition factory to retry. Show `result.create_runtime()` for tests
  that need the analysed execution plan without recompilation. Document optional
  external composition for overrides, no handle requirement for ordinary scopes,
  no separate composition close lifecycle, and its retained-memory cost.
- Compilation-profile tooling selects the named operation; do not retain a public
  `build(mode=...)` or fine-grained validation switch solely for this command.
- Migrate policies/bundles to `add_validation_rule(rule)` with no phase argument;
  remove `mode="validation"` and any explicit `mode="build"`. Both real Bark UoW rules
  remain registered, run during analyse, and are never run by build. No per-rule
  opt-in safety requirement or mandatory analysis token is introduced.
- Update examples, upgrade notes, errors, generated API references, fixtures and
  public tests. Historical benchmark sources/results retain their recorded meaning;
  archived private harnesses must not become a supported third operation.
- Adapt Bark's build wrapper, actual Cop application factories and tests in isolated
  copies when downstream work is assigned. Preserve empty automatic provider roots,
  private handler discovery, deferred decorators and dispatch behavior.
- Move invalid-UoW/captive/policy assertions to analyse tests and add explicit
  build-skips-rule tests. This is an intentional contract change, not an assertion
  removed to hide a failure. Keep actual runtime cleanup and capacity assertions.
- Define the documented separate validation workflow for CI using the same
  composition factory/inputs. Analysis of one input set is not claimed to approve
  every environment or future runtime configuration.

## Acceptance

- Full library CI, executable docs, strict docs and supported-Python checks pass.
- Actual Bark/Cop unit and integration verification checks discovery (previously
  245 API / 332 worker entries), real command/reply/saga dispatch and cleanup.
  Compare semantic catalogues, not random IDs between independent builders.
- Valid analysis returns full findings in one call; invalid policy fixtures fail
  analysis; production builds neither call nor retain the validators.
- Consumer patches and actual source/import hashes are recorded. No release,
  production deployment or edits to unrelated checkouts are implied.

Performance acceptance belongs to 25; passing compatibility tests is insufficient.
