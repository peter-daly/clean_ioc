# 01 — Compact and share decorator-selection facts

Status: Complete — scoped to diagnostics disabled; see [result](01-result.md)\
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Priority: First experiment\
Prerequisite: Capture the current richer-fixture baseline.

Read the [shared plan](README.md) for measurement and compatibility requirements.

## Outcome

Reduce the retained cost of decorator-selection evidence, particularly repeated
template nonmatches, while preserving captured decisions and public explanations.

## Evidence and code to inspect

The eight-route fixture retains 56,522 decorator explanations with diagnostics
disabled. A follow-up census found 565,220 decisions and the same number of
template facts; only 792 decisions were selected. The related objects and tuples
accounted for 139.7 MiB of shallow storage. Reproduce and save this census before
treating it as a before/after baseline.

Start with `_Compiler._compile_decorators`, `_ExplanationCloneContext`,
`_clone_component_tree` and `_GraphExplanationSidecars` in
[container.py](../../clean_ioc/container.py); `CandidateDecision`,
`TemplateDecision`, `CompilationExplanation` and `CompiledGraph.explain_decorators`
in [tooling.py](../../clean_ioc/tooling.py); and consumers in
[selection_census.py](../../clean_ioc/selection_census.py).

## Work

1. Extend the evidence runner to count unique explanations, decisions, template
   facts and tuples, their outcomes/reasons and shallow storage. Deduplicate by
   identity and keep this census outside measured build/resolution intervals.
2. Identify fields shared by a template/source or registration-level selector
   result, and fields specific to an occurrence or callback evaluation. Account
   for source/target bindings, boundaries and cloned occurrence remapping.
3. Implement a narrow compact representation for repeated immutable facts.
   Explore storing a shared decision pattern plus occurrence-specific references
   and exceptions. Retain actual predicate results and deterministic ordering.
4. Materialize the existing public explanation representation when requested,
   using captured facts only. Do not silently remove rejected decisions merely
   because diagnostics are disabled; existing inspection and validation consume
   decorator facts in that mode.
5. Measure build and retained memory before/after, plus the first and repeated
   explanation/census accesses. Record whether lazy views or caches retain memory.

## Acceptance criteria

- [x] The additional decorator-object census is reproducible and saved.
- [x] Selected/rejected facts, template provenance, ordering, overlap facts and
  cloned target occurrence IDs match the baseline with diagnostics on and off.
- [x] Filters, factories and position callbacks retain their invocation semantics;
  resolution and inspection do not rerun them.
- [x] Validation, selection census, reports and explanation errors retain their
  documented behaviour, including boundaries and overlays.
- [x] The richer fixture resolves the same instances, decorators, providers and
  maps with the same lifetimes; relevant tests and required checks pass.
- [x] Repeated measurements demonstrate retained-memory benefit and document
  peak/build/runtime/inspection tradeoffs without treating 139.7 MiB as a promised saving.
- [x] Record the implementation or declined-experiment decision and update status.

## Recorded result

See the [implementation and measurements](01-result.md). Retained traced allocations
fall 75.9% in the eight-route fixture, with a 48.0% build-time increase and uncached
public explanation materialization costs. Diagnostics-enabled history remains eager
to preserve census identity semantics. All 2,055 tests and required checks pass;
strict MkDocs retains its eight pre-existing external-to-docs link warnings.
