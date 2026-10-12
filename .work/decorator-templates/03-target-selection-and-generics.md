# 03 — Generic projection and DerivedServices

Status: Accepted; all applicable gates passed, final checkpoint ready. Dependency: 02 accepted (`fa33b7f`).
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 02 handoff.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-astra | high |
| Independent review | gpt-6-astra | high |

Astra High is recommended for multi-level generic projection, protocol bases, aliases, and registration identity.

## Bounded outcome

Supply a common internal target-selection and contract-projection interface for explicit groups and DerivedServices.
This milestone does not activate decorators.

## Search assignment

Find current decorator service matching, generic specialization helpers, type-alias handling, concrete closed requests,
and existing regressions for inherited/reordered generic variables. Check supported Python syntax/version boundaries.

## Implementation assignment

- Select explicit group members by registration identity.
- Add immutable, reusable `DerivedServices(Base)` selecting base/explicitly derived registered service contracts.
  Do not match a compatible implementation registered under an unrelated service key.
- Project concrete target services onto the declaration's contract, keeping the original requested service identity.
  Complete the unresolved membership validation handed off from M02.
- Cover fixed/reordered parameters, multi-level inheritance, aliases, repeated variables, concrete generated subclasses,
  same-named distinct TypeVars, and conflicting projections. Preserve declaration identity in generic bindings.
- Include closed requests from open registrations and structural patterns, plus queued discoveries. Avoid scanning
  all possible generic specializations or inferring explicit group membership.
- Keep candidate ordering/deduplication deterministic. Do not introduce runtime service aliases.

## Verification and review gate

Prove explicit nonmembers are excluded, derived selection includes newly discovered compatible services, and both forms
produce equivalent projections when they select the same registration. Exercise factory/instance targets and
unrelated-service negative cases. Ambiguous/unresolved mappings must fail clearly without guessing.

Review the shared interface and run generic/alias/group regressions. Handoff the matching/projection API for M04–05.
