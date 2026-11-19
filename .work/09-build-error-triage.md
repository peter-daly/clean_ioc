# 09 — Build-error triage

Status: Implemented and independently reviewed (2026-09-25)  
Priority: P1  
Dependencies: 05 failed-build diagnostic graphs; existing build reports and compilation explanations  
Related work: 04 parameter explanations; 01 semantic references

## Outcome

Turn a long failed-build report into a short list of distinct, evidenced problems and their affected roots. A developer
should see where to investigate first without losing the individual issues, witness paths, or retry outcomes.

Illustrative output:

```text
Build failed: 23 root failures, 2 triage groups

Missing Clock in boundary orders
  Observed in 19 root failures; 4 marked entry points affected
  Example: PlaceOrder → OrderRepository → clock: Clock
  Inspect: registration and visibility of Clock in orders

Singleton ReportCache retains scoped RequestContext
  Observed in 4 root failures
  Example: ReportCache → ReportBuilder → RequestContext
  Inspect: lifespans along this retaining path
```

Counts describe recorded evidence. A group identifies a shared failure mechanism, not a guarantee that one edit will
repair every member or that later failures will not appear after repair.

## Current foundation

`BuildReport` retains stable issue codes, severities, roots, and paths. `ContainerBuildError` also carries captured
selection explanations and a bounded `PartialGraph`. `_error_report()` retries independent roots to collect failures;
those attempts are deliberately separate. Existing deduplication removes repeated findings but is not a user-facing
cross-root triage report.

The current `BuildIssue` shape does not encode every fact needed to prove that two errors share a cause. Add small
structured evidence records at compiler failure sites where necessary; do not recover identity by parsing messages.

Primary integration points: `tooling.py`, `ContainerBuildError`, `_Compiler` failure capture, `_error_report()`,
`_compile_with_report()`, validation-rule reporting, `cli.py`, and compiler-tooling tests.

## Scope and non-goals

- Group supported structural failures conservatively and retain an explicit ungrouped category for insufficient evidence.
- Offer evidence-based investigation hints and declaration locations where available.
- Preserve original error codes, severities, findings, and CLI failure policy.
- Do not edit registrations, propose an automatically applied fix, invoke application code, or add compilation retries.
- Do not merge separate diagnostic attempts into a supposedly coherent executable graph.

## Proposed model and API

- `FailureEvidence`: safe failure kind, normalized requested service, definition/parameter references, relevant
  boundary/layer and selection context, attempt reference, and witness references when known.
- `TriageGroup`: stable report-local reference, grouping reason, member issue references, distinct affected roots and
  marked entry points, bounded witness paths, optional provenance, and a fixed investigation hint.
- `BuildTriage`: groups, ungrouped issues, source-report references, evidence completeness, and truncation/count metadata.

Proposed Python surface: `error.triage_report()` and a pure `BuildTriage.from_report(report, evidence=...)` factory for
validation-only reports or saved evidence. Without sufficient evidence the factory retains separate findings. All
reports support `to_text()` and `to_json()`; names are proposals until implemented.

Proposed CLI: `clean-ioc check TARGET --triage --format text|json`. Default `check` output and existing `BuildReport`
serialization remain unchanged. The triage JSON includes the original findings and member references so automation
does not have to reconstruct individual errors from a group summary.

## Implementation stages

### 1. Define grouping evidence

- [x] Define conservative keys for missing dependencies/slots, captive dependencies, cycles, and generic failures.
  Missing-service groups must include the actual selection and visibility context; equal service names alone are
  insufficient. Keep distinct named requests, filters, boundaries, and overlay layers separate unless equivalence is
  established by captured compiler facts. Never inspect callback closures to establish equivalence.
- [x] For captive dependencies retain both the retaining ancestor and offending dependency; for cycles retain the
  actual directed definition sequence; for generic errors retain the requested specialization and template context.
- [x] Use internal identities for matching within one build and deterministic semantic references for serialization.
  Preserve alias normalization and NewType distinctions without relying on display-name equality.
- [x] Keep custom validation findings, callback failures, pre-graph failures, and unsupported error kinds separate
  unless explicit structured evidence supports grouping. Never group arbitrary custom messages by text similarity.
- [x] Distinguish missing declarations, invisible definitions, rejected candidates, and unexamined candidates. Attach
  different hints only when the corresponding cause was actually established.

### 2. Capture once and aggregate honestly

- [x] Capture missing evidence alongside existing failure snapshots and associate every issue with its attempt.
  Do not rerun filters, derivations, validation rules, or normal compilation to improve a group.
- [x] Count distinct roots, entry points, raw issues, and attempts separately. Repeated retries must not inflate an
  affected-root count, and unknown entry-point membership must remain unknown.
- [x] Allow a report group to reference separate attempts without merging their graphs. Flag incompatible attempt
  evidence and retain it separately; do not infer one common cause from inconsistent retries.
- [x] Bound group details, witnesses, and evidence retention. Distinguish exact totals, retained counts, and lower
  bounds when the underlying partial graph was truncated. Never invent omitted paths.
- [x] Order groups deterministically by severity, known affected-root count, and semantic reference. Avoid an
  unsupported numerical estimate of repair cost or architectural risk.
- [x] Return fresh immutable triage data; repairing and rebuilding the builder must not retain prior failure evidence.

### 3. Expose actionable reports

- [x] Render a concise cause, evidence for grouping, affected roots, one representative path, and a fixed next step.
  Keep all retained member references available in JSON and detailed text output.
- [x] Cover failed structural builds, build-mode policy errors after structural compilation, validation-only errors,
  and errors before a partial graph exists. Fall back to a standalone issue when evidence is unavailable.
- [x] Apply existing warning suppression and strictness rules consistently in `check --triage`; errors remain fatal.
  A failed build still exits 1 even when triage generation succeeds. Invalid usage or output failures exit 2.
- [x] Keep group identifiers separate from stable issue codes. Suppression continues to use the original warning
  codes; grouping must not hide findings or turn errors into warnings.
- [x] Redact configured/default/provided values, build-input identifiers, callback state, and arbitrary exception text.
  Reuse safe compiler labels and optional best-effort relative source provenance.

### 4. Documentation and cost

- [x] Add examples of one missing dependency affecting many roots and same-type failures that must remain separate.
- [x] Explain that triage groups summarize known evidence and that fixing one can reveal additional failures.
- [x] Measure bounded aggregation on wide invalid graphs; successful builds and ordinary resolution must not perform
  triage aggregation or retain failed-attempt objects.

## Verification

Cover many roots sharing one missing dependency; same-type failures in different boundaries, layers, names, and filter
contexts; transitive captive paths with different retaining ancestors; cycles entered at different roots; and distinct
closed generic failures. Include custom rules with identical messages but different meanings, failures before graph
allocation, and validation-only errors.

Test inconsistent callback results across existing retries, partial-graph truncation, exact versus lower-bound counts,
and successful repair of the same builder. Callback counters must show that repeated rendering adds no calls. Check
deterministic group references, complete member accounting, CLI strictness/suppression, and unchanged ordinary report
JSON. Exercise sentinel secrets and representations that raise if evaluated.

## Acceptance criteria

- A repeated supported failure produces one useful group with traceable member issues and affected roots.
- Different causes are not merged merely because their issue codes, service labels, or messages match.
- Incomplete and inconsistent evidence is explicit; original findings and attempt boundaries remain accessible.
- Triage adds no application activation, composition passes, or changes to build success/failure semantics.
- Default reports, manifests, fingerprints, and uninstrumented runtime behaviour remain compatible.

## Implementation record (2026-09-24)

`clean_ioc.tooling` now exports frozen `FailureEvidence`, `TriageGroup`, and `BuildTriage`; failed builds expose
`ContainerBuildError.triage_report()`. `BuildTriage.from_report()` keeps validation-only and unsupported findings
individual. Compiler failure sites capture missing/visibility, captive, cycle, and selected generic-specialization
facts. The existing independent retry attempts are referenced; triage rendering does not compile or invoke callbacks.
`clean-ioc check TARGET --triage --format text|json` applies the existing warning policy and preserves a failing exit
status. The default `BuildReport` JSON and default CLI output are unchanged. Public examples and uncertainty rules are
documented in `docs/compiler-tooling.md`; focused coverage is in `tests/test_build_triage.py`.

Group root, entry-point, attempt, and witness lists are capped while retaining exact counts and every original
finding reference. Count-status fields distinguish exact issue/attempt totals, retained detail, and lower-bound
witness evidence when partial capture is truncated. Evidence capture retains at most 500 detailed facts; additional findings remain ungrouped and
are marked incomplete. The pre-existing partial graph retains at most 100 retry attempts. A local 200-invalid-root
measurement produced 200 findings, one group, and 201 attempts (101 retained); aggregating the captured report 100
times averaged 0.178 ms per call on this machine. This is a diagnostic cost sample, not a runtime benchmark.

Verification: 836 repository tests passed; full Ruff lint and format checks, full `ty check`, and documentation
example validation passed. No new compiler retries or ordinary-resolution traversal were added.

Limitations for independent review: generic failures before graph allocation remain standalone. Overlay-layer separation follows captured definition origins,
but a dedicated overlay integration test is still needed. Source provenance is best-effort.

Independent review follow-up: retry and entry-point correlation now uses boundary-aware root identity. Reports retain
separate issues for the same root label failing in two boundaries; successful roots in other boundaries do not clear
evidence or imply an inconsistent retry. `tests/test_build_triage.py` covers all four review cases.
The subsequent count review is addressed by storing issue-boundary context alongside the original findings, including
unsupported callback failures. Detached reports without that context label their affected-root count a lower bound.
The text renderer uses the same count status and prints "at least" for lower-bound affected-root counts; focused
triage/compiler-tooling tests (130 cases), Ruff, type checking, and whitespace checks passed after this correction.
