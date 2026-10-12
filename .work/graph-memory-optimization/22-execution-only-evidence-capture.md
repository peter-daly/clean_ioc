# 22 — Avoid analysis evidence allocation during build

Created: 2026-10-10\
Status: Complete — scoped implementation review accepted; [result](22-result.md)\
Assignment: `/root/graph_memory_task_22`, extra-high reasoning\
Recommended reasoning effort: Extra high (`xhigh`)\
Prerequisites: 19–21; tasks 06, 11–17 reader and lifetime findings

Use the reviewed [19-inventory](19-inventory.md) and
[ownership contract](19-contract.md). Task 19 design review is complete;
the maintainer has authorized sequential tasks 21–24. Task 21's core review is
complete; task 22's scoped implementation review is accepted. Task 23 will complete the remaining feature
integration gate. No commit, push, release or deployment is included.

Measurement scheduling: defer memory/timing benchmarks and performance population
studies to task 25 after tasks 20–24 are integrated. Continue source reader audits,
correctness/ownership checks and focused assertions of absent forbidden allocation
here; preserve instrumentation and source identity for final measurement.

## Outcome

Stop creating analysis-only data throughout registration, preparation and compilation,
rather than relying on reduced retention after the peak. The new no-validation
contract removes previous rule/report readers but not wiring callbacks.

## Work

- Inventory per-field readers for candidate/rejection histories, decorator/template
  decisions, origins/source locations, census records, generic/parameter explanation
  labels, partial attempts, entrypoint evidence and boundary report descriptions.
  Include builder declarations and source-inspection subcompilers, not just the
  primary compiler's final result.
- Classify compact facts needed for selection/activation separately from analysis
  presentation. Template source predicates, registration/decorator conditions,
  positions, preferences and `derive()` still define the graph.
- Build must not format or allocate histories used only by validation/reporting.
  Analyse retains complete evidence. Share semantic calculations where possible
  without creating rich objects just to adapt them into smaller ones.
- Evaluate whether origins/decorator compact indexes from task 15 become unnecessary
  on the execution path. Remove a table only when its remaining readers are replaced
  or absent; do not stack a new compression experiment on an unused structure.
- Revisit draft/definition/cache lifetimes now that whole-graph validation has no
  build-time ownership. Use actual last readers, including source snapshots and
  caller-retained Components. Preserve opaque value identity and disposal order.
- Maintain ancestry/sibling/decorator relationships needed by wiring or runtime
  filters. No broad subtree merging or retention deletion based only on reachability
  from public roots; private/deferred execution and callback-held owners matter.
- Analyse must still capture original decisions; never recover them by replaying
  selection callbacks on demand. Independent analyse/build invocations are separate
  compositions and can legitimately execute those callbacks once in each.

## Acceptance

- Separate counts for constructed, simultaneous live and runtime-retained objects,
  plus caller-owned snapshots. Prove absent allocation, not only empty final fields.
- Count explicit composition handles, consumed builders, analysis results, runtime
  internal Component graphs and callback/source snapshots separately from forbidden
  library `CompiledGraph`/report/index objects in build. Opaque finalizers and
  graph-qualified parent/provider/owner references still have real last readers.
- Compare composition unrequested, explicitly held and released, including a
  still-referenced consumed builder and boundary handles. The composition object
  has no separate close lifecycle; retained source data still counts as process
  memory even when it lives outside the runtime.
- No-rule and rule-registered builds take the same execution capture path. The
  presence of arbitrary or failing rule functions does not enable any evidence.
- Valid selection, snapshot fields, discovery, providers/maps, aliases/generics,
  lifetimes and cleanup stay correct; analysis evidence remains complete.
- Measure rich repeated structure and low-reuse definitions. Do not assume previous
  sharing/index tradeoffs improve this new pipeline; explicitly keep/refine/drop.

Use independent observers for populations and timing. No claimed performance win
until task 25 measures the whole change against the consumer's original baseline.
