# 02 — Separate component definitions from occurrences

Status: Complete\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Priority: Second experiment\
Prerequisite: Reassess the remaining graph-record cost after task 01.

Read the [shared plan](README.md) for measurement and compatibility requirements.

## Outcome

Replace repeated common metadata in component records with shared immutable
definitions and smaller occurrence records, while preserving the public
`Component` interface and occurrence-specific behaviour.

## Evidence and code to inspect

The baseline has 88,558 physical `_ComponentRecord` objects with 28 fields each.
Those objects alone occupy 21.6 MiB of shallow storage, excluding indexes and
referenced objects. Many fields describe the registration or activation, while
others describe a particular use of it. Equal registration IDs alone do not prove
that generic specialization, derived build arguments or ownership are equal.

Start with `_ComponentDraft`, `_ComponentRecord`, `_ComponentGraph`,
`_ComponentViewRecord` and `Component` in [components.py](../../clean_ioc/components.py),
then the draft/freeze, specialization, clone and ownership paths in
[container.py](../../clean_ioc/container.py).

## Work

1. Measure which fields repeat and which vary across occurrences, including
   ordinary registrations, values, decorators, providers and provider maps.
2. Propose a shared definition for genuinely invariant fields and an occurrence
   record for identity, parent/dependency relationships and necessary overrides.
   Include generic binding and lazy generic-mapping behaviour in the design.
3. Implement one representation split behind the existing public accessors.
   Define sharing keys without calling arbitrary application equality/hash/repr
   functions or retaining a global cache across builds.
4. Avoid unnecessary allocations for absent metadata where the representation
   permits it. Count new definition/index/override storage so moved allocations
   are not reported as eliminated allocations.
5. Measure before/after retained memory, freeze-time peak, build time, resolution
   and representative component traversal/inspection costs.

## Acceptance criteria

- [x] Shared fields have explicit equivalence conditions; contextual fields remain
  correct for generic specializations, derived arguments, boundaries and overlays.
- [x] Public component properties, relationships, occurrence IDs and frozen-view
  behaviour match the baseline, including escaped callback views.
- [x] Runtime filters, ownership/cleanup, managed providers, scope builders and
  observed resolution remain correct; transient products are not merged.
- [x] Manifests, explanations, semantic fingerprints and graph reports remain
  equivalent; diagnostics on/off and relevant feature tests pass.
- [x] Storage accounting includes shared definitions and their indexes, and
  repeated measurements show a useful net benefit with documented tradeoffs.
- [x] Record the implementation or declined-experiment decision and update status.

## Result

[Implementation, measurements and limitations](02-result.md): eleven captured
metadata fields share 116 definitions behind 88,558 unchanged occurrences.
Retained traced allocations fall 45.17→38.43 MiB; build allocation peak falls
80.22→73.58 MiB. RSS does not improve. All 2,070 tests and required checks pass;
strict MkDocs retains its eight existing outside-docs link warnings.
