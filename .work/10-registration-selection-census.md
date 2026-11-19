# 10 — Registration selection census

Status: Implemented and independently reviewed (2026-09-25)  
Priority: P1  
Dependencies: Existing compilation explanations; 01 semantic references  
Related work: 04 generic explanations; 05 partial failures; 08 runtime coverage; 07 build variants

## Outcome

Provide a declaration-wide view of where registrations are selected, included in collections, rejected, or excluded
by compiler precedence and visibility. Help developers investigate redundant defaults, unexpectedly broad overrides,
and composition rules that never participate in the analyzed requests.

Illustrative output:

```text
Selection census — marked entry points, including deferred targets

PaymentGateway → StripeGateway
  Selected by 6 distinct dependency requests across 3 entry points
  Root selection: reported separately

PaymentGateway → SandboxGateway
  Selected by 0 dependency requests in this view
  Rejected by its registration condition in 6 recorded requests
  Direct named root remains available

Serializer[list[T]]
  2 closed specializations selected
  Exact-registration precedence recorded for Serializer[list[Order]]
```

The census describes compiler decisions within an explicit view. It does not establish that a registration is unused
by the application, safe to delete, or unselectable under other inputs or runtime requests.

## Current foundation

`CompilationExplanation`, `CandidateDecision`, `_CandidateRecord`, and declaration origins already capture selection
evidence. `CompiledGraph` supplies occurrence paths, entry-point reachability, and reverse queries. Generic patterns,
decorator templates, provider maps, and boundaries have additional selection metadata.

A graph of selected occurrences cannot account for every losing or never-requested definition. The census needs a
safe declaration inventory plus captured request decisions; absence from the final graph is not a rejection reason.
Current decision records may need extra sidecar facts to distinguish eligible-but-not-selected from predicate rejection.

Primary integration points: blueprint/layer inventories, `_Compiler` candidate selection and specialization,
`_recorded_root_selection()`, boundary visibility, template expansion, `tooling.py`, `graph_analysis.py`, and `cli.py`.

## Scope and non-goals

- Cover ordinary, named, discovered, generic, pattern-generated, and boundary-exposed service registrations first.
- Link generated registrations back to their source definition without conflating declaration and specialization counts.
- Include decorators and pre-configurations as distinct definition kinds with their own applicability results.
- Separate root selection from dependency selection and eager use from deferred provider/per-call targets.
- Do not run extra filters, enumerate hypothetical build configurations, remove registrations, or invent runtime usage.
- Keep this report informational. Any future policy about census findings requires an explicit application rule.

## Proposed model and API

- `DefinitionReference`: deterministic declaration reference, kind, structural service/implementation labels, layer,
  boundary, name, source/template linkage, and optional provenance; never export raw registration UUIDs.
- `SelectionUse`: exact request/occurrence reference, selected view and phase, definition reference, recorded outcome,
  reason codes, candidate tier/precedence evidence, and contributing attempt when compilation failed.
- `DefinitionCensus`: distinct root/dependency request counts, collection inclusions, specialization counts, recorded
  rejection reasons, and bounded example paths for one definition.
- `SelectionCensus`: inventory, per-definition summaries, analyzed roots, deferred-edge policy, completeness, and
  capture/retention limits.

Proposed Python: `graph.selection_census(all_roots=False, include_deferred=True)` and
`error.selection_census()` for the recorded partial build. Text and JSON are the first deliverables. Proposed CLI:
`clean-ioc census TARGET [--all] [--exclude-deferred] --format text|json [-o PATH]`.

Default presentation uses marked entry points when present, otherwise all public compiled roots, and states that choice
explicitly. The declaration inventory remains visible, with counts scoped to that view. Private boundary definitions
appear through their actual contexts; inventorying them does not make them public resolution roots.

## Implementation stages

### 1. Define inventory and accounting units

- [x] Capture safe definition metadata before selection discards alternatives. Include declarations without a closed
  request, such as an unspecialized generic pattern, without pretending a concrete plan exists for them.
- [x] Distinguish source registrations, boundary aliases, generated specializations, graph occurrences, and executable
  steps. An alias of a source must not imply a second underlying registration or instance.
- [x] Define stable references using compiler-owned structural context and deterministic declaration ordinals where
  necessary. Identical-looking declarations must remain distinct even without source locations.
- [x] Count distinct requests separately from root reachability and candidate evaluation attempts. A shared occurrence
  reachable through two paths is not automatically two selection decisions; preserve both paths as evidence.
- [x] Separate root lookups from dependency uses so compiling a registration as its own root does not conceal that
  no analyzed dependency selected it. Treat collection inclusion as a valid use, not a lost single-service selection.
- [x] Preserve exact closed generic, structural-pattern, and open-fallback tiers and connect closed selections to their
  declaration. Retain existing alias normalization and NewType identity semantics.

### 2. Capture only established decisions

- [x] Aggregate existing selection records and add missing facts at the point normal compilation establishes them.
  Never reevaluate a `when`, filter, derivation, key function, or template callback for reporting.
- [x] Distinguish selected, collection-included, eligible-but-not-selected, predicate-rejected, excluded by a known
  tier/visibility rule, failed during compilation, and not-examined. A structurally failing candidate whose predicate
  never ran is not predicate-rejected.
- [x] Report no recorded request separately from zero selections across recorded requests. Arbitrary runtime filters
  and uncompiled generic requests remain outside the census; do not imply exhaustive selectability analysis.
- [x] Surface precedence-sensitive choices only where existing evidence identifies multiple eligible alternatives and
  the tie-break rule. Do not evaluate skipped candidates or reorder registrations to prove hypothetical alternatives.
- [x] Include provider/map targets, per-call scope targets, generated decorators, shared pre-configurations, private
  boundary selections, and declared runtime-resolution requests with their relationship kinds intact.
- [ ] For overlays distinguish new selection work from inherited anchored plans. Reused parent decisions may explain
  effective wiring but must not count as callbacks evaluated again during the overlay build.

### 3. Aggregate and render bounded views

- [x] Build lazy immutable census summaries from the frozen inventory and decision sidecars. Do not scan every
  definition against every occurrence when there is no recorded relationship.
- [x] Bound captured detail and example paths; expose omitted counts and whether totals are exact or lower bounds.
  Unknown outcomes and truncated capture must not become zero-selection claims.
- [x] Render per-definition summaries with links/references to representative selection explanations, paths, and
  provenance. Use language such as "not selected in this view", never "dead" or "safe to delete".
- [x] Keep partial failed-build attempts distinct and label the overall census incomplete. Reporting failure evidence
  must not add root retries or construct a successful graph from partial drafts.
- [x] Make successful census queries exit 0 even for zero selections; preserve exit 1 for a failed build when a partial
  census is emitted, and exit 2 for invalid input/output. Default manifests and issue policies remain unchanged.
- [x] Omit values, build-input identifiers, callback representations, provider-map keys, and private runtime identities.
  Renderers must not call arbitrary user representations to produce definition labels.

### 4. Documentation and cost

- [x] Document counts with examples for a fallback, a named-only registration, a collection, and a generic pattern.
- [x] Explain the difference between this census, entry-point reachability warnings, and observed activation coverage.
- [x] Measure inventory/capture cost separately from lazy report generation on many-candidate and many-specialization
  compositions. Preserve ordinary scope creation and runtime resolution paths.

## Verification

Cover same-type registrations with different names/conditions; root-only and dependency-only selections; collection
members; exact/pattern/open precedence; unspecialized templates; discovery; aliases; boundary visibility and aliases;
provider maps; per-call targets; generated decorators; shared pre-configurations; and anchored overlays.

Use a structurally invalid candidate whose predicate must never run, a skipped candidate, and multiple evaluated
eligible alternatives. Verify counts by request, definition, specialization, and root membership separately. Check
entry-point/all-root views, deferred exclusions, incomplete failed attempts, and bounded capture. Repeated census
queries must add zero callback invocations and produce deterministic redacted output with unchanged graph fingerprints.

## Acceptance criteria

- Every inventoried definition has an honest selection summary for an explicitly identified analyzed view.
- Root selection, dependency selection, collection inclusion, and generated specialization counts remain distinct.
- Rejection, precedence/visibility exclusion, failure, and missing evidence are never conflated.
- Overlap findings cite recorded eligibility and precedence evidence rather than speculating about unexamined cases.
- Reporting does not execute application/composition callbacks or change selection, runtime, or manifest semantics.

## Implementation record (2026-09-25)

`clean_ioc/selection_census.py` defines the public frozen references, per-definition summaries, uses, and report.
`CompiledGraph.selection_census()` and `ContainerBuildError.selection_census()` expose successful-view and primary
failed-attempt evidence; `clean-ioc census` renders text or JSON. The declaration inventory is captured once per normal
build. The report uses frozen compiler decisions and graph paths, with eight examples per definition. The partial
report retains the compiler's existing 500-candidate primary-attempt bound and labels totals as lower bounds.

Verification: `tests/test_selection_census.py` covers root/dependency/collection accounting, named rejection,
generic specialization and precedence, deferred provider and per-call targets, provider-map key redaction, generated
decorator links, boundary aliases, failed structural candidates, and bounded examples. The full suite passed with
852 tests; `ty check .`, Ruff, and documentation-example validation passed. A local 81-definition composition spent
0.39 ms inventorying, 90.14 ms building, 1.97 ms generating the lazy census, and 0.55 ms rendering JSON. A second
composition with 30 closed specializations spent 0.16 ms inventorying, 69.83 ms building, and 1.37 ms generating
the report. These are single local measurements, not performance guarantees.

Remaining review point: anchored overlay decisions retain existing compiler reason codes, but the census has no
separate callback-evaluation count for reused parent plans. The report counts effective recorded uses and does not
claim that an inherited callback ran again. Other build configurations, arbitrary runtime filters, and uncompiled
requests remain unknown.

Independent review fixes: global and boundary entry-point decisions now retain separate area context in the frozen
sidecar; partial attempts count recorded selected outcomes without implying complete root/dependency totals; marked
collection entry points use a distinct root-collection count. Public and boundary-local roots are also labelled by area
in the analyzed view and each root example. Regression tests cover all four cases.
