# 15 — Compact temporary indexes and relationship tables

Created: 2026-10-10\
Status: Complete — scoped index KEEP accepted; wider tables DROP / DEFER after root review\
Assignment: `/root/graph_memory_task_15`, high reasoning, sequential workstream\
Recommended reasoning effort: High (`high`)\
Priority: Peak compiler memory; analysis retention\
Prerequisites: Task 09 corrected prototype; 10–11 contracts; coordinate with 14

## Recorded result

[Result](15-result.md) and [inventory](15-inventory.md): retain bounded origin/decorator
indexes, decline relationship tuple interning and defer wider packed rows/ranges.
Large compiler peak falls about 4.96 MiB with 3.2–3.4% build cost. Cold/steady
resolution timing remains an explicit task 18 check despite zero index accesses
during the measured workloads. All CI/docs and supported-Python checks pass.

## Outcome

Reduce the storage surrounding occurrences: origin/decorator indexes, repeated
references, relationship tuples and potentially compact occurrence rows. Preserve
the logical graph and the public Component views required by either mode.

## Work in separately measured stages

1. Review task 09's corrected native-delegation/sparse-fallback index candidate
   for current-source integration. Reuse its differential cases and codec checks;
   do not restart with task 08's known-incompatible mapping adapter.
2. Inventory relationship tuple lengths, duplication, reference lifetimes and
   mutable append/update patterns. Compare shared immutable sequences, indexed
   ranges or compact rows only where their actual readers support them.
3. Consider occurrence-to-definition references alongside task 14. Keep topology
   fields and graph-qualified occurrence identities explicit; never renumber
   public identities or merge distinct parent/owner contexts accidentally.

Account for tiny, sparse, negative, gapped and reverse-inserted IDs, overlays,
provider views, failures, promotion peaks and caller-held mapping views. Preserve
key/value identity, dictionary hash/equality behaviour, order, iterator invalidation
and backing sharing wherever existing consumers depend on them. Compact storage
must not allocate arrays proportional to arbitrarily large sparse IDs.

## Starting evidence

[Task 09](09-result.md) has a corrected isolated candidate and roughly 4.96 MiB
traced savings. Dense lookup remains slower than native dictionaries and full
artifact export/load medians rose about 13%; these costs remain relevant.
Production adoption was not approved by that investigation.

The current rich fixture retains about 45,000 relationship tuples with metadata,
and about 4,800 after reduction. Sharing already-shared values does not save them
again: 88,558 origin entries refer to only 45 distinct origin objects.

## Acceptance and deliverables

- Separate index-adoption and wider-table recommendations; each can be declined
  without blocking the other. Document all representation consumer contracts.
- All six hash counterexamples and the full native-operation differential audit
  remain passing; public graph/evidence and failed-build semantics remain correct.
- Measure actual backing capacities, conversion overlap, per-operation costs,
  build/resolve time and both modes. Never count borrowed referents twice.
- Preserve existing experimental artifact sharing and supported round trips where
  touched, without promoting that experiment into a production persistence API.
- No new graph traversal during ordinary resolution and no reconstruction by
  callback replay. Include inspection costs for analysis and temporary rule views.

Readiness gate resolved: scoped index tradeoff recommended KEEP with costs recorded;
relationship interning dropped and broader rows/ranges deferred for lack of a
measured benefit that justifies their reader/mutation design. Root review precedes task 16.
