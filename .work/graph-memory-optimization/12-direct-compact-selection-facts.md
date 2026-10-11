# 12 — Construct compact selection facts directly

Created: 2026-10-10\
Status: Complete — scoped direct capture retained for CPU/churn; rich payload sharing deferred\
Assignment: `/root/graph_memory_task_12`, high reasoning, sequential workstream\
Recommended reasoning effort: High (`high`)\
Priority: Allocation churn and build time\
Prerequisites: Task 06 fact-interning evidence; 10–11 for mode integration

## Outcome

Capture the minimum immutable selection facts at the original decision point,
without first constructing a rich object and then normalizing or discarding it.
Analysis mode can retain detailed history; run mode captures exactly the evidence
required by task 11. Shared facts may benefit both modes.

## Work

- Trace candidate decisions, template facts, explanation patterns and occurrence
  remapping through decorator compilation, template expansion and failure paths.
- Split shared facts from occurrence context. Use compiler-local interning with
  identity-safe keys; preserve target IDs, boundary, generic bindings, selectors,
  order, outcomes, required rejection reasons and actual callback results.
- Check for a shared fact before constructing its public diagnostic object.
  Avoid allocating formatted descriptions and argument tuples for an evidence
  sink that will discard them. A no-op sink fed eagerly allocated objects is not
  allocation avoidance.
- Preserve mandatory build-rule access through compact facts or bounded public
  views, and capture rich analysis evidence without rerunning callbacks.
- Avoid global caches and accidental retention of application values. Include
  interning keys, normalization temporaries and pool lifetime in measurements.

## Starting evidence

The current eight-route census creates approximately 1.13 million candidate
decisions and 1.13 million template facts. [Task 06](06-result.md) reduced template
facts to 570 and candidate decisions to 565,278 in an isolated probe. Build time
improved about 41%; traced peak did not improve. These are historical probe
results, not a production claim or acceptance target.

The same task's coarse evidence-omission probe is rejected. Do not revive it as
an optimization justified only by the new mode name.

## Acceptance and deliverables

- Source-integrated design without the earlier probe's AST/temporary-field hacks.
- Constructor counts plus simultaneously live facts and pool entries, separately
  from timing, RSS and traced peak; include diagnostics-heavy analysis controls.
- Full analysis facts and failures match the contract. Run preserves selected
  outcomes, build-rule evidence and actionable failures without callback replay.
- Template directions, decorator positions, generic targets, boundaries,
  callback failures and repeated inspection are covered.
- Report a CPU/churn benefit honestly if peak memory remains unchanged; measure
  deferred view construction and repeated-access retention where introduced.

Readiness gate: task 11 identifies required evidence and task 10 fixes mode
selection. Initial investigation can refine the existing probe independently.

## Result

Root review accepted the scoped implementation. The [result](12-result.md) and
[inventory](12-inventory.md) record 47.8% lower no-rule build time, a 0.300 MiB
traced-peak increase, unchanged rich history, 2,247 passing tests and the task 13
handoff. This is not a memory-reduction claim.
