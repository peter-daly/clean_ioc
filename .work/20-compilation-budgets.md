# 20 — Compilation budgets

Created: 2026-10-04\
Status: Deferred; not scheduled; implementation not started\
Priority: P2\
Baseline: Clean IoC 2.0.0b29 on `version2`\
Dependencies: Existing compiler work counters, structured failures, and partial diagnostic graphs\
Related work: [Compilation profiler](11-compilation-profiler.md),
[failed-build diagnostics](05-failed-build-diagnostic-graphs.md), and
[build-error triage](09-build-error-triage.md)

## Outcome

Allow applications to set explicit limits on compiler work and receive a useful build diagnostic when a composition
exceeds them. This prevents unexpectedly large occurrence expansion or template/specialization work from producing
an uncontrolled build, without changing ordinary compilation when no budget is configured.

The feature enforces deterministic work-count limits. It is not a timeout mechanism that can interrupt arbitrary
application callbacks, and it does not activate components to estimate their runtime cost.

## Proposed surface

Consider an immutable `CompilationBudget` supplied through a separate optional `budget=` argument on root and scope
builder `build()` methods. Names and exact fields remain proposed. Candidate limits are graph occurrences, dependency
depth, specialization materializations, generated template outputs, and diagnostic attempts.

Do not put compiler control in magic `build_args` keys. Define legal values, counting units, exact threshold behavior,
and default-unlimited semantics before accepting the API. A configured limit of zero must have an explicit meaning;
do not silently interpret it as unlimited. Budget configuration and outcomes do not alter graph fingerprints.

## Counting and failure contract

1. Count real compiler operations with explicit units. Occurrences, candidate attempts, specialized registrations,
   templates, and executable steps are different quantities. Reuse item 11's operation boundaries rather than sampling
   profiler detail or inferring work from the final graph alone.
2. Cover the full build, including discovery/preparation, source-inspection compilers, recursive expansion, primary
   compilation, and diagnostic retries where applicable. Specify per-phase versus whole-build accounting. Dependency
   depth describes one active path; it is not summed across independent roots.
3. Existing structural-pattern non-termination checks remain mandatory and distinct. An optional general budget must
   not relax those checks or turn a bounded-depth diagnostic into a generic Python recursion error.
4. Stop before performing the operation that would exceed its configured limit. Produce a stable structured error
   with the limit kind, configured maximum, observed work, phase, and best available declaration/root/path evidence.
   Never report a partially compiled graph as a usable runtime.
5. Budget exhaustion must not trigger unbounded recovery compilation. Carry the budget through retries, retain the
   original exhaustion finding, and label omitted/truncated diagnostic evidence honestly. Do not replay composition
   callbacks merely to reconstruct information that the budget already prevents collecting.
6. Failed builders remain repairable. A fresh explicit build starts fresh counters; diagnostic retries within that
   build do not replenish its work allowance. Overlay builds count work they actually perform, with existing anchored
   reuse distinguished from fresh materialization.
7. `BuildMatrix` budgets, if exposed there, apply to each variant build and aggregate through existing failure reports.
   Do not quietly create a matrix-wide budget or require caller-owned parents to be rebuilt.
8. Reports never include private build/provision values, owner tokens, or arbitrary callback/exception representations.
   Timing information from an optional profiler stays separate from deterministic limit enforcement.
9. Normal runtime resolution, provider invocation, and scope creation gain no budget work. Unconfigured compilation
   overhead must be measured and kept small; runtime component activation is outside these counters.

## Diagnostics and tooling

Define stable codes such as a proposed `compilation-budget-exceeded`, with a structured limit kind rather than
interchangeable names for different counters. Decide whether distinct codes improve suppression/triage before
implementation; these failures remain errors and cannot be ignored into a successful build.

Integrate text/JSON, source-linked SARIF, partial-graph/triage reporting, and compilation profiles. Explain which
operations were counted and which diagnostics could not be collected after exhaustion. No standalone web UI is needed.

## Stages when resumed

1. Inventory existing count/recursion/retry limits and define precise deterministic units and threshold semantics.
2. Add the optional immutable budget and propagate one build-owned counter state through relevant phases.
3. Integrate safe exhaustion diagnostics, bounded recovery, builder repairability, and tooling exports.
4. Verify boundary cases, no-activation behavior, supported Python, and configured/unconfigured overhead; obtain review.

## Acceptance criteria

- Small controlled graphs stop at the documented limit, with useful phase/path/source evidence and no usable partial
  runtime. Disabled limits preserve existing behavior.
- Generic expansion, source/template work, overlays, and failed-build retries obey their defined counting rules.
- Budget exhaustion cannot cause unbounded diagnostic work, secret leakage, or repeated resets within one build.
- Failed builders can be repaired and rebuilt; reports and matrix aggregation remain deterministic and source linked.
- CI/docs and focused measurements validate the contract without introducing wall-clock-dependent tests.

## Deferred status

Resume only when the maintainer prioritizes this item. It can proceed independently of incremental compilation and
plan optimization; neither is required to define deterministic work limits.
