# 08 — Local bark-core integration proof

Status: Not started. Dependency: 07 accepted.
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 07 handoff.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-astra | high |
| Independent review | gpt-6-astra | high |

Astra High is recommended because cross-repository policy wiring, transaction validation, and generic handlers interact.

## Bounded outcome

Prove the feature against real application composition while keeping all bark-core work local and uncommitted.
This is internal integration evidence, never public documentation reference material.

## Search assignment

Recheck both repositories' current status and applicable instructions. Map SQLAlchemy/DynamoDB UoW registration,
shared handler bundles, saga/data-protection discovery, policy markers, retained decorator handles, and validation.
Find focused unit and available SQLite/integration tests; do not assume the old baseline/environment is unchanged.

## Implementation assignment

- Verify bark-core imports this clean-ioc checkout. Prefer the feature contract's process-local import override.
  An editable dependency is authorized if necessary, but record the pin/environment changes and avoid auto-sync reversal.
- Declare a shared explicit group and contribute ordinary, saga, and deferred data-protection handler registrations.
- Install independent source-filtered backend templates; remove task-local per-service/per-UoW handler-policy wiring.
  Add a previously unknown compatible family through group contribution. Also exercise DerivedServices in a bounded
  alternative composition so both paths are validated.
- Preserve exact session/UoW binding, coordinator behaviour, resource tags, disabled policies, opt-out, and positions.
- Adapt policy evidence/validation intentionally, including explicit exclusions, nonmembers, custom group members,
  and independent resource-safety checks. Do not make tests pass by weakening transaction ownership validation.
- Fix any clean-ioc defects with portable synthetic regression tests that do not require bark-core imports or code.
- Keep a ledger of task-owned code/dependency/environment changes. Do not commit, reset unrelated work, publish,
  deploy, or change external databases for this proof.

## Verification and review gate

Re-run the focused baseline (previously 110 passing tests; current counts may differ) plus new group/template scenarios.
Exercise named/generic SQLAlchemy sources, DynamoDB mocks, mixed resources, sessionless/opted-out handlers, dynamic
registration, custom families, and transaction success/failure with available local SQLite tests.
Record unavailable external-service checks explicitly, without claiming they passed.

Astra review covers clean-ioc regressions and the bark-core diff. Handoff lists every task-owned change, actual imported
checkout, before/after git state and no task-created bark-core commits. Restore only temporary task-owned wiring no longer
needed; retained local experiments must be listed. Public documentation must not be generated from this handoff.
