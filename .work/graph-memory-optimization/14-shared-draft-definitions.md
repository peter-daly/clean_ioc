# 14 — Share component definitions in mutable drafts

Created: 2026-10-10\
Status: Complete — scoped KEEP accepted after coordinating review; [result](14-result.md), [inventory](14-inventory.md)\
Assignment: `/root/graph_memory_task_14`, high reasoning, sequential workstream\
Recommended reasoning effort: High (`high`)\
Priority: Peak compiler memory\
Prerequisites: Tasks 02 and 07; 10–11 for publication/evidence contracts

## Outcome

Move immutable definition sharing earlier into mutable compilation. Preserve each
contextual occurrence while avoiding repeated type, implementation, name, tags,
lifespan and other definition fields in every draft.

## Work

- Use task 07's mutation inventory to separate immutable shared definition facts
  from per-occurrence parent, argument, dependency, decorator and ownership state.
- Prototype copy-on-write definition replacement for source enrichment, boundary
  exposure, preference previews, alias/generic changes and cache-root rebinding.
  Changing one occurrence must never alter another occurrence's definition.
- Preserve reference identity without application-defined equality or hashing.
  Keep occurrence-specific generic caches out of shared definitions.
- Design pool/key ownership and disposal. A strong intern pool must not retain
  overwritten opaque facts forever or survive through an escaped graph accidentally.
- Keep existing freeze, clone, dataclass/introspection consumers and callback
  snapshots correct, or document a deliberate private representation adapter.
- Apply to both modes where valid; run still needs all draft facts required by
  callbacks and mandatory checks until their last consumer.

## Starting evidence

The eight-route build has 88,558 primary drafts and 116 shared definitions in its
finished graph. [Task 07](07-inventory.md) found the repeated draft fields and
tested only bounded packing/copy-on-write examples. This is not an integrated
memory result, and 116 definitions is fixture-specific.

## Acceptance and deliverables

- Field/mutation/owner inventory and an implementable pool lifetime policy.
- Tests for mutation and restoration, distinct context/identity, aliases,
  generics, boundary visibility, saved callback views and failed builds.
- Repeated memory/timing measurements including pool keys, temporary tuples,
  replacement definitions and freeze overlap. Use a higher-definition-diversity
  fixture as a control; do not infer savings by field-count arithmetic alone.
- No unintended instance sharing, changed selection or generic bindings, or
  additional runtime traversal. Report actual live peak and retained output.

Readiness gate resolved under the authorized sequential execution: every definition
mutation uses occurrence-local replacement; weak pooling releases overwritten facts
without extending opaque-value ownership. Scoped implementation is retained for
coordinating review, with measured repeated-definition gains and unique-definition
regressions recorded in the result. No commit or release is included.
