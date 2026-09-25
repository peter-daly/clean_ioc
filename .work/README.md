# Graph information work list

Created: 2026-09-12  
Status: Items are tracked individually; see each row for its current implementation status.  
Baseline: Clean IoC 2.0.0b12

This work list turns the graph-information and compiler-diagnostic ideas discussed with the maintainer into implementation plans. Each
item is independently reviewable and includes its scope, data/API design, implementation stages, tests, and completion
criteria. API names below are proposed until implemented; examples must not be presented as existing public APIs.

Items 09–11 were added on 2026-09-24 against Clean IoC 2.0.0b18 and are implemented and independently reviewed.
Item 12 was added on 2026-09-25 as the first runtime-profiling slice of item 08 and is implemented and independently reviewed.

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
| 08 | [Runtime observations over the compiled graph](08-runtime-observations-and-graph-overlays.md) | P2 | 12 core profiler; 01–03 stable references and execution semantics |
| 09 | [Build-error triage](09-build-error-triage.md) — implemented and independently reviewed | P1 | 05 partial failure evidence; existing build reports |
| 10 | [Registration selection census](10-registration-selection-census.md) — implemented and independently reviewed | P1 | Existing selection explanations; 01 semantic references |
| 11 | [Compilation profiler](11-compilation-profiler.md) — implemented and independently reviewed | P1 | Existing build pipeline; independent of runtime tracing |
| 12 | [Runtime resolution profiler](12-runtime-resolution-profiler.md) — implemented and independently reviewed | P1 | 01–03 graph analysis; V2 resource ownership proof |

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

## Agent assignments and review

Assign each work item to a Terra agent (`gpt-5.6-terra`) with **medium** reasoning for implementation.
Have a separate Sol agent (`gpt-5.6-sol`) with **high** reasoning review each item's implementation against its plan,
acceptance criteria, and the shared design rules below. Resolve review findings before marking the item complete.
Schedule implementation according to the prerequisites and recommended sequence above.

For items 09–11, the maintainer requested sequential implementation by a Sol agent at high reasoning, with a
different Sol agent at high reasoning reviewing each item. This instruction supersedes the assignment above for those
items. Complete implementation and review of 09 before starting 10, and likewise complete 10 before starting 11.
For item 12, the maintainer requested Sol High implementation and separate Sol Extra High review.

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

- [ ] Implemented by a Terra agent with medium reasoning and reviewed by a Sol agent with high reasoning; review
  findings are resolved.
- [ ] Public API, compiler capture where needed, and frozen report representation agree.
- [ ] Python and CLI output are documented with executable public-API examples.
- [ ] Relevant tests cover real selection/ownership behaviours, not just dataclass serialization.
- [ ] Redaction, deterministic output, boundaries, overlays, and sync/async behaviour are verified.
- [ ] Required runtime/build-cost checks pass; measurements and limitations are recorded without unsupported claims.
- [ ] Existing public API and manifest behaviour remain compatible, or an intentional beta change is documented.
- [ ] Work-item status and relevant older roadmap entries are updated with implementation/test references.
