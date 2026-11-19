# 11 — Define validation requirements and minimum failure evidence

Created: 2026-10-10\
Status: Complete — scoped lifetime/failure implementation retained; further construction narrowing deferred\
Assignment: `/root/graph_memory_task_11`, extra-high reasoning, sequential workstream\
Recommended reasoning effort: Extra high (`xhigh`)\
Priority: Establish safety before omitting temporary evidence\
Prerequisites: [10 mode contract](10-run-and-analysis-modes.md); task 06 counterexamples

## Outcome

Separate information required for correct compilation and mandatory build rules
from optional analysis evidence. Make run mode lean without weakening safety or
reintroducing either consumer regression: unavailable discovery or rejection
merely because validation-only rules are registered.

## Work

- Inventory built-in checks, build-mode callbacks, validation-only callbacks,
  boundary-local rules and inherited overlay rules. Trace their reads of topology,
  ownership, origins, selected/rejected decorators, template facts and histories.
- Preserve every mandatory structural/build-mode check. Rules registered for
  explicit validation remain dormant in run builds; registration alone never
  forces analysis retention or causes rejection.
- Specify the full-validation pass for a fresh analysis build with task 10.
  Ensure CLI/matrix integration runs the intended callbacks exactly once per
  requested pass. Retain build findings without rerunning build callbacks.
- Design conservative handling of existing arbitrary build rules. They may
  require rich temporary graph facts. Keep those facts for their actual lifetime
  until a narrower, explicit requirement is established; never guess requirements
  by inspecting callback source or silently skip the rule.
- Investigate rule requirement declarations or a smaller validation context.
  This is a rule contract, not another fine-grained build option. Unknown existing
  rules need a safe compatibility path; a declaration must be checked and have
  documented failure behaviour when a rule accesses undeclared capabilities.
- Define run-mode failure facts: useful code/message, dependency path and
  relevant origin/selection witness. Retain evidence at the original decision;
  never rerun derivations, filters or templates after failure to recreate it.
- Full analysis captures the supported histories and independent failures.
  Distinguish intentionally unavailable run evidence from empty/complete reports.
- Keep `selected_registrations`, implementation types and registration identity
  available in run mode, including selected private/deferred paths and decorators.

## Evidence and boundaries

[Task 06](06-result.md) rejected coarse omission of decorator evidence because
build rules and failed-finalization reports consume it. The RC4 discovery fix
and current local deferred-validation fix establish consumer requirements.
Neither the rich fixture's lack of custom rules nor a passing no-rule benchmark
proves rules can safely lose evidence.

## Acceptance and deliverables

- Reader/lifetime inventory and a concrete validation/error capability contract.
- Cases for build errors, validation-only findings, boundaries, overlays,
  budgets, callback failures, unsuccessful-builder retry and saved callback views.
- Legacy build rules continue to run correctly; narrowed rules demonstrate
  avoided allocations without callback replay or changed decision ordering.
- Fresh analysis reports full findings; run analysis APIs fail clearly; retained
  callbacks/graphs are released when no supported capability needs them.
- Bark/Cop-shaped command/saga rule registrations and discovery are covered.
  Actual downstream verification is a separate task 18 result, not inferred.

Readiness gate: task 10's lifecycle is settled and the minimum evidence plus
legacy-rule compatibility contract is reviewed. This task may legitimately limit
the savings available when an application registers a rich build-time rule.

Completed outcome: [result](11-result.md), [reader/lifetime contract](11-inventory.md).
Unknown rules remain rich; no requirements DSL or coarse evidence omission was adopted.
