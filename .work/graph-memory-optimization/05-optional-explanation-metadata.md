# 05 — Make explanation metadata optional and minimize the runtime container

Created: 2026-10-09\
Status: Complete — retained on 2026-10-09\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), high reasoning\
Priority: Next memory optimization\
Prerequisite: Tasks 01 and 02 retained; use task 03's audit and task 04's rollback baseline.

## Outcome

Add an `explain_metadata` boolean option to the build process. When it is off,
retain only what is necessary for resolution and explicitly enabled runtime
capabilities. Remove explanation-only metadata and graph records that become
unnecessary, rather than merely hiding the explanation APIs.

The maintainer requested this task after task 03 found that preserving all
existing inspection behaviour prevented conservative pruning. This task
intentionally permits reduced inspection when `explain_metadata=False`.
The shared plan's inspection, explanation and manifest compatibility rules
continue to apply when the option is on; they must not prevent removal when it
is off. Resolution semantics remain protected in both modes.

## Build contract

Implemented; see the [result and evidence](05-result.md):

```python
container = builder.build(
    explain_metadata=False,
    allow_scope_builders=False,
)
```

- Add `explain_metadata: bool = True` to `ContainerBuilder.build()` and
  `ScopeBuilder.build()`. The default preserves existing behaviour;
  passing `False` explicitly selects reduced metadata retention. Validate the
  argument and propagate it through compilation, finalization and descendants.
- `False` must release unnecessary metadata after a successful build. Avoid
  capturing explanation-only data in the first place where it is safe to do so.
  Do not replace eager storage with a cache that recreates it after resolution.
- Keep `diagnostics` distinct: it controls build diagnostic capture, while
  `explain_metadata` controls what the successful runtime retains. Define and
  test all four combinations. In particular, `diagnostics=True` must not silently
  defeat `explain_metadata=False` on a successful build. Preserve truthful
  failure evidence according to the requested diagnostics setting.
- Keep `allow_scope_builders` independent. The example disables future overlay
  compilation as well as explanation retention. With scope builders enabled,
  retain only the composition and parent context necessary for that capability;
  quantify this extra cost. Do not silently disable scope builders.
- Explanation/report APIs that require removed data must report that the
  capability is disabled. Do not return a misleading empty explanation, pretend
  that a reduced graph is a complete inspection graph, rerun callbacks, or
  recompile to reconstruct missing information.

## Evidence and starting points

The [task 03 report](03-result.md) classified 88,558 physical records: 8,932 in
public relationship closure, 50 additional runtime/provider records, and 79,576
additional records under conservatively protected explanation-owner closures.
These are component records, not counts of explanation objects or proven waste.
The 1,765 execution steps are also not a target record count.

Task 03's forwarding-predicate experiment retained 20 callback component views
at two routes, reaching 600 primary records outside runtime-root closure and two
additional inspection graphs. Its compatibility boundary must be reconsidered
explicitly for the new opt-out mode, rather than used to preserve the entire
old graph by default.

Inspect `_PlanSet`, `_GraphExplanationSidecars`, both builders, finalization,
root selection and runtime steps in [container.py](../../clean_ioc/container.py);
record/view ownership in [components.py](../../clean_ioc/components.py); and
explanations, reports and inspection caches in [tooling.py](../../clean_ioc/tooling.py).
Extend the [reachability audit](../../benchmarks/graph_reachability_audit.py) and
use the [rich fixture](../../benchmarks/graph_memory_fixture.py) and
[measurement runner](../../benchmarks/graph_memory_evidence.py).

## Work

1. Inventory everything retained from the built container. For each field,
   index, sidecar and graph category, identify its actual readers and classify
   it as required for ordinary resolution, required for an enabled optional
   capability, needed only during compilation, or explanation/inspection only.
   Include origins, candidates, template facts, parameter/generic explanations,
   build reports, validation rules, graph caches, registrations, blueprints and
   references to inherited/source graphs. Record ownership and measured sizes;
   do not infer removability from a field name.
2. Establish the minimum runtime closure from all execution paths. Include
   default and filtered roots, `has_component`, collections, sync/async and
   managed providers, maps, decorators, pre-configurations, lifetimes, cache
   ownership, cleanup, slots/provisions and warmups. Runtime filters receive
   Components and may traverse relationships: that data is a runtime requirement
   while those filters are supported. Preserve error behaviour as well as
   successful activation. Verify aliases, generics and boundaries separately.
3. Specify the reduced-mode capability boundary for graph access, traversal,
   explanations, manifests, census, architecture/validation reports, build
   variants and profiling. Full-mode behaviour must remain compatible. In
   reduced mode, retain only the data each enabled capability demonstrably needs;
   explicitly reject unsupported combinations rather than secretly keeping the
   complete graph. Run essential build validation before discarding its inputs.
   Address deferred `check_unreachable=False` validation explicitly.
4. Resolve callback escape semantics. Selection callbacks must see valid
   Components while running. Define what applications may inspect on saved
   build-time views after a reduced-mode build; an explicitly documented limit
   is allowed in this mode. Compare detaching views, minimal snapshots or clear
   invalidation against their memory cost. Never leave dangling references,
   mutate an ancestor's shared graph, or silently break Components needed by
   runtime filters. Measure application-owned retained views separately from
   memory kept alive by the container alone.
5. Implement flag propagation and conditional capture/finalization. Remove
   unnecessary sidecars and record/index entries together, after all required
   validation, warmup planning and failure-evidence boundaries. Audit indirect
   references through execution steps, reports, closures, caches and builders
   so released metadata is actually collectible. Keep ordinary resolution free
   of new whole-graph traversal or compilation work.
6. Cover ordinary scopes and overlays, including enabled/disabled metadata on
   parent and child plans, inherited execution and owner relationships, and
   instrumentation inheritance. A child must not claim to recover explanation
   facts its parent discarded. Preserve normal scopes and managed acquisitions.
7. Document the option, capability limits and examples. Account for the private
   schema-5 artifact experiment so reduced graphs are either supported and
   tested or explicitly rejected by that experiment. Do not expand this task
   into a production artifact format or revive task 04.

## Measurement and verification

- Preserve previous evidence. Capture a fresh baseline from the task 04 rollback
  state, recording revision, local changes, Python, architecture and build flags.
- Compare identical rich eight-route workloads with `explain_metadata=True`
  and `False`, initially with diagnostics and scope builders disabled. Separately
  measure the effect of retaining scope-builder composition and test all
  diagnostics combinations. Do not confound flag effects with workload changes.
- Follow the shared plan: at least three serial fresh normal processes and three
  separately traced processes per memory comparison, with no concurrent tests
  or benchmarks. Report collected Python retention, allocation peak, current and
  peak RSS, build time, resolution time and retained record/sidecar counts.
- Measure the container retained alone after releasing build-only references,
  and a case where application code keeps its builder or callback views. State
  these ownership conditions clearly; the flag cannot reclaim caller-owned data.
- Measure immediately after build and after the full resolution workload.
  Do not invoke inspection or census before runtime measurements. Check that
  disabled inspection calls neither reconstruct metadata nor retain new caches.
- Reuse behavioural checks for selected implementations, callback counts,
  provider/map targets, instance identity, lifetime and cleanup. The full-mode
  manifest fingerprint remains comparable; a disabled full-graph manifest is
  not a reason to skip independent resolution-equivalence checks.
- Add focused tests for the new mode, flag combinations, errors and escaped
  views. Run the repository's required checks and record existing limitations.
  Report RSS independently from Python allocation savings: task 04 was reverted
  because lower traced retention did not translate into lower process memory.

## Acceptance criteria

- [x] A source-backed inventory explains what survives and why it is necessary
  for resolution or a specifically enabled capability.
- [x] Both build entry points accept the flag; its default, propagation and
  interaction with diagnostics, overlays and scope builders are documented.
- [x] Off mode actually omits/releases explanation-only data and prunes records
  proven unnecessary under the newly documented capability boundary.
- [x] Resolution, selection, identity, ownership, provisions and cleanup remain
  correct; runtime-required references resolve in ordinary and inherited graphs.
- [x] Full-mode inspection remains compatible; reduced-mode unsupported APIs
  fail clearly, and saved callback views have deliberate, tested semantics.
- [x] Required validation and failed-build diagnostics remain truthful; no
  callback replay or hidden full-graph retention restores disabled features.
- [x] Repeated measurements demonstrate the memory effect and quantify all
  build/runtime/peak tradeoffs, including any remaining memory floor.
- [x] Tests and required checks pass; a result report and evidence are recorded
  and the task index is updated before marking the task complete.
