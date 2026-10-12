# 04 — Share repeated subtrees through contextual views

Status: Reverted — dropped at the maintainer's request on 2026-10-09
Implementation agent: GPT-6.1 Sol (`gpt-6.1-sol`), medium reasoning\
Priority: Fourth experiment; broader representation change\
Prerequisite: Use the representation and reachability findings from tasks 01–03.

Read the [shared plan](README.md) for measurement and compatibility requirements.

[Completed implementation, evidence and tradeoffs](04-result.md).

The implementation was removed because process RSS increased and inspection
slowed despite a smaller retained Python allocation footprint. See the
[rollback record](04-rollback.md). The plan and completed acceptance checklist
below describe the historical experiment; they do not indicate active subtree
sharing in the current runtime.

## Outcome

Store proven-equivalent graph subtrees once and represent their uses through
small contexts that preserve distinct logical occurrences, parents and ownership.
Extend the existing provider-view mechanism only where its semantics fit.

## Evidence and code to inspect

The baseline retains 88,558 physical records, 1,765 distinct execution steps and
50 provider view contexts. The compiler already shares some execution and
provider metadata, but the remaining physical subtrees may repeat structure.
Do not assume all occurrences can collapse to the execution-step count.

Start with `_ComponentGraph.view`, `_ComponentViewContext`, `_ComponentViewRecord`
and traversal in [components.py](../../clean_ioc/components.py); provider target
reuse, `_clone_component_tree`, subplan eligibility and explanation remapping in
[container.py](../../clean_ioc/container.py); and occurrence-aware reporting in
[tooling.py](../../clean_ioc/tooling.py).

## Work

1. Measure repeated subtree shapes after the preceding optimizations. Separate
   structural similarity from proven-equivalent selection and activation facts.
2. Define a narrow eligibility rule covering dependency selections, decorators,
   derived arguments, generic bindings, lifetime/cache/cleanup ownership,
   boundary visibility and template decisions. Context-sensitive cases must keep
   the existing representation until equivalence is established.
3. Represent eligible uses with a shared frozen subtree plus explicit contextual
   remapping for parent, occurrence and owner relationships. Support or reject
   nested/inherited views deliberately; do not leave ambiguous identity rules.
4. Preserve logical traversal and explanation targets without eagerly retaining
   a materialized copy for every use. Keep uninstrumented resolution free of new
   whole-graph traversal or compilation work.
5. Measure physical storage, view contexts, logical traversal, runtime and
   inspection costs separately. Check memory after repeated graph inspections
   to detect caches that recreate the original duplication.

## Acceptance criteria

- [x] A documented equivalence rule limits sharing to safe subtrees; regression
  cases prove that parent-dependent templates and other differing contexts remain distinct.
- [x] Logical occurrence identity, parent/dependency/decorator links, origins,
  ownership and explanation remapping remain correct across nested views/overlays.
- [x] Transient identity, scoped/singleton sharing, managed acquisitions,
  sync/async cleanup, failures and relevant concurrency behaviour are preserved.
- [x] Graph filters, manifests, reports, fingerprints and observed calling-edge
  attribution match the baseline; relevant tests and required checks pass.
- [x] Repeated measurements show a useful net retained-memory benefit and record
  peak/build/runtime/traversal tradeoffs, including repeated inspection.
- [x] Record the implementation or declined-experiment decision and update status.
