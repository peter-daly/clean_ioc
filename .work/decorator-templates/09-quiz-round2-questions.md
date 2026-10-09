# M09 round 2 — coordinator-only quiz preparation

Examiner `/root/m09_review`, gpt-6-astra high. Prepared against public documentation revision `0457789`, before the new reader's Phase A response. Do not include this file in the public packet or supply questions before neutral Phase A completes. Send only the reader instructions and questions below to that same new reader after Phase A, without corrections, answers, rubric, or coaching.

Frozen rubric remains ten questions scored 0–2, at least 18/20, Q1–Q7 each 2/2, no zero, and no substantiated core documentation gap. Q9 explicitly retests the repaired source-order rule. No thresholds or critical topics changed.

## Reader instructions and questions

Use only the public documentation packet. Cite the supporting page and section for each answer. Explicitly distinguish anything you cannot establish from the packet. Code requested as a complete program should include its imports and locally defined types.

1. An application registers two differently configured `AlertChannel` sources using the same `QueuedChannel` implementation. Each selected source should supply an `AlertingAction` decorator around eligible `Action` targets. Describe the factory input and result, and show the minimal template configuration that ensures each decorator's `channel` argument uses its own selected registration. Explain what source enumeration activates, if anything.

2. Only channels tagged `delivery="buffered"` should produce definitions. A definition should apply only to action occurrences that have an ordinary descendant tagged `capability="alerts"`. Show both filter expressions and where they belong. Describe what each filter can inspect, including parents, descendants, and dependencies introduced by decorators. Does either filter receive both a source and a target?

3. Two registrations of `Action` share one implementation class, but only the second joins a shared `ServiceGroup`. A third registration uses an implementation inheriting `Action` under an unrelated service contract. Compare which registrations an explicit group template and `DerivedServices(Action)` can select. What effect does automatic selection have on registrations, explicit memberships, or injectable collections?

4. `action_bundle.py` and `alert_policy.py` each construct `ServiceGroup("alerted-actions", service_type=Action)`. Will membership added by the first module meet the second module's template? Show an arrangement across modules that works. Explain whether group contribution keys are needed and whether the group changes ordinary service resolution.

5. A policy is registered before a subclass-discovery rule. `PublishAction` is imported afterward, but before the builder succeeds. Show how the discovery rule contributes its generated registrations to an explicit group. Explain when discovery and template expansion occur, whether a target selector itself discovers classes, and whether importing another subclass after build changes the existing container.

6. A source registered under a closed `Channel[Notice]` service key has a statically known implementation derived from `TransportBackend[Socket]`. A target is requested through a closed alias of `Action[Input, Output]`. Explain how the factory inspects the source implementation's generic binding and how target decorator specialization is determined. Address same-named but distinct TypeVars, unavailable implementation metadata, preservation of the requested alias, ambiguous target projection, and whether open `Channel` is an equivalent `for_each` key.

7. Two configured `CachePolicy` registrations correspond to resource labels `"short"` and `"long"`. A target occurrence reaches three ordinary resources tagged with `"short"`, including one through a nested dependency, and no resource tagged with `"long"`. Explain a source-dependent target predicate and exact source binding that produce the intended layers. How many layers does one template add, and can another same-class policy substitute if the selected registration cannot be injected there?

8. Applicable decorators are declared in this order: `Annotate` at position `4`, `Validate` at position `9`, and `Measure` at position `4`. Give their outside-to-inside order. Explain the result if two distinct templates also choose the same source and target, and whether an ordinary dependency added solely by `Annotate` can make another template's `when` succeed.

9. One inherited template selects sources at three levels: root registers `Aster` then `Birch`; a child overlay registers `Cedar` then `Dahlia`; a nested overlay registers `Elm`. All five sources remain visible and selected, all generated layers have position `5`, and the target plan belongs to the nested overlay. Give the outside-to-inside source-layer order. What changes if only Birch's generated layer has position `20`? Compare this with an inherited root singleton and a plain child scope. Can a shared group expose a boundary-private source, and when may the template's filters and factory execute again?

10. Invent a small complete program in a domain of your choice using either explicit membership or automatic selection. Include a source filter, exact source argument binding, a target `when`, and assertions showing the result. Show all changes needed to switch to the other selector form. Identify any API detail needed for your program that the packet leaves unresolved.
