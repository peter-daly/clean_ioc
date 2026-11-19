# 20 — Move all validation into analyse

Created: 2026-10-10\
Status: Complete — scoped source/evidence review accepted; integrated acceptance remains with 21–24; performance deferred\
Assignment: `/root/graph_memory_task_20`, extra-high reasoning\
Recommended reasoning effort: Extra high (`xhigh`)\
Prerequisites: 19; current rule/failure/lifetime inventory

Contract input: [19-contract](19-contract.md) and [19-inventory](19-inventory.md),
reviewed with the maintainer's accepted builder/composition decisions. The
maintainer assigned this task on 2026-10-10, authorizing its local implementation
and verification. Subsequent maintainer direction defers further memory/timing
measurements until all compiler changes are integrated for task 25. Source and
environment baselines and completed samples are preserved; no additional
measurement is a prerequisite for implementation. Continue correctness and
quality checks during this task; do not run per-step performance comparisons.
Tasks 21–25 remain unassigned; preserve their implementation/acceptance boundaries.
No commit, push, release or deployment is included in this assignment.

## Outcome

Give `analyse()` sole ownership of built-in validation and registered rules,
including every rule formerly in either group, through one unified rule category. Merely skipping
`_run_validation_rules` is insufficient: validation is embedded in preparation,
specialization and instruction compilation.

## Work

- Audit `_compile_with_report`, `_finalize_plan`, boundary/alias preparation,
  `_validate_captive_lifespan`, `_validate_runtime_context_dependency`, factory
  return compatibility, per-call checks and warmup checks against task 19's matrix.
- Split helpers mixing computation and checking. For example effective context
  lifespan and cleanup ownership are needed to emit steps even when their policy
  checks are absent. Avoid two divergent implementations of dependency selection.
- Build must never call root, boundary or inherited validation rules, iterate
  their returned generators, create a validation context or request rich evidence
  because a rule is registered. Remove the `conservative_rules` production fallback.
- Analyse constructs full evidence, performs built-in checks and executes all
  applicable rules before returning. Preserve deterministic context/order and
  diagnostics, including AST readers, private/deferred paths and failure provenance.
- Do not abort at the old build-rule gate before the rest of full analysis can
  inspect an otherwise compilable graph. For incomplete graphs, report the original
  failure and which checks could not run rather than claiming full validation.
- Preserve analysis partial graphs/retry evidence where supported. Keep build
  failures small and local; no diagnostic root retries or replay of callbacks.
- Use one `add_validation_rule(rule)` registration with no phase argument. Remove
  the internal build/validation category split and migrate all old declarations.
  Preserve deterministic registration/context ordering without a second validation
  phase. There is no requirement-declaration DSL, source-based purity inference,
  or compatibility path that runs rules in build.

## Verification

- Root/boundary/inherited rules with counters, side effects, yielded errors and
  exceptions: build invokes none; analyse invokes each applicable declaration in
  its intended context and reports findings or callback failure.
- Both real Bark UoW rules stay registered. Build skips both by design; analyse
  runs both and catches invalid UoW cases. This deliberately replaces prior tests
  that expected mandatory UoW rejection during production compilation.
- Captive lifetime, factory mismatch, entrypoint/architecture and mixed-helper
  cases follow the approved matrix; wiring remains identical for valid inputs.
- Reading reports, CLI check and matrix capture do not execute a second pass.
- Return `AnalysisResult.report` with complete/invalid/incomplete coverage, explicit
  rule outcomes, and preserved findings before a callback failure. Under the
  recommended contract, custom full-graph rules are unavailable on an incomplete
  graph; built-in partial/declaration checks still run where supported. Policy
  errors on a complete graph do not suppress any rule.
- Audit registration-time rejections against the inventory, including group
  compatibility, typed-provider value overrides, configured names, return-only
  generics and per-call conformance. Do not move policy rejection earlier merely
  to keep it outside the `build()` body.

Deliver a source-backed check matrix and focused tests. Coordinate with 21–23;
do not publish a half-migrated public API while old hidden validation paths remain.


## Implementation result

See [20-result.md](20-result.md) and the [source/check matrix](20-inventory.md).
The final compiler SHA-256 is
`502988d4c3af9faa33577e82e7bd8bde53a7b55c639a6dca01acee43806051d8`.
262 focused tests pass in the workspace and from an isolated reconstruction of
the task-relative patch. Both real Bark UoW rules are verified with build/analyse
counters and invalid lifetime/SQL fixtures. Type, lint and format checks pass.
Tasks 21–24 retain their documented ownership, finalization, runtime-feature and
migration work; final performance acceptance remains deferred to task 25.
No release or memory-saving claim is made by this result.
