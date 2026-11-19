# M01 independent technical review

Reviewer: `/root/m01_review`, `gpt-6-astra`, high reasoning, fresh context.
Implementation agent is separate: `/root/m01_implementation`.

## Round 1 — request changes

Reviewed checkpoint: `ae33390c8e255a2a0c386cfc36bae42e2de0af6c` against search checkpoint
`da20679d89cf0779c8c30365196375901f62e8b5`. Reviewer made no file edits or commits.

1. **P2 — anchored canonical source argument.** `_compile_source_core` restores definition-side metadata but retains
   the anchored occurrence's consumer argument. Registering Consumer(source: Source) before singleton Source makes
   inspection report parent=None, argument="source" instead of canonical argument=None. Reset the root argument only;
   prove descendant arguments and parent-owned activation remain intact.
2. **P2 — target filter view.** Normal target `when` receives a core whose dependency descendants can still include
   their own decorator branches. A marker added only by a dependency decorator can enable a target predicate. The
   template contract requires recursive exclusion. Prove an internal disposable generated-template target-filter view
   retaining target occurrence context and selected dependencies, and hand its interface to M05. Do not change existing
   ordinary decorator behaviour as part of this fix.

Reviewer verification: 92 focused tests passed; independent PEP 695 nested projection passed; anchored boundary-alias
service/name/tag restoration passed. Existing source suppression, no-activation, exact binding, cycles and boundary
consistency probes were supported. The implementation-verification gate is reopened for these corrections.

## Round 2

**Accepted** at `2179fa6fc5660cd4f960a7fc89258bde3de9136a` by the same independent Astra High reviewer.

Both findings are resolved. Canonical source root argument is cleared while descendant arguments and anchored
ownership remain intact. `_undecorated_component_view` provides a separate recursive snapshot retaining occurrence
and parent context; ordinary decorator behaviour is unchanged. The handoff and M05 contract describe the seam accurately.

Independent verification: **14 feasibility tests passed**, including draft/frozen snapshots, nested decorator exclusion,
non-root context, and anchored source metadata. No remaining blocking findings. Whole-graph snapshot cost is explicitly
retained as an M05 implementation concern. Reviewer made no file edits or commits. Acceptance covers M01 only.
