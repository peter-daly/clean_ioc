# 14 — Parent-context registration selection

Status: Complete — implemented by Astra medium, independently reviewed by Astra high; KEEP\
Created: 2026-09-27\
Priority: P1\
Branch: `codex/parent-filter-precedence`\
Base: `version2` at `63cbea4` (`2.0.0b23`)\
Implementation: Astra (`gpt-6-astra`), medium reasoning\
Review: Separate Astra (`gpt-6-astra`), high reasoning\
Replaces: [13 — Component-filter match strength](13-component-filter-match-strength.md)\
Evidence: [use cases](14-parent-context-use-cases.md), [baseline probe](probes/parent_filter_baseline.py),
[recorded baseline](probes/parent_filter_baseline.json)

## Outcome

Let independently composed registrations express which parent contexts they
serve, and select the best applicable registration for a single dependency
without requiring bundle installation order to encode every contextual
override.

The motivating distinction is that each registration supplies its own policy.
This is not an attempt to infer preferences from one consumer filter applied
uniformly to all candidates.

For example, a general connection, a connection for transactional parents, and
a connection for a particular reporting handler may all be eligible at the
same dependency occurrence. A contextual preference can make that choice
explicit while retaining LIFO as the tie-breaker.

This plan uses **explicit scalar precedence**, attached to the registration.
It does not infer specificity from predicate syntax. The maintainer authorized
implementation of this plan on 2026-09-27. The public API and scoped compiler behavior
are now implemented; the original contract below remains the acceptance reference.

## Before/after evaluation comes first

The maintainer requested concrete use cases before implementation. See
[the benefit probes](14-parent-context-use-cases.md), including executable
baseline observations and verified after results.

The baseline currently satisfies the intended overlapping-policy behavior for
**1/2** orders in the targeted-policy/fallback case and **1/6** orders in the
general/batch/regional case. The real after probe achieves **2/2** and **6/6**,
and P3 accepts its uniquely preferred target. Disjoint and mutually exclusive
rules already succeed in every tested order and demonstrate no scoring benefit.

The probe also records counterexamples: a deliberate application override can
be defeated by automatic conditional preference; orthogonal parent conditions
do not imply a business priority; and synthetic provider/collection parents
affect eligibility before scoring can apply. The implemented contract below
addresses those cases explicitly. It remains valid to keep LIFO if the practical
benefit is insufficient.

## Scope

- Preserve the restored boolean/LIFO behavior of ordinary component predicates,
  component selectors, and explicit runtime root filters.
- Limit the new choice to competing service registrations for a parent-context
  dependency occurrence during compilation.
- Consumer filters remain hard eligibility requirements. Preference cannot
  make a failed predicate, hidden registration, or invalid dependency eligible.
- Collection selection, provider-map membership, and plural queries retain all
  eligible members in their existing order.
- Decorator and pre-configuration `when` conditions remain boolean; several
  applicable decorators or pre-configurations may run together.
- Boundary import/export cardinality and definition-site visibility remain
  unchanged. A boundary consumer must not introduce a parent context where the
  current compiler deliberately hides that context.
- No parent score is inherited by children. Do not add scores across dependency
  edges, selected subtrees, or different application contexts.
- Ordinary runtime resolution activates the frozen plan. It does not evaluate
  parent policies again. New overlay builds are separate compilations.

## Public contract

Add one keyword to service-registration APIs:

```python
# Classes are the use-case fixture types.
builder.register(WaitPolicy, DefaultWait)  # parent_precedence defaults to 0
builder.register(
    WaitPolicy,
    OrdersWait,
    when=cf.parent(cf.with_name("orders")),
    parent_precedence=10,
)
```

`when` remains a boolean eligibility predicate. `parent_precedence` is a
constant declaration used to compare eligible candidates for an injected
single dependency. It is not a strength accumulated on the resulting component.

| Question | Decision |
| --- | --- |
| Value | Signed Python integer, excluding booleans; reject floats, strings, `None`, and callbacks. No reserved range or finite maximum. |
| Default | `0`, including registrations with `when`. Being conditional grants no automatic bonus. |
| Ordering | Higher wins. Negative values permit an explicit low-precedence fallback. Compare values; never add them. |
| Equal values | Preserve existing candidate order. Ordinary dependencies select the first and retain the ambiguity warning; typed providers retain their equal-best ambiguity error. |
| Applicability | Both registration `when` and the consumer filter must pass. Precedence cannot bypass either. |
| Predicate composition | Existing boolean operators and short-circuiting stay unchanged. `A`, `A & A`, and equivalent callbacks do not receive different scores. |
| Parent scope | Apply only to injected dependency selection during compilation, in the same visible definition-side parent context used by `when`. |
| Parentless selection | Ignore precedence for top-level roots, root entrypoints, builder previews, and runtime root filters. Dependencies inside those plans can still use contextual selection. |
| Collections | Preserve every eligible member and original order. No sorting, trimming, or score-based duplicate-key suppression. |
| Custom behavior | No computed-score callbacks, tiers, strength wrappers, or new expression engine. |

Validate values before mutating the builder. Zero behaves like omission. An
invalid declaration or patch must not leave partially changed registration state.

### API coverage and mutation

Add `parent_precedence: int = 0` to `register`, `register_pattern`,
`register_subclasses`, and `register_generic_subclasses`, including their
`ComponentBuilder` protocol signatures. Container, boundary, and scope builders
share the contract. Discovered registrations and discovery fallbacks carry the
declared value; exact/pattern/open-generic definition selection still runs first.

Add `parent_precedence: int | None = None` to `patch_component`: `None` leaves
the value unchanged; `0` resets it. Apply existing patch ownership/mutability
rules and preserve a patch to a discovered registration across materialization.
No API for modifying another boundary or an already built parent is introduced.

No additions to `ComponentSelector`, `cf.parent`, `select`, `resolve`, decorator
registration, pre-configuration, scope-slot declarations, or provider-map
registration are needed. A map member's service registration may declare a
value, but membership ignores it.

### Application overrides and incomparable rules

For R1, omission means zero; a library rule does not automatically outrank an
application registration simply because it has a `when` predicate. If the
library explicitly opts into `10`, the application can deliberately override
it with a greater value:

```python
# The application owns this policy; no artificial when rule needed.
builder.register(WaitPolicy, ApplicationWait, parent_precedence=30)
```

This applies to eligible injected occurrences. The application can narrow it
with `when`, register at an equal value and use LIFO, or patch a locally owned
registration. A later zero-precedence registration does not defeat an explicit
`10`; document that opt-in tradeoff. Scores do not change parentless root order.

For R2, geography and privacy have no intrinsic ordering. Their owner assigns
an explicit preference or leaves a tie. Do not publish universal type/name/tag
tiers or fixed "library versus application" number bands. Bundles opting into
nonzero values must expose/document their policy so applications can coordinate
overrides. Assess that coordination cost in the final usefulness review.

## Selection algorithm

1. Preserve visibility and exact/pattern/open-generic definition selection. Do
   not resurrect excluded registrations or search a rejected definition tier.
2. Compile/validate candidates in the existing order. Evaluate `when` at its
   current point, in the current definition-side view, with existing profiling
   and exception paths. Do not add a second predicate evaluation for scoring.
3. Capture effective precedence while the parent view is valid. A parent hidden
   across a boundary makes preference inapplicable: use a neutral comparison
   value and record that it was not applied.
4. Apply the consumer's boolean filter. Compare only surviving candidates.
5. For singular injected selection, retain the maximum-value candidates in
   their existing relative order. A unique maximum wins; use the ordinary or
   provider tie contract for that maximum group only.
6. Freeze the activation step. Runtime activation does not compare values,
   replay `when`, or rewire a provider target.

Use an O(n) stable maximum pass, not sorting. Preserve the all-zero path where
practical. A negative-only candidate set still selects its highest value; do
not initialize the maximum to zero and discard every negative candidate.

Compile and validate losing candidates as today. Low precedence does not hide
an invalid dependency, ownership error, or throwing predicate. Preserve failed
build repair, per-call scopes, and anchored singleton plans. No score propagates
between dependency edges.

### Selection-path audit

| Path | Apply parent precedence? | Required behavior |
| --- | --- | --- |
| Constructor and injected factory arguments | Yes, for a single registered dependency | Same parent eligibility and stable maximum rule |
| Service dependencies injected into decorators/pre-configurations | Yes | Does not rank which decorators/configurations apply |
| Injected `Provider[T]` / `AsyncProvider[T]` target | Yes | Unique maximum accepted; tied maximum retains `provider-ambiguous-component` |
| Collection or provider of a collection | No for membership | Same members/order/validation/cleanup; members' own dependencies can rank |
| Provider map | No for membership/keys | All eligible targets; duplicate keys remain errors |
| Parentless roots and marked root/provider entrypoints | No for root choice | Existing cached/default/custom-filter behavior and cardinality rules |
| `get_component_id(s)` / `has_component` previews | No for top-level query | No fabricated parent; compiled internal dependencies can rank |
| Declared `ResolutionContext` requests, `use_component` / async helper | No for requested root | These compile with `parent=None`; do not turn them into injection requests |
| Scope-slot fallback | No | Existing fallback only after registration selection fails |
| Boundary `Use` / `Expose` | No | Existing exactly-one contract and definition-side visibility |
| Scope overlay build | Yes for new dependency occurrences | Existing layer order breaks equal scores; frozen parent singletons are not rewired |
| Ordinary `new_scope()` and runtime resolution | No new work | Activate the frozen plan |

Pass selection purpose explicitly through internal calls if needed. Do not
infer it from a diagnostic subject string, or treat any synthetic parent as
authorization to rank a parentless root selection.

Keep the existing immediate-parent graph shapes:

```text
Worker → Policy
Worker → list[Policy] → Policy
Worker → Provider[Policy] → Policy
```

P3 explicitly navigates through the provider node; G3 does not and must keep
selecting the fallback. No implicit ancestor search or wrapper skipping is
part of this feature.

## Implementation map

| Area | Planned change |
| --- | --- |
| `clean_ioc/components.py` | Add protocol keywords. Keep `ComponentFilter` boolean. |
| `_BuilderBase` in `clean_ioc/container.py` | Validate/store metadata by source registration ID; support local patching and freeze/repair lifecycle. |
| `_Layer`, `_RegistrationDiscovery`, `_layer()` | Snapshot metadata immutably; carry through discovery, fallback, boundaries, and overlays. Preserve patches and source IDs during specialization. |
| `_CompiledCandidate`, `_Compiler._compile_candidates` | Capture effective value and whether it applies before restoring the temporary parent view. Do not add a global component strength. |
| `_Compiler._select_candidates`, `_compile_dependency`, `_compile_provider_dependency` | Stable maximum for intended singular paths; keep all maximum ties for caller-specific warning/error behavior. |
| `_compile_provider_map` and collection branches | Retain membership-only selection; no maximum pass. |
| Root compilation/finalization, `_compile_resolution_requests`, `_matching_slot`, runtime root selectors | Preserve top-level behavior; do not reuse ranked selection indiscriminately. |
| `clean_ioc/tooling.py`, `clean_ioc/selection_census.py` | Captured preference evidence and eligible-but-not-selected classification. |
| Docs, examples, probes, tests, benchmarks | Exercise the P/C/G/R cases and report actual benefit and cost. |

Prefer private metadata alongside `registration_when` and
`registration_policies` over widening the legacy registration engine. This is
a direction, not a requirement to add a redundant map if a simpler equivalent
representation exists.

## Diagnostics and compatibility

For preference decisions, explain the actual winner, effective values, and why
alternatives lost. Distinct reason codes such as `lower-parent-precedence` and
`equal-parent-precedence-order` should count as eligible-but-not-selected in
the census, not predicate rejection or generic-tier exclusion.

Distinguish "not applied" from a valid zero; an optional `parent_precedence`
evidence field can do that. Omit it from unrelated root/collection decisions.
For a tied provider maximum, report ambiguity without claiming a successful
winner. Preserve default diagnostics where no preference decision is made.

Capture evidence once. Reports, census, and profiling must not replay predicates.
The explicit integer is public policy metadata; callback closures, build-input
values, object addresses, and private names remain redacted. Do not include
preference numbers in structural fingerprints when wiring is unchanged; an
actual winner change must be reflected in the ordinary graph wiring.

No root-explanation cache redesign is required. Preserve single/collection and
boundary contexts rather than copying the retired experiment's root changes.
With all values omitted/zero, retain baseline selection, provider errors,
applicability, collection order, and tie behavior.

## Acceptance cases

- A targeted parent gets its contextual registration regardless of whether the
  general fallback was registered later.
- Another parent still gets the general fallback.
- Two contextual registrations can both match; the agreed scalar policy picks
  one deterministically and equal scores use the agreed tie behavior.
- An explicit consumer filter can exclude the higher-preference candidate.
- Omitted/zero values reproduce baseline selection; all-negative values still
  select the maximum. Invalid values fail before mutating the builder.
- Provider targets accept one unique maximum but retain ambiguity errors for
  two or more equal maxima, even when lower-precedence candidates also exist.
- R1 preserves default LIFO overrides and supports an explicit higher-valued
  application override. R2 uses explicit preference or a tie, without inferring
  business priority from predicate shape.
- List/tuple/set and provider-map membership remain unchanged, including order
  where ordered. Preference never trims a collection to its highest score.
- Parentless roots and builder queries preserve the decided parentless policy.
- Exact/pattern/open-generic precedence and boundary visibility are respected
  before contextual preference.
- Scores neither propagate into grandchildren nor rewire frozen singleton plans.
- A new overlay build may make a new local choice while ordinary `new_scope()`
  uses existing compiled plans.
- Decorators and pre-configurations retain their existing applicability and order.
- Callback errors retain useful paths; a failed build remains repairable.
- Explanations report captured choices without callback replay.
- Equivalent boolean predicates with the same declared value have identical
  preference behavior; changing only syntax cannot manufacture extra weight.

## Delivery stages

Each stage ends with concrete evidence. Baseline success does not complete an
after check. Stages 1–4 and the public documentation are implemented below.

### 1. Fix the comparison contract

- Keep the recorded baseline JSON unchanged. Reuse the same fixture registrations,
  parent metadata, and consumer filters in an after runner; add only preference
  declarations. Exercise the real compiler, not a model that sorts fixtures.
- Assign P1 `0/10`, P2 `0/10/20`, and P3 `0/10`. Keep C1/C2 equivalent and C3 tied.
- Add R1 variants: all-default values preserve the later application override;
  an explicitly preferred library policy is overridden by a greater application
  value. Add both tied and explicitly ordered R2 variants.
- Record selected implementations, providers, collections, warnings/errors,
  root controls, and explanation evidence.

Deliverable: executable comparison with fixed success criteria. P1 must reach
**2/2** orders, P2 **6/6**, and P3 must accept one uniquely preferred target.

### 2. Add declarations and immutable metadata

- Implement keywords, validation, patching, and protocol signatures.
- Cover direct registration, patterns, discovery/fallbacks, patch preservation,
  boundary handles, and scope builders.
- Verify omitted/zero, positive/negative/large values, rejected bool/non-integer
  input, failed-declaration atomicity, and post-build mutation rejection.

Deliverable: typed declarations with selection unchanged until stage 3.

### 3. Compile contextual choices

- Capture values in the same parent/visibility view as `when`.
- Apply maximum selection after consumer filtering for singular injected
  requests only; follow the path audit for everything else.
- Preserve ordinary tied-best LIFO warnings and provider tied-best errors.
- Exercise sync/async targets, wrapper-aware P3, and unchanged G3 eligibility.

Deliverable: P1/P2/P3 after targets achieved without predicate-expression or
runtime-root scoring changes.

### 4. Integrate diagnostics and lifecycle tests

- Record winner/loser evidence, census classification, and profiling without
  callback replay. Verify unchanged-wiring fingerprint stability.
- Cover hard consumer filters, equal/negative ties, roots/provider entrypoints,
  previews, parentless factory requests, and scope-slot fallback.
- Cover collection order, provider-map duplicate keys, and ranking of members'
  own dependencies independently of membership selection.
- Cover aliases, closed generics, structural-pattern precedence, definition-side
  parent masking, overlay precedence, anchored singletons, ownership, per-call
  scopes, callback failures, and repair after failed builds.

Deliverable: focused regression coverage proving both benefits and limits.
Extend existing suites where clearer than duplicating their lifecycle fixtures.

### 5. Document and measure

- Update filtering, arguments/compilation, and provider docs with an executable
  default-plus-contextual-override example and the R1 application override.
- Explain signed values, zero default, tie differences, immediate/synthetic
  parents, collections, root behavior, and absence of runtime rescoring.
- Run `make ci` and supported Python 3.11–3.14 suites. If experimental 3.15 is run,
  report it separately rather than treating it as a supported-version pass.
- Benchmark against `63cbea4`: unscored control builds, increasing contextual
  parent/candidate counts, injected providers, and membership-only collections.
  Check default and explicit-filter runtime roots to demonstrate no new scoring
  work there.
- Use the repository BenchBro workflow, separate timing from tests, repeat
  baseline/current measurements, and retain raw results and noise estimates.
  Investigate repeatable control-path regressions; do not infer performance
  from correctness or claim precision below observed variation.

Deliverable: after results, docs, CI evidence, and an honest cost comparison.
No arbitrary latency budget is imposed by this plan.

### 6. Independently review correctness and usefulness

- Review the API and every path against the contract. Reproduce P1/P2/P3,
  controls, and R1/R2 variants.
- Assess numerical coordination against controlled ordering, explicit consumer
  selection, and mutually exclusive rules.
- Resolve findings and rerun affected checks. Record a keep/revise/drop
  recommendation: correctness alone does not prove sufficient design benefit.

Deliverable: independent report and final work-item status. Commit, push,
version bump, merge, or release are not implied by this planning task.

## Completion checklist and current evidence

- [x] Preserve and retire the ordinary-filter scoring experiment.
- [x] Create a clean branch from the existing `version2` base.
- [x] Add concrete before/after benefit probes and execute the baseline without
  implementing scoring: 11 cases / 22 scenario-order runs, with five existing
  focused tests passing.
- [x] Verify the restored baseline: `make ci` passed on Python 3.14 with
  **961 tests**, lint, formatting, types, executable docs, and benchmark discovery.
  Log: `/tmp/clean-ioc-parent-filter-restart-ci.log`. Production code, tests, public
  docs, and package metadata matched `63cbea4` at that baseline checkpoint.
- [x] Draft explicit scalar API, path audit, delivery stages, diagnostics,
  acceptance targets, and usefulness-review criteria.
- [x] Implement declarations, validation, metadata, and local patching.
- [x] Implement scoped compiler selection and captured diagnostics.
- [x] Execute after probes: P1 2/2, P2 6/6, P3 unique maximum, controls, and risks.
- [x] Pass focused lifecycle/visibility/callback/type checks and supported CI.
- [x] Complete before/after performance measurements and public documentation.
- [x] Independently review, resolve findings, and record keep/revise/drop recommendation.

Implementation evidence:

- Added signed integer declarations, atomic validation, immutable layer snapshots,
  local patches including discovered registrations and fallbacks, and protocol coverage.
- Captured definition-side values and applied a stable maximum only at injected
  singular service/provider seams. Default/zero paths retain baseline behavior.
- Added captured explanation values and eligible-but-not-selected census reasons;
  independent review identified and fixed misleading legacy `first-eligible-wins`
  evidence on precedence losers, including tied maxima after a lower-valued first candidate. Review also caught
  Python's decimal conversion guard for huge integers; scores remain unbounded,
  reasons avoid decimal conversion, and large JSON evidence uses exact hexadecimal.
- [After runner](probes/parent_filter_after.py) and [recorded results](probes/parent_filter_after.json)
  exercise the real compiler. P1 2/2, P2 6/6, P3 `OrdersWait`; C/G controls and R1/R2
  default/tied and explicit variants pass. The saved baseline JSON is unchanged.
- `tests/test_parent_precedence.py` adds 47 focused tests for declarations, signed
  values, hard filters, discovery/patch, collections/maps, synthetic providers,
  immutable metadata, diagnostics/fingerprints/callbacks, boundary masking,
  generic tiers, overlays/anchored singletons, decorators/pre-configurations,
  failed-build repair, slots, and per-call activation.
- Python 3.14.4 `make ci` passed: **1008 tests**, lint, formatting, types,
  executable docs, and benchmark discovery; log `/tmp/clean-ioc-parent-precedence-ci.log`.
  Full suites also passed on Python 3.11–3.13; after the final diagnostics fixes,
  178 affected-path tests passed again on each version. Exact counts and skips
  are recorded in the measurement report below.
- Public filtering, argument, compilation and provider documentation now describes
  executable contextual selection and explicit application overrides.
- No commit, push, version bump, release, runtime ranking or retired scoring engine
  reinstatement was performed. Package version remains `2.0.0b23`.

Independent [Astra high review](14-parent-context-registration-selection-review.md):
**KEEP**, both findings resolved, 236 independently executed tests passed, and
root/request/boundary probes preserved the intended scope. Numerical coordination
remains an explicit tradeoff, not inferred specificity.

Performance and supported-version evidence: [measurement report](14-parent-precedence-performance.md).
Two baseline and two candidate passes show about 2–5% additional build time for
explicit-precedence single-dependency cases, with noisy local measurements and
no demonstrated material runtime effect. The largest measured graph adds about
0.756 ms. No latency budget was imposed; the bounded opt-in cost supports KEEP.
