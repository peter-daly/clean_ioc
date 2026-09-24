# 06 — Composition edits, scopes, and boundaries

Status: Search accepted; implementation awaits checkpoint. Dependency: 05 accepted (`d62c87e`).
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 05 handoff.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-astra | high |
| Independent review | gpt-6-astra | high |

Astra High is recommended for ownership/visibility invariants and inherited blueprint behaviour.

## Bounded outcome

Make the root-builder feature safe and complete across composition edits, boundaries, and scope overlays.

## Search assignment

Locate template/decorator patch/remove conventions, layers, inherited registration precedence, boundary Use/Expose
contracts, owner tokens, parent singleton step reuse, and diagnostic retry compilers.

## Implementation assignment

- Implement the agreed pre-build template replacement/removal, including inherited suppression in overlays.
- Preserve templates, membership, IDs, order, and generic metadata through layered blueprints and normalization.
- Apply inherited templates to newly compiled eligible overlay plans and visible new sources.
- Keep parent-owned singleton activation anchored. Plain runtime scopes perform no re-expansion.
- An override carries only its own explicit group membership; same service key is not implicit membership inheritance.
- Respect private areas and ordinary boundary contract visibility. Shared group identity does not grant access.
- Ensure failed build/repair and diagnostic retries cannot accumulate or duplicate generated definitions.
- Preserve normal validation of unavailable/ineligible exact source dependencies.

## Verification and review gate

Test new source/new target overlays, multiple nested overlays, parent singleton ownership, template edits/removal,
named overrides with/without membership, private source/target boundaries, legal Use/Expose paths, and retry idempotence.
Compare actual instance/cleanup ownership with the graph. Run relevant existing scope/boundary/decorator tests.

Reviewer must explicitly check no private-source shortcut and no redecoration of anchored parent-owned objects.
