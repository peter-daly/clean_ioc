# 15 — Chained component preferences

Status: Complete — implemented by Astra medium; independently reviewed by Astra high (KEEP)\
Created: 2026-09-27\
Priority: P1\
Prerequisite: [14 — Parent-context registration selection](14-parent-context-registration-selection.md)\
Planning context: `codex/parent-filter-precedence`, based on `version2` at `63cbea4` (`2.0.0b23`),
with the completed item 14 changes still uncommitted\
Implementation: Astra (`gpt-6-astra`), medium reasoning\
Review: Separate Astra (`gpt-6-astra`), high reasoning

## Outcome

Support an explicit, reusable preference chain for choosing between otherwise tied
eligible registrations. A consumer can prefer characteristics of its dependency;
a registration can prefer particular parent contexts. A preference expresses
"favour this, but keep a fallback", without making the condition a requirement.

The maintainer requested `.then()` chaining. Each successive rule breaks only a
remaining tie. Earlier preferences cannot be outweighed by multiple later ones.
There are no numerical weights, inferred predicate specificity, or component-ID
tiers. Existing component predicates and their boolean composition remain intact.

This work item records the agreed behavior and implemented contract.
The APIs below are implemented; measured results are in the linked evidence.
The maintainer authorized implementation and independent review on 2026-09-27.
A version bump, commit, push or release is not part of this assignment.

## Public API

Export `prefer` and an immutable `ComponentPreference` type from `clean_ioc`.
The type holds an ordered tuple of component predicates; it is not itself an
eligibility predicate or a numeric score.

```python
# Fixture classes are introduced in the acceptance examples.
from clean_ioc import prefer, select
from clean_ioc import component_filters as cf

preferred_endpoint = (
    prefer(cf.has_tag("primary"))
    .then(cf.has_tag("region", "eu"))
    .then(cf.is_named)
)

builder.register(
    Client,
    arguments={"endpoint": select(cf.all_components, prefer=preferred_endpoint)},
)
```

Public signatures:

```python
def prefer(predicate: ComponentFilter) -> ComponentPreference: ...

class ComponentPreference:
    def then(self, predicate: ComponentFilter) -> Self: ...

def select(
    filter: ComponentFilter = default_component_filter,
    *,
    prefer: ComponentPreference | None = None,
) -> _SelectArgument: ...
```

- `prefer(predicate)` creates a one-stage chain. `.then(predicate)` returns a
  new chain; it never mutates the original. Reuse the same chain across bundles,
  builders and argument policies without shared mutable evaluation state.
- Accept one existing `ComponentFilter` per stage, including ordinary synchronous
  callbacks and composed predicates such as `A & B`. Composition inside a stage
  retains its existing boolean short-circuit behavior; its clauses gain no weights.
- Absence of a chain is `None`. No empty constructor, chain concatenation,
  operator overloads, custom comparators, score callbacks or numeric stages are
  needed for this item. `prefer()` without a predicate is invalid.
- Validate inputs before mutation. Reject non-callable stages, known async or
  generator callbacks, and values of the wrong chain type at the API boundary.
  Account for callable objects. Never accidentally treat an awaitable returned
  by a callback as a truthy preference; fail with a useful build diagnostic.
- Ordinary component-filter truth semantics apply. A preference failure does
  not remove a candidate unless another survivor satisfies the same stage.
- `select(prefer=chain)` retains the existing unnamed-component default filter.
  To prefer named registrations while allowing unnamed fallbacks, explicitly
  admit both with `cf.all_components`. Preference cannot undo the default filter.

### Registration-specific parent preferences

Add `prefer: ComponentPreference | None = None` to `register`,
`register_pattern`, `register_subclasses` and `register_generic_subclasses`,
including `ComponentBuilder` signatures. Container, boundary and scope builders
share the same contract. This chain is owned by the dependency registration.

```python
# All three implementations remain valid fallback policies.
builder.register(
    Policy,
    EuropeBatchPolicy,
    prefer=(
        prefer(cf.parent(cf.has_tag("workload", "batch")))
        .then(cf.parent(cf.has_tag("region", "eu")))
    ),
)
builder.register(
    Policy,
    AmericaBatchPolicy,
    prefer=(
        prefer(cf.parent(cf.has_tag("workload", "batch")))
        .then(cf.parent(cf.has_tag("region", "us")))
    ),
)
builder.register(Policy, GeneralPolicy)
```

The callback receives the candidate component, just as `when` does; `cf.parent`
explicitly navigates to its parent. No implicit parent conversion or ancestor
search is introduced. A chain can inspect any information available to the
existing predicate interface in that context.

Different registrations supply different parent rules. One shared predicate on
the same parent would give all candidates the same answer and break no tie.
These soft rules do not exclude a registration for other parents. Use `when`
for conditions that must hold for the implementation to be valid.

Patch contract: `patch_component(..., prefer=Undefined)` leaves the
chain unchanged; `prefer=None` clears it; supplying a chain replaces it. Reuse
the existing sentinel, validate before mutation, and preserve discovery patches
across materialization. Do not change `parent_precedence=None` patch semantics.

### Typed selectors and other surfaces

Keep `ComponentSelector` an eligibility abstraction in this slice. A bundle can
pair `selector.to_filter()` with a separate immutable preference chain when
constructing `select(...)`. Do not hide preference metadata inside the boolean
result of `to_filter()`, or make existing selector fingerprints silently ignore
new behavior. A future combined bundle-selection value would be separate work.

Do not add preference keywords to runtime `resolve`, builder previews, decorator
applicability, pre-configuration applicability, boundary imports/exports, scope
slots or provider-map definitions in this item.

## Decision order

Apply preferences only to a single injected dependency occurrence:

1. Preserve existing visibility, generic-definition tier selection, candidate
   compilation/validation, registration `when`, and consumer eligibility filter.
2. Retain the maximum effective `parent_precedence`, using item 14's definition-side
   parent masking and negative-value behavior. Preserve every maximum tie.
3. Apply the consumer's dependency-preference chain from `select(..., prefer=...)`.
4. Apply the remaining candidates' registration-specific preference chains.
5. If still tied, use ordinary LIFO plus the existing ambiguity warning. Injected
   typed providers still require one unique winner and retain an ambiguity error.
6. Freeze the resulting activation step. Ordinary runtime activation performs
   no preference work.

The consumer chain runs before registration soft preferences because it expresses
the choice at the injection site. Explicit numeric parent precedence remains
stronger than both. Neither phase can revive a candidate eliminated earlier.
This ordering is public behavior and needs a conflict example in the docs.

Preferences of a selected parent are not inherited by its child; children are
separate decisions. Do not add, propagate or compare preference results across
dependency edges, consumers or complete subtrees.

### One chain stage

Starting with the remaining ordered candidates:

1. If zero or one remains, do not evaluate any further preference callbacks.
2. Evaluate this stage once for every remaining candidate, in existing order.
   Do not stop at the first true result: other matches must remain eligible.
3. If any stage result is true, retain all true candidates in their existing
   relative order. Otherwise retain the complete set.
4. Continue to the next stage only while a tie remains.

All-true and all-false stages therefore preserve the tie. The chain cannot turn
a nonempty eligible set into an empty one. Every surviving candidate shares the
same consumer predicate at a given consumer stage.

For registration chains, stage zero compares each candidate's own first rule,
stage one its own second rule, and so on. A missing rule, absent chain, or
inapplicable definition-side parent context contributes a neutral non-match;
it invokes no callback. Continue through the longest remaining chain, stopping
when the tie resolves or all chains are exhausted. Distinguish these neutral
cases from an evaluated false predicate in captured evidence.

A longer chain gains no preference merely by being longer. An explicitly true
later rule can break a tie against a candidate with no rule at that stage.
For example, `[false, true]` beats `[false]`, while `[true]` beats
`[false, true, true]` at the first stage. `[false]` versus no chain stays tied.
These are boolean stage outcomes, not a public tuple-valued score API.

Use stable narrowing passes, not sorting. Worst-case work is O(candidates ×
evaluated stages). Preserve a fast path when no chains are configured. Appending
`.then(...)` must never change a winner already uniquely decided by the prefix.

## Context, laziness and lifecycle

Registration preferences observe the same definition-side component view as
`when`, including source identity/name/tags and masked external parents. When
that parent context is unavailable, skip the registration chain entirely; even
`prefer(cf.all_components)` must not make a hidden parent context influential.
Consumer preferences use the same visible candidate view as the consumer filter.

This requires care: `_compile_candidates` currently applies temporary source-view
and parent masking before `_select_candidates` runs. Item 14 can capture a
constant number there; a lazy preference chain cannot simply be evaluated eagerly
at that point. Preserve enough private context to evaluate only the required
stages later, using an immutable projection or an exception-safe scoped view.
Restore all affected fields on failure. Do not replay `when` or evaluate chains
twice to reconstruct the correct context.

Compile and validate losing candidates as today. A preference cannot hide an
invalid constructor graph, ownership violation or failing eligibility predicate.
Preference callbacks themselves are different: an unreachable later stage is
deliberately not executed. A reached callback exception fails the build with
the dependency path, phase and stage, rather than counting as false or falling
back to another candidate. Require pure synchronous predicates and document this
short-circuit contract.

"Once" means once per surviving candidate, reached stage and selection occurrence
within a compilation attempt. Multiple occurrences and existing diagnostic
recompilation attempts remain distinct. Reports never invoke callbacks to recover
missing evidence, and profiling must distinguish those attempts.

Successful build freezes configuration with its owner. Failed builds remain
repairable. New overlays can compile new choices; anchored parent singleton
plans retain their original dependencies, ownership and cleanup. No preference
evaluation is added to ordinary `new_scope()` or frozen-plan activation.

## Selection-path audit

| Path | Preference behavior |
| --- | --- |
| Constructor and injected factory dependency | Consumer chain, then registration chains, after precedence |
| Dependency injected into decorator/pre-configuration | Same; decorator/configuration applicability and order stay boolean |
| Injected `Provider[T]` / `AsyncProvider[T]` | Apply to the target; unique survivor succeeds, final tie remains an error |
| Collection, tuple, set, or provider of a collection | Membership/order unchanged; configured chains are not evaluated for membership |
| Provider map | Members/keys unchanged; duplicate-key errors remain; registration chains do not run for membership |
| A collection/map member's own single dependency | Independent injection decision; preferences can apply there |
| Parentless roots, root/provider entrypoints, runtime explicit filters | Existing root behavior; registration preferences do not run |
| `get_component_id(s)` and `has_component` previews | Existing top-level behavior; no fabricated parent or preference evaluation |
| Declared `ResolutionContext` requests and `use_component`/async helper | Preserve parentless root selection; do not turn these into injection requests |
| Scope-slot fallback | Existing fallback and binding behavior; no preference ranking of slots |
| Boundary `Use` / `Expose` | Preserve exact cardinality; no preference-based ambiguity suppression |
| Scope overlays and inherited singletons | New occurrences can choose; frozen inherited plans stay anchored |

A reused `select(filter, prefer=chain)` on a collection keeps its filter and
ignores the chain for membership; document that explicitly. An ignored chain
must not be evaluated, even if a stage would raise. Collections never acquire
a new sort order or lose non-preferred members.

Preserve synthetic graph parents. `Worker → Provider[Policy] → Policy` and
`Worker → list[Policy] → Policy` remain distinct from `Worker → Policy`.
Traversing to a worker through a provider still requires explicit nested
`cf.parent(...)`. The preference API does not redefine parent relationships.

## Before/after examples and acceptance targets

The following are **expected outcomes to probe**, not measured results. Record
the before state on the completed item 14 implementation, with preference
declarations absent. Use the same eligible registrations and metadata afterward;
add only the new preference declarations. Execute the real compiler.

| ID | Case | Before / target after |
| --- | --- | --- |
| P1 | Child chain: A is primary/EU, B primary/US, C secondary/EU; prefer primary, then EU | LIFO is expected to pick A in 2/6 orders; chain must pick A in 6/6 |
| P2 | First rule has no matches: EU and US endpoints, neither primary; same chain | Retain both after primary misses; EU wins in both orders rather than a missing-component failure |
| P3 | Earlier rule dominates: A primary/US/unnamed, B secondary/EU/named | A wins in both orders; B's two later matches cannot outweigh primary |
| P4 | Registration chains from the example above; batch/EU and batch/US consumers | With all precedence values zero, LIFO cannot give the two parents different winners; chains must give Europe/America respectively in all 6 orders |
| P5 | Two injected provider targets tie on explicit precedence; consumer chain distinguishes them | Existing provider ambiguity becomes a unique target; tied final chains still error, sync and async |
| P6 | Different-length registration chains and missing stages | Verify all three boolean examples above, all-false fallback, and exhausted-chain ties |
| G1 | Hard filter rejects the first-preferred candidate | Rejected candidate cannot return; the surviving fallback is valid |
| G2 | Consumer chain prefers B; registration chain would prefer A | At equal numeric precedence B wins; higher numeric precedence on A wins before either chain |
| G3 | `select(prefer=prefer(cf.is_named))` with its default filter | Named registrations stay excluded; explicit `cf.all_components` is needed to consider them |
| G4 | Collection membership, provider maps, duplicate keys, root selection, boundary cardinality | Exact existing results/order/errors; preference callback counts are zero at these selection sites |
| G5 | Provider wrapper context, cross-boundary alias/source context, overlays | No implicit ancestor matching, external-parent influence or rewiring of anchored plans |
| C1 | One eligible candidate, omitted chain, all-true/all-false stages | No new choice; skip unnecessary callbacks and preserve final tie contracts |
| C2 | Disjoint hard filters or an existing unique numeric maximum | No claimed benefit; chains do not override the already decided winner |
| R1 | Extend a shared chain; compare original and extended use sites | Original stays unchanged; extension cannot change a prefix's unique winner |
| R2 | A library adds a nonempty registration chain | Document how it can defeat a later zero-precedence fallback; application consumer preferences or explicit precedence can override deliberately |

Also cover every decisive stage position, equivalent boolean predicates, aliases,
generic binding inspections and exact/pattern/open-generic eligibility precedence.
An ID used as a hard filter remains an eligibility constraint; an ID predicate
used inside a chain obeys its declared stage order, with no privileged tier.

Retain actual winners, registration order, stage observations, final warnings or
errors, collection membership and callback counts. Before evidence must not be
overwritten with after data. Assess the benefit against numeric precedence,
explicit hard selection, controlled registration order and mutually exclusive
rules; a correct implementation alone is not sufficient reason to keep it.

## Diagnostics

Capture the selection phase (`consumer` or `registration`), stage index, boolean
outcome where evaluated, neutral/not-applied reason where relevant, and the stage
that eliminated each otherwise eligible candidate. Distinguish evaluated false,
missing rule, masked context and later stages not reached; never label skipped
work as a failed predicate.

Finalize winner/tie explanations only after all phases. Item 14 currently emits
equal-precedence LIFO/provider-ambiguity evidence inside `_select_candidates`.
That evidence would become incorrect if a later preference picked another
candidate. Refactor the decision boundary so ordinary ambiguity warnings and
provider errors describe only the final surviving set. Preserve item 14's
existing output when no chains are supplied.

Preference losers are eligible-but-not-selected in the selection census. They
must not be labelled rejected-by-filter or `first-eligible-wins` when those
were not the reasons. An ambiguous provider has no selected winner. Failed
callbacks identify phase/stage and partial work without exposing exception
payloads, closure values or arbitrary object representations.

Use safe predicate descriptions only where existing redaction allows them.
Do not export callback reprs, addresses, closure state or build-input values.
Avoid using callable equality, repr or serialized closure contents for identity.
No automatic structural fingerprint of arbitrary predicate behavior is promised.
Static graph fingerprints stay unchanged when final wiring is unchanged; an
actual winner change is reflected by the normal dependency edge.

Capture profiling counts/durations during actual evaluation. Rendering text,
JSON, explanations, census or profiling reports must never replay preference
callbacks. Preserve deterministic reports from the same captured recording.

## Implementation map and stages

| Area | Required change |
| --- | --- |
| New small preference module; `clean_ioc/__init__.py` | Immutable chain, `prefer`, `.then`, validation and exports; no replacement predicate engine |
| `clean_ioc/arguments.py` | Carry optional chain in `_SelectArgument`; preserve existing `select`/`inject` behavior |
| `_arguments_to_dependency_config`, `_compile_dependency`, `_compile_provider_dependency` | Carry the argument policy through ordinary and typed-provider compilation without losing it in the legacy parser adapter |
| `ComponentBuilder`, `_BuilderBase`, discovery and `_Layer` | Registration keywords, private source metadata, immutable snapshots and atomic local patch/clear |
| `_CompiledCandidate`, `_compile_candidates` | Preserve definition-side context needed for lazy registration preference evaluation |
| `_select_candidates` and its callers | Explicit single-injection selection mode; stable staged narrowing after numeric precedence; final tie evidence only |
| `tooling.py`, `selection_census.py`, compilation profiling | Captured phase/stage outcomes, eligible losers, partial failure evidence and no replay |
| Existing collection, map, root, boundary and slot paths | Audit for bypass and zero preference callback evaluation |
| Documentation, probes, tests and benchmarks | Demonstrate fallback value and tradeoffs, not inferred specificity |

1. **Record before cases.** Pin the actual completed item 14 source snapshot,
   run the planned examples without new keywords, and save baseline JSON. Item
   14 is currently uncommitted: `63cbea4` alone is not the correct baseline for
   this feature. Recheck repository state when implementation starts.
2. **Implement declarations.** Add chain immutability/validation, argument and
   registration transport, discovery/patch/freeze coverage and static typing.
3. **Implement selection and context.** Apply the decision order lazily, preserve
   all ties through each stage, and cover boundaries, synthetic parents, generic
   tiers, providers, overlays and callback failures.
4. **Integrate captured evidence.** Verify actual winners and final ambiguity,
   census classifications, fingerprints, redaction and profiling with callback
   counters. In particular test a preference winner that was not the first
   candidate tied at maximum numeric precedence.
5. **Verify benefit and cost.** Run after probes and compare every permutation
   and control. Add executable public examples; run full repository CI and the
   supported Python matrix. Use the repository's BenchBro workflow to compare
   the completed item 14 baseline against the candidate: absent-chain controls,
   early unique winner, long unresolved chains, increasing candidates, consumer
   versus registration phases, providers, collections and runtime activation.
   Measure real compilation and captured evidence, preserve raw runs, repeat
   unchanged baselines and investigate repeatable control-path regressions.
6. **Independent review.** Audit the public semantics and all selection paths,
   reproduce benefit probes, resolve findings, and record KEEP/REVISE/DROP. Weigh
   soft fallback and ordered choices against the added coordination and API cost.

## Completion checklist

- [x] Record `.then()` semantics, public API proposal, decision order and scope.
- [x] Specify before/after cases and non-benefit controls without claiming execution.
- [x] Capture the completed item 14 baseline and execute before probes.
- [x] Implement immutable chains, argument/registration transport and local patches.
- [x] Implement lazy, context-correct narrowing and final tie handling.
- [x] Preserve roots, collections, maps, visibility, generic tiers and lifecycles.
- [x] Capture accurate, redacted, non-replayed diagnostics and profiling.
- [x] Execute after probes, focused tests, full CI and supported Python checks.
- [x] Document API, fallback behavior, collection bypass and override coordination.
- [x] Record repeated before/after performance measurements and their limitations.
- [x] Complete independent review and a benefit-based KEEP/REVISE/DROP decision.

## Implementation evidence

- [Documentation comprehension check](15-filter-docs-comprehension.md): minimally
  briefed Luna low readers exposed wording gaps and a stale summary. Documentation
  was clarified; new scenarios and targeted rereading resolved the quiz errors.
- [Measured use cases and behavioral controls](15-chained-preferences-use-cases.md):
  55 primary plus eight context cases per version, with immutable baseline JSON.
- Python 3.14.4 `make ci`: 1072 passed, including 64 new preference tests;
  lint, format, static typing, documentation examples and benchmark discovery pass.
- Independent review found and prompted fixes for Python 3.11 partial callback
  validation, partial-failure census precision, and compact skipped-tail evidence.
  All findings were resolved and independently verified. The final
  [review](15-chained-component-preferences-review.md) recommends **KEEP**.
- [Performance evidence](15-chained-preferences-performance.md) and supported-Python
  matrix are complete: 27 cases, twice per baseline/candidate. At 16 candidates
  and 8 parents, late consumer chains add 2.65 ms (+16.17%) and registration
  chains add 3.40 ms (+20.59%) to build. Control and runtime differences remain
  within observed desktop variation. Long skipped tails show no growing cost.

Supported-Python validation: full earlier snapshots passed 1052 tests / 8 skipped
on 3.11.13, 1057 / 3 skipped on 3.12.11, and 1060 on 3.13.5. After the final
small source/test additions, 282 affected-module tests passed on each version.
Python 3.14.4 full CI passed 1072 tests on the final implementation.
