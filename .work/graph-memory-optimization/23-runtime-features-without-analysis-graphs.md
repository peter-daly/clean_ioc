# 23 — Decouple warmups, instrumentation and composition ownership

Created: 2026-10-10\
Status: Complete — scoped implementation and task 21 feature gate reviewed; [result](23-result.md)\
Assignment: `/root/graph_memory_task_23`, high reasoning\
Recommended reasoning effort: High (`high`)\
Prerequisites: 19 and 21; coordinate reader changes with 22

Feature decisions are recorded in the reviewed [19-contract](19-contract.md),
with mixed warmup/per-call/provider checks in [19-inventory](19-inventory.md).
Task 19 design review is complete. Sequential work on 21–24 is authorized;
task 22's scoped implementation review and task 23's feature review are accepted.

Measurement scheduling: memory/timing comparisons, including optional observer
and composition costs, are deferred to task 25 after tasks 20–24 are integrated.
Complete functional, ownership and quality checks here without per-step benchmarks.

## Outcome

Execution features must not quietly recreate full inspection metadata. Warmup
planning and runtime instrumentation currently depend on a CompiledGraph and its
manifest/indexes. Overlay composition also needs an explicit owner outside the
minimum runtime.

## Work

- `_compile_warmup_plans`: separate target binding and emitted steps from policy
  validation, diagnostic paths and manifest fingerprinting. Keep explicit startup
  activation and cleanup semantics; do not warm the application during compilation.
- Warmup target ambiguity/missing targets/non-singleton cases follow task 19's
  instruction-versus-policy matrix. Do not retain all current checks merely because
  the helper mixes them with plan construction.
- `_observe_plan_impl`: derive necessary profiling identities, labels and lookup
  tables from execution data. Avoid `graph.manifest()`, `graph_index()` and
  `sharing_report()` on build. Breaking profiling identifier/report changes are
  permitted but must be documented and reflected in downstream tests.
- Compilation profiling observes the chosen operation without enabling validation
  or diagnostic histories. Explicit observer metadata costs are measured separately.
- Implement the chosen overlay/composition owner. An execution runtime retains
  ordinary scopes and slot provisioning; it does not own a composition blueprint
  just to support subsequent registration edits. Analyse/test ownership is explicit.
- Reviewed API: `builder.retain_composition()` requests an external realized
  `Composition` owner before compilation; `ScopeBuilder(parent, composition=...)`
  checks matching owner lineage. Analysis exposes its captured composition through
  the result. Plain build requires neither a handle nor analysis. Remove runtime
  `new_scope_builder()` rather than retaining a hidden blueprint.
- Composition has structurally immutable declarations and ordinary reference
  ownership, with no separate `close()`, `aclose()` or context-manager lifecycle.
  It owns no application-resource cleanup, report or analysis graph. Releasing it
  does not invalidate emitted children; a retained child builder/result owns the
  source facts it still needs. Analysis-result cleanup closes its test runtimes
  without revoking separately retained composition handles.
- Warmup duplicate-target and non-singleton checks are analysis-only when target
  binding is possible. Preserve ordered activations and declared cache/cleanup
  ownership. Replace warmup/observer manifest identity with compact execution-plan,
  step and owner IDs; document the loss of cross-process manifest-fingerprint meaning.
- Audit providers/maps, managed acquisitions, per-call scopes, inherited singleton
  state and cleanup owners for references that retain analysis/source blueprints.
- Existing experimental artifact tests may need adaptation to new execution types;
  compatibility work does not make the artifact supported or start pre-compilation.

## Acceptance

- Warmup-only, instrumentation-only and combined successful builds construct no
  library analysis graph, manifest, validation context or full inspection index.
- Profiling measurements do not change selected targets, handler discovery,
  callback counts, runtime identity or teardown behavior.
- Warmup async/sync behavior, failure cleanup, multiple scopes, slots and supported
  overlays match the new documented contracts.
- Compare optional observer/label memory separately from uninstrumented startup.
- Ordinary scopes need no composition handle. A handle must match a live parent;
  releasing source data preserves emitted execution, inherited owners and cleanup.
  Report retained handle data separately; external ownership alone is not a saving.

Do not mark 21 complete while these features still call the old analysis finalizer.
