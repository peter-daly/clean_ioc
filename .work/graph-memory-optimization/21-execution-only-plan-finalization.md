# 21 — Emit the execution runtime without analysis finalization

Created: 2026-10-10\
Status: Complete — core and task 23 feature integration reviews accepted\
Assignment: `/root/graph_memory_task_21`, extra-high reasoning\
Recommended reasoning effort: Extra high (`xhigh`)\
Prerequisites: 19 operation contract; 20 check separation

Reviewed contract: [19-contract](19-contract.md), with source classifications in
[19-inventory](19-inventory.md). Task 19 design review is complete;
20's scoped review is accepted. The maintainer has authorized sequential work on
21–24; task 21 is first. Complete and review its implementation before task 22
starts, then revisit the feature integration gate when task 23 completes. No
commit, push, release or deployment is included.

Measurement scheduling: the maintainer has deferred memory/timing benchmarks to
task 25 after tasks 20–24 are integrated. Preserve source identities and complete
correctness/quality checks here; measurement criteria below feed final acceptance
and do not require per-step benchmarking.

## Outcome

Create a direct execution pipeline shared with analysis at the wiring layer.
Successful `build()` must not construct a rich `CompiledGraph`, `BuildReport`,
validation-only root lists or report payloads and then discard them.

## Work

- Separate `_compile_with_report` into shared preparation/wiring and explicit
  execution/analysis orchestration. No blanket exception suppression and no private
  flag combination standing in for a completed architectural split.
- Split `_PlanSet` or its ownership so the runtime result does not carry dormant
  rule callbacks, diagnostic maps, analysis history, inspection caches or a blueprint.
  Empty dicts/tuples in a rich result are not the only design to consider.
- Bypass `_finalize_plan` for execution. Identify root declarations that affect
  provider/public wiring and retain that computation; omit only their audit/report
  work. Boundary visibility is still part of selection, not a global exposure switch.
- Produce the selected-registration catalogue directly from executable roots,
  providers, decorators and warmup targets. Preserve implementation type/identity,
  name/tags and selection semantics without public-root expansion.
- Freeze only required execution records after their actual wiring consumers finish.
  Keep graph-qualified ownership and relationships needed by runtime filters,
  scopes, providers/maps, per-call handles, explicit cleanup and warmup execution.
- Retain a minimal failure path when instructions cannot be emitted. Do not freeze
  an entire discarded graph or create report/census objects just to format that error.
- Keep analysis able to inspect the complete graph. No implicit reconstruction of
  analysis from an execution runtime and no preservation of an old overlay blueprint
  on build output solely for compatibility.

## Acceptance

- Default successful build creates zero library-owned analysis graph/report/index
  objects. Source/component snapshots required by wiring are counted separately.
- Discovery and all valid resolution/lifetime/cleanup tests remain equivalent.
- Ordinary scopes work; unsupported inspection/overlay operations follow task 19.
- Retained owners and temporary freeze overlap are measured separately. Rule
  registration alone changes neither build rule counts nor diagnostic populations.
- Failure and opaque-reference lifetimes are tested; earlier task 17 finalizer
  counterexamples are not assumed obsolete merely because validators moved.
- Apply single-attempt builder consumption and reentrancy to root and scope
  builders, including failed/budget-interrupted operations; only pre-admission
  input errors leave them mutable. Minimal build errors own no analysis report.
- Release consumed-builder declaration references at proven last use, including
  references through retained boundary handles. Preserve explicit composition,
  opaque values and caller-held snapshots. Merely rejecting a second operation
  does not establish a memory reduction; measure transfer/freeze overlap.
- `AnalysisResult.create_runtime()` uses an already emitted execution projection
  without recompilation or callback replay, with independent root runtime state.
  A fully emitted policy-invalid result can create an explicit test runtime;
  partial diagnostic attempts cannot be substituted for a primary execution plan.

Warmups and instrumentation must pass task 23 before this pipeline is accepted.
No pre-compilation/export API is introduced.

Core delivery: [21-result](21-result.md), [ownership inventory](21-inventory.md), and [task-relative patch](evidence/21/task21.patch). Ordinary finalization and projected runtime ownership are implemented and verified; task23 must remove the explicit observer bridge and complete the public composition/feature integration gate.
