# 04 — Source filtering and template expansion

Status: Accepted; all applicable gates passed, final checkpoint ready. Dependency: 03 accepted (`530a725`).
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 01/03 handoffs.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-astra | high |
| Independent review | gpt-6-astra | high |

Astra High is recommended because real source-component graphs, compiler ordering, and retries must agree.

## Bounded outcome

Create source-bound candidate decorator definitions at the compiler phase proven in M01.
Target decoration/activation is completed in M05. Keep any not-yet-usable entry points internal until end-to-end wiring.

## Search assignment

Recheck actual compiler phase changes since M01, registration source views, definition provenance, canonical aliases,
undecorated graph filtering, expansion failure paths, and blueprint storage.

## Implementation assignment

- Add immutable template definitions/source metadata and the agreed builder/protocol surface.
- Enumerate exact visible source service registrations after discovery. Support generic implementations without
  pretending an open generic source service has a finite implicit set of specializations.
- Evaluate ordinary source ComponentFilters against the agreed real undecorated source context. Support descendants,
  parent context, tags, names, lifespan, and static generic metadata without creating runtime objects.
- Call the template factory per selected source identity; retain exact ID, specialization, and source arguments.
  Never replace a selected source with a name/type-equivalent registration.
- Produce candidate decorator definitions with template/source provenance and deterministic declaration/source order.
- Enforce source visibility and minimum cycle/retry safety now. Do not postpone fundamental invalid-plan protection
  until M06/M07. No fixed-point loop that repeatedly calls user predicates to recover from unstable expansion.

## Verification and review gate

Test zero/two/same-type sources, distinct generic sources, composed source filters, real descendant traversal,
source conditions, late discovery, factories with only broad declared types, retry after failure, and expansion cycles.
Sentinel constructors/factories must demonstrate no activation during enumeration/filtering/expansion.

Review must check the M01 staging contract is actually implemented, with no incomplete frozen target plan.
Record generated-definition interfaces and remaining M05 activation work in the handoff.
