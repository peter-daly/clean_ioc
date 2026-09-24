# M09 fresh-reader round 2 — examiner grade

**PASS: 20/20.** Q1–Q7 each receive full marks; no zero scores. No substantiated core documentation gap remains. The new reader independently transfers the repaired overlay source-order rule and its position override. This accepts the comprehension gate for the frozen public revision `0457789`; coordinator still records/commits the gate and final handoff.

## Inputs and independence

- Examiner: `/root/m09_review`, gpt-6-astra high, independent M09 technical reviewer.
- Reader: `/root/m09_reader_r2`, gpt-6-luna low, fresh context and distinct from round 1; same reader for neutral Phase A and subsequent uncoached Phase B.
- Public revision `0457789`; technical-repair acceptance checkpoint `87529ef`.
- Packet inventory, hashes, initial prompt and access statement: [09-reader-round2.json](09-reader-round2.json). Examiner independently recomputed every recorded packet-file SHA-256 hash: all matched.
- Exact questions: [09-quiz-round2-questions.md](09-quiz-round2-questions.md). Verbatim review: [09-reader-round2-review.md](09-reader-round2-review.md). Verbatim answers: [09-reader-round2-answers.md](09-reader-round2-answers.md). Each numbered question/answer below refers to these preserved records; no answers were edited.
- Coordinator reports packet-only reads and no observed excluded access/coaching. After quiz completion the reader made an explicitly authorized write-only copy of its own answer to a temporary transcript. That does not expose new material or invalidate the run. Isolation is procedural, not an independently audited access-log guarantee.
- Frozen rubric unchanged: 0–2 per question, at least 18/20, Q1–Q7 full marks, no zero scores, and no substantiated core documentation gap.

## Question-by-question assessment

All page evidence below refers to the frozen public packet. Implementation/test evidence was available only to the examiner.

| Question | Score | Assessment and supporting evidence | Classification / corrective action |
| --- | --- | --- | --- |
| Q1 — factory/exact binding | 2/2 | Identifies frozen `RegistrationInfo`, synchronous returned specification, exact `select(cf.with_id(source.id))`, and activation-free source enumeration; shows correct factory and declaration. Guide opening and “One source, one target”; `_decorator_templates.py`, expansion implementation/tests. | Correct; none. |
| Q2 — filter contexts | 2/2 | Correct source/target filter placement, actual target parent context, parentless canonical source, ordinary dependency descendants, recursive exclusion of decorator branches, and one-component predicates. Guide “Two sources and selective targets”; recursive source and target-context tests. | Correct; none. |
| Q3 — selection modes | 2/2 | Correct registration-level opt-in, both compatible registered contracts automatically eligible, unrelated registered contract excluded, and no created services/memberships/collections. Guide “Explicit membership or registered-contract matching”; `_select_service_target` and group tests. | Correct; none. |
| Q4 — shared identity | 2/2 | Correctly requires one shared object imported by both modules, supplies membership/selector uses, distinguishes provider-map keys, and preserves ordinary resolution. Guide membership section; identity equality and group tests. | Correct; none. Schematic ellipsis is not presented as a complete program. |
| Q5 — deferred discovery | 2/2 | Real `register_subclasses(Action, groups=[alerted_actions])` API; discovery precedes expansion, selectors do not discover, postbuild class availability requires another build. Guide discovery paragraphs and generics; discovery propagation/expansion tests. | Correct; none. |
| Q6 — generic identity | 2/2 | Correct source implementation projection with actual TypeVar keys, independent target projection, unknown metadata, alias retention, ambiguity failure, and closed source key versus open `Channel`. Guide “Generic identities and projection”; projection and same-named-TypeVar tests. | Correct; none. |
| Q7 — resource matching/deduplication | 2/2 | Gives a concrete valid name-to-resource-tag policy, explicitly states the source-name assumption, selects the short source once despite three paths and excludes long, and binds by exact registration ID without fallback. Guide filter, ordering and error sections; nested-resource and exact-source tests. | Correct core answer; optional metadata caveat assessed below. No required correction. |
| Q8 — positions/overlap | 2/2 | Correct `Validate → Annotate → Measure → core`, additive independent templates, and exclusion of decorator-added dependencies from `when`. Ordinary ordering and template ordering sections; ordering/snapshot tests. | Correct; none. |
| Q9 — overlay ordering and ownership | 2/2 | Correct `Elm → Cedar → Dahlia → Aster → Birch → core`; correctly moves only Birch outside all position-5 layers when its position is 20. Preserves parent singleton anchoring, plain-scope reuse, boundary visibility and build-only callback timing. Repaired ordering section and overlay section; `_template_sources`, nested-overlay composition tests and ordinary position ordering. | Correct; none. Independently demonstrates F1 is resolved. |
| Q10 — executable transfer program | 2/2 | Complete explicit-group program includes filters, exact binding and meaningful assertions. Alternative explicitly adds the `DerivedServices` import and changes selector/removes membership. Both programs execute successfully. Guide complete programs and selector comparison. | Correct; minor prose typo only, detailed below. No substantive omission. |

Some Markdown citations have malformed closing punctuation or a mistyped temporary path, but their named pages/sections identify the supporting public text. This is citation formatting imprecision, not an incorrect conceptual claim or excluded-material access.

## Q10 execution and minor wording

Using `uv run python` from the checkout, extracted the final Python block directly from the preserved answer file, wrote it to a temporary directory, and executed it in a separate Python subprocess using `runpy.run_path`. Both assertions passed unchanged (exit 0).

For the automatic alternative, applied the stated changes: import `DerivedServices`, replace `services=actions` with `services=DerivedServices(Action)`, and remove the existing `groups` keyword argument from the `Action` registration. This program also passed both assertions (exit 0). Temporary files were removed; no implementation source was supplied to the reader.

The prose says “Remove `groups=actions`” although the complete program spells that existing argument `groups=[actions]`. This uniquely identifies the keyword to remove and does not instruct a new invalid registration or omit a required operation. It is a minor quoting typo, not a substantive partial answer. In contrast, round 1 omitted an essential import entirely and its literal changes failed at runtime. No hidden correction or new API fact was needed here.

## Phase A and additional caveat dispositions

Every concern is assessed independently of the numeric score; correct guessing would not excuse a missing core rule.

1. **Factory annotation/import path and other metadata:** a nonblocking reference usability omission. The guide explicitly names frozen `RegistrationInfo`, its five fields, tuple tags, and possible unknown implementation type. It does not demonstrate importing that optional annotation or provide the complete callable type signature. The public unannotated factory is executable and its input/output contract is established. An annotation/import example would improve the reference without repairing a missing behavioral rule.
2. **Two-source nesting explanation near the example:** nonblocking organization suggestion. The ordering section explicitly explains first source outside and the example's event order. Reader acknowledges that later section supplies the rule.
3. **Dense source/target contexts:** nonblocking presentation suggestion. Ordinary dependencies and parent differences are explicitly documented; reader acknowledges the details exist and transfers them correctly in Q2.
4. **Compatible versus non-identical registered service:** nonblocking example suggestion. The guide defines selection through derived registered contracts and contrasts implementation-only inheritance. A small subclass example would aid readers new to inheritance, but Q3 correctly applies the documented rule.
5. **Runnable generic factory example:** nonblocking usability suggestion. The source-projection API, target mapping, TypeVar identities, alias retention, unknown state, and ambiguity behavior are explicit; Q6 transfers them. A separate generic program is optional under M09's required examples.
6. **Overlay/layer terminology:** nonblocking terminology suggestion. The repaired guide states the actual order, within-layer order and ownership caveats; the linked scopes page explains overlay ownership. Q9 correctly answers a more complex five-source scenario and position override. The round-1 missing direction of source precedence is now documented, not guessed.
7. **Patch signature, boundary inheritance and IDs:** no new core gap established. The guide says the returned ID identifies the whole declaration, lists patchable fields, permits edits to visible inherited templates for the overlay's own plan without changing the parent, and reports unknown IDs. The linked boundaries section explicitly states an overlay cannot reopen or patch a parent boundary. An exposed service does not export its private template declaration. A template-specific editing example/full signature is optional reference work; the packet does not grant a cross-boundary edit route.
8. **Diagnostic samples/codes/schema:** nonblocking reference-detail suggestion. `compiler-tooling.md` documents `error.report`, `error.partial_graph`, source decisions, occurrence IDs, captured fields and early-failure limits. The template guide names broad failure cases and structured diagnostics. A complete serialization schema or condition-to-code table is not required to establish the core API behavior; a direct link/sample would improve discoverability.
9. **Source/registration/occurrence and closed-key terminology:** nonblocking learning aid. The guide distinguishes registration IDs from target occurrences and closed keys from rejected open generics; linked generics/filtering/tooling pages supply context. Q1/Q2/Q6/Q7 show correct use. A compact glossary is optional.
10. **Installation, Python/package version and execution status:** installation is present in packet `index.md`; an exact supported Python/package-version statement and execution provenance are not stated in this feature page. Those are nonblocking distribution/reference details for these independently executable examples, not missing template semantics. The technical review executed the exact published programs, and the examiner executed this reader's transfer program. No claim is made that the reader could know test results from prose alone.
11. **Additional construction/validation constraints:** no concrete missing core constraint was identified. The guide specifies selector kinds, synchronous factory contract, accepted ordinary options, immutable build behavior and error categories; ordinary decorator/argument guides cover the referenced behavior. A full signature/validation table is optional API-reference improvement.
12. **Implementation beyond public statements:** appropriate uncertainty, not a documentation defect. The gate requires the supported public contract, not access to hidden internals.
13. **Q7 metadata caveat:** the guide explicitly says `tags` is a tuple and shows `Tag` usage, so saying its representation is wholly unexplained is an overstatement. A complete tag-element field reference is not supplied at that point. The submitted code uses documented `source.name`, with its assumption explicit, and needs no unknown tag representation or invented filter API. The caveat does not undermine the correct resource-matching answer; metadata extraction examples remain optional.

These dispositions do not require public edits or coaching. Optional suggestions may be retained for future reference improvements; any future substantive public changes would require their applicable documentation gate.

## Outcome

Round 2 passes the frozen comprehension protocol. Retain round 1's failed gate record and repair history. Coordinator may record and commit this gate, then complete the M09 final handoff. Examiner wrote only this internal grading record and made no public edits or commits.
