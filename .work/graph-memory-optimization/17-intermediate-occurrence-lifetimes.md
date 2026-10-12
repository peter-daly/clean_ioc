# 17 — Release completed intermediate occurrences earlier

Created: 2026-10-10\
Status: Complete — scoped retained-draft transfer KEEP accepted; broader reclamation DROP / DEFER\
Assignment: `/root/graph_memory_task_17`, extra-high reasoning, sequential workstream\
Recommended reasoning effort: Extra high (`xhigh`)\
Priority: Longer-term architectural investigation\
Prerequisites: 10–11; ownership findings from 13 and representation findings from 14–16

## Outcome

Reduce the number of contextual occurrences simultaneously retained during a run
build. Finish a candidate/subtree, preserve its required execution and validation
facts, and release obsolete intermediate state before the entire build finishes.

## Required investigation

- Produce a last-consumer map for draft records, rejected candidates, decorator
  selection, owner links, source graphs, cache entries, error witnesses and
  caller-held Components. Distinguish selected, rejected and not-yet-decided data.
- Identify which mandatory checks can consume facts incrementally and which need
  a complete topology. Preserve their coverage and error reporting; do not reduce
  graph-wide validation merely to make streaming reclamation possible.
- Design explicit ownership/liveness accounting and graph-qualified handles.
  References needed by another candidate, a managed target, validation callback,
  anchored parent, or escaped view must remain valid.
- Compare releasing only compiler ownership with compacting necessary facts into
  a smaller intermediate representation. Keep failure evidence captured at the
  original decision and never reconstruct it by callbacks or a hidden rebuild.
- Analysis retains its complete supported evidence. Both modes preserve selection
  and lifetime semantics even when their physical retained graph sizes differ.

## Known boundaries

[Task 03](03-result.md) could not prune records while retaining every inspection
contract; [task 04](04-rollback.md) was reverted after RSS increased. Task 05
successfully reduces runtime closure after validation, but that does not prove
the same records can be dropped during compilation.

The eight-route run still reaches 88,558 primary drafts before retaining 8,982
records. Task 06 found repeated contextual compilation to be the draft multiplier
in this fixture, with primary clone calls absent. Do not assume subtree-copy
elimination or merging identical registration IDs solves that population.

## Acceptance and deliverables

- A reader/last-consumer proof for one bounded reclamation opportunity before any
  general streaming compiler proposal. Explain cases that must retain full state.
- Tests exercise late graph-wide rules, alternative branches, contextual filters,
  templates, boundaries, overlays, managed providers, failure paths and captures.
- No weakened safety checks, missing deferred targets, changed transient sharing,
  callback replay, dangling views or different derived-value lifetimes.
- Measure simultaneous live drafts/records and phase peaks, not only final size
  or cumulative allocations. Include bookkeeping and any deferred materialization.

Readiness gate: tasks 10–11 define available views and validation consumers, and
the first safe last-use boundary is demonstrated. It is valid to conclude that
the existing callback contract prevents a worthwhile implementation.
