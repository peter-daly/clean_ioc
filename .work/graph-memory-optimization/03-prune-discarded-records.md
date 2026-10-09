# 03 — Audit and prune discarded compilation records

Status: Complete — audit retained; production pruning declined\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Priority: Third experiment\
Prerequisite: Establish reachability on the current output representation.

Read the [shared plan](README.md) for measurement and compatibility requirements.

## Outcome

Determine whether records retained solely from discarded compilation candidates
can be released after a successful build. Remove only records proven unnecessary
for execution and supported graph/inspection behaviour.

## Evidence and code to inspect

The baseline has 88,558 physical records and 1,765 distinct execution steps.
This difference is an investigation lead, not a count of removable records:
logical occurrences carry context that shared steps do not.

Start with `_PlanSet`, root/candidate selection, clone paths and graph finalization
in [container.py](../../clean_ioc/container.py), graph/view references in
[components.py](../../clean_ioc/components.py), and retained graph/report evidence
in [tooling.py](../../clean_ioc/tooling.py). Earlier early-rejection work already
avoids some candidate allocations; focus on remaining retained records.

## Work

1. Add an audit classifying records reachable from public roots, provider and
   managed-provider roots, map targets, warm-up/architecture roots, executable
   steps, parent/owner relationships, view sources and diagnostic evidence.
2. Distinguish public logical occurrences, internal activation targets, rejected
   evidence and truly unreferenced/intermediate records. Account for root filters
   that traverse component metadata and anchored parent/overlay graphs.
3. Quantify each category and document a precise removal boundary. Establish
   separate requirements for successful builds, full diagnostics and partial
   graphs retained after failures.
4. If justified, prune at a defined finalization stage after required validation.
   Update all affected indexes and sidecars consistently; preserve externally
   retained component views and all supported inspection facts.
5. Measure the pass's own peak/time cost and the net retained-memory reduction.
   If no safely removable set exists, retain the audit and record that conclusion.

## Acceptance criteria

- [x] The audit explains every retained record category; no saving is inferred
  merely from the physical-record/execution-step ratio.
- [x] All remaining references resolve, including negative provider-view IDs,
  parent/decorated/owner links and inherited graph references.
- [x] Public selection, filters, traversal, ownership, explanations, census,
  manifests, fingerprints and profiler attribution remain equivalent.
- [x] Diagnostic and failed-build evidence remains truthful and available under
  its existing contract; discarded callbacks are never rerun to recreate facts.
- [x] Relevant behaviour tests and required checks pass. Repeated measurements
  record both retained savings and the cost of pruning, or justify no change.
- [x] Record the implementation or declined-experiment decision and update status.

## Recorded outcome

The [result](03-result.md) classifies all 88,558 eight-route records and records
a concrete escaped-callback counterexample to pruning from runtime roots alone.
The conservative removable set is empty; no compiler/runtime pruning was added.
Fresh before/unchanged-after measurements, diagnostics and inherited/contextual
link validation, public inspection and required checks are complete. Task 04
remains planned.
