# Task 06 — compiler creation and lifetime inventory

Baseline: `d51b6f569e67891e72e022b35aa5590c1c0fda46`. Source locations below refer to
that revision. The probe changes functions only inside its own process. See
[the result](06-result.md) for measured counts, mode comparisons, and readiness.

## Actual creation sites and consumers

| Category / creation | First consumer and required facts | Last consumer / retaining owner | Mode boundary |
| --- | --- | --- | --- |
| Blueprint snapshots; `_BuilderBase._build_plan` (`container.py:14264`), `_compilation_snapshot`, alias normalization (`1409`) and visibility preparation | Discovery results, exact service aliases, declaration order, origins and visibility are compiler inputs. Registration/decorator expansion produces new layers and generated definitions. | `_compile_with_report` locals retain original, expanded and prepared blueprints; compiler owns final blueprint; successful plan keeps composition only for scope builders. Caller builder is a separate owner. | Cannot omit semantic declarations because explanations are off. Duplicate mapping/layer ownership needs identity-aware accounting. |
| Registration template source inspection (`11738`, `11801`) | Source filter receives a lazy Component; accessing relationships may compile it. `finish_inspection()` closes the inspection, so later saved views cannot start compilation. Factory consumes `RegistrationInfo`. | `_TemplateSourceSelection.component` owns the completed source graph. `_check_registration_template_sources` (`11999`) reads source IDs, not its Component. Final template-source explanation conversion (`11456`) reads scalar selection facts, not the Component. | Source callbacks and application-retained source snapshots remain valid. Retaining a Component in the private expansion result supports existing full-mode tests. Reduced internal selection carriers could drop that ownership after callback completion. |
| Decorator source compilers (`12022`, `_compile_source_core` at `6182`) | Exact source specialization and dependencies, source predicate and template factory. Source graphs are frozen, undecorated, disposable inspection graphs; activation steps must not become runtime plans. | `selections` / blueprint hold graph through Component; source compiler's caches die when compiler is replaced/released. Full expansion helper returns selected and rejected source Components. | Do not skip compilation if predicates may inspect dependencies. Releasing the compiler's reference is different from invalidating a callback-held snapshot. |
| Primary `_ComponentDraft` (`components.py:183`; `_draft` at `container.py:7115`) | All Component fields support compilation, applicability predicates, ancestor/sibling/owner traversal, generic binding and failure evidence. Each occurrence retains 28 slots; eleven definition fields later become shared. | Primary graph owns every draft. Final validation and warmup use draft-backed Components in reduced mode; `_retain_runtime_graph` (`5101`) keeps the successful runtime closure and freezes only it. Failure finalization freezes all drafts (`12669`). | Already slotted. Task 05 already skips freezing discarded successful drafts. Copying all facts into draft occurrences is a representation opportunity, not proof those occurrences are unnecessary. |
| Context clones (`_clone_component_tree`, `8807`) | Rebind occurrence, parent, argument, ownership and decorator/dependency relationships while steps are reused. Mapping must preserve owner references and contextual callback views. | Clone drafts live in primary graph; per-call mapping and `_ExplanationCloneContext` die at clone completion. Invariant-subplan caches refer back to graph Components. | Shared registration/step identity does not imply equal contexts. Task 04 subtree-sharing remains reverted. No proposal here merges contextual occurrences or transient instances. |
| Undecorated predicate snapshots (`components.py:628`; caller `container.py:10156`) | Generated decorator `when` and position callbacks need a completed, undecorated connected context. Freeze exact fields; preserve ancestors/dependencies/preconfigurations/owners; hide decorator pipelines. | Local `target_view` lives through `_compile_decorators`; callback may retain it independently forever. Position preview makes another records dictionary plus one preview record. | Definition interning inside a snapshot can preserve every occurrence. Redundant record replacement can be avoided when decorator IDs already empty. Snapshot graph is still detached; do not turn it into a live view. |
| `_ComponentDefinition` / `_ComponentRecord` (`components.py:97`, `114`, `210`) | Frozen metadata used by Components and snapshot filters. Graph freezing already interns definitions by captured reference identity. | Graph records retain definitions; freeze-local interning keys die when freeze completes. Undecorated snapshots currently call `draft.freeze()` without an interning map. | Sharing only reference-identical immutable facts avoids user equality/hashing. Mutable `_generic_mapping` cache belongs to occurrence records, not shared definitions. |
| Candidate lists and `_CandidateRecord` (`_compile_candidates`, `7211`; `compile`, `6241`) | Eligibility, preference, fallback, ordering and explicit root filters determine selected roots. `_recorded_root_selection` (`11073`) still reads fallback reason codes with diagnostics off. | Root/area candidate indexes survive through entrypoint validation, errors, build rules and optional full explanations; reduced success clears them. | A scalar eligibility/fallback carrier is possible, but removing all CandidateDecision objects blindly removes facts still read for selection. Root candidates are not solely presentation. |
| Decorator decisions, `TemplateDecision`, `CompilationExplanation` (`10033–10430`) | Service selectors and predicate results determine selected decorators. Decision objects are written after outcomes, not used to choose decorators. `_capture_decorator_pattern` (`9998`) interns diagnostics-off facts after initially constructing them. | Clone remapping (`8894`), `CompiledGraph.explain_decorators` (`tooling.py:2384`), selection census (`selection_census.py:423`), build rules and failed final-validation graph. Diagnostic history separately retains original explanations. | Both explanations and diagnostics off does **not** currently mean nobody can read decorator facts: build rules can, and a failed final-validation graph can. Omitting construction requires a capability/contract decision or a complete compact capture that can materialize truthful evidence without replay. |
| Parameter, generic and occurrence explanations (`9020`, `9064`, candidate/clone sites) | Diagnostics-on explanation/census and failure details. Captured values are facts; they must not be reconstructed by running value factories or predicates. | Compiler dictionaries, decision history and plan sidecars; reduced success clears them. Clone remaps IDs and copies parameter dictionaries. | Parameter/generic capture already exits early with diagnostics off. Applying the same early return without checking readers to decorator facts would change the contract. |
| Origins (`_draft`, `7199`) | Clone provenance, issue source evidence (`_record_issue`, `5469`), budget witnesses, graph manifests, build rules and failure reports. Values frequently shared; occurrence-key dictionary is large. | Compiler and plan share origin dictionary via mapping proxies; full graph borrows it. Reduced success releases it. | Count unique origins separately from 1-origin-entry-per-occurrence. Early removal loses location/boundary evidence. Definition-origin + exception mapping is a possible smaller design, not a verified omission. |
| Provider view contexts (`components.py:304`; `_provider_view`, `container.py:6509`) | Negative IDs encode physical source plus contextual parent. Runtime/provider filters, ownership and managed acquisition views require remapped relationships. | Graph `_views` retained in runtime; closure includes physical sources and contextual parents. | No sharing change tested. Records and logical view visits are different counts. |
| Compiler caches (`5359–5468`) | Activation/invariant templates avoid repeated compilation, specialized registrations bind generics, service-target cache avoids repeated matching, managed adapters preserve shared step/owner semantics. | Compiler owns caches until `_compile_with_report` returns; partial failure/budget logic may still consult compiler. Plan sidecars alias some compiler dictionaries. | Caches are build-only but not all dictionaries can be cleared: a plan's mapping proxies often reference the same dict. Dropping caches early requires failure-path audit and cannot be credited as avoided creation. |
| Graph analysis, root/path indexes, report carriers (`_finalize_plan`, `11189`; `CompiledGraph`, `tooling.py:1874`) | Built-in entrypoint/reachability checks, build validation rules, reports. Rules can invoke arbitrary supported inspection, manifests, census and ownership analysis. | `CompiledGraph` caches can grow when inspected. Successful reduced graph is explicitly expired after instrumentation preparation (`5169`); saved scalar snapshots are caller-owned. | No validation rules or warmups in the rich fixture means their worst-case costs are not measured by its baseline. Later disabled inspection must not silently reconstruct missing facts. |
| Warmup planning (`12336`) | Select named singleton targets, establish sync/async cleanup support and compute manifest fingerprint before reduction. | Warmup info and steps remain runtime inputs; temporary path map, full manifest and build graph can be released after planning. | Actual argument/filter call counts and fingerprint must survive. Warmup-free fixture exercises the early-return path only. |
| Final graph reduction (`5101`, `5169`) | Identity walk of executable carriers plus all Component relationships establishes required closure; no arbitrary user-object traversal or callback execution. | `pending`, `seen_objects`, `seeds`, `live`, `seen_occurrences`, old drafts/records and new index overlap during the pass. Two successful passes bracket instrumentation and final reduction. | This is earlier release/freezing, not avoided construction. Its temporary sets and old/new maps must be included in peak accounting; already implemented, not a Task 06 optimization. |

## Failure and diagnostic requirements

The four flag combinations are independent. Full successful mode preserves all
current inspection whether diagnostics are on or off. Reduced successful mode
releases inspection only **after** build rules, warmup, validation and observation.
Diagnostics adds occurrence/parameter/generic history and partial candidate/edge
capture even if successful explanations are eventually disabled.

Selection exceptions capture the current request, evaluated/failed/not-examined
candidate states and original exception path. Template source/factory exceptions
are wrapped at their actual phase. Budget refusal uses captured findings and
compiler partial state; a budget can stop during preparation, compilation,
validation or diagnostic retries. Final validation failure publishes its full
compiled graph (and freezes drafts) rather than reducing it.

The existing `aggregate_errors=True` implementation already retries root
compilation (`_error_report`, `container.py:10925`). Those retries can re-invoke
selection callbacks; this investigation must preserve that existing count, not
add replay to recover omitted facts. `aggregate_errors=False` captures the failed
attempt without those retries. Template expansion itself is outside root retries.
Deferred unreachable checking does not run in reduced mode later, because later
validation is unavailable; eager requested checks must still run.

A diagnostics compaction design can share immutable captured decision content
and occurrence remapping, but must preserve per-attempt history, deterministic
order, truncation/not-examined states, target identities, and census semantics.
Task 01 intentionally kept diagnostic history eager. Turning diagnostics off or
replaying callbacks after an exception is not an acceptable memory optimization.

## Measured creation versus sampled live objects

The instrumented baseline in `evidence/06-count-baseline.json` counts constructor
calls, including short-lived objects, from fixture import through successful
build. It separately counts GC-tracked live instances at phase boundaries; those
are **sampled lower bounds on maximum live counts**, not continuous heap maxima.
Instrumentation time/peak must not be substituted for the unmodified measurement.

| Category | Created through build | Created in primary compilation | Live at primary return | Live after build + GC |
| --- | ---: | ---: | ---: | ---: |
| Component drafts | 90,250 | 88,558 | 88,558 | 0 |
| Component records | 194,306 | 183,632 | 1,692 | 8,982 |
| Component definitions | 92,104 | 91,816 | 172 | 116 |
| Candidate decisions | 1,130,498 | 1,130,498 | 488 | 0 |
| Template decisions | 1,130,440 | 1,130,440 | 430 | 0 |
| Compilation explanations | 56,565 | 56,565 | 43 | 0 |
| Remapped decorator explanations | 56,522 | 56,522 | 56,522 | 0 |
| Registration-step base initializer calls¹ | 56,708 | 56,514 | Not censused by exact subtype | 745 ordinary registration steps; 32 provider maps; 1,765 all steps |
| Compiled dependency helpers | 61,220 | 60,922 | Not censused | Runtime census in raw result |
| `_clone_component_tree` invocations | 1,352 | **0** | N/A | N/A |
| Explanation clone contexts | 488 | **0** | Not censused | 0 |

¹ Subclasses with their own generated initializer (notably provider-map steps) do not pass through the wrapped base initializer; this row is not a total of every step constructor.

Primary snapshot construction accounts for 91,816 new definitions and twice that
many records: `draft.freeze()` followed by `replace(record, decorator_ids=())`.
These are cumulative allocation counts, not concurrently live storage. Source
inspection accounts for 1,692 drafts/records across 26 graphs; the primary graph
is the 27th live graph at primary return. The final runtime has one graph.

This fixture's current primary compiler does not hit invariant subtree cloning.
The hypotheses about cloning amplification must therefore be split: repeated
contextual **compilation** produces 88,558 drafts here, but physical clone calls
happen in disposable source inspections. This evidence does not say cloning is
cheap in other compositions or justify reviving Task 04.

At primary return the largest shallow compiler containers are the origin index
(88,558 entries; 5,242,960 bytes), decorator sidecar index (56,522; 2,621,528 bytes),
activation-template cache (31,025; 1,310,800 bytes), and registration history list
(56,522; 499,960 bytes). The managed adapter memo has 1,539 entries, service-target
cache 114, decorator pattern cache 43, managed adapter source owners 26 and root
candidate groups 18. Invariant subplans, diagnostic occurrence/parameter/generic
maps and diagnostic history are empty in this mode. Their shallow totals exclude
referents and overlap with plan-owned objects; they cannot be added to inferred
savings.

## Smaller necessary representations: next design work

A compact draft could share the same eleven definition fields already shared by
frozen records, leaving occurrence/parent/owner/argument/relationship fields on
individual drafts. Replacing eleven reference slots with one definition pointer
has an **ideal shallow ceiling** of 80 bytes per draft on this interpreter:
about 6.76 MiB across 88,558 primary drafts, before definition objects, interning
keys, mutation bookkeeping and temporary overlap. That is a sizing hypothesis,
not a measured peak/RSS saving.

Draft facts are not immutable at creation: source inspection enriches service,
name, tags and implementation type (`container.py:6225`); visibility aliases and
preference evaluation temporarily replace facts (`1647`, `8023`, `8137`); cached
subplan roots are rebound (`8494`). A viable implementation must preserve these
writes through explicit definition replacement or overlays, without sharing the
mutation with another occurrence. IDs, parent/dependency topology, generic
bindings, owner references and all callback-visible fields remain per the current
contract. This is smaller necessary representation, not omission or subtree
sharing. No compact-draft probe was run, and no implementation readiness is claimed.

Likewise, origins could be indexed through shared definition provenance with
explicit per-occurrence exceptions, but source/boundary/alias/budget evidence
must remain exact. No field is proved removable merely because it is cleared
at successful reduction. The graph and origins dictionaries have separate keys
and lookup purposes; eliminating one requires a representation design, not a
blind dictionary clear.

The registration-history list is built for invariant-subplan caching even when
this fixture's generated decorators make every primary subtree unsafe to cache.
Its measured backing capacity is about 0.48 MiB. Capability-aware avoidance of
that history and key work is a narrower future candidate, but it needs a proof
that a subtree cannot later become cache-eligible, including source inspection.
This was not probed and is not counted as an achieved saving.

Activation-template interning currently constructs a registration step before its
cache lookup (`container.py:8595–8635`), then discards that new step on a hit.
Computing the same semantic key before constructing the step could avoid these
throwaway carriers after all selection/dependency/decorator work has already run.
It must keep sync support, cleanup descriptors, per-call/map exclusions and
profiling counters exact. This is a source-backed creation candidate, not a
measured result; it does not remove the strongly retained cache misses responsible
for the measured lifetime problem.


## Compiler cache payloads are not exclusively metadata

The plain weak-cache counterexample in `evidence/06-payload-lifetime.py` proves
that `_activation_templates` can be the last strong owner of a rejected derived
argument. `_ValueStep.value` (`container.py:2707`, created at `9550`) holds the
actual result, whereas its Component only records `type(value)`. The caller can
save a weak reference and observe its lifetime in a later build callback. Clearing
or weakening the whole cache early therefore changes argument/selection behavior
even when callback invocation counts, graph topology and ordinary tests match.

`_ProviderMapStep.key_indices` can likewise own keys returned by a key callback
(`_compile_provider_map`, `8660`); the corresponding graph metadata is not an
owner of every actual key. These values are opaque, not traversal targets for a
metadata optimizer. Retaining their containing cache entries is a conservative
way to preserve the current lifetime. A generalized split-payload design would
need a complete ownership inventory and targeted weak-reference/finalizer tests,
not just a list of metadata dataclasses.


The conservative probe walks only exact known registration-step carriers and
exact scalar `_ValueStep` leaves. It requires no decorators or pre-configurations
and recursively checks dependencies; provider, map, collection and unknown steps,
scalar subclasses and containers all stay strongly owned. It never introspects
an arbitrary application object. This compile-only eligibility check changes
cache ownership, not step construction, resolution work or graph occurrence IDs.
`06-value-kinds-*.json` verifies all four flag combinations for opaque values,
string subclasses, containers and provider-map keys: 16 baseline/conservative
agreements and 16 plain-cache disagreements, with unchanged callback sequences.
A future carrier type must default to strong ownership until explicitly audited.
