# 05 — Decorator compilation and activation

Status: Implementation verified; independent review pending. Dependency: 04 accepted (`596e12a`).
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 03/04 handoffs.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-astra | high |
| Independent review | gpt-6-astra | high |

Astra High is recommended for integration of exact source binding, target generics, filter context, and activation.

## Bounded outcome

Deliver the first end-to-end template feature on the root builder, using the existing decorator pipeline.

## Search assignment

Locate decorator materialization/argument inference, selection filters, order calculation, lifespan/cleanup,
sync/async activation, and cached plans. Identify the M03/M04 interfaces and current ordinary-decorator tests.

## Implementation assignment

- Wire M04 source expansion before runtime compilation, then generated definitions into group/derived target selection and generic specialization.
- Before exposing the public API, connect M04's one-shot boundary consistency primitive to the actual generated decorator compiler. Recheck from the normalized expanded snapshot and compare initial ordered uses/exposes; test selector-based generated effects rather than relying on M04's synthetic ordinary-decorator probes. Preserve source/template provenance and original boundary causes; do not rerun expansion callbacks to seek a fixed point. Full boundary/overlay scenarios remain M06.
- Evaluate generated-template `when` against one `_undecorated_component_view(core)` snapshot per target occurrence
  (M01 helper in `components.py`). It excludes attached decorator branches recursively while retaining original
  parent/argument context and selected dependency/owner facts. Reuse that snapshot for every generated predicate
  at the occurrence, skip it with no generated candidates, and assess copying only relevant context for scale.
  Keep ordinary decorator predicates on their existing view; do not recompile targets as roots.
- Compile source argument selection by exact registration identity. Preserve source conditions/configuration,
  generic specialization, and declared lifespan without reconstructing the source implementation.
- Retain existing decorated-argument validation, callable/class support, async behaviour, cleanup, and target lifespan.
- Apply positions and tie-breaking relative to ordinary decorators and source declaration order.
- Prevent duplicate layers from repeated membership, multiple inheritance paths, or multiple resource matches.
  Distinct templates remain additive even when they use the same decorator class.
- Publish/export the agreed usable surface and maintain ordinary decorator compatibility.

## Verification and review gate

Use independent portable fixtures with two source families and targets using either, both, or neither.
Cover group nonmembers, opt-out filters, descendant-only resources, decorator-introduced resources, factory/instance
targets, open/pattern-backed closed requests, same-name TypeVars, and source/target declaration permutations.
Verify sync/async success and failure cleanup and that runtime resolution/inspection does not rerun composition callbacks.

Reviewer must check actual runtime instances/wrapper order and dependency identity, not only compiled graph shape.
Document that full overlay/boundary/edit acceptance follows in M06; no release claim yet.
