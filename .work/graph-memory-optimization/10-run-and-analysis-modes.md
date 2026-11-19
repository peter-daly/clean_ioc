# 10 — Replace fine-grained build switches with run and analysis modes

Created: 2026-10-10\
Status: Complete — implemented; [result](10-result.md), [contract](10-contract.md)\
Assignment: Task agent at high reasoning, authorized sequential workstream\
Recommended reasoning effort: High (`high`)\
Priority: First contract decision\
Prerequisites: Current consumer fixes and the [shared plan](README.md)

## Outcome

Replace fine-grained public build policy controls with exactly two modes:
**run** for the minimum correct application build, and **analysis** for the
complete supported analysis and validation workflow. These names and this
direction are agreed. `builder.build(mode="run")` and
`builder.build(mode="analysis")` are proposed syntax, not existing API examples.
Do not leave the old switches as permanent overrides or introduce a custom mode.

## Scope

- Inventory both builder entry points, ordinary scopes, overlays, CLI commands,
  build matrices, profiling, docs, fixtures and the experimental artifact codec.
- Account for `diagnostics`, `explain_metadata`, `check_unreachable`,
  `aggregate_errors`, `clean_orphans` and `allow_scope_builders`. Give each a
  fixed mode policy or an explicit replacement capability contract.
- Review `provider_roots` separately: it changes publicly resolvable handles.
  Preserve the requested composition surface through an appropriate declaration
  API rather than silently dropping roots in run mode or exposing extra roots
  in analysis mode. Discovery must not require public-root expansion.
- Account for actual composition inputs (`build_args`), budgets and observer
  hooks (`profile`, `instrumentation`). Decide which remain inputs or move to a
  dedicated API; they must not become a back door to combinable policy flags.
- Implement modes as shared compiler semantics with mode-specific evidence and
  retention policies. Merely translating a mode to existing flags is an initial
  migration step, not completion of the allocation-reduction workstream.
- Analysis must support the full documented graph/explanation/manifest/census,
  diagnostic and validation capabilities. Optional runtime observations still
  require actual runtime activity; building must not activate the application.
- Run retains resolution relationships, ownership/cleanup, the discovery
  catalogue, required warmup descriptors and an actionable failure contract.
  Task 11 settles validation and temporary evidence requirements.

## Decisions to settle before implementation

1. Default mode. `run` is the working proposal, not yet an agreed compatibility
   change to existing `build()` calls.
2. RC migration: immediate removal versus a time-limited deprecated adapter;
   error handling for mixed old/new arguments; update downstream Bark/Cop use.
3. Overlay composition. The minimum run output should avoid retaining a blueprint
   solely for future builds. Decide whether run runtimes reject scope builders,
   or whether an explicit separate composition owner supports them. Specify all
   parent/child mode combinations without adding another build-policy switch.
4. Analysis lifecycle and return contract: where full validation executes, how
   its errors are surfaced, and how CLI/matrix callers avoid duplicate passes.
5. Fixed unreachable-advisory, orphan-retention and failure-aggregation policies.
   Run may omit optional analysis work; it may not omit mandatory safety checks.

## Acceptance and deliverables

- A complete capability/migration table covering every current build parameter,
  runtime API and tooling entry point; no unsupported hybrid configurations.
- A documented decision for each item above before readiness changes.
- When implemented: both modes select the same components and preserve provider,
  decorator, scope, cleanup and discovery semantics for the same declarations.
- Analysis commands request analysis mode; normal application examples use run.
  A reduced runtime is never silently rebuilt to satisfy an analysis request.
- Clear errors for unavailable capabilities and removed arguments, executable
  migration examples and focused default/invalid-mode/overlay/tooling tests.

Historical readiness gate satisfied by the approved conservative contract in [10-contract.md](10-contract.md).
Implementation and checks are complete; task 11 now audits the deeper validation/evidence requirements.
