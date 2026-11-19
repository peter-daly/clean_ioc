# 05 — Build inputs, constants and graph variants

Created: 2026-10-09\
Status: Not ready — value policy and variant selection need decisions\
Assignment: Unassigned\
Prerequisites: Task 01's slot contract and task 02's feature inventory

## Outcome

Make the boundary between compilation inputs, embedded constants and runtime
provisions explicit. A loaded graph keeps its compiled wiring while permitting
the runtime values deliberately represented by slots.

## Readiness and remaining decisions

- Choose the initial embedded constant types and whether embedding is explicitly
  opted into or follows a documented supported-value rule. Decide immutable
  configuration records and mutable container values deliberately.
- Decide how `fixed`, derived arguments, defaults and build inputs are classified
  after compilation. Do not assume every value that happens to serialize should
  enter the artifact.
- Choose how applications name and select separately compiled graph variants,
  reusing the existing build-matrix concepts where appropriate.
- Define whether and how variant/build provenance appears in a deployment
  manifest without adding configured names/values to public analysis reports.

The parent work list prohibits configured/build values in public analysis
exports. An executable artifact may need approved constants to resolve services;
record that distinct contract explicitly before changing the codec. Do not apply
the prototype's serialization of actual `build_args` as an accepted policy.

## Work

1. Trace values retained through build arguments, fixed arguments, derivations,
   defaults, registration metadata and optional explanation data. Classify each
   by actual runtime use and define what can be dropped after compilation.
2. Specify a small, explicit value representation for the approved constants.
   Define type preservation, shared references and mutable-value semantics.
   Unsupported values fail with their dependency/declaration location; no
   fallback to arbitrary object serialization or object representations.
3. Route late environment-derived objects through task 01's slots. Demonstrate
   two processes using different slot values with the same frozen graph.
4. Demonstrate a topology-changing input, such as implementation or decorator
   selection, producing separate artifacts. Loading selects an already compiled
   variant and does not evaluate build callbacks against runtime environment data.
5. Keep integrity/freshness identity separate from public graph fingerprints:
   a report that omits configured values cannot alone establish artifact freshness.
   Coordinate value-sensitive compatibility with task 06 without exposing values
   through ordinary diagnostics.

## Verification and acceptance

- [ ] A documented value table covers supported constants, late inputs, discarded
  build-only values and rejected objects, including their sharing semantics.
- [ ] Build-only inputs/callbacks are absent when no executable or explicitly
  supported reporting capability requires their results.
- [ ] Runtime-provided values are absent from exported artifacts; approved embedded
  constants are distinguishable from those late inputs in documentation and tests.
- [ ] Variant selection preserves frozen implementation/decorator decisions and
  incompatible or missing variants fail clearly.
- [ ] Independent-process tests verify constant/type identity requirements and
  mutable-value isolation where supported; public reports retain redaction.

## Starting points

- [Arguments](../../clean_ioc/arguments.py) and
  [argument documentation](../../docs/advanced/arguments.md).
- `_PlanSet.build_args` and compiled value steps in
  [container.py](../../clean_ioc/container.py).
- [Build matrix](../../clean_ioc/matrix.py),
  [matrix tests](../../tests/test_build_matrix.py) and the
  [current codec](../../benchmarks/graph_artifact.py).
