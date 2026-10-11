# 16 — Reduce callback snapshot copying

Created: 2026-10-10\
Status: Complete — scoped direct-freeze KEEP for CPU/churn; broader sharing DROP; accepted after root review\
Assignment: `/root/graph_memory_task_16`, high reasoning, sequential workstream\
Recommended reasoning effort: High (`high`)\
Priority: Lower; allocation churn with unproven peak benefit\
Prerequisites: Task 06 snapshot results; 11 callback contracts; coordinate with 14–15

## Outcome

Avoid redundant frozen-record and definition copies while preserving stable,
detached views presented to decorator/template callbacks and position previews.

## Work

- Inventory source snapshots, undecorated target snapshots, preview records and
  escape paths. Distinguish snapshots owned by the compiler from views retained
  by application callbacks; those have different release obligations.
- Test reuse of already-immutable records when the requested transformation
  changes nothing. Compare persistent/copy-on-write snapshots that copy only
  modified portions, preserving snapshot state after later compilation changes.
- Preserve ancestors, dependencies, owners, boundaries and the intentionally
  hidden decorator pipeline. Do not replace detached snapshots with live views
  into mutable drafts or reclaim caller-held views prematurely.
- Coordinate definition sharing with task 14 without retaining whole obsolete
  graphs via shared back references. Account for memo/index overhead and chains
  of persistent snapshots, including long-lived callback captures.
- Keep the same callback count/order and observed fields in both modes. Analysis
  may retain more evidence; run still honours promised callback view semantics.

## Starting evidence

The current build constructs about 194,000 frozen records in reduced mode and
274,000 with metadata, including temporary snapshot copies. These totals are not
simultaneously live records or automatically recoverable peak memory.
[Task 06](06-result.md) found no established peak benefit from simple snapshot
record reuse; snapshot definition interning increased peak in its screen. Source
graphs were not the dominant peak in that workload. Preserve those results.

## Acceptance and deliverables

- Snapshot lifetime/read contract and a retain/refine/drop recommendation.
- Tests for escaped views inspected during and after build, callback exceptions,
  failed builders, position previews, boundary/overlay parents and generic types.
- Separate counts for created/live snapshots and copied records, plus peak and
  retained memory, build time and later inspection costs. Report a churn-only
  result as such rather than claiming a peak reduction.
- Demonstrate no retained-history chain or new allocation burst after build that
  outweighs the saved copies. Do not resurrect task 04's reverted contextual
  subtree-sharing implementation under a different name.

Readiness gate: stable escaped-view semantics and bounded sharing ownership are
specified; proceed only if fresh evidence justifies this lower-priority change.

## Recorded outcome

See [result](16-result.md) and [ownership inventory](16-inventory.md). Direct draft
snapshot freezing avoids 91,816 record constructors in the large controls with
unchanged peak-live/retained counts and effectively flat traced peak. Measured
build medians improve 5–7%; rich-run resolution +2.01% remains explicit for task 18.
All 2,401 tests/full CI, strict docs and supported-interpreter focused checks pass.
No persistent snapshot structure or task 17 lifetime change was adopted.
