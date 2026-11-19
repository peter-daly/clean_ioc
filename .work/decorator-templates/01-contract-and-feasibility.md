# 01 — Contract and compiler feasibility

Status: Accepted; all gates passed, final local handoff checkpoint ready. Dependency: none.
Read the [workflow](README.md) and [feature contract](../decorator-templates.md).

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-astra | high |
| Independent review | gpt-6-astra | high |

Astra High is recommended because source graph filtering, generic projection, and decorator expansion interact with
compiler phase ordering; a wrong assumption here would propagate into every later milestone.

## Bounded outcome

Settle the implementable API and prove the difficult compiler staging with minimal portable probes.
Produce an accepted decision record and reusable helper/test seeds, not the whole feature.

## Search assignment

Locate registration snapshots/discovery, root and dependency compilation, undecorated graph views, decorator selection,
diagnostic retries, generic mapping, and inherited singleton handling. Identify existing reusable metadata types.
Start with `container.py`, `components.py`, `generic_utils.py`, `provider_maps.py`, and relevant tests.
Consult applicable generic-library skills when inspecting or extending that library's integration.

## Implementation assignment

- Settle public spellings for `ServiceGroup`, `groups=`, `DerivedServices`, source metadata, template factory,
  `source_filter`, target `when`, and pre-build template edit/removal. Preserve the agreed semantics.
- Prove a completed source core view can be filtered before relevant target decoration without publishing incomplete
  plans, changing normal runtime wiring, or activating application objects.
- Resolve the proposed canonical-root source context, contextual registration conditions, boundaries/overlays,
  deduplication, and the expansion-dependency-cycle diagnostic. Include a source depending on a target candidate.
- Prove projection from a registered derived generic service onto a group contract and independent generic source
  bindings, including a generated concrete subclass. Do not solve matching using TypeVar names alone.
- Record the compiler phase/data-flow design, stable ordering strategy, ID derivation, and minimum retained blueprint
  metadata needed by later milestones. Mark rejected approaches and why only when relevant to the chosen design.
- Use synthetic Clean IoC fixtures. Existing bark-core observations may validate assumptions internally; public
  documentation is not produced here.

## Verification and review gate

Run the small probes and appropriate existing compiler/generic regressions. Review must independently verify a viable
source-filter phase, no activation, generic variable separation, and deterministic cycle failure.
No unexplained sequencing question may be handed to M04 as an assumed fact. If infeasible, revise the design here
while preserving user requirements; do not silently downgrade source filters to metadata predicates.

Deliver `01-handoff.md` with chosen API, phase diagram/description, probe results, and exact next-step interfaces.
Review in `01-review.md`. Do not start M02 before acceptance.
