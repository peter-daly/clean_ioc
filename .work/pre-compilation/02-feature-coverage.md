# 02 — Feature coverage and first supported subset

Created: 2026-10-09\
Status: Ready for investigation only — implementation is not ready\
Assignment: Unassigned\
Prerequisite: Existing artifact experiment and runtime feature tests

## Outcome

Establish exactly which Clean IoC features can be exported and loaded, then
implement the agreed first subset without changing normal container semantics.
Produce a source-backed coverage matrix before extending the codec. A feature
must have both an artifact representation and equivalent runtime behaviour.

## Readiness and decisions

The inventory can be assigned now. Implementation needs a reviewed first subset
and the relevant contracts from tasks 01 and 03–08. The initial recommendation is
fixed composition with ordinary scopes, importable factories/resources and the
features required by the application selected in task 09. This is a proposal.

Decide which features are required for the first delivery, which have clear
export-time rejection, and whether full metadata/profiling must ship initially.
Decide artifact-backed `ScopeBuilder` overlays separately from frozen boundaries;
supporting ordinary scopes does not require retaining a composition blueprint.

## Work

1. Inventory public declarations, compiled step/activation types and runtime
   readers. Compare `_check_plan`, the codec's record allowlist and actual
   independent-process coverage. Do not infer support from activation labels.
2. Record each feature's current normal-build behaviour, artifact status,
   missing representation, lifetime/cleanup requirements and test evidence.
   Cover these families and meaningful combinations:
   - constructors, sync/async factories, generators and context-manager resources;
   - singleton, scoped, per-resolution and transient lifetimes;
   - collections, managed collections, all provider families and provider maps;
   - decorators, registration/decorator templates and contextual selection;
   - aliases, closed generics and other supported type-key forms;
   - injected Scope/Container/ResolutionContext and declared resolution requests;
   - pre-configurations, boundaries, per-call proxies and warmup plans;
   - slots, runtime root filters, explanation modes, profiling and overlays.
3. Propose the first subset using task 09's application requirements. Mark each
   row supported, planned, deferred or unsupported, with evidence and an owning
   task. A synthetic fixture pass is evidence for its combinations only.
4. After the subset is agreed, implement execution-feature gaps owned here:
   factories/resources, ordinary and managed collections, injected contexts,
   declared resolution requests, and any approved boundary/per-call support.
   Coordinate callable/generated-type encoding with 03 and state/ownership
   reconstruction with 04. Task 01 owns slots; 07 owns startup/warmup; 08 owns
   reporting. Record a precise implementation scope before starting this stage.
5. Validate unsupported constructs before completing export and identify their
   consuming dependency or declaration. Preserve existing registration,
   collection, cleanup and selection semantics; do not quietly drop features.

## Verification and acceptance

- [ ] An evidence-backed matrix covers execution paths and combinations, with
  explicit owners and a reviewed first-delivery list.
- [ ] Every supported row has a normal-versus-loaded semantic test; lifetimes,
  sync/async cleanup and failed activation are included where relevant.
- [ ] Missing codec records/types are caught before a completed artifact is
  published, with actionable errors rather than silent omission.
- [ ] Deferred features are rejected explicitly and documented; normal compiled
  containers retain their existing capabilities.
- [ ] Loading does not repeat template expansion, dependency inspection or
  selection. Shared acceptance rules and applicable checks pass.

## Starting points

- [Artifact codec](../../benchmarks/graph_artifact.py) and
  [artifact tests](../../tests/test_graph_artifact_experiment.py).
- [Runtime/compiler steps](../../clean_ioc/container.py),
  [factories](../../docs/factories.md), [scopes](../../docs/scopes.md),
  [boundaries](../../docs/boundaries.md) and
  [pre-configurations](../../docs/pre-configurations.md).
- [Application validation](09-application-validation.md) and the
  [shared plan](README.md).
