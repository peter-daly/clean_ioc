# Task 19 — Contract design result

Date: 2026-10-10\
Status: Complete — design reviewed; builder/composition recommendations accepted\
Assignment: `/root/graph_memory_task_19`, high reasoning\
Decision: Use the reviewed [contract](19-contract.md) and
[source/check inventory](19-inventory.md) for follow-on planning; implementation has not started.

## Reviewed design

The settled direction is `build()` for execution with no validation and `analyse()`
for complete supported analysis, with one `add_validation_rule(rule)` API. The
reviewed details now make that direction implementable:

- Root/scope builds return ordinary `Container`/`Scope`; analyses return a distinct
  `AnalysisResult` with a completed `AnalysisReport`, coverage/rule outcomes,
  complete or partial graph evidence, and explicitly created test runtimes.
  Report reads execute no callbacks. Invalid/incomplete results do not require a
  second `validation_report()` call or a thrown build exception to inspect them.
- Every applicable rule on a complete graph runs once per declaration/context,
  including inherited and boundary declarations, despite prior policy findings.
  Rule failure preserves earlier findings and continues other rules. Incomplete
  graph contexts make full-graph rules explicitly unavailable rather than passed.
- Builders are consumed by one admitted operation, including compilation failure,
  invalid analysis or budget interruption; only pre-admission input errors leave
  them mutable. Production and analysis normally use fresh composition factories.
- An explicit external `Composition` handle, requested before compilation through
  `retain_composition()`, supports `ScopeBuilder(parent, composition=...)`.
  Analysis owns one in its result. Ordinary runtimes retain execution identity and
  actual parent anchors, not a blueprint merely to support future overrides.
  Composition uses ordinary reference ownership, has structurally immutable
  declarations and no separate close/context-management or resource-cleanup API.
- Keep selection, generic dependency binding, provider/map targets, cache/cleanup
  placement, slots, discovery and normal runtime guards. Move annotation proofs,
  captive and architecture checks, complete entrypoint audits and custom rules
  into analysis, including eager declaration checks that currently enforce policy.
- Budgets remain operational admission limits. Compilation profiling cannot turn
  build into analysis. Warmup and runtime observation use compact execution IDs,
  replacing their hidden dependence on manifests and inspection indexes.

The separate-result design is preferred to a rich runtime because it represents
partial/invalid analysis directly and makes evidence/source/activation ownership
explicit. `create_runtime()` is allowed when the primary execution projection is
complete, including a policy-invalid result, and performs no compilation or
application activation itself. Root test runtimes receive fresh runtime caches;
scope test runtimes intentionally borrow their declared parent's existing anchors.

## Source findings that materially constrain implementation

The compiler does more checking than a final rule runner. Registration currently
rejects service-group incompatibility and some per-call policies; boundary
preparation mixes alias binding with architecture checks; generic specialization
mixes needed dependency inference with return-type proof; per-call construction
mixes forwarding shape with implementation conformance. The inventory classifies
these individual operations rather than retaining entire helpers as mandatory.

Concrete deliberately invalid but emittable examples include captive scoped
dependencies, definite factory-result mismatch, a configured keyword absent from
the callable, sync providers of async targets, per-call implementation method
mismatch, and a uniquely bound non-singleton warmup target. Analyse rejects them;
build preserves their declared instruction behavior. Genuine missing targets,
ambiguous injected scalar providers, unresolved required TypeVars, unsupported
eager recursion and impossible owner anchors still fail locally. The contract
does not invent missing targets, collision winners, new lifetimes or missing cleanup.

Warmups currently use `CompiledGraph._component_paths()` and `graph.manifest()`;
observation uses the graph manifest, `graph_index()` and `sharing_report()`.
Tasks 21 and 23 must change these together. Registering no validators does not
make arbitrary selection/template Components, detached callback snapshots,
opaque value owners, provider projection parents or task 17's disposal-order
counterexample disappear. Task 22 needs an actual last-reader proof per owner.

## Review decisions and readiness

The two operations/no-build-validation/single-rule-category decisions were already
settled by the maintainer. On 2026-10-10 the coordinating review recommended
single-attempt builders and explicit external composition ownership, with a
simpler composition lifecycle. The maintainer accepted those recommendations.

An admitted compilation consumes its builder even on failure. This intentionally
removes repair-and-retry on the same builder; pre-admission input errors do not
consume it. Fresh composition factories serve production and analysis, while
`AnalysisResult.create_runtime()` supports testing the already analysed plan
without another compilation. Implementation must actually release declaration
references at proven last use; changing the state flag alone saves no memory.

Optional external composition preserves production overlays without source data
on every runtime or a mandatory analysis prerequisite. Ordinary `new_scope()`
requires no handle. Composition must match the live parent and retain structurally
immutable declarations; opaque application objects retain their identity. Unlike
the initial agent proposal, the reviewed contract has no composition `close()`,
`aclose()` or context-manager lifecycle. Releasing references allows otherwise
unowned source data to be collected and does not invalidate emitted children.
Analysis-result cleanup still closes its owned test runtimes, not the handle.

A small handle can retain substantial declaration data. Moving ownership outside
the runtime saves no process memory while that data is still held. Tasks 22/25
must compare unrequested, held and released composition, retained consumed
builders and declaration/transfer/freeze overlap. No savings have been measured.

Design review is complete. Task 20 is ready for assignment, with task 25 baseline
capture required before compiler changes. Tasks 21–23 have named execution,
evidence and ownership contracts but still depend on their coordinated
implementation prerequisites. Task 24 waits for 20–23. Task 25's baseline
investigation remains ready/unassigned. No follow-on task was started or agent
assigned, and accepting these planning decisions does not start implementation.

## Evidence boundary

Read the actual [Bark/Cop handover](/Users/peter.daly/WS/bark/bark-core/docs/evidence/clean-ioc-run-analysis-verification-20261010/README.md)
without editing it. The current compiler hash is
`1a60386b392058ac47143b3acf4fc82b1034b95f360854dae2e98ff6cde42223`; the earlier
consumer compiler is `6253f5e38bd8819099db53514ede0d3c0efc4f451b3ea33f05c6e4a9932e4253`.
The worker's recorded native build 3.306→4.756 seconds, peak RSS
214.938→277.891 MiB and traced peak 46.566→98.799 MiB regress despite retained
traced allocations falling 30.273→19.207 MiB. The automatic rich path for build
rules is a source-backed lead, not isolated attribution or a measured saving.
Task 18's baseline begins after the task 10/11 policy and does not measure its
whole-upgrade cost. Existing evidence and historical README outcomes stay intact.

## Changed planning files and verification

Created:

- [19-contract.md](19-contract.md)
- [19-inventory.md](19-inventory.md)
- [19-result.md](19-result.md)

Updated narrowly:

- [19-build-and-analyse-contract.md](19-build-and-analyse-contract.md)
- [20-analysis-validation-pipeline.md](20-analysis-validation-pipeline.md)
- [21-execution-only-plan-finalization.md](21-execution-only-plan-finalization.md)
- [22-execution-only-evidence-capture.md](22-execution-only-evidence-capture.md)
- [23-runtime-features-without-analysis-graphs.md](23-runtime-features-without-analysis-graphs.md)
- [24-build-analyse-tools-and-consumers.md](24-build-analyse-tools-and-consumers.md)
- [25-build-analyse-consumer-memory-acceptance.md](25-build-analyse-consumer-memory-acceptance.md)
- [Folder index](README.md), [work index](../README.md) and
  [investigation status](build-and-analyse-investigation.md)

Verified local Markdown link destinations, source hash, planning whitespace and
consistency of the operation/report/lifecycle/removal recommendations. The
coordinating review updated the lifecycle contract, dependent task acceptance
criteria and status indexes after the maintainer accepted its recommendations. No runtime,
test, consumer, historical evidence or benchmark files were edited. No tests or
benchmarks were run for this planning-only change. No commit, version bump, push,
release, deployment, pre-compilation work or external message was made.

The assigned agent's work is complete; these subsequent review updates are planning only.
