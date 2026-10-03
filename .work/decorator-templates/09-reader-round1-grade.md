# M09 fresh-reader round 1 — examiner grade

**Verdict: request documentation revision; comprehension gate does not pass.** Quiz score: **19/20**, with Q1–Q7 each 2/2 and no zero scores. The numerical conditions pass. Phase A, however, substantiates a missing source-ordering rule across overlay layers. The protocol separately rejects substantiated core documentation gaps. Do not record round 1 as acceptance or advance to M10.

## Frozen inputs and independence

- Examiner: `/root/m09_review`, gpt-6-astra high, independent technical reviewer; no public-document authorship.
- Reader: `/root/m09_reader_r1`, gpt-6-luna low, fresh context for Phase A; same reader for uncoached Phase B.
- Public documentation revision: `1507ef2`; technical checkpoint: `f56369a`.
- Packet, initial prompt, inventory, SHA-256 hashes: [09-reader-round1.json](09-reader-round1.json). Examiner recomputed all recorded packet-file hashes: all matched.
- Verbatim Phase A: [09-reader-round1-review.md](09-reader-round1-review.md).
- Full original questions: [09-quiz-questions.md](09-quiz-questions.md), restored from the original examiner response, replacing the abbreviated summary.
- Verbatim Phase B: [09-reader-round1-answers.md](09-reader-round1-answers.md). The numbered answers and line references below are the preserved answer evidence; none were rewritten.
- Reader reports packet-only access; coordinator reports no observed excluded reads. This records procedural isolation, not independently audited access logs.
- No public-document edits, corrections, answers, or implementation source were sent to the reader during grading.

Frozen rubric: each question 0–2; 0 incorrect/missing, 1 partly correct with substantive omission, 2 correct and supported. Pass requires at least 18/20, Q1–Q7 full marks, no zero, and no substantiated core documentation gap. No threshold changed after answers arrived.

## Per-question scores and evidence

The complete exact questions are preserved in the linked question record above. Each Q number below maps to that question and the same-numbered verbatim answer.

### Q1 — factory contract and exact binding: 2/2

Answer lines 7–16 correctly identify frozen `RegistrationInfo`, returned `DecoratorTemplate`, exact `select(cf.with_id(source.id))` binding, and no activation to enumerate. The factory fragment supplies the requested minimal binding configuration; no complete program was requested here.

Evidence: guide “One source, one target” and “Two sources and selective targets”; `_decorator_templates.py` metadata/specification classes; `container.py::_expand_decorator_templates`; same-class source and activation-free expansion tests.

Classification: correct. Corrective action: none.

### Q2 — source and target contexts: 2/2

Answer lines 18–26 correctly place both predicates and describe the parentless source, real target parent context, ordinary descendants, recursive exclusion of decorator branches, and one-component signatures.

Evidence: guide “Two sources and selective targets”; `test_real_recursive_source_filters_conditions_build_args_and_no_activation`; `test_when_snapshot_reused_recursive_undecoration_parent_context_and_scale`.

Classification: correct. Corrective action: none; a comparison table is optional presentation work.

### Q3 — membership and automatic matching: 2/2

Answer line 28 correctly selects only the explicit registration member, uses registered service contracts for automatic matching, excludes implementation-only compatibility, and denies creation of services/memberships/maps.

Evidence: guide “Explicit membership or registered-contract matching”; `_service_targets.py::_select_service_target`; group/target tests.

Classification: correct. Corrective action: none.

### Q4 — shared group identity: 2/2

Answer lines 30–43 correctly distinguish same-name objects and require one shared module/imported object; no keys or runtime group resolution. The ellipsis policy fragment is a schematic placeholder matching the guide's inline convention, not a claimed executable program.

Evidence: guide “Explicit membership or registered-contract matching”; `ServiceGroup` identity equality; `test_identity_immutability_and_per_registration_membership_across_builders`.

Classification: correct. Corrective action: none.

### Q5 — deferred discovery: 2/2

Answer lines 45–51 use the real `register_subclasses(Job, groups=[measured_jobs])` API, propagate membership, materialize discovery before expansion, acknowledge optional ensured imports, and reject discovery by selectors and postbuild mutation.

Evidence: guide membership/discovery paragraphs; generic discovery guide; `ComponentBuilder.register_subclasses`; group discovery and expansion discovery tests.

Classification: correct. Corrective action: none. “Target declarations” cites a descriptive paragraph rather than a literal heading; that minor citation imprecision does not change the supported answer.

### Q6 — generic identities and projection: 2/2

Answer line 53 correctly covers implementation bindings keyed by actual TypeVars, unknown metadata, separate registered-target projection, same-name variable independence, preserved alias/request key, and ambiguous/unresolved projection failure.

Evidence: guide “Generic identities and projection”; `RegistrationInfo.implementation_bindings`; `_select_service_target`; `test_projected_generics_partial_source_alias_distinct_same_name_variables`; generic diagnostic tests.

Classification: correct. Corrective action: none. A runnable generic example is useful but no missing conceptual rule was established.

### Q7 — source-specific applicability and deduplication: 2/2

Answer lines 55–61 correctly bind the source ID, construct a source-specific ordinary target predicate from metadata, select one cold-source layer despite repeated paths, omit the hot-source layer, and forbid fallback when exact injection fails.

The answer's optional phrase “keyed to the source ID” applies only if that exact registration appears in the ordinary target subtree; resource IDs do not automatically alias source IDs. The answer also explicitly supplies the valid name/tag correlation for the cold/hot labels, which is a correct configuration strategy for the question. “Cold registration” is imprecise shorthand; no credit is inferred for an automatic resource/source identity mapping.

Evidence: guide exact-binding, filter-context, ordering/deduplication, and error paragraphs; `test_exact_source_condition_has_no_fallback_and_runtime_callbacks_do_not_replay`; `test_nested_resource_matching_produces_one_layer_and_preserves_position`; exact-source visibility tests.

Classification: correct core answer, minor reader wording imprecision. Corrective action: no blocking repair or coaching; a future example should show the chosen resource-tag relation explicitly.

### Q8 — wrapper order and overlap: 2/2

Answer lines 63–69 correctly give `OuterTrace(Timing(Checksum(core)))`, additive independent templates, and exclusion of decorator-introduced dependencies from `when`.

Evidence: guide “Ordering, overlap, and lifecycle”; ordinary decorators “Ordering”; position and predicate-snapshot tests.

Classification: correct. Corrective action: none for this answer. This question did not ask cross-layer source ordering, so full marks do not resolve Phase A's separate gap.

### Q9 — overlays, boundaries, and callback timing: 2/2

Answer line 71 correctly describes plain-scope reuse, overlay-owned plans, new sources/targets, anchored parent singletons, unchanged boundary visibility, and preview/overlay/retry callback evaluation versus ordinary runtime activation.

Evidence: guide “Editing, overlays, and boundaries”; composition tests for inherited templates, parent anchoring, private boundaries, and repair/retry.

Classification: correct. Corrective action: none for this answer. The question asks which plans change, not exact cross-layer source order.

### Q10 — executable program and alternative: 1/2

Answer lines 73–150 provide a valid complete explicit-group program, both filters, exact binding, and meaningful assertions for two selected sources and one excluded source. It executes unchanged.

The automatic-selector changes omit importing `DerivedServices`. Applying exactly the stated two changes fails during template expansion because the factory raises `NameError`. Adding only `from clean_ioc import DerivedServices` makes the alternative execute successfully. The main program and conceptual switch are correct; the changes are incomplete runnable instructions.

Evidence: independent runs below; guide's first complete program already imports `DerivedServices`, and the comparison establishes its use.

Classification: reader error, missing import; not a missing documentation spelling/import. Corrective action: include the import in completed alternative instructions; do not coach and count the original reader as fresh.

## Independent execution

Ran `uv run python` from the checkout. Extracted the final Python block directly from the preserved answer, wrote variants in an isolated temporary directory, and executed each in a separate Python subprocess using `runpy.run_path`. The checkout was importable; no implementation source was exposed to the reader. Temporary files were removed.

| Version | Changes | Result |
| --- | --- | --- |
| Verbatim explicit program | None | Exit 0; both assertions pass |
| Literal automatic alternative | Replace selector, remove `groups=` exactly as instructed | Exit 1; `ContainerBuildError`, `template-expansion`, factory raised `NameError` |
| Examiner diagnostic control | Same changes plus `from clean_ioc import DerivedServices` | Exit 0; both assertions pass |

The control diagnoses the omission and does not retroactively correct the submitted answer.

## Phase A dispositions

1. **Compact signatures/defaults:** substantiated reference-format omission, nonblocking. Required selector/decorator fields and optional names are stated; complete calls establish minimal usage; edit methods identify replaceable fields. No demonstrated core selection/identity/ownership rule is missing from this concern. A consolidated signature summary is optional.
2. **Exact closed source-key example:** nonblocking clarity suggestion. Opening explicitly limits enumeration to one exact closed key; generic section gives `ResourceStore[Image]` and rejects open keys. Base-versus-implementation/two-key examples would help but no missing rule is established.
3. **Source/target comparison table:** nonblocking presentation suggestion. Both contexts are explicit, and Q2 transfers them correctly.
4. **Ordinary dependency/build context terminology:** nonblocking. The guide describes parent and dependency content; linked filtering docs explain the model. An illustration is optional.
5. **Overlay/inherited source order:** blocking documentation gap F1 below. The reader identifies an unspecified direction of a runtime-observable ordering rule.
6. **Group/automatic-selection decision cue:** nonblocking presentation suggestion. Existing comparison is explicit and Q3/Q4 demonstrate transfer.
7. **Runnable generic example:** nonblocking usability suggestion. Concepts/API are stated and Q6 answers them correctly. M09's required complete programs/comparison do not mandate a complete generic program in addition. Optional improvement.
8. **Diagnostic shapes and first inspection step:** nonblocking reference/navigation suggestion. Packet `compiler-tooling.md` sections “Structured build reports,” “Inspect a failed build,” and “Explain decorator templates” identify `error.report`, `error.partial_graph`, captured source fields, occurrence decisions, and early-failure limits. A direct guide link/sample would help, but the claim that the packet offers no failed-build inspection route is not substantiated. A complete serialization schema is not necessary to establish core behavior.

### F1 — explicitly state source ordering across overlay layers

Location: `docs/decorator-templates.md:156` (“Ordering, overlap, and lifecycle”), with related overlay discussion at line 164. Reader raised this in Phase A lines 19 and 30.

“Visible registration declaration order (and overlay precedence)” never says whether overlay sources are outside or inside inherited sources. The linked scopes page demonstrates normal resolution override, not generated source-layer ordering. Provider-map/generic-pattern pages specify their own newest-first orders; applying those by analogy requires undocumented inference because template sources instead use declaration order within each layer.

Implementation: `container.py::_template_sources` retains layer precedence and then sorts into declaration order within each layer. `tests/test_decorator_template_composition.py:91` asserts overlay source before root source; line 96 asserts nested-overlay source, parent-overlay source, then root source. Existing positions still determine wrapper order, and anchored singleton plans remain unchanged.

Required repair: for equal-position layers generated by one template, explicitly state nearest-overlay sources before inherited layers, retaining declaration order within each layer. Add a compact outside-to-inside illustration for an overlay-owned target (nested overlay, parent overlay, root). Preserve the higher-position rule and singleton anchoring caveat. Use independently invented identifiers; validate any executable example added.

Classification: documentation gap in core ordering/overlay semantics. This refines the earlier technical acceptance after an independent reader identified the omission; existing prose is not false, but the completeness gate is reopened for this narrow repair.

## Required next action

Author repairs F1 and runs applicable example/strict-build checks; technical reviewer rechecks the revision. Then create a newly hashed isolated packet and use an entirely NEW fresh Luna Low reader for neutral Phase A followed by a new uncoached ten-question quiz. Optional improvements above are not mandatory findings. Preserve this first-run evidence and failed gate honestly. Do not teach the original reader and count it as a fresh pass.

Examiner changed only internal quiz/grading evidence and made no commit. Public docs were unchanged during grading.
