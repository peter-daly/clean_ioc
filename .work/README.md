# Graph information work list

Created: 2026-09-12  
Status: Items are tracked individually; see each row for its current implementation status.  
Baseline: Clean IoC 2.0.0b12

This work list turns the graph-information and compiler-diagnostic ideas discussed with the maintainer into implementation plans. Each
item is independently reviewable and includes its scope, data/API design, implementation stages, tests, and completion
criteria. API names below are proposed until implemented; examples must not be presented as existing public APIs.

Items 09–11 were added on 2026-09-24 against Clean IoC 2.0.0b18 and are implemented and independently reviewed.
Item 12 was added on 2026-09-25 as the first runtime-profiling slice of item 08 and is implemented and independently reviewed.
Item 13's ordinary-filter scoring experiment was retired on 2026-09-27. Item 14 restarts the design around
parent-context registration selection. Astra medium implemented explicit scalar precedence;
Astra high independently reviewed it and recommended KEEP. Before/after probes,
supported-Python checks and performance evidence are recorded with the item.
Item 15 implements explicit chained preferences for remaining single-dependency ties,
with consumer and registration-context chains built using `prefer(...).then(...)`.
Implementation is complete; Python 3.14 CI and supported-Python checks pass.
Repeated benchmarks document compilation cost; separate Astra high review recommends KEEP.

Item 16 was added on 2026-10-04 against Clean IoC 2.0.0b29. Managed resource providers are implemented by Sol Medium
and independently reviewed by Sol High; APPROVE / KEEP. Explicit context-manager acquisitions execute frozen targets
in isolated scopes. CI, supported-Python checks, executable docs and focused measurements are recorded with the item.

Item 17 was also added on 2026-10-04: declared warm-up plans compile selected singleton startup targets, then activate
them only through an explicit runtime call with aggregated diagnostics. Sol Medium implemented the feature and
Sol High independently reviewed it; APPROVE / KEEP. CI, supported-Python checks and executable docs pass;
focused measurements and their noise limits are recorded with the item.

Items 18–22 were added on 2026-10-04. The maintainer prioritized compiler items 18–20 on branch
`codex/compiler-optimization`, starting from released beta 2.0.0b30. [Baseline benchmarks](compiler-optimization-baseline.md)
were captured before production changes; implementation and independent review completed sequentially. Items 21–22 remain deferred,
scope the remaining coverage/tracing deliverables of item 08, and reuse item 12's implemented profiler.

Item 18's Sol High investigation is complete and independently reviewed; KEEP the evidence and decline production
cross-build caching for this delivery. Eligible reuse saves little additional work across builds, and timing is inconclusive.

Item 19 reuses captured implementation-type metadata when cloning compiled graphs. Sol High implemented and a
separate Sol High agent reviewed it; KEEP. Repeated normalizations are eliminated while graph occurrences, ownership
and executable structure remain unchanged. The introspection boundary and noisy measurements are documented with the item.

Item 20 implements optional deterministic compilation budgets with bounded, source-linked diagnostics and independent
allowances for matrix variants. Sol High implemented and a separate Sol High agent reviewed it; APPROVE / KEEP.
CI, Python 3.11–3.14, executable docs and strict documentation checks pass. Measurements establish exact work limits;
machine noise prevents a reliable small overhead estimate. Runtime execution gains no budget work.

## Graph memory optimization

The separate [graph memory optimization plan](graph-memory-optimization/README.md),
created on 2026-10-08, tracks four completed experiments: compact decorator-selection
facts, shared component definitions, discarded-record pruning, and contextual
subtree sharing. Tasks 01 and 02 retain scoped implementations; task 04 was
reverted at the maintainer's request on 2026-10-09 because process RSS increased;
its measurements are preserved. Task 03
declines production pruning. Task 04 ran as GPT-6.1 Sol at medium reasoning.
Task 05, implemented by GPT-6.1 Sol at high reasoning on 2026-10-09, is retained:
`explain_metadata=False` releases unnecessary successful-build metadata and graph
records with explicit inspection limits while preserving resolution. The
[result](graph-memory-optimization/05-result.md) records same-source eight-route
Python retention 38.43→3.10 MiB and RSS 134.16→129.45 MiB, diagnostics' larger
compilation floor, ownership costs, all 2,127 passing tests and the existing strict
documentation-link limitation.
[Task 06](graph-memory-optimization/06-result.md) was investigated by GPT-6 Astra
with high reasoning; production sources remain unchanged. Its conservative
scalar-only weak cache probe lowers peak 72.844→52.053 MiB and RSS
130.766→106.781 MiB, with observed timing costs and strong fallback for opaque
application values. Broad weak caching and coarse evidence omission are rejected.
Early immutable fact interning is a separate build-speed proposal. The report
records phase attribution, repeated measurements, lifetime counterexamples and
ranked implementation readiness.
[Task 07](graph-memory-optimization/07-result.md) was completed by GPT-6.1 Sol
with medium reasoning. Effective slots reduce traced peak 1.422 MiB and normal
RSS median 1.766 MiB (overlapping ranges), preserving weakrefs; ready for scoped
implementation/review. Compact indexes save more in the probe but have eight
artifact failures and mapping design limits; not ready. Draft sharing remains
not ready, and pre-lookup avoids 25,081 constructors without established memory/
speed benefit. All 2,132 tests pass for slots/pre-lookup, lifetime/attribution/fact
checks match and slots checks pass Python 3.11–3.14. These are investigation
artifacts; production sources remain unchanged.

[Task 08](graph-memory-optimization/08-result.md) was completed as an investigation
by GPT-6.1 Sol with high reasoning. Bounded compact indexes lower reduced build
peak 72.844→67.851 MiB and RSS 130.438→119.734 MiB, with full retention
38.432→33.523 MiB. All eight artifact failures and ordinary mapping/view cases are
resolved; 2,132 tests and focused Python 3.11–3.13 checks pass. Six stronger custom-
hash counterexamples remain, including read-only proxy equality; a separate native-
delegation feasibility refinement passes them but is unintegrated/unmeasured.
Sparse-only storage and full artifact loading have measured costs. **REFINE; not
ready for implementation**, with a bounded adapter/fallback and remeasurement plan.
Production sources, earlier evidence and parked pre-compilation work are unchanged.

[Task 09](graph-memory-optimization/09-result.md) is complete: GPT-6.1 Sol with
medium reasoning integrated native delegation and bounded small/sparse fallback
in an isolated prototype. All six hash counterexamples, 103 operation/codec checks,
2,132 tests, 16 lifetime cases and focused Python 3.11–3.13 checks pass. The final
104-process matrix retains ~4.96 MiB reduced-peak/full-retention savings; sparse
maps pay only 72-byte carrier overhead. Full artifact export/load medians rise
~13%, and dense sidecar lookup remains ~3× native. **RETAIN the prototype for
implementation review; production adoption is not approved.** Shared sources,
prior evidence and parked pre-compilation work are unchanged. Repository checks
pass with one narrowly documented prior Task 08 evidence E501 exception.

## Pre-compilation

The [pre-compilation plan](pre-compilation/README.md), created on 2026-10-09,
tracks nine tasks after the reduced-artifact experiment: unified slots, feature
coverage, Python symbol loading, fresh runtime state, build inputs and variants,
artifact format and packaging, startup, profiling, and application validation.
The feature inventory is ready for investigation; the implementation work is
marked not ready where decisions or prerequisites remain. The agreed slot rules
are preserved. This work is planning only and remains unassigned.

## Work items

| ID | Item | Priority | Prerequisites |
| --- | --- | --- | --- |
| 01 | [Reverse dependencies and impact analysis](01-reverse-dependencies-and-impact-analysis.md) | P0 | Existing compiled graph |
| 02 | [Instance-sharing groups](02-instance-sharing-groups.md) | P0 | 01 graph references/index |
| 03 | [Entry-point activation analysis](03-entrypoint-activation-analysis.md) | P0 | 01; 02 for cache scenarios |
| 04 | [Argument and generic-binding explanations](04-argument-and-generic-binding-explanations.md) — implemented and reviewed; failed-specialization limitation documented | P1 | Existing explanation capture; 01 references |
| 05 | [Failed-build diagnostic graphs](05-failed-build-diagnostic-graphs.md) — implemented and reviewed | P1 | 01 reference conventions; 04 improves detail |
| 06 | [Architecture annotations and evidence paths](06-architecture-annotations-and-evidence-paths.md) | P1 | 01; 03 for eager/deferred summaries |
| 07 | [Behaviour-aware diffs and build variants](07-behaviour-aware-diffs-and-build-variants.md) | P1 | 01–03; 06 for capability comparison |
| 08 | [Runtime observations over the compiled graph](08-runtime-observations-and-graph-overlays.md) — remaining extensions deferred; scoped by 21–22 | P2 | 12 core profiler; 01–03 stable references and execution semantics |
| 09 | [Build-error triage](09-build-error-triage.md) — implemented and independently reviewed | P1 | 05 partial failure evidence; existing build reports |
| 10 | [Registration selection census](10-registration-selection-census.md) — implemented and independently reviewed | P1 | Existing selection explanations; 01 semantic references |
| 11 | [Compilation profiler](11-compilation-profiler.md) — implemented and independently reviewed | P1 | Existing build pipeline; independent of runtime tracing |
| 12 | [Runtime resolution profiler](12-runtime-resolution-profiler.md) — implemented and independently reviewed | P1 | 01–03 graph analysis; V2 resource ownership proof |
| 13 | [Component-filter match strength](13-component-filter-match-strength.md) — retired; implementation archived locally | P1 | Superseded by 14 |
| 14 | [Parent-context registration selection](14-parent-context-registration-selection.md) — implemented by Astra medium and independently reviewed by Astra high; KEEP | P1 | Existing contextual registration compilation and selection explanations |
| 15 | [Chained component preferences](15-chained-component-preferences.md) — implemented by Astra medium and independently reviewed by Astra high; KEEP | P1 | 14; existing argument policies and captured selection explanations |
| 16 | [Managed resource providers](16-managed-resource-providers.md) — implemented and independently reviewed; KEEP | P1 | Existing typed providers, resource ownership proof, and isolated per-call scopes |
| 17 | [Declared warm-up plans](17-declared-warmup-plans.md) — implemented and independently reviewed; KEEP | P1 | Existing frozen root/activation plans, singleton ownership, and structured diagnostics |
| 18 | [Incremental compilation](18-incremental-compilation.md) — investigation complete and reviewed; production cache declined for this delivery | P2 | Existing composition snapshots, occurrence-specific compilation, and 11 |
| 19 | [Execution-plan optimization](19-execution-plan-optimization.md) — implemented and independently reviewed; KEEP | P2 | Existing frozen steps, ownership/sharing analysis, and 11–12 |
| 20 | [Compilation budgets](20-compilation-budgets.md) — implemented and independently reviewed; KEEP | P2 | Existing work counters, structured failures, and 05 diagnostic evidence |
| 21 | [Test activation coverage](21-test-activation-coverage.md) — deferred; slice of 08 | P2 | 12 exact runtime observations and matching full graph catalog |
| 22 | [Detailed activation tracing](22-detailed-activation-tracing.md) — deferred; slice of 08 | P2 | Existing observed plans, full graph catalog, and resource ownership proof |

## Recommended implementation sequence

1. Implement 01's semantic references, relationship index, reverse queries, and text/JSON reports.
2. Implement 02's sharing identities and 03's basic activation obligations. These are the first developer-facing release.
3. Implement 04 and 05 to make valid and invalid composition understandable at parameter and failure-path level.
4. Implement 06, then 07's semantic diff and explicit build-matrix stages.
5. Implement 12 after static correlation and ownership semantics are covered by tests; extend it with 08's recording,
   graph overlays, and telemetry integration afterward.

An item need not wait for every optional extension of its prerequisites. For example, 08 does not require graph-diff
policy, and 05 can ship without richer generic explanation rendering. Numbering groups work; it is not a requirement
to implement every file strictly in order.

For the new diagnostic items, start with 09 using the existing failed-build snapshots, then 10's declaration inventory
and selection accounting. Item 11 can proceed independently; it profiles the actual compiler work and does not depend
on 08's runtime instrumentation. None of 09–11 requires completing policy packs or build-variant comparison first.

Implement 12 as the first runtime slice before 08's event-stream, graph-overlay, coverage, and OpenTelemetry extensions.
It measures actual resolution and activation; item 11 measures compilation and shares neither timing records nor its
`profile=` keyword. A composition-root configuration variable may choose item 12's independent `instrumentation=`
option.

Item 15 builds on item 14's explicit parent precedence, with its completed baseline
captured before implementation. Preferences narrow remaining ties without
changing ordinary predicate composition, root selection or collection membership.

Item 16 can proceed independently using the existing provider and per-call scope foundations. Its profiler integration
uses item 12; detailed tracing from item 08 is not a prerequisite.

Item 17 can proceed independently of item 16 and detailed tracing. Build compiles warm-up declarations; explicit startup
activation is a separate runtime operation, and item 12's existing profiler observes it when enabled.

Items 18–20 completed sequentially after capturing a pre-change benchmark baseline. Items 18 and 19 began with
measurement and equivalence investigations; item 20 followed the reviewed item 19 implementation.
Items 21–22 remain deferred. Item 21 can derive coverage from item
12 without waiting for item 22. Item 08 remains the shared observation design; its remaining extensions are deferred.

## Agent assignments and review

Assign each work item to a Terra agent (`gpt-5.6-terra`) with **medium** reasoning for implementation.
Have a separate Sol agent (`gpt-5.6-sol`) with **high** reasoning review each item's implementation against its plan,
acceptance criteria, and the shared design rules below. Resolve review findings before marking the item complete.
Schedule implementation according to the prerequisites and recommended sequence above.

For items 09–11, the maintainer requested sequential implementation by a Sol agent at high reasoning, with a
different Sol agent at high reasoning reviewing each item. This instruction supersedes the assignment above for those
items. Complete implementation and review of 09 before starting 10, and likewise complete 10 before starting 11.
For item 12, the maintainer requested Sol High implementation and separate Sol Extra High review.
For items 14 and 15, the maintainer requested Astra Medium implementation and separate Astra High review.
This overrides the default agent assignment above for those items.
For items 16 and 17, the maintainer requested sequential Sol Medium implementation and separate Sol High review,
with a local commit after each reviewed item. Finish and commit 16 before starting 17.
For items 18–20, the maintainer requested a new branch, baseline benchmarks before compiler changes, and sequential
Sol High implementation. A separate Sol High agent reviews each item under the existing review requirement.
Capture and preserve the baseline first, then finish implementation, verification and review of 18 before starting 19,
and likewise finish 19 before starting 20. Record each reviewed item separately on the local branch.

## Shared design rules

- Keep three evidence categories explicit: **compiled facts**, **application declarations**, and **runtime observations**.
  Observations must never silently become static guarantees, and declarations must not be described as verified effects.
- Preserve build-time-only composition and immutable runtime wiring. Analysis cannot invoke application constructors,
  factories, generators, context managers, argument derivations, or selection filters to recover missing information.
- Distinguish registration identity, graph occurrence, semantic path, cache owner, and runtime event identity. None is an
  interchangeable substitute for another. Shared initializers and anchored parent steps require explicit handling.
- Keep default manifests/fingerprints stable when only analysis, provenance, annotation, or telemetry changes. Add
  optional report/export sidecars instead of putting every new field into the existing manifest.
- Retain beta's unversioned JSON convention. If a semantic format change is necessary, document regeneration of
  baselines; do not add version adapters or schema-version fields during beta.
- Do not serialize configured values, provided values, build-input names/values/hashes, runtime object IDs, owner tokens,
  callback closure state, or arbitrary object representations. Public user-authored annotations are deliberately public
  metadata and must be labelled as such. Source provenance keeps the current best-effort, relative-path policy.
- Static analysis output must be deterministic. Observation/profile reports must render the same captured recording
  deterministically; measured durations can differ between runs and never enter structural fingerprints.
  Reports must work for aliases, closed generics, structural patterns, provider maps,
  decorators, pre-configurations, boundaries, scope slots, and overlays.
- Ordinary `new_scope()` and uninstrumented resolution must gain no analysis traversal, observer branch, timing call, or
  event allocation. Lazily construct tooling indexes from frozen data; capture missing facts once during compilation.
- Keep current methods, return types, CLI commands, and raw diffs working. New report commands use import locators,
  never evaluated Python expressions. CLI exit codes are 0 for success, 1 for findings/build failure as documented by the
  command, and 2 for invalid usage/input or output failures.
- Do not build a new web application as a prerequisite. Deliver Python APIs, text/JSON, and focused Mermaid projections
  first; those artifacts can later power an interactive viewer.

## Existing roadmap relationship

The older [.v2_roadmap](../.v2_roadmap/README.md) remains architectural context. In particular:

- Item 06 complements its architecture-contract and policy-pack proposal.
- Item 07 implements the graph-information portions of semantic change policy and build-variant checking.
- Item 08 extends activation tracing with aggregation and graph overlays.
- Item 09 builds on 05's partial snapshots to summarize failure evidence without replacing raw build issues.
- Item 10 aggregates compilation provenance into a declaration-wide selection inventory; it is separate from 08's
  runtime activation coverage.
- Item 11 measures compilation itself, including diagnostic retries, independently of activation tracing.
- Item 12 makes the first part of 08 useful for slow resolves and frequently constructed factories; 08 extends its
  instrumentation and graph correlation rather than defining a second runtime observation system.

Avoid implementing competing models for those proposals. Reuse and refine them, updating their status and links when
an implementation lands. Where terminology differs, current `Boundary` and `per_resolution` names apply. These plans
add explicit identity, redaction, uncertainty, and bounded-output requirements to those earlier proposals.

## Completion checklist for every item

- [ ] Implemented and reviewed with the assigned models and reasoning levels (including item-specific overrides); review
  findings are resolved.
- [ ] Public API, compiler capture where needed, and frozen report representation agree.
- [ ] Python and CLI output are documented with executable public-API examples.
- [ ] Relevant tests cover real selection/ownership behaviours, not just dataclass serialization.
- [ ] Redaction, deterministic output, boundaries, overlays, and sync/async behaviour are verified.
- [ ] Required runtime/build-cost checks pass; measurements and limitations are recorded without unsupported claims.
- [ ] Existing public API and manifest behaviour remain compatible, or an intentional beta change is documented.
- [ ] Work-item status and relevant older roadmap entries are updated with implementation/test references.
