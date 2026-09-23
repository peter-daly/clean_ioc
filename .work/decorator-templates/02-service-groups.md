# 02 — Explicit service-group membership

Status: Search accepted; implementation awaits search checkpoint. Dependency: 01 accepted (final checkpoint `485e27d`).
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 01 handoff.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-sol | high |
| Independent review | gpt-6-astra | high |

Sol High is recommended for bounded declaration/metadata plumbing once M01 has resolved the architecture.

## Bounded outcome

Represent explicit group membership consistently across all registration paths, without changing resolution.
Decorator execution and automatic derived-service selection belong to later milestones.

## Search assignment

Map `ProviderMapGroup` identity/contribution handling, registration APIs and protocol, queued discoveries, patterns,
alias normalization, layer snapshots, and specialization metadata copying. Locate tests for transactional registration.

## Implementation assignment

- Add immutable group declarations with identity equality and diagnostic labels.
- Add `groups=` to agreed builder/protocol registration paths: direct class/factory/instance, subclass discovery,
  generic-subclass discovery, and structural patterns. Materialize iterable inputs once.
- Store membership on registration definitions. Propagate through discovered registrations, snapshots, normalization,
  and specialized copies. Avoid storing per-builder members in the shared group object.
- Implement known contract validation using the M01 helper and defer legitimately unresolved specialization checks
  to the M03 interface. Keep declaration-time rejection transactional.
- Preserve ProviderMapGroup/contributes and ordinary resolution. Repeated membership is idempotent; registrations
  of one class can have different groups. Empty and same-name/different-identity groups remain well-defined.

## Verification and review gate

Exercise all registration paths, generator inputs, multiple groups, independent builders, incompatible contributions,
aliases, and unchanged provider maps/resolution. Verify no global membership leakage and no partial state after failure.
Tests should observe registration/selection behaviour through available boundaries, not only dataclass serialization.

Handoff states where unresolved generic contract validation is completed in M03. Do not claim decorators work yet.
Record review acceptance before M03.
