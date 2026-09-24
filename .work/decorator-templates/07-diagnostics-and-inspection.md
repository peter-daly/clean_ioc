# 07 — Diagnostics and inspection

Status: Accepted; all applicable gates passed. Dependency: 06 accepted (`34f19e6`).
Read the [workflow](README.md), [feature contract](../decorator-templates.md), and 06 handoff.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation | gpt-6-sol | high |
| Independent review | gpt-6-astra | high |

Sol High is recommended for bounded reporting work once the compiler and provenance facts are established.

## Bounded outcome

Explain source selection, group/derived target selection, generic projection, and generated decorators from captured facts.
Improve basic diagnostics already required by earlier milestones; do not defer structural error correctness to reporting.

## Search assignment

Locate BuildIssue/BuildReport, definition origins, frozen explanation sidecars, partial failure graphs, text/JSON
renderers, redaction and semantic manifest/fingerprint tests. Identify current template provenance from M04–06.

## Implementation assignment

- Preserve enough provenance to identify template, source registration, target registration/occurrence, and group contract.
- Explain ordinary source-filter/target-when decisions and actual source/target generic mappings without re-execution.
- Give actionable context for incompatible contributions, unresolved/ambiguous mapping, exact-binding failure,
  expansion dependency cycles, and overlapping independently declared policies.
- Keep definition IDs distinct from occurrence IDs. Make equivalent results deterministic.
- Reuse existing reporting facilities and privacy conventions. Do not leak closure contents, argument values,
  build-input secrets, private object representations, or add incidental provenance to semantic fingerprints.

## Verification and review gate

Exercise successful and failed builds and frozen inspection. Use sentinel private values and callbacks that fail if
re-evaluated by inspection. Verify alias labels, stable ordering, and appropriate boundary contexts.
Run tooling/manifest/failure-report regressions. Review must trace reported facts back to compiler capture.
