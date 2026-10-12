# Fresh-reader documentation review and quiz

Coordinator/reviewer instructions only. Do not include this file, the work item, milestone plans, answer rubric,
integration notes, code-search findings, implementation code/tests, or earlier review transcripts in the reader packet.

Apply this gate whenever public feature documentation/examples change; M09 always uses the full protocol.
For partial documentation in earlier milestones, tailor the quiz to the concepts actually documented and retain the
same independence/no-coaching rules. Final M09 covers the whole feature.

## Isolation and agent roles

- Code search: the milestone's ordinary Luna Low. It is NOT the fresh reader.
- Author: the milestone's implementation agent. It cannot play the fresh-reader role.
- Technical reviewer/examiner: the independent Astra High review agent.
- Fresh reader: a NEW `gpt-6-luna` agent at `low`, spawned with `fork_turns="none"`.
  Do not reuse the code-search agent or any agent that has seen this feature's code, plans, conversation, or prior quiz.
- Prepare an isolated packet containing only the public docs being reviewed and the necessary public prerequisite
  documentation they link to. Preserve readable links within that packet. Do not copy repository planning or source.
  Instruct the reader to access only the packet, not the repository, web, skills about the implementation, or other tasks.
  Context isolation is procedural: record the supplied files/prompt and any observed access outside them. If the reader
  accesses excluded feature material, invalidate the run and start a fresh reader.

The reader may use ordinary Python/dependency-injection knowledge. “No prior information” means no task-specific
history or hidden implementation knowledge supplied by the coordinator. Do not promise to erase pretrained knowledge.

## Phase A — review before quiz

Use this neutral initial prompt, substituting only the packet path:

> Read only the public documentation in <packet path> as a developer encountering this feature for the first time.
> Review its clarity, completeness, examples, prerequisites, and ambiguous terminology. Give your understanding in
> your own words and identify what you cannot determine from the pages. Cite the page/section for each concern.
> Do not read repository code, tests, plans, previous conversations, or external material. Do not change files.
> Stop after your review; a separate follow-up will ask questions.

Do not include quiz questions, expected answers, conceptual hints, or a design summary in this first prompt.
Save the unedited response. Do not coach the reader or correct misconceptions before Phase B.

## Phase B — quiz the same reader

After the review arrives, send a follow-up task to that SAME agent. Ask it to answer using only the packet, to cite
supporting sections, and to say when an answer is not documented. The reader may consult the packet again.
The examiner chooses fresh names/scenarios so the quiz tests transfer rather than copying examples.

Suggested full-feature questions (give questions only, never the expected answers below):

1. A policy should create one decorator per selected registration. Explain what the factory receives and returns,
   and write the smallest configuration that binds each decorator to its own source when two sources share a class.
2. A backend source has a “remote” tag and a target has a matching dependency. Which filter would you use to restrict
   the sources, and which to restrict the targets? What component and graph does each inspect?
3. Two compatible target registrations share an implementation but only one explicitly joins a ServiceGroup.
   Which is eligible? What if the template uses DerivedServices instead? Does that create memberships or services?
4. Two bundles independently create same-name groups. Will their registrations and template meet? Show a corrected
   shared declaration and explain whether group membership needs map keys or produces a runtime collection.
5. A discovery rule runs after the template is declared. Show how generated registrations join an explicit group.
   Can either target declaration discover classes by itself or add a new service after the container is built?
6. A source is specialized by resource type, while a target is specialized by request/result type. Explain how their
   bindings stay independent and which service key is resolved after decoration. What happens to ambiguous mapping?
7. A source is registered twice with different settings; the target uses only one resource, also reachable by several
   dependency paths. Explain how exact source identity, when, and per-template deduplication determine the layers.
8. Predict the wrapper order for two positions and an equal-position tie. What happens when two separate templates
   select the same source/target? Can a dependency added only by another decorator enable the target predicate?
9. What changes in a scope overlay with a new source or target? Can a shared group expose a boundary-private service
   or rewire an already anchored parent singleton? When are template factories/filters evaluated again?
10. Write a small new example using either explicit membership or automatic selection, and show the alternative.
    Include source selection, exact binding, and target when; identify any limits or unresolved API detail in the docs.

## Examiner-only rubric

Astra High grades against accepted behaviour and the implemented API. Capture question, verbatim answer, evidence,
score, mistake classification (documentation gap, misleading prose/example, or reader error), and corrective action.
Do not infer understanding from confidence or plausible prose. Incorrect claims with citations are still incorrect.

Score each question 0–2: 0 incorrect/missing; 1 partly correct with a substantive omission; 2 correct and supported.
Pass requires at least 18/20, full marks on Q1–Q7, and no zero scores. Syntax must match the implemented API.
A substantiated documentation gap on a core concept fails the gate even if prior general knowledge produces a correct guess.

For an earlier partial-documentation gate, the examiner selects applicable questions and marks critical concepts before
the reader starts; keep that selection/rubric out of the reader's initial prompt. Use at least one transfer question for
each newly documented core concept. Score each question 0–2, require at least 90% of the available points (round the
required point count up), full marks on all designated critical questions, and no zero scores. Q1–Q7 topics are critical
whenever within the documented scope. Record exclusions and reasons; do not lower the threshold after seeing answers.
M09 and the final full-feature documentation always require all ten questions and the 18/20 rule above.

Expected concepts:

- Q1: registration metadata, returned decorator specification, one expansion per selected source identity,
  exact source argument binding; no source activation to enumerate.
- Q2: source_filter sees the agreed undecorated source context; when sees each undecorated target occurrence.
  Real descendant semantics and the documented parent context; neither is a two-argument predicate.
- Q3: explicit membership belongs to a registration; automatic matching uses registered service contracts.
  DerivedServices does not create services or modify group memberships.
- Q4: group object identity, shared import/reference, no map keys or injectable collection.
- Q5: discovery contribution propagation; matching after queued discovery/closed requests; no runtime hot registration.
- Q6: independent generic identities, contract projection, preserved target service key, diagnostic on ambiguity.
- Q7: exact configured registration rather than class/name equivalence; independent ordinary when decisions;
  one layer per source/template/target occurrence rather than resource path.
- Q8: existing position/tie rules, separate templates additive, target predicates exclude decorator-introduced dependencies.
- Q9: overlay-owned recompilation and visibility rules, parent anchoring, plain-scope reuse, pure build callbacks may
  rerun on compilation/retries but ordinary runtime activation does not perform new composition.
- Q10: an internally consistent original example, runnable when intended, no invented runtime map/alias behaviour.

The examiner may execute the submitted example against the working implementation in isolation; do not reveal source
code to the reader to make it work. Review any errors for missing imports/prerequisites in the docs as well as API misuse.

## Revise and repeat

Record the first run honestly even if it fails. The author fixes demonstrated documentation gaps, examples are rerun,
and Astra rechecks correctness. Start a NEW fresh Luna Low reader for revised docs, again with Phase A then Phase B.
Do not teach the original reader and count its improved answer as a fresh comprehension pass.
Use equivalent new scenarios on retest; record documentation revision/hash, packet manifest, agent/model/effort,
initial review, quiz/answers, scores, and technical verdict internally. If a gate cannot pass, keep the milestone open.
