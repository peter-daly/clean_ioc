# Parent-context selection: before/after benefit probes

Status: Baseline and real after comparison executed; performance/review finalization pending\
Recorded: 2026-09-27\
Baseline: `63cbea4` / Clean IoC `2.0.0b23`\
Related: [work item 14](14-parent-context-registration-selection.md)

## What would count as a benefit?

The feature should remove unwanted dependence on bundle installation order
when independently supplied contextual policies overlap. Merely choosing a
different winner is not sufficient: state the intended winner first, explain
who owns that policy, and compare against solutions available today.

The cases below use illustrative outbox-worker wait policies, inspired by the
bundle-composition discussion. They are not claims about current Bark Core
registrations. The probe uses real Clean IoC APIs and also checks existing
repository examples. All dependency registrations in the probe are unnamed;
worker names/tags are parent metadata, not dependency names.

These baseline cases were recorded before choosing a scoring method. The
[implementation plan](14-parent-context-registration-selection.md) now implements
an explicit `parent_precedence` integer, defaulting to zero without an automatic
conditional bonus. The after runner exercises the actual compiler and verifies the targets below.

## Before/after matrix

Registration orders below are always written oldest to newest.

| ID | Use case | Before: observed baseline | After: required or conditional target | What it tells us |
| --- | --- | --- | --- | --- |
| P1 | Orders-specific wait policy plus a general fallback | Both apply to the orders worker; the later registration wins. Only **1 of 2** installation orders gives orders its custom policy and invoices the fallback. | **2 of 2** orders produce `OrdersWait` for orders and `DefaultWait` for invoices, if contextual-over-fallback is the declared policy. | Potential benefit: independently installed defaults cannot accidentally mask a targeted extension. |
| P2 | General, batch, and European-batch policies | All three apply to an EU batch worker; two apply to a US batch worker. Only **1 of 6** registration permutations gives every parent its intended policy. | **6 of 6** permutations give EU batch → `EuropeanBatchWait`, US batch → `BatchWait`, interactive → `DefaultWait`, under that declared policy. | Potential benefit: overlapping local overrides without making broader bundles enumerate every exception. |
| P3 | The same overlap behind a typed provider, with an explicit path through its parent node | Both targets are eligible; build fails with `provider-ambiguous-component`. | The plan accepts a unique maximum and freezes that target; tied maxima retain the ambiguity error. | Potential benefit, but also an intentional change to a stricter existing contract. |
| C1 | Disjoint EU/US parent rules | Correct targets in **2 of 2** orders already. | Exactly the same targets. | No scoring benefit. Parent filtering itself already solves this. |
| C2 | Orders rule plus a fallback explicitly excluding orders | Correct targets in **2 of 2** orders already. | Exactly the same targets. | A working alternative today; scoring is useful only if it avoids undesirable coupling between independent bundles. |
| C3 | Two implementations with the identical parent rule | The later implementation wins in both tested orders. | LIFO still wins when scores are equal. | No benefit from inferred specificity; useful control for ordinary application overrides. |
| G1 | Consumer explicitly requires the default implementation | The default wins even when a newer contextual registration is also applicable. | The default still wins, regardless of another candidate's score. | Eligibility must remain a hard requirement. |
| G2 | A contextual collection whose predicates explicitly account for its synthetic parent | Both eligible policies are included, newest first, in both orders. | Preserve the exact same list for each order; do not retain only the preferred policy or sort it first. | Collection ordering is a protection, not a scoring benefit. |
| G3 | A direct-worker parent rule used behind a provider | The rule does not match the synthetic provider parent; the provider resolves the fallback. | Same eligibility and fallback unless parent-navigation behavior is changed in a separately approved design. | Scoring cannot repair a rule that does not match. |
| R1 | Application intentionally registers a replacement after a library's targeted policy | The application replacement wins today. | Blindly giving every conditional registration a higher score would make the library policy win instead. | Counterexample: order independence can defeat a legitimate explicit override. The application needs a clear way to express its intent. |
| R2 | EU policy and privacy-restricted policy both apply | Reversing registration order changes the winner. | There is no objectively correct inferred winner; an explicit business policy or the existing tie rule must decide. | Overlap does not imply one policy is more specific or more appropriate. |

## P1 — Default assembly plus an application extension

An application installs an orders-specific wait policy. A convenience bundle
also installs a normal wait policy for every worker. Both are legitimate,
independently authored contributions to the same boundary composition target.

Existing declarations use `when=cf.parent(cf.with_name("orders"))` for
`OrdersWait`, with an unconditional `DefaultWait`. The parent named `invoices`
only admits the default.

| Installation order | Orders before | Invoices before | Desired after |
| --- | --- | --- | --- |
| Default, orders-specific | Orders-specific | Default | Same |
| Orders-specific, default | Default | Default | Orders-specific; invoices still default |

An explicit policy could assign fallback `0` and orders-specific `10`. An
automatic policy would have to establish the same relationship independently
of registration order. Neither approach may make the orders registration
eligible for invoices or a parentless root.

**Alternative today:** install the extension last, select it explicitly at the
consumer, or make the default negate the orders condition. If composition order
is centrally owned and already deliberate, scoring offers little benefit.
Its case is strongest when bundles should remain independent of each other's
installation order and exception lists.

## P2 — A narrower context overrides a broader context

The rules are:

- `DefaultWait`: unconditional fallback.
- `BatchWait`: parent has `workload=batch`.
- `EuropeanBatchWait`: parent has both `workload=batch` and `region=eu`.

The intended policy is explicit: EU batch workers need the regional behavior;
other batch workers need batch behavior; interactive workers need the default.
One illustrative scalar policy is `0`, `10`, and `20`, respectively.

The baseline gets every parent right only for the order default → batch → EU
batch. A successful feature should satisfy the policy for all six permutations.
The lower-level default and batch declarations should not need to know about a
regional extension that is supplied later by a different bundle.

**Alternative today:** make the predicates mutually exclusive. This is correct
and simple when one composition root owns all policies. The tradeoff is keeping
the broader predicates synchronized with independently supplied exceptions.

For automatic scoring, this example alone is insufficient justification for
counting syntax: `A & A`, `A`, and an equivalent custom predicate must not gain
different preferences merely because they are written differently. Any proposed
automatic rule needs an explicit answer for that probe before implementation.

## P3 / G2 / G3 — Know which parent is being inspected

The baseline probe exposed an important existing behavior:

```text
Worker → WaitPolicy
Worker → list[WaitPolicy] → WaitPolicy
Worker → Provider[WaitPolicy] → WaitPolicy
```

`cf.parent(...)` inspects the immediate parent. For a direct dependency that is
the worker. For a collection member or provider target it is the synthetic
collection/provider node, whose name is not the worker's name.

Consequently, P1's direct-worker rule is ineligible for those wrapper paths.
The collected policies in P1 contain only the default; the G3 provider also
resolves the default. Treating this as a ranking failure would misdiagnose the
problem.

G2 deliberately uses `orders | cf.parent(orders)`, where
`orders = cf.parent(cf.with_name("orders"))`, to cover the direct edge and the
one wrapper level in this fixture. Its observed collection is:

- default → orders registration order: `[OrdersWait, DefaultWait]`;
- orders → default registration order: `[DefaultWait, OrdersWait]`.

Both exact sequences must survive a scoring change.

P3 deliberately uses the nested parent rule for the provider target, making
both candidates eligible. It then reaches the baseline's provider ambiguity
error. The plan allows a unique preferred target to resolve this and preserves
the equal-score error. It does not convert that error into an ordinary LIFO warning.

## Cases that must not be sold as improvements

C1 matches existing repository use cases: named parents, tagged parents, and
different generic parent bindings already select different dependencies with
boolean `when` rules. These cases establish compatibility, not a reason to add
scoring.

C2 removes P1's overlap with `DefaultWait.when = ~orders`. It demonstrates that
the desired result is possible today. The proposed feature must earn its cost
through better independent composition, not a claim that existing filters
cannot express the choice.

R1 and R2 challenge the proposed defaults. A library's parent-specific policy
does not automatically outrank a later application decision, and privacy does
not automatically outrank geography or vice versa. If scores merely move
coordination from registration order into arbitrary competing numbers, record
that cost rather than counting it as a benefit.

Parentless root lookup and builder previews are also controls: the contextual
orders rule is unavailable there and the default remains the root. A score must
not manufacture a parent context. Boundary definition-site visibility,
anchored singleton plans, and decorator/pre-configuration behavior need the
existing regression coverage before any new ranking is accepted.

## How to compare after implementation

1. Reuse the same registrations, parent metadata, and consumer filters. Add
   only the proposed contextual preference declaration for the after run.
2. Execute every listed registration permutation through the real compiler.
   Record actual dependency instances, provider targets, warnings/errors,
   collection order, and explanations.
3. Compare P1 and P2 to the stated intended policy: target **2/2** and **6/6**
   correct permutations. The after runner verifies both targets.
4. Confirm C1–C3 and G1–G3 remain consistent with their contracts. Review R1 and
   R2 with an explicit application policy; do not invent an automatic winner.
5. Show the declarations required by scoring alongside the existing alternatives
   (controlled ordering, explicit consumer selection, mutually exclusive rules).
   Evaluate the coordination burden as well as line count.
6. Measure build cost on representative contextual graphs. Ordinary runtime
   resolution should gain no scoring work; inspect captured explanations without
   re-executing predicates.

Proceed only if the overlap cases represent a useful composition problem and
the proposed rule solves them without hiding the override and wrapper-context
tradeoffs. If users can express their intent more clearly with existing tools,
retaining LIFO is a valid outcome.

## Reproduction and evidence

- [Baseline probe](probes/parent_filter_baseline.py): 11 cases covering 22
  scenario/order runs using existing public APIs; no scoring implementation.
- [Recorded baseline JSON](probes/parent_filter_baseline.json): actual before
  results, including the failed provider build. This baseline file remains unchanged; separate after results are recorded below.
- Run from the repository root:
  `PYTHONPATH=. uv run python .work/probes/parent_filter_baseline.py`.
- The probe passed Ruff lint/format and ty. Five existing focused tests passed:
  named/tagged parent selection, generic-decorator dependency selection,
  boundary definition-side selection, and typed-provider ambiguity.

Repository anchors: `tests/test_complex_dependencies.py` tests
`test_can_filter_parent_based_on_registration_name`,
`test_can_filter_parent_based_on_registration_tags`, and
`test_generic_decorators_with_different_implementations_of_the_same_dependency`;
`tests/test_boundaries.py::test_alias_projects_only_after_the_complete_source_plan_is_compiled`;
`tests/test_typed_providers.py::test_provider_rejects_invalid_target_policy_missing_and_ambiguity`.

## Executed after comparison

[After runner](probes/parent_filter_after.py) and [recorded JSON](probes/parent_filter_after.json)
reuse the baseline fixture shapes, metadata and filters with declared integer values.
Run `PYTHONPATH=. uv run python .work/probes/parent_filter_after.py`.

| Case | Measured after |
| --- | --- |
| P1 | 2/2 installation orders produce OrdersWait / DefaultWait |
| P2 | 6/6 permutations produce EuropeanBatchWait / BatchWait / DefaultWait |
| P3 | Build succeeds; frozen provider target is OrdersWait |
| C1 / C2 | Both orders retain their disjoint/exclusive results |
| C3 | Equal declared values preserve latest-registration choice |
| G1 | Explicit consumer filter still selects DefaultWait |
| G2 | Both eligible policies remain in their original order |
| G3 | Direct-worker rule remains ineligible behind provider; DefaultWait wins |
| R1 default | Later application replacement wins with omitted values |
| R1 explicit | Application 30 overrides library 10 |
| R2 tied | Existing registration order decides |
| R2 explicit | Privacy 20 wins over geography 10 in both orders |

The JSON includes root/preview controls, warnings, and captured explanation codes
and values. The 47-case focused test module additionally verifies tied-provider
errors, no callback replay, and unchanged-wiring fingerprint stability.

The benefit is confined to intentionally overlapping, independently composed
policies. Coordinated integer choices still require ownership: an application
must know about a library's declared preference to override it. Controlled order
and mutually exclusive rules remain simpler when one composition root owns all
policies. Final keep/revise/drop judgment and measured cost belong to independent
review and the [performance report](14-parent-precedence-performance.md).
